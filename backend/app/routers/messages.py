from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import ChatMember, Message, User
from app.schemas import MessageCreate, MessageOut, ReadReceipt

router = APIRouter(prefix="/chats/{chat_id}/messages", tags=["messages"])


def _ensure_member(chat_id: int, user_id: int, db: Session) -> ChatMember:
    membership = db.scalar(
        select(ChatMember).where(and_(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id))
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a chat member")
    return membership


@router.get("", response_model=list[MessageOut])
def list_messages(
    chat_id: int,
    before_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    _ensure_member(chat_id, current_user.id, db)
    stmt = select(Message).where(Message.chat_id == chat_id)
    if before_id is not None:
        stmt = stmt.where(Message.id < before_id)
    stmt = stmt.order_by(Message.id.desc()).limit(limit)
    rows = db.scalars(stmt).all()
    rows = list(reversed(rows))
    return [MessageOut.model_validate(r) for r in rows]


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def post_message(
    chat_id: int,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageOut:
    _ensure_member(chat_id, current_user.id, db)
    if not payload.content and not payload.image_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty message")

    msg_type = "image" if payload.image_url else "text"
    msg = Message(
        chat_id=chat_id,
        sender_id=current_user.id,
        type=msg_type,
        content=payload.content,
        image_url=payload.image_url,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    out = MessageOut.model_validate(msg)

    from app.websocket import manager

    await manager.broadcast_chat(
        chat_id,
        {"type": "message", "chat_id": chat_id, "message": out.model_dump(mode="json")},
    )
    return out


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    chat_id: int,
    payload: ReadReceipt,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    membership = _ensure_member(chat_id, current_user.id, db)
    msg = db.get(Message, payload.message_id)
    if msg is None or msg.chat_id != chat_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found in chat")
    if (
        membership.last_read_message_id is None
        or payload.message_id > membership.last_read_message_id
    ):
        membership.last_read_message_id = payload.message_id
        db.commit()

    from app.websocket import manager

    await manager.broadcast_chat(
        chat_id,
        {
            "type": "read",
            "chat_id": chat_id,
            "user_id": current_user.id,
            "message_id": payload.message_id,
        },
    )
