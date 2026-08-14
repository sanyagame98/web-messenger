from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, Message, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v4 as v4
from app.routers import roof_tweb_v5 as v5

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _channel_message_peer(item: dict[str, Any], chat: Chat) -> None:
    if chat.type == "channel":
        item["peer_id"] = {"_": "peerChannel", "channel_id": chat.id}


def _entity_chat(chat: Chat) -> dict[str, Any]:
    if chat.type == "channel":
        return {
            "_": "channel",
            "id": chat.id,
            "access_hash": "0",
            "title": chat.name or "Roof Channel",
            "photo": {"_": "chatPhotoEmpty"},
            "date": legacy._unix(chat.created_at),
            "participants_count": len(chat.members),
            "pFlags": {"broadcast": True},
        }
    return legacy._chat_entity(chat)


def _accessible_chat_ids(current_user: User, db: Session) -> list[int]:
    return list(
        db.scalars(
            select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)
        ).all()
    )


def _serialize_messages(
    rows: list[Message],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat_ids = {row.chat_id for row in rows}
    if not chat_ids:
        return {
            "_": "messages.messages",
            "messages": [],
            "chats": [],
            "users": [],
        }

    chats = list(
        db.scalars(
            select(Chat)
            .where(Chat.id.in_(chat_ids))
            .options(selectinload(Chat.members).selectinload(ChatMember.user))
        ).unique().all()
    )
    by_id = {chat.id: chat for chat in chats}
    users: dict[int, User] = {current_user.id: current_user}
    entities: dict[int, dict[str, Any]] = {}
    messages: list[dict[str, Any]] = []

    for chat in chats:
        for member in chat.members:
            users[member.user_id] = member.user
        if chat.type != "direct":
            entities[chat.id] = _entity_chat(chat)

    for row in rows:
        chat = by_id.get(row.chat_id)
        if chat is None:
            continue
        item = legacy._message(row, chat, current_user.id)
        _channel_message_peer(item, chat)
        v4._decorate_message(item, current_user.id, db)
        messages.append(item)

    return {
        "_": "messages.messages",
        "messages": messages,
        "chats": list(entities.values()),
        "users": [legacy._user(user, current_user.id) for user in users.values()],
    }


def _search_peer(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = legacy._resolve_peer(params.get("peer"), current_user, db)
    query = str(params.get("q", "")).strip()
    limit = max(1, min(int(params.get("limit", 50)), 100))
    offset_id = int(params.get("offset_id", 0) or 0)

    stmt = select(Message).where(Message.chat_id == chat.id)
    if query:
        stmt = stmt.where(Message.content.ilike(f"%{query}%"))
    if offset_id:
        stmt = stmt.where(Message.id < offset_id)
    rows = list(db.scalars(stmt.order_by(Message.id.desc()).limit(limit)).all())
    return _serialize_messages(rows, current_user, db)


def _search_global(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat_ids = _accessible_chat_ids(current_user, db)
    if not chat_ids:
        return _serialize_messages([], current_user, db)

    query = str(params.get("q", "")).strip()
    limit = max(1, min(int(params.get("limit", 50)), 100))
    offset_id = int(params.get("offset_id", 0) or 0)
    stmt = select(Message).where(Message.chat_id.in_(chat_ids))
    if query:
        stmt = stmt.where(Message.content.ilike(f"%{query}%"))
    if offset_id:
        stmt = stmt.where(Message.id < offset_id)
    rows = list(db.scalars(stmt.order_by(Message.id.desc()).limit(limit)).all())
    return _serialize_messages(rows, current_user, db)


def _get_messages(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    ids = params.get("id") or []
    if not isinstance(ids, list):
        ids = [ids]
    message_ids: list[int] = []
    for value in ids:
        if isinstance(value, dict):
            message_id = int(value.get("id", 0) or 0)
        else:
            message_id = int(value or 0)
        if message_id > 0:
            message_ids.append(message_id)

    chat_ids = _accessible_chat_ids(current_user, db)
    if not chat_ids or not message_ids:
        return _serialize_messages([], current_user, db)
    rows = list(
        db.scalars(
            select(Message)
            .where(Message.id.in_(message_ids), Message.chat_id.in_(chat_ids))
            .order_by(Message.id.asc())
        ).all()
    )
    return _serialize_messages(rows, current_user, db)


def _search_users(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    query = str(params.get("q", "")).strip().lstrip("@").lower()
    limit = max(1, min(int(params.get("limit", 50)), 100))
    stmt = select(User).where(User.id != current_user.id)
    if query:
        stmt = stmt.where(
            or_(
                User.username.ilike(f"%{query}%"),
                User.display_name.ilike(f"%{query}%"),
            )
        )
    users = list(db.scalars(stmt.order_by(User.id.desc()).limit(limit)).all())
    return {
        "_": "contacts.found",
        "my_results": [],
        "results": [{"_": "peerUser", "user_id": user.id} for user in users],
        "chats": [],
        "users": [legacy._user(user, current_user.id) for user in users],
    }


@router.post("/invoke")
async def invoke_v6(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if payload.method == "messages.search":
        return _search_peer(payload.params, current_user, db)
    if payload.method == "messages.searchGlobal":
        return _search_global(payload.params, current_user, db)
    if payload.method in {"messages.getMessages", "channels.getMessages"}:
        return _get_messages(payload.params, current_user, db)
    if payload.method == "contacts.search":
        return _search_users(payload.params, current_user, db)

    return await v5.invoke_v5(payload, current_user, db)
