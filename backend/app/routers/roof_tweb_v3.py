from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, Message, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v2 as v2
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _now() -> int:
    return int(datetime.now(UTC).timestamp())


def _load_chat(chat_id: int, current_user: User, db: Session) -> Chat:
    chat = db.scalar(
        select(Chat)
        .where(Chat.id == chat_id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof chat not found")
    if not any(member.user_id == current_user.id for member in chat.members):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a Roof chat member")
    return chat


def _member(chat: Chat, user_id: int) -> ChatMember | None:
    return next((item for item in chat.members if item.user_id == user_id), None)


def _can_manage(chat: Chat, user_id: int) -> bool:
    member = _member(chat, user_id)
    return bool(member and member.role in {"owner", "admin"})


def _channel_entity(chat: Chat) -> dict[str, Any]:
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


def _channel_full(chat: Chat, current_user: User) -> dict[str, Any]:
    return {
        "_": "messages.chatFull",
        "full_chat": {
            "_": "channelFull",
            "id": chat.id,
            "about": "",
            "participants_count": len(chat.members),
            "admins_count": sum(1 for item in chat.members if item.role in {"owner", "admin"}),
            "banned_count": 0,
            "kicked_count": 0,
            "online_count": 0,
            "read_inbox_max_id": 0,
            "read_outbox_max_id": 0,
            "unread_count": 0,
            "chat_photo": {"_": "photoEmpty", "id": "0"},
            "notify_settings": {"_": "peerNotifySettings"},
            "bot_info": [],
            "pts": 0,
            "pFlags": {},
        },
        "chats": [_channel_entity(chat)],
        "users": [legacy._user(item.user, current_user.id) for item in chat.members],
    }


def _updates(chat: Chat, current_user: User) -> dict[str, Any]:
    return {
        "_": "updates",
        "updates": [],
        "users": [legacy._user(item.user, current_user.id) for item in chat.members],
        "chats": [_channel_entity(chat)],
        "date": _now(),
        "seq": 0,
    }


def _channelize(result: Any, current_user: User, db: Session) -> Any:
    if not isinstance(result, dict):
        return result
    raw_chats = result.get("chats")
    if not isinstance(raw_chats, list):
        return result

    channel_ids: set[int] = set()
    for item in raw_chats:
        if not isinstance(item, dict):
            continue
        chat_id = int(item.get("id", 0) or 0)
        chat = db.get(Chat, chat_id)
        if chat is not None and chat.type == "channel":
            channel_ids.add(chat_id)
            item.clear()
            item.update(_channel_entity(chat))

    if not channel_ids:
        return result

    for dialog in result.get("dialogs") or []:
        if not isinstance(dialog, dict):
            continue
        peer = dialog.get("peer")
        if isinstance(peer, dict) and int(peer.get("chat_id", 0) or 0) in channel_ids:
            chat_id = int(peer.get("chat_id"))
            dialog["peer"] = {"_": "peerChannel", "channel_id": chat_id}

    for message in result.get("messages") or []:
        if not isinstance(message, dict):
            continue
        peer = message.get("peer_id")
        if isinstance(peer, dict) and int(peer.get("chat_id", 0) or 0) in channel_ids:
            chat_id = int(peer.get("chat_id"))
            message["peer_id"] = {"_": "peerChannel", "channel_id": chat_id}

    return result


def _channel_id(value: Any) -> int:
    if isinstance(value, dict):
        return int(value.get("channel_id", 0) or value.get("chat_id", 0) or 0)
    return int(value or 0)


def _create_channel(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    title = str(params.get("title", "")).strip()[:120]
    if not title:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof channel title is required")
    chat = Chat(type="channel", name=title, created_by=current_user.id)
    db.add(chat)
    db.flush()
    db.add(ChatMember(chat_id=chat.id, user_id=current_user.id, role="owner"))
    db.commit()
    return _updates(_load_chat(chat.id, current_user, db), current_user)


def _invite_channel(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = _load_chat(_channel_id(params.get("channel")), current_user, db)
    if chat.type != "channel" or not _can_manage(chat, current_user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Roof channel admins can invite users")
    values = params.get("users") or []
    if not isinstance(values, list):
        values = [values]
    for value in values:
        user_id = legacy._input_user_id(value, current_user)
        if user_id <= 0 or db.get(User, user_id) is None:
            continue
        exists = db.scalar(
            select(ChatMember.id).where(
                ChatMember.chat_id == chat.id,
                ChatMember.user_id == user_id,
            )
        )
        if exists is None:
            db.add(ChatMember(chat_id=chat.id, user_id=user_id, role="member"))
    db.commit()
    return _updates(_load_chat(chat.id, current_user, db), current_user)


def _edit_channel_title(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = _load_chat(_channel_id(params.get("channel")), current_user, db)
    if not _can_manage(chat, current_user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Roof channel admins can edit it")
    title = str(params.get("title", "")).strip()[:120]
    if not title:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof channel title is required")
    chat.name = title
    db.commit()
    return _updates(_load_chat(chat.id, current_user, db), current_user)


async def _set_typing(params: dict[str, Any], current_user: User, db: Session) -> bool:
    chat = legacy._resolve_peer(params.get("peer"), current_user, db)
    await manager.broadcast_chat(
        chat.id,
        {"type": "typing", "chat_id": chat.id, "user_id": current_user.id},
    )
    return True


async def _edit_message(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = legacy._resolve_peer(params.get("peer"), current_user, db)
    message = db.get(Message, int(params.get("id", 0)))
    if message is None or message.chat_id != chat.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof message not found")
    if message.sender_id != current_user.id and not _can_manage(chat, current_user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot edit this Roof message")
    text = str(params.get("message", "")).strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message is empty")
    message.content = text
    message.edited = True
    db.commit()
    db.refresh(message)
    item = legacy._message(message, chat, current_user.id)
    if chat.type == "channel":
        item["peer_id"] = {"_": "peerChannel", "channel_id": chat.id}
    await manager.broadcast_chat(
        chat.id,
        {
            "type": "roof_message_edit",
            "chat_id": chat.id,
            "chat_type": chat.type,
            "member_user_ids": [member.user_id for member in chat.members],
            "message": {
                "id": message.id,
                "sender_id": message.sender_id,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
                "edited": True,
            },
        },
    )
    return {
        "_": "updates",
        "updates": [{"_": "updateEditMessage", "message": item, "pts": message.id, "pts_count": 1}],
        "users": [legacy._user(current_user, current_user.id)],
        "chats": [_channel_entity(chat)] if chat.type == "channel" else [],
        "date": _now(),
        "seq": message.id,
    }


async def _delete_messages(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    ids = params.get("id") or []
    if not isinstance(ids, list):
        ids = [ids]
    deleted: list[int] = []
    by_chat: dict[int, list[int]] = {}
    for raw_id in ids:
        message = db.get(Message, int(raw_id))
        if message is None:
            continue
        chat = _load_chat(message.chat_id, current_user, db)
        if message.sender_id != current_user.id and not _can_manage(chat, current_user.id):
            continue
        deleted.append(message.id)
        by_chat.setdefault(chat.id, []).append(message.id)
        db.delete(message)
    db.commit()
    for chat_id, message_ids in by_chat.items():
        await manager.broadcast_chat(
            chat_id,
            {"type": "roof_messages_deleted", "chat_id": chat_id, "message_ids": message_ids},
        )
    top = max(deleted, default=0)
    return {"_": "messages.affectedMessages", "pts": top, "pts_count": len(deleted)}


@router.post("/invoke")
async def invoke_v3(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "channels.createChannel":
        return _create_channel(params, current_user, db)
    if method == "channels.getChannels":
        values = params.get("id") or []
        if not isinstance(values, list):
            values = [values]
        chats = []
        for value in values:
            chat_id = _channel_id(value)
            if chat_id <= 0:
                continue
            try:
                chat = _load_chat(chat_id, current_user, db)
            except HTTPException:
                continue
            if chat.type == "channel":
                chats.append(_channel_entity(chat))
        return {"_": "messages.chats", "chats": chats}
    if method == "channels.getFullChannel":
        chat = _load_chat(_channel_id(params.get("channel")), current_user, db)
        return _channel_full(chat, current_user)
    if method == "channels.inviteToChannel":
        return _invite_channel(params, current_user, db)
    if method == "channels.editTitle":
        return _edit_channel_title(params, current_user, db)
    if method == "channels.leaveChannel":
        chat = _load_chat(_channel_id(params.get("channel")), current_user, db)
        membership = _member(chat, current_user.id)
        if membership is not None:
            db.delete(membership)
            db.commit()
        return {
            "_": "updates",
            "updates": [],
            "users": [],
            "chats": [],
            "date": _now(),
            "seq": 0,
        }
    if method == "channels.deleteChannel":
        chat = _load_chat(_channel_id(params.get("channel")), current_user, db)
        membership = _member(chat, current_user.id)
        if membership is None or membership.role != "owner":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Roof channel owner can delete it")
        db.delete(chat)
        db.commit()
        return {
            "_": "updates",
            "updates": [],
            "users": [],
            "chats": [],
            "date": _now(),
            "seq": 0,
        }

    if method == "messages.setTyping":
        return await _set_typing(params, current_user, db)
    if method == "messages.editMessage":
        return await _edit_message(params, current_user, db)
    if method == "messages.deleteMessages":
        return await _delete_messages(params, current_user, db)

    if method == "messages.sendMessage":
        chat = legacy._resolve_peer(params.get("peer"), current_user, db)
        if chat.type == "channel" and not _can_manage(chat, current_user.id):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Roof channel admins can post")
        result = await v2.invoke_v2(payload, current_user, db)
        if chat.type == "channel":
            result = _channelize(result, current_user, db)
            for update in result.get("updates") or []:
                message = update.get("message") if isinstance(update, dict) else None
                if isinstance(message, dict):
                    message["peer_id"] = {"_": "peerChannel", "channel_id": chat.id}
            result["chats"] = [_channel_entity(chat)]
        return result

    if method in {"messages.getDialogs", "messages.getPinnedDialogs", "messages.getPeerDialogs"}:
        return _channelize(await v2.invoke_v2(payload, current_user, db), current_user, db)

    if method == "messages.getHistory":
        chat = legacy._resolve_peer(params.get("peer"), current_user, db)
        result = await v2.invoke_v2(payload, current_user, db)
        if chat.type == "channel":
            for message in result.get("messages") or []:
                message["peer_id"] = {"_": "peerChannel", "channel_id": chat.id}
            result["chats"] = [_channel_entity(chat)]
        return result

    return await v2.invoke_v2(payload, current_user, db)
