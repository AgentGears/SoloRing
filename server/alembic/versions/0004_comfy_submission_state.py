"""comfy submission state (M5A-1)

Revision ID: 0004_comfy_submission_state
Revises: 0003_generation_attempt_id
Create Date: 2026-08-15

Durable one-shot submission authority (M5 plan §6-§11, as amended):

    executor_submission_state answers a question DISTINCT from
    Generation.status: "may an irreversible remote submission already have
    occurred for this attempt?"

    not_started          → no POST has been permitted
    submission_possible  → a worker durably announced intent to POST
    confirmed            → executor_job_id persisted (POST provably happened)
    uncertain            → ambiguity unresolved; POST permanently forbidden

Only the stack frame whose fenced transition not_started → submission_possible
committed receives MAY_POST. Every later path (crash recovery, adoption,
requeue) is REDISCOVER_ONLY — this deliberately prefers possible lost
execution over possible duplicate expensive execution (v0.1 §65).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_comfy_submission_state"
down_revision: Union[str, None] = "0003_generation_attempt_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.add_column(
            sa.Column(
                "executor_submission_state",
                sa.Text(),
                nullable=False,
                server_default="not_started",
            )
        )
        batch.add_column(sa.Column("submission_possible_at", sa.Text(), nullable=True))
        batch.create_check_constraint(
            "ck_generations_executor_submission_state",
            "executor_submission_state IN ("
            "'not_started','submission_possible','confirmed','uncertain')",
        )
        batch.create_check_constraint(
            "ck_generations_submission_possible_attempt",
            "executor_submission_state != 'submission_possible' "
            "OR attempt_id IS NOT NULL",
        )
        batch.create_check_constraint(
            "ck_generations_submission_confirmed_job",
            "executor_submission_state != 'confirmed' "
            "OR executor_job_id IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.drop_constraint(
            "ck_generations_submission_confirmed_job", type_="check"
        )
        batch.drop_constraint(
            "ck_generations_submission_possible_attempt", type_="check"
        )
        batch.drop_constraint(
            "ck_generations_executor_submission_state", type_="check"
        )
        batch.drop_column("submission_possible_at")
        batch.drop_column("executor_submission_state")
