"""Authentication and role-based permissions.

Reads of the hazard database are public (anonymous visitors can browse the map and
dashboard); every write needs a login, and each role carries only the permissions it needs.
Field reports are the exception: they are unverified and may name informants, so only
their author and staff with VIEW_REPORTS can read them. Data entry (editor) is kept
separate from quality assurance and release (qa_officer): nobody who enters or clears data
can sign it off, which is the point of QA. Admin holds everything.
"""

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.db import get_db
from app.models import Role, User


class Permission(StrEnum):
    WRITE = "write"  # create/update hazards, tasks, clearance records
    IMPORT = "import"  # bulk import
    QA = "qa"  # record QA/QC inspections
    RELEASE = "release"  # move a hazard to 'released'
    DELETE = "delete"  # delete records
    MANAGE_USERS = "manage_users"
    REPORT = "report"  # submit field reports
    VIEW_REPORTS = "view_reports"  # see every field report (not only your own)


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(),
    Role.SURVEYOR: frozenset({Permission.REPORT}),
    Role.EDITOR: frozenset(
        {Permission.WRITE, Permission.IMPORT, Permission.REPORT, Permission.VIEW_REPORTS}
    ),
    Role.QA_OFFICER: frozenset({Permission.QA, Permission.RELEASE, Permission.VIEW_REPORTS}),
    Role.ADMIN: frozenset(Permission),
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)
DbDep = Annotated[Session, Depends(get_db)]


def has_permission(user: User, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[user.role]


def get_current_user(
    db: DbDep, token: Annotated[str | None, Depends(oauth2_scheme)]
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Login required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized
    payload = security.decode_token(token)
    username = payload.get("sub") if payload else None
    if not isinstance(username, str):
        raise unauthorized
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require(permission: Permission) -> Callable[..., User]:
    """Dependency factory: the caller must be logged in and hold `permission`."""

    def dependency(user: CurrentUser) -> User:
        ensure(user, permission)
        return user

    return dependency


def ensure(user: User, permission: Permission, what: str | None = None) -> None:
    if not has_permission(user, permission):
        action = what or f"'{permission.value}' actions"
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=f"Role '{user.role.value}' may not perform {action}"
        )
