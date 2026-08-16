from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models import utcnow


class ChatMeta(Base):
    __tablename__ = "chat_meta"

    chat_id: Mapped[int] = mapped_column(
        ForeignKey("chats.id", ondelete="CASCADE"), primary_key=True
    )
    about: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    username: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    invite_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    comments_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hide_members: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    history_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    posting_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="all")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
