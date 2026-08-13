from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health")
def admin_health() -> dict[str, bool]:
    return {"ok": True}
