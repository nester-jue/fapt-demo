"""Add investor marketplace, management, notifications and ledger integrity."""

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

revision: str = "9a31d7f0e2c4"
down_revision: Union[str, Sequence[str], None] = "c6e8f0a2b471"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "token_transactions",
        sa.Column("status", sa.String(40), nullable=False, server_default="COMPLETED"),
    )
    op.add_column(
        "token_transactions",
        sa.Column(
            "payment_status", sa.String(40), nullable=False, server_default="NOT_APPLICABLE"
        ),
    )
    op.add_column(
        "token_transactions", sa.Column("purchase_value", sa.Numeric(38, 16), nullable=True)
    )
    op.add_column(
        "token_transactions", sa.Column("currency", sa.String(10), nullable=True)
    )
    op.add_column(
        "token_transactions", sa.Column("idempotency_key", sa.String(100), nullable=True)
    )
    for column in (
        "from_balance_before",
        "from_balance_after",
        "to_balance_before",
        "to_balance_after",
    ):
        op.add_column(
            "token_transactions", sa.Column(column, sa.Numeric(28, 8), nullable=True)
        )
    op.add_column(
        "token_transactions", sa.Column("previous_hash", sa.String(64), nullable=True)
    )
    op.add_column(
        "token_transactions", sa.Column("transaction_hash", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_token_transactions_transaction_hash",
        "token_transactions",
        ["transaction_hash"],
    )
    op.create_index(
        "ix_token_transactions_idempotency_key",
        "token_transactions",
        ["idempotency_key"],
        unique=True,
    )

    op.add_column("audit_events", sa.Column("event_uuid", sa.String(36), nullable=True))
    op.add_column("audit_events", sa.Column("previous_hash", sa.String(64), nullable=True))
    op.add_column("audit_events", sa.Column("event_hash", sa.String(64), nullable=True))
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE token_transactions SET idempotency_key = "
            "'LEGACY-' || transaction_ref "
            "WHERE transaction_type IN ('PURCHASE', 'TRANSFER') "
            "AND idempotency_key IS NULL"
        )
    )
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.create_unique_constraint(
            "uq_audit_events_event_uuid", ["event_uuid"]
        )
    op.create_index("ix_audit_events_event_hash", "audit_events", ["event_hash"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=True),
        sa.Column("entity_id", sa.String(100), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_id", "notifications", ["id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_event_type", "notifications", ["event_type"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])

    op.create_table(
        "property_manager_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("manager_user_id", sa.Integer(), nullable=False),
        sa.Column("assigned_by_user_id", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["manager_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_property_manager_assignments_id", "property_manager_assignments", ["id"])
    op.create_index(
        "ix_property_manager_assignments_asset_id", "property_manager_assignments", ["asset_id"]
    )
    op.create_index(
        "ix_property_manager_assignments_manager_user_id",
        "property_manager_assignments",
        ["manager_user_id"],
    )
    op.create_index(
        "ix_property_manager_assignments_is_active",
        "property_manager_assignments",
        ["is_active"],
    )

    op.create_table(
        "property_management_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("manager_user_id", sa.Integer(), nullable=False),
        sa.Column("record_type", sa.String(40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("document_ids", sa.Text(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["manager_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_property_management_records_id", "property_management_records", ["id"])
    op.create_index(
        "ix_property_management_records_asset_id", "property_management_records", ["asset_id"]
    )
    op.create_index(
        "ix_property_management_records_manager_user_id",
        "property_management_records",
        ["manager_user_id"],
    )
    op.create_index(
        "ix_property_management_records_record_type",
        "property_management_records",
        ["record_type"],
    )

    session = Session(bind=bind, expire_on_commit=False)
    try:
        transaction_heads = {}
        for transaction in session.query(TokenTransaction).order_by(TokenTransaction.id).all():
            if transaction.transaction_type == "PURCHASE" and transaction.purchase_value is None:
                issuance = session.query(TokenIssuance).filter(
                    TokenIssuance.id == transaction.issuance_id
                ).first()
                if issuance:
                    transaction.purchase_value = transaction.amount * issuance.token_price
                    transaction.currency = issuance.currency
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
        with op.batch_alter_table("token_transactions") as batch_op:
            batch_op.create_check_constraint(
                "check_market_transaction_idempotency",
                "transaction_type NOT IN ('PURCHASE', 'TRANSFER') OR idempotency_key IS NOT NULL",
            )
            batch_op.create_check_constraint(
                "check_purchase_value_and_currency",
                "transaction_type != 'PURCHASE' OR (purchase_value IS NOT NULL AND currency IS NOT NULL)",
            )
        with op.batch_alter_table("audit_events") as batch_op:
            batch_op.alter_column("event_uuid", existing_type=sa.String(36), nullable=False)
            batch_op.alter_column("event_hash", existing_type=sa.String(64), nullable=False)
        with op.batch_alter_table("token_transactions") as batch_op:
            batch_op.alter_column(
                "transaction_hash", existing_type=sa.String(64), nullable=False
            )
    finally:
        session.close()


def downgrade() -> None:
    op.drop_table("property_management_records")
    op.drop_table("property_manager_assignments")
    op.drop_table("notifications")
    op.drop_index("ix_audit_events_event_hash", table_name="audit_events")
    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_constraint("uq_audit_events_event_uuid", type_="unique")
    with op.batch_alter_table("token_transactions") as batch_op:
        batch_op.drop_constraint(
            "check_purchase_value_and_currency", type_="check"
        )
        batch_op.drop_constraint(
            "check_market_transaction_idempotency", type_="check"
        )
    op.drop_column("audit_events", "event_hash")
    op.drop_column("audit_events", "previous_hash")
    op.drop_column("audit_events", "event_uuid")
    op.drop_index(
        "ix_token_transactions_idempotency_key", table_name="token_transactions"
    )
    op.drop_index(
        "ix_token_transactions_transaction_hash", table_name="token_transactions"
    )
    for column in (
        "transaction_hash",
        "previous_hash",
        "to_balance_after",
        "to_balance_before",
        "from_balance_after",
        "from_balance_before",
        "idempotency_key",
        "payment_status",
        "status",
        "currency",
        "purchase_value",
    ):
        op.drop_column("token_transactions", column)
