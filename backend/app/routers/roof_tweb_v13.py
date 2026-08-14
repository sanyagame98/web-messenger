from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.media_models import ProfilePhoto, StoredFile
from app.models import Chat, ChatMember, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v3 as v3
from app.routers import roof_tweb_v11 as v11
from app.routers import roof_tweb_v12 as v12
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _profile_row_for_user(user_id: int, db: Session) -> tuple[ProfilePhoto, StoredFile] | None:
    row = db.execute(
        select(ProfilePhoto, StoredFile)
        .join(StoredFile, StoredFile.id == ProfilePhoto.stored_file_id)
        .where(ProfilePhoto.user_id == user_id)
    ).first()
    return row if row is not None else None


def _profile_row_for_chat(chat_id: int, db: Session) -> tuple[ProfilePhoto, StoredFile] | None:
    row = db.execute(
        select(ProfilePhoto, StoredFile)
        .join(StoredFile, StoredFile.id == ProfilePhoto.stored_file_id)
        .where(ProfilePhoto.chat_id == chat_id)
    ).first()
    return row if row is not None else None


def _user_profile_photo(stored: StoredFile) -> dict[str, Any]:
    return {
        "_": "userProfilePhoto",
        "photo_id": stored.id,
        "dc_id": 1,
        "pFlags": {},
    }


def _chat_photo(stored: StoredFile) -> dict[str, Any]:
    return {
        "_": "chatPhoto",
        "photo_id": stored.id,
        "dc_id": 1,
        "pFlags": {},
    }


def _decorate_user(user: dict[str, Any], db: Session) -> None:
    user_id = int(user.get("id", 0) or 0)
    if user_id <= 0:
        return
    row = _profile_row_for_user(user_id, db)
    if row is None:
        return
    _, stored = row
    user["photo"] = _user_profile_photo(stored)


def _decorate_chat(chat: dict[str, Any], db: Session) -> None:
    chat_id = int(chat.get("id", 0) or 0)
    if chat_id <= 0:
        return
    row = _profile_row_for_chat(chat_id, db)
    if row is None:
        return
    _, stored = row
    chat["photo"] = _chat_photo(stored)


def _decorate_avatar_entities(result: Any, db: Session) -> Any:
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict) and item.get("_") == "user":
                _decorate_user(item, db)
        return result
    if not isinstance(result, dict):
        return result

    users = result.get("users") or []
    if isinstance(users, list):
        for user in users:
            if isinstance(user, dict):
                _decorate_user(user, db)

    chats = result.get("chats") or []
    if isinstance(chats, list):
        for chat in chats:
            if isinstance(chat, dict):
                _decorate_chat(chat, db)

    full_user = result.get("full_user")
    if isinstance(full_user, dict):
        user_id = int(full_user.get("id", 0) or 0)
        row = _profile_row_for_user(user_id, db) if user_id else None
        if row is not None:
            full_user["profile_photo"] = v12._photo_entity(row[1])

    full_chat = result.get("full_chat")
    if isinstance(full_chat, dict):
        chat_id = int(full_chat.get("id", 0) or 0)
        row = _profile_row_for_chat(chat_id, db) if chat_id else None
        if row is not None:
            full_chat["chat_photo"] = v12._photo_entity(row[1])

    return result


def _uploaded_photo(input_file: Any, current_user: User, db: Session) -> StoredFile:
    media = {"_": "inputMediaUploadedPhoto"}
    stored = v12._assemble_uploaded_file(input_file, media, current_user, db)
    stored.kind = "photo"
    if not stored.mime_type.startswith("image/"):
        stored.mime_type = "image/jpeg"
    return stored


def _set_user_photo(current_user: User, stored: StoredFile, db: Session) -> None:
    row = db.scalar(select(ProfilePhoto).where(ProfilePhoto.user_id == current_user.id))
    if row is None:
        db.add(ProfilePhoto(user_id=current_user.id, stored_file_id=stored.id))
    else:
        row.stored_file_id = stored.id
    current_user.avatar_url = f"/uploads/{stored.storage_name}"


def _set_chat_photo(chat: Chat, stored: StoredFile, db: Session) -> None:
    row = db.scalar(select(ProfilePhoto).where(ProfilePhoto.chat_id == chat.id))
    if row is None:
        db.add(ProfilePhoto(chat_id=chat.id, stored_file_id=stored.id))
    else:
        row.stored_file_id = stored.id
    chat.avatar_url = f"/uploads/{stored.storage_name}"


def _remove_user_photo(current_user: User, db: Session) -> None:
    db.execute(delete(ProfilePhoto).where(ProfilePhoto.user_id == current_user.id))
    current_user.avatar_url = None


def _remove_chat_photo(chat: Chat, db: Session) -> None:
    db.execute(delete(ProfilePhoto).where(ProfilePhoto.chat_id == chat.id))
    chat.avatar_url = None


async def _broadcast_user_photo(current_user: User, stored: StoredFile | None, db: Session) -> None:
    chat_ids = list(
        db.scalars(select(ChatMember.chat_id).where(ChatMember.user_id == current_user.id)).all()
    )
    peer_ids: set[int] = set()
    if chat_ids:
        peer_ids = set(
            db.scalars(
                select(ChatMember.user_id)
                .where(ChatMember.chat_id.in_(chat_ids))
                .where(ChatMember.user_id != current_user.id)
            ).all()
        )
    update = {
        "_": "updateUserPhoto",
        "user_id": current_user.id,
        "date": legacy._unix(None),
        "photo": _user_profile_photo(stored) if stored else {"_": "userProfilePhotoEmpty"},
        "pFlags": {},
    }
    for user_id in peer_ids:
        await manager.send_to_user(user_id, {"roof_update": update})


async def _upload_profile_photo(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any]:
    stored = _uploaded_photo(params.get("file"), current_user, db)
    db.flush()
    _set_user_photo(current_user, stored, db)
    db.commit()
    db.refresh(stored)
    await _broadcast_user_photo(current_user, stored, db)
    user = legacy._user(current_user, current_user.id)
    _decorate_user(user, db)
    return {
        "_": "photos.photo",
        "photo": v12._photo_entity(stored),
        "users": [user],
    }


async def _update_profile_photo(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any]:
    photo = params.get("id")
    kind = str(photo.get("_", "")) if isinstance(photo, dict) else ""
    if kind in {"inputPhotoEmpty", "photoEmpty"}:
        _remove_user_photo(current_user, db)
        db.commit()
        await _broadcast_user_photo(current_user, None, db)
        return {"_": "photos.photo", "photo": {"_": "photoEmpty", "id": 0}, "users": []}
    stored = v12._stored_from_reference(photo, current_user, db)
    if stored.kind != "photo":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof avatar must be an image")
    _set_user_photo(current_user, stored, db)
    db.commit()
    await _broadcast_user_photo(current_user, stored, db)
    user = legacy._user(current_user, current_user.id)
    _decorate_user(user, db)
    return {"_": "photos.photo", "photo": v12._photo_entity(stored), "users": [user]}


async def _delete_profile_photos(
    params: dict[str, Any], current_user: User, db: Session
) -> list[int]:
    values = params.get("id") or []
    if not isinstance(values, list):
        values = [values]
    ids = {
        int(value.get("id", 0) or 0)
        for value in values
        if isinstance(value, dict) and int(value.get("id", 0) or 0) > 0
    }
    row = _profile_row_for_user(current_user.id, db)
    if row is None or row[1].id not in ids:
        return []
    removed_id = row[1].id
    _remove_user_photo(current_user, db)
    db.commit()
    await _broadcast_user_photo(current_user, None, db)
    return [removed_id]


def _get_user_photos(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    user_id = legacy._input_user_id(params.get("user_id"), current_user) or current_user.id
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof user not found")
    row = _profile_row_for_user(user.id, db)
    serialized = legacy._user(user, current_user.id)
    _decorate_user(serialized, db)
    return {
        "_": "photos.photos",
        "photos": [v12._photo_entity(row[1])] if row else [],
        "users": [serialized],
    }


def _input_chat_stored_photo(
    value: Any, current_user: User, db: Session
) -> StoredFile | None:
    if not isinstance(value, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof chat photo is required")
    kind = str(value.get("_", ""))
    if kind == "inputChatPhotoEmpty":
        return None
    if kind == "inputChatUploadedPhoto":
        stored = _uploaded_photo(value.get("file"), current_user, db)
        return stored
    if kind == "inputChatPhoto":
        stored = v12._stored_from_reference(value.get("id"), current_user, db)
        if stored.kind != "photo":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Roof chat avatar must be an image")
        return stored
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        f"Unsupported Roof chat photo type: {kind or 'unknown'}",
    )


def _chat_updates(chat: Chat, current_user: User, db: Session) -> dict[str, Any]:
    fresh = v11._load_chat(chat.id, current_user, db)
    entity = v3._channel_entity(fresh) if fresh.type == "channel" else legacy._chat_entity(fresh)
    _decorate_chat(entity, db)
    updates: list[dict[str, Any]] = []
    if fresh.type == "channel":
        updates.append({"_": "updateChannel", "channel_id": fresh.id})
    return {
        "_": "updates",
        "updates": updates,
        "users": [legacy._user(member.user, current_user.id) for member in fresh.members],
        "chats": [entity],
        "date": legacy._unix(None),
        "seq": 0,
    }


async def _edit_group_photo(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any]:
    chat = v11._load_chat(int(params.get("chat_id", 0) or 0), current_user, db)
    if chat.type != "group":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a Roof group")
    v11._require_manager(chat, current_user.id)
    stored = _input_chat_stored_photo(params.get("photo"), current_user, db)
    if stored is None:
        _remove_chat_photo(chat, db)
    else:
        db.flush()
        _set_chat_photo(chat, stored, db)
    db.commit()
    result = _chat_updates(chat, current_user, db)
    await manager.broadcast_chat(chat.id, {"roof_update": {"_": "updateChat", "chat_id": chat.id}})
    return result


async def _edit_channel_photo(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any]:
    channel_id = v3._channel_id(params.get("channel"))
    chat = v11._load_chat(channel_id, current_user, db)
    if chat.type != "channel":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a Roof channel")
    v11._require_manager(chat, current_user.id)
    stored = _input_chat_stored_photo(params.get("photo"), current_user, db)
    if stored is None:
        _remove_chat_photo(chat, db)
    else:
        db.flush()
        _set_chat_photo(chat, stored, db)
    db.commit()
    result = _chat_updates(chat, current_user, db)
    await manager.broadcast_chat(chat.id, {"roof_update": {"_": "updateChannel", "channel_id": chat.id}})
    return result


def _profile_upload_get_file(
    params: dict[str, Any], current_user: User, db: Session
) -> dict[str, Any] | None:
    location = params.get("location")
    if not isinstance(location, dict):
        return None
    try:
        stored_id = int(location.get("id", 0) or 0)
    except (TypeError, ValueError):
        return None
    if stored_id <= 0:
        return None
    profile = db.scalar(
        select(ProfilePhoto.id).where(ProfilePhoto.stored_file_id == stored_id).limit(1)
    )
    if profile is None:
        return None
    stored = db.get(StoredFile, stored_id)
    if stored is None:
        return None
    path = settings.uploads_dir / stored.storage_name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Roof avatar bytes were not found")
    offset = max(0, int(params.get("offset", 0) or 0))
    limit = max(1, min(int(params.get("limit", 512 * 1024) or 512 * 1024), 1024 * 1024))
    with path.open("rb") as source:
        source.seek(offset)
        data = source.read(limit)
    return {
        "_": "upload.file",
        "type": {"_": "storage.fileJpeg"},
        "mtime": legacy._unix(stored.created_at),
        "bytes": v12._bytes_payload(data),
    }


@router.post("/invoke")
async def invoke_v13(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "photos.uploadProfilePhoto":
        return await _upload_profile_photo(params, current_user, db)
    if method == "photos.updateProfilePhoto":
        return await _update_profile_photo(params, current_user, db)
    if method == "photos.deletePhotos":
        return await _delete_profile_photos(params, current_user, db)
    if method == "photos.getUserPhotos":
        return _get_user_photos(params, current_user, db)
    if method == "messages.editChatPhoto":
        return await _edit_group_photo(params, current_user, db)
    if method == "channels.editPhoto":
        return await _edit_channel_photo(params, current_user, db)
    if method == "upload.getFile":
        profile_file = _profile_upload_get_file(params, current_user, db)
        if profile_file is not None:
            return profile_file

    result = await v12.invoke_v12(payload, current_user, db)
    return _decorate_avatar_entities(result, db)
