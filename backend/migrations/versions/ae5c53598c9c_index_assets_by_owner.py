"""index assets by owner

Revision ID: ae5c53598c9c
Revises: 53cbc3c9657c
Create Date: 2026-11-06 22:06:09.351232

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae5c53598c9c'
down_revision: Union[str, Sequence[str], None] = '53cbc3c9657c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    indexes = sa.inspect(op.get_bind()).get_indexes("assets")
    if not any(index["name"] == "ix_assets_user_id" for index in indexes):
        op.create_index("ix_assets_user_id", "assets", ["user_id"], unique=False)


def downgrade() -> None:
    indexes = sa.inspect(op.get_bind()).get_indexes("assets")
    if any(index["name"] == "ix_assets_user_id" for index in indexes):
        op.drop_index("ix_assets_user_id", table_name="assets")
