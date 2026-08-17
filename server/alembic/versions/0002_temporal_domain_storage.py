"""temporal_domain_storage (M1)

Revision ID: 0002_temporal_domain_storage
Revises: 0001_worker_leases
Create Date: 2026-08-14

Creates the complete M1 schema: projects, blobs, shots, shot_revisions,
generations, takes, assets, shot_references, generation_inputs, plus the
required recovery/query indexes. Every constraint has a deterministic explicit
name (plan §4.2). `shots.approved_take_id` is intentionally NOT a FK (plan §5.1).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from soloring.db.timeutil import DB_NOW_SQL

# revision identifiers, used by Alembic.
revision: str = "0002_temporal_domain_storage"
down_revision: Union[str, None] = "0001_worker_leases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text(DB_NOW_SQL)
_UUID = sa.String(length=36)

_STATUSES = (
    "'queued', 'preparing', 'submitted', 'running', 'importing', "
    "'succeeded', 'failed', 'interrupted', 'cancelled'"
)


def upgrade() -> None:
    # --- tables in dependency order (plan §4.1) ---------------------------
    op.create_table(
        "projects",
        sa.Column("id", _UUID),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_projects_name_nonempty"),
        sa.CheckConstraint("length(name) <= 500", name="ck_projects_name_maxlen"),
    )

    op.create_table(
        "blobs",
        sa.Column("hash", sa.Text()),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("detected_media_type", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("hash", name="pk_blobs"),
        sa.UniqueConstraint("path", name="uq_blobs_path"),
        sa.CheckConstraint("length(hash) = 64", name="ck_blobs_hash_len"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_blobs_size_nonneg"),
    )

    op.create_table(
        "shots",
        sa.Column("id", _UUID),
        sa.Column("project_id", _UUID, nullable=False),
        sa.Column("shot_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("environment", sa.Text(), nullable=True),
        sa.Column("framing", sa.Text(), nullable=True),
        sa.Column("camera_motion", sa.Text(), nullable=True),
        sa.Column("lens", sa.Text(), nullable=True),
        sa.Column("mood", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("approved_take_id", _UUID, nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_shots"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_shots_project_id_projects", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("project_id", "shot_number", name="uq_shots_project_id_shot_number"),
        sa.CheckConstraint("length(trim(subject)) > 0", name="ck_shots_subject_nonempty"),
        sa.CheckConstraint("length(subject) <= 20000", name="ck_shots_subject_maxlen"),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_shots_duration_nonneg"),
    )

    op.create_table(
        "shot_revisions",
        sa.Column("id", _UUID),
        sa.Column("shot_id", _UUID, nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("id", name="pk_shot_revisions"),
        sa.ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_shot_revisions_shot_id_shots", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shot_id", "revision_number", name="uq_shot_revisions_shot_id_revision_number"),
        sa.UniqueConstraint("shot_id", "snapshot_hash", name="uq_shot_revisions_shot_id_snapshot_hash"),
        sa.CheckConstraint("length(snapshot_hash) = 64", name="ck_shot_revisions_snapshot_hash_len"),
    )

    op.create_table(
        "generations",
        sa.Column("id", _UUID),
        sa.Column("shot_id", _UUID, nullable=False),
        sa.Column("shot_revision_id", _UUID, nullable=False),
        sa.Column("generation_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("executor", sa.Text(), nullable=False),
        sa.Column("workflow_id", sa.Text(), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("workflow_template_hash", sa.Text(), nullable=False),
        sa.Column("manifest_hash", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("compiled_prompt", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("prompt_compiler_version", sa.Text(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("parameters_json", sa.Text(), nullable=False),
        sa.Column("workflow_spec_json", sa.Text(), nullable=False),
        sa.Column("workflow_spec_hash", sa.Text(), nullable=False),
        sa.Column("executor_submission_json", sa.Text(), nullable=True),
        sa.Column("executor_submission_hash", sa.Text(), nullable=True),
        sa.Column("executor_job_id", sa.Text(), nullable=True),
        sa.Column("executor_handle_json", sa.Text(), nullable=True),
        sa.Column("rerun_of_generation_id", _UUID, nullable=True),
        sa.Column("claimed_at", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.Text(), nullable=True),
        sa.Column("progress_current", sa.Integer(), nullable=True),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("current_node", sa.Text(), nullable=True),
        sa.Column("cancel_requested_at", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.Column("queued_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_generations"),
        sa.ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_generations_shot_id_shots", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_generations_shot_revision_id_shot_revisions", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rerun_of_generation_id"], ["generations.id"],
            name="fk_generations_rerun_of_generation_id_generations", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shot_id", "generation_number", name="uq_generations_shot_id_generation_number"),
        sa.CheckConstraint("operation IN ('generate', 'rerun')", name="ck_generations_operation"),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_generations_status"),
        sa.CheckConstraint("executor IN ('fake', 'comfy')", name="ck_generations_executor"),
        sa.CheckConstraint("length(workflow_template_hash) = 64", name="ck_generations_workflow_template_hash_len"),
        sa.CheckConstraint("length(manifest_hash) = 64", name="ck_generations_manifest_hash_len"),
        sa.CheckConstraint("length(workflow_spec_hash) = 64", name="ck_generations_workflow_spec_hash_len"),
        sa.CheckConstraint(
            "executor_submission_hash IS NULL OR length(executor_submission_hash) = 64",
            name="ck_generations_executor_submission_hash_len",
        ),
    )

    op.create_table(
        "takes",
        sa.Column("id", _UUID),
        sa.Column("shot_id", _UUID, nullable=False),
        sa.Column("generation_id", _UUID, nullable=False),
        sa.Column("output_key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("rejected_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("id", name="pk_takes"),
        sa.ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_takes_shot_id_shots", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["generation_id"], ["generations.id"],
            name="fk_takes_generation_id_generations", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("generation_id", "output_key", name="uq_takes_generation_id_output_key"),
        sa.CheckConstraint("length(output_key) > 0", name="ck_takes_output_key_nonempty"),
    )

    op.create_table(
        "assets",
        sa.Column("id", _UUID),
        sa.Column("project_id", _UUID, nullable=False),
        sa.Column("take_id", _UUID, nullable=True),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("upload_mime_type", sa.Text(), nullable=True),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("id", name="pk_assets"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_assets_project_id_projects", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["take_id"], ["takes.id"],
            name="fk_assets_take_id_takes", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_assets_blob_hash_blobs", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("kind IN ('reference', 'output')", name="ck_assets_kind"),
        sa.CheckConstraint(
            "(kind = 'reference' AND take_id IS NULL) OR (kind = 'output' AND take_id IS NOT NULL)",
            name="ck_assets_kind_take_consistency",
        ),
        sa.CheckConstraint("width IS NULL OR width > 0", name="ck_assets_width_pos"),
        sa.CheckConstraint("height IS NULL OR height > 0", name="ck_assets_height_pos"),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_assets_duration_nonneg"),
        sa.CheckConstraint("fps IS NULL OR fps > 0", name="ck_assets_fps_pos"),
    )

    op.create_table(
        "shot_references",
        sa.Column("shot_id", _UUID, nullable=False),
        sa.Column("asset_id", _UUID, nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=_NOW),
        sa.PrimaryKeyConstraint("shot_id", "asset_id", "role", name="pk_shot_references"),
        sa.ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_shot_references_shot_id_shots", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_shot_references_asset_id_assets", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("shot_id", "role", "position", name="uq_shot_references_shot_id_role_position"),
        sa.CheckConstraint("position >= 0", name="ck_shot_references_position_nonneg"),
        sa.CheckConstraint(
            "length(role) BETWEEN 1 AND 64 AND length(trim(role)) > 0",
            name="ck_shot_references_role",
        ),
    )

    op.create_table(
        "generation_inputs",
        sa.Column("generation_id", _UUID, nullable=False),
        sa.Column("asset_id", _UUID, nullable=False),
        sa.Column("input_key", sa.Text(), nullable=False),
        sa.Column("reference_role", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("generation_id", "input_key", "position", name="pk_generation_inputs"),
        sa.ForeignKeyConstraint(
            ["generation_id"], ["generations.id"],
            name="fk_generation_inputs_generation_id_generations", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_generation_inputs_asset_id_assets", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_generation_inputs_blob_hash_blobs", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("position >= 0", name="ck_generation_inputs_position_nonneg"),
        sa.CheckConstraint("length(input_key) > 0", name="ck_generation_inputs_input_key_nonempty"),
        sa.CheckConstraint(
            "reference_role IS NULL OR (length(reference_role) BETWEEN 1 AND 64 AND length(trim(reference_role)) > 0)",
            name="ck_generation_inputs_reference_role",
        ),
        sa.CheckConstraint("length(blob_hash) = 64", name="ck_generation_inputs_blob_hash_len"),
    )

    # --- indexes (plan §33, §34) -----------------------------------------
    op.create_index("ix_blobs_created_at", "blobs", ["created_at"])
    op.create_index("ix_shots_project_active_number", "shots", ["project_id", "deleted_at", "shot_number"])
    op.create_index("ix_shots_approved_take_id", "shots", ["approved_take_id"])
    op.create_index("ix_shot_references_asset_id", "shot_references", ["asset_id"])
    op.create_index("ix_assets_project_created", "assets", ["project_id", "created_at"])
    op.create_index("ix_assets_take", "assets", ["take_id"])
    op.create_index("ix_assets_blob_hash", "assets", ["blob_hash"])
    op.create_index("ix_takes_shot_created", "takes", ["shot_id", "created_at"])
    op.create_index("ix_generation_inputs_asset_id", "generation_inputs", ["asset_id"])
    op.create_index("ix_generations_queue", "generations", ["status", "queued_at"])
    op.create_index("ix_generations_active_recovery", "generations", ["status", "heartbeat_at"])
    op.create_index("ix_generations_worker_active", "generations", ["worker_id", "status", "heartbeat_at"])


def downgrade() -> None:
    # reverse dependency order
    op.drop_index("ix_generations_worker_active", table_name="generations")
    op.drop_index("ix_generations_active_recovery", table_name="generations")
    op.drop_index("ix_generations_queue", table_name="generations")
    op.drop_index("ix_generation_inputs_asset_id", table_name="generation_inputs")
    op.drop_index("ix_takes_shot_created", table_name="takes")
    op.drop_index("ix_assets_blob_hash", table_name="assets")
    op.drop_index("ix_assets_take", table_name="assets")
    op.drop_index("ix_assets_project_created", table_name="assets")
    op.drop_index("ix_shot_references_asset_id", table_name="shot_references")
    op.drop_index("ix_shots_approved_take_id", table_name="shots")
    op.drop_index("ix_shots_project_active_number", table_name="shots")
    op.drop_index("ix_blobs_created_at", table_name="blobs")

    op.drop_table("generation_inputs")
    op.drop_table("shot_references")
    op.drop_table("assets")
    op.drop_table("takes")
    op.drop_table("generations")
    op.drop_table("shot_revisions")
    op.drop_table("shots")
    op.drop_table("blobs")
    op.drop_table("projects")
