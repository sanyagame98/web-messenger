from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.dialog_folder_models import DialogArchiveState, DialogFilterState
from app.models import Chat, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v8 as v8
from app.routers import roof_tweb_v9 as v9
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _archive_state(chat_id: int, user_id: int, db: Session) -> DialogArchiveState | None:
    return db.scalar(
        select(DialogArchiveState).where(
            DialogArchiveState.chat_id == chat_id,
            DialogArchiveState.user_id == user_id,
        )
    )


def _archive_state_or_create(
    chat_id: int,
    user_id: int,
    db: Session,
) -> DialogArchiveState:
    row = _archive_state(chat_id, user_id, db)
    if row is not None:
        return row
    row = DialogArchiveState(chat_id=chat_id, user_id=user_id, folder_id=0)
    db.add(row)
    db.flush()
    return row


def _chat_for_peer(peer: Any, current_user: User, db: Session) -> Chat | None:
    try:
        return v8._resolve_peer(peer, current_user, db)
    except HTTPException:
        return None


def _decorate_archive(
    result: Any,
    current_user: User,
    db: Session,
    requested_folder: int | None = None,
) -> Any:
    if not isinstance(result, dict):
        return result

    kept: list[dict[str, Any]] = []
    for dialog in result.get("dialogs") or []:
        if not isinstance(dialog, dict):
            continue
        chat = _chat_for_peer(dialog.get("peer"), current_user, db)
        if chat is None:
            continue
        state = _archive_state(chat.id, current_user.id, db)
        folder_id = int(state.folder_id if state else 0)
        dialog["folder_id"] = folder_id
        if requested_folder is None or folder_id == requested_folder:
            kept.append(dialog)

    result["dialogs"] = kept
    if requested_folder is not None:
        top_ids = {
            int(dialog.get("top_message", 0) or 0)
            for dialog in kept
            if int(dialog.get("top_message", 0) or 0) > 0
        }
        result["messages"] = [
            item
            for item in result.get("messages") or []
            if isinstance(item, dict) and int(item.get("id", 0) or 0) in top_ids
        ]
    return result


def _decode_filter(row: DialogFilterState) -> dict[str, Any] | None:
    try:
        payload = json.loads(row.payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    payload["id"] = row.filter_id
    return payload


def _get_filters(current_user: User, db: Session) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(DialogFilterState)
            .where(DialogFilterState.user_id == current_user.id)
            .order_by(DialogFilterState.order_index.asc(), DialogFilterState.filter_id.asc())
        ).all()
    )
    filters = [item for row in rows if (item := _decode_filter(row)) is not None]
    return {"_": "messages.dialogFilters", "filters": filters}


async def _update_filter(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> bool:
    filter_id = int(params.get("id", 0) or 0)
    if filter_id < 2:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Roof custom folder id must be 2 or greater",
        )

    payload = params.get("filter")
    row = db.scalar(
        select(DialogFilterState).where(
            DialogFilterState.user_id == current_user.id,
            DialogFilterState.filter_id == filter_id,
        )
    )

    if payload is None:
        if row is not None:
            db.delete(row)
        db.commit()
        update = {"_": "updateDialogFilter", "id": filter_id}
        await manager.send_to_user(current_user.id, {"roof_update": update})
        return True

    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Roof folder payload")

    normalized = dict(payload)
    normalized["id"] = filter_id
    normalized.setdefault("_", "dialogFilter")
    normalized.setdefault("pFlags", {})
    normalized.setdefault("title", {"_": "textWithEntities", "text": "Roof", "entities": []})
    normalized.setdefault("pinned_peers", [])
    normalized.setdefault("include_peers", [])
    normalized.setdefault("exclude_peers", [])

    if row is None:
        max_order = db.scalar(
            select(DialogFilterState.order_index)
            .where(DialogFilterState.user_id == current_user.id)
            .order_by(DialogFilterState.order_index.desc())
            .limit(1)
        )
        row = DialogFilterState(
            user_id=current_user.id,
            filter_id=filter_id,
            order_index=int(max_order or 0) + 1,
            payload=json.dumps(normalized, ensure_ascii=False, separators=(",", ":")),
        )
        db.add(row)
    else:
        row.payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    db.commit()

    update = {"_": "updateDialogFilter", "id": filter_id, "filter": normalized}
    await manager.send_to_user(current_user.id, {"roof_update": update})
    return True


async def _reorder_filters(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> bool:
    raw_order = params.get("order") or []
    if not isinstance(raw_order, list):
        raw_order = [raw_order]
    order = [int(value) for value in raw_order if int(value) >= 2]
    rows = list(
        db.scalars(
            select(DialogFilterState).where(DialogFilterState.user_id == current_user.id)
        ).all()
    )
    by_id = {row.filter_id: row for row in rows}
    next_index = 1
    touched: set[int] = set()
    for filter_id in order:
        row = by_id.get(filter_id)
        if row is None:
            continue
        row.order_index = next_index
        next_index += 1
        touched.add(filter_id)
    for row in sorted(rows, key=lambda item: (item.order_index, item.filter_id)):
        if row.filter_id in touched:
            continue
        row.order_index = next_index
        next_index += 1
    db.commit()
    update = {"_": "updateDialogFilterOrder", "order": order}
    await manager.send_to_user(current_user.id, {"roof_update": update})
    return True


async def _edit_peer_folders(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> dict[str, Any]:
    values = params.get("folder_peers") or []
    if not isinstance(values, list):
        values = [values]
    updates: list[dict[str, Any]] = []

    for value in values:
        if not isinstance(value, dict):
            continue
        peer = value.get("peer")
        chat = _chat_for_peer(peer, current_user, db)
        if chat is None:
            continue
        folder_id = int(value.get("folder_id", 0) or 0)
        if folder_id not in {0, 1}:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Roof archive folder must be 0 or 1",
            )
        row = _archive_state_or_create(chat.id, current_user.id, db)
        row.folder_id = folder_id
        updates.append(
            {
                "_": "folderPeer",
                "peer": v8._peer(chat, current_user),
                "folder_id": folder_id,
            }
        )

    db.commit()
    update = {"_": "updateFolderPeers", "folder_peers": updates, "pts": 0, "pts_count": 0}
    await manager.send_to_user(current_user.id, {"roof_update": update})
    return {
        "_": "updates",
        "updates": [update],
        "users": [legacy._user(current_user, current_user.id)],
        "chats": [],
        "date": legacy._unix(None),
        "seq": 0,
    }


@router.post("/invoke")
async def invoke_v10(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "messages.getDialogFilters":
        return _get_filters(current_user, db)
    if method == "messages.updateDialogFilter":
        return await _update_filter(params, current_user, db)
    if method == "messages.updateDialogFiltersOrder":
        return await _reorder_filters(params, current_user, db)
    if method == "messages.getSuggestedDialogFilters":
        return {"_": "messages.suggestedDialogFilters", "filters": []}
    if method == "folders.editPeerFolders":
        return await _edit_peer_folders(params, current_user, db)

    if method in {"messages.getDialogs", "messages.getPinnedDialogs"}:
        result = await v9.invoke_v9(payload, current_user, db)
        folder_id = int(params.get("folder_id", 0) or 0)
        return _decorate_archive(result, current_user, db, requested_folder=folder_id)
    if method == "messages.getPeerDialogs":
        result = await v9.invoke_v9(payload, current_user, db)
        return _decorate_archive(result, current_user, db)

    return await v9.invoke_v9(payload, current_user, db)
