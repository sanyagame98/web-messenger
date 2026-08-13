from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.admin_schemas import AdminPremiumGrant, AdminStarsGrant, AdminUserOut, AdminVerifiedSet
from app.database import get_db
from app.deps import get_admin_user
from app.models import AdminGrantLog, User, UserEntitlement

router = APIRouter(prefix="/admin", tags=["admin"])


def _entitlement(user: User, db: Session) -> UserEntitlement:
    if user.entitlement is None:
        user.entitlement = UserEntitlement(user_id=user.id)
        db.flush()
    return user.entitlement


def _admin_user(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        avatar_url=user.avatar_url,
        stars=user.stars,
        premium_until=user.premium_until,
        is_premium=user.is_premium,
        is_verified=user.is_verified,
        is_admin=user.is_admin,
        last_seen_at=user.last_seen_at,
    )


def _audit(db: Session, admin: User, target: User, action: str, details: str) -> None:
    db.add(
        AdminGrantLog(
            admin_id=admin.id,
            target_user_id=target.id,
            action=action,
            details=details,
        )
    )


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    q: str = Query(default="", max_length=100),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> list[AdminUserOut]:
    del admin
    stmt = select(User).order_by(User.id.desc())
    query = q.strip().lower().lstrip("@")
    if query:
        like = f"%{query}%"
        stmt = stmt.where(
            or_(User.email.ilike(like), User.username.ilike(like), User.display_name.ilike(like))
        )
    return [_admin_user(user) for user in db.scalars(stmt).all()]


@router.post("/users/{user_id}/stars", response_model=AdminUserOut)
def grant_stars(
    user_id: int,
    payload: AdminStarsGrant,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    ent = _entitlement(target, db)
    ent.stars += payload.amount
    _audit(db, admin, target, "grant_roof_stars", str(payload.amount))
    db.commit()
    db.refresh(target)
    return _admin_user(target)


@router.post("/users/{user_id}/premium", response_model=AdminUserOut)
def grant_premium(
    user_id: int,
    payload: AdminPremiumGrant,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    ent = _entitlement(target, db)
    now = datetime.now(UTC)
    base = ent.premium_until
    if base is not None and base.tzinfo is None:
        base = base.replace(tzinfo=UTC)
    if base is None or base < now:
        base = now
    ent.premium_until = base + timedelta(days=payload.days)
    _audit(db, admin, target, "gift_roof_premium", f"{payload.days} days")
    db.commit()
    db.refresh(target)
    return _admin_user(target)


@router.delete("/users/{user_id}/premium", response_model=AdminUserOut)
def revoke_premium(
    user_id: int,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    ent = _entitlement(target, db)
    ent.premium_until = None
    _audit(db, admin, target, "revoke_roof_premium", "")
    db.commit()
    db.refresh(target)
    return _admin_user(target)


@router.post("/users/{user_id}/verified", response_model=AdminUserOut)
def set_verified(
    user_id: int,
    payload: AdminVerifiedSet,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
) -> AdminUserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    ent = _entitlement(target, db)
    ent.verified = payload.verified
    _audit(db, admin, target, "set_official_badge", str(payload.verified).lower())
    db.commit()
    db.refresh(target)
    return _admin_user(target)
