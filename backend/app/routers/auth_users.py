from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import audit, security
from app.auth import CurrentUser, Permission, require
from app.config import get_settings
from app.db import get_db
from app.models import Role, User
from app.schemas import DemoUser, LoginResponse, Meta, UserCreate, UserRead

router = APIRouter(tags=["auth"])
DbDep = Annotated[Session, Depends(get_db)]


@router.post("/auth/login", response_model=LoginResponse)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbDep, request: Request
) -> LoginResponse:
    username = form.username.strip().lower()
    key = f"{username}|{request.client.host if request.client else '-'}"
    if (wait := security.login_throttle.retry_after(key)) is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )
    user = db.scalar(select(User).where(User.username == username))
    # Always verify a hash so response time does not reveal whether the username exists.
    stored = user.password_hash if user else security.DUMMY_HASH
    valid = security.verify_password(form.password, stored)
    if user is None or not user.is_active or not valid:
        security.login_throttle.failure(key)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    security.login_throttle.reset(key)
    return LoginResponse(
        access_token=security.create_token(user.username, user.role.value),
        user=UserRead.model_validate(user),
    )


@router.get("/auth/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user


@router.get("/meta", response_model=Meta)
def meta(db: DbDep) -> Meta:
    """Public. In demo mode, lists the demo accounts so visitors can try each role."""
    settings = get_settings()
    if not settings.demo_mode:
        return Meta(demo_mode=False, demo_password=None, demo_users=[])
    users = db.scalars(select(User).where(User.is_active).order_by(User.id)).all()
    return Meta(
        demo_mode=True,
        demo_password=settings.demo_password,
        demo_users=[DemoUser(username=u.username, role=u.role) for u in users],
    )


@router.get("/users", response_model=list[UserRead])
def list_users(
    db: DbDep, _: Annotated[User, Depends(require(Permission.MANAGE_USERS))]
) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)).all())


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: DbDep,
    admin: Annotated[User, Depends(require(Permission.MANAGE_USERS))],
) -> User:
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        role=Role(payload.role),
        password_hash=security.hash_password(payload.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"Username '{payload.username}' is taken"
        ) from exc
    audit.record(
        db,
        "user",
        user.id,
        "create",
        {"username": [None, user.username], "role": [None, user.role.value]},
        actor=admin.username,
    )
    db.commit()
    return user
