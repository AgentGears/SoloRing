"""worker_leases table (plan §30)

Revision ID: 0001_worker_leases
Revises:
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_worker_leases"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_leases",
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("worker_id", sa.Text(), nullable=False),
        sa.Column("acquired_at", sa.Text(), nullable=False),
        sa.Column("heartbeat_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("name", name="pk_worker_leases"),
    )


def downgrade() -> None:
    op.drop_table("worker_leases")
