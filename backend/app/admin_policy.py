from __future__ import annotations

ADMIN_EMAIL = "nadone229@gmail.com"


def is_admin_email(email: str) -> bool:
    return email.strip().lower() == ADMIN_EMAIL
