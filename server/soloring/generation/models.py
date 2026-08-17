"""ORM models: Generations, GenerationInputs, Takes (plan §31, §38, §41).

Large JSON payloads (workflow_spec_json, executor_submission_json,
error_details_json) are deferred from the first definition (plan §35) so
lightweight queue/status/list reads never load them.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from soloring.db.base import Base
from soloring.db.timeutil import DB_NOW_SQL

UUID = String(36)

_STATUSES = (
    "'queued', 'preparing', 'submitted', 'running', 'importing', "
    "'succeeded', 'failed', 'interrupted', 'cancelled'"
)


class Generation(Base):
    """Complete durable Generation record (plan §31). Not executable in M1."""

    __tablename__ = "generations"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_generations"),
        ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_generations_shot_id_shots", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_generations_shot_revision_id_shot_revisions", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["rerun_of_generation_id"], ["generations.id"],
            name="fk_generations_rerun_of_generation_id_generations", ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "shot_id", "generation_number",
            name="uq_generations_shot_id_generation_number",
        ),
        CheckConstraint("operation IN ('generate', 'rerun')", name="ck_generations_operation"),
        CheckConstraint(f"status IN ({_STATUSES})", name="ck_generations_status"),
        CheckConstraint("executor IN ('fake', 'comfy')", name="ck_generations_executor"),
        CheckConstraint(
            "length(workflow_template_hash) = 64",
            name="ck_generations_workflow_template_hash_len",
        ),
        CheckConstraint("length(manifest_hash) = 64", name="ck_generations_manifest_hash_len"),
        CheckConstraint(
            "length(workflow_spec_hash) = 64", name="ck_generations_workflow_spec_hash_len"
        ),
        CheckConstraint(
            "executor_submission_hash IS NULL OR length(executor_submission_hash) = 64",
            name="ck_generations_executor_submission_hash_len",
        ),
        CheckConstraint(
            "executor_submission_state IN ("
            "'not_started','submission_possible','confirmed','uncertain')",
            name="ck_generations_executor_submission_state",
        ),
        CheckConstraint(
            "executor_submission_state != 'submission_possible' "
            "OR attempt_id IS NOT NULL",
            name="ck_generations_submission_possible_attempt",
        ),
        CheckConstraint(
            "executor_submission_state != 'confirmed' OR executor_job_id IS NOT NULL",
            name="ck_generations_submission_confirmed_job",
        ),
        CheckConstraint(
            "soft_cancel_selected_at IS NULL OR cancel_requested_at IS NOT NULL",
            name="ck_generations_soft_cancel_implies_intent",
        ),
        Index("ix_generations_queue", "status", "queued_at"),
        Index("ix_generations_active_recovery", "status", "heartbeat_at"),
        Index("ix_generations_worker_active", "worker_id", "status", "heartbeat_at"),
    )

    id: Mapped[str] = mapped_column(UUID)
    shot_id: Mapped[str] = mapped_column(UUID, nullable=False)
    shot_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    generation_number: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    executor: Mapped[str] = mapped_column(Text, nullable=False)

    workflow_id: Mapped[str] = mapped_column(Text, nullable=False)
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_template_hash: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(Text, nullable=False)

    model: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)

    compiled_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text)
    prompt_compiler_version: Mapped[str] = mapped_column(Text, nullable=False)

    seed: Mapped[int | None] = mapped_column(Integer)
    parameters_json: Mapped[str] = mapped_column(Text, nullable=False)

    workflow_spec_json: Mapped[str] = mapped_column(Text, nullable=False, deferred=True)
    workflow_spec_hash: Mapped[str] = mapped_column(Text, nullable=False)

    executor_submission_json: Mapped[str | None] = mapped_column(Text, deferred=True)
    executor_submission_hash: Mapped[str | None] = mapped_column(Text)

    executor_job_id: Mapped[str | None] = mapped_column(Text)
    executor_handle_json: Mapped[str | None] = mapped_column(Text)

    # Durable execution-attempt fence identity (M3C): minted at claim, used as
    # the idempotent executor submission identity and staging namespace.
    attempt_id: Mapped[str | None] = mapped_column(Text)

    # One-shot submission authority (M5A-1): distinct from lifecycle status.
    # not_started -> submission_possible -> {confirmed | uncertain}, one-way.
    executor_submission_state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'not_started'")
    )
    submission_possible_at: Mapped[str | None] = mapped_column(Text)

    # Durable Soft Cancel decision (M5A-8): one-way; implies cancel intent.
    soft_cancel_selected_at: Mapped[str | None] = mapped_column(Text)

    rerun_of_generation_id: Mapped[str | None] = mapped_column(UUID)

    claimed_at: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[str | None] = mapped_column(Text)
    worker_id: Mapped[str | None] = mapped_column(Text)

    progress_current: Mapped[int | None] = mapped_column(Integer)
    progress_total: Mapped[int | None] = mapped_column(Integer)
    current_node: Mapped[str | None] = mapped_column(Text)

    cancel_requested_at: Mapped[str | None] = mapped_column(Text)
    cancel_reason: Mapped[str | None] = mapped_column(Text)

    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    error_details_json: Mapped[str | None] = mapped_column(Text, deferred=True)

    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    queued_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    started_at: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[str | None] = mapped_column(Text)


class GenerationInput(Base):
    """Immutable historical execution-input binding (plan §38)."""

    __tablename__ = "generation_inputs"

    __table_args__ = (
        PrimaryKeyConstraint(
            "generation_id", "input_key", "position", name="pk_generation_inputs"
        ),
        ForeignKeyConstraint(
            ["generation_id"], ["generations.id"],
            name="fk_generation_inputs_generation_id_generations", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_generation_inputs_asset_id_assets", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_generation_inputs_blob_hash_blobs", ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 0", name="ck_generation_inputs_position_nonneg"),
        CheckConstraint("length(input_key) > 0", name="ck_generation_inputs_input_key_nonempty"),
        CheckConstraint(
            "reference_role IS NULL OR "
            "(length(reference_role) BETWEEN 1 AND 64 AND length(trim(reference_role)) > 0)",
            name="ck_generation_inputs_reference_role",
        ),
        CheckConstraint("length(blob_hash) = 64", name="ck_generation_inputs_blob_hash_len"),
        Index("ix_generation_inputs_asset_id", "asset_id"),
    )

    generation_id: Mapped[str] = mapped_column(UUID, nullable=False)
    asset_id: Mapped[str] = mapped_column(UUID, nullable=False)
    input_key: Mapped[str] = mapped_column(Text, nullable=False)
    reference_role: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    blob_hash: Mapped[str] = mapped_column(Text, nullable=False)


class Take(Base):
    """Candidate creative result identity (plan §41). No import in M1."""

    __tablename__ = "takes"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_takes"),
        ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_takes_shot_id_shots", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["generation_id"], ["generations.id"],
            name="fk_takes_generation_id_generations", ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "generation_id", "output_key", name="uq_takes_generation_id_output_key"
        ),
        CheckConstraint("length(output_key) > 0", name="ck_takes_output_key_nonempty"),
        Index("ix_takes_shot_created", "shot_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(UUID)
    shot_id: Mapped[str] = mapped_column(UUID, nullable=False)
    generation_id: Mapped[str] = mapped_column(UUID, nullable=False)
    output_key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    rejected_at: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
