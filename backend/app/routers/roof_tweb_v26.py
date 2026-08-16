from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.chat_meta_models import ChatMeta
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.routers import roof_tweb as legacy
from app.routers import roof_tweb_v11 as v11
from app.routers import roof_tweb_v13 as v13
from app.routers import roof_tweb_v17 as v17
from app.routers import roof_tweb_v25 as v25

router = APIRouter(prefix="/roof", tags=["roof-tweb"])


def _full_group(params: dict[str, Any], current_user: User, db: Session) -> dict[str, Any]:
    chat = v17._load_chat(v17._chat_id(params.get("chat_id")), current_user, db)
    result = v11._full_group(chat, current_user)
    meta = v17._meta(chat, db)
    assert meta is not None
    result["full_chat"]["about"] = meta.about
    result["full_chat"]["exported_invite"] = {
        "_": "chatInviteExported",
        "link": f"roof://join/{meta.invite_code}",
        "admin_id": current_user.id,
        "date": legacy._unix(chat.created_at),
        "pFlags": {"permanent": True},
    }
    result["chats"] = [v17._chat_entity(chat, db)]
    return v13._decorate_avatar_entities(result, db)


def _repair_direct_posting_mode(params: dict[str, Any], current_user: User, db: Session) -> None:
    peer = params.get("peer")
    if not isinstance(peer, dict) or str(peer.get("_", "")) not in {"inputPeerUser", "peerUser"}:
        return
    chat = legacy._resolve_peer(peer, current_user, db)
    if chat.type != "direct":
        return
    meta = db.get(ChatMeta, chat.id)
    if meta is not None and meta.posting_mode != "all":
        meta.posting_mode = "all"
        db.commit()


@router.post("/invoke")
async def invoke_v26(
    payload: legacy.RoofInvokeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    method = payload.method
    params = payload.params

    if method == "messages.getFullChat":
        return _full_group(params, current_user, db)

    if method in {"messages.sendMessage", "messages.sendMedia", "messages.sendMultiMedia"}:
        _repair_direct_posting_mode(params, current_user, db)

    result = await v25.invoke_v25(payload, current_user, db)

    if method in {
        "messages.getDialogs",
        "messages.getPinnedDialogs",
        "messages.getPeerDialogs",
        "channels.getChannels",
        "channels.getFullChannel",
    }:
        return v13._decorate_avatar_entities(result, db)

    return result
