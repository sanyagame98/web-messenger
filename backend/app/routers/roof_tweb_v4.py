from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, Message, User
from app.reaction_models import MessageReaction
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v3 as v3
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _reaction_key(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    if isinstance(value, dict):
        kind = str(value.get("_", ""))
        if kind == "reactionEmoji":
            emoticon = str(value.get("emoticon", "")).strip()
            return f"emoji:{emoticon}" if emoticon else None
        if kind == "reactionCustomEmoji":
            document_id = str(value.get("document_id", "")).strip()
            return f"custom:{document_id}" if document_id else None
    text = str(value).strip()
    return f"emoji:{text}" if text else None


def _tl_reaction(key: str) -> dict[str, Any]:
    if key.startswith("custom:"):
        return {"_": "reactionCustomEmoji", "document_id": key.removeprefix("custom:")}
    return {"_": "reactionEmoji", "emoticon": key.removeprefix("emoji:")}


def _peer_for_chat(chat: Chat, current_user_id: int) -> dict[str, Any]:
    if chat.type == "channel":
        return {"_": "peerChannel", "channel_id": chat.id}
    return legacy._peer_for_chat(chat, current_user_id)


def _summary(message_id: int, current_user_id: int, db: Session) -> dict[str, Any] | None:
    rows = list(
        db.scalars(
            select(MessageReaction)
            .where(MessageReaction.message_id == message_id)
            .order_by(MessageReaction.id.asc())
        ).all()
    )
    if not rows:
        return None

    counts = Counter(row.reaction for row in rows)
    chosen = next((row.reaction for row in rows if row.user_id == current_user_id), None)
    results: list[dict[str, Any]] = []
    for key, count in counts.items():
        item: dict[str, Any] = {
            "_": "reactionCount",
            "reaction": _tl_reaction(key),
            "count": count,
        }
        if key == chosen:
            item["chosen_order"] = 0
        results.append(item)

    return {
        "_": "messageReactions",
        "results": results,
        "recent_reactions": [],
        "pFlags": {"can_see_list": True},
    }


def _decorate_message(item: Any, current_user_id: int, db: Session) -> None:
    if not isinstance(item, dict):
        return
    message_id = int(item.get("id", 0) or 0)
    if message_id <= 0:
        return
    summary = _summary(message_id, current_user_id, db)
    if summary is not None:
        item["reactions"] = summary


def _decorate(result: Any, current_user_id: int, db: Session) -> Any:
    if not isinstance(result, dict):
        return result
    for item in result.get("messages") or []:
        _decorate_message(item, current_user_id, db)
    for update in result.get("updates") or []:
        if isinstance(update, dict):
            _decorate_message(update.get("message"), current_user_id, db)
    return result


def _load_message_for_peer(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> tuple[Message, Chat]:
    chat = legacy._resolve_peer(params.get("peer"), current_user, db)
    message_id = int(params.get("msg_id") or params.get("id") or 0)
    message = db.get(Message, message_id)
    if message is None or message.chat_id != chat.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof message not found")
    return message, chat


async def _send_reaction(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    message, chat = _load_message_for_peer(params, current_user, db)
    key = _reaction_key(params.get("reaction"))
    row = db.scalar(
        select(MessageReaction).where(
            MessageReaction.message_id == message.id,
            MessageReaction.user_id == current_user.id,
        )
    )
    if key is None:
        if row is not None:
            db.delete(row)
    elif row is None:
        db.add(
            MessageReaction(
                message_id=message.id,
                user_id=current_user.id,
                reaction=key,
            )
        )
    else:
        row.reaction = key
    db.commit()

    reactions = _summary(message.id, current_user.id, db)
    peer = _peer_for_chat(chat, current_user.id)
    update = {
        "_": "updateMessageReactions",
        "peer": peer,
        "msg_id": message.id,
        "top_msg_id": 0,
        "reactions": reactions,
    }
    await manager.broadcast_chat(
        chat.id,
        {
            "type": "roof_reaction",
            "chat_id": chat.id,
            "chat_type": chat.type,
            "member_user_ids": [member.user_id for member in chat.members],
            "message_id": message.id,
            "reaction_user_id": current_user.id,
            "reactions": reactions,
        },
    )
    return {
        "_": "updates",
        "updates": [update],
        "users": [legacy._user(current_user, current_user.id)],
        "chats": [],
        "date": legacy._unix(None),
        "seq": message.id,
    }


def _reaction_list(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    message, _ = _load_message_for_peer(params, current_user, db)
    filter_key = _reaction_key(params.get("reaction"))
    stmt = select(MessageReaction).where(MessageReaction.message_id == message.id)
    if filter_key is not None:
        stmt = stmt.where(MessageReaction.reaction == filter_key)
    rows = list(db.scalars(stmt.order_by(MessageReaction.id.desc()).limit(100)).all())
    user_ids = {row.user_id for row in rows}
    users = list(db.scalars(select(User).where(User.id.in_(user_ids))).all()) if user_ids else []
    return {
        "_": "messages.messageReactionsList",
        "count": len(rows),
        "reactions": [
            {
                "_": "messagePeerReaction",
                "peer_id": {"_": "peerUser", "user_id": row.user_id},
                "date": legacy._unix(row.created_at),
                "reaction": _tl_reaction(row.reaction),
                "pFlags": {},
            }
            for row in rows
        ],
        "chats": [],
        "users": [legacy._user(user, current_user.id) for user in users],
        "next_offset": "",
    }


def _reactions_updates(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = legacy._resolve_peer(params.get("peer"), current_user, db)
    ids = params.get("id") or []
    if not isinstance(ids, list):
        ids = [ids]
    updates = []
    for raw_id in ids:
        message = db.get(Message, int(raw_id))
        if message is None or message.chat_id != chat.id:
            continue
        reactions = _summary(message.id, current_user.id, db)
        if reactions is None:
            continue
        updates.append(
            {
                "_": "updateMessageReactions",
                "peer": _peer_for_chat(chat, current_user.id),
                "msg_id": message.id,
                "top_msg_id": 0,
                "reactions": reactions,
            }
        )
    return {
        "_": "updates",
        "updates": updates,
        "users": [],
        "chats": [],
        "date": legacy._unix(None),
        "seq": 0,
    }


@router.post("/invoke")
async def invoke_v4(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method

    if method == "messages.sendReaction":
        return await _send_reaction(payload.params, current_user, db)
    if method == "messages.getMessageReactionsList":
        return _reaction_list(payload.params, current_user, db)
    if method == "messages.getMessagesReactions":
        return _reactions_updates(payload.params, current_user, db)

    result = await v3.invoke_v3(payload, current_user, db)
    if method in {
        "messages.getDialogs",
        "messages.getPinnedDialogs",
        "messages.getPeerDialogs",
        "messages.getHistory",
        "messages.sendMessage",
        "messages.editMessage",
    }:
        return _decorate(result, current_user.id, db)
    return result
