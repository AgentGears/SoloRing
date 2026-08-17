"""generations.attempt_id (M3C)

Revision ID: 0003_generation_attempt_id
Revises: 0002_temporal_domain_storage
Create Date: 2026-08-15

Persists the execution-attempt fence identity on the Generation row. The
attempt id is minted inside the fenced claim transaction and becomes the
idempotent SUBMISSION identity for the executor: a crash between external
submit and handle persistence is recoverable without duplicate external
execution, because recovery re-submits with the same durable identity and the
executor rejoins the existing job (M3C review, Hard Gate C headline case).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_generation_attempt_id"
down_revision: Union[str, None] = "0002_temporal_domain_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.add_column(sa.Column("attempt_id", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.drop_column("attempt_id")
