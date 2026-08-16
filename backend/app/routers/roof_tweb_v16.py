from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, Message, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v8 as v8
from app.routers import roof_tweb_v15 as v15
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _direct_chats(current_user: User, db: Session) -> list[Chat]:
    chat_ids = list(
        db.scalars(select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)).all()
    )
    if not chat_ids:
        return []
    return list(
        db.scalars(
            select(Chat)
            .where(Chat.id.in_(chat_ids), Chat.type == "direct")
            .options(selectinload(Chat.members).selectinload(ChatMember.user))
        ).unique().all()
    )


def _other_user(chat: Chat, current_user: User) -> User | None:
    return next(
        (member.user for member in chat.members if member.user_id != current_user.id),
        None,
    )


def _contacts(current_user: User, db: Session) -> dict[str, Any]:
    peers: dict[int, User] = {}
    for chat in _direct_chats(current_user, db):
        other = _other_user(chat, current_user)
        if other is not None:
            peers[other.id] = other

    users = sorted(peers.values(), key=lambda user: (user.username.lower(), user.id))
    return {
        "_": "contacts.contacts",
        "contacts": [
            {"_": "contact", "user_id": user.id, "pFlags": {}}
            for user in users
        ],
        "saved_count": len(users),
        "users": [legacy._user(user, current_user.id) for user in users],
    }


def _search_username(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    query = str(params.get("q") or "").strip().lstrip("@").lower()
    limit = max(1, min(int(params.get("limit", 50) or 50), 100))
    if not query:
        return {"_": "contacts.found", "my_results": [], "results": [], "chats": [], "users": []}

    users = list(
        db.scalars(
            select(User)
            .where(User.id != current_user.id)
            .where(User.username.ilike(f"%{query}%"))
            .order_by(User.username.asc())
            .limit(limit)
        ).all()
    )
    exact = [user for user in users if user.username.lower() == query]
    rest = [user for user in users if user.username.lower() != query]
    ordered = exact + rest
    return {
        "_": "contacts.found",
        "my_results": [],
        "results": [{"_": "peerUser", "user_id": user.id} for user in ordered],
        "chats": [],
        "users": [legacy._user(user, current_user.id) for user in ordered],
    }


def _resolve_username(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    username = str(params.get("username") or "").strip().lstrip("@").lower()
    if not username:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_USERNAME_REQUIRED")
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_USERNAME_NOT_FOUND")
    return {
        "_": "contacts.resolvedPeer",
        "peer": {"_": "peerUser", "user_id": user.id},
        "chats": [],
        "users": [legacy._user(user, current_user.id)],
    }


def _peer_profile_extras(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    raw_user_id = params.get("user_id")
    if raw_user_id is None and isinstance(params.get("peer"), dict):
        raw_user_id = params["peer"].get("user_id")
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_USER_ID_REQUIRED") from None

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_USER_NOT_FOUND")
    row = v15._meta(user.id, db)
    return {
        "_": "roof.peerProfileExtras",
        "user_id": user.id,
        "emoji_status": row.emoji_status if row else "",
        "premium": bool(user.is_premium),
        "premium_until": user.premium_until.isoformat() if user.premium_until else None,
        "verified": bool(user.is_verified),
        "is_self": user.id == current_user.id,
    }


def _direct_dialog(chat: Chat, current_user: User, db: Session) -> dict[str, Any]:
    dialog, last = v8._dialog_for_chat(chat, current_user, db)
    other = _other_user(chat, current_user)
    users = [legacy._user(current_user, current_user.id)]
    if other is not None:
        users.append(legacy._user(other, current_user.id))
    messages = [v8._message_item(last, chat, current_user, db)] if last is not None else []
    return {
        "_": "messages.peerDialogs",
        "dialogs": [dialog],
        "messages": messages,
        "chats": [],
        "users": users,
        "state": legacy._updates_state(),
    }


async def _open_direct_chat(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    username = str(params.get("username") or "").strip().lstrip("@").lower()
    raw_user_id = params.get("user_id")

    target: User | None = None
    if username:
        target = db.scalar(select(User).where(User.username == username))
    elif raw_user_id is not None:
        try:
            target = db.get(User, int(raw_user_id))
        except (TypeError, ValueError):
            target = None

    if target is None or target.id == current_user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_DIRECT_USER_NOT_FOUND")

    existed = legacy._direct_chat(current_user.id, target.id, db) is not None
    chat = legacy._get_or_create_direct_chat(current_user, target.id, db)
    result = _direct_dialog(chat, current_user, db)

    if not existed:
        update = {
            "_": "updatePeerSettings",
            "peer": {"_": "peerUser", "user_id": current_user.id},
            "settings": {"_": "peerSettings", "pFlags": {}},
        }
        await manager.send_to_user(target.id, {"roof_update": update})
    return result


async def _read_history(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = v8._resolve_peer(params.get("peer"), current_user, db)
    membership = legacy._membership(chat.id, current_user.id, db)
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a Roof chat member")

    max_id = int(params.get("max_id", 0) or 0)
    if max_id <= 0:
        max_id = int(
            db.scalar(
                select(Message.id)
                .where(Message.chat_id == chat.id)
                .order_by(Message.id.desc())
                .limit(1)
            )
            or 0
        )
    membership.last_read_message_id = max_id or None
    db.commit()

    peer = v8._peer(chat, current_user)
    own_update = {
        "_": "updateReadHistoryInbox",
        "peer": peer,
        "max_id": max_id,
        "still_unread_count": 0,
        "pts": max_id,
        "pts_count": 0,
    }
    await manager.send_to_user(current_user.id, {"roof_update": own_update})

    if chat.type == "direct":
        other = _other_user(chat, current_user)
        if other is not None:
            other_update = {
                "_": "updateReadHistoryOutbox",
                "peer": {"_": "peerUser", "user_id": current_user.id},
                "max_id": max_id,
                "pts": max_id,
                "pts_count": 0,
            }
            await manager.send_to_user(other.id, {"roof_update": other_update})

    return {"_": "messages.affectedMessages", "pts": max_id, "pts_count": 0}


@router.post("/invoke")
async def invoke_v16(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "contacts.getContacts":
        return _contacts(current_user, db)
    if method == "contacts.search":
        return _search_username(params, current_user, db)
    if method == "contacts.resolveUsername":
        return _resolve_username(params, current_user, db)
    if method == "roof.getPeerProfileExtras":
        return _peer_profile_extras(params, current_user, db)
    if method == "roof.openDirectChat":
        return await _open_direct_chat(params, current_user, db)
    if method == "messages.readHistory":
        return await _read_history(params, current_user, db)

    return await v15.invoke_v15(payload, current_user, db)
