"""the poker project server."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.dealer import DealerError, DealerSession, interpret
from app.engine import GameError
from app.rooms import Manager
from app.vision import recognize_card

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
app = FastAPI(title="the poker project")
manager = Manager()
sessions: dict[str, DealerSession] = {}


class ModelIn(BaseModel):
    name: str
    style: str = "balanced"
    looseness: int | None = None
    aggression: int | None = None
    bluff: int | None = None


class CreateTable(BaseModel):
    mode: str = "models"
    your_name: str | None = None
    play: bool = True
    models: list[ModelIn] = Field(default_factory=list)
    stack: int = 1000
    sb: int = 10
    bb: int = 20


class JoinTable(BaseModel):
    name: str


class DealerCreate(BaseModel):
    names: list[str]
    hero: int = 0
    stack: int = 200
    sb: int = 1
    bb: int = 2


class DealerCommand(BaseModel):
    text: str | None = None
    event: dict | None = None


@app.get("/api/health")
async def health():
    return {"ok": True}


def _fail(exc: Exception) -> None:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/tables")
async def create_table(body: CreateTable):
    try:
        return manager.create(body)
    except GameError as exc:
        _fail(exc)


@app.post("/api/tables/{code}/join")
async def join_table(code: str, body: JoinTable):
    try:
        room = manager.get(code)
        player_id = room.join(body.name)
        await room.broadcast()
        return {"code": room.code, "player_id": player_id, "host": False}
    except GameError as exc:
        _fail(exc)


@app.websocket("/ws/{code}/{player_id}")
async def table_socket(websocket: WebSocket, code: str, player_id: str):
    try:
        room = manager.get(code)
    except GameError:
        await websocket.close(code=4404)
        return
    await room.connect(player_id, websocket)
    try:
        while True:
            message = await websocket.receive_json()
            await room.handle(player_id, message)
    except WebSocketDisconnect:
        room.disconnect(player_id)
    except Exception:
        room.disconnect(player_id)


@app.post("/api/dealer")
async def create_dealer(body: DealerCreate):
    try:
        if not 1 <= body.sb < body.bb <= body.stack:
            raise DealerError("Blinds should sit under the buy-in, with the big blind larger.")
        names = []
        for name in body.names:
            clean = " ".join(name.split())
            if not clean or len(clean) > 18:
                raise DealerError("Use a name of one to eighteen characters.")
            names.append(clean)
        session_id = uuid.uuid4().hex[:10]
        session = DealerSession(names, body.stack, body.hero, body.sb, body.bb, session_id)
        session.command({"type": "new_hand"})
        sessions[session_id] = session
        if len(sessions) > 40:
            oldest = next(iter(sessions))
            if oldest != session_id:
                sessions.pop(oldest, None)
        return session.public()
    except DealerError as exc:
        _fail(exc)


@app.get("/api/dealer/{session_id}")
async def get_dealer(session_id: str):
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="That dealer station is gone. Open it again.")
    return session.public()


@app.post("/api/dealer/{session_id}/command")
async def dealer_command(session_id: str, body: DealerCommand):
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="That dealer station is gone. Open it again.")
    try:
        event = body.event if body.event else interpret(body.text or "")
        if event.get("type") == "unknown":
            raise DealerError("I didn't catch that. Try 'Alex calls' or 'my cards are ace of spades and king of spades'.")
        heard = session.command(event)
        payload = session.public()
        payload["heard"] = heard
        return payload
    except DealerError as exc:
        _fail(exc)


@app.post("/api/dealer/{session_id}/scan")
async def dealer_scan(session_id: str, frame: UploadFile):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="That dealer station is gone. Open it again.")
    data = await frame.read()
    if len(data) > 4_000_000:
        raise HTTPException(status_code=413, detail="That image is too large.")
    return recognize_card(data)


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


app.mount("/assets", StaticFiles(directory=STATIC), name="assets")
