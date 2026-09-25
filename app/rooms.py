"""In-memory tables for friends and for models."""

from __future__ import annotations

import asyncio
import random
import uuid

from app.ai import choose_action, resolve_style
from app.engine import BETTING, Game, GameError, Player

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class Room:
    def __init__(self, code: str, game: Game, host_id: str, mode: str, reveal_all: bool, auto_next: bool):
        self.code = code
        self.game = game
        self.host_id = host_id
        self.mode = mode
        self.reveal_all = reveal_all
        self.auto_next = auto_next
        self.buy_in = game.players[0].stack if game.players else 1000
        self.connections: dict[str, object] = {}
        self.lock = asyncio.Lock()
        self._bot_task: asyncio.Task | None = None

    def can_deal(self, player_id: str) -> bool:
        if player_id == self.host_id:
            return True
        return any(player.id == player_id and not player.is_bot for player in self.game.players)

    def snapshot_for(self, player_id: str, error: str | None = None) -> dict:
        viewer = None if player_id.startswith("watch-") else player_id
        game = self.game
        seated = sum(player.stack > 0 for player in game.players)
        hand_over = game.street in ("waiting", "showdown", "complete")
        return {
            "type": "state",
            "code": self.code,
            "you": viewer,
            "host": player_id == self.host_id,
            "mode": self.mode,
            "auto_next": self.auto_next,
            "reveal": self.reveal_all,
            "can_deal": self.can_deal(player_id) and hand_over and seated >= 2,
            "game_over": hand_over and seated < 2 and game.hand_number > 0,
            "error": error,
            "state": game.snapshot(viewer, reveal_all=self.reveal_all),
        }

    async def connect(self, player_id: str, websocket) -> None:
        await websocket.accept()
        self.connections[player_id] = websocket
        await self.send_to(player_id)
        await self.maybe_bots()

    def disconnect(self, player_id: str) -> None:
        self.connections.pop(player_id, None)

    async def handle(self, player_id: str, message: dict) -> None:
        kind = message.get("type")
        async with self.lock:
            try:
                if kind == "start":
                    if not self.can_deal(player_id):
                        raise GameError("Only someone at the table can deal.")
                    self.game.start_hand()
                elif kind == "action":
                    amount = message.get("amount")
                    self.game.act(player_id, message.get("action"), None if amount is None else int(amount))
                elif kind == "auto":
                    if not self.can_deal(player_id):
                        raise GameError("Only someone at the table can do that.")
                    self.auto_next = bool(message.get("on"))
                    if self.auto_next and self.game.street in ("showdown", "complete"):
                        self.game.start_hand()
                else:
                    raise GameError("Unknown message.")
            except GameError as exc:
                await self.send_to(player_id, str(exc))
                return
            await self.broadcast()
        await self.maybe_bots()

    async def broadcast(self) -> None:
        dead = []
        for player_id, websocket in list(self.connections.items()):
            try:
                await websocket.send_json(self.snapshot_for(player_id))
            except Exception:
                dead.append(player_id)
        for player_id in dead:
            self.connections.pop(player_id, None)

    async def send_to(self, player_id: str, error: str | None = None) -> None:
        websocket = self.connections.get(player_id)
        if websocket is None:
            return
        try:
            await websocket.send_json(self.snapshot_for(player_id, error))
        except Exception:
            self.connections.pop(player_id, None)

    async def maybe_bots(self) -> None:
        if self._bot_task and not self._bot_task.done():
            return
        self._bot_task = asyncio.create_task(self._bot_loop())

    async def _bot_loop(self) -> None:
        while True:
            async with self.lock:
                game = self.game
                if game.street not in BETTING:
                    if self.auto_next and game.street in ("showdown", "complete"):
                        should_next = True
                        actor = None
                    else:
                        return
                else:
                    should_next = False
                    if game.to_act_index is None:
                        return
                    actor = game.players[game.to_act_index]
                    if not actor.is_bot:
                        return
                    try:
                        action, amount = choose_action(actor, game)
                    except Exception:
                        action, amount = "check", None
            if should_next:
                await asyncio.sleep(2.6)
                async with self.lock:
                    if not self.auto_next or self.game.street not in ("showdown", "complete"):
                        await self.broadcast()
                        return
                    try:
                        self.game.start_hand()
                    except GameError:
                        await self.broadcast()
                        return
                    await self.broadcast()
                continue
            await asyncio.sleep(0.85)
            async with self.lock:
                game = self.game
                if game.street not in BETTING or game.to_act_index is None:
                    continue
                current = game.players[game.to_act_index]
                if actor is None or current.id != actor.id:
                    continue
                try:
                    game.act(current.id, action, amount)
                except GameError:
                    legal = game.legal_for(current)
                    if legal["check"]:
                        game.act(current.id, "check")
                    elif legal["call"]:
                        game.act(current.id, "call")
                    else:
                        game.act(current.id, "fold")
                await self.broadcast()

    def join(self, name: str) -> str:
        clean = _name(name)
        if self.game.street not in ("waiting", "showdown", "complete"):
            raise GameError("Wait for the next hand to sit down.")
        player = Player(
            id=uuid.uuid4().hex[:10],
            name=clean,
            stack=self.buy_in,
            seat=len(self.game.players),
        )
        self.game.add_player(player)
        if self.reveal_all:
            self.reveal_all = False
            self.auto_next = False
        return player.id


class Manager:
    def __init__(self):
        self.rooms: dict[str, Room] = {}

    def create(self, body) -> dict:
        mode = body.mode if body.mode in ("models", "friends") else "models"
        stack = int(body.stack)
        sb = int(body.sb)
        bb = int(body.bb)
        if not 1 <= sb < bb:
            raise GameError("The big blind has to be larger than the small blind.")
        if stack < bb:
            raise GameError("The buy-in has to cover the big blind.")
        if stack > 100_000 or bb > 10_000:
            raise GameError("Those stakes are too large for this room.")
        models = list(body.models or [])
        play = bool(body.play) if mode == "models" else True
        your_name = _name(body.your_name or "You") if play else None
        if mode == "friends" and not play:
            raise GameError("Friends tables start with you sitting down.")
        seats = (1 if play else 0) + len(models)
        if mode == "models" and seats < 2:
            raise GameError("Seat at least two players.")
        if seats > 6:
            raise GameError("Six seats is the table limit.")
        if mode == "friends" and len(models) > 5:
            raise GameError("Leave a seat for the friends who are coming.")
        players: list[Player] = []
        host_id = None
        if play:
            host_id = uuid.uuid4().hex[:10]
            players.append(Player(id=host_id, name=your_name, stack=stack, seat=0))
        for model in models:
            style = resolve_style(model.style, model.looseness, model.aggression, model.bluff)
            players.append(Player(
                id=uuid.uuid4().hex[:10],
                name=_name(model.name),
                stack=stack,
                seat=len(players),
                is_bot=True,
                style=style["style"],
                looseness=style["looseness"],
                aggression=style["aggression"],
                bluff=style["bluff"],
            ))
        if len(players) > 6:
            raise GameError("Six seats is the table limit.")
        human_first = play and any(player.is_bot for player in players)
        button = _opening_button(len(players), human_first)
        game = Game(players, sb=sb, bb=bb, rng=random.Random(), button=button)
        reveal = mode == "models" and not play
        auto_next = reveal
        if mode == "models" and len(players) >= 2:
            game.start_hand()
        if host_id is None:
            host_id = "watch-" + uuid.uuid4().hex[:10]
        code = self._code()
        room = Room(code, game, host_id, mode, reveal, auto_next)
        room.buy_in = stack
        self.rooms[code] = room
        return {"code": code, "player_id": host_id, "host": True}

    def get(self, code: str) -> Room:
        room = self.rooms.get(code.upper())
        if room is None:
            raise GameError("That table code doesn't exist.")
        return room

    def _code(self) -> str:
        for _ in range(20):
            code = "".join(random.choice(ALPHABET) for _ in range(4))
            if code not in self.rooms:
                return code
        return uuid.uuid4().hex[:4].upper()


def _opening_button(count: int, human_first: bool) -> int:
    if not human_first or count < 2:
        return 0
    if count == 2:
        return 1
    return (count - 2) % count


def _name(value: str) -> str:
    clean = " ".join((value or "").split())
    if not clean or len(clean) > 18:
        raise GameError("Use a name of one to eighteen characters.")
    return clean
