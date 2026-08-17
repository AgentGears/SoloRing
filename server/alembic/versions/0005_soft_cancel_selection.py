"""soft cancel selection (M5A-8)

Revision ID: 0005_soft_cancel_selection
Revises: 0004_comfy_submission_state
Create Date: 2026-08-15

Durable Soft Cancel decision (M5A-8 review §1-§2): the choice to degrade a
running cancellation to Soft Cancel must survive worker death, so a successor
knows a later successful executor result must be discarded, not imported.

    soft_cancel_selected_at IS NOT NULL
    → cancel_requested_at IS NOT NULL        (CHECK-enforced)
    → never hard-cancel; never publish outputs; one-way (no path to NULL)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_soft_cancel_selection"
down_revision: Union[str, None] = "0004_comfy_submission_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.add_column(sa.Column("soft_cancel_selected_at", sa.Text(),
                                    nullable=True))
        batch.create_check_constraint(
            "ck_generations_soft_cancel_implies_intent",
            "soft_cancel_selected_at IS NULL OR cancel_requested_at IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.drop_constraint(
            "ck_generations_soft_cancel_implies_intent", type_="check"
        )
        batch.drop_column("soft_cancel_selected_at")
