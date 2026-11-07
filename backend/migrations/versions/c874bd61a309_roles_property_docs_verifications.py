"""Add user audit events, property details, documents and verification history."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c874bd61a309"
down_revision: Union[str, Sequence[str], None] = "ae5c53598c9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("country", sa.String(100), nullable=True))
    op.add_column(
        "assets", sa.Column("jurisdiction", sa.String(100), nullable=True)
    )
    op.add_column(
        "assets", sa.Column("registration_number", sa.String(100), nullable=True)
    )
    op.add_column(
        "assets", sa.Column("property_size", sa.Numeric(18, 2), nullable=True)
    )
    op.add_column(
        "assets", sa.Column("property_size_unit", sa.String(30), nullable=True)
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=True),
        sa.Column("previous_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_id", "audit_events", ["id"])
    op.create_index("ix_audit_events_user_id", "audit_events", ["user_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    op.create_table(
        "property_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("file_size > 0", name="check_property_document_size"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_property_documents_id", "property_documents", ["id"]
    )
    op.create_index(
        "ix_property_documents_asset_id", "property_documents", ["asset_id"]
    )
    op.create_index(
        "ix_property_documents_uploaded_by_user_id",
        "property_documents",
        ["uploaded_by_user_id"],
    )

    op.create_table(
        "property_verifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("verifier_user_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("comments", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.String(50), nullable=False),
        sa.Column("new_status", sa.String(50), nullable=False),
        sa.Column("supporting_references", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["verifier_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_property_verifications_id", "property_verifications", ["id"]
    )
    op.create_index(
        "ix_property_verifications_asset_id",
        "property_verifications",
        ["asset_id"],
    )
    op.create_index(
        "ix_property_verifications_verifier_user_id",
        "property_verifications",
        ["verifier_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_property_verifications_verifier_user_id",
        table_name="property_verifications",
    )
    op.drop_index(
        "ix_property_verifications_asset_id",
        table_name="property_verifications",
    )
    op.drop_index("ix_property_verifications_id", table_name="property_verifications")
    op.drop_table("property_verifications")

    op.drop_index(
        "ix_property_documents_uploaded_by_user_id",
        table_name="property_documents",
    )
    op.drop_index(
        "ix_property_documents_asset_id", table_name="property_documents"
    )
    op.drop_index("ix_property_documents_id", table_name="property_documents")
    op.drop_table("property_documents")

    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_user_id", table_name="audit_events")
    op.drop_index("ix_audit_events_id", table_name="audit_events")
    op.drop_table("audit_events")

    op.drop_column("assets", "property_size_unit")
    op.drop_column("assets", "property_size")
    op.drop_column("assets", "registration_number")
    op.drop_column("assets", "jurisdiction")
    op.drop_column("assets", "country")
