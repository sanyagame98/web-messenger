from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.chat_admin_models import DEFAULT_ADMIN_RIGHTS
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v18 as v18
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


async def _set_member_admin(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any]:
    chat = v18._load(v18._chat_id(params.get("chat_id")), current_user, db)
    target_id = int(params.get("user_id", 0) or 0)
    enabled = bool(params.get("enabled", True))
    raw_rights = params.get("rights") if isinstance(params.get("rights"), dict) else {}
    rights = {
        key: bool(raw_rights.get(key, enabled and DEFAULT_ADMIN_RIGHTS.get(key, False)))
        for key in DEFAULT_ADMIN_RIGHTS
    }
    if not enabled:
        rights = {key: False for key in DEFAULT_ADMIN_RIGHTS}
    await v18._set_admin(
        chat,
        target_id,
        {"pFlags": rights},
        str(params.get("rank") or "Admin"),
        current_user,
        db,
    )
    return v18._serialize_settings(v18._load(chat.id, current_user, db), current_user, db)


async def _remove_member(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any]:
    chat = v18._load(v18._chat_id(params.get("chat_id")), current_user, db)
    actor = v18._require_manager(chat, current_user)
    target_id = int(params.get("user_id", 0) or 0)
    target = v18._member(chat, target_id)
    if target is None:
        return v18._serialize_settings(chat, current_user, db)
    if target.role == "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_OWNER_CANNOT_BE_REMOVED")
    if target.role == "admin" and actor.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_OWNER_REQUIRED_FOR_ADMIN_REMOVAL")
    if target_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_USE_LEAVE_CHAT")
    db.delete(target)
    db.commit()
    await manager.broadcast_chat(
        chat.id,
        {"roof_update": {"_": "roofUpdateMemberRemoved", "chat_id": chat.id, "user_id": target_id}},
    )
    return v18._serialize_settings(v18._load(chat.id, current_user, db), current_user, db)


async def _leave_chat(params: dict[str, Any], current_user: User, db: Session) -> bool:
    chat = v18._load(v18._chat_id(params.get("chat_id")), current_user, db)
    member = v18._member(chat, current_user.id)
    if member is None:
        return True
    if member.role == "owner":
        raise HTTPException(status.HTTP_409_CONFLICT, "ROOF_TRANSFER_OWNERSHIP_BEFORE_LEAVING")
    db.delete(member)
    db.commit()
    await manager.broadcast_chat(
        chat.id,
        {"roof_update": {"_": "roofUpdateMemberRemoved", "chat_id": chat.id, "user_id": current_user.id}},
    )
    return True


@router.post("/invoke")
async def invoke_v19(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if payload.method == "roof.setMemberAdmin":
        return await _set_member_admin(payload.params, current_user, db)
    if payload.method == "roof.removeMember":
        return await _remove_member(payload.params, current_user, db)
    if payload.method == "roof.leaveChat":
        return await _leave_chat(payload.params, current_user, db)
    return await v18.invoke_v18(payload, current_user, db)
