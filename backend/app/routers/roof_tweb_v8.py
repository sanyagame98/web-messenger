from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.message_feature_models import MessageMeta, PinnedMessage
from app.models import Chat, ChatMember, Message, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v3 as v3
from app.routers import roof_tweb_v4 as v4
from app.routers import roof_tweb_v7 as v7
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _is_self_peer(peer: Any, current_user: User) -> bool:
    if not isinstance(peer, dict):
        return False
    kind = str(peer.get("_", ""))
    if kind in {"inputPeerSelf", "peerSelf"}:
        return True
    return kind in {"inputPeerUser", "peerUser"} and int(
        peer.get("user_id", 0) or 0
    ) == current_user.id


def _saved_chat(current_user: User, db: Session) -> Chat:
    ids = list(
        db.scalars(
            select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)
        ).all()
    )
    if ids:
        chats = list(
            db.scalars(
                select(Chat)
                .where(Chat.id.in_(ids), Chat.type == "direct")
                .options(selectinload(Chat.members).selectinload(ChatMember.user))
            ).unique().all()
        )
        for chat in chats:
            if len(chat.members) == 1 and chat.members[0].user_id == current_user.id:
                return chat

    chat = Chat(type="direct", name="Saved Messages", created_by=current_user.id)
    db.add(chat)
    db.flush()
    db.add(
        ChatMember(
            chat_id=chat.id,
            user_id=current_user.id,
            role="member",
        )
    )
    db.commit()
    return db.scalar(
        select(Chat)
        .where(Chat.id == chat.id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )


def _resolve_peer(peer: Any, current_user: User, db: Session) -> Chat:
    if _is_self_peer(peer, current_user):
        return _saved_chat(current_user, db)
    return legacy._resolve_peer(peer, current_user, db)


def _peer(chat: Chat, current_user: User) -> dict[str, Any]:
    if chat.type == "channel":
        return {"_": "peerChannel", "channel_id": chat.id}
    if chat.type == "direct" and len(chat.members) == 1:
        return {"_": "peerUser", "user_id": current_user.id}
    return legacy._peer_for_chat(chat, current_user.id)


def _message_item(message: Message, chat: Chat, current_user: User, db: Session) -> dict[str, Any]:
    item: dict[str, Any] = {
        "_": "message",
        "id": message.id,
        "peer_id": _peer(chat, current_user),
        "date": legacy._unix(message.created_at),
        "message": message.content,
        "pFlags": {"out": True} if message.sender_id == current_user.id else {},
    }
    if message.sender_id is not None:
        item["from_id"] = {"_": "peerUser", "user_id": message.sender_id}
    if message.image_url:
        item["roof_media"] = {"type": "image", "url": message.image_url}
    v4._decorate_message(item, current_user.id, db)
    return item


def _entity(chat: Chat) -> dict[str, Any] | None:
    if chat.type == "direct":
        return None
    if chat.type == "channel":
        return v3._channel_entity(chat)
    return legacy._chat_entity(chat)


def _load_user_chats(current_user: User, db: Session) -> list[Chat]:
    ids = list(
        db.scalars(
            select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)
        ).all()
    )
    if not ids:
        return []
    return list(
        db.scalars(
            select(Chat)
            .where(Chat.id.in_(ids))
            .options(selectinload(Chat.members).selectinload(ChatMember.user))
        ).unique().all()
    )


def _dialog_for_chat(
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
    membership = next(
        (item for item in chat.members if item.user_id == current_user.id),
        None,
    )
    top_id = last.id if last else 0
    return (
        {
            "_": "dialog",
            "peer": _peer(chat, current_user),
            "top_message": top_id,
            "read_inbox_max_id": membership.last_read_message_id if membership else 0,
            "read_outbox_max_id": top_id,
            "unread_count": 0,
            "notify_settings": {"_": "peerNotifySettings"},
            "pFlags": {},
        },
        last,
    )


def _dialogs(current_user: User, db: Session) -> Any:
    chats = _load_user_chats(current_user, db)
    entries: list[tuple[int, dict[str, Any], Message | None, Chat]] = []
    users: dict[int, User] = {current_user.id: current_user}
    entities: dict[int, dict[str, Any]] = {}

    for chat in chats:
        dialog, last = _dialog_for_chat(chat, current_user, db)
        entries.append((dialog["top_message"], dialog, last, chat))
        for member in chat.members:
            users[member.user_id] = member.user
        entity = _entity(chat)
        if entity is not None:
            entities[chat.id] = entity

    entries.sort(key=lambda item: item[0], reverse=True)
    result = {
        "_": "messages.dialogs",
        "dialogs": [item[1] for item in entries],
        "messages": [
            _message_item(last, chat, current_user, db)
            for _, _, last, chat in entries
            if last is not None
        ],
        "chats": list(entities.values()),
        "users": [legacy._user(user, current_user.id) for user in users.values()],
    }
    return v7._decorate_result(result, current_user, db)


def _peer_dialogs(params: dict[str, Any], current_user: User, db: Session) -> Any:
    raw_peers = params.get("peers") or []
    dialogs: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    chats: dict[int, dict[str, Any]] = {}
    users: dict[int, User] = {current_user.id: current_user}

    for raw in raw_peers:
        peer = raw.get("peer", raw) if isinstance(raw, dict) else raw
        chat = _resolve_peer(peer, current_user, db)
        dialog, last = _dialog_for_chat(chat, current_user, db)
        dialogs.append(dialog)
        if last is not None:
            messages.append(_message_item(last, chat, current_user, db))
        entity = _entity(chat)
        if entity is not None:
            chats[chat.id] = entity
        for member in chat.members:
            users[member.user_id] = member.user

    result = {
        "_": "messages.peerDialogs",
        "dialogs": dialogs,
        "messages": messages,
        "chats": list(chats.values()),
        "users": [legacy._user(user, current_user.id) for user in users.values()],
        "state": legacy._updates_state(),
    }
    return v7._decorate_result(result, current_user, db)


def _saved_history(params: dict[str, Any], current_user: User, db: Session) -> Any:
    chat = _saved_chat(current_user, db)
    limit = max(1, min(int(params.get("limit", 50)), 100))
    offset_id = int(params.get("offset_id", 0) or 0)
    stmt = select(Message).where(Message.chat_id == chat.id)
    if offset_id:
        stmt = stmt.where(Message.id < offset_id)
    rows = list(db.scalars(stmt.order_by(Message.id.desc()).limit(limit)).all())
    rows.reverse()
    result = {
        "_": "messages.messages",
        "messages": [_message_item(row, chat, current_user, db) for row in rows],
        "chats": [],
        "users": [legacy._user(current_user, current_user.id)],
    }
    return v7._decorate_result(result, current_user, db)


async def _send_saved(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> Any:
    chat = _saved_chat(current_user, db)
    text = str(params.get("message", "")).strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Message is empty")
    reply_to = v7._reply_id(params)
    if reply_to:
        source = db.get(Message, reply_to)
        if source is None or source.chat_id != chat.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Roof Saved Messages reply target was not found",
            )

    message = Message(
        chat_id=chat.id,
        sender_id=current_user.id,
        content=text,
        type="text",
    )
    db.add(message)
    db.flush()
    if reply_to:
        db.add(MessageMeta(message_id=message.id, reply_to_message_id=reply_to))
    db.commit()
    db.refresh(message)

    item = _message_item(message, chat, current_user, db)
    result = {
        "_": "updates",
        "updates": [
            {
                "_": "updateNewMessage",
                "message": item,
                "pts": message.id,
                "pts_count": 1,
            }
        ],
        "users": [legacy._user(current_user, current_user.id)],
        "chats": [],
        "date": legacy._unix(message.created_at),
        "seq": message.id,
    }
    await manager.send_to_user(
        current_user.id,
        {
            "type": "roof_message",
            "chat_id": chat.id,
            "chat_type": "direct",
            "member_user_ids": [current_user.id],
            "message": {
                "id": message.id,
                "sender_id": message.sender_id,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            },
        },
    )
    return v7._decorate_result(result, current_user, db)


def _saved_search(params: dict[str, Any], current_user: User, db: Session) -> Any:
    chat = _saved_chat(current_user, db)
    query = str(params.get("q", "")).strip()
    limit = max(1, min(int(params.get("limit", 50)), 100))
    stmt = select(Message).where(Message.chat_id == chat.id)
    if query:
        stmt = stmt.where(Message.content.ilike(f"%{query}%"))
    rows = list(db.scalars(stmt.order_by(Message.id.desc()).limit(limit)).all())
    result = {
        "_": "messages.messages",
        "messages": [_message_item(row, chat, current_user, db) for row in rows],
        "chats": [],
        "users": [legacy._user(current_user, current_user.id)],
    }
    return v7._decorate_result(result, current_user, db)


async def _saved_pin(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = _saved_chat(current_user, db)
    message_id = int(params.get("id", 0) or 0)
    message = db.get(Message, message_id)
    if message is None or message.chat_id != chat.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof saved message not found")
    row = db.scalar(
        select(PinnedMessage).where(
            PinnedMessage.chat_id == chat.id,
            PinnedMessage.message_id == message_id,
        )
    )
    unpin = bool(params.get("unpin", False))
    if unpin and row is not None:
        db.delete(row)
    elif not unpin and row is None:
        db.add(
            PinnedMessage(
                chat_id=chat.id,
                message_id=message_id,
                pinned_by_user_id=current_user.id,
            )
        )
    db.commit()
    update = {
        "_": "updatePinnedMessages",
        "peer": {"_": "peerUser", "user_id": current_user.id},
        "messages": [message_id],
        "pFlags": {} if unpin else {"pinned": True},
    }
    await manager.send_to_user(current_user.id, {"roof_update": update})
    return {
        "_": "updates",
        "updates": [update],
        "users": [],
        "chats": [],
        "date": legacy._unix(None),
        "seq": message_id,
    }


def _saved_pins(params: dict[str, Any], current_user: User, db: Session) -> Any:
    chat = _saved_chat(current_user, db)
    limit = max(1, min(int(params.get("limit", 50)), 100))
    ids = list(
        db.scalars(
            select(PinnedMessage.message_id)
            .where(PinnedMessage.chat_id == chat.id)
            .order_by(PinnedMessage.id.desc())
            .limit(limit)
        ).all()
    )
    rows = (
        list(
            db.scalars(
                select(Message)
                .where(Message.id.in_(ids))
                .order_by(Message.id.desc())
            ).all()
        )
        if ids
        else []
    )
    result = {
        "_": "messages.messages",
        "messages": [_message_item(row, chat, current_user, db) for row in rows],
        "chats": [],
        "users": [legacy._user(current_user, current_user.id)],
    }
    return v7._decorate_result(result, current_user, db)


async def _saved_unpin_all(current_user: User, db: Session) -> dict[str, Any]:
    chat = _saved_chat(current_user, db)
    db.execute(delete(PinnedMessage).where(PinnedMessage.chat_id == chat.id))
    db.commit()
    update = {
        "_": "updatePinnedMessages",
        "peer": {"_": "peerUser", "user_id": current_user.id},
        "messages": [],
        "pFlags": {},
    }
    await manager.send_to_user(current_user.id, {"roof_update": update})
    return {"_": "messages.affectedHistory", "pts": 0, "pts_count": 0, "offset": 0}


async def _forward(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> Any:
    source_chat = _resolve_peer(params.get("from_peer"), current_user, db)
    target_chat = _resolve_peer(params.get("to_peer"), current_user, db)
    if target_chat.type == "channel" and not v3._can_manage(target_chat, current_user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot post to this Roof channel")

    raw_ids = params.get("id") or []
    if not isinstance(raw_ids, list):
        raw_ids = [raw_ids]
    ids = [int(value) for value in raw_ids if int(value) > 0]
    sources = list(
        db.scalars(
            select(Message)
            .where(Message.chat_id == source_chat.id, Message.id.in_(ids))
            .order_by(Message.id.asc())
        ).all()
    )
    created: list[Message] = []
    drop_author = bool(params.get("drop_author", False))
    for source in sources:
        message = Message(
            chat_id=target_chat.id,
            sender_id=current_user.id,
            type=source.type,
            content=source.content,
            image_url=source.image_url,
        )
        db.add(message)
        db.flush()
        if not drop_author:
            db.add(
                MessageMeta(
                    message_id=message.id,
                    forward_from_message_id=source.id,
                    forward_from_chat_id=source.chat_id,
                    forward_from_user_id=source.sender_id,
                )
            )
        created.append(message)
    db.commit()

    updates = []
    for message in created:
        db.refresh(message)
        item = _message_item(message, target_chat, current_user, db)
        updates.append(
            {
                "_": "updateNewMessage",
                "message": item,
                "pts": message.id,
                "pts_count": 1,
            }
        )
        await manager.broadcast_chat(
            target_chat.id,
            {
                "type": "roof_message",
                "chat_id": target_chat.id,
                "chat_type": target_chat.type,
                "member_user_ids": [member.user_id for member in target_chat.members],
                "message": {
                    "id": message.id,
                    "sender_id": message.sender_id,
                    "content": message.content,
                    "created_at": message.created_at.isoformat(),
                },
            },
        )
    result = {
        "_": "updates",
        "updates": updates,
        "users": [legacy._user(current_user, current_user.id)],
        "chats": [],
        "date": legacy._unix(None),
        "seq": max((message.id for message in created), default=0),
    }
    entity = _entity(target_chat)
    if entity is not None:
        result["chats"] = [entity]
    return v7._decorate_result(result, current_user, db)


@router.post("/invoke")
async def invoke_v8(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method in {"messages.getDialogs", "messages.getPinnedDialogs"}:
        return _dialogs(current_user, db)
    if method == "messages.getPeerDialogs":
        return _peer_dialogs(params, current_user, db)

    peer = params.get("peer")
    is_self = _is_self_peer(peer, current_user)
    if method == "messages.getHistory" and is_self:
        return _saved_history(params, current_user, db)
    if method == "messages.sendMessage" and is_self:
        return await _send_saved(params, current_user, db)
    if method == "messages.search" and is_self:
        return _saved_search(params, current_user, db)
    if method == "messages.updatePinnedMessage" and is_self:
        return await _saved_pin(params, current_user, db)
    if method == "messages.getPinnedHistory" and is_self:
        return _saved_pins(params, current_user, db)
    if method == "messages.unpinAllMessages" and is_self:
        return await _saved_unpin_all(current_user, db)

    if method == "messages.forwardMessages":
        from_self = _is_self_peer(params.get("from_peer"), current_user)
        to_self = _is_self_peer(params.get("to_peer"), current_user)
        if from_self or to_self:
            return await _forward(params, current_user, db)

    return await v7.invoke_v7(payload, current_user, db)
