from __future__ import annotations

import argparse
import re

from app.atlas_platform.database import SessionLocal
from app.atlas_platform.models import Membership, Organization, Role, User
from app.atlas_platform.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an owner in the canonical ATLAS platform schema.",
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--full-name", default="Platform Administrator")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Replace the password if the user already exists.",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    organization_name = args.organization.strip()
    slug = re.sub(r"[^a-z0-9]+", "-", organization_name.lower()).strip("-")
    if not slug:
        raise SystemExit("The organization name does not produce a valid slug.")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).one_or_none()
        if user is None:
            user = User(
                email=email,
                full_name=args.full_name.strip(),
                password_hash=hash_password(args.password),
                is_active=True,
            )
            db.add(user)
        else:
            user.full_name = args.full_name.strip()
            user.is_active = True
            if args.reset_password:
                user.password_hash = hash_password(args.password)
        db.flush()

        organization = (
            db.query(Organization)
            .filter(Organization.slug == slug)
            .one_or_none()
        )
        if organization is None:
            organization = Organization(name=organization_name, slug=slug)
            db.add(organization)
            db.flush()

        membership = (
            db.query(Membership)
            .filter(
                Membership.organization_id == organization.id,
                Membership.user_id == user.id,
            )
            .one_or_none()
        )
        if membership is None:
            db.add(
                Membership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role=Role.OWNER.value,
                )
            )
        else:
            membership.role = Role.OWNER.value

        db.commit()
        print(f"Canonical owner ready: {email} / {organization.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
