from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.sql import func

from database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_type = Column(String(80), nullable=False, index=True)
    message = Column(Text, nullable=False)
    entity_type = Column(String(80), nullable=True)
    entity_id = Column(String(100), nullable=True)
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PropertyManagerAssignment(Base):
    __tablename__ = "property_manager_assignments"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    manager_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    assigned_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PropertyManagementRecord(Base):
    __tablename__ = "property_management_records"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    manager_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    record_type = Column(String(40), nullable=False, index=True)
    description = Column(Text, nullable=False)
    amount = Column(Numeric(18, 2), nullable=True)
    currency = Column(String(10), nullable=True)
    document_ids = Column(Text, nullable=False, default="[]")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
