from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class AdminUserOut(BaseModel):
    id: int
    email: EmailStr
    username: str
    display_name: str
    avatar_url: str | None
    stars: int
    premium_until: datetime | None
    is_premium: bool
    is_verified: bool
    is_admin: bool
    last_seen_at: datetime


class AdminStarsGrant(BaseModel):
    amount: int = Field(ge=1, le=1_000_000_000)


class AdminPremiumGrant(BaseModel):
    days: int = Field(default=30, ge=1, le=3650)


class AdminVerifiedSet(BaseModel):
    verified: bool
