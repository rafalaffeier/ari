"""Add workspace key wrapping metadata.

Revision ID: 20260523_0004
Revises: 20260523_0003
Create Date: 2026-05-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260523_0004"
down_revision: Union[str, None] = "20260523_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "workspace_key_wraps",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("device_id", sa.UUID(), nullable=False),
        sa.Column("key_id", sa.String(length=200), nullable=False),
        sa.Column("wrapping_algorithm", sa.String(length=100), nullable=False),
        sa.Column("wrapped_key", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "device_id", "key_id", name="uq_workspace_key_wraps_workspace_device_key"),
    )
    op.create_index(
        "ix_workspace_key_wraps_device_key",
        "workspace_key_wraps",
        ["device_id", "key_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_key_wraps_device_key", table_name="workspace_key_wraps")
    op.drop_table("workspace_key_wraps")
    op.drop_column("devices", "revoked_at")
