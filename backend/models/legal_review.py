from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from database import Base


class LegalReview(Base):
    __tablename__ = "legal_reviews"

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False, index=True)
    reviewer_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    jurisdiction = Column(String(100), nullable=False)
    jurisdiction_requirements = Column(Text, nullable=False)
    proposed_tokenisation_arrangements = Column(Text, nullable=False)
    token_rights_description = Column(Text, nullable=False)
    legal_risks = Column(Text, nullable=False)
    comments = Column(Text, nullable=False)
    decision = Column(String(40), nullable=False)
    supporting_document_ids = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
