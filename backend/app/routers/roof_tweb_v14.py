from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import ChatMember, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v13 as v13
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{4,32}$")


def _clean_username(value: Any) -> str:
    username = str(value or "").strip().lstrip("@").lower()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_USERNAME_INVALID")
    return username


def _serialized_user(current_user: User) -> dict[str, Any]:
    return legacy._user(current_user, current_user.id)


async def _broadcast_identity(current_user: User, db: Session) -> None:
    chat_ids = list(
        db.scalars(select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)).all()
    )
    if not chat_ids:
        return
    peer_ids = set(
        db.scalars(
            select(ChatMember.user_id)
            .where(ChatMember.chat_id.in_(chat_ids))
            .where(ChatMember.user_id != current_user.id)
        ).all()
    )
    update = {
        "_": "updateUserName",
        "user_id": current_user.id,
        "first_name": current_user.display_name or current_user.username,
        "last_name": "",
        "usernames": [
            {
                "_": "username",
                "username": current_user.username,
                "pFlags": {"active": True},
            }
        ],
    }
    for user_id in peer_ids:
        await manager.send_to_user(user_id, {"roof_update": update})


def _check_username(params: dict[str, Any], current_user: User, db: Session) -> bool:
    username = _clean_username(params.get("username"))
    owner = db.scalar(select(User).where(User.username == username))
    return owner is None or owner.id == current_user.id


async def _update_username(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any]:
    username = _clean_username(params.get("username"))
    owner = db.scalar(select(User).where(User.username == username))
    if owner is not None and owner.id != current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "USERNAME_OCCUPIED")
    current_user.username = username
    db.commit()
    db.refresh(current_user)
    await _broadcast_identity(current_user, db)
    return _serialized_user(current_user)


async def _update_profile(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any]:
    if "first_name" in params or "last_name" in params:
        first_name = str(params.get("first_name") or "").strip()
        last_name = str(params.get("last_name") or "").strip()
        display_name = " ".join(part for part in (first_name, last_name) if part).strip()
        if not display_name or len(display_name) > 64:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "FIRSTNAME_INVALID")
        current_user.display_name = display_name
    if "about" in params:
        current_user.bio = str(params.get("about") or "").strip()[:280]
    db.commit()
    db.refresh(current_user)
    await _broadcast_identity(current_user, db)
    return _serialized_user(current_user)


def _available_reactions() -> dict[str, Any]:
    # TWeb can still use Unicode reactions through Roof's messages.sendReaction.
    # No Telegram animation documents are returned because Roof is fully local.
    return {"_": "messages.availableReactions", "hash": 1, "reactions": []}


def _emoji_keywords(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "_": "emojiKeywordsDifference",
        "lang_code": str(params.get("lang_code") or "en"),
        "from_version": int(params.get("from_version", 0) or 0),
        "version": 1,
        "keywords": [],
    }


@router.post("/invoke")
async def invoke_v14(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "account.checkUsername":
        return _check_username(params, current_user, db)
    if method == "account.updateUsername":
        return await _update_username(params, current_user, db)
    if method == "account.updateProfile":
        return await _update_profile(params, current_user, db)
    if method == "account.updateStatus":
        return True

    # Native emoji/reaction UI must open even though Roof does not use Telegram
    # sticker/animation document infrastructure.
    if method == "messages.getEmojiKeywordsDifference":
        return _emoji_keywords(params)
    if method == "messages.getCustomEmojiDocuments":
        return []
    if method == "messages.getAvailableReactions":
        return _available_reactions()
    if method in {"messages.getEmojiStickers", "messages.getFeaturedEmojiStickers"}:
        return {"_": "messages.allStickers", "hash": 1, "sets": []}
    if method in {"messages.getRecentReactions", "messages.getTopReactions"}:
        return {"_": "messages.reactions", "hash": 1, "reactions": []}
    if method == "messages.getSavedReactionTags":
        return {"_": "messages.savedReactionTags", "tags": [], "hash": 1}

    # Harmless settings calls used by TWeb. Roof keeps these local/default for now
    # instead of making the UI fail with ROOF_METHOD_NOT_IMPLEMENTED.
    if method == "account.getAuthorizations":
        return {"_": "account.authorizations", "authorization_ttl_days": 30, "authorizations": []}
    if method == "account.getWebAuthorizations":
        return {"_": "account.webAuthorizations", "authorizations": [], "users": []}
    if method == "account.getAccountTTL":
        return {"_": "accountDaysTTL", "days": 365}
    if method == "account.getPrivacy":
        return {"_": "account.privacyRules", "rules": [{"_": "privacyValueAllowAll"}], "chats": [], "users": []}
    if method == "account.setPrivacy":
        return {"_": "account.privacyRules", "rules": params.get("rules") or [{"_": "privacyValueAllowAll"}], "chats": [], "users": []}
    if method in {"account.getDefaultProfilePhotoEmojis", "account.getDefaultGroupPhotoEmojis"}:
        return {"_": "emojiListNotModified"}

    return await v13.invoke_v13(payload, current_user, db)
