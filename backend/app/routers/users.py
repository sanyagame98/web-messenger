from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import UserPublic

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=list[UserPublic])
def search_users(
    q: str = Query(min_length=1, max_length=64),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[UserPublic]:
    q_norm = q.strip().lower()
    if not q_norm:
        return []
    stmt = (
        select(User)
        .where(User.username.ilike(f"%{q_norm}%"))
        .where(User.id != current_user.id)
        .order_by(User.username)
        .limit(20)
    )
    rows = db.scalars(stmt).all()
    return [UserPublic.model_validate(r) for r in rows]


@router.get("/{username}", response_model=UserPublic)
def get_user_by_username(
    username: str,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    db: Session = Depends(get_db),
) -> UserPublic:
    user = db.scalar(select(User).where(User.username == username.lower()))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return UserPublic.model_validate(user)
