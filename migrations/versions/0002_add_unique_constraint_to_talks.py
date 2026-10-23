"""add unique constraint to talks

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-29 23:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Preserve duplicate rows and their related jobs/reviews while making the
    # legacy key unique. Later rows receive a deterministic title suffix.
    op.execute(
        """
        UPDATE talks AS duplicate
        SET title = left(
            duplicate.title,
            255 - length(' [duplicate ' || duplicate.id::text || ']')
        ) || ' [duplicate ' || duplicate.id::text || ']'
        WHERE EXISTS (
            SELECT 1
            FROM talks AS original
            WHERE original.event_id = duplicate.event_id
              AND original.start = duplicate.start
              AND original.title = duplicate.title
              AND original.id < duplicate.id
        )
        """
    )
    op.create_unique_constraint(
        "uq_talks_event_id_title_start",
        "talks",
        ["event_id", "title", "start"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_talks_event_id_title_start", "talks", type_="unique")
