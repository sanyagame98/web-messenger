from __future__ import annotations

import getpass

from sqlalchemy import select

from app.admin_policy import ADMIN_EMAIL
from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.models import User


def main() -> None:
    Base.metadata.create_all(bind=engine)
    password = getpass.getpass(f"New password for {ADMIN_EMAIL}: ")
    if len(password) < 6:
        raise SystemExit("Password must be at least 6 characters")
    confirm = getpass.getpass("Repeat password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if user is None:
            username = "roof_owner"
            n = 1
            while db.scalar(select(User.id).where(User.username == username)) is not None:
                n += 1
                username = f"roof_owner_{n}"
            user = User(
                email=ADMIN_EMAIL,
                username=username,
                display_name="Roof Owner",
                password_hash=hash_password(password),
            )
            db.add(user)
            action = "created"
        else:
            user.password_hash = hash_password(password)
            action = "password updated"
        db.commit()
        db.refresh(user)
        print(f"Admin {action}: {user.email} (@{user.username}, id={user.id})")


if __name__ == "__main__":
    main()
