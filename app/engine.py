"""Texas hold'em cards, hand ranks, and a betting table."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from itertools import combinations

RANKS = "23456789TJQKA"
SUITS = "shdc"
BETTING = {"preflop", "flop", "turn", "river"}

RANK_NAMES = {
    14: "ace", 13: "king", 12: "queen", 11: "jack", 10: "ten",
    9: "nine", 8: "eight", 7: "seven", 6: "six", 5: "five",
    4: "four", 3: "three", 2: "two",
}
RANK_PLURAL = {
    14: "aces", 13: "kings", 12: "queens", 11: "jacks", 10: "tens",
    9: "nines", 8: "eights", 7: "sevens", 6: "sixes", 5: "fives",
    4: "fours", 3: "threes", 2: "twos",
}
SUIT_NAMES = {"s": "spades", "h": "hearts", "d": "diamonds", "c": "clubs"}
STREET_LABEL = {
    "waiting": "Waiting",
    "preflop": "Pre-flop",
    "flop": "Flop",
    "turn": "Turn",
    "river": "River",
    "showdown": "Showdown",
    "complete": "Hand over",
}


class GameError(Exception):
    pass


@dataclass(frozen=True)
class Card:
    rank: int
    suit: str

    def code(self) -> str:
        return RANKS[self.rank - 2] + self.suit


def full_deck() -> list[Card]:
    return [Card(rank, suit) for rank in range(2, 15) for suit in SUITS]


def parse_card(token: str) -> Card:
    token = token.strip()
    if len(token) >= 3 and token[:2].upper() == "10":
        rank_ch, suit = "T", token[2]
    else:
        rank_ch, suit = token[0], token[1]
    rank_ch = rank_ch.upper()
    suit = suit.lower()
    if rank_ch not in RANKS or suit not in SUITS:
        raise GameError(f"I don't know the card {token}.")
    return Card(RANKS.index(rank_ch) + 2, suit)


def parse_cards(text: str) -> list[Card]:
    return [parse_card(tok) for tok in text.split()]


def card_name(card: Card) -> str:
    return f"{RANK_NAMES[card.rank]} of {SUIT_NAMES[card.suit]}"


def cards_phrase(cards: list[Card]) -> str:
    names = [card_name(card) for card in cards]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + ", and " + names[-1]


def hole_name(hole: list[Card]) -> str:
    high, low = sorted(hole, key=lambda card: card.rank, reverse=True)
    if high.rank == low.rank:
        return f"a pair of {RANK_PLURAL[high.rank]}"
    texture = "suited" if high.suit == low.suit else "offsuit"
    return f"{RANK_NAMES[high.rank]}-{RANK_NAMES[low.rank]} {texture}"


def evaluate_five(cards: list[Card]) -> tuple:
    ranks = sorted((card.rank for card in cards), reverse=True)
    flush = len({card.suit for card in cards}) == 1
    unique = sorted(set(ranks), reverse=True)
    straight = False
    straight_high = 0
    if len(unique) == 5:
        if unique[0] - unique[4] == 4:
            straight = True
            straight_high = unique[0]
        elif unique == [14, 5, 4, 3, 2]:
            straight = True
            straight_high = 5
    counts: dict[int, int] = {}
    for rank in ranks:
        counts[rank] = counts.get(rank, 0) + 1
    groups = sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    pattern = tuple(sorted(counts.values(), reverse=True))
    if straight and flush:
        return (8, (straight_high,))
    if pattern == (4, 1):
        return (7, (groups[0][0], groups[1][0]))
    if pattern == (3, 2):
        return (6, (groups[0][0], groups[1][0]))
    if flush:
        return (5, tuple(ranks))
    if straight:
        return (4, (straight_high,))
    if pattern == (3, 1, 1):
        return (3, (groups[0][0], groups[1][0], groups[2][0]))
    if pattern == (2, 2, 1):
        pairs = sorted((rank for rank, count in groups if count == 2), reverse=True)
        kicker = next(rank for rank, count in groups if count == 1)
        return (2, (pairs[0], pairs[1], kicker))
    if pattern == (2, 1, 1, 1):
        kickers = tuple(rank for rank, count in groups if count == 1)
        return (1, (groups[0][0],) + kickers)
    return (0, tuple(ranks))


def best_hand(cards: list[Card]) -> tuple[tuple, tuple[Card, ...]]:
    if len(cards) < 5:
        raise GameError("A hand needs five cards.")
    best_score = None
    best_combo: tuple[Card, ...] = ()
    for combo in combinations(cards, 5):
        score = evaluate_five(list(combo))
        if best_score is None or score > best_score:
            best_score = score
            best_combo = combo
    return best_score, best_combo


def hand_name(score: tuple) -> str:
    category, tie = score
    if category == 8:
        if tie[0] == 14:
            return "a royal flush"
        return f"a {RANK_NAMES[tie[0]]}-high straight flush"
    if category == 7:
        return f"four {RANK_PLURAL[tie[0]]}"
    if category == 6:
        return f"{RANK_PLURAL[tie[0]]} full of {RANK_PLURAL[tie[1]]}"
    if category == 5:
        return f"a {RANK_NAMES[tie[0]]}-high flush"
    if category == 4:
        return f"a {RANK_NAMES[tie[0]]}-high straight"
    if category == 3:
        return f"three {RANK_PLURAL[tie[0]]}"
    if category == 2:
        return f"two pair, {RANK_PLURAL[tie[0]]} and {RANK_PLURAL[tie[1]]}"
    if category == 1:
        return f"a pair of {RANK_PLURAL[tie[0]]}"
    return f"{RANK_NAMES[tie[0]]} high"


def estimate_equity(
    hole: list[Card],
    board: list[Card],
    opponents: int,
    rng: random.Random,
    iters: int = 160,
) -> float:
    if len(hole) != 2 or opponents < 1:
        return 0.5
    known = set(hole + board)
    deck = [card for card in full_deck() if card not in known]
    need_board = 5 - len(board)
    need = opponents * 2 + need_board
    if need > len(deck) or need_board < 0:
        return 0.5
    wins = 0.0
    for _ in range(iters):
        draw = rng.sample(deck, need)
        index = 0
        full_board = board + draw[index:index + need_board]
        index += need_board
        hero_score, _ = best_hand(hole + full_board)
        best_opp = None
        for _opp in range(opponents):
            opp_hole = draw[index:index + 2]
            index += 2
            opp_score, _ = best_hand(list(opp_hole) + full_board)
            if best_opp is None or opp_score > best_opp:
                best_opp = opp_score
        if hero_score > best_opp:
            wins += 1
        elif hero_score == best_opp:
            wins += 0.5
    return wins / iters


@dataclass
class Player:
    id: str
    name: str
    stack: int
    seat: int
    is_bot: bool = False
    style: str | None = None
    looseness: int = 50
    aggression: int = 50
    bluff: int = 10
    hole: list[Card] = field(default_factory=list)
    bet: int = 0
    total_bet: int = 0
    folded: bool = False
    all_in: bool = False
    acted: bool = False
    busted: bool = False


class Game:
    def __init__(
        self,
        players: list[Player],
        sb: int = 10,
        bb: int = 20,
        rng: random.Random | None = None,
        button: int = 0,
    ):
        self.players = players
        self.sb = sb
        self.bb = bb
        self.rng = rng or random.Random()
        self.button = button
        self.street = "waiting"
        self.board: list[Card] = []
        self.pot = 0
        self.current_bet = 0
        self.min_raise = bb
        self.to_act_index: int | None = None
        self.hand_number = 0
        self.log_lines: list[str] = []
        self.last_result: dict | None = None
        self.sb_index: int | None = None
        self.bb_index: int | None = None
        self.deck: list[Card] = []

    def start_hand(self) -> None:
        if self.street not in ("waiting", "showdown", "complete"):
            raise GameError("The hand is still going.")
        if sum(player.stack > 0 for player in self.players) < 2:
            raise GameError("Need at least two players with chips.")
        for player in self.players:
            player.hole = []
            player.bet = 0
            player.total_bet = 0
            player.folded = False
            player.all_in = False
            player.acted = False
            player.busted = player.stack <= 0
        if self.hand_number == 0:
            if self.players[self.button].busted:
                nxt = self._next_index(self.button, lambda player: not player.busted)
                if nxt is None:
                    raise GameError("Need at least two players with chips.")
                self.button = nxt
        else:
            nxt = self._next_index(self.button, lambda player: not player.busted)
            if nxt is None:
                raise GameError("Need at least two players with chips.")
            self.button = nxt
        self.hand_number += 1
        self.board = []
        self.pot = 0
        self.last_result = None
        self.deck = full_deck()
        self.rng.shuffle(self.deck)
        self._log(f"Hand {self.hand_number}")
        self._post_blinds()
        self._deal_hole()
        self.street = "preflop"
        self.current_bet = max(player.bet for player in self.players)
        self.min_raise = self.bb
        self.to_act_index = self._next_index(
            self.bb_index if self.bb_index is not None else self.button,
            lambda player: not player.busted and not player.all_in,
        )
        self._progress()

    def act(self, player_id: str, action: str, amount: int | None = None) -> None:
        if self.street not in BETTING:
            raise GameError("The betting is closed.")
        if self.to_act_index is None:
            raise GameError("Nobody needs to act.")
        player = self.players[self.to_act_index]
        if player.id != player_id:
            raise GameError("It isn't your turn.")
        action = (action or "").lower()
        legal = self.legal_for(player)
        if action == "allin":
            if legal["can_raise"]:
                action = "raise"
                amount = player.bet + player.stack
            elif legal["call"]:
                action = "call"
            elif legal["check"]:
                action = "check"
            else:
                action = "fold"
        if action == "fold":
            player.folded = True
            player.acted = True
            self._log(f"{player.name} folds")
        elif action == "check":
            if not legal["check"]:
                raise GameError("You can call, fold, or raise.")
            player.acted = True
            self._log(f"{player.name} checks")
        elif action == "call":
            if not legal["call"]:
                raise GameError("There is nothing to call.")
            paid = self._pay_to(player, player.bet + legal["call_amount"])
            player.acted = True
            if player.all_in:
                self._log(f"{player.name} calls {paid}, all in")
            else:
                self._log(f"{player.name} calls {paid}")
        elif action in ("raise", "bet"):
            if not legal["can_raise"]:
                raise GameError("You can't raise.")
            if amount is None:
                raise GameError("Choose an amount to raise to.")
            self._raise_to(player, int(amount), legal)
        else:
            raise GameError("That action isn't part of the game.")
        self._progress()

    def legal_for(self, player: Player) -> dict:
        to_call = max(0, self.current_bet - player.bet)
        call_amount = min(to_call, player.stack)
        max_raise_to = player.bet + player.stack
        min_full = self.current_bet + self.min_raise
        can_raise = player.stack > to_call and max_raise_to > self.current_bet
        min_raise_to = min(min_full, max_raise_to) if can_raise else None
        return {
            "fold": True,
            "check": to_call == 0,
            "call": to_call > 0 and call_amount > 0,
            "call_amount": call_amount,
            "can_raise": can_raise,
            "min_raise_to": min_raise_to,
            "max_raise_to": max_raise_to if can_raise else None,
        }

    def add_player(self, player: Player) -> None:
        if self.street not in ("waiting", "showdown", "complete"):
            raise GameError("Wait until the hand is over to sit down.")
        if len(self.players) >= 6:
            raise GameError("The table is full.")
        if any(existing.name.lower() == player.name.lower() for existing in self.players):
            raise GameError("Someone already has that name.")
        player.seat = len(self.players)
        self.players.append(player)

    def snapshot(self, viewer_id: str | None, reveal_all: bool = False) -> dict:
        players = []
        for player in self.players:
            hole = self._hole_view(player, viewer_id, reveal_all)
            visible = bool(hole) and "??" not in hole
            players.append({
                "id": player.id,
                "name": player.name,
                "stack": player.stack,
                "bet": player.bet,
                "folded": player.folded,
                "all_in": player.all_in,
                "busted": player.busted,
                "is_bot": player.is_bot,
                "style": player.style,
                "hole": hole,
                "hand_name": self._hand_label(player) if visible else None,
            })
        actor_id = None
        legal = None
        if self.to_act_index is not None and self.street in BETTING:
            actor = self.players[self.to_act_index]
            actor_id = actor.id
            if viewer_id == actor.id:
                legal = self.legal_for(actor)
        button_id = self.players[self.button].id if self.players else None
        sb_id = self.players[self.sb_index].id if self.sb_index is not None else None
        bb_id = self.players[self.bb_index].id if self.bb_index is not None else None
        return {
            "street": self.street,
            "street_label": STREET_LABEL.get(self.street, self.street),
            "pot": self.pot,
            "board": [card.code() for card in self.board],
            "button": button_id,
            "sb": sb_id,
            "bb": bb_id,
            "sb_amount": self.sb,
            "bb_amount": self.bb,
            "current_bet": self.current_bet,
            "hand_number": self.hand_number,
            "actor_id": actor_id,
            "legal": legal,
            "log": self.log_lines[-24:],
            "last_result": self.last_result,
            "players": players,
        }

    def _hole_view(self, player: Player, viewer_id: str | None, reveal_all: bool) -> list[str]:
        if not player.hole:
            return []
        mine = viewer_id is not None and player.id == viewer_id
        if reveal_all or mine or (self.street == "showdown" and not player.folded):
            return [card.code() for card in player.hole]
        return ["??"] * len(player.hole)

    def _hand_label(self, player: Player) -> str | None:
        if len(player.hole) < 2:
            return None
        cards = player.hole + self.board
        if len(cards) >= 5:
            score, _combo = best_hand(cards)
            return hand_name(score)
        if not self.board:
            return hole_name(player.hole)
        return None

    def _post_blinds(self) -> None:
        in_hand = [index for index, player in enumerate(self.players) if not player.busted]
        if len(in_hand) == 2:
            self.sb_index = self.button
            self.bb_index = self._next_index(self.button, lambda player: not player.busted)
        else:
            self.sb_index = self._next_index(self.button, lambda player: not player.busted)
            self.bb_index = self._next_index(self.sb_index, lambda player: not player.busted)
        self._post(self.players[self.sb_index], self.sb, "the small blind")
        self._post(self.players[self.bb_index], self.bb, "the big blind")

    def _post(self, player: Player, amount: int, label: str) -> None:
        pay = min(player.stack, amount)
        player.stack -= pay
        player.bet += pay
        player.total_bet += pay
        self.pot += pay
        if player.stack == 0:
            player.all_in = True
        self._log(f"{player.name} posts {pay} for {label}")

    def _deal_hole(self) -> None:
        start = self.sb_index if self.sb_index is not None else 0
        order = [player for player in self._ring(start) if not player.busted]
        for _ in range(2):
            for player in order:
                player.hole.append(self._draw())

    def _deal_board(self, count: int) -> None:
        if self.deck:
            self._draw()
        for _ in range(count):
            self.board.append(self._draw())
        self._log_board()

    def _deal_to_five(self) -> None:
        while len(self.board) < 5:
            count = 3 if not self.board else 1
            self._deal_board(count)

    def _log_board(self) -> None:
        if len(self.board) == 3:
            label, shown = "Flop", self.board
        elif len(self.board) == 4:
            label, shown = "Turn", self.board[-1:]
        elif len(self.board) == 5:
            label, shown = "River", self.board[-1:]
        else:
            return
        self._log(f"{label}: {' '.join(card.code() for card in shown)}")

    def _draw(self) -> Card:
        if not self.deck:
            raise GameError("The deck is empty.")
        return self.deck.pop()

    def _raise_to(self, player: Player, amount: int, legal: dict) -> None:
        max_to = legal["max_raise_to"]
        min_to = legal["min_raise_to"]
        if amount > max_to:
            raise GameError("That raise is more than your stack.")
        if amount != max_to and amount < min_to:
            raise GameError(f"The minimum raise is to {min_to}.")
        if amount <= player.bet or amount < self.current_bet:
            raise GameError("A raise has to increase the bet.")
        prev = self.current_bet
        self._pay_to(player, amount)
        increment = player.bet - prev
        if player.bet > prev and increment >= self.min_raise:
            self.min_raise = increment
            for other in self.players:
                if other is not player and not other.folded and not other.all_in and not other.busted:
                    other.acted = False
        if player.bet > prev:
            self.current_bet = player.bet
        player.acted = True
        if player.all_in:
            self._log(f"{player.name} is all in for {player.bet}")
        elif prev == 0:
            self._log(f"{player.name} bets {player.bet}")
        else:
            self._log(f"{player.name} raises to {player.bet}")

    def _pay_to(self, player: Player, target: int) -> int:
        delta = target - player.bet
        if delta < 0:
            raise GameError("That amount is too small.")
        pay = min(delta, player.stack)
        player.stack -= pay
        player.bet += pay
        player.total_bet += pay
        self.pot += pay
        if player.stack == 0:
            player.all_in = True
        return pay

    def _progress(self) -> None:
        guard = 0
        while self.street in BETTING and guard < 8:
            guard += 1
            if len(self._live()) <= 1:
                self._award_fold()
                return
            if not self._round_over():
                self.to_act_index = self._player_to_act()
                if self.to_act_index is None:
                    self._end_street()
                    continue
                return
            self._end_street()

    def _end_street(self) -> None:
        if len(self._live()) <= 1:
            self._award_fold()
            return
        actors = [player for player in self._live() if not player.all_in]
        if self.street == "river" or len(actors) <= 1:
            self._deal_to_five()
            self._showdown()
            return
        for player in self.players:
            player.bet = 0
            player.acted = False
        self.current_bet = 0
        self.min_raise = self.bb
        if self.street == "preflop":
            self._deal_board(3)
            self.street = "flop"
        elif self.street == "flop":
            self._deal_board(1)
            self.street = "turn"
        elif self.street == "turn":
            self._deal_board(1)
            self.street = "river"
        self.to_act_index = self._next_index(
            self.button,
            lambda player: not player.folded and not player.all_in and not player.busted,
        )

    def _round_over(self) -> bool:
        live = self._live()
        if len(live) <= 1:
            return True
        actors = [player for player in live if not player.all_in]
        if not actors:
            return True
        return all(player.acted and player.bet == self.current_bet for player in actors)

    def _needs_action(self, player: Player) -> bool:
        if player.busted or player.folded or player.all_in:
            return False
        if not player.acted or player.bet < self.current_bet:
            return True
        return False

    def _player_to_act(self) -> int | None:
        if self.to_act_index is not None and self._needs_action(self.players[self.to_act_index]):
            return self.to_act_index
        start = self.button if self.to_act_index is None else self.to_act_index
        return self._find_next_actor(start)

    def _find_next_actor(self, start: int) -> int | None:
        count = len(self.players)
        for step in range(1, count + 1):
            index = (start + step) % count
            if self._needs_action(self.players[index]):
                return index
        return None

    def _next_index(self, start: int, pred) -> int | None:
        count = len(self.players)
        for step in range(1, count + 1):
            index = (start + step) % count
            if pred(self.players[index]):
                return index
        return None

    def _ring(self, start: int) -> list[Player]:
        count = len(self.players)
        return [self.players[(start + step) % count] for step in range(count)]

    def _live(self) -> list[Player]:
        return [player for player in self.players if not player.folded and not player.busted]

    def _award_fold(self) -> None:
        live = self._live()
        winner = live[0] if live else self.players[0]
        amount = sum(player.total_bet for player in self.players)
        winner.stack += amount
        line = f"{winner.name} wins {amount}"
        self.last_result = {
            "kind": "fold",
            "lines": [line],
            "winners": [winner.id],
            "won": {winner.id: amount},
            "highlight": {},
        }
        self._log(line)
        self.street = "complete"
        self.to_act_index = None

    def _showdown(self) -> None:
        won: dict[str, int] = {}
        highlight: dict[str, list[str]] = {}
        lines: list[str] = []
        for amount, eligible in self._collect_pots():
            scored = []
            for player in eligible:
                score, combo = best_hand(player.hole + self.board)
                scored.append((score, player, combo))
            best = max(item[0] for item in scored)
            winners = [item for item in scored if item[0] == best]
            ordered = sorted(winners, key=lambda item: self._left_of_button(item[1]))
            share, remainder = divmod(amount, len(ordered))
            names = []
            for index, (score, player, combo) in enumerate(ordered):
                get = share + (1 if index < remainder else 0)
                player.stack += get
                won[player.id] = won.get(player.id, 0) + get
                highlight[player.id] = [card.code() for card in combo]
                names.append(player.name)
            label = hand_name(best)
            if len(names) == 1:
                lines.append(f"{names[0]} wins {amount} with {label}")
            else:
                lines.append(f"{' and '.join(names)} split {amount} with {label}")
        self.last_result = {
            "kind": "showdown",
            "lines": lines,
            "winners": list(won),
            "won": won,
            "highlight": highlight,
        }
        for line in lines:
            self._log(line)
        self.street = "showdown"
        self.to_act_index = None

    def _collect_pots(self) -> list[tuple[int, list[Player]]]:
        contrib = {player.id: player.total_bet for player in self.players}
        pots: list[tuple[int, list[Player]]] = []
        guard = 0
        while any(value > 0 for value in contrib.values()) and guard < 12:
            guard += 1
            level = min(value for value in contrib.values() if value > 0)
            amount = 0
            involved: list[Player] = []
            for player in self.players:
                if contrib[player.id] <= 0:
                    continue
                amount += level
                contrib[player.id] -= level
                involved.append(player)
            eligible = [player for player in involved if not player.folded and not player.busted]
            if not eligible:
                eligible = self._live() or involved[:1]
            pots.append((amount, eligible))
        return pots

    def _left_of_button(self, player: Player) -> int:
        index = self.players.index(player)
        distance = (index - self.button) % len(self.players)
        return distance if distance else len(self.players)

    def _log(self, text: str) -> None:
        self.log_lines.append(text)
        if len(self.log_lines) > 80:
            self.log_lines = self.log_lines[-80:]
