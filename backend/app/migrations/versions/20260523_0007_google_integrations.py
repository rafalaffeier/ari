"""Add Google integrations.

Revision ID: 20260523_0007
Revises: 20260523_0006
Create Date: 2026-05-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260523_0007"
down_revision: Union[str, None] = "20260523_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_integrations_user_provider"),
    )
    op.create_index(op.f("ix_integrations_user_id"), "integrations", ["user_id"], unique=False)
    op.create_index(op.f("ix_integrations_provider"), "integrations", ["provider"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_integrations_provider"), table_name="integrations")
    op.drop_index(op.f("ix_integrations_user_id"), table_name="integrations")
    op.drop_table("integrations")
