from __future__ import annotations

import base64
import hashlib
import mimetypes
import secrets
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.media_models import MessageMedia, StoredFile
from app.message_feature_models import MessageMeta
from app.models import Chat, ChatMember, Message, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v3 as v3
from app.routers import roof_tweb_v7 as v7
from app.routers import roof_tweb_v8 as v8
from app.routers import roof_tweb_v11 as v11
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])

_BYTES_KEY = "__roof_bytes_base64"
_MAX_PART_BYTES = 512 * 1024


def _bytes_payload(value: bytes) -> dict[str, str]:
    return {_BYTES_KEY: base64.b64encode(value).decode("ascii")}


def _decode_bytes(value: Any) -> bytes:
    if isinstance(value, dict):
        encoded = value.get(_BYTES_KEY)
        if isinstance(encoded, str):
            try:
                return base64.b64decode(encoded, validate=True)
            except ValueError as exc:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    "Invalid Roof upload bytes",
                ) from exc
        numeric_items: list[tuple[int, int]] = []
        for key, item in value.items():
            if not str(key).isdigit():
                numeric_items = []
                break
            numeric_items.append((int(key), int(item)))
        if numeric_items:
            numeric_items.sort(key=lambda pair: pair[0])
            return bytes(item & 0xFF for _, item in numeric_items)
    if isinstance(value, list):
        return bytes(int(item) & 0xFF for item in value)
    if isinstance(value, str):
        try:
            return base64.b64decode(value, validate=True)
        except ValueError:
            return value.encode("utf-8")
    raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof upload bytes are required")


def _file_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 128:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Roof file id")
    return text


def _part_dir(user_id: int, file_id: str) -> Path:
    digest = hashlib.sha256(f"{user_id}:{file_id}".encode()).hexdigest()
    target = settings.uploads_dir / ".parts" / digest
    target.mkdir(parents=True, exist_ok=True)
    return target


def _save_file_part(params: dict[str, Any], current_user: User) -> bool:
    file_id = _file_id(params.get("file_id"))
    file_part = int(params.get("file_part", -1))
    if file_part < 0 or file_part > 100_000:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Roof file part")
    data = _decode_bytes(params.get("bytes"))
    if len(data) > _MAX_PART_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "Roof upload part is too large",
        )
    target = _part_dir(current_user.id, file_id) / f"{file_part:08d}.part"
    target.write_bytes(data)
    return True


def _safe_suffix(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if len(suffix) > 12:
        return ""
    if suffix and not all(char.isalnum() or char == "." for char in suffix):
        return ""
    return suffix


def _document_details(media: dict[str, Any], original_name: str) -> tuple[str, int, int, int]:
    kind = "document"
    width = 0
    height = 0
    duration = 0
    attributes = media.get("attributes") or []
    if not isinstance(attributes, list):
        attributes = []
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        attribute_type = str(attribute.get("_", ""))
        if attribute_type == "documentAttributeVideo":
            kind = "video"
            width = int(attribute.get("w", 0) or 0)
            height = int(attribute.get("h", 0) or 0)
            duration = int(float(attribute.get("duration", 0) or 0))
        elif attribute_type == "documentAttributeAudio":
            flags = attribute.get("pFlags") or {}
            is_voice = isinstance(flags, dict) and bool(flags.get("voice"))
            kind = "voice" if is_voice else "audio"
            duration = int(float(attribute.get("duration", 0) or 0))
        elif attribute_type == "documentAttributeAnimated":
            kind = "animation"
        elif attribute_type == "documentAttributeImageSize":
            width = int(attribute.get("w", 0) or 0)
            height = int(attribute.get("h", 0) or 0)
    if kind == "document" and original_name.lower().endswith(".gif"):
        kind = "animation"
    return kind, width, height, duration


def _assemble_uploaded_file(
    input_file: Any,
    media: dict[str, Any],
    current_user: User,
    db: Session,
) -> StoredFile:
    if not isinstance(input_file, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof input file is required")
    file_id = _file_id(input_file.get("id"))
    parts = int(input_file.get("parts", 0) or 0)
    if parts <= 0 or parts > 100_000:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Roof file part count")

    original_name = str(input_file.get("name") or "file")[:255]
    media_type = str(media.get("_", ""))
    if media_type == "inputMediaUploadedPhoto":
        kind = "photo"
        mime_type = mimetypes.guess_type(original_name)[0] or "image/jpeg"
        width = 0
        height = 0
        duration = 0
    else:
        mime_type = str(media.get("mime_type") or "application/octet-stream")[:160]
        kind, width, height, duration = _document_details(media, original_name)

    part_dir = _part_dir(current_user.id, file_id)
    part_paths = [part_dir / f"{index:08d}.part" for index in range(parts)]
    missing = [path.name for path in part_paths if not path.is_file()]
    if missing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Roof upload is incomplete; missing {len(missing)} part(s)",
        )

    storage_name = f"roof_{secrets.token_urlsafe(18)}{_safe_suffix(original_name)}"
    target = settings.uploads_dir / storage_name
    max_bytes = settings.max_upload_mb * 1024 * 1024
    total = 0
    try:
        with target.open("wb") as output:
            for path in part_paths:
                chunk = path.read_bytes()
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        f"Roof file exceeds {settings.max_upload_mb} MB",
                    )
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        shutil.rmtree(part_dir, ignore_errors=True)

    stored = StoredFile(
        owner_user_id=current_user.id,
        storage_name=storage_name,
        original_name=original_name,
        mime_type=mime_type,
        size=total,
        kind=kind,
        width=width,
        height=height,
        duration=duration,
    )
    db.add(stored)
    db.flush()
    return stored


def _can_access_file(stored: StoredFile, current_user: User, db: Session) -> bool:
    if stored.owner_user_id == current_user.id:
        return True
    message_id = db.scalar(
        select(MessageMedia.message_id)
        .join(Message, Message.id == MessageMedia.message_id)
        .join(ChatMember, ChatMember.chat_id == Message.chat_id)
        .where(
            MessageMedia.stored_file_id == stored.id,
            ChatMember.user_id == current_user.id,
        )
        .limit(1)
    )
    return message_id is not None


def _stored_from_reference(value: Any, current_user: User, db: Session) -> StoredFile:
    raw_id = value.get("id") if isinstance(value, dict) else value
    try:
        stored_id = int(raw_id or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Roof media id") from exc
    stored = db.get(StoredFile, stored_id)
    if stored is None or not _can_access_file(stored, current_user, db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof media file not found")
    return stored


def _stored_from_media(
    media: Any,
    current_user: User,
    db: Session,
) -> StoredFile:
    if not isinstance(media, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof media is required")
    kind = str(media.get("_", ""))
    if kind in {"inputMediaUploadedPhoto", "inputMediaUploadedDocument"}:
        return _assemble_uploaded_file(media.get("file"), media, current_user, db)
    if kind in {"inputMediaPhoto", "inputMediaDocument"}:
        return _stored_from_reference(media.get("id"), current_user, db)
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        f"Unsupported Roof media type: {kind or 'unknown'}",
    )


def _file_reference(stored: StoredFile) -> dict[str, str]:
    return _bytes_payload(f"roof:{stored.id}".encode())


def _photo_entity(stored: StoredFile) -> dict[str, Any]:
    width = stored.width or 1280
    height = stored.height or 1280
    return {
        "_": "photo",
        "id": stored.id,
        "access_hash": "0",
        "file_reference": _file_reference(stored),
        "date": legacy._unix(stored.created_at),
        "sizes": [
            {
                "_": "photoSize",
                "type": "x",
                "w": width,
                "h": height,
                "size": stored.size,
            }
        ],
        "dc_id": 1,
        "pFlags": {},
    }


def _document_attributes(stored: StoredFile) -> list[dict[str, Any]]:
    attributes: list[dict[str, Any]] = [
        {"_": "documentAttributeFilename", "file_name": stored.original_name}
    ]
    if stored.kind == "video":
        attributes.append(
            {
                "_": "documentAttributeVideo",
                "duration": stored.duration,
                "w": stored.width or 1280,
                "h": stored.height or 720,
                "pFlags": {},
            }
        )
    elif stored.kind in {"audio", "voice"}:
        flags = {"voice": True} if stored.kind == "voice" else {}
        attributes.append(
            {
                "_": "documentAttributeAudio",
                "duration": stored.duration,
                "pFlags": flags,
            }
        )
    elif stored.kind == "animation":
        attributes.append({"_": "documentAttributeAnimated"})
    return attributes


def _document_entity(stored: StoredFile) -> dict[str, Any]:
    return {
        "_": "document",
        "id": stored.id,
        "access_hash": "0",
        "file_reference": _file_reference(stored),
        "date": legacy._unix(stored.created_at),
        "mime_type": stored.mime_type,
        "size": stored.size,
        "thumbs": [],
        "dc_id": 1,
        "attributes": _document_attributes(stored),
        "pFlags": {},
    }


def _message_media(stored: StoredFile) -> dict[str, Any]:
    if stored.kind == "photo":
        return {
            "_": "messageMediaPhoto",
            "photo": _photo_entity(stored),
            "pFlags": {},
        }
    return {
        "_": "messageMediaDocument",
        "document": _document_entity(stored),
        "pFlags": {},
    }


def _media_by_message_ids(ids: set[int], db: Session) -> dict[int, StoredFile]:
    if not ids:
        return {}
    rows = list(
        db.execute(
            select(MessageMedia, StoredFile)
            .join(StoredFile, StoredFile.id == MessageMedia.stored_file_id)
            .where(MessageMedia.message_id.in_(ids))
        ).all()
    )
    return {media.message_id: stored for media, stored in rows}


def _result_message_items(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    items: list[dict[str, Any]] = []
    for item in result.get("messages") or []:
        if isinstance(item, dict):
            items.append(item)
    for update in result.get("updates") or []:
        if not isinstance(update, dict):
            continue
        item = update.get("message")
        if isinstance(item, dict):
            items.append(item)
    return items


def _decorate_media(result: Any, db: Session) -> Any:
    items = _result_message_items(result)
    ids = {int(item.get("id", 0) or 0) for item in items}
    ids.discard(0)
    stored_by_message = _media_by_message_ids(ids, db)
    for item in items:
        stored = stored_by_message.get(int(item.get("id", 0) or 0))
        if stored is not None:
            item["media"] = _message_media(stored)
            item.pop("roof_media", None)
    return result


def _check_send_access(chat: Chat, current_user: User) -> None:
    if chat.type == "channel" and not v11._is_manager(chat, current_user.id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only Roof channel admins can post media",
        )


def _reply_id(params: dict[str, Any]) -> int:
    return v7._reply_id(params)


def _attach_reply(
    message: Message,
    chat: Chat,
    params: dict[str, Any],
    db: Session,
) -> None:
    reply_to = _reply_id(params)
    if not reply_to:
        return
    source = db.get(Message, reply_to)
    if source is None or source.chat_id != chat.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Roof media reply target was not found",
        )
    db.add(MessageMeta(message_id=message.id, reply_to_message_id=reply_to))


def _chat_entities(chat: Chat, current_user: User) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    users = [legacy._user(member.user, current_user.id) for member in chat.members]
    if chat.type == "channel":
        return [v3._channel_entity(chat)], users
    if chat.type == "direct":
        return [], users
    return [legacy._chat_entity(chat)], users


def _create_media_message(
    chat: Chat,
    stored: StoredFile,
    caption: str,
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> Message:
    message = Message(
        chat_id=chat.id,
        sender_id=current_user.id,
        type=stored.kind,
        content=caption,
        image_url=f"/uploads/{stored.storage_name}" if stored.kind == "photo" else None,
    )
    db.add(message)
    db.flush()
    db.add(
        MessageMedia(
            message_id=message.id,
            stored_file_id=stored.id,
            kind=stored.kind,
        )
    )
    _attach_reply(message, chat, params, db)
    return message


def _serialize_created_message(
    message: Message,
    chat: Chat,
    stored: StoredFile,
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    item = v8._message_item(message, chat, current_user, db)
    item["media"] = _message_media(stored)
    item.pop("roof_media", None)
    return item


async def _send_media(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = v8._resolve_peer(params.get("peer"), current_user, db)
    _check_send_access(chat, current_user)
    stored = _stored_from_media(params.get("media"), current_user, db)
    caption = str(params.get("message") or "")[:4096]
    message = _create_media_message(chat, stored, caption, params, current_user, db)
    db.commit()
    db.refresh(message)
    db.refresh(stored)

    item = _serialize_created_message(message, chat, stored, current_user, db)
    update = {
        "_": "updateNewMessage",
        "message": item,
        "pts": message.id,
        "pts_count": 1,
    }
    chats, users = _chat_entities(chat, current_user)
    result: dict[str, Any] = {
        "_": "updates",
        "updates": [update],
        "users": users,
        "chats": chats,
        "date": legacy._unix(message.created_at),
        "seq": message.id,
    }
    result = v7._decorate_result(result, current_user, db)
    result = _decorate_media(result, db)
    await manager.broadcast_chat(chat.id, {"roof_update": update})
    return result


async def _send_multi_media(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    chat = v8._resolve_peer(params.get("peer"), current_user, db)
    _check_send_access(chat, current_user)
    values = params.get("multi_media") or []
    if not isinstance(values, list) or not values:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof media album is empty")

    created: list[tuple[Message, StoredFile]] = []
    for value in values[:20]:
        if not isinstance(value, dict):
            continue
        stored = _stored_from_media(value.get("media"), current_user, db)
        caption = str(value.get("message") or "")[:4096]
        message = _create_media_message(chat, stored, caption, params, current_user, db)
        created.append((message, stored))
    if not created:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof media album is empty")
    db.commit()

    updates: list[dict[str, Any]] = []
    for message, stored in created:
        db.refresh(message)
        db.refresh(stored)
        item = _serialize_created_message(message, chat, stored, current_user, db)
        updates.append(
            {
                "_": "updateNewMessage",
                "message": item,
                "pts": message.id,
                "pts_count": 1,
            }
        )

    chats, users = _chat_entities(chat, current_user)
    result: dict[str, Any] = {
        "_": "updates",
        "updates": updates,
        "users": users,
        "chats": chats,
        "date": legacy._unix(None),
        "seq": max(message.id for message, _ in created),
    }
    result = v7._decorate_result(result, current_user, db)
    result = _decorate_media(result, db)
    for update in updates:
        await manager.broadcast_chat(chat.id, {"roof_update": update})
    return result


def _upload_media(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    peer = params.get("peer")
    if peer is not None:
        chat = v8._resolve_peer(peer, current_user, db)
        _check_send_access(chat, current_user)
    stored = _stored_from_media(params.get("media"), current_user, db)
    db.commit()
    db.refresh(stored)
    return _message_media(stored)


def _upload_get_file(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    location = params.get("location")
    if not isinstance(location, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof file location is required")
    kind = str(location.get("_", ""))
    if kind not in {"inputPhotoFileLocation", "inputDocumentFileLocation"}:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unsupported Roof file location: {kind or 'unknown'}",
        )
    stored = _stored_from_reference(location.get("id"), current_user, db)
    path = settings.uploads_dir / stored.storage_name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof media bytes were not found")
    offset = max(0, int(params.get("offset", 0) or 0))
    limit = max(1, min(int(params.get("limit", 512 * 1024) or 512 * 1024), 1024 * 1024))
    with path.open("rb") as source:
        source.seek(offset)
        data = source.read(limit)
    return {
        "_": "upload.file",
        "type": {"_": "storage.fileUnknown"},
        "mtime": legacy._unix(stored.created_at),
        "bytes": _bytes_payload(data),
    }


def _copy_forwarded_media(
    params: dict[str, Any],
    result: Any,
    db: Session,
) -> None:
    raw_ids = params.get("id") or []
    if not isinstance(raw_ids, list):
        raw_ids = [raw_ids]
    source_ids = [int(value) for value in raw_ids if int(value) > 0]
    new_ids = [
        int(item.get("id", 0) or 0)
        for item in _result_message_items(result)
        if int(item.get("id", 0) or 0) > 0
    ]
    source_media = _media_by_message_ids(set(source_ids), db)
    changed = False
    for source_id, new_id in zip(source_ids, new_ids, strict=False):
        stored = source_media.get(source_id)
        if stored is None or db.get(MessageMedia, new_id) is not None:
            continue
        db.add(
            MessageMedia(
                message_id=new_id,
                stored_file_id=stored.id,
                kind=stored.kind,
            )
        )
        changed = True
    if changed:
        db.commit()


@router.post("/invoke")
async def invoke_v12(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method in {"upload.saveFilePart", "upload.saveBigFilePart"}:
        return _save_file_part(params, current_user)
    if method == "upload.getFile":
        return _upload_get_file(params, current_user, db)
    if method == "messages.uploadMedia":
        return _upload_media(params, current_user, db)
    if method == "messages.sendMedia":
        return await _send_media(params, current_user, db)
    if method == "messages.sendMultiMedia":
        return await _send_multi_media(params, current_user, db)

    result = await v11.invoke_v11(payload, current_user, db)
    if method == "messages.forwardMessages":
        _copy_forwarded_media(params, result, db)
    if method in {
        "messages.getDialogs",
        "messages.getPinnedDialogs",
        "messages.getPeerDialogs",
        "messages.getHistory",
        "messages.search",
        "messages.searchGlobal",
        "messages.getMessages",
        "channels.getMessages",
        "messages.forwardMessages",
        "messages.editMessage",
        "messages.getPinnedHistory",
        "messages.getSavedDialogs",
        "messages.getSavedHistory",
    }:
        return _decorate_media(result, db)
    return result
