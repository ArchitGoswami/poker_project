from app.dealer import DealerSession, interpret


def test_speech_parses_actions_and_cards():
    assert interpret("alex folds")["verb"] == "fold"
    assert interpret("I call")["name"] is None
    raised = interpret("sam raises to 60")
    assert raised["verb"] == "raise" and raised["amount"] == 60
    flop = interpret("flop ace of spades king of hearts seven of clubs")
    assert flop["cards"] == ["As", "Kh", "7c"]
    assert interpret("undo")["type"] == "undo"


def test_advice_for_pocket_aces():
    session = DealerSession(["You", "Alex"], 200, 0, 1, 2, "t")
    session.command({"type": "new_hand"})
    session.command({"type": "hole", "name": None, "cards": ["As", "Ad"]})
    advice = session.advice()
    assert advice["suggestion"] == "Bet"
    assert "aces" in advice["hand"]


def test_call_grows_the_pot():
    session = DealerSession(["You", "Alex"], 200, 0, 1, 2, "t")
    session.command({"type": "new_hand"})
    before = session.pot
    session.command({"type": "action", "name": "Alex", "verb": "raise", "amount": 6})
    assert session.pot > before
    session.command({"type": "undo"})
    assert session.pot == before
