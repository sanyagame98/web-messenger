from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.profile_meta_models import UserProfileMeta
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v14 as v14
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


ROOF_PREMIUM_EMOJI = ["😂", "❤️", "🔥", "👍", "💯", "😁", "😎", "👑", "⚡", "💜", "🖤", "🚀"]


def _meta(user_id: int, db: Session) -> UserProfileMeta | None:
    return db.scalar(select(UserProfileMeta).where(UserProfileMeta.user_id == user_id))


def _meta_or_create(user_id: int, db: Session) -> UserProfileMeta:
    row = _meta(user_id, db)
    if row is None:
        row = UserProfileMeta(user_id=user_id, emoji_status="")
        db.add(row)
        db.flush()
    return row


def _profile(current_user: User, db: Session) -> dict[str, Any]:
    row = _meta(current_user.id, db)
    return {
        "_": "roof.ownProfile",
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.display_name or current_user.username,
        "username": current_user.username,
        "bio": current_user.bio or "",
        "avatar_url": current_user.avatar_url,
        "emoji_status": row.emoji_status if row else "",
        "premium": current_user.is_premium,
        "premium_until": (
            current_user.premium_until.isoformat() if current_user.premium_until else None
        ),
        "stars": current_user.stars,
        "verified": current_user.is_verified,
    }


def _extras(current_user: User, db: Session) -> dict[str, Any]:
    row = _meta(current_user.id, db)
    return {
        "_": "roof.profileExtras",
        "emoji_status": row.emoji_status if row else "",
        "premium": current_user.is_premium,
        "premium_until": current_user.premium_until.isoformat() if current_user.premium_until else None,
        "stars": current_user.stars,
        "available_statuses": ROOF_PREMIUM_EMOJI,
        "brand": "Roof",
    }


async def _update_emoji_status(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any]:
    emoji = str(params.get("emoji") or "").strip()
    if emoji and emoji not in ROOF_PREMIUM_EMOJI:
        emoji = ""
    row = _meta_or_create(current_user.id, db)
    row.emoji_status = emoji
    db.commit()

    update = {
        "_": "roofUpdateEmojiStatus",
        "user_id": current_user.id,
        "emoji": emoji,
    }
    await manager.send_to_user(current_user.id, {"roof_update": update})
    return _profile(current_user, db)


async def _update_own_profile(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any]:
    if "name" in params:
        name = " ".join(str(params.get("name") or "").split()).strip()
        if not name or len(name) > 64:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_NAME_INVALID")
        current_user.display_name = name

    if "username" in params:
        username = v14._clean_username(params.get("username"))
        owner = db.scalar(select(User).where(User.username == username))
        if owner is not None and owner.id != current_user.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "USERNAME_OCCUPIED")
        current_user.username = username

    if "bio" in params:
        bio = str(params.get("bio") or "").strip()
        if len(bio) > 280:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_BIO_TOO_LONG")
        current_user.bio = bio

    if "avatar_url" in params:
        avatar_url = str(params.get("avatar_url") or "").strip()
        if avatar_url and not avatar_url.startswith("/uploads/"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_AVATAR_INVALID")
        current_user.avatar_url = avatar_url or None

    db.commit()
    db.refresh(current_user)
    await v14._broadcast_identity(current_user, db)
    await manager.send_to_user(
        current_user.id,
        {"roof_update": {"_": "roofUpdateOwnProfile", "profile": _profile(current_user, db)}},
    )
    return _profile(current_user, db)


@router.post("/invoke")
async def invoke_v15(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if payload.method == "roof.getProfileExtras":
        return _extras(current_user, db)
    if payload.method == "roof.getOwnProfile":
        return _profile(current_user, db)
    if payload.method == "roof.updateOwnProfile":
        return await _update_own_profile(payload.params, current_user, db)
    if payload.method == "roof.updateEmojiStatus":
        return await _update_emoji_status(payload.params, current_user, db)

    return await v14.invoke_v14(payload, current_user, db)
