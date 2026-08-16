from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.chat_admin_models import ChatAdminRights, DEFAULT_ADMIN_RIGHTS
from app.chat_meta_models import ChatMeta
from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v3 as v3
from app.routers import roof_tweb_v11 as v11
from app.routers import roof_tweb_v17 as v17
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _load(chat_id: int, current_user: User, db: Session) -> Chat:
    return v17._load_chat(chat_id, current_user, db)


def _chat_id(value: Any) -> int:
    return v17._chat_id(value)


def _member(chat: Chat, user_id: int) -> ChatMember | None:
    return next((item for item in chat.members if item.user_id == user_id), None)


def _is_manager(chat: Chat, user_id: int) -> bool:
    member = _member(chat, user_id)
    return bool(member and member.role in {"owner", "admin"})


def _require_manager(chat: Chat, current_user: User) -> ChatMember:
    member = _member(chat, current_user.id)
    if member is None or member.role not in {"owner", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_ADMIN_REQUIRED")
    return member


def _require_owner(chat: Chat, current_user: User) -> ChatMember:
    member = _member(chat, current_user.id)
    if member is None or member.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_OWNER_REQUIRED")
    return member


def _meta(chat: Chat, db: Session) -> ChatMeta:
    meta = v17._meta(chat, db)
    assert meta is not None
    return meta


def _rights_row(chat_id: int, user_id: int, db: Session, create: bool = False) -> ChatAdminRights | None:
    row = db.scalar(
        select(ChatAdminRights).where(
            ChatAdminRights.chat_id == chat_id,
            ChatAdminRights.user_id == user_id,
        )
    )
    if row is None and create:
        row = ChatAdminRights(chat_id=chat_id, user_id=user_id)
        row.set_rights(DEFAULT_ADMIN_RIGHTS)
        db.add(row)
        db.flush()
    return row


def _rights_for(chat: Chat, member: ChatMember, db: Session) -> dict[str, bool]:
    if member.role == "owner":
        return {key: True for key in DEFAULT_ADMIN_RIGHTS}
    if member.role != "admin":
        return {key: False for key in DEFAULT_ADMIN_RIGHTS}
    row = _rights_row(chat.id, member.user_id, db)
    return row.rights() if row else DEFAULT_ADMIN_RIGHTS.copy()


def _serialize_settings(chat: Chat, current_user: User, db: Session) -> dict[str, Any]:
    meta = _meta(chat, db)
    actor = _member(chat, current_user.id)
    assert actor is not None
    members = []
    for member in chat.members:
        rights = _rights_for(chat, member, db)
        members.append(
            {
                "user": legacy._user(member.user, current_user.id),
                "role": member.role,
                "rights": rights,
                "rank": (_rights_row(chat.id, member.user_id, db).rank if _rights_row(chat.id, member.user_id, db) else ("Owner" if member.role == "owner" else "Admin" if member.role == "admin" else "")),
            }
        )
    return {
        "_": "roof.chatSettings",
        "id": chat.id,
        "type": chat.type,
        "title": chat.name,
        "avatar_url": chat.avatar_url,
        "about": meta.about,
        "username": meta.username,
        "is_public": meta.is_public,
        "invite_link": f"roof://join/{meta.invite_code}",
        "hide_members": meta.hide_members,
        "history_visible": meta.history_visible,
        "posting_mode": meta.posting_mode,
        "comments_enabled": meta.comments_enabled,
        "my_role": actor.role,
        "can_manage": actor.role in {"owner", "admin"},
        "is_owner": actor.role == "owner",
        "members": members if not meta.hide_members or actor.role in {"owner", "admin"} else [],
    }


async def _broadcast_settings(chat: Chat, db: Session) -> None:
    meta = _meta(chat, db)
    await manager.broadcast_chat(
        chat.id,
        {
            "roof_update": {
                "_": "roofUpdateChatSettings",
                "chat_id": chat.id,
                "chat": v17._chat_entity(chat, db),
                "settings": {
                    "about": meta.about,
                    "username": meta.username,
                    "is_public": meta.is_public,
                    "hide_members": meta.hide_members,
                    "history_visible": meta.history_visible,
                    "posting_mode": meta.posting_mode,
                    "comments_enabled": meta.comments_enabled,
                },
            }
        },
    )


def _bool(value: Any) -> bool:
    return bool(value)


async def _update_settings(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = _load(_chat_id(params.get("chat_id") or params.get("peer") or params.get("channel")), current_user, db)
    _require_manager(chat, current_user)
    meta = _meta(chat, db)

    if "title" in params:
        title = " ".join(str(params.get("title") or "").split()).strip()
        if not title or len(title) > 100:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_CHAT_TITLE_INVALID")
        chat.name = title
    if "about" in params:
        about = str(params.get("about") or "").strip()
        if len(about) > 255:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_CHAT_ABOUT_TOO_LONG")
        meta.about = about
    if "avatar_url" in params:
        avatar_url = str(params.get("avatar_url") or "").strip()
        if avatar_url and not avatar_url.startswith("/uploads/"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_CHAT_AVATAR_INVALID")
        chat.avatar_url = avatar_url or None
    if "hide_members" in params:
        meta.hide_members = _bool(params.get("hide_members"))
    if "history_visible" in params:
        meta.history_visible = _bool(params.get("history_visible"))
    if "comments_enabled" in params:
        if chat.type != "channel":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_COMMENTS_CHANNEL_ONLY")
        meta.comments_enabled = _bool(params.get("comments_enabled"))
    if "posting_mode" in params:
        mode = str(params.get("posting_mode") or "").strip().lower()
        if mode not in {"all", "admins"}:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_POSTING_MODE_INVALID")
        if chat.type == "channel":
            mode = "admins"
        meta.posting_mode = mode
    if "is_public" in params or "username" in params:
        raw_public = _bool(params.get("is_public", meta.is_public))
        raw_username = str(params.get("username", meta.username or "") or "").strip().lstrip("@").lower()
        if raw_public:
            username = v17._clean_username(raw_username)
            if not v17._username_available(username, chat.id, db):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "USERNAME_OCCUPIED")
            meta.username = username
            meta.is_public = True
        else:
            meta.username = None
            meta.is_public = False

    db.commit()
    chat = _load(chat.id, current_user, db)
    await _broadcast_settings(chat, db)
    return _serialize_settings(chat, current_user, db)


async def _reset_invite(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = _load(_chat_id(params.get("chat_id") or params.get("peer")), current_user, db)
    _require_manager(chat, current_user)
    meta = _meta(chat, db)
    meta.invite_code = secrets.token_urlsafe(18)
    db.commit()
    await _broadcast_settings(chat, db)
    return _serialize_settings(chat, current_user, db)


def _extract_admin_rights(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {key: False for key in DEFAULT_ADMIN_RIGHTS}
    flags = value.get("pFlags") if isinstance(value.get("pFlags"), dict) else value
    return {key: bool(flags.get(key, False)) for key in DEFAULT_ADMIN_RIGHTS}


async def _set_admin(
    chat: Chat,
    target_id: int,
    rights_value: Any,
    rank: str,
    current_user: User,
    db: Session,
) -> None:
    _require_owner(chat, current_user)
    target = _member(chat, target_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_MEMBER_NOT_FOUND")
    if target.role == "owner":
        return
    rights = _extract_admin_rights(rights_value)
    enabled = any(rights.values())
    target.role = "admin" if enabled else "member"
    if enabled:
        row = _rights_row(chat.id, target_id, db, create=True)
        assert row is not None
        row.set_rights(rights)
        row.rank = (rank or "Admin").strip()[:32] or "Admin"
    else:
        db.execute(
            delete(ChatAdminRights).where(
                ChatAdminRights.chat_id == chat.id,
                ChatAdminRights.user_id == target_id,
            )
        )
    db.commit()
    await _broadcast_settings(_load(chat.id, current_user, db), db)


def _can_send(chat: Chat, current_user: User, db: Session) -> bool:
    meta = _meta(chat, db)
    if chat.type == "channel":
        return _is_manager(chat, current_user.id)
    if meta.posting_mode == "admins":
        return _is_manager(chat, current_user.id)
    return True


async def _delete_chat(params: dict[str, Any], current_user: User, db: Session) -> bool:
    chat = _load(_chat_id(params.get("chat_id") or params.get("peer") or params.get("channel")), current_user, db)
    _require_owner(chat, current_user)
    chat_id = chat.id
    await manager.broadcast_chat(chat_id, {"roof_update": {"_": "roofUpdateChatDeleted", "chat_id": chat_id}})
    db.delete(chat)
    db.commit()
    return True


@router.post("/invoke")
async def invoke_v18(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "roof.getChatSettings":
        chat = _load(_chat_id(params.get("chat_id") or params.get("peer") or params.get("channel")), current_user, db)
        return _serialize_settings(chat, current_user, db)
    if method == "roof.updateChatSettings":
        return await _update_settings(params, current_user, db)
    if method == "roof.resetInviteLink":
        return await _reset_invite(params, current_user, db)
    if method == "roof.deleteChat":
        return await _delete_chat(params, current_user, db)

    if method == "channels.toggleParticipantsHidden":
        chat = _load(_chat_id(params.get("channel")), current_user, db)
        _require_manager(chat, current_user)
        meta = _meta(chat, db)
        meta.hide_members = bool(params.get("enabled", False))
        db.commit()
        await _broadcast_settings(chat, db)
        return v17._updates(chat, current_user, db)

    if method == "messages.editChatDefaultBannedRights":
        chat = _load(_chat_id(params.get("peer")), current_user, db)
        _require_manager(chat, current_user)
        rights = params.get("banned_rights") or {}
        flags = rights.get("pFlags") if isinstance(rights, dict) else {}
        if isinstance(flags, dict):
            _meta(chat, db).posting_mode = "admins" if flags.get("send_messages") else "all"
            db.commit()
            await _broadcast_settings(chat, db)
        return v17._updates(chat, current_user, db)

    if method == "channels.setDiscussionGroup":
        chat = _load(_chat_id(params.get("broadcast")), current_user, db)
        _require_manager(chat, current_user)
        if chat.type != "channel":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_COMMENTS_CHANNEL_ONLY")
        group_id = _chat_id(params.get("group"))
        _meta(chat, db).comments_enabled = group_id > 0
        db.commit()
        await _broadcast_settings(chat, db)
        return True

    if method == "channels.editAdmin":
        chat = _load(_chat_id(params.get("channel")), current_user, db)
        target_id = legacy._input_user_id(params.get("user_id"), current_user)
        await _set_admin(
            chat,
            target_id,
            params.get("admin_rights"),
            str(params.get("rank") or "Admin"),
            current_user,
            db,
        )
        return v17._updates(_load(chat.id, current_user, db), current_user, db)

    if method == "messages.editChatAdmin":
        chat = _load(int(params.get("chat_id", 0) or 0), current_user, db)
        target_id = legacy._input_user_id(params.get("user_id"), current_user)
        enabled = bool(params.get("is_admin", False))
        rights = {key: enabled for key in DEFAULT_ADMIN_RIGHTS}
        rights["add_admins"] = False
        await _set_admin(chat, target_id, {"pFlags": rights}, "Admin", current_user, db)
        return True

    if method == "channels.getParticipants":
        chat = _load(_chat_id(params.get("channel")), current_user, db)
        meta = _meta(chat, db)
        if meta.hide_members and not _is_manager(chat, current_user.id):
            own = _member(chat, current_user.id)
            if own is None:
                return {"_": "channels.channelParticipants", "count": 0, "participants": [], "chats": [], "users": []}
            return {
                "_": "channels.channelParticipants",
                "count": 1,
                "participants": [v11._channel_participant_entity(chat, own)],
                "chats": [],
                "users": [legacy._user(own.user, current_user.id)],
            }

    if method in {"messages.sendMessage", "messages.sendMedia", "messages.sendMultiMedia"}:
        try:
            chat = legacy._resolve_peer(params.get("peer"), current_user, db)
        except HTTPException:
            chat = None
        if chat is not None and not _can_send(chat, current_user, db):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_POSTING_ADMINS_ONLY")

    return await v17.invoke_v17(payload, current_user, db)
