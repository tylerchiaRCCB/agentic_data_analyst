"""Seed or reset an admin user: python -m app.create_admin <username>"""

import getpass
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.security.passwords import hash_password, validate_new_password


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m app.create_admin <username>")
        raise SystemExit(1)
    username = sys.argv[1].strip().lower()
    password = getpass.getpass(f"Password for {username!r}: ")
    if err := validate_new_password(password):
        print(err)
        raise SystemExit(1)
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username, display_name=username)
            db.add(user)
            action = "created"
        else:
            action = "updated"
        user.password_hash = hash_password(password)
        user.role = "admin"
        user.is_active = True
        db.commit()
        print(f"Admin user {username!r} {action}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
