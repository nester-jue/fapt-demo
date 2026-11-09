"""Reconcile purchase metadata and enforce ledger invariants."""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

from models.audit_event import AuditEvent
from models.token_issuance import TokenIssuance
from models.token_transaction import TokenTransaction
from services.ledger import (
    _chain_hash,
    audit_hash_payload,
    transaction_hash_payload,
)

revision: str = "b7e5c20419af"
down_revision: Union[str, Sequence[str], None] = "9a31d7f0e2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    transaction_columns = {
        column["name"]: column
        for column in inspector.get_columns("token_transactions")
    }
    if "purchase_value" not in transaction_columns:
        op.add_column(
            "token_transactions",
            sa.Column("purchase_value", sa.Numeric(38, 16), nullable=True),
        )
    if "currency" not in transaction_columns:
        op.add_column(
            "token_transactions", sa.Column("currency", sa.String(10), nullable=True)
        )

    bind.execute(
        sa.text(
            "UPDATE token_transactions SET idempotency_key = "
            "'LEGACY-' || transaction_ref "
            "WHERE transaction_type IN ('PURCHASE', 'TRANSFER') "
            "AND idempotency_key IS NULL"
        )
    )

    session = Session(bind=bind, expire_on_commit=False)
    try:
        for transaction in session.query(TokenTransaction).order_by(TokenTransaction.id).all():
            if transaction.transaction_type == "PURCHASE" and transaction.purchase_value is None:
                issuance = session.query(TokenIssuance).filter(
                    TokenIssuance.id == transaction.issuance_id
                ).first()
                if issuance:
                    transaction.purchase_value = transaction.amount * issuance.token_price
                    transaction.currency = issuance.currency
        transaction_heads = {}
        for transaction in session.query(TokenTransaction).order_by(TokenTransaction.id).all():
            previous_hash = transaction_heads.get(transaction.issuance_id)
            transaction.previous_hash = previous_hash
            transaction.transaction_hash = _chain_hash(
                previous_hash, transaction_hash_payload(transaction)
            )
            transaction_heads[transaction.issuance_id] = transaction.transaction_hash

        previous_audit_hash = None
        for event in session.query(AuditEvent).order_by(AuditEvent.id).all():
            if not event.event_uuid:
                event.event_uuid = str(uuid4())
            event.previous_hash = previous_audit_hash
            event.event_hash = _chain_hash(
                previous_audit_hash, audit_hash_payload(event)
            )
            previous_audit_hash = event.event_hash
        session.flush()

        check_names = {
            check["name"]
            for check in inspector.get_check_constraints("token_transactions")
        }
        transaction_nullable = {
            column["name"]: column["nullable"]
            for column in sa.inspect(bind).get_columns("token_transactions")
        }
        audit_nullable = {
            column["name"]: column["nullable"]
            for column in sa.inspect(bind).get_columns("audit_events")
        }
        with op.batch_alter_table("token_transactions") as batch_op:
            if "check_market_transaction_idempotency" not in check_names:
                batch_op.create_check_constraint(
                    "check_market_transaction_idempotency",
                    "transaction_type NOT IN ('PURCHASE', 'TRANSFER') OR idempotency_key IS NOT NULL",
                )
            if "check_purchase_value_and_currency" not in check_names:
                batch_op.create_check_constraint(
                    "check_purchase_value_and_currency",
                    "transaction_type != 'PURCHASE' OR (purchase_value IS NOT NULL AND currency IS NOT NULL)",
                )
            if transaction_nullable.get("transaction_hash", True):
                batch_op.alter_column(
                    "transaction_hash", existing_type=sa.String(64), nullable=False
                )
        with op.batch_alter_table("audit_events") as batch_op:
            if audit_nullable.get("event_uuid", True):
                batch_op.alter_column(
                    "event_uuid", existing_type=sa.String(36), nullable=False
                )
            if audit_nullable.get("event_hash", True):
                batch_op.alter_column(
                    "event_hash", existing_type=sa.String(64), nullable=False
                )
    finally:
        session.close()


def downgrade() -> None:
    """Keep the reconciled schema, which is already part of the parent revision."""
    pass
