"""Start-up helpers: demo users and optional first-boot seeding (used by the container)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import security
from app.config import get_settings
from app.db import SessionLocal
from app.models import Hazard, Role, User

DEMO_USERS: list[tuple[str, str, Role]] = [
    ("viewer", "Viola Viewer", Role.VIEWER),
    ("surveyor", "Sam Surveyor (field team)", Role.SURVEYOR),
    ("editor", "Eli Editor (IM officer)", Role.EDITOR),
    ("qa", "Quinn QA Officer", Role.QA_OFFICER),
    ("admin", "Ada Admin", Role.ADMIN),
]


def ensure_demo_users(db: Session) -> int:
    """Create the demo accounts (one per role) if missing. Synthetic; password comes from settings."""
    existing = set(db.scalars(select(User.username)))
    created = 0
    for username, display_name, role in DEMO_USERS:
        if username in existing:
            continue
        db.add(
            User(
                username=username,
                display_name=display_name,
                role=role,
                password_hash=security.hash_password(get_settings().demo_password),
            )
        )
        created += 1
    db.commit()
    return created


def main() -> None:
    """Run before the API starts in a deployed container."""
    settings = get_settings()
    with SessionLocal() as db:
        if settings.demo_mode:
            ensure_demo_users(db)
        if settings.seed_on_empty and not db.scalar(select(func.count()).select_from(Hazard)):
            from app import seed

            seed.seed(db)
            print("Database was empty: loaded synthetic data.")


if __name__ == "__main__":
    main()
