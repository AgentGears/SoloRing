"""m10 derived spatial execution provenance

Revision ID: 0011_m10_derived_spatial_execution
Revises: 0010_m10_spatial_cinematic_continuity
Create Date: 2026-08-23

Frozen r3 plan §102: exactly two execution/provenance tables. No Asset.kind
change, no nullable rewrite of generation_inputs.asset_id, no derived columns
on M10 authority tables.

Downgrade (§102.3): fail-closed preflight BEFORE any DDL refuses when either
0011 table has rows, any workflow-spec references derived spatial provenance,
or malformed workflow-spec bytes prevent proving absence. Only an unused 0011
schema can be dropped. 0010→0009 is not attempted while 0011 is applied.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_m10_derived_spatial_execution"
down_revision: Union[str, None] = "0010_m10_spatial_cinematic_continuity"


def _preflight_clear(conn) -> None:
    for table in ("generation_derived_spatial_inputs", "derived_spatial_artifacts"):
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0011 downgrade refused: {table} contains {n} row(s); "
                "derived execution provenance/history is never destroyed"
            )
    bad = conn.execute(sa.text(
        "SELECT COUNT(*) FROM generations WHERE workflow_spec_json IS NULL "
        "OR json_extract(workflow_spec_json, '$.schema_version') >= 3"
    )).scalar()
    if bad:
        raise RuntimeError(
            f"0011 downgrade refused: {bad} workflow_spec(s) malformed or "
            "schema >= 3 (may reference derived provenance)"
        )


def upgrade() -> None:
    op.create_table(
        "derived_spatial_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("spec_schema_version", sa.Integer(), nullable=False),
        sa.Column("spec_json", sa.Text(), nullable=False),
        sa.Column("spec_hash", sa.Text(), nullable=False),
        sa.Column("spatial_continuity_schema_version", sa.Integer(), nullable=False),
        sa.Column("spatial_continuity_hash", sa.Text(), nullable=False),
        sa.Column("artifact_kind", sa.Text(), nullable=False),
        sa.Column("artifact_schema_version", sa.Integer(), nullable=False),
        sa.Column("algorithm_id", sa.Text(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("runtime_fingerprint_json", sa.Text(), nullable=False),
        sa.Column("runtime_fingerprint_hash", sa.Text(), nullable=False),
        sa.Column("determinism_class", sa.Text(), nullable=False),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("spec_schema_version = 1", name="ck_dsa_spec_schema"),
        sa.CheckConstraint("length(spec_hash) = 64", name="ck_dsa_spec_hash_len"),
        sa.CheckConstraint("spatial_continuity_schema_version = 1", name="ck_dsa_continuity_schema"),
        sa.CheckConstraint("length(spatial_continuity_hash) = 64", name="ck_dsa_continuity_hash_len"),
        sa.CheckConstraint("artifact_schema_version > 0", name="ck_dsa_artifact_schema"),
        sa.CheckConstraint("length(runtime_fingerprint_hash) = 64", name="ck_dsa_fp_hash_len"),
        sa.CheckConstraint("determinism_class = 'D0'", name="ck_dsa_d0_only"),
        sa.CheckConstraint("length(blob_hash) = 64", name="ck_dsa_blob_hash_len"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_dsa_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["blob_hash"], ["blobs.hash"], name="fk_dsa_blob", ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "spec_hash", "runtime_fingerprint_hash", name="uq_dsa_project_spec_runtime"),
        sa.UniqueConstraint("id", "blob_hash", name="uq_dsa_id_blob"),
    )
    op.create_index("ix_dsa_spec_runtime", "derived_spatial_artifacts", ["spec_hash", "runtime_fingerprint_hash"])
    op.create_index("ix_dsa_project_continuity", "derived_spatial_artifacts", ["project_id", "spatial_continuity_hash"])
    op.create_index("ix_dsa_blob", "derived_spatial_artifacts", ["blob_hash"])

    op.create_table(
        "generation_derived_spatial_inputs",
        sa.Column("generation_id", sa.String(36), primary_key=True),
        sa.Column("input_key", sa.Text(), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("artifact_role", sa.Text(), nullable=False),
        sa.Column("derived_spatial_artifact_id", sa.String(36), nullable=False),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_gdsi_position"),
        sa.CheckConstraint("length(blob_hash) = 64", name="ck_gdsi_blob_hash_len"),
        sa.ForeignKeyConstraint(["generation_id"], ["generations.id"], name="fk_gdsi_generation", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["derived_spatial_artifact_id", "blob_hash"], ["derived_spatial_artifacts.id", "derived_spatial_artifacts.blob_hash"], name="fk_gdsi_artifact", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["blob_hash"], ["blobs.hash"], name="fk_gdsi_blob", ondelete="RESTRICT"),
        sa.UniqueConstraint("generation_id", "artifact_role", "position", name="uq_gdsi_gen_role_position"),
    )
    op.create_index("ix_gdsi_artifact", "generation_derived_spatial_inputs", ["derived_spatial_artifact_id"])
    op.create_index("ix_gdsi_blob", "generation_derived_spatial_inputs", ["blob_hash"])


def downgrade() -> None:
    conn = op.get_bind()
    _preflight_clear(conn)
    op.drop_table("generation_derived_spatial_inputs")
    op.drop_table("derived_spatial_artifacts")
