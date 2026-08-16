from __future__ import annotations

import hashlib
import io
import os
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.deps import get_current_user
from app.models import User

router = APIRouter(prefix="/premium-emoji", tags=["premium-emoji"])

PACKS_DIR = Path(os.environ.get("PREMIUM_EMOJI_PACKS_DIR", "/app/premium-emoji-packs"))
MAX_TGS_BYTES = 8 * 1024 * 1024


def _pack_id(path: Path) -> str:
    digest = hashlib.sha1(path.name.encode("utf-8")).hexdigest()[:12]
    return f"pack_{digest}"


def _emoji_id(pack_id: str, member: str) -> str:
    digest = hashlib.sha1(f"{pack_id}:{member}".encode("utf-8")).hexdigest()[:16]
    return f"emoji_{digest}"


def _safe_zip(path: Path) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid emoji ZIP: {path.name}") from exc


def _iter_pack_files() -> list[Path]:
    if not PACKS_DIR.exists():
        return []
    return sorted(
        (p for p in PACKS_DIR.iterdir() if p.is_file() and p.suffix.lower() == ".zip"),
        key=lambda p: p.name.lower(),
    )


def _manifest_for(path: Path) -> dict[str, Any]:
    pack_id = _pack_id(path)
    emojis: list[dict[str, Any]] = []
    with _safe_zip(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".tgs"):
                continue
            if info.file_size <= 0 or info.file_size > MAX_TGS_BYTES:
                continue
            member = info.filename.replace("\\", "/")
            name = Path(member).stem
            emoji_id = _emoji_id(pack_id, member)
            emojis.append(
                {
                    "id": emoji_id,
                    "name": name,
                    "member": member,
                    "status_token": f"roof-tgs:{pack_id}:{emoji_id}",
                    "url": f"/api/premium-emoji/packs/{pack_id}/items/{emoji_id}.tgs",
                }
            )

    return {
        "id": pack_id,
        "title": path.stem,
        "file_name": path.name,
        "count": len(emojis),
        "emojis": emojis,
    }


def _find_pack(pack_id: str) -> Path:
    for path in _iter_pack_files():
        if _pack_id(path) == pack_id:
            return path
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Premium emoji pack not found")


def _find_member(path: Path, pack_id: str, emoji_id: str) -> tuple[str, bytes]:
    with _safe_zip(path) as archive:
        for info in archive.infolist():
            member = info.filename.replace("\\", "/")
            if info.is_dir() or not member.lower().endswith(".tgs"):
                continue
            if _emoji_id(pack_id, member) != emoji_id:
                continue
            if info.file_size <= 0 or info.file_size > MAX_TGS_BYTES:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Premium emoji is too large")
            return member, archive.read(info)
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Premium emoji not found")


@router.get("/packs")
def list_packs(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    del current_user
    packs = [_manifest_for(path) for path in _iter_pack_files()]
    return {
        "packs": packs,
        "total_packs": len(packs),
        "total_emojis": sum(pack["count"] for pack in packs),
    }


@router.get("/packs/{pack_id}/items/{emoji_id}.tgs")
def get_tgs(pack_id: str, emoji_id: str) -> StreamingResponse:
    # LottieLoader performs a plain fetch() without Roof's Authorization header.
    # These assets live only on the user's localhost and use hashed pack/item ids.
    path = _find_pack(pack_id)
    member, payload = _find_member(path, pack_id, emoji_id)
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{Path(member).name}"',
        },
    )
