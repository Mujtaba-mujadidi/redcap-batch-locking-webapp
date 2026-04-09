#!/usr/bin/env python3
import argparse
from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password, normalize_email
from app.db.session import SessionLocal
from app.models.enums import Role
from app.models.user import User


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a bootstrap super admin user.")
    parser.add_argument("--email", required=True, help="Email address for the bootstrap user.")
    parser.add_argument("--full-name", dest="full_name", default=None, help="Optional full name.")
    parser.add_argument(
        "--role",
        choices=[role.value for role in Role],
        default=Role.SUPER_ADMIN.value,
        help="Role for the created account. Defaults to super_admin.",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Password for the account. If omitted, you will be prompted securely.",
    )
    return parser.parse_args()


def get_password(provided_password: str | None) -> str:
    if provided_password:
        password = provided_password
    else:
        password = getpass("Password: ")
        password_confirm = getpass("Confirm password: ")
        if password != password_confirm:
            raise SystemExit("Passwords did not match.")

    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters long.")

    return password


def main() -> None:
    args = parse_args()
    email = normalize_email(args.email)
    password = get_password(args.password)

    db = SessionLocal()
    try:
        existing_user = db.scalar(select(User).where(User.email == email))
        if existing_user is not None:
            raise SystemExit(f"User already exists for email: {email}")

        user = User(
            email=email,
            full_name=args.full_name,
            password_hash=hash_password(password),
            role=Role(args.role),
        )
        db.add(user)
        db.commit()
        print(f"Created {user.role.value} user: {user.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
