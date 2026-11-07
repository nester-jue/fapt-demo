"""Add valuation, legal, compliance, approval and issuance workflows."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "78d4f1a2c6b0"
down_revision: Union[str, Sequence[str], None] = "c874bd61a309"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "property_documents",
        sa.Column(
            "document_type",
            sa.String(40),
            nullable=False,
            server_default="PROPERTY_SUPPORT",
        ),
    )
    op.add_column(
        "token_issuances",
        sa.Column("decimal_precision", sa.Integer(), nullable=False, server_default="8"),
    )
    op.add_column(
        "token_issuances",
        sa.Column(
            "minimum_investment",
            sa.Numeric(18, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "token_issuances", sa.Column("maximum_investment", sa.Numeric(18, 2))
    )
    op.add_column("token_issuances", sa.Column("issuance_date", sa.Date()))
    op.add_column(
        "token_issuances",
        sa.Column("issuance_terms", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "token_issuances",
        sa.Column("restrictions", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "token_issuances",
        sa.Column("status", sa.String(30), nullable=False, server_default="ISSUED"),
    )
    op.add_column(
        "token_issuances",
        sa.Column(
            "approval_references",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )

    op.create_table(
        "property_valuations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("valuer_user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("valuation_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("methodology", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("review_comments", sa.Text()),
        sa.Column("reviewed_by_user_id", sa.Integer()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["valuer_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_property_valuations_id", "property_valuations", ["id"])
    op.create_index(
        "ix_property_valuations_asset_id", "property_valuations", ["asset_id"]
    )
    op.create_index(
        "ix_property_valuations_valuer_user_id",
        "property_valuations",
        ["valuer_user_id"],
    )
    op.add_column(
        "property_valuations",
        sa.Column("report_document_ids", sa.Text(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "token_issuances", sa.Column("valuation_id", sa.Integer(), nullable=True)
    )
    with op.batch_alter_table("token_issuances") as batch_op:
        batch_op.create_foreign_key(
            "fk_token_issuances_valuation_id",
            "property_valuations",
            ["valuation_id"],
            ["id"],
        )

    op.create_table(
        "legal_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=False),
        sa.Column("jurisdiction", sa.String(100), nullable=False),
        sa.Column("jurisdiction_requirements", sa.Text(), nullable=False),
        sa.Column("proposed_tokenisation_arrangements", sa.Text(), nullable=False),
        sa.Column("token_rights_description", sa.Text(), nullable=False),
        sa.Column("legal_risks", sa.Text(), nullable=False),
        sa.Column("comments", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("supporting_document_ids", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legal_reviews_id", "legal_reviews", ["id"])
    op.create_index("ix_legal_reviews_asset_id", "legal_reviews", ["asset_id"])
    op.create_index(
        "ix_legal_reviews_reviewer_user_id", "legal_reviews", ["reviewer_user_id"]
    )

    op.create_table(
        "investor_compliance",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kyc_status", sa.String(30), nullable=False),
        sa.Column("aml_status", sa.String(30), nullable=False),
        sa.Column("identity_verification_status", sa.String(30), nullable=False),
        sa.Column("eligibility_status", sa.String(30), nullable=False),
        sa.Column("is_eligible", sa.Boolean(), nullable=False),
        sa.Column("required_documents", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_investor_compliance_id", "investor_compliance", ["id"])
    op.create_index(
        "ix_investor_compliance_user_id", "investor_compliance", ["user_id"]
    )

    op.create_table(
        "compliance_review_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("comments", sa.Text(), nullable=False),
        sa.Column("status_snapshot", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_compliance_review_history_id", "compliance_review_history", ["id"]
    )
    op.create_index(
        "ix_compliance_review_history_user_id",
        "compliance_review_history",
        ["user_id"],
    )
    op.create_index(
        "ix_compliance_review_history_reviewer_user_id",
        "compliance_review_history",
        ["reviewer_user_id"],
    )

    op.create_table(
        "tokenization_proposals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=False),
        sa.Column("token_name", sa.String(150), nullable=False),
        sa.Column("token_symbol", sa.String(20), nullable=False),
        sa.Column("token_price", sa.Numeric(18, 8), nullable=False),
        sa.Column("total_supply", sa.Numeric(28, 8), nullable=False),
        sa.Column("decimal_precision", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("minimum_investment", sa.Numeric(18, 2), nullable=False),
        sa.Column("maximum_investment", sa.Numeric(18, 2)),
        sa.Column("issuance_date", sa.Date(), nullable=False),
        sa.Column("issuance_terms", sa.Text(), nullable=False),
        sa.Column("restrictions", sa.Text(), nullable=False),
        sa.Column("disclosures", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("review_comments", sa.Text()),
        sa.Column("reviewed_by_user_id", sa.Integer()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["submitted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id"),
    )
    op.create_index(
        "ix_tokenization_proposals_id", "tokenization_proposals", ["id"]
    )
    op.create_index(
        "ix_tokenization_proposals_asset_id",
        "tokenization_proposals",
        ["asset_id"],
    )

    op.create_table(
        "tokenization_approvals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("approval_ref", sa.String(40), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("responsible_user_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("comments", sa.Text(), nullable=False),
        sa.Column("supporting_document_ids", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_ref"),
    )
    op.create_index(
        "ix_tokenization_approvals_id", "tokenization_approvals", ["id"]
    )
    op.create_index(
        "ix_tokenization_approvals_approval_ref",
        "tokenization_approvals",
        ["approval_ref"],
    )
    op.create_index(
        "ix_tokenization_approvals_asset_id",
        "tokenization_approvals",
        ["asset_id"],
    )
    op.create_index(
        "ix_tokenization_approvals_stage", "tokenization_approvals", ["stage"]
    )


def downgrade() -> None:
    op.drop_index("ix_tokenization_approvals_stage", table_name="tokenization_approvals")
    op.drop_index(
        "ix_tokenization_approvals_asset_id", table_name="tokenization_approvals"
    )
    op.drop_index(
        "ix_tokenization_approvals_approval_ref", table_name="tokenization_approvals"
    )
    op.drop_index("ix_tokenization_approvals_id", table_name="tokenization_approvals")
    op.drop_table("tokenization_approvals")

    op.drop_index(
        "ix_tokenization_proposals_asset_id", table_name="tokenization_proposals"
    )
    op.drop_index(
        "ix_tokenization_proposals_id", table_name="tokenization_proposals"
    )
    op.drop_table("tokenization_proposals")

    op.drop_index(
        "ix_compliance_review_history_reviewer_user_id",
        table_name="compliance_review_history",
    )
    op.drop_index(
        "ix_compliance_review_history_user_id",
        table_name="compliance_review_history",
    )
    op.drop_index(
        "ix_compliance_review_history_id", table_name="compliance_review_history"
    )
    op.drop_table("compliance_review_history")

    op.drop_index("ix_investor_compliance_user_id", table_name="investor_compliance")
    op.drop_index("ix_investor_compliance_id", table_name="investor_compliance")
    op.drop_table("investor_compliance")

    op.drop_index("ix_legal_reviews_reviewer_user_id", table_name="legal_reviews")
    op.drop_index("ix_legal_reviews_asset_id", table_name="legal_reviews")
    op.drop_index("ix_legal_reviews_id", table_name="legal_reviews")
    op.drop_table("legal_reviews")

    op.drop_index(
        "ix_property_valuations_valuer_user_id", table_name="property_valuations"
    )
    op.drop_column("property_valuations", "report_document_ids")
    with op.batch_alter_table("token_issuances") as batch_op:
        batch_op.drop_constraint(
            "fk_token_issuances_valuation_id", type_="foreignkey"
        )
        batch_op.drop_column("valuation_id")
    op.drop_index("ix_property_valuations_asset_id", table_name="property_valuations")
    op.drop_index("ix_property_valuations_id", table_name="property_valuations")
    op.drop_table("property_valuations")

    op.drop_column("token_issuances", "approval_references")
    op.drop_column("token_issuances", "status")
    op.drop_column("token_issuances", "restrictions")
    op.drop_column("token_issuances", "issuance_terms")
    op.drop_column("token_issuances", "issuance_date")
    op.drop_column("token_issuances", "maximum_investment")
    op.drop_column("token_issuances", "minimum_investment")
    op.drop_column("token_issuances", "decimal_precision")
    op.drop_column("property_documents", "document_type")
