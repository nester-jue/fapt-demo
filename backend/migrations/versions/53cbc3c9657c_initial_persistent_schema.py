"""Create the initial persistent schema or adopt an existing matching schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "53cbc3c9657c"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names()) - {"alembic_version"}
    required_columns = {
        "users": {
            "id", "full_name", "email", "hashed_password", "role",
            "is_active", "created_at",
        },
        "assets": {
            "id", "asset_code", "name", "category", "description",
            "location", "estimated_value", "currency", "owner_name",
            "status", "user_id", "reviewed_by", "reviewed_at",
            "rejection_reason", "created_at",
        },
        "asset_review_logs": {
            "id", "asset_id", "admin_user_id", "action", "reason",
            "created_at",
        },
        "token_issuances": {
            "id", "asset_id", "issued_by_user_id", "token_name",
            "token_symbol", "currency", "token_price", "total_supply",
            "created_at",
        },
        "token_holdings": {
            "id", "issuance_id", "user_id", "balance", "updated_at",
        },
        "token_transactions": {
            "id", "transaction_ref", "issuance_id", "from_user_id",
            "to_user_id", "amount", "transaction_type", "created_at",
        },
    }

    if existing_tables:
        missing_tables = set(required_columns) - existing_tables
        missing_columns = {
            table: columns - {
                column["name"] for column in inspector.get_columns(table)
            }
            for table, columns in required_columns.items()
            if table in existing_tables
        }
        missing_columns = {
            table: columns
            for table, columns in missing_columns.items()
            if columns
        }
        if missing_tables or missing_columns:
            raise RuntimeError(
                "The existing database does not match the initial NEXA "
                "schema. No tables were changed. Back up the database and "
                "create a dedicated migration for its current schema before "
                f"upgrading. Missing tables: {sorted(missing_tables)}; "
                f"missing columns: {missing_columns}"
            )
        return

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_id", "users", ["id"], unique=False)

    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("estimated_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("owner_name", sa.String(length=150), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assets_asset_code", "assets", ["asset_code"], unique=True)
    op.create_index("ix_assets_id", "assets", ["id"], unique=False)
    op.create_index("ix_assets_user_id", "assets", ["user_id"], unique=False)

    op.create_table(
        "asset_review_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("admin_user_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_asset_review_logs_asset_id", "asset_review_logs", ["asset_id"]
    )
    op.create_index("ix_asset_review_logs_id", "asset_review_logs", ["id"])

    op.create_table(
        "token_issuances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("issued_by_user_id", sa.Integer(), nullable=False),
        sa.Column("token_name", sa.String(length=150), nullable=False),
        sa.Column("token_symbol", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("token_price", sa.Numeric(18, 8), nullable=False),
        sa.Column("total_supply", sa.Numeric(28, 8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "token_price > 0", name="check_token_price_positive"
        ),
        sa.CheckConstraint(
            "total_supply > 0", name="check_total_supply_positive"
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["issued_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_token_issuances_asset_id", "token_issuances", ["asset_id"],
        unique=True,
    )
    op.create_index("ix_token_issuances_id", "token_issuances", ["id"])

    op.create_table(
        "token_holdings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issuance_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("balance", sa.Numeric(28, 8), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "balance >= 0", name="check_token_balance_non_negative"
        ),
        sa.ForeignKeyConstraint(["issuance_id"], ["token_issuances.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "issuance_id", "user_id",
            name="uq_token_holding_issuance_user",
        ),
    )
    op.create_index("ix_token_holdings_id", "token_holdings", ["id"])
    op.create_index(
        "ix_token_holdings_issuance_id", "token_holdings", ["issuance_id"]
    )
    op.create_index("ix_token_holdings_user_id", "token_holdings", ["user_id"])

    op.create_table(
        "token_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("transaction_ref", sa.String(length=100), nullable=False),
        sa.Column("issuance_id", sa.Integer(), nullable=False),
        sa.Column("from_user_id", sa.Integer(), nullable=True),
        sa.Column("to_user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(28, 8), nullable=False),
        sa.Column("transaction_type", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "amount > 0", name="check_token_transaction_amount_positive"
        ),
        sa.CheckConstraint(
            "from_user_id IS NULL OR from_user_id <> to_user_id",
            name="check_token_transaction_different_users",
        ),
        sa.ForeignKeyConstraint(["from_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["issuance_id"], ["token_issuances.id"]),
        sa.ForeignKeyConstraint(["to_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_token_transactions_id", "token_transactions", ["id"]
    )
    op.create_index(
        "ix_token_transactions_issuance_id", "token_transactions", ["issuance_id"]
    )
    op.create_index(
        "ix_token_transactions_transaction_ref", "token_transactions",
        ["transaction_ref"], unique=True,
    )


def downgrade() -> None:
    raise RuntimeError(
        "The initial NEXA schema migration is intentionally irreversible "
        "because it may adopt an existing database. Create a reviewed "
        "follow-up migration instead of dropping persistent tables."
    )
