from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models import utcnow


DEFAULT_ADMIN_RIGHTS = {
    "change_info": True,
    "delete_messages": True,
    "pin_messages": True,
    "invite_users": True,
    "ban_users": True,
    "add_admins": False,
    "post_messages": True,
    "edit_messages": True,
    "manage_call": False,
}


class ChatAdminRights(Base):
    __tablename__ = "chat_admin_rights"
    __table_args__ = (UniqueConstraint("chat_id", "user_id", name="uq_chat_admin_rights_chat_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rights_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    rank: Mapped[str] = mapped_column(String(32), nullable=False, default="Admin")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def rights(self) -> dict[str, bool]:
        try:
            raw = json.loads(self.rights_json or "{}")
        except json.JSONDecodeError:
            raw = {}
        result = DEFAULT_ADMIN_RIGHTS.copy()
        if isinstance(raw, dict):
            for key in result:
                if key in raw:
                    result[key] = bool(raw[key])
        return result

    def set_rights(self, rights: dict[str, bool]) -> None:
        clean = {key: bool(rights.get(key, False)) for key in DEFAULT_ADMIN_RIGHTS}
        self.rights_json = json.dumps(clean, separators=(",", ":"), sort_keys=True)
