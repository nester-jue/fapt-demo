from sqlalchemy import (
    Column,
    Date,
    Integer,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Text,
)
from sqlalchemy.sql import func

from database import Base


class TokenIssuance(Base):
    __tablename__ = "token_issuances"

    __table_args__ = (
        CheckConstraint(
            "token_price > 0",
            name="check_token_price_positive"
        ),
        CheckConstraint(
            "total_supply > 0",
            name="check_total_supply_positive"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    asset_id = Column(
        Integer,
        ForeignKey("assets.id"),
        nullable=False,
        unique=True,
        index=True
    )

    valuation_id = Column(
        Integer,
        ForeignKey("property_valuations.id"),
        nullable=True
    )

    issued_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    token_name = Column(String(150), nullable=False)
    token_symbol = Column(String(20), nullable=False)

    currency = Column(String(10), nullable=False)

    token_price = Column(
        Numeric(18, 8),
        nullable=False
    )

    total_supply = Column(
        Numeric(28, 8),
        nullable=False
    )

    decimal_precision = Column(Integer, nullable=False, default=8)
    minimum_investment = Column(Numeric(18, 2), nullable=False, default=0)
    maximum_investment = Column(Numeric(18, 2), nullable=True)
    issuance_date = Column(Date, nullable=True)
    issuance_terms = Column(Text, nullable=False, default="")
    restrictions = Column(Text, nullable=False, default="")
    proposed_tokenisation_arrangements = Column(Text, nullable=False, default="")
    token_rights_description = Column(Text, nullable=False, default="")
    status = Column(String(30), nullable=False, default="ISSUED")
    approval_references = Column(Text, nullable=False, default="[]")

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
