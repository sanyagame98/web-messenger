from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.media_album_models import MediaAlbumItem
from app.models import Chat, Message, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v22 as v22
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _message_items(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    items: list[dict[str, Any]] = []
    for item in result.get("messages") or []:
        if isinstance(item, dict):
            items.append(item)
    for update in result.get("updates") or []:
        if isinstance(update, dict) and isinstance(update.get("message"), dict):
            items.append(update["message"])
    return items


def _enable_video_streaming(item: dict[str, Any]) -> None:
    media = item.get("media")
    if not isinstance(media, dict) or media.get("_") != "messageMediaDocument":
        return
    document = media.get("document")
    if not isinstance(document, dict):
        return
    for attribute in document.get("attributes") or []:
        if not isinstance(attribute, dict) or attribute.get("_") != "documentAttributeVideo":
            continue
        flags = attribute.setdefault("pFlags", {})
        if isinstance(flags, dict):
            flags["supports_streaming"] = True


def _album_rows(ids: set[int], db: Session) -> dict[int, MediaAlbumItem]:
    if not ids:
        return {}
    rows = list(
        db.scalars(select(MediaAlbumItem).where(MediaAlbumItem.message_id.in_(ids))).all()
    )
    return {row.message_id: row for row in rows}


def _decorate_media(result: Any, db: Session) -> Any:
    items = _message_items(result)
    ids = {int(item.get("id", 0) or 0) for item in items}
    ids.discard(0)
    albums = _album_rows(ids, db)
    for item in items:
        _enable_video_streaming(item)
        row = albums.get(int(item.get("id", 0) or 0))
        if row is not None:
            item["grouped_id"] = str(row.grouped_id)
    return result


def _remember_album(result: Any, db: Session) -> tuple[int, list[int]] | None:
    ids = [int(item.get("id", 0) or 0) for item in _message_items(result)]
    ids = list(dict.fromkeys(message_id for message_id in ids if message_id > 0))
    if len(ids) < 2:
        return None
    grouped_id = secrets.randbits(62) + 1
    existing = _album_rows(set(ids), db)
    for position, message_id in enumerate(ids):
        row = existing.get(message_id)
        if row is None:
            db.add(
                MediaAlbumItem(
                    message_id=message_id,
                    grouped_id=grouped_id,
                    position=position,
                )
            )
        else:
            row.grouped_id = grouped_id
            row.position = position
    db.commit()
    return grouped_id, ids


async def _rebroadcast_album(grouped_id: int, ids: list[int], db: Session) -> None:
    rows = _album_rows(set(ids), db)
    for message_id in ids:
        message = db.get(Message, message_id)
        if message is None:
            continue
        chat = db.get(Chat, message.chat_id)
        if chat is None:
            continue
        row = rows.get(message_id)
        await manager.broadcast_chat(
            chat.id,
            {
                "roof_update": {
                    "_": "roofUpdateMediaAlbum",
                    "chat_id": chat.id,
                    "message_id": message_id,
                    "grouped_id": str(grouped_id),
                    "position": row.position if row is not None else 0,
                }
            },
        )


@router.post("/invoke")
async def invoke_v23(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    result = await v22.invoke_v22(payload, current_user, db)

    if payload.method == "messages.sendMultiMedia":
        album = _remember_album(result, db)
        if album is not None:
            grouped_id, ids = album
            result = _decorate_media(result, db)
            await _rebroadcast_album(grouped_id, ids, db)
            return result

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
        "messages.sendMedia",
        "messages.editMessage",
    }:
        return _decorate_media(result, db)
    return result
