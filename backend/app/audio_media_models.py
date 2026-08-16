from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AudioMediaMeta(Base):
    __tablename__ = "audio_media_meta"

    stored_file_id: Mapped[int] = mapped_column(
        ForeignKey("stored_files.id", ondelete="CASCADE"), primary_key=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    performer: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    waveform_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    duration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_voice: Mapped[bool] = mapped_column(nullable=False, default=False)
