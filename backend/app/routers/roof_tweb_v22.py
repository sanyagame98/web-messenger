from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v21 as v21

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _decorate_native_post(item: Any) -> None:
    if not isinstance(item, dict) or "roof_post_author" not in item:
        return
    flags = item.setdefault("pFlags", {})
    if isinstance(flags, dict):
        flags["post"] = True
    author = item.get("roof_post_author")
    if isinstance(author, dict) and author.get("mode") == "admin":
        item["post_author"] = str(author.get("name") or "Admin")
    else:
        item.pop("post_author", None)


def _decorate(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    for item in result.get("messages") or []:
        _decorate_native_post(item)
    for update in result.get("updates") or []:
        if isinstance(update, dict):
            _decorate_native_post(update.get("message"))
    return result


@router.post("/invoke")
async def invoke_v22(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    result = await v21.invoke_v21(payload, current_user, db)
    if payload.method in {
        "messages.getDialogs",
        "messages.getPinnedDialogs",
        "messages.getPeerDialogs",
        "messages.getHistory",
        "messages.getMessages",
        "channels.getMessages",
        "messages.search",
        "messages.searchGlobal",
        "messages.forwardMessages",
        "messages.sendMessage",
        "messages.sendMedia",
        "messages.sendMultiMedia",
        "messages.editMessage",
    }:
        return _decorate(result)
    return result
