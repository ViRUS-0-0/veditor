"""add_talk_handoff_tracking

Revision ID: 0020
Revises: 0019
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    cols = [c["name"] for c in insp.get_columns("talks")]
    if "handed_off_at" not in cols:
        op.add_column("talks", sa.Column("handed_off_at", sa.DateTime(timezone=True), nullable=True))
    if "handed_off_by_user_id" not in cols:
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
