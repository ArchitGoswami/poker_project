"""Style-based opponents. The numbers, not the label, decide the line."""

from __future__ import annotations

from app.engine import BETTING, Card, Game, Player, best_hand

PRESETS = {
    "conservative": {"looseness": 18, "aggression": 34, "bluff": 3, "label": "Conservative"},
    "super_casual": {"looseness": 80, "aggression": 22, "bluff": 8, "label": "Super casual"},
    "balanced": {"looseness": 44, "aggression": 60, "bluff": 12, "label": "Balanced"},
    "reckless": {"looseness": 90, "aggression": 94, "bluff": 40, "label": "Reckless"},
    "custom": {"looseness": 50, "aggression": 50, "bluff": 10, "label": "Custom"},
}


def resolve_style(style: str, looseness: int | None, aggression: int | None, bluff: int | None) -> dict:
    key = style if style in PRESETS else "balanced"
    base = PRESETS[key]
    return {
        "style": key,
        "looseness": _clamp(base["looseness"] if looseness is None else looseness),
        "aggression": _clamp(base["aggression"] if aggression is None else aggression),
        "bluff": _clamp(base["bluff"] if bluff is None else bluff),
    }


def choose_action(player: Player, game: Game) -> tuple[str, int | None]:
    legal = game.legal_for(player)
    action, amount = _think(player, game, legal)
    return _legalize(action, amount, legal)


def _think(player: Player, game: Game, legal: dict) -> tuple[str, int | None]:
    perceived = _strength(player.hole, game.board)
    perceived += (player.looseness - 40) / 220
    perceived += game.rng.uniform(-0.04, 0.04)
    to_call = legal["call_amount"]
    pot = max(game.pot, 1)
    odds = to_call / (pot + to_call) if to_call else 0
    bluff = game.rng.random() < (player.bluff / 100) * (0.55 if game.board else 0.8)
    if to_call == 0:
        threshold = 0.58 - (player.aggression / 250)
        if legal["can_raise"] and (bluff or perceived > threshold):
            return _sized(player, game, legal, bluff)
        return ("check", None)
    fold_line = odds + 0.08 - (player.looseness / 400)
    if perceived < fold_line and perceived < 0.62 and not bluff:
        return ("fold", None)
    if legal["can_raise"] and (perceived > 0.7 or (bluff and player.aggression > 65 and to_call < pot)):
        return _sized(player, game, legal, bluff)
    return ("call", None)


def _sized(player: Player, game: Game, legal: dict, bluff: bool) -> tuple[str, int | None]:
    if player.aggression < 36 and game.rng.random() < 0.7:
        target = legal["min_raise_to"]
    else:
        fraction = 0.33 + (player.aggression / 100) * (1.05 if not bluff else 0.8)
        target = game.current_bet + max(legal["min_raise_to"] - game.current_bet, int(game.pot * fraction))
    if player.aggression > 88 and game.rng.random() < 0.18:
        target = legal["max_raise_to"]
    return ("raise", target)


def _legalize(action: str, amount: int | None, legal: dict) -> tuple[str, int | None]:
    if action in ("raise", "bet"):
        if not legal["can_raise"]:
            return _passive(legal)
        amount = int(amount if amount is not None else legal["min_raise_to"])
        amount = max(legal["min_raise_to"], min(legal["max_raise_to"], amount))
        if amount >= legal["max_raise_to"] and legal["max_raise_to"] > legal["min_raise_to"]:
            if amount == legal["max_raise_to"]:
                return ("allin", None)
        if amount <= legal["min_raise_to"] and legal["max_raise_to"] == legal["min_raise_to"]:
            return ("allin", None)
        return ("raise", amount)
    if action == "allin":
        if legal["can_raise"]:
            return ("allin", None)
        return _passive(legal)
    if action == "call" and not legal["call"]:
        return ("check", None) if legal["check"] else ("fold", None)
    if action == "check" and not legal["check"]:
        return ("call", None) if legal["call"] else ("fold", None)
    if action == "fold" and legal["check"]:
        return ("check", None)
    return (action, None)


def _passive(legal: dict) -> tuple[str, int | None]:
    if legal["check"]:
        return ("check", None)
    if legal["call"]:
        return ("call", None)
    return ("fold", None)


def _strength(hole: list[Card], board: list[Card]) -> float:
    if len(hole) < 2:
        return 0.3
    if not board:
        return _preflop(hole)
    return _postflop(hole, board)


def _preflop(hole: list[Card]) -> float:
    high, low = sorted(hole, key=lambda card: card.rank, reverse=True)
    if high.rank == low.rank:
        score = 0.45 + (high.rank - 2) / 12 * 0.5
    else:
        score = 0.18 + (high.rank - 2) / 12 * 0.36 + (low.rank - 2) / 12 * 0.14
        if high.suit == low.suit:
            score += 0.06
        gap = high.rank - low.rank
        if gap == 1:
            score += 0.04
        elif gap >= 4:
            score -= 0.08
        if high.rank == 14:
            score += 0.07
    return max(0.02, min(0.98, score))


def _postflop(hole: list[Card], board: list[Card]) -> float:
    cards = hole + board
    score, _combo = best_hand(cards) if len(cards) >= 5 else ((0, (hole[0].rank,)), ())
    if len(cards) < 5:
        score = (0, (max(card.rank for card in hole),))
    category = score[0]
    floors = {8: 0.99, 7: 0.97, 6: 0.91, 5: 0.84, 4: 0.78, 3: 0.7, 2: 0.6, 1: 0.46, 0: 0.2}
    base = floors[category]
    if category == 1:
        pair_rank = score[1][0]
        base = 0.32 + (pair_rank - 2) / 12 * 0.3
        if board and pair_rank > max(card.rank for card in board):
            base += 0.1
    if category == 0:
        base = 0.12 + (max(card.rank for card in hole) - 2) / 12 * 0.12
        if _flush_draw(hole, board):
            base += 0.16
        if _straight_draw(cards):
            base += 0.1
    return max(0.05, min(0.99, base))


def _flush_draw(hole: list[Card], board: list[Card]) -> bool:
    if len(board) >= 5:
        return False
    suits: dict[str, int] = {}
    for card in hole + board:
        suits[card.suit] = suits.get(card.suit, 0) + 1
    return any(count == 4 and any(card.suit == suit for card in hole) for suit, count in suits.items())


def _straight_draw(cards: list[Card]) -> bool:
    ranks = {card.rank for card in cards}
    if 14 in ranks:
        ranks.add(1)
    for low in range(1, 11):
        window = [low + step for step in range(5)]
        have = sum(rank in ranks for rank in window)
        if have == 4:
            return True
    return False


def _clamp(value: int) -> int:
    return max(0, min(100, int(value)))
