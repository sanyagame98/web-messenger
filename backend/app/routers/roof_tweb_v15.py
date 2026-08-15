from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
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
    return _extras(current_user, db)


@router.post("/invoke")
async def invoke_v15(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if payload.method == "roof.getProfileExtras":
        return _extras(current_user, db)
    if payload.method == "roof.updateEmojiStatus":
        return await _update_emoji_status(payload.params, current_user, db)

    return await v14.invoke_v14(payload, current_user, db)
