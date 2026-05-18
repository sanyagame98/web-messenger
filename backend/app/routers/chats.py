from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import Chat, ChatMember, Message, User
from app.schemas import (
    ChatCreateDirect,
    ChatCreateGroup,
    ChatOut,
    MessageOut,
    UserPublic,
)

router = APIRouter(prefix="/chats", tags=["chats"])


def _chat_to_out(chat: Chat, current_user_id: int, db: Session) -> ChatOut:
    members = [UserPublic.model_validate(m.user) for m in chat.members]

    last_msg = db.scalar(
        select(Message).where(Message.chat_id == chat.id).order_by(Message.id.desc()).limit(1)
    )
    last_message = MessageOut.model_validate(last_msg) if last_msg else None

    my_membership = next((m for m in chat.members if m.user_id == current_user_id), None)
    last_read_id = my_membership.last_read_message_id if my_membership else None
    unread_stmt = (
        select(func.count(Message.id))
        .where(Message.chat_id == chat.id)
        .where(Message.sender_id != current_user_id)
    )
    if last_read_id:
        unread_stmt = unread_stmt.where(Message.id > last_read_id)
    unread_count = db.scalar(unread_stmt) or 0

    display_name = chat.name
    avatar_url = chat.avatar_url
    if chat.type == "direct":
        other = next((m.user for m in chat.members if m.user_id != current_user_id), None)
        if other:
            display_name = other.display_name or other.username
            avatar_url = other.avatar_url

    return ChatOut(
        id=chat.id,
        type=chat.type,
        name=display_name,
        avatar_url=avatar_url,
        created_at=chat.created_at,
        members=members,
        last_message=last_message,
        unread_count=int(unread_count),
    )


def _ensure_member(chat_id: int, user_id: int, db: Session) -> ChatMember:
    membership = db.scalar(
        select(ChatMember).where(and_(ChatMember.chat_id == chat_id, ChatMember.user_id == user_id))
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a chat member")
    return membership


@router.get("", response_model=list[ChatOut])
def list_chats(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ChatOut]:
    chat_ids = db.scalars(
        select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)
    ).all()
    if not chat_ids:
        return []
    chats = (
        db.scalars(
            select(Chat)
            .where(Chat.id.in_(chat_ids))
            .options(selectinload(Chat.members).selectinload(ChatMember.user))
        )
        .unique()
        .all()
    )
    results = [_chat_to_out(c, current_user.id, db) for c in chats]
    results.sort(
        key=lambda c: c.last_message.created_at if c.last_message else c.created_at,
        reverse=True,
    )
    return results


@router.post("/direct", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
def create_direct_chat(
    payload: ChatCreateDirect,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatOut:
    if payload.username == current_user.username:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot chat with yourself")
    other = db.scalar(select(User).where(User.username == payload.username))
    if other is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    my_chat_ids = set(
        db.scalars(select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)).all()
    )
    other_chat_ids = set(
        db.scalars(select(ChatMember.chat_id).where(ChatMember.user_id == other.id)).all()
    )
    common_ids = my_chat_ids & other_chat_ids
    if common_ids:
        existing = db.scalar(
            select(Chat)
            .where(Chat.id.in_(common_ids))
            .where(Chat.type == "direct")
            .options(selectinload(Chat.members).selectinload(ChatMember.user))
        )
        if existing is not None:
            return _chat_to_out(existing, current_user.id, db)

    chat = Chat(type="direct", name="", created_by=current_user.id)
    db.add(chat)
    db.flush()
    db.add(ChatMember(chat_id=chat.id, user_id=current_user.id, role="member"))
    db.add(ChatMember(chat_id=chat.id, user_id=other.id, role="member"))
    db.commit()
    db.refresh(chat)
    chat = db.scalar(
        select(Chat)
        .where(Chat.id == chat.id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    assert chat is not None
    return _chat_to_out(chat, current_user.id, db)


@router.post("/group", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
def create_group_chat(
    payload: ChatCreateGroup,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatOut:
    usernames = {u for u in payload.member_usernames if u != current_user.username}
    members: list[User] = []
    if usernames:
        members = list(db.scalars(select(User).where(User.username.in_(usernames))).all())
        found = {u.username for u in members}
        missing = usernames - found
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Users not found: {', '.join(sorted(missing))}",
            )

    chat = Chat(type="group", name=payload.name.strip(), created_by=current_user.id)
    db.add(chat)
    db.flush()
    db.add(ChatMember(chat_id=chat.id, user_id=current_user.id, role="owner"))
    for u in members:
        db.add(ChatMember(chat_id=chat.id, user_id=u.id, role="member"))
    db.commit()
    db.refresh(chat)
    chat = db.scalar(
        select(Chat)
        .where(Chat.id == chat.id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    assert chat is not None
    return _chat_to_out(chat, current_user.id, db)


@router.get("/{chat_id}", response_model=ChatOut)
def get_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatOut:
    _ensure_member(chat_id, current_user.id, db)
    chat = db.scalar(
        select(Chat)
        .where(Chat.id == chat_id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found")
    return _chat_to_out(chat, current_user.id, db)
