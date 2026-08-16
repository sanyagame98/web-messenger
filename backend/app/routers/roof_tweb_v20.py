from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.chat_meta_models import ChatMeta
from app.database import get_db
from app.deps import get_current_user
from app.discussion_models import DiscussionReaction, PostDiscussion
from app.message_feature_models import MessageMeta
from app.models import Chat, ChatMember, Message, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v14 as v14
from app.routers import roof_tweb_v19 as v19
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])
ALLOWED_REACTIONS = set(v14.ROOF_REACTIONS)


def _channel(channel_id: int, current_user: User, db: Session) -> Chat:
    chat = db.scalar(
        select(Chat)
        .where(Chat.id == channel_id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    if chat is None or chat.type != "channel":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_CHANNEL_NOT_FOUND")
    if not any(member.user_id == current_user.id for member in chat.members):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_CHANNEL_ACCESS_DENIED")
    meta = db.get(ChatMeta, chat.id)
    if meta is None or not meta.comments_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "ROOF_CHANNEL_COMMENTS_DISABLED")
    return chat


def _post(channel: Chat, post_id: int, db: Session) -> Message:
    message = db.get(Message, post_id)
    if message is None or message.chat_id != channel.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_CHANNEL_POST_NOT_FOUND")
    return message


def _discussion_link(channel: Chat, post: Message, db: Session, create: bool = True) -> PostDiscussion | None:
    link = db.get(PostDiscussion, post.id)
    if link is not None:
        return link
    if not create:
        return None
    discussion = Chat(type="discussion", name=f"Комментарии · {channel.name}", created_by=channel.created_by)
    db.add(discussion)
    db.flush()
    for member in channel.members:
        if member.role in {"owner", "admin"}:
            db.add(ChatMember(chat_id=discussion.id, user_id=member.user_id, role=member.role))
    link = PostDiscussion(post_message_id=post.id, channel_id=channel.id, discussion_chat_id=discussion.id)
    db.add(link)
    db.flush()
    return link


def _discussion_chat(link: PostDiscussion, db: Session) -> Chat:
    chat = db.scalar(
        select(Chat)
        .where(Chat.id == link.discussion_chat_id)
        .options(selectinload(Chat.members).selectinload(ChatMember.user))
    )
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_DISCUSSION_NOT_FOUND")
    return chat


def _joined(chat: Chat, user_id: int) -> bool:
    return any(member.user_id == user_id for member in chat.members)


def _reaction_summary(message_id: int, current_user_id: int, db: Session) -> list[dict[str, Any]]:
    rows = list(db.scalars(select(DiscussionReaction).where(DiscussionReaction.message_id == message_id)).all())
    counts = Counter(row.emoji for row in rows)
    mine = {row.emoji for row in rows if row.user_id == current_user_id}
    return [{"emoji": emoji, "count": count, "chosen": emoji in mine} for emoji, count in counts.items()]


def _comment(message: Message, current_user_id: int, db: Session) -> dict[str, Any]:
    sender = db.get(User, message.sender_id) if message.sender_id else None
    meta = db.get(MessageMeta, message.id)
    return {
        "id": message.id,
        "message": message.content,
        "created_at": message.created_at.isoformat(),
        "edited": bool(message.edited),
        "reply_to": meta.reply_to_message_id if meta else None,
        "sender": {
            "id": sender.id,
            "name": sender.display_name or sender.username,
            "username": sender.username,
            "avatar_url": sender.avatar_url,
        } if sender else None,
        "reactions": _reaction_summary(message.id, current_user_id, db),
        "can_edit": message.sender_id == current_user_id,
    }


def _comments(link: PostDiscussion, current_user_id: int, db: Session) -> list[dict[str, Any]]:
    rows = list(db.scalars(select(Message).where(Message.chat_id == link.discussion_chat_id).order_by(Message.id.asc())).all())
    return [_comment(message, current_user_id, db) for message in rows]


def _state(channel: Chat, post: Message, current_user: User, db: Session) -> dict[str, Any]:
    link = _discussion_link(channel, post, db, create=True)
    assert link is not None
    discussion = _discussion_chat(link, db)
    comments = _comments(link, current_user.id, db)
    db.commit()
    return {
        "_": "roof.postDiscussion",
        "post": {"id": post.id, "channel_id": channel.id, "channel_title": channel.name, "message": post.content, "created_at": post.created_at.isoformat()},
        "discussion_chat_id": discussion.id,
        "joined": _joined(discussion, current_user.id),
        "count": len(comments),
        "comments": comments,
        "available_reactions": v14.ROOF_REACTIONS,
    }


def _counts(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    channel = _channel(int(params.get("channel_id", 0) or 0), current_user, db)
    values = params.get("post_ids") or []
    if not isinstance(values, list):
        values = [values]
    post_ids = {int(value) for value in values if int(value or 0) > 0}
    valid_ids = set(db.scalars(select(Message.id).where(Message.chat_id == channel.id, Message.id.in_(post_ids))).all()) if post_ids else set()
    counts = {post_id: 0 for post_id in valid_ids}
    links = list(db.scalars(select(PostDiscussion).where(PostDiscussion.post_message_id.in_(valid_ids))).all()) if valid_ids else []
    chat_to_post = {link.discussion_chat_id: link.post_message_id for link in links}
    if chat_to_post:
        for chat_id, count in db.execute(select(Message.chat_id, func.count(Message.id)).where(Message.chat_id.in_(chat_to_post)).group_by(Message.chat_id)).all():
            counts[chat_to_post[int(chat_id)]] = int(count)
    return {"_": "roof.postCommentCounts", "counts": {str(key): value for key, value in counts.items()}}


async def _join(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    channel = _channel(int(params.get("channel_id", 0) or 0), current_user, db)
    post = _post(channel, int(params.get("post_id", 0) or 0), db)
    link = _discussion_link(channel, post, db, create=True)
    assert link is not None
    discussion = _discussion_chat(link, db)
    if not _joined(discussion, current_user.id):
        db.add(ChatMember(chat_id=discussion.id, user_id=current_user.id, role="member"))
        db.commit()
    return _state(channel, post, current_user, db)


async def _send_comment(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    channel = _channel(int(params.get("channel_id", 0) or 0), current_user, db)
    post = _post(channel, int(params.get("post_id", 0) or 0), db)
    link = _discussion_link(channel, post, db, create=True)
    assert link is not None
    discussion = _discussion_chat(link, db)
    if not _joined(discussion, current_user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_DISCUSSION_JOIN_REQUIRED")
    text = str(params.get("message") or "").strip()
    if not text or len(text) > 4096:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_COMMENT_INVALID")
    message = Message(chat_id=discussion.id, sender_id=current_user.id, type="text", content=text)
    db.add(message)
    db.flush()
    reply_to = int(params.get("reply_to", 0) or 0)
    if reply_to:
        parent = db.get(Message, reply_to)
        if parent is None or parent.chat_id != discussion.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_COMMENT_REPLY_INVALID")
        db.add(MessageMeta(message_id=message.id, reply_to_message_id=reply_to))
    db.commit()
    db.refresh(message)
    item = _comment(message, current_user.id, db)
    count = int(db.scalar(select(func.count(Message.id)).where(Message.chat_id == discussion.id)) or 0)
    update = {"_": "roofUpdatePostComment", "channel_id": channel.id, "post_id": post.id, "discussion_chat_id": discussion.id, "count": count, "comment": item}
    await manager.broadcast_chat(discussion.id, {"roof_update": update})
    await manager.broadcast_chat(channel.id, {"roof_update": update})
    return item


async def _react(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    channel = _channel(int(params.get("channel_id", 0) or 0), current_user, db)
    post = _post(channel, int(params.get("post_id", 0) or 0), db)
    link = _discussion_link(channel, post, db, create=False)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_DISCUSSION_NOT_FOUND")
    discussion = _discussion_chat(link, db)
    if not _joined(discussion, current_user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_DISCUSSION_JOIN_REQUIRED")
    comment = db.get(Message, int(params.get("comment_id", 0) or 0))
    if comment is None or comment.chat_id != discussion.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ROOF_COMMENT_NOT_FOUND")
    emoji = str(params.get("emoji") or "").strip()
    if emoji not in ALLOWED_REACTIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ROOF_REACTION_INVALID")
    existing = db.scalar(select(DiscussionReaction).where(DiscussionReaction.message_id == comment.id, DiscussionReaction.user_id == current_user.id))
    if existing is not None and existing.emoji == emoji:
        db.delete(existing)
    elif existing is None:
        db.add(DiscussionReaction(message_id=comment.id, user_id=current_user.id, emoji=emoji))
    else:
        existing.emoji = emoji
    db.commit()
    reactions = _reaction_summary(comment.id, current_user.id, db)
    await manager.broadcast_chat(discussion.id, {"roof_update": {"_": "roofUpdateDiscussionReaction", "channel_id": channel.id, "post_id": post.id, "comment_id": comment.id, "reactions": reactions}})
    return {"comment_id": comment.id, "reactions": reactions}


async def _delete_comment(params: dict[str, Any], current_user: User, db: Session) -> bool:
    channel = _channel(int(params.get("channel_id", 0) or 0), current_user, db)
    post = _post(channel, int(params.get("post_id", 0) or 0), db)
    link = _discussion_link(channel, post, db, create=False)
    if link is None:
        return True
    discussion = _discussion_chat(link, db)
    comment = db.get(Message, int(params.get("comment_id", 0) or 0))
    if comment is None or comment.chat_id != discussion.id:
        return True
    manager_member = next((member for member in channel.members if member.user_id == current_user.id), None)
    if comment.sender_id != current_user.id and not bool(manager_member and manager_member.role in {"owner", "admin"}):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ROOF_COMMENT_DELETE_FORBIDDEN")
    comment_id = comment.id
    db.delete(comment)
    db.commit()
    count = int(db.scalar(select(func.count(Message.id)).where(Message.chat_id == discussion.id)) or 0)
    update = {"_": "roofUpdatePostCommentDeleted", "channel_id": channel.id, "post_id": post.id, "comment_id": comment_id, "count": count}
    await manager.broadcast_chat(discussion.id, {"roof_update": update})
    await manager.broadcast_chat(channel.id, {"roof_update": update})
    return True


@router.post("/invoke")
async def invoke_v20(payload: legacy.RoofInvokeRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    method = payload.method
    params = payload.params
    if method == "roof.getPostCommentCounts":
        return _counts(params, current_user, db)
    if method == "roof.getPostDiscussion":
        channel = _channel(int(params.get("channel_id", 0) or 0), current_user, db)
        post = _post(channel, int(params.get("post_id", 0) or 0), db)
        return _state(channel, post, current_user, db)
    if method == "roof.joinPostDiscussion":
        return await _join(params, current_user, db)
    if method == "roof.sendPostComment":
        return await _send_comment(params, current_user, db)
    if method == "roof.reactPostComment":
        return await _react(params, current_user, db)
    if method == "roof.deletePostComment":
        return await _delete_comment(params, current_user, db)
    return await v19.invoke_v19(payload, current_user, db)
