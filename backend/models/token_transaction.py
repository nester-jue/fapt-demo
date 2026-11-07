from sqlalchemy import (
    Column,
    Integer,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
)
from sqlalchemy.sql import func

from database import Base


class TokenTransaction(Base):
    __tablename__ = "token_transactions"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="check_token_transaction_amount_positive"
        ),
        CheckConstraint(
            "from_user_id IS NULL OR from_user_id <> to_user_id",
            name="check_token_transaction_different_users"
        ),
        CheckConstraint(
            "transaction_type NOT IN ('PURCHASE', 'TRANSFER') OR idempotency_key IS NOT NULL",
            name="check_market_transaction_idempotency",
        ),
        CheckConstraint(
            "transaction_type != 'PURCHASE' OR (purchase_value IS NOT NULL AND currency IS NOT NULL)",
            name="check_purchase_value_and_currency",
        ),
        Index(
            "ix_token_transactions_idempotency_key",
            "idempotency_key",
            unique=True,
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    transaction_ref = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    issuance_id = Column(
        Integer,
        ForeignKey("token_issuances.id"),
        nullable=False,
        index=True
    )

    from_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    to_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    amount = Column(
        Numeric(28, 8),
        nullable=False
    )

    transaction_type = Column(
        String(30),
        nullable=False
    )

    status = Column(String(40), nullable=False, default="COMPLETED")
    payment_status = Column(String(40), nullable=False, default="NOT_APPLICABLE")
    purchase_value = Column(Numeric(38, 16), nullable=True)
    currency = Column(String(10), nullable=True)
    idempotency_key = Column(String(100), nullable=True)
    from_balance_before = Column(Numeric(28, 8), nullable=True)
    from_balance_after = Column(Numeric(28, 8), nullable=True)
    to_balance_before = Column(Numeric(28, 8), nullable=True)
    to_balance_after = Column(Numeric(28, 8), nullable=True)
    previous_hash = Column(String(64), nullable=True)
    transaction_hash = Column(String(64), nullable=False, index=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
