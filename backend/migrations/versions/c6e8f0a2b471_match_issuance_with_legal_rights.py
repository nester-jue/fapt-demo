"""Bind proposal and issuance rights to the approved legal review."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c6e8f0a2b471"
down_revision: Union[str, Sequence[str], None] = "78d4f1a2c6b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tokenization_proposals",
        sa.Column("proposed_tokenisation_arrangements", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "tokenization_proposals",
        sa.Column("token_rights_description", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "token_issuances",
        sa.Column("proposed_tokenisation_arrangements", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "token_issuances",
        sa.Column("token_rights_description", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("token_issuances", "token_rights_description")
    op.drop_column("token_issuances", "proposed_tokenisation_arrangements")
    op.drop_column("tokenization_proposals", "token_rights_description")
    op.drop_column("tokenization_proposals", "proposed_tokenisation_arrangements")
