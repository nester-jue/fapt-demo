from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models.audit_event import AuditEvent
from models.user import User
from schemas.user_admin import (
    ManagedUserResponse,
    UserRoleUpdate,
    UserStatusUpdate,
)
from services.audit import record_audit_event
from services.authorization import SUPER_ADMIN_ROLES, require_roles


router = APIRouter(prefix="/admin/users", tags=["Administrator - User Management"])


def _get_managed_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    return user


def _ensure_another_active_super_admin(
    db: Session,
    target: User,
    *,
    will_remain_super_admin: bool,
) -> None:
    if target.role not in SUPER_ADMIN_ROLES or not target.is_active:
        return
    if will_remain_super_admin:
        return

    active_super_admins = (
        db.query(func.count(User.id))
        .filter(User.role.in_(SUPER_ADMIN_ROLES), User.is_active.is_(True))
        .scalar()
    )
    if active_super_admins <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The last active super administrator cannot be removed.",
        )


@router.get("", response_model=list[ManagedUserResponse])
def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("super_admin")),
):
    return (
        db.query(User)
        .order_by(User.created_at.desc(), User.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.patch("/{user_id}/role", response_model=ManagedUserResponse)
def update_user_role(
    user_id: int,
    role_data: UserRoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("super_admin")),
):
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators cannot change their own role.",
        )

    target = _get_managed_user(db, user_id)
    previous_role = target.role
    if previous_role == role_data.role:
        return target

    _ensure_another_active_super_admin(
        db,
        target,
        will_remain_super_admin=role_data.role == "super_admin",
    )

    target.role = role_data.role
    record_audit_event(
        db,
        user=admin,
        action="USER_ROLE_CHANGED",
        entity_type="user",
        entity_id=target.id,
        request=request,
        previous_value={"role": previous_role},
        new_value={"role": target.role},
    )
    db.commit()
    db.refresh(target)
    return target


@router.patch("/{user_id}/status", response_model=ManagedUserResponse)
def update_user_status(
    user_id: int,
    status_data: UserStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("super_admin")),
):
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators cannot suspend or deactivate themselves.",
        )

    target = _get_managed_user(db, user_id)
    if target.is_active == status_data.is_active:
        return target

    _ensure_another_active_super_admin(
        db,
        target,
        will_remain_super_admin=status_data.is_active,
    )

    previous_status = target.is_active
    target.is_active = status_data.is_active
    record_audit_event(
        db,
        user=admin,
        action="USER_ACTIVATED" if target.is_active else "USER_SUSPENDED",
        entity_type="user",
        entity_id=target.id,
        request=request,
        previous_value={"is_active": previous_status},
        new_value={"is_active": target.is_active},
    )
    db.commit()
    db.refresh(target)
    return target


@router.get("/audit-events")
def list_audit_events(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles("super_admin")),
):
    events = (
        db.query(AuditEvent)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": event.id,
            "user_id": event.user_id,
            "action": event.action,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "previous_value": event.previous_value,
            "new_value": event.new_value,
            "created_at": event.created_at,
        }
        for event in events
    ]
