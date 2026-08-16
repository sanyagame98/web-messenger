from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, Message, User
from app.saved_messages_models import SavedMessage
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v24 as v24
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _source_message(message_id: int, current_user: User, db: Session) -> tuple[Message, Chat]:
    message = db.get(Message, message_id)
    if message is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof message not found")
    chat = db.scalar(
        select(Chat)
        .where(Chat.id == message.chat_id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    if chat is None or not any(member.user_id == current_user.id for member in chat.members):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Message is not visible to this user")
    return message, chat


def _saved_items(current_user: User, db: Session, limit: int = 100) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(SavedMessage)
            .where(SavedMessage.user_id == current_user.id)
            .order_by(SavedMessage.id.desc())
            .limit(max(1, min(limit, 200)))
        ).all()
    )
    result: list[dict[str, Any]] = []
    for row in reversed(rows):
        message = db.get(Message, row.message_id)
        if message is None:
            continue
        chat = db.scalar(
            select(Chat)
            .where(Chat.id == message.chat_id)
            .options(selectinload(Chat.members).selectinload(ChatMember.user))
        )
        if chat is None:
            continue
        item = legacy._message(message, chat, current_user.id)
        item["roof_saved"] = True
        item["roof_saved_at"] = legacy._unix(row.created_at)
        item["roof_source_chat_id"] = chat.id
        result.append(item)
    return result


@router.post("/invoke")
async def invoke_v25(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "roof.getSavedMessages":
        return {
            "_": "roof.savedMessages",
            "messages": _saved_items(current_user, db, int(params.get("limit", 100) or 100)),
        }

    if method == "roof.saveMessage":
        message_id = int(params.get("message_id", 0) or 0)
        _source_message(message_id, current_user, db)
        row = db.scalar(
            select(SavedMessage).where(
                SavedMessage.user_id == current_user.id,
                SavedMessage.message_id == message_id,
            )
        )
        if row is None:
            row = SavedMessage(user_id=current_user.id, message_id=message_id)
            db.add(row)
            db.commit()
            db.refresh(row)
        await manager.send_to_user(current_user.id, {"roof_update": {"_": "roofUpdateSavedMessages", "message_id": message_id, "saved": True}})
        return {"_": "boolTrue"}

    if method == "roof.unsaveMessage":
        message_id = int(params.get("message_id", 0) or 0)
        row = db.scalar(
            select(SavedMessage).where(
                SavedMessage.user_id == current_user.id,
                SavedMessage.message_id == message_id,
            )
        )
        if row is not None:
            db.delete(row)
            db.commit()
        await manager.send_to_user(current_user.id, {"roof_update": {"_": "roofUpdateSavedMessages", "message_id": message_id, "saved": False}})
        return {"_": "boolTrue"}

    if method == "roof.clearSavedMessages":
        rows = list(db.scalars(select(SavedMessage).where(SavedMessage.user_id == current_user.id)).all())
        for row in rows:
            db.delete(row)
        db.commit()
        await manager.send_to_user(current_user.id, {"roof_update": {"_": "roofUpdateSavedMessages", "cleared": True}})
        return {"_": "boolTrue"}

    return await v24.invoke_v24(payload, current_user, db)
