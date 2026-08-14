from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v3 as v3
from app.routers import roof_tweb_v8 as v8
from app.routers import roof_tweb_v10 as v10
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


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


def _is_manager(chat: Chat, user_id: int) -> bool:
    member = _member(chat, user_id)
    return bool(member and member.role in {"owner", "admin"})


def _require_manager(chat: Chat, user_id: int) -> ChatMember:
    member = _member(chat, user_id)
    if member is None or member.role not in {"owner", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Roof admin rights required")
    return member


def _require_owner(chat: Chat, user_id: int) -> ChatMember:
    member = _member(chat, user_id)
    if member is None or member.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Roof owner rights required")
    return member


def _chat_entity(chat: Chat) -> dict[str, Any]:
    if chat.type == "channel":
        return v3._channel_entity(chat)
    return legacy._chat_entity(chat)


def _updates(chat: Chat, current_user: User) -> dict[str, Any]:
    return {
        "_": "updates",
        "updates": [],
        "users": [legacy._user(item.user, current_user.id) for item in chat.members],
        "chats": [_chat_entity(chat)],
        "date": legacy._unix(None),
        "seq": 0,
    }


def _group_participant(chat: Chat, member: ChatMember) -> dict[str, Any]:
    if member.role == "owner":
        return {
            "_": "chatParticipantCreator",
            "user_id": member.user_id,
        }
    if member.role == "admin":
        return {
            "_": "chatParticipantAdmin",
            "user_id": member.user_id,
            "inviter_id": chat.created_by or member.user_id,
            "date": legacy._unix(member.joined_at),
        }
    return {
        "_": "chatParticipant",
        "user_id": member.user_id,
        "inviter_id": chat.created_by or member.user_id,
        "date": legacy._unix(member.joined_at),
    }


def _channel_participant(chat: Chat, member: ChatMember) -> dict[str, Any]:
    if member.role == "owner":
        return {
            "_": "channelParticipantCreator",
            "user_id": member.user_id,
            "admin_rights": {
                "_": "chatAdminRights",
                "pFlags": {
                    "change_info": True,
                    "post_messages": True,
                    "edit_messages": True,
                    "delete_messages": True,
                    "ban_users": True,
                    "invite_users": True,
                    "pin_messages": True,
                    "add_admins": True,
                    "manage_call": True,
                },
            },
            "pFlags": {},
        }
    if member.role == "admin":
        return {
            "_": "channelParticipantAdmin",
            "user_id": member.user_id,
            "inviter_id": chat.created_by or member.user_id,
            "promoted_by": chat.created_by or member.user_id,
            "date": legacy._unix(member.joined_at),
            "admin_rights": {
                "_": "chatAdminRights",
                "pFlags": {
                    "change_info": True,
                    "post_messages": True,
                    "edit_messages": True,
                    "delete_messages": True,
                    "ban_users": True,
                    "invite_users": True,
                    "pin_messages": True,
                    "manage_call": True,
                },
            },
            "rank": "Admin",
            "pFlags": {"can_edit": True},
        }
    return {
        "_": "channelParticipant",
        "user_id": member.user_id,
        "date": legacy._unix(member.joined_at),
        "pFlags": {},
    }


def _resolve_user_id(value: Any, current_user: User) -> int:
    return legacy._input_user_id(value, current_user)


def _add_member(
    chat: Chat,
    user_id: int,
    current_user: User,
    db: Session,
) -> None:
    _require_manager(chat, current_user.id)
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof user not found")
    if _member(chat, user_id) is None:
        db.add(ChatMember(chat_id=chat.id, user_id=user_id, role="member"))
        db.commit()


def _remove_member(
    chat: Chat,
    user_id: int,
    current_user: User,
    db: Session,
) -> None:
    target = _member(chat, user_id)
    if target is None:
        return
    actor = _member(chat, current_user.id)
    if actor is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a Roof chat member")
    if user_id != current_user.id:
        if actor.role not in {"owner", "admin"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Roof admin rights required")
        if target.role == "owner":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Roof owner cannot be removed")
        if target.role == "admin" and actor.role != "owner":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owner can remove an admin")
    elif target.role == "owner":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Transfer Roof ownership before leaving",
        )
    db.delete(target)
    db.commit()


def _edit_group_admin(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> bool:
    chat = _load_chat(int(params.get("chat_id", 0) or 0), current_user, db)
    if chat.type != "group":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a Roof group")
    _require_owner(chat, current_user.id)
    user_id = _resolve_user_id(params.get("user_id"), current_user)
    target = _member(chat, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof member not found")
    if target.role == "owner":
        return True
    target.role = "admin" if bool(params.get("is_admin", False)) else "member"
    db.commit()
    return True


async def _edit_channel_admin(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = _load_chat(v3._channel_id(params.get("channel")), current_user, db)
    if chat.type != "channel":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a Roof channel")
    _require_owner(chat, current_user.id)
    user_id = _resolve_user_id(params.get("user_id"), current_user)
    target = _member(chat, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof subscriber not found")
    if target.role != "owner":
        rights = params.get("admin_rights") or {}
        flags = rights.get("pFlags") if isinstance(rights, dict) else {}
        enabled = bool(flags) if isinstance(flags, dict) else bool(rights)
        target.role = "admin" if enabled else "member"
        db.commit()
    fresh = _load_chat(chat.id, current_user, db)
    await manager.broadcast_chat(
        fresh.id,
        {
            "roof_update": {
                "_": "updateChannelParticipant",
                "channel_id": fresh.id,
                "date": legacy._unix(None),
                "user_id": user_id,
                "prev_participant": _channel_participant(fresh, target),
                "new_participant": _channel_participant(fresh, _member(fresh, user_id)),
                "inviter_id": current_user.id,
            }
        },
    )
    return _updates(fresh, current_user)


async def _edit_channel_banned(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = _load_chat(v3._channel_id(params.get("channel")), current_user, db)
    _require_manager(chat, current_user.id)
    user_id = _resolve_user_id(params.get("participant"), current_user)
    rights = params.get("banned_rights") or {}
    flags = rights.get("pFlags") if isinstance(rights, dict) else {}
    kicked = bool(isinstance(flags, dict) and flags.get("view_messages"))
    if kicked:
        _remove_member(chat, user_id, current_user, db)
    fresh = _load_chat(chat.id, current_user, db)
    return _updates(fresh, current_user)


def _channel_participants(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = _load_chat(v3._channel_id(params.get("channel")), current_user, db)
    query = str(params.get("q", "")).strip().lower()
    offset = max(0, int(params.get("offset", 0) or 0))
    limit = max(1, min(int(params.get("limit", 50) or 50), 200))
    members = list(chat.members)
    filter_value = params.get("filter") or {}
    filter_kind = str(filter_value.get("_", "")) if isinstance(filter_value, dict) else ""
    if filter_kind == "channelParticipantsAdmins":
        members = [item for item in members if item.role in {"owner", "admin"}]
    elif filter_kind == "channelParticipantsSearch" and query:
        members = [
            item
            for item in members
            if query in item.user.username.lower()
            or query in (item.user.display_name or "").lower()
        ]
    total = len(members)
    members = members[offset : offset + limit]
    return {
        "_": "channels.channelParticipants",
        "count": total,
        "participants": [_channel_participant(chat, item) for item in members],
        "chats": [],
        "users": [legacy._user(item.user, current_user.id) for item in members],
    }


def _channel_participant(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = _load_chat(v3._channel_id(params.get("channel")), current_user, db)
    user_id = _resolve_user_id(params.get("participant"), current_user)
    member = _member(chat, user_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof subscriber not found")
    return {
        "_": "channels.channelParticipant",
        "participant": _channel_participant(chat, member),
        "chats": [],
        "users": [legacy._user(member.user, current_user.id)],
    }


def _full_group(chat: Chat, current_user: User) -> dict[str, Any]:
    return {
        "_": "messages.chatFull",
        "full_chat": {
            "_": "chatFull",
            "id": chat.id,
            "about": "",
            "participants": {
                "_": "chatParticipants",
                "chat_id": chat.id,
                "participants": [_group_participant(chat, item) for item in chat.members],
                "version": 1,
            },
            "notify_settings": {"_": "peerNotifySettings"},
            "pFlags": {},
        },
        "chats": [legacy._chat_entity(chat)],
        "users": [legacy._user(item.user, current_user.id) for item in chat.members],
    }


@router.post("/invoke")
async def invoke_v11(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "messages.getFullChat":
        chat = _load_chat(int(params.get("chat_id", 0) or 0), current_user, db)
        return _full_group(chat, current_user)
    if method == "messages.addChatUser":
        chat = _load_chat(int(params.get("chat_id", 0) or 0), current_user, db)
        _add_member(chat, _resolve_user_id(params.get("user_id"), current_user), current_user, db)
        return _updates(_load_chat(chat.id, current_user, db), current_user)
    if method == "messages.deleteChatUser":
        chat = _load_chat(int(params.get("chat_id", 0) or 0), current_user, db)
        target_id = _resolve_user_id(params.get("user_id"), current_user)
        _remove_member(chat, target_id, current_user, db)
        if target_id == current_user.id:
            return {"_": "updates", "updates": [], "users": [], "chats": [], "date": legacy._unix(None), "seq": 0}
        return _updates(_load_chat(chat.id, current_user, db), current_user)
    if method == "messages.editChatAdmin":
        return _edit_group_admin(params, current_user, db)
    if method == "messages.editChatTitle":
        chat = _load_chat(int(params.get("chat_id", 0) or 0), current_user, db)
        _require_manager(chat, current_user.id)
        title = str(params.get("title", "")).strip()[:120]
        if not title:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof group title is required")
        chat.name = title
        db.commit()
        return _updates(_load_chat(chat.id, current_user, db), current_user)

    if method == "channels.getParticipants":
        return _channel_participants(params, current_user, db)
    if method == "channels.getParticipant":
        return _channel_participant(params, current_user, db)
    if method == "channels.editAdmin":
        return await _edit_channel_admin(params, current_user, db)
    if method == "channels.editBanned":
        return await _edit_channel_banned(params, current_user, db)

    return await v10.invoke_v10(payload, current_user, db)
