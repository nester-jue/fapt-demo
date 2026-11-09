from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.sql import func

from database import Base


class PropertyDocument(Base):
    __tablename__ = "property_documents"
    __table_args__ = (
        CheckConstraint("file_size > 0", name="check_property_document_size"),
    )

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    uploaded_by_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    document_type = Column(String(40), nullable=False, default="PROPERTY_SUPPORT")
    storage_key = Column(String(80), unique=True, nullable=False)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
