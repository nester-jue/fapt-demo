"""Enforce unique case-insensitive property registry references."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4a9f2c781be"
down_revision: Union[str, Sequence[str], None] = "b7e5c20419af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "uq_assets_registration_number_key"


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT lower(trim(registration_number)) "
            "FROM assets "
            "WHERE registration_number IS NOT NULL "
            "AND trim(registration_number) <> '' "
            "GROUP BY lower(trim(registration_number)) "
            "HAVING count(*) > 1 "
            "LIMIT 1"
        )
    ).first()
    if duplicates:
        raise RuntimeError(
            "Cannot enforce unique property registration references: "
            "duplicate values already exist. Resolve them before retrying."
        )

    columns = {
        column["name"]
        for column in sa.inspect(bind).get_columns("assets")
    }
    if "registration_number_key" not in columns:
        op.add_column(
            "assets",
            sa.Column("registration_number_key", sa.String(100), nullable=True),
        )
    bind.execute(
        sa.text(
            "UPDATE assets "
            "SET registration_number_key = NULLIF(lower(trim(registration_number)), '') "
            "WHERE registration_number_key IS NULL"
        )
    )

    indexes = sa.inspect(bind).get_indexes("assets")
    if not any(index["name"] == INDEX_NAME for index in indexes):
        op.create_index(
            INDEX_NAME,
            "assets",
            ["registration_number_key"],
            unique=True,
        )


def downgrade() -> None:
    indexes = sa.inspect(op.get_bind()).get_indexes("assets")
    if any(index["name"] == INDEX_NAME for index in indexes):
        op.drop_index(INDEX_NAME, table_name="assets")
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("assets")
    }
    if "registration_number_key" in columns:
        with op.batch_alter_table("assets") as batch_op:
            batch_op.drop_column("registration_number_key")
