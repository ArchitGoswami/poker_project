"""Same table and dealer, without a socket, for the static site."""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.dealer import DealerError, DealerSession, interpret
from app.engine import BETTING, GameError
from app.rooms import Manager


def _plain(value):
    if hasattr(value, "to_py"):
        value = value.to_py()
    return value


class TableSession:
    def __init__(self):
        self.manager = Manager()
        self.room = None
        self.player_id = None

    def create(self, body) -> str:
        body = _plain(body)
        models = [SimpleNamespace(**item) for item in body.get("models") or []]
        request = SimpleNamespace(
            mode=body.get("mode") or "models",
            your_name=body.get("your_name"),
            play=body.get("play", True),
            models=models,
            stack=body.get("stack", 1000),
            sb=body.get("sb", 10),
            bb=body.get("bb", 20),
        )
        created = self.manager.create(request)
        self.room = self.manager.get(created["code"])
        self.player_id = created["player_id"]
        return json.dumps(self.room.snapshot_for(self.player_id))

    def handle(self, message) -> str:
        message = _plain(message)
        room = self.room
        player_id = self.player_id
        kind = message.get("type")
        try:
            if kind == "start":
                if not room.can_deal(player_id):
                    raise GameError("Only someone at the table can deal.")
                room.game.start_hand()
            elif kind == "action":
                amount = message.get("amount")
                room.game.act(player_id, message.get("action"), None if amount is None else int(amount))
            elif kind == "auto":
                if not room.can_deal(player_id):
                    raise GameError("Only someone at the table can do that.")
                room.auto_next = bool(message.get("on"))
                if room.auto_next and room.game.street in ("showdown", "complete"):
                    room.game.start_hand()
            else:
                raise GameError("Unknown message.")
        except GameError as exc:
            return json.dumps(room.snapshot_for(player_id, str(exc)))
        return json.dumps(room.snapshot_for(player_id))

    def pending(self) -> str:
        game = self.room.game
        if game.street in BETTING and game.to_act_index is not None:
            if game.players[game.to_act_index].is_bot:
                return "bot"
            return ""
        if self.room.auto_next and game.street in ("showdown", "complete"):
            return "deal"
        return ""

    def act_bot(self) -> str:
        from app.ai import choose_action

        game = self.room.game
        player = game.players[game.to_act_index]
        try:
            action, amount = choose_action(player, game)
            game.act(player.id, action, amount)
        except GameError:
            legal = game.legal_for(player)
            if legal["check"]:
                game.act(player.id, "check")
            elif legal["call"]:
                game.act(player.id, "call")
            else:
                game.act(player.id, "fold")
        return json.dumps(self.room.snapshot_for(self.player_id))

    def auto_deal(self) -> str:
        if not self.room.auto_next or self.room.game.street not in ("showdown", "complete"):
            return json.dumps(self.room.snapshot_for(self.player_id))
        try:
            self.room.game.start_hand()
        except GameError as exc:
            return json.dumps(self.room.snapshot_for(self.player_id, str(exc)))
        return json.dumps(self.room.snapshot_for(self.player_id))


class DealerBridge:
    def __init__(self):
        self.session = None

    def create(self, body) -> str:
        body = _plain(body)
        names = [" ".join(name.split()) for name in body["names"]]
        session = DealerSession(
            names,
            int(body.get("stack", 200)),
            int(body.get("hero", 0)),
            int(body.get("sb", 1)),
            int(body.get("bb", 2)),
            "local",
        )
        session.command({"type": "new_hand"})
        self.session = session
        return json.dumps(session.public())

    def command(self, body) -> str:
        body = _plain(body)
        try:
            event = body.get("event") if body.get("event") else interpret(body.get("text") or "")
            if hasattr(event, "to_py"):
                event = event.to_py()
            if event.get("type") == "unknown":
                raise DealerError("I didn't catch that. Try 'Alex calls' or 'my cards are ace of spades and king of spades'.")
            heard = self.session.command(event)
        except DealerError as exc:
            return json.dumps({"error": str(exc)})
        payload = self.session.public()
        payload["heard"] = heard
        return json.dumps(payload)
