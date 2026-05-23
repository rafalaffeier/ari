"""Add workspace recovery key wraps.

Revision ID: 20260523_0005
Revises: 20260523_0004
Create Date: 2026-05-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0005"
down_revision: Union[str, None] = "20260523_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_recovery_wraps",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("key_id", sa.String(length=200), nullable=False),
        sa.Column("wrapping_algorithm", sa.String(length=100), nullable=False),
        sa.Column("wrapped_key", sa.Text(), nullable=False),
        sa.Column("recovery_hint", sa.String(length=200), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "key_id", name="uq_workspace_recovery_wraps_workspace_key"),
    )


def downgrade() -> None:
    op.drop_table("workspace_recovery_wraps")
