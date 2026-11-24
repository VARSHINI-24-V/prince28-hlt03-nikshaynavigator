"""add page headings and parse_failures

Revision ID: e96c56e542e4
Revises: 98a8d884fea6
Create Date: 2026-11-24 14:01:10.967029
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e96c56e542e4"
down_revision: Union[str, Sequence[str], None] = "98a8d884fea6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # Create a table to track files that could not be parsed.
    op.create_table(
        "parse_failures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parse_failures")),
        sa.UniqueConstraint("path", name=op.f("uq_parse_failures_path")),
    )

    # Index reason for faster failure filtering.
    op.create_index(
        op.f("ix_parse_failures_reason"),
        "parse_failures",
        ["reason"],
        unique=False,
    )

    # Store section heading paths for each parsed page.
    op.add_column(
        "pages",
        sa.Column(
            "headings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Revert schema changes."""

    op.drop_column("pages", "headings")

    op.drop_index(
        op.f("ix_parse_failures_reason"),
        table_name="parse_failures",
    )

    op.drop_table("parse_failures")
