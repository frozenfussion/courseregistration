"""Create the admin account, or change its password:  python -m scripts.create_admin [username]

The password is typed at a hidden prompt, so it never appears in shell history or in any file.
"""
import getpass
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AdminUser
from app.security import hash_password

MIN_LENGTH = 12


def upsert_admin(username: str, password: str) -> str:
    """Create the admin or update the password. Returns 'created' or 'updated'."""
    with SessionLocal() as db:
        admin = db.scalar(select(AdminUser).where(AdminUser.username == username))
        if admin is None:
            db.add(AdminUser(username=username, password_hash=hash_password(password)))
            result = "created"
        else:
            admin.password_hash = hash_password(password)
            result = "updated"
        db.commit()
        return result


def main() -> int:
    username = sys.argv[1] if len(sys.argv) > 1 else input("Admin username: ").strip()
    if not username:
        print("A username is required.")
        return 1
    password = getpass.getpass(f"Password for {username} (at least {MIN_LENGTH} characters): ")
    if len(password) < MIN_LENGTH:
        print(f"That password is too short. Use at least {MIN_LENGTH} characters.")
        return 1
    if password != getpass.getpass("Type it again: "):
        print("The passwords do not match.")
        return 1
    print(f"Admin '{username}' {upsert_admin(username, password)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
