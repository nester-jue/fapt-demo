from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models.notification import Notification
from models.user import User
from routes.auth import get_current_user


router = APIRouter(prefix="/notifications", tags=["In-app Notifications"])


@router.get("")
def list_notifications(
    unread_only: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    rows = query.order_by(Notification.created_at.desc(), Notification.id.desc())
    notifications = rows.offset(skip).limit(limit).all()
    return {
        "items": [
            {
                "id": item.id,
                "event_type": item.event_type,
                "message": item.message,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "is_read": item.is_read,
                "created_at": item.created_at,
            }
            for item in notifications
        ],
        "unread_count": query.filter(Notification.is_read.is_(False)).count(),
    }


@router.post("/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .with_for_update()
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    notification.is_read = True
    db.commit()
    return {"id": notification.id, "is_read": notification.is_read}
