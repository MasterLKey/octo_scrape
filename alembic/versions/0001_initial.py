"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-23

"""
from typing import Sequence, Union
import datetime

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scrape_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("html_snapshot", sa.Text(), nullable=True),
        sa.Column("offer_detected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("offer_accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("page_changed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    op.create_table(
        "schedule_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("window_start", sa.Time(), nullable=False, server_default="08:00:00"),
        sa.Column("window_end", sa.Time(), nullable=False, server_default="22:00:00"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Insert the single default schedule config row
    op.execute(
        "INSERT INTO schedule_config (id, interval_minutes, window_start, window_end, enabled) "
        "VALUES (1, 60, '08:00:00', '22:00:00', false)"
    )


def downgrade() -> None:
    op.drop_table("scrape_records")
    op.drop_table("schedule_config")
