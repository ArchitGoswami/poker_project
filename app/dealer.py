"""Tracks a real table and prices the hand you are holding."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from app.engine import (
    STREET_LABEL,
    Card,
    GameError,
    best_hand,
    card_name,
    cards_phrase,
    estimate_equity,
    hand_name,
    hole_name,
    parse_card,
)

RANK_WORD = {
    "ace": "A", "king": "K", "queen": "Q", "jack": "J", "ten": "T",
    "nine": "9", "eight": "8", "seven": "7", "six": "6", "five": "5",
    "four": "4", "three": "3", "two": "2", "deuce": "2",
}
SUIT_WORD = {
    "spades": "s", "spade": "s", "hearts": "h", "heart": "h",
    "diamonds": "d", "diamond": "d", "clubs": "c", "club": "c",
}
WORD_CARD = re.compile(
    r"\b(ace|king|queen|jack|ten|nine|eight|seven|six|five|four|three|two|deuce)"
    r"\s+(?:of\s+)?(spades|hearts|diamonds|clubs|spade|heart|diamond|club)\b",
    re.I,
)
CODE_CARD = re.compile(r"\b(10|[AKQJT2-9])([shdc])\b", re.I)
HERO_WORDS = {"i", "me", "my", "i'll", "ill", "i'm", "im"}


class DealerError(GameError):
    pass


@dataclass
class Seat:
    name: str
    stack: int
    bet: int = 0
    folded: bool = False
    all_in: bool = False
    hole: list[Card] = field(default_factory=list)


class DealerSession:
    def __init__(self, names: list[str], stack: int, hero: int, sb: int, bb: int, session_id: str):
        if not 2 <= len(names) <= 6:
            raise DealerError("A live table needs two to six players.")
        if hero < 0 or hero >= len(names):
            raise DealerError("Pick which seat is you.")
        self.id = session_id
        self.players = [Seat(name, stack) for name in names]
        self.hero = hero
        self.sb = sb
        self.bb = bb
        self.button = self._button_for_hero_bb()
        self.hand_number = 0
        self.board: list[Card] = []
        self.pot = 0
        self.current_bet = 0
        self.street = "waiting"
        self.log: list[str] = []
        self.history: list[dict] = []
        self.rng = random.Random()

    def command(self, event: dict) -> str:
        if event.get("type") == "undo":
            self._undo()
            return "Undid that."
        snap = self.to_state()
        try:
            heard = self._apply(event)
        except DealerError:
            self._load(snap)
            raise
        self.history.append(snap)
        self.history = self.history[-30:]
        self.log.append(heard)
        self.log = self.log[-30:]
        return heard

    def public(self) -> dict:
        hero = self.players[self.hero]
        return {
            "id": self.id,
            "street": self.street,
            "street_label": STREET_LABEL.get(self.street, self.street),
            "pot": self.pot,
            "current_bet": self.current_bet,
            "to_call": max(0, self.current_bet - hero.bet),
            "board": [card.code() for card in self.board],
            "button": self.button,
            "hero": self.hero,
            "sb": self.sb,
            "bb": self.bb,
            "log": self.log[-16:],
            "players": [
                {
                    "name": seat.name,
                    "stack": seat.stack,
                    "bet": seat.bet,
                    "folded": seat.folded,
                    "all_in": seat.all_in,
                    "hole": [card.code() for card in seat.hole],
                    "hero": index == self.hero,
                }
                for index, seat in enumerate(self.players)
            ],
            "advice": self.advice(),
        }

    def advice(self) -> dict:
        hero = self.players[self.hero]
        if hero.folded:
            return {
                "suggestion": "Folded",
                "reason": "You are out of this hand. The station will keep tracking the others.",
                "equity": None,
                "hand": None,
                "to_call": 0,
            }
        if len(hero.hole) < 2:
            return {
                "suggestion": "Hold on",
                "reason": "Tell me your two cards, by voice or by tapping them, and I can price the hand.",
                "equity": None,
                "hand": None,
                "to_call": max(0, self.current_bet - hero.bet),
            }
        opponents = max(1, sum(1 for seat in self.players if not seat.folded) - 1)
        equity = estimate_equity(hero.hole, self.board, opponents, self.rng)
        label = self._label(hero.hole)
        to_call = max(0, self.current_bet - hero.bet)
        suggestion, reason = _suggest(equity, to_call, self.pot, label)
        return {
            "suggestion": suggestion,
            "reason": reason,
            "equity": round(equity, 3),
            "hand": label,
            "to_call": to_call,
        }

    def to_state(self) -> dict:
        return {
            "players": [
                {
                    "name": seat.name,
                    "stack": seat.stack,
                    "bet": seat.bet,
                    "folded": seat.folded,
                    "all_in": seat.all_in,
                    "hole": [card.code() for card in seat.hole],
                }
                for seat in self.players
            ],
            "board": [card.code() for card in self.board],
            "pot": self.pot,
            "current_bet": self.current_bet,
            "street": self.street,
            "button": self.button,
            "hand_number": self.hand_number,
            "log": list(self.log),
        }

    def _apply(self, event: dict) -> str:
        kind = event.get("type")
        if kind == "new_hand":
            self._new_hand()
            return f"New hand. Blinds are {self.sb} and {self.bb}."
        if kind == "pot":
            self.pot = int(event["amount"])
            return f"Pot set to {self.pot}."
        if kind == "blinds":
            if event.get("sb"):
                self.sb = int(event["sb"])
            if event.get("bb"):
                self.bb = int(event["bb"])
            return f"Blinds are {self.sb} and {self.bb}."
        if kind == "stack":
            seat = self._resolve(event.get("name"))
            seat.stack = max(0, int(event["amount"]))
            return f"{seat.name} has {seat.stack} behind."
        if kind == "clear_hole":
            seat = self._resolve(event.get("name"))
            seat.hole = []
            return f"Cleared {seat.name}'s cards."
        if kind == "clear_board":
            self.board = []
            self.street = "preflop"
            return "Cleared the board."
        if kind == "add_card":
            return self._add_card(parse_card(event["card"]), event.get("target") or "board")
        if kind == "hole":
            cards = [parse_card(code) for code in event.get("cards") or []]
            if len(cards) != 2:
                raise DealerError("A player needs two hole cards.")
            seat = self._resolve(event.get("name"))
            seat.hole = cards
            self._unique()
            return f"{seat.name} has {cards_phrase(cards)}."
        if kind == "board":
            cards = [parse_card(code) for code in event.get("cards") or []]
            return self._set_board(event.get("street") or "board", cards)
        if kind == "action":
            return self._action(event.get("name"), event.get("verb"), event.get("amount"))
        raise DealerError("I didn't catch that. Try 'Alex calls' or 'flop ace of spades king of hearts two of clubs'.")

    def _new_hand(self) -> None:
        if sum(seat.stack > 0 for seat in self.players) < 2:
            raise DealerError("Need at least two players with chips.")
        if self.hand_number > 0:
            self.button = self._next_with_chips(self.button)
        self.hand_number += 1
        self.board = []
        self.pot = 0
        self.current_bet = 0
        self.street = "preflop"
        for seat in self.players:
            seat.bet = 0
            seat.folded = False
            seat.all_in = False
            seat.hole = []
        self._post_blinds()

    def _post_blinds(self) -> None:
        if sum(seat.stack > 0 for seat in self.players) < 2:
            raise DealerError("Need at least two players with chips.")
        if len([seat for seat in self.players if seat.stack > 0]) == 2:
            sb_index = self.button if self.players[self.button].stack > 0 else self._next_with_chips(self.button)
            bb_index = self._next_with_chips(sb_index)
        else:
            sb_index = self._next_with_chips(self.button)
            bb_index = self._next_with_chips(sb_index)
        self._commit(self.players[sb_index], min(self.sb, self.players[sb_index].stack))
        self._commit(self.players[bb_index], min(self.bb, self.players[bb_index].stack + self.players[bb_index].bet) - self.players[bb_index].bet)
        self.current_bet = max(seat.bet for seat in self.players)

    def _commit(self, seat: Seat, pay: int) -> None:
        pay = min(seat.stack, pay)
        seat.stack -= pay
        seat.bet += pay
        self.pot += pay
        if seat.stack == 0 and pay > 0:
            seat.all_in = True

    def _action(self, name: str | None, verb: str, amount) -> str:
        seat = self._resolve(name)
        verb = (verb or "").lower()
        if verb == "fold":
            seat.folded = True
            return f"{seat.name} folds."
        if verb == "check":
            if seat.bet < self.current_bet:
                raise DealerError(f"{seat.name} still owes {self.current_bet - seat.bet}.")
            return f"{seat.name} checks."
        if verb == "call":
            due = max(0, self.current_bet - seat.bet)
            if due == 0:
                return f"{seat.name} checks."
            pay = min(due, seat.stack)
            self._commit(seat, pay)
            return f"{seat.name} calls {pay}."
        if verb in ("raise", "bet", "allin"):
            if verb == "allin":
                target = seat.bet + seat.stack
            else:
                if amount is None:
                    raise DealerError("Say the amount, as in 'raises to 60'.")
                target = int(amount)
            if target <= seat.bet:
                raise DealerError("That amount is already in front of them.")
            pay = target - seat.bet
            if pay > seat.stack:
                raise DealerError(f"{seat.name} only has {seat.stack} behind.")
            self._commit(seat, pay)
            if seat.bet > self.current_bet:
                self.current_bet = seat.bet
            if seat.all_in:
                return f"{seat.name} is all in for {seat.bet}."
            if verb == "bet":
                return f"{seat.name} bets {seat.bet}."
            return f"{seat.name} raises to {seat.bet}."
        raise DealerError("I can track fold, check, call, bet, and raise.")

    def _set_board(self, street: str, cards: list[Card]) -> str:
        street = street.lower()
        if street == "flop":
            if len(cards) != 3:
                raise DealerError("A flop is three cards.")
            self.board = cards
            new_street = "flop"
        elif street == "turn":
            if len(cards) == 1 and len(self.board) == 3:
                self.board = self.board + cards
            elif len(cards) == 4:
                self.board = cards
            else:
                raise DealerError("The turn is one more card, after a flop.")
            new_street = "turn"
        elif street == "river":
            if len(cards) == 1 and len(self.board) == 4:
                self.board = self.board + cards
            elif len(cards) == 5:
                self.board = cards
            else:
                raise DealerError("The river is one more card, after a turn.")
            new_street = "river"
        else:
            if len(cards) not in (3, 4, 5):
                raise DealerError("The board needs three, four, or five cards.")
            self.board = cards
            new_street = {3: "flop", 4: "turn", 5: "river"}[len(cards)]
        self._unique()
        order = {"waiting": 0, "preflop": 0, "flop": 1, "turn": 2, "river": 3}
        if order[new_street] > order.get(self.street, 0):
            self._reset_street_bets()
        self.street = new_street
        return f"{new_street.capitalize()}: {cards_phrase(self.board)}."

    def _add_card(self, card: Card, target: str) -> str:
        if target == "hero":
            seat = self.players[self.hero]
            if len(seat.hole) >= 2:
                raise DealerError("You already have two cards. Clear them to replace the hand.")
            seat.hole.append(card)
            self._unique()
            return f"Your card: {card_name(card)}."
        if len(self.board) >= 5:
            raise DealerError("The board already has five cards.")
        self.board.append(card)
        self._unique()
        order = {"waiting": 0, "preflop": 0, "flop": 1, "turn": 2, "river": 3}
        if len(self.board) >= 3:
            new_street = {3: "flop", 4: "turn", 5: "river"}[len(self.board)]
            if order[new_street] > order.get(self.street, 0):
                self._reset_street_bets()
            self.street = new_street
        return f"Board card: {card_name(card)}."

    def _reset_street_bets(self) -> None:
        for seat in self.players:
            seat.bet = 0
        self.current_bet = 0

    def _unique(self) -> None:
        seen: list[Card] = list(self.board)
        for seat in self.players:
            seen.extend(seat.hole)
        if len(seen) != len(set(seen)):
            raise DealerError("That card is already on the table.")

    def _resolve(self, name: str | None) -> Seat:
        if name is None or name.strip().lower() in HERO_WORDS:
            return self.players[self.hero]
        key = name.strip().lower()
        hits = [seat for seat in self.players if seat.name.lower() == key or seat.name.lower().startswith(key)]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise DealerError(f"I don't see a player named {name}.")
        raise DealerError("More than one player matches that name.")

    def _label(self, hole: list[Card]) -> str:
        cards = hole + self.board
        if len(cards) >= 5:
            score, _combo = best_hand(cards)
            return hand_name(score)
        return hole_name(hole)

    def _next_with_chips(self, start: int) -> int:
        count = len(self.players)
        for step in range(1, count + 1):
            index = (start + step) % count
            if self.players[index].stack > 0:
                return index
        raise DealerError("Need at least two players with chips.")

    def _button_for_hero_bb(self) -> int:
        count = len(self.players)
        if count == 2:
            return (self.hero + 1) % 2
        return (self.hero - 2) % count

    def _undo(self) -> None:
        if not self.history:
            raise DealerError("Nothing to undo.")
        self._load(self.history.pop())

    def _load(self, state: dict) -> None:
        self.board = [parse_card(code) for code in state["board"]]
        self.pot = state["pot"]
        self.current_bet = state["current_bet"]
        self.street = state["street"]
        self.button = state["button"]
        self.hand_number = state["hand_number"]
        self.log = list(state["log"])
        for seat, raw in zip(self.players, state["players"]):
            seat.name = raw["name"]
            seat.stack = raw["stack"]
            seat.bet = raw["bet"]
            seat.folded = raw["folded"]
            seat.all_in = raw["all_in"]
            seat.hole = [parse_card(code) for code in raw["hole"]]


def interpret(text: str) -> dict:
    raw = " ".join((text or "").strip().split())
    if not raw:
        return {"type": "unknown", "text": text or ""}
    low = raw.lower()
    if low in {"undo", "undo that", "go back"}:
        return {"type": "undo"}
    if low in {"new hand", "next hand", "deal", "new deal"}:
        return {"type": "new_hand"}
    match = re.match(r"^pot(?:\s+is)?\s+(\d+)$", low)
    if match:
        return {"type": "pot", "amount": int(match.group(1))}
    match = re.match(r"^small blind\s+(\d+)$", low)
    if match:
        return {"type": "blinds", "sb": int(match.group(1))}
    match = re.match(r"^big blind\s+(\d+)$", low)
    if match:
        return {"type": "blinds", "bb": int(match.group(1))}
    match = re.match(r"^(flop|turn|river|board)\b", low)
    if match:
        return {"type": "board", "street": match.group(1), "cards": extract_cards(raw)}
    match = re.match(r"^(my cards|i have|i've got|ive got)\b", low)
    if match:
        return {"type": "hole", "name": None, "cards": extract_cards(raw)}
    if extract_cards(raw):
        match = re.match(r"^(.+?)\s+(?:has|have|holds)\b", raw, re.I)
        if match:
            return {"type": "hole", "name": match.group(1).strip(), "cards": extract_cards(raw)}
    match = re.match(
        r"^(?:(.+?)\s+)?(folds?|checks?|calls?|bets?|raises?|all[\s-]?in|shoves?)"
        r"(?:\s+(?:to\s+)?(\d+))?$",
        low,
    )
    if match:
        name = match.group(1)
        if name and name.strip() in HERO_WORDS:
            name = None
        return {
            "type": "action",
            "name": name.strip() if name else None,
            "verb": _verb(match.group(2)),
            "amount": int(match.group(3)) if match.group(3) else None,
        }
    cards = extract_cards(raw)
    if len(cards) == 2:
        return {"type": "hole", "name": None, "cards": cards}
    if len(cards) >= 3:
        return {"type": "board", "street": "board", "cards": cards}
    return {"type": "unknown", "text": raw}


def extract_cards(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    spans: list[tuple[int, int]] = []
    for match in WORD_CARD.finditer(text):
        rank = RANK_WORD[match.group(1).lower()]
        suit = SUIT_WORD[match.group(2).lower()]
        found.append((match.start(), rank + suit))
        spans.append((match.start(), match.end()))
    for match in CODE_CARD.finditer(text):
        if any(start <= match.start() < end for start, end in spans):
            continue
        rank = match.group(1).upper()
        if rank == "10":
            rank = "T"
        found.append((match.start(), rank + match.group(2).lower()))
    found.sort()
    return [code for _index, code in found]


def _verb(token: str) -> str:
    token = token.lower().replace("-", "").replace(" ", "")
    if token.startswith("fold"):
        return "fold"
    if token.startswith("check"):
        return "check"
    if token.startswith("call"):
        return "call"
    if token.startswith("bet"):
        return "bet"
    if token.startswith("raise"):
        return "raise"
    return "allin"


def _suggest(equity: float, to_call: int, pot: int, label: str) -> tuple[str, str]:
    percent = round(equity * 100)
    if to_call <= 0:
        if equity >= 0.62:
            return "Bet", f"You have {label}. That wins about {percent}% of the time against a random hand, which is enough to bet."
        return "Check", f"You have {label}. Nothing is owed, and checking keeps the pot where it is."
    price = to_call / (pot + to_call) if (pot + to_call) else 1
    need = round(price * 100)
    if equity + 0.03 < price and equity < 0.45:
        return "Fold", f"You have {label}. The bet asks for about {need}%, and this hand wins about {percent}%."
    if equity > price + 0.16 and equity >= 0.58:
        return "Raise", f"You have {label}. You win about {percent}% from here, which is ahead of the {need}% the bet is charging."
    return "Call", f"You have {label}. You need about {need}% to call, and this hand wins about {percent}%."
