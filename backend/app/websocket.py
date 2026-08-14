from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.auth import decode_token
from app.database import SessionLocal
from app.models import ChatMember, User

log = logging.getLogger(__name__)


class ConnectionManager:
    """In-process WebSocket connection manager.

    Tracks one or more WebSocket connections per user_id and routes events
    to users that share a chat with the sender.
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[user_id].add(ws)
        await self.broadcast_presence(user_id, online=True)

    async def disconnect(self, user_id: int, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._connections.get(user_id)
            if conns is None:
                return
            conns.discard(ws)
            if not conns:
                self._connections.pop(user_id, None)
                gone_offline = True
            else:
                gone_offline = False
        if gone_offline:
            self._update_last_seen(user_id)
            await self.broadcast_presence(user_id, online=False)

    def is_online(self, user_id: int) -> bool:
        return user_id in self._connections

    def online_user_ids(self) -> set[int]:
        return set(self._connections.keys())

    def _update_last_seen(self, user_id: int) -> None:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if user is not None:
                user.last_seen_at = datetime.now(UTC)
                db.commit()

    async def _send(self, ws: WebSocket, data: dict[str, Any]) -> None:
        try:
            await ws.send_json(data)
        except Exception as exc:  # noqa: BLE001
            log.warning("WebSocket send failed: %s", exc)

    async def send_to_user(self, user_id: int, data: dict[str, Any]) -> None:
        conns = list(self._connections.get(user_id, ()))
        if not conns:
            return
        await asyncio.gather(*(self._send(ws, data) for ws in conns))

    async def broadcast_chat(self, chat_id: int, data: dict[str, Any]) -> None:
        with SessionLocal() as db:
            user_ids = list(
                db.scalars(select(ChatMember.user_id).where(ChatMember.chat_id == chat_id)).all()
            )
        await asyncio.gather(*(self.send_to_user(uid, data) for uid in user_ids))

    async def broadcast_presence(self, user_id: int, online: bool) -> None:
        """Broadcast presence change to all users who share a chat with `user_id`."""
        with SessionLocal() as db:
            chat_ids = db.scalars(
                select(ChatMember.chat_id).where(ChatMember.user_id == user_id)
            ).all()
            if not chat_ids:
                return
            peer_ids = set(
                db.scalars(
                    select(ChatMember.user_id)
                    .where(ChatMember.chat_id.in_(chat_ids))
                    .where(ChatMember.user_id != user_id)
                ).all()
            )
        payload = {
            "type": "presence",
            "user_id": user_id,
            "online": online,
            "last_seen_at": datetime.now(UTC).isoformat(),
        }
        await asyncio.gather(*(self.send_to_user(uid, payload) for uid in peer_ids))


manager = ConnectionManager()


async def websocket_endpoint(ws: WebSocket) -> None:
    token = ws.query_params.get("token")
    if not token:
        await ws.close(code=4401)
        return
    user_id = decode_token(token)
    if user_id is None:
        await ws.close(code=4401)
        return
    with SessionLocal() as db:
        if db.get(User, user_id) is None:
            await ws.close(code=4401)
            return

    await manager.connect(user_id, ws)
    try:
        # send a presence snapshot of users that share a chat with us
        with SessionLocal() as db:
            chat_ids = db.scalars(
                select(ChatMember.chat_id).where(ChatMember.user_id == user_id)
            ).all()
            peer_ids = set(
                db.scalars(
                    select(ChatMember.user_id)
                    .where(ChatMember.chat_id.in_(chat_ids))
                    .where(ChatMember.user_id != user_id)
                ).all()
            )
        online_peers = [uid for uid in peer_ids if manager.is_online(uid)]
        await ws.send_json({"type": "presence_snapshot", "online_user_ids": online_peers})

        while True:
            data = await ws.receive_json()
            event_type = data.get("type")
            if event_type == "typing":
                chat_id = int(data.get("chat_id") or 0)
                if chat_id <= 0:
                    continue
                with SessionLocal() as db:
                    is_member = db.scalar(
                        select(ChatMember.id).where(
                            ChatMember.chat_id == chat_id,
                            ChatMember.user_id == user_id,
                        )
                    )
                if not is_member:
                    continue
                await manager.broadcast_chat(
                    chat_id,
                    {
                        "type": "typing",
                        "chat_id": chat_id,
                        "user_id": user_id,
                    },
                )
            elif event_type == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(user_id, ws)
