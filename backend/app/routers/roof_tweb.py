from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, Message, User

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


class RoofInvokeRequest(BaseModel):
    method: str = Field(min_length=1, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict)


def _unix(value: datetime | None) -> int:
    if value is None:
        return int(datetime.now(UTC).timestamp())
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp())


def _user(user: User, current_user_id: int) -> dict[str, Any]:
    flags: dict[str, bool] = {}
    if user.id == current_user_id:
        flags["self"] = True
    if user.is_premium:
        flags["premium"] = True
    if user.is_verified:
        flags["verified"] = True
    return {
        "_": "user",
        "id": user.id,
        "access_hash": "0",
        "first_name": user.display_name or user.username,
        "last_name": "",
        "username": user.username,
        "usernames": [{"_": "username", "username": user.username, "pFlags": {"active": True}}],
        "phone": "",
        "photo": {"_": "userProfilePhotoEmpty"},
        "status": {"_": "userStatusOffline", "was_online": _unix(user.last_seen_at)},
        "pFlags": flags,
    }


def _chat_entity(chat: Chat) -> dict[str, Any]:
    return {
        "_": "chat",
        "id": chat.id,
        "title": chat.name or "Roof group",
        "photo": {"_": "chatPhotoEmpty"},
        "participants_count": len(chat.members),
        "date": _unix(chat.created_at),
        "version": 1,
        "pFlags": {},
    }


def _peer_for_chat(chat: Chat, current_user_id: int) -> dict[str, Any]:
    if chat.type == "direct":
        other = next((m.user for m in chat.members if m.user_id != current_user_id), None)
        if other is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Broken direct chat")
        return {"_": "peerUser", "user_id": other.id}
    return {"_": "peerChat", "chat_id": chat.id}


def _message(message: Message, chat: Chat, current_user_id: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "_": "message",
        "id": message.id,
        "peer_id": _peer_for_chat(chat, current_user_id),
        "date": _unix(message.created_at),
        "message": message.content,
        "pFlags": {"out": True} if message.sender_id == current_user_id else {},
    }
    if message.sender_id is not None:
        result["from_id"] = {"_": "peerUser", "user_id": message.sender_id}
    if message.image_url:
        result["roof_media"] = {"type": "image", "url": message.image_url}
    return result


def _membership(chat_id: int, user_id: int, db: Session) -> ChatMember | None:
    return db.scalar(
        select(ChatMember).where(
            and_(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id)
        )
    )


def _direct_chat(user_id: int, other_id: int, db: Session) -> Chat | None:
    mine = set(db.scalars(select(ChatMember.chat_id).where(ChatMember.user_id == user_id)).all())
    theirs = set(db.scalars(select(ChatMember.chat_id).where(ChatMember.user_id == other_id)).all())
    common = mine & theirs
    if not common:
        return None
    return db.scalar(
        select(Chat)
        .where(Chat.id.in_(common), Chat.type == "direct")
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )


def _resolve_peer(peer: Any, current_user: User, db: Session) -> Chat:
    if not isinstance(peer, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof requires an explicit peer")
    kind = str(peer.get("_", ""))
    if kind in {"inputPeerUser", "peerUser"}:
        chat = _direct_chat(current_user.id, int(peer.get("user_id", 0)), db)
    elif kind in {"inputPeerChat", "peerChat", "inputPeerChannel", "peerChannel"}:
        chat_id = int(peer.get("chat_id") or peer.get("channel_id") or 0)
        chat = db.scalar(
            select(Chat)
            .where(Chat.id == chat_id)
            .options(selectinload(Chat.members).selectinload(ChatMember.user))
        )
        if chat is not None and _membership(chat.id, current_user.id, db) is None:
            chat = None
    else:
        chat = None
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof peer not found")
    return chat


def _dialogs(current_user: User, db: Session) -> dict[str, Any]:
    ids = db.scalars(
        select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)
    ).all()
    if not ids:
        return {"_": "messages.dialogs", "dialogs": [], "messages": [], "chats": [], "users": []}
    chats = (
        db.scalars(
            select(Chat)
            .where(Chat.id.in_(ids))
            .options(selectinload(Chat.members).selectinload(ChatMember.user))
        )
        .unique()
        .all()
    )
    dialogs: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    group_entities: list[dict[str, Any]] = []
    users: dict[int, User] = {current_user.id: current_user}
    for chat in chats:
        for member in chat.members:
            users[member.user_id] = member.user
        last = db.scalar(
            select(Message).where(Message.chat_id == chat.id).order_by(Message.id.desc()).limit(1)
        )
        top_id = last.id if last else 0
        membership = next((m for m in chat.members if m.user_id == current_user.id), None)
        read_id = membership.last_read_message_id if membership else None
        dialogs.append(
            {
                "_": "dialog",
                "peer": _peer_for_chat(chat, current_user.id),
                "top_message": top_id,
                "read_inbox_max_id": read_id or 0,
                "read_outbox_max_id": top_id,
                "unread_count": 0,
                "notify_settings": {"_": "peerNotifySettings"},
                "pFlags": {},
            }
        )
        if last:
            messages.append(_message(last, chat, current_user.id))
        if chat.type != "direct":
            group_entities.append(_chat_entity(chat))
    return {
        "_": "messages.dialogs",
        "dialogs": dialogs,
        "messages": messages,
        "chats": group_entities,
        "users": [_user(u, current_user.id) for u in users.values()],
    }


@router.post("/invoke")
def invoke(
    payload: RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "users.getUsers":
        return [_user(current_user, current_user.id)]
    if method in {"messages.getDialogs", "messages.getPinnedDialogs"}:
        return _dialogs(current_user, db)
    if method == "messages.getHistory":
        chat = _resolve_peer(params.get("peer"), current_user, db)
        limit = max(1, min(int(params.get("limit", 50)), 100))
        offset_id = int(params.get("offset_id", 0))
        stmt = select(Message).where(Message.chat_id == chat.id)
        if offset_id:
            stmt = stmt.where(Message.id < offset_id)
        rows = list(db.scalars(stmt.order_by(Message.id.desc()).limit(limit)).all())
        rows.reverse()
        users = {m.user_id: m.user for m in chat.members}
        return {
            "_": "messages.messages",
            "messages": [_message(m, chat, current_user.id) for m in rows],
            "chats": [] if chat.type == "direct" else [_chat_entity(chat)],
            "users": [_user(u, current_user.id) for u in users.values()],
        }
    if method == "messages.sendMessage":
        chat = _resolve_peer(params.get("peer"), current_user, db)
        text = str(params.get("message", "")).strip()
        if not text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message is empty")
        message = Message(chat_id=chat.id, sender_id=current_user.id, content=text, type="text")
        db.add(message)
        db.commit()
        db.refresh(message)
        item = _message(message, chat, current_user.id)
        return {
            "_": "updates",
            "updates": [
                {"_": "updateNewMessage", "message": item, "pts": message.id, "pts_count": 1}
            ],
            "users": [_user(current_user, current_user.id)],
            "chats": [] if chat.type == "direct" else [_chat_entity(chat)],
            "date": _unix(message.created_at),
            "seq": message.id,
        }
    if method == "messages.readHistory":
        chat = _resolve_peer(params.get("peer"), current_user, db)
        membership = _membership(chat.id, current_user.id, db)
        if membership is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a chat member")
        membership.last_read_message_id = int(params.get("max_id", 0)) or None
        db.commit()
        return {"_": "messages.affectedMessages", "pts": 0, "pts_count": 0}
    if method == "contacts.search":
        query = str(params.get("q", "")).strip().lstrip("@").lower()
        stmt = select(User).where(User.id != current_user.id)
        if query:
            stmt = stmt.where(User.username.ilike(f"%{query}%"))
        found = list(db.scalars(stmt.limit(50)).all())
        return {
            "_": "contacts.found",
            "my_results": [],
            "results": [{"_": "peerUser", "user_id": u.id} for u in found],
            "chats": [],
            "users": [_user(u, current_user.id) for u in found],
        }
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        f"ROOF_METHOD_NOT_IMPLEMENTED: {method}",
    )
