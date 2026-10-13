"""add_talk_handoff_tracking

Revision ID: 0019
Revises: 0018
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("talks", sa.Column("handed_off_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "talks",
        sa.Column(
            "handed_off_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("talks", "handed_off_by_user_id")
    op.drop_column("talks", "handed_off_at")
