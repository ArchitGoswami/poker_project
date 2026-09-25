import random

from app.ai import choose_action
from app.engine import Card, Game, Player, best_hand, evaluate_five, hand_name, parse_cards


def test_royal_beats_straight_flush():
    royal = parse_cards("As Ks Qs Js Ts")
    steel = parse_cards("Ah Kh Qh Jh 9h")
    assert hand_name(evaluate_five(royal)) == "a royal flush"
    assert evaluate_five(royal) > evaluate_five(steel)


def test_wheel_and_kickers():
    wheel = parse_cards("As 2d 3c 4h 5s")
    six = parse_cards("6h 7d 8c 9s Td")
    assert evaluate_five(wheel)[0] == 4
    assert evaluate_five(wheel) < evaluate_five(six)
    aces = parse_cards("Ah Ad Kd Qc 2c")
    weaker = parse_cards("As Ac Qd Jc 3c")
    assert evaluate_five(aces) > evaluate_five(weaker)
    full = parse_cards("Ah Ad As Kh Kd")
    lesser = parse_cards("Kh Kd Ks Ah Ad")
    assert "aces full" in hand_name(evaluate_five(full))
    assert evaluate_five(full) > evaluate_five(lesser)


def test_best_seven_picks_the_flush():
    cards = parse_cards("As Ks 9s 4s 2s Kd Qh")
    score, _combo = best_hand(cards)
    assert score[0] == 5


def _players(stacks, button=0):
    people = []
    for index, stack in enumerate(stacks):
        people.append(Player(id=f"p{index}", name=f"P{index}", stack=stack, seat=index))
    return Game(people, sb=10, bb=20, rng=random.Random(1), button=button)


def test_heads_up_blinds_and_order():
    game = _players([1000, 1000], button=1)
    game.start_hand()
    assert game.players[1].bet == 10
    assert game.players[0].bet == 20
    assert game.players[game.to_act_index].id == "p1"
    assert game.pot == 30


def test_raise_fold_call_reaches_flop():
    game = _players([1000, 1000, 1000], button=1)
    game.start_hand()
    assert game.pot == 30
    actor = game.players[game.to_act_index]
    game.act(actor.id, "raise", 60)
    actor = game.players[game.to_act_index]
    game.act(actor.id, "fold")
    actor = game.players[game.to_act_index]
    game.act(actor.id, "call")
    assert game.street == "flop"
    assert game.pot == 130
    assert len(game.board) == 3


def test_side_pots_pay_the_right_players():
    game = _players([100, 1000, 1000], button=0)
    game.street = "river"
    game.board = parse_cards("2c 3d 4h 5s 9c")
    game.players[0].hole = parse_cards("Ah Ad")
    game.players[1].hole = parse_cards("Kh Kd")
    game.players[2].hole = parse_cards("Qh Qd")
    game.players[0].stack = 0
    game.players[0].total_bet = 100
    game.players[1].stack = 700
    game.players[1].total_bet = 300
    game.players[2].stack = 700
    game.players[2].total_bet = 300
    game.pot = 700
    game._showdown()
    assert game.players[0].stack == 300
    assert game.players[1].stack == 1100
    assert game.players[2].stack == 700


def test_chips_stay_on_the_table():
    rng = random.Random(4)
    players = [
        Player("a", "June", 1000, 0, True, "conservative", 18, 34, 3),
        Player("b", "Ellis", 1000, 1, True, "super_casual", 80, 22, 8),
        Player("c", "Marlow", 1000, 2, True, "reckless", 90, 94, 40),
    ]
    game = Game(players, sb=10, bb=20, rng=rng, button=0)
    for _ in range(20):
        if sum(player.stack > 0 for player in game.players) < 2:
            break
        game.start_hand()
        guard = 0
        while game.street in ("preflop", "flop", "turn", "river"):
            guard += 1
            assert guard < 80
            player = game.players[game.to_act_index]
            action, amount = choose_action(player, game)
            game.act(player.id, action, amount)
        assert sum(player.stack for player in game.players) == 3000
