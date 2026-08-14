from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.message_feature_models import DialogPreference
from app.models import Chat, User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v8 as v8
from app.websocket import manager

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _pref(chat_id: int, user_id: int, db: Session) -> DialogPreference | None:
    return db.scalar(
        select(DialogPreference).where(
            DialogPreference.chat_id == chat_id,
            DialogPreference.user_id == user_id,
        )
    )


def _pref_or_create(chat_id: int, user_id: int, db: Session) -> DialogPreference:
    row = _pref(chat_id, user_id, db)
    if row is not None:
        return row
    row = DialogPreference(chat_id=chat_id, user_id=user_id)
    db.add(row)
    db.flush()
    return row


def _notify_settings(row: DialogPreference | None) -> dict[str, Any]:
    flags: dict[str, bool] = {}
    if row is not None:
        if row.show_previews:
            flags["show_previews"] = True
        if row.silent:
            flags["silent"] = True
    return {
        "_": "peerNotifySettings",
        "mute_until": row.mute_until if row else 0,
        "pFlags": flags,
    }


def _unwrap_notify_peer(value: Any) -> Any:
    if isinstance(value, dict) and value.get("_") in {
        "inputNotifyPeer",
        "inputNotifyForumTopic",
    }:
        return value.get("peer")
    return value


def _chat_for_dialog_peer(peer: Any, current_user: User, db: Session) -> Chat | None:
    try:
        return v8._resolve_peer(peer, current_user, db)
    except HTTPException:
        return None


def _decorate_dialogs(
    result: Any,
    current_user: User,
    db: Session,
    only_pinned: bool = False,
) -> Any:
    if not isinstance(result, dict):
        return result
    decorated: list[tuple[int, int, dict[str, Any]]] = []
    for dialog in result.get("dialogs") or []:
        if not isinstance(dialog, dict):
            continue
        chat = _chat_for_dialog_peer(dialog.get("peer"), current_user, db)
        if chat is None:
            continue
        row = _pref(chat.id, current_user.id, db)
        pinned = bool(row and row.pinned)
        flags = dialog.setdefault("pFlags", {})
        if isinstance(flags, dict):
            if pinned:
                flags["pinned"] = True
            else:
                flags.pop("pinned", None)
        dialog["notify_settings"] = _notify_settings(row)
        if only_pinned and not pinned:
            continue
        decorated.append(
            (
                row.pin_order if pinned and row else 0,
                int(dialog.get("top_message", 0) or 0),
                dialog,
            )
        )

    decorated.sort(
        key=lambda item: (bool(item[0]), item[0], item[1]),
        reverse=True,
    )
    result["dialogs"] = [item[2] for item in decorated]

    if only_pinned:
        top_ids = {
            int(dialog.get("top_message", 0) or 0)
            for dialog in result["dialogs"]
        }
        result["messages"] = [
            message
            for message in result.get("messages") or []
            if isinstance(message, dict) and int(message.get("id", 0) or 0) in top_ids
        ]
    return result


async def _toggle_pin(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> bool:
    chat = v8._resolve_peer(params.get("peer"), current_user, db)
    row = _pref_or_create(chat.id, current_user.id, db)
    if "pinned" in params:
        pinned = bool(params.get("pinned"))
    else:
        pinned = not row.pinned
    row.pinned = pinned
    if pinned:
        highest = db.scalar(
            select(DialogPreference.pin_order)
            .where(
                DialogPreference.user_id == current_user.id,
                DialogPreference.pinned.is_(True),
            )
            .order_by(DialogPreference.pin_order.desc())
            .limit(1)
        )
        row.pin_order = int(highest or 0) + 1
    else:
        row.pin_order = 0
    db.commit()

    update = {
        "_": "updateDialogPinned",
        "peer": {"_": "dialogPeer", "peer": v8._peer(chat, current_user)},
        "folder_id": int(params.get("folder_id", 0) or 0),
        "pFlags": {"pinned": True} if pinned else {},
    }
    await manager.send_to_user(current_user.id, {"roof_update": update})
    return True


async def _reorder_pins(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> bool:
    order = params.get("order") or []
    if not isinstance(order, list):
        order = [order]
    score = len(order)
    touched: set[int] = set()
    for peer in order:
        try:
            chat = v8._resolve_peer(peer, current_user, db)
        except HTTPException:
            continue
        row = _pref_or_create(chat.id, current_user.id, db)
        row.pinned = True
        row.pin_order = score
        touched.add(chat.id)
        score -= 1

    rows = list(
        db.scalars(
            select(DialogPreference).where(
                DialogPreference.user_id == current_user.id,
                DialogPreference.pinned.is_(True),
            )
        ).all()
    )
    for row in rows:
        if row.chat_id not in touched:
            row.pinned = False
            row.pin_order = 0
    db.commit()
    return True


def _get_notify(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    peer = _unwrap_notify_peer(params.get("peer"))
    if not isinstance(peer, dict):
        return _notify_settings(None)
    chat = v8._resolve_peer(peer, current_user, db)
    return _notify_settings(_pref(chat.id, current_user.id, db))


async def _update_notify(
    params: dict[str, Any],
    current_user: User,
    db: Session,
) -> bool:
    peer = _unwrap_notify_peer(params.get("peer"))
    if not isinstance(peer, dict):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Roof requires a peer for notification settings",
        )
    chat = v8._resolve_peer(peer, current_user, db)
    settings = params.get("settings") or {}
    if not isinstance(settings, dict):
        settings = {}
    flags = settings.get("pFlags") or {}
    if not isinstance(flags, dict):
        flags = {}

    row = _pref_or_create(chat.id, current_user.id, db)
    if "mute_until" in settings:
        row.mute_until = max(0, int(settings.get("mute_until", 0) or 0))
    if "show_previews" in flags:
        row.show_previews = bool(flags.get("show_previews"))
    if "silent" in flags:
        row.silent = bool(flags.get("silent"))
    db.commit()

    update = {
        "_": "updateNotifySettings",
        "peer": {"_": "notifyPeer", "peer": v8._peer(chat, current_user)},
        "notify_settings": _notify_settings(row),
    }
    await manager.send_to_user(current_user.id, {"roof_update": update})
    return True


@router.post("/invoke")
async def invoke_v9(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "messages.toggleDialogPin":
        return await _toggle_pin(params, current_user, db)
    if method == "messages.reorderPinnedDialogs":
        return await _reorder_pins(params, current_user, db)
    if method == "account.getNotifySettings":
        return _get_notify(params, current_user, db)
    if method == "account.updateNotifySettings":
        return await _update_notify(params, current_user, db)

    if method == "messages.getPinnedDialogs":
        result = await v8.invoke_v8(payload, current_user, db)
        return _decorate_dialogs(result, current_user, db, only_pinned=True)
    if method in {"messages.getDialogs", "messages.getPeerDialogs"}:
        result = await v8.invoke_v8(payload, current_user, db)
        return _decorate_dialogs(result, current_user, db)

    return await v8.invoke_v8(payload, current_user, db)
