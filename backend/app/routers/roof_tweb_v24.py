from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audio_media_models import AudioMediaMeta
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v23 as v23

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _items(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict):
        return []
    values: list[dict[str, Any]] = []
    for item in result.get("messages") or []:
        if isinstance(item, dict):
            values.append(item)
    for update in result.get("updates") or []:
        if isinstance(update, dict) and isinstance(update.get("message"), dict):
            values.append(update["message"])
    return values


def _document_id(item: dict[str, Any]) -> int:
    media = item.get("media")
    if not isinstance(media, dict) or media.get("_") != "messageMediaDocument":
        return 0
    document = media.get("document")
    if not isinstance(document, dict):
        return 0
    return int(document.get("id", 0) or 0)


def _audio_input(media: Any) -> dict[str, Any] | None:
    if not isinstance(media, dict):
        return None
    attrs = media.get("attributes") or []
    if not isinstance(attrs, list):
        return None
    for attr in attrs:
        if isinstance(attr, dict) and attr.get("_") == "documentAttributeAudio":
            return attr
    return None


def _normalize_waveform(value: Any) -> list[int]:
    if isinstance(value, dict) and isinstance(value.get("__roof_bytes_base64"), str):
        return []
    if isinstance(value, (bytes, bytearray)):
        return [int(x) for x in value[:128]]
    if isinstance(value, list):
        return [max(0, min(255, int(x))) for x in value[:128]]
    if isinstance(value, dict):
        numeric: list[tuple[int, int]] = []
        for key, item in value.items():
            if not str(key).isdigit():
                return []
            numeric.append((int(key), max(0, min(255, int(item)))))
        numeric.sort(key=lambda pair: pair[0])
        return [item for _, item in numeric[:128]]
    return []


def _remember_one(item: dict[str, Any], media: Any, db: Session) -> None:
    stored_id = _document_id(item)
    attr = _audio_input(media)
    if stored_id <= 0 or attr is None:
        return
    flags = attr.get("pFlags") if isinstance(attr.get("pFlags"), dict) else {}
    row = db.get(AudioMediaMeta, stored_id)
    if row is None:
        row = AudioMediaMeta(stored_file_id=stored_id)
        db.add(row)
    row.title = str(attr.get("title") or "")[:255]
    row.performer = str(attr.get("performer") or "")[:255]
    row.duration = max(0, int(float(attr.get("duration", 0) or 0)))
    row.is_voice = bool(flags.get("voice"))
    row.waveform_json = json.dumps(_normalize_waveform(attr.get("waveform")), separators=(",", ":"))


def _decorate_one(item: dict[str, Any], db: Session) -> None:
    stored_id = _document_id(item)
    if stored_id <= 0:
        return
    row = db.get(AudioMediaMeta, stored_id)
    if row is None:
        return
    media = item.get("media")
    document = media.get("document") if isinstance(media, dict) else None
    if not isinstance(document, dict):
        return
    attrs = document.get("attributes") or []
    if not isinstance(attrs, list):
        attrs = []
        document["attributes"] = attrs
    attr = next((x for x in attrs if isinstance(x, dict) and x.get("_") == "documentAttributeAudio"), None)
    if attr is None:
        attr = {"_": "documentAttributeAudio", "pFlags": {}}
        attrs.append(attr)
    flags = attr.setdefault("pFlags", {})
    if not isinstance(flags, dict):
        flags = {}
        attr["pFlags"] = flags
    if row.is_voice:
        flags["voice"] = True
    attr["duration"] = row.duration
    if row.title:
        attr["title"] = row.title
    if row.performer:
        attr["performer"] = row.performer
    try:
        waveform = json.loads(row.waveform_json or "[]")
    except json.JSONDecodeError:
        waveform = []
    if waveform:
        attr["waveform"] = waveform


def _decorate(result: Any, db: Session) -> Any:
    for item in _items(result):
        _decorate_one(item, db)
    return result


@router.post("/invoke")
async def invoke_v24(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    result = await v23.invoke_v23(payload, current_user, db)

    if payload.method == "messages.sendMedia":
        items = _items(result)
        if items:
            _remember_one(items[0], payload.params.get("media"), db)
            db.commit()
            return _decorate(result, db)

    if payload.method == "messages.sendMultiMedia":
        values = payload.params.get("multi_media") or []
        if isinstance(values, list):
            for item, value in zip(_items(result), values, strict=False):
                if isinstance(value, dict):
                    _remember_one(item, value.get("media"), db)
            db.commit()
            return _decorate(result, db)

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
        "messages.editMessage",
    }:
        return _decorate(result, db)
    return result
