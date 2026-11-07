from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models.audit_event import AuditEvent
from models.user import User
from schemas.user import UserRegister, UserLogin, UserResponse, TokenResponse
from services.audit import record_audit_event
from services.authorization import require_roles
from services.auth import (
    _DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from services.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])
LOGIN_FAILURE_LIMIT = 10
LOGIN_FAILURE_WINDOW = timedelta(minutes=15)
LOGIN_RETRY_AFTER_SECONDS = int(LOGIN_FAILURE_WINDOW.total_seconds())


def _recent_login_failures(db: Session, request: Request) -> int:
    client_ip = request.client.host if request.client else None
    query = db.query(func.count(AuditEvent.id)).filter(
        AuditEvent.action.in_(
            ["LOGIN_ATTEMPT_FAILED", "LOGIN_ATTEMPT_BLOCKED"]
        ),
        AuditEvent.created_at
        >= datetime.now(timezone.utc) - LOGIN_FAILURE_WINDOW,
    )
    if client_ip is None:
        query = query.filter(AuditEvent.ip_address.is_(None))
    else:
        query = query.filter(AuditEvent.ip_address == client_ip)
    return query.scalar() or 0


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register_user(
    user_data: UserRegister,
    request: Request,
    db: Session = Depends(get_db),
):
    email = str(user_data.email).lower()

    existing_user = db.query(User).filter(
        User.email == email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists."
        )

    new_user = User(
        full_name=user_data.full_name,
        email=email,
        hashed_password=hash_password(user_data.password),
        role=user_data.role,
        is_active=True
    )

    try:
        db.add(new_user)
        db.flush()
        record_audit_event(
            db,
            user=new_user,
            action="USER_REGISTERED",
            entity_type="user",
            entity_id=new_user.id,
            request=request,
            new_value={"role": new_user.role, "is_active": new_user.is_active},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from None
    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=TokenResponse)
def login_user(
    login_data: UserLogin,
    request: Request,
    db: Session = Depends(get_db)
):
    if _recent_login_failures(db, request) >= LOGIN_FAILURE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(LOGIN_RETRY_AFTER_SECONDS)},
        )

    email = str(login_data.email).lower()

    user = db.query(User).filter(
        User.email == email
    ).first()

    password_is_valid = verify_password(
        login_data.password,
        user.hashed_password if user else _DUMMY_PASSWORD_HASH,
    )
    if not user or not password_is_valid:
        record_audit_event(
            db,
            user=user,
            action="LOGIN_ATTEMPT_FAILED",
            entity_type="authentication",
            entity_id=None,
            request=request,
            details={"outcome": "FAILURE"},
        )
        db.commit()
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    if not user.is_active:
        record_audit_event(
            db,
            user=user,
            action="LOGIN_ATTEMPT_BLOCKED",
            entity_type="authentication",
            entity_id=user.id,
            request=request,
            details={"outcome": "INACTIVE_ACCOUNT"},
        )
        db.commit()
        raise HTTPException(
            status_code=403,
            detail="This account has been deactivated."
        )

    record_audit_event(
        db,
        user=user,
        action="LOGIN_SUCCEEDED",
        entity_type="authentication",
        entity_id=user.id,
        request=request,
        details={"outcome": "SUCCESS"},
    )
    db.commit()
    token = create_access_token(user.id)

    return {
        "access_token": token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserResponse)
def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user


def require_admin(
    current_user: User = Depends(require_roles("super_admin")),
):
    return current_user
