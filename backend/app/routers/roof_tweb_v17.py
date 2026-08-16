from __future__ import annotations

import re
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.chat_meta_models import ChatMeta
from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v2 as v2
from app.routers import roof_tweb_v3 as v3
from app.routers import roof_tweb_v16 as v16
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])

CHAT_USERNAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{4,31}$")


def _load_chat(chat_id: int, current_user: User, db: Session) -> Chat:
    chat = db.scalar(
        select(Chat)
        .where(Chat.id == chat_id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_CHAT_NOT_FOUND")
    if not any(member.user_id == current_user.id for member in chat.members):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_CHAT_ACCESS_DENIED")
    return chat


def _chat_id(value: Any) -> int:
    if isinstance(value, dict):
        return int(value.get("channel_id", 0) or value.get("chat_id", 0) or 0)
    return int(value or 0)


def _can_manage(chat: Chat, user_id: int) -> bool:
    return any(
        member.user_id == user_id and member.role in {"owner", "admin"}
        for member in chat.members
    )


def _meta(chat: Chat, db: Session, create: bool = True) -> ChatMeta | None:
    row = db.get(ChatMeta, chat.id)
    if row is None and create:
        row = ChatMeta(
            chat_id=chat.id,
            invite_code=secrets.token_urlsafe(18),
            posting_mode="admins" if chat.type == "channel" else "all",
        )
        db.add(row)
        db.flush()
    return row


def _require_manager(chat: Chat, current_user: User) -> None:
    if not _can_manage(chat, current_user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_ADMIN_REQUIRED")


def _clean_username(value: Any) -> str:
    username = str(value or "").strip().lstrip("@").lower()
    if not CHAT_USERNAME_RE.fullmatch(username):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_CHAT_USERNAME_INVALID")
    return username


def _username_available(username: str, chat_id: int, db: Session) -> bool:
    user_taken = db.scalar(select(User.id).where(User.username == username)) is not None
    if user_taken:
        return False
    owner = db.scalar(select(ChatMeta).where(ChatMeta.username == username))
    return owner is None or owner.chat_id == chat_id


def _chat_entity(chat: Chat, db: Session) -> dict[str, Any]:
    meta = _meta(chat, db)
    assert meta is not None
    if chat.type == "channel":
        entity = v3._channel_entity(chat)
        entity["about"] = meta.about
        entity["username"] = meta.username
        entity["usernames"] = (
            [{"_": "username", "username": meta.username, "pFlags": {"active": True}}]
            if meta.username
            else []
        )
        entity.setdefault("pFlags", {})
        entity["pFlags"]["broadcast"] = True
        if meta.username:
            entity["pFlags"]["username"] = True
        return entity
    entity = legacy._chat_entity(chat)
    entity["about"] = meta.about
    return entity


def _updates(chat: Chat, current_user: User, db: Session) -> dict[str, Any]:
    return {
        "_": "updates",
        "updates": [],
        "users": [legacy._user(member.user, current_user.id) for member in chat.members],
        "chats": [_chat_entity(chat, db)],
        "date": legacy._unix(None),
        "seq": 0,
    }


def _decorate_result(result: Any, db: Session) -> Any:
    if not isinstance(result, dict):
        return result
    chats = result.get("chats")
    if not isinstance(chats, list):
        return result
    for item in chats:
        if not isinstance(item, dict):
            continue
        chat_id = int(item.get("id", 0) or 0)
        chat = db.get(Chat, chat_id)
        if chat is None or chat.type == "direct":
            continue
        item.clear()
        item.update(_chat_entity(chat, db))
    return result


def _create_group(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    result = v2._create_group(params, current_user, db)
    chat_id = int((result.get("chats") or [{}])[0].get("id", 0) or 0)
    chat = _load_chat(chat_id, current_user, db)
    _meta(chat, db)
    db.commit()
    return _updates(chat, current_user, db)


def _create_channel(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    title = str(params.get("title") or "").strip()
    if not title or len(title) > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_CHANNEL_TITLE_INVALID")
    about = str(params.get("about") or "").strip()
    if len(about) > 255:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_CHANNEL_ABOUT_TOO_LONG")

    chat = Chat(type="channel", name=title, created_by=current_user.id)
    db.add(chat)
    db.flush()
    db.add(ChatMember(chat_id=chat.id, user_id=current_user.id, role="owner"))
    db.add(
        ChatMeta(
            chat_id=chat.id,
            about=about,
            invite_code=secrets.token_urlsafe(18),
            posting_mode="admins",
        )
    )
    db.commit()
    chat = _load_chat(chat.id, current_user, db)
    return _updates(chat, current_user, db)


def _edit_about(params: dict[str, Any], current_user: User, db: Session) -> bool:
    chat = _load_chat(_chat_id(params.get("peer")), current_user, db)
    _require_manager(chat, current_user)
    about = str(params.get("about") or "").strip()
    if len(about) > 255:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_CHAT_ABOUT_TOO_LONG")
    meta = _meta(chat, db)
    assert meta is not None
    meta.about = about
    db.commit()
    return True


def _check_channel_username(params: dict[str, Any], current_user: User, db: Session) -> bool:
    chat = _load_chat(_chat_id(params.get("channel")), current_user, db)
    _require_manager(chat, current_user)
    username = _clean_username(params.get("username"))
    return _username_available(username, chat.id, db)


def _update_channel_username(params: dict[str, Any], current_user: User, db: Session) -> bool:
    chat = _load_chat(_chat_id(params.get("channel")), current_user, db)
    _require_manager(chat, current_user)
    raw = str(params.get("username") or "").strip().lstrip("@").lower()
    meta = _meta(chat, db)
    assert meta is not None
    if not raw:
        meta.username = None
        meta.is_public = False
        db.commit()
        return True
    username = _clean_username(raw)
    if not _username_available(username, chat.id, db):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "USERNAME_OCCUPIED")
    meta.username = username
    meta.is_public = True
    db.commit()
    return True


def _export_invite(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = _load_chat(_chat_id(params.get("peer")), current_user, db)
    _require_manager(chat, current_user)
    meta = _meta(chat, db)
    assert meta is not None
    db.commit()
    return {
        "_": "chatInviteExported",
        "link": f"roof://join/{meta.invite_code}",
        "admin_id": current_user.id,
        "date": legacy._unix(chat.created_at),
        "pFlags": {"permanent": True},
    }


def _get_exported_invites(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = _load_chat(_chat_id(params.get("peer")), current_user, db)
    _require_manager(chat, current_user)
    invite = _export_invite(params, current_user, db)
    return {"_": "messages.exportedChatInvites", "count": 1, "invites": [invite], "users": []}


def _full_channel(chat: Chat, current_user: User, db: Session) -> dict[str, Any]:
    meta = _meta(chat, db)
    assert meta is not None
    full = v3._channel_full(chat, current_user)
    full["chats"] = [_chat_entity(chat, db)]
    full_chat = full["full_chat"]
    full_chat["about"] = meta.about
    full_chat["exported_invite"] = {
        "_": "chatInviteExported",
        "link": f"roof://join/{meta.invite_code}",
        "admin_id": current_user.id,
        "date": legacy._unix(chat.created_at),
        "pFlags": {"permanent": True},
    }
    return full


def _full_group(chat: Chat, current_user: User, db: Session) -> dict[str, Any]:
    result = v2._full_chat(chat, current_user)
    meta = _meta(chat, db)
    assert meta is not None
    result["full_chat"]["about"] = meta.about
    result["full_chat"]["exported_invite"] = {
        "_": "chatInviteExported",
        "link": f"roof://join/{meta.invite_code}",
        "admin_id": current_user.id,
        "date": legacy._unix(chat.created_at),
        "pFlags": {"permanent": True},
    }
    result["chats"] = [_chat_entity(chat, db)]
    return result


async def _broadcast_chat_identity(chat: Chat, db: Session) -> None:
    payload = {"_": "roofUpdateChatIdentity", "chat": _chat_entity(chat, db)}
    await manager.broadcast_chat(chat.id, {"roof_update": payload})


@router.post("/invoke")
async def invoke_v17(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "messages.createChat":
        return _create_group(params, current_user, db)
    if method == "channels.createChannel":
        return _create_channel(params, current_user, db)
    if method == "messages.editChatAbout":
        result = _edit_about(params, current_user, db)
        chat = _load_chat(_chat_id(params.get("peer")), current_user, db)
        await _broadcast_chat_identity(chat, db)
        return result
    if method == "channels.checkUsername":
        return _check_channel_username(params, current_user, db)
    if method == "channels.updateUsername":
        result = _update_channel_username(params, current_user, db)
        chat = _load_chat(_chat_id(params.get("channel")), current_user, db)
        await _broadcast_chat_identity(chat, db)
        return result
    if method == "messages.exportChatInvite":
        return _export_invite(params, current_user, db)
    if method == "messages.getExportedChatInvites":
        return _get_exported_invites(params, current_user, db)
    if method == "channels.getFullChannel":
        chat = _load_chat(_chat_id(params.get("channel")), current_user, db)
        return _full_channel(chat, current_user, db)
    if method == "messages.getFullChat":
        chat = _load_chat(_chat_id(params.get("chat_id")), current_user, db)
        return _full_group(chat, current_user, db)

    result = await v16.invoke_v16(payload, current_user, db)
    if method in {
        "messages.getDialogs",
        "messages.getPinnedDialogs",
        "messages.getPeerDialogs",
        "channels.getChannels",
    }:
        return _decorate_result(result, db)
    return result
