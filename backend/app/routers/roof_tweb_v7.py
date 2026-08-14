from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.message_feature_models import MessageMeta, PinnedMessage
from app.models import Chat, ChatMember, Message, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v3 as v3
from app.routers import roof_tweb_v4 as v4
from app.routers import roof_tweb_v6 as v6
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _reply_id(params: dict[str, Any]) -> int:
    reply = params.get("reply_to")
    if isinstance(reply, dict):
        return int(reply.get("reply_to_msg_id", 0) or 0)
    return int(params.get("reply_to_msg_id", 0) or 0)


def _message_ids(result: Any) -> set[int]:
    if not isinstance(result, dict):
        return set()
    ids: set[int] = set()
    for item in result.get("messages") or []:
        if isinstance(item, dict):
            ids.add(int(item.get("id", 0) or 0))
    for update in result.get("updates") or []:
        if not isinstance(update, dict):
            continue
        message = update.get("message")
        if isinstance(message, dict):
            ids.add(int(message.get("id", 0) or 0))
    ids.discard(0)
    return ids


def _decorate_item(
    item: Any,
    meta_by_id: dict[int, MessageMeta],
    source_by_id: dict[int, Message],
    pinned_ids: set[int],
) -> None:
    if not isinstance(item, dict):
        return
    message_id = int(item.get("id", 0) or 0)
    if message_id <= 0:
        return

    meta = meta_by_id.get(message_id)
    if meta is not None and meta.reply_to_message_id:
        item["reply_to"] = {
            "_": "messageReplyHeader",
            "reply_to_msg_id": meta.reply_to_message_id,
            "pFlags": {},
        }
    if meta is not None and meta.forward_from_message_id:
        source = source_by_id.get(meta.forward_from_message_id)
        header: dict[str, Any] = {
            "_": "messageFwdHeader",
            "date": legacy._unix(source.created_at if source else None),
            "pFlags": {},
        }
        if meta.forward_from_user_id:
            header["from_id"] = {
                "_": "peerUser",
                "user_id": meta.forward_from_user_id,
            }
        item["fwd_from"] = header
    if message_id in pinned_ids:
        flags = item.setdefault("pFlags", {})
        if isinstance(flags, dict):
            flags["pinned"] = True


def _decorate_result(result: Any, current_user: User, db: Session) -> Any:
    ids = _message_ids(result)
    if not ids:
        return result

    metas = list(db.scalars(select(MessageMeta).where(MessageMeta.message_id.in_(ids))).all())
    meta_by_id = {meta.message_id: meta for meta in metas}
    source_ids = {
        meta.forward_from_message_id
        for meta in metas
        if meta.forward_from_message_id is not None
    }
    sources = (
        list(db.scalars(select(Message).where(Message.id.in_(source_ids))).all())
        if source_ids
        else []
    )
    source_by_id = {message.id: message for message in sources}
    pinned_ids = set(
        db.scalars(select(PinnedMessage.message_id).where(PinnedMessage.message_id.in_(ids))).all()
    )

    if isinstance(result, dict):
        for item in result.get("messages") or []:
            _decorate_item(item, meta_by_id, source_by_id, pinned_ids)
        for update in result.get("updates") or []:
            if isinstance(update, dict):
                _decorate_item(
                    update.get("message"),
                    meta_by_id,
                    source_by_id,
                    pinned_ids,
                )
    return result


def _ensure_accessible_message(
    message_id: int,
    current_user: User,
    db: Session,
) -> Message:
    message = db.get(Message, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof message not found")
    membership = db.scalar(
        select(ChatMember.id).where(
            ChatMember.chat_id == message.chat_id,
            ChatMember.user_id == current_user.id,
        )
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Roof message is not accessible")
    return message


def _can_pin(chat: Chat, current_user: User) -> bool:
    if chat.type == "direct":
        return True
    return v3._can_manage(chat, current_user.id)


async def _send_with_reply(
    payload: legacy.RoofInvokeRequest,
    current_user: User,
    db: Session,
) -> Any:
    reply_to = _reply_id(payload.params)
    chat = legacy._resolve_peer(payload.params.get("peer"), current_user, db)
    if reply_to:
        source = _ensure_accessible_message(reply_to, current_user, db)
        if source.chat_id != chat.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Roof reply must point to a message in the same chat",
            )

    result = await v6.invoke_v6(payload, current_user, db)
    if reply_to:
        ids = _message_ids(result)
        new_id = max(ids, default=0)
        if new_id:
            existing = db.get(MessageMeta, new_id)
            if existing is None:
                db.add(MessageMeta(message_id=new_id, reply_to_message_id=reply_to))
            else:
                existing.reply_to_message_id = reply_to
            db.commit()
    return _decorate_result(result, current_user, db)


async def _forward_messages(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    source_chat = legacy._resolve_peer(params.get("from_peer"), current_user, db)
    target_chat = legacy._resolve_peer(params.get("to_peer"), current_user, db)
    if target_chat.type == "channel" and not v3._can_manage(target_chat, current_user.id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only Roof channel admins can forward posts to this channel",
        )

    raw_ids = params.get("id") or []
    if not isinstance(raw_ids, list):
        raw_ids = [raw_ids]
    ids = [int(value) for value in raw_ids if int(value) > 0]
    source_messages = list(
        db.scalars(
            select(Message)
            .where(Message.chat_id == source_chat.id, Message.id.in_(ids))
            .order_by(Message.id.asc())
        ).all()
    )
    drop_author = bool(params.get("drop_author", False))
    created: list[Message] = []

    for source in source_messages:
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

    updates: list[dict[str, Any]] = []
    for message in created:
        db.refresh(message)
        item = legacy._message(message, target_chat, current_user.id)
        if target_chat.type == "channel":
            item["peer_id"] = {"_": "peerChannel", "channel_id": target_chat.id}
        v4._decorate_message(item, current_user.id, db)
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

    result: dict[str, Any] = {
        "_": "updates",
        "updates": updates,
        "users": [legacy._user(current_user, current_user.id)],
        "chats": [],
        "date": legacy._unix(None),
        "seq": max((message.id for message in created), default=0),
    }
    if target_chat.type == "channel":
        result["chats"] = [v3._channel_entity(target_chat)]
    elif target_chat.type != "direct":
        result["chats"] = [legacy._chat_entity(target_chat)]
    return _decorate_result(result, current_user, db)


async def _update_pin(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = legacy._resolve_peer(params.get("peer"), current_user, db)
    if not _can_pin(chat, current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot pin messages in this Roof chat")
    message_id = int(params.get("id", 0) or 0)
    message = _ensure_accessible_message(message_id, current_user, db)
    if message.chat_id != chat.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof message belongs to another chat")

    existing = db.scalar(
        select(PinnedMessage).where(
            PinnedMessage.chat_id == chat.id,
            PinnedMessage.message_id == message_id,
        )
    )
    unpin = bool(params.get("unpin", False))
    if unpin and existing is not None:
        db.delete(existing)
    elif not unpin and existing is None:
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
        "peer": legacy._peer_for_chat(chat, current_user.id),
        "messages": [message_id],
        "pFlags": {} if unpin else {"pinned": True},
    }
    if chat.type == "channel":
        update["peer"] = {"_": "peerChannel", "channel_id": chat.id}
    await manager.broadcast_chat(
        chat.id,
        {
            "roof_update": update,
            "chat_id": chat.id,
            "member_user_ids": [member.user_id for member in chat.members],
        },
    )
    return {
        "_": "updates",
        "updates": [update],
        "users": [],
        "chats": [],
        "date": legacy._unix(None),
        "seq": message_id,
    }


def _pinned_history(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> Any:
    chat = legacy._resolve_peer(params.get("peer"), current_user, db)
    limit = max(1, min(int(params.get("limit", 50)), 100))
    pins = list(
        db.scalars(
            select(PinnedMessage)
            .where(PinnedMessage.chat_id == chat.id)
            .order_by(PinnedMessage.id.desc())
            .limit(limit)
        ).all()
    )
    ids = [pin.message_id for pin in pins]
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
    result = v6._serialize_messages(rows, current_user, db)
    return _decorate_result(result, current_user, db)


async def _unpin_all(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = legacy._resolve_peer(params.get("peer"), current_user, db)
    if not _can_pin(chat, current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot unpin messages in this Roof chat")
    db.execute(delete(PinnedMessage).where(PinnedMessage.chat_id == chat.id))
    db.commit()
    update = {
        "_": "updatePinnedMessages",
        "peer": legacy._peer_for_chat(chat, current_user.id),
        "messages": [],
        "pFlags": {},
    }
    if chat.type == "channel":
        update["peer"] = {"_": "peerChannel", "channel_id": chat.id}
    await manager.broadcast_chat(chat.id, {"roof_update": update})
    return {
        "_": "messages.affectedHistory",
        "pts": 0,
        "pts_count": 0,
        "offset": 0,
    }


@router.post("/invoke")
async def invoke_v7(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method

    if method == "messages.sendMessage" and _reply_id(payload.params):
        return await _send_with_reply(payload, current_user, db)
    if method == "messages.forwardMessages":
        return await _forward_messages(payload.params, current_user, db)
    if method == "messages.updatePinnedMessage":
        return await _update_pin(payload.params, current_user, db)
    if method == "messages.getPinnedHistory":
        return _pinned_history(payload.params, current_user, db)
    if method == "messages.unpinAllMessages":
        return await _unpin_all(payload.params, current_user, db)

    result = await v6.invoke_v6(payload, current_user, db)
    if method in {
        "messages.getDialogs",
        "messages.getPinnedDialogs",
        "messages.getPeerDialogs",
        "messages.getHistory",
        "messages.search",
        "messages.searchGlobal",
        "messages.getMessages",
        "channels.getMessages",
        "messages.sendMessage",
        "messages.editMessage",
    }:
        return _decorate_result(result, current_user, db)
    return result
