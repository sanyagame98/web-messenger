from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v4 as v4
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


@router.post("/invoke")
async def invoke_v5(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    if payload.method == "messages.setTyping":
        chat = legacy._resolve_peer(payload.params.get("peer"), current_user, db)
        await manager.broadcast_chat(
            chat.id,
            {
                "type": "typing",
                "chat_id": chat.id,
                "chat_type": chat.type,
                "member_user_ids": [member.user_id for member in chat.members],
                "user_id": current_user.id,
            },
        )
        return True

    return await v4.invoke_v4(payload, current_user, db)
