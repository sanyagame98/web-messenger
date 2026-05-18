from __future__ import annotations

import secrets
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.config import settings
from app.deps import get_current_user
from app.models import User
from app.schemas import FileUploadResponse

router = APIRouter(prefix="/files", tags=["files"])

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
EXT_MAP = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


@router.post("/image", response_model=FileUploadResponse)
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> FileUploadResponse:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported image type: {file.content_type}",
        )
    max_bytes = settings.max_upload_mb * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File too large (>{settings.max_upload_mb} MB)",
        )
    ext = EXT_MAP.get(file.content_type or "", "")
    name = f"{secrets.token_urlsafe(16)}{ext}"
    target: Path = settings.uploads_dir / name
    async with aiofiles.open(target, "wb") as f:
        await f.write(contents)
    return FileUploadResponse(url=f"/uploads/{name}")
