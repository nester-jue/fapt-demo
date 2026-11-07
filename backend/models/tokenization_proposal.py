from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from database import Base


class TokenizationProposal(Base):
    __tablename__ = "tokenization_proposals"
    __table_args__ = (UniqueConstraint("asset_id"),)

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(
        Integer, ForeignKey("assets.id"), nullable=False, index=True
    )
    submitted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_name = Column(String(150), nullable=False)
    token_symbol = Column(String(20), nullable=False)
    token_price = Column(Numeric(18, 8), nullable=False)
    total_supply = Column(Numeric(28, 8), nullable=False)
    decimal_precision = Column(Integer, nullable=False)
    currency = Column(String(10), nullable=False)
    minimum_investment = Column(Numeric(18, 2), nullable=False)
    maximum_investment = Column(Numeric(18, 2), nullable=True)
    issuance_date = Column(Date, nullable=False)
    issuance_terms = Column(Text, nullable=False)
    restrictions = Column(Text, nullable=False)
    disclosures = Column(Text, nullable=False)
    proposed_tokenisation_arrangements = Column(Text, nullable=False)
    token_rights_description = Column(Text, nullable=False)
    status = Column(String(40), nullable=False, default="PENDING_REVIEW")
    review_comments = Column(Text, nullable=True)
    reviewed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TokenizationApproval(Base):
    __tablename__ = "tokenization_approvals"
    __table_args__ = (UniqueConstraint("approval_ref"),)

    id = Column(Integer, primary_key=True, index=True)
    approval_ref = Column(String(40), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    responsible_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stage = Column(String(40), nullable=False, index=True)
    decision = Column(String(40), nullable=False)
    comments = Column(Text, nullable=False)
    supporting_document_ids = Column(Text, nullable=False, default="[]")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
