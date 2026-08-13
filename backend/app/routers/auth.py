from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin_policy import is_admin_email
from app.auth import create_access_token, hash_password, verify_password
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import TokenResponse, UserCreate, UserLogin, UserMe, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"])


def _make_username(email: str, db: Session) -> str:
    local = email.split("@", 1)[0].lower()
    base = re.sub(r"[^a-z0-9_]", "_", local).strip("_")
    if len(base) < 4:
        base = f"roof_{base}" if base else "roof_user"
    base = base[:24]
    candidate = base
    suffix = 1
    while db.scalar(select(User.id).where(User.username == candidate)) is not None:
        suffix_text = str(suffix)
        candidate = f"{base[: 31 - len(suffix_text)]}_{suffix_text}"
        suffix += 1
    return candidate


@router.post("/register", response_model=TokenResponse)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()
    if is_admin_email(email):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "The Roof administrator account is created from the server console",
        )
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    username = _make_username(email, db)
    user = User(
        email=email,
        username=username,
        display_name=email.split("@", 1)[0][:64],
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserMe.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return TokenResponse(
        access_token=create_access_token(user.id),
        user=UserMe.model_validate(user),
    )


@router.get("/me", response_model=UserMe)
def me(current_user: User = Depends(get_current_user)) -> UserMe:
    return UserMe.model_validate(current_user)


@router.patch("/me", response_model=UserMe)
def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserMe:
    if payload.username is not None and payload.username != current_user.username:
        taken = db.scalar(select(User.id).where(User.username == payload.username))
        if taken is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
        current_user.username = payload.username
    if payload.display_name is not None:
        current_user.display_name = payload.display_name.strip()
    if payload.bio is not None:
        current_user.bio = payload.bio.strip()
    db.commit()
    db.refresh(current_user)
    return UserMe.model_validate(current_user)
