import json

from app.solo import TableSession


def test_local_table_deals():
    session = TableSession()
    raw = session.create({
        "mode": "models",
        "play": True,
        "your_name": "You",
        "stack": 1000,
        "sb": 10,
        "bb": 20,
        "models": [
            {"name": "June", "style": "conservative", "looseness": 18, "aggression": 34, "bluff": 3},
            {"name": "Marlow", "style": "reckless", "looseness": 90, "aggression": 94, "bluff": 40},
        ],
    })
    state = json.loads(raw)
    assert state["state"]["street"] == "preflop"
    assert state["code"]
    assert len(state["state"]["players"]) == 3
