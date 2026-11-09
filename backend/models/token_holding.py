from sqlalchemy import (
    Column,
    Integer,
    Numeric,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint
)
from sqlalchemy.sql import func

from database import Base


class TokenHolding(Base):
    __tablename__ = "token_holdings"

    __table_args__ = (
        UniqueConstraint(
            "issuance_id",
            "user_id",
            name="uq_token_holding_issuance_user"
        ),
        CheckConstraint(
            "balance >= 0",
            name="check_token_balance_non_negative"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    issuance_id = Column(
        Integer,
        ForeignKey("token_issuances.id"),
        nullable=False,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    balance = Column(
        Numeric(28, 8),
        nullable=False,
        default=0
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
