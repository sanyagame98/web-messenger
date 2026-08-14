from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
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


def _updates_state() -> dict[str, Any]:
    return {
        "_": "updates.state",
        "pts": 0,
        "qts": 0,
        "date": _unix(None),
        "seq": 0,
        "unread_count": 0,
    }


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
        "usernames": [
            {
                "_": "username",
                "username": user.username,
                "pFlags": {"active": True},
            }
        ],
        "phone": "",
        "photo": {"_": "userProfilePhotoEmpty"},
        "status": {
            "_": "userStatusOffline",
            "was_online": _unix(user.last_seen_at),
        },
        "pFlags": flags,
    }


def _full_user(user: User) -> dict[str, Any]:
    return {
        "_": "userFull",
        "id": user.id,
        "about": user.bio,
        "settings": {"_": "peerSettings", "pFlags": {}},
        "notify_settings": {"_": "peerNotifySettings"},
        "common_chats_count": 0,
        "pFlags": {},
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
        other = next(
            (m.user for m in chat.members if m.user_id != current_user_id),
            None,
        )
        if other is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Broken direct chat")
        return {"_": "peerUser", "user_id": other.id}
    return {"_": "peerChat", "chat_id": chat.id}


def _message(
    message: Message,
    chat: Chat,
    current_user_id: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "_": "message",
        "id": message.id,
        "peer_id": _peer_for_chat(chat, current_user_id),
        "date": _unix(message.created_at),
        "message": message.content,
        "pFlags": {"out": True} if message.sender_id == current_user_id else {},
    }
    if message.sender_id is not None:
        result["from_id"] = {
            "_": "peerUser",
            "user_id": message.sender_id,
        }
    if message.image_url:
        result["roof_media"] = {
            "type": "image",
            "url": message.image_url,
        }
    return result


def _membership(
    chat_id: int,
    user_id: int,
    db: Session,
) -> ChatMember | None:
    return db.scalar(
        select(ChatMember).where(
            and_(
                ChatMember.chat_id == chat_id,
                ChatMember.user_id == user_id,
            )
        )
    )


def _direct_chat(
    user_id: int,
    other_id: int,
    db: Session,
) -> Chat | None:
    mine = set(
        db.scalars(
            select(ChatMember.chat_id).where(ChatMember.user_id == user_id)
        ).all()
    )
    theirs = set(
        db.scalars(
            select(ChatMember.chat_id).where(ChatMember.user_id == other_id)
        ).all()
    )
    common = mine & theirs
    if not common:
        return None
    return db.scalar(
        select(Chat)
        .where(Chat.id.in_(common), Chat.type == "direct")
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )


def _get_or_create_direct_chat(
    current_user: User,
    other_id: int,
    db: Session,
) -> Chat:
    if other_id <= 0 or other_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Roof user")
    existing = _direct_chat(current_user.id, other_id, db)
    if existing is not None:
        return existing

    other = db.get(User, other_id)
    if other is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof user not found")

    chat = Chat(type="direct", name="", created_by=current_user.id)
    db.add(chat)
    db.flush()
    db.add(
        ChatMember(
            chat_id=chat.id,
            user_id=current_user.id,
            role="member",
        )
    )
    db.add(
        ChatMember(
            chat_id=chat.id,
            user_id=other.id,
            role="member",
        )
    )
    db.commit()
    return db.scalar(
        select(Chat)
        .where(Chat.id == chat.id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )


def _resolve_peer(
    peer: Any,
    current_user: User,
    db: Session,
) -> Chat:
    if not isinstance(peer, dict):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Roof requires an explicit peer",
        )
    kind = str(peer.get("_", ""))
    if kind in {"inputPeerUser", "peerUser"}:
        return _get_or_create_direct_chat(
            current_user,
            int(peer.get("user_id", 0)),
            db,
        )
    if kind in {
        "inputPeerChat",
        "peerChat",
        "inputPeerChannel",
        "peerChannel",
    }:
        chat_id = int(peer.get("chat_id") or peer.get("channel_id") or 0)
        chat = db.scalar(
            select(Chat)
            .where(Chat.id == chat_id)
            .options(selectinload(Chat.members).selectinload(ChatMember.user))
        )
        if chat is not None and _membership(
            chat.id,
            current_user.id,
            db,
        ) is not None:
            return chat
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof peer not found")


def _dialog(
    chat: Chat,
    current_user: User,
    db: Session,
) -> tuple[dict[str, Any], Message | None]:
    last = db.scalar(
        select(Message)
        .where(Message.chat_id == chat.id)
        .order_by(Message.id.desc())
        .limit(1)
    )
    top_id = last.id if last else 0
    membership = next(
        (m for m in chat.members if m.user_id == current_user.id),
        None,
    )
    read_id = membership.last_read_message_id if membership else None
    item = {
        "_": "dialog",
        "peer": _peer_for_chat(chat, current_user.id),
        "top_message": top_id,
        "read_inbox_max_id": read_id or 0,
        "read_outbox_max_id": top_id,
        "unread_count": 0,
        "notify_settings": {"_": "peerNotifySettings"},
        "pFlags": {},
    }
    return item, last


def _dialogs(current_user: User, db: Session) -> dict[str, Any]:
    ids = db.scalars(
        select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)
    ).all()
    if not ids:
        return {
            "_": "messages.dialogs",
            "dialogs": [],
            "messages": [],
            "chats": [],
            "users": [_user(current_user, current_user.id)],
        }
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
        item, last = _dialog(chat, current_user, db)
        dialogs.append(item)
        if last:
            messages.append(_message(last, chat, current_user.id))
        if chat.type != "direct":
            group_entities.append(_chat_entity(chat))
    return {
        "_": "messages.dialogs",
        "dialogs": dialogs,
        "messages": messages,
        "chats": group_entities,
        "users": [
            _user(user, current_user.id)
            for user in users.values()
        ],
    }


def _input_user_id(value: Any, current_user: User) -> int:
    if isinstance(value, dict):
        kind = str(value.get("_", ""))
        if kind in {"inputUserSelf", "inputPeerSelf"}:
            return current_user.id
        return int(value.get("user_id", 0) or 0)
    return int(value or 0)


@router.post("/invoke")
async def invoke(
    payload: RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "users.getUsers":
        values = params.get("id") or []
        if not isinstance(values, list):
            values = [values]
        ids = {
            _input_user_id(value, current_user)
            for value in values
        }
        ids.discard(0)
        ids.add(current_user.id)
        users = list(db.scalars(select(User).where(User.id.in_(ids))).all())
        return [_user(user, current_user.id) for user in users]

    if method == "users.getFullUser":
        user_id = _input_user_id(params.get("id"), current_user)
        user = db.get(User, user_id or current_user.id)
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof user not found")
        return {
            "_": "users.userFull",
            "full_user": _full_user(user),
            "chats": [],
            "users": [_user(user, current_user.id)],
        }

    if method in {"messages.getDialogs", "messages.getPinnedDialogs"}:
        return _dialogs(current_user, db)

    if method == "messages.getPeerDialogs":
        raw_peers = params.get("peers") or []
        dialogs: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        chats: dict[int, dict[str, Any]] = {}
        users: dict[int, User] = {current_user.id: current_user}
        for raw in raw_peers:
            peer = raw.get("peer", raw) if isinstance(raw, dict) else raw
            chat = _resolve_peer(peer, current_user, db)
            item, last = _dialog(chat, current_user, db)
            dialogs.append(item)
            if last:
                messages.append(_message(last, chat, current_user.id))
            for member in chat.members:
                users[member.user_id] = member.user
            if chat.type != "direct":
                chats[chat.id] = _chat_entity(chat)
        return {
            "_": "messages.peerDialogs",
            "dialogs": dialogs,
            "messages": messages,
            "chats": list(chats.values()),
            "users": [
                _user(user, current_user.id)
                for user in users.values()
            ],
            "state": _updates_state(),
        }

    if method == "messages.getHistory":
        chat = _resolve_peer(params.get("peer"), current_user, db)
        limit = max(1, min(int(params.get("limit", 50)), 100))
        offset_id = int(params.get("offset_id", 0))
        stmt = select(Message).where(Message.chat_id == chat.id)
        if offset_id:
            stmt = stmt.where(Message.id < offset_id)
        rows = list(
            db.scalars(
                stmt.order_by(Message.id.desc()).limit(limit)
            ).all()
        )
        rows.reverse()
        users = {m.user_id: m.user for m in chat.members}
        return {
            "_": "messages.messages",
            "messages": [
                _message(message, chat, current_user.id)
                for message in rows
            ],
            "chats": [] if chat.type == "direct" else [_chat_entity(chat)],
            "users": [
                _user(user, current_user.id)
                for user in users.values()
            ],
        }

    if method == "messages.sendMessage":
        chat = _resolve_peer(params.get("peer"), current_user, db)
        text = str(params.get("message", "")).strip()
        if not text:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message is empty")
        message = Message(
            chat_id=chat.id,
            sender_id=current_user.id,
            content=text,
            type="text",
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        item = _message(message, chat, current_user.id)
        update = {
            "_": "updateNewMessage",
            "message": item,
            "pts": message.id,
            "pts_count": 1,
        }

        from app.websocket import manager

        await manager.broadcast_chat(
            chat.id,
            {
                "type": "roof_message",
                "chat_id": chat.id,
                "chat_type": chat.type,
                "member_user_ids": [m.user_id for m in chat.members],
                "message": {
                    "id": message.id,
                    "sender_id": message.sender_id,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                },
            },
        )
        return {
            "_": "updates",
            "updates": [update],
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
        return {
            "_": "messages.affectedMessages",
            "pts": 0,
            "pts_count": 0,
        }

    if method == "contacts.search":
        query = str(params.get("q", "")).strip().lstrip("@").lower()
        stmt = select(User).where(User.id != current_user.id)
        if query:
            stmt = stmt.where(
                or_(
                    User.username.ilike(f"%{query}%"),
                    User.display_name.ilike(f"%{query}%"),
                )
            )
        found = list(db.scalars(stmt.limit(50)).all())
        return {
            "_": "contacts.found",
            "my_results": [],
            "results": [
                {"_": "peerUser", "user_id": user.id}
                for user in found
            ],
            "chats": [],
            "users": [
                _user(user, current_user.id)
                for user in found
            ],
        }

    if method == "contacts.resolveUsername":
        username = str(params.get("username", "")).strip().lstrip("@").lower()
        user = db.scalar(
            select(User).where(User.username.ilike(username))
        )
        if user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof username not found")
        return {
            "_": "contacts.resolvedPeer",
            "peer": {"_": "peerUser", "user_id": user.id},
            "chats": [],
            "users": [_user(user, current_user.id)],
        }

    if method == "updates.getState":
        return _updates_state()

    if method == "updates.getDifference":
        return {
            "_": "updates.differenceEmpty",
            "date": _unix(None),
            "seq": 0,
        }

    if method == "account.getNotifySettings":
        return {"_": "peerNotifySettings"}

    if method == "messages.getDialogFilters":
        return []

    if method == "contacts.getContacts":
        return {
            "_": "contacts.contacts",
            "contacts": [],
            "saved_count": 0,
            "users": [],
        }

    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        f"ROOF_METHOD_NOT_IMPLEMENTED: {method}",
    )
