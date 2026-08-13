from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{4,32}$")


def _validate_username(value: str) -> str:
    value = value.strip()
    if not USERNAME_RE.fullmatch(value):
        raise ValueError("Username must be 4-32 characters, only letters, digits and underscores")
    return value.lower()


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    bio: str
    avatar_url: str | None
    last_seen_at: datetime
    is_premium: bool = False
    is_verified: bool = False


class UserMe(UserPublic):
    email: EmailStr
    stars: int = 0
    premium_until: datetime | None = None
    is_admin: bool = False


class UserUpdate(BaseModel):
    username: str | None = None
    display_name: str | None = Field(default=None, max_length=64)
    bio: str | None = Field(default=None, max_length=280)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str | None) -> str | None:
        return _validate_username(v) if v is not None else None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserMe


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


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    sender_id: int | None
    type: str
    content: str
    image_url: str | None
    edited: bool
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(default="", max_length=4000)
    image_url: str | None = None

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        return v.strip()


class ChatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    name: str
    avatar_url: str | None
    created_at: datetime
    members: list[UserPublic]
    last_message: MessageOut | None = None
    unread_count: int = 0


class ChatCreateDirect(BaseModel):
    username: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        return _validate_username(v)


class ChatCreateGroup(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    member_usernames: list[str] = Field(default_factory=list)

    @field_validator("member_usernames")
    @classmethod
    def validate_members(cls, v: list[str]) -> list[str]:
        return [_validate_username(u) for u in v]


class ReadReceipt(BaseModel):
    message_id: int


class FileUploadResponse(BaseModel):
    url: str
