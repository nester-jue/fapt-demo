from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from database import Base


class PropertyVerification(Base):
    __tablename__ = "property_verifications"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    verifier_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    decision = Column(String(40), nullable=False)
    comments = Column(Text, nullable=False)
    previous_status = Column(String(50), nullable=False)
    new_status = Column(String(50), nullable=False)
    supporting_references = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
