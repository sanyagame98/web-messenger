from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, User
from app.routers import roof_tweb as legacy
from app.schemas import USERNAME_RE

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _now() -> int:
    return int(datetime.now(UTC).timestamp())


def _app_config() -> dict[str, Any]:
    return {
        "hash": 1,
        "ignore_restriction_reasons": [],
        "dialogs_pinned_limit_default": 5,
        "dialogs_pinned_limit_premium": 10,
        "dialogs_folder_pinned_limit_default": 100,
        "dialogs_folder_pinned_limit_premium": 200,
        "dialog_filters_limit_default": 10,
        "dialog_filters_limit_premium": 20,
        "stickers_faved_limit_default": 5,
        "stickers_faved_limit_premium": 10,
        "reactions_user_max_default": 1,
        "reactions_user_max_premium": 1,
        "about_length_limit_default": 280,
        "about_length_limit_premium": 280,
        "topics_pinned_limit": 5,
        "caption_length_limit_default": 1024,
        "caption_length_limit_premium": 2048,
        "chatlist_invites_limit_default": 10,
        "chatlist_invites_limit_premium": 20,
        "chatlists_joined_limit_default": 10,
        "chatlists_joined_limit_premium": 20,
        "channels_limit_default": 500,
        "channels_limit_premium": 1000,
        "channels_public_limit_default": 10,
        "channels_public_limit_premium": 20,
        "saved_gifs_limit_default": 200,
        "saved_gifs_limit_premium": 400,
        "dialog_filters_chats_limit_default": 100,
        "dialog_filters_chats_limit_premium": 200,
        "upload_max_fileparts_default": 4000,
        "upload_max_fileparts_premium": 8000,
        "recommended_channels_limit_default": 10,
        "recommended_channels_limit_premium": 20,
        "saved_dialogs_pinned_limit_default": 5,
        "saved_dialogs_pinned_limit_premium": 10,
    }


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


def _chat_users(chat: Chat, current_user: User) -> list[dict[str, Any]]:
    return [legacy._user(member.user, current_user.id) for member in chat.members]


def _chat_updates(chat: Chat, current_user: User) -> dict[str, Any]:
    return {
        "_": "updates",
        "updates": [],
        "users": _chat_users(chat, current_user),
        "chats": [legacy._chat_entity(chat)],
        "date": _now(),
        "seq": 0,
    }


def _full_chat(chat: Chat, current_user: User) -> dict[str, Any]:
    participants = []
    for member in chat.members:
        participants.append(
            {
                "_": "chatParticipantCreator" if member.role == "owner" else "chatParticipant",
                "user_id": member.user_id,
                "inviter_id": chat.created_by or current_user.id,
                "date": legacy._unix(member.joined_at),
            }
        )
    return {
        "_": "messages.chatFull",
        "full_chat": {
            "_": "chatFull",
            "id": chat.id,
            "about": "",
            "participants": {
                "_": "chatParticipants",
                "chat_id": chat.id,
                "participants": participants,
                "version": 1,
            },
            "notify_settings": {"_": "peerNotifySettings"},
            "pFlags": {},
        },
        "chats": [legacy._chat_entity(chat)],
        "users": _chat_users(chat, current_user),
    }


def _resolve_user_ids(values: Any, current_user: User) -> list[int]:
    if not isinstance(values, list):
        values = [values]
    result: list[int] = []
    for value in values:
        user_id = legacy._input_user_id(value, current_user)
        if user_id > 0 and user_id not in result:
            result.append(user_id)
    return result


def _create_group(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    title = str(params.get("title", "")).strip()[:120]
    if not title:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof group title is required")
    member_ids = _resolve_user_ids(params.get("users") or [], current_user)
    if current_user.id not in member_ids:
        member_ids.insert(0, current_user.id)
    users = list(db.scalars(select(User).where(User.id.in_(member_ids))).all())
    if len(users) != len(member_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more Roof users were not found")

    chat = Chat(type="group", name=title, created_by=current_user.id)
    db.add(chat)
    db.flush()
    for user in users:
        db.add(
            ChatMember(
                chat_id=chat.id,
                user_id=user.id,
                role="owner" if user.id == current_user.id else "member",
            )
        )
    db.commit()
    return _chat_updates(_load_chat(chat.id, current_user, db), current_user)


def _update_profile(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    if "first_name" in params or "last_name" in params:
        first = str(params.get("first_name", "")).strip()
        last = str(params.get("last_name", "")).strip()
        name = " ".join(part for part in (first, last) if part).strip()
        if not name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof display name cannot be empty")
        current_user.display_name = name[:64]
    if "about" in params:
        current_user.bio = str(params.get("about", "")).strip()[:280]
    db.commit()
    db.refresh(current_user)
    return legacy._user(current_user, current_user.id)


def _update_username(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    username = str(params.get("username", "")).strip().lstrip("@").lower()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Username must be 4-32 characters, only letters, digits and underscores",
        )
    taken = db.scalar(select(User.id).where(User.username == username, User.id != current_user.id))
    if taken is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    current_user.username = username
    db.commit()
    db.refresh(current_user)
    return legacy._user(current_user, current_user.id)


def _check_username(params: dict[str, Any], current_user: User, db: Session) -> bool:
    username = str(params.get("username", "")).strip().lstrip("@").lower()
    if not USERNAME_RE.fullmatch(username):
        return False
    taken = db.scalar(select(User.id).where(User.username == username, User.id != current_user.id))
    return taken is None


def _add_chat_user(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = _load_chat(int(params.get("chat_id", 0)), current_user, db)
    user_id = legacy._input_user_id(params.get("user_id"), current_user)
    if db.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof user not found")
    exists = db.scalar(
        select(ChatMember.id).where(ChatMember.chat_id == chat.id, ChatMember.user_id == user_id)
    )
    if exists is None:
        db.add(ChatMember(chat_id=chat.id, user_id=user_id, role="member"))
        db.commit()
    return _chat_updates(_load_chat(chat.id, current_user, db), current_user)


def _delete_chat_user(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = _load_chat(int(params.get("chat_id", 0)), current_user, db)
    user_id = legacy._input_user_id(params.get("user_id"), current_user)
    member = db.scalar(
        select(ChatMember).where(ChatMember.chat_id == chat.id, ChatMember.user_id == user_id)
    )
    if member is not None:
        db.delete(member)
        db.commit()
    if user_id == current_user.id:
        return {
            "_": "updates",
            "updates": [],
            "users": [legacy._user(current_user, current_user.id)],
            "chats": [],
            "date": _now(),
            "seq": 0,
        }
    return _chat_updates(_load_chat(chat.id, current_user, db), current_user)


def _edit_chat_title(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = _load_chat(int(params.get("chat_id", 0)), current_user, db)
    title = str(params.get("title", "")).strip()[:120]
    if not title:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof group title is required")
    chat.name = title
    db.commit()
    return _chat_updates(_load_chat(chat.id, current_user, db), current_user)


def _handle(method: str, params: dict[str, Any], current_user: User, db: Session) -> Any:
    if method == "help.getConfig":
        return {
            "_": "config",
            "date": _now(),
            "expires": _now() + int(timedelta(days=1).total_seconds()),
            "test_mode": False,
            "this_dc": 1,
            "dc_options": [],
            "dc_txt_domain_name": "roof.local",
            "chat_size_max": 200,
            "megagroup_size_max": 1000000,
            "forwarded_count_max": 100,
            "online_update_period_ms": 120000,
            "offline_blur_timeout_ms": 5000,
            "offline_idle_timeout_ms": 30000,
            "online_cloud_timeout_ms": 300000,
            "notify_cloud_delay_ms": 30000,
            "notify_default_delay_ms": 1500,
            "push_chat_period_ms": 60000,
            "push_chat_limit": 2,
            "edit_time_limit": 172800,
            "revoke_time_limit": 172800,
            "revoke_pm_time_limit": 172800,
            "rating_e_decay": 2419200,
            "stickers_recent_limit": 30,
            "channels_read_media_period": 604800,
            "tmp_sessions": 0,
            "call_receive_timeout_ms": 20000,
            "call_ring_timeout_ms": 90000,
            "call_connect_timeout_ms": 30000,
            "call_packet_timeout_ms": 10000,
            "me_url_prefix": "roof://",
            "caption_length_max": 2048,
            "message_length_max": 4096,
            "webfile_dc_id": 1,
            "pFlags": {},
        }

    if method == "help.getAppConfig":
        return {"_": "help.appConfig", "hash": 1, "config": _app_config()}
    if method in {"help.getPeerColors", "help.getPeerProfileColors"}:
        return {"_": "help.peerColors", "hash": 1, "colors": []}
    if method == "help.getNearestDc":
        return {"_": "nearestDc", "country": "", "this_dc": 1, "nearest_dc": 1}
    if method == "help.getTermsOfServiceUpdate":
        return {"_": "help.termsOfServiceUpdateEmpty", "expires": _now() + 86400}
    if method == "help.getAppUpdate":
        return {"_": "help.noAppUpdate"}

    if method == "account.updateProfile":
        return _update_profile(params, current_user, db)
    if method == "account.checkUsername":
        return _check_username(params, current_user, db)
    if method == "account.updateUsername":
        return _update_username(params, current_user, db)
    if method == "account.getGlobalPrivacySettings":
        return {"_": "globalPrivacySettings", "pFlags": {}}
    if method == "account.getContentSettings":
        return {"_": "account.contentSettings", "pFlags": {}}
    if method == "account.getPrivacy":
        return {
            "_": "account.privacyRules",
            "rules": [{"_": "privacyValueAllowAll"}],
            "chats": [],
            "users": [],
        }

    if method == "messages.createChat":
        return _create_group(params, current_user, db)
    if method == "messages.getFullChat":
        return _full_chat(_load_chat(int(params.get("chat_id", 0)), current_user, db), current_user)
    if method == "messages.addChatUser":
        return _add_chat_user(params, current_user, db)
    if method == "messages.deleteChatUser":
        return _delete_chat_user(params, current_user, db)
    if method == "messages.editChatTitle":
        return _edit_chat_title(params, current_user, db)
    if method == "messages.getAllDrafts":
        return {"_": "updates", "updates": [], "users": [], "chats": [], "date": _now(), "seq": 0}
    if method == "messages.getSearchCounters":
        return []
    if method == "messages.getAvailableReactions":
        return {"_": "messages.availableReactions", "hash": 1, "reactions": []}
    if method in {
        "messages.getEmojiGroups",
        "messages.getEmojiStatusGroups",
        "messages.getEmojiProfilePhotoGroups",
    }:
        return {"_": "messages.emojiGroups", "hash": 1, "groups": []}

    if method == "contacts.getStatuses":
        return []
    if method == "contacts.getTopPeers":
        return {"_": "contacts.topPeers", "categories": [], "chats": [], "users": []}

    return None


@router.post("/invoke")
async def invoke_v2(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    result = _handle(payload.method, payload.params, current_user, db)
    if result is not None:
        return result
    return await legacy.invoke(payload, current_user, db)
