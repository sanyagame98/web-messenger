from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v26 as v26

router = APIRouter(prefix="/roof", tags=["roof-tweb"])

ROOF_PREMIUM_ORDER = [
    "animated_emoji",
    "emoji_status",
    "profile_badge",
    "infinite_reactions",
    "animated_userpics",
    "advanced_chat_management",
    "no_ads",
    "peer_colors",
    "wallpapers",
]


def _premium_promo(current_user: User) -> dict[str, Any]:
    return {
        "_": "help.premiumPromo",
        # Roof Premium is currently granted/managed inside Roof, so no fake
        # prices or Telegram bot URL are exposed in the native TWeb popup.
        "period_options": [],
        "video_sections": [],
        "videos": [],
        "status_text": "Roof Premium" if current_user.is_premium else "",
        "status_entities": [],
        "roof_premium": bool(current_user.is_premium),
        "roof_stars": int(current_user.stars),
    }


def _premium_app_config() -> dict[str, Any]:
    return {
        "_": "roof.premiumAppConfig",
        "premium_promo_order": ROOF_PREMIUM_ORDER,
    }


@router.post("/invoke")
async def invoke_v27(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method

    if method == "roof.getPremiumPromo":
        return _premium_promo(current_user)

    if method == "roof.getPremiumAppConfig":
        return _premium_app_config()

    if method == "roof.beginPremiumPurchase":
        # Purchase transport is deliberately Roof-local. Until a Roof billing
        # URL is configured there is no t.me/Telegram fallback.
        return {
            "_": "roof.premiumPurchase",
            "available": False,
            "url": "",
            "premium": bool(current_user.is_premium),
        }

    return await v26.invoke_v26(payload, current_user, db)
