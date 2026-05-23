"""Drop legacy SQL memory/message storage.

Revision ID: 20260523_0009
Revises: 20260523_0008
Create Date: 2026-05-23
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260523_0009"
down_revision: Union[str, None] = "20260523_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS memory")


def downgrade() -> None:
    pass
