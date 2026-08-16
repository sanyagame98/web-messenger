from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channel_post_models import ChannelPostMeta, ChannelPostingPreference, ChannelPostView
from app.chat_meta_models import ChatMeta
from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, Message, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v20 as v20
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _channel(channel_id: int, current_user: User, db: Session) -> Chat:
    chat = db.get(Chat, channel_id)
    if chat is None or chat.type != "channel":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_CHANNEL_NOT_FOUND")
    member = db.scalar(
        select(ChatMember).where(
            ChatMember.chat_id == chat.id,
            ChatMember.user_id == current_user.id,
        )
    )
    if member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_CHANNEL_ACCESS_DENIED")
    return chat


def _is_manager(chat: Chat, user_id: int, db: Session) -> bool:
    member = db.scalar(
        select(ChatMember).where(
            ChatMember.chat_id == chat.id,
            ChatMember.user_id == user_id,
        )
    )
    return bool(member and member.role in {"owner", "admin"})


def _posting_pref(chat: Chat, db: Session, create: bool = True) -> ChannelPostingPreference | None:
    pref = db.get(ChannelPostingPreference, chat.id)
    if pref is None and create:
        pref = ChannelPostingPreference(channel_id=chat.id, author_mode="channel")
        db.add(pref)
        db.flush()
    return pref


def _post_meta(message: Message, db: Session, create: bool = True) -> ChannelPostMeta | None:
    row = db.get(ChannelPostMeta, message.id)
    if row is None and create:
        row = ChannelPostMeta(
            message_id=message.id,
            channel_id=message.chat_id,
            author_mode="channel",
            author_user_id=None,
            views_count=0,
        )
        db.add(row)
        db.flush()
    return row


def _post_link(channel: Chat, message_id: int, db: Session) -> str:
    meta = db.get(ChatMeta, channel.id)
    if meta is not None and meta.is_public and meta.username:
        return f"roof://{meta.username}/{message_id}"
    return f"roof://c/{channel.id}/{message_id}"


def _author_payload(row: ChannelPostMeta, db: Session) -> dict[str, Any]:
    if row.author_mode != "admin" or not row.author_user_id:
        channel = db.get(Chat, row.channel_id)
        return {
            "mode": "channel",
            "name": channel.name if channel else "Roof Channel",
            "user_id": None,
        }
    user = db.get(User, row.author_user_id)
    return {
        "mode": "admin",
        "name": (user.display_name or user.username) if user else "Admin",
        "username": user.username if user else None,
        "user_id": row.author_user_id,
    }


def _decorate_message(item: Any, db: Session) -> None:
    if not isinstance(item, dict):
        return
    message_id = int(item.get("id", 0) or 0)
    if message_id <= 0:
        return
    message = db.get(Message, message_id)
    if message is None:
        return
    chat = db.get(Chat, message.chat_id)
    if chat is None or chat.type != "channel":
        return
    row = _post_meta(message, db)
    assert row is not None
    item["views"] = row.views_count
    item["roof_post_author"] = _author_payload(row, db)
    item["roof_post_link"] = _post_link(chat, message.id, db)
    if row.author_mode == "channel":
        item.pop("from_id", None)
    elif row.author_user_id:
        item["from_id"] = {"_": "peerUser", "user_id": row.author_user_id}


def _decorate_result(result: Any, db: Session) -> Any:
    if not isinstance(result, dict):
        return result
    for item in result.get("messages") or []:
        _decorate_message(item, db)
    for update in result.get("updates") or []:
        if isinstance(update, dict):
            _decorate_message(update.get("message"), db)
    db.commit()
    return result


def _result_message_ids(result: Any) -> list[int]:
    ids: list[int] = []
    if not isinstance(result, dict):
        return ids
    for item in result.get("messages") or []:
        if isinstance(item, dict) and int(item.get("id", 0) or 0) > 0:
            ids.append(int(item["id"]))
    for update in result.get("updates") or []:
        if isinstance(update, dict):
            item = update.get("message")
            if isinstance(item, dict) and int(item.get("id", 0) or 0) > 0:
                ids.append(int(item["id"]))
    return list(dict.fromkeys(ids))


def _requested_author_mode(params: dict[str, Any], chat: Chat, db: Session) -> str:
    raw = str(params.get("roof_author_mode") or "").strip().lower()
    if raw in {"channel", "admin"}:
        return raw
    pref = _posting_pref(chat, db)
    return pref.author_mode if pref is not None else "channel"


def _remember_sent_authorship(
    result: Any,
    chat: Chat,
    mode: str,
    current_user: User,
    db: Session,
) -> None:
    for message_id in _result_message_ids(result):
        message = db.get(Message, message_id)
        if message is None or message.chat_id != chat.id:
            continue
        row = _post_meta(message, db)
        assert row is not None
        row.author_mode = mode
        row.author_user_id = current_user.id if mode == "admin" else None
    db.commit()


async def _mark_views(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    channel = _channel(int(params.get("channel_id", 0) or 0), current_user, db)
    raw_ids = params.get("post_ids") or []
    if not isinstance(raw_ids, list):
        raw_ids = [raw_ids]
    post_ids = [int(value) for value in raw_ids if int(value or 0) > 0]
    counts: dict[str, int] = {}
    changed: list[tuple[int, int]] = []

    for post_id in post_ids:
        message = db.get(Message, post_id)
        if message is None or message.chat_id != channel.id:
            continue
        row = _post_meta(message, db)
        assert row is not None
        existing = db.scalar(
            select(ChannelPostView.id).where(
                ChannelPostView.message_id == post_id,
                ChannelPostView.user_id == current_user.id,
            )
        )
        if existing is None:
            db.add(ChannelPostView(message_id=post_id, user_id=current_user.id))
            row.views_count += 1
            changed.append((post_id, row.views_count))
        counts[str(post_id)] = row.views_count
    db.commit()

    for post_id, count in changed:
        await manager.broadcast_chat(
            channel.id,
            {
                "roof_update": {
                    "_": "roofUpdateChannelPostViews",
                    "channel_id": channel.id,
                    "post_id": post_id,
                    "views": count,
                }
            },
        )
    return {"_": "roof.channelPostViews", "counts": counts}


def _get_post_info(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    channel = _channel(int(params.get("channel_id", 0) or 0), current_user, db)
    message = db.get(Message, int(params.get("post_id", 0) or 0))
    if message is None or message.chat_id != channel.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_CHANNEL_POST_NOT_FOUND")
    row = _post_meta(message, db)
    assert row is not None
    db.commit()
    return {
        "_": "roof.channelPostInfo",
        "post_id": message.id,
        "channel_id": channel.id,
        "views": row.views_count,
        "author": _author_payload(row, db),
        "link": _post_link(channel, message.id, db),
    }


async def _set_posting_mode(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    channel = _channel(int(params.get("channel_id", 0) or 0), current_user, db)
    if not _is_manager(channel, current_user.id, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_ADMIN_REQUIRED")
    mode = str(params.get("author_mode") or "").strip().lower()
    if mode not in {"channel", "admin"}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_CHANNEL_AUTHOR_MODE_INVALID")
    pref = _posting_pref(channel, db)
    assert pref is not None
    pref.author_mode = mode
    db.commit()
    await manager.broadcast_chat(
        channel.id,
        {
            "roof_update": {
                "_": "roofUpdateChannelPostingMode",
                "channel_id": channel.id,
                "author_mode": mode,
            }
        },
    )
    return {"_": "roof.channelPostingMode", "channel_id": channel.id, "author_mode": mode}


def _get_posting_mode(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    channel = _channel(int(params.get("channel_id", 0) or 0), current_user, db)
    pref = _posting_pref(channel, db)
    assert pref is not None
    db.commit()
    return {"_": "roof.channelPostingMode", "channel_id": channel.id, "author_mode": pref.author_mode}


@router.post("/invoke")
async def invoke_v21(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "roof.markChannelPostViewed":
        return await _mark_views(params, current_user, db)
    if method == "roof.getChannelPostInfo":
        return _get_post_info(params, current_user, db)
    if method == "roof.getChannelPostingMode":
        return _get_posting_mode(params, current_user, db)
    if method == "roof.setChannelPostingMode":
        return await _set_posting_mode(params, current_user, db)

    if method == "roof.getChatSettings":
        result = await v20.invoke_v20(payload, current_user, db)
        if isinstance(result, dict) and result.get("type") == "channel":
            chat = _channel(int(result.get("id", 0) or 0), current_user, db)
            pref = _posting_pref(chat, db)
            result["post_author_mode"] = pref.author_mode if pref else "channel"
            db.commit()
        return result

    if method in {"messages.sendMessage", "messages.sendMedia", "messages.sendMultiMedia"}:
        try:
            chat = legacy._resolve_peer(params.get("peer"), current_user, db)
        except HTTPException:
            chat = None
        if chat is not None and chat.type == "channel":
            mode = _requested_author_mode(params, chat, db)
            result = await v20.invoke_v20(payload, current_user, db)
            _remember_sent_authorship(result, chat, mode, current_user, db)
            return _decorate_result(result, db)

    result = await v20.invoke_v20(payload, current_user, db)
    if method in {
        "messages.getDialogs",
        "messages.getPinnedDialogs",
        "messages.getPeerDialogs",
        "messages.getHistory",
        "messages.getMessages",
        "channels.getMessages",
        "messages.search",
        "messages.searchGlobal",
        "messages.forwardMessages",
        "messages.editMessage",
    }:
        return _decorate_result(result, db)
    return result
