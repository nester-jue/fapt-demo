from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from database import Base


class InvestorCompliance(Base):
    __tablename__ = "investor_compliance"
    __table_args__ = (UniqueConstraint("user_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    kyc_status = Column(String(30), nullable=False, default="NOT_STARTED")
    aml_status = Column(String(30), nullable=False, default="NOT_STARTED")
    identity_verification_status = Column(
        String(30), nullable=False, default="NOT_STARTED"
    )
    eligibility_status = Column(String(30), nullable=False, default="NOT_STARTED")
    is_eligible = Column(Boolean, nullable=False, default=False)
    required_documents = Column(Text, nullable=False, default="[]")
    updated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ComplianceReviewHistory(Base):
    __tablename__ = "compliance_review_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    reviewer_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    decision = Column(String(40), nullable=False)
    comments = Column(Text, nullable=False)
    status_snapshot = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
