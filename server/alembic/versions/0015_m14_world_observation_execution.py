"""m14 world observation execution provenance

Revision ID: 0015_m14_world_observation_execution
Revises: 0014_m13_authority_complete_world
Create Date: 2026-09-10

Frozen R2 §22/§23: exactly two execution-only tables. No ShotRevision,
M13 authority, ProductionRevision, CompositionRevision, GenerationInput,
or M10 provenance table is altered.

Downgrade (§23.1): fail-closed preflight BEFORE any DDL refuses unless
ALL THREE hold simultaneously:
  * no Generation has workflow_spec_json schema_version = 4
    (M14A-3 can create schema-4 history independently of these tables —
    empty new tables alone must NOT permit 0015 → 0014);
  * generation_derived_observation_inputs is empty;
  * derived_observation_artifacts is empty.
Malformed workflow-spec bytes that prevent proving absence also refuse.
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_m14_world_observation_execution"
down_revision: Union[str, None] = "0014_m13_authority_complete_world"


def _preflight_clear(conn) -> None:
    for table in ("generation_derived_observation_inputs",
                  "derived_observation_artifacts"):
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0015 downgrade refused: {table} contains {n} row(s); "
                "derived observation provenance/history is never destroyed"
            )
    schema4 = conn.execute(sa.text(
        "SELECT COUNT(*) FROM generations WHERE workflow_spec_json IS NULL "
        "OR json_extract(workflow_spec_json, '$.schema_version') = 4"
    )).scalar()
    if schema4:
        raise RuntimeError(
            f"0015 downgrade refused: {schema4} workflow_spec(s) malformed "
            "or schema 4 (M14 observation history is live even with empty "
            "derived tables)")


def upgrade() -> None:
    op.create_table(
        "derived_observation_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("observation_spec_hash", sa.Text(), nullable=False),
        sa.Column("artifact_role", sa.Text(), nullable=False),
        sa.Column("materializer_id", sa.Text(), nullable=False),
        sa.Column("materializer_version", sa.Integer(), nullable=False),
        sa.Column("materializer_contract_hash", sa.Text(), nullable=False),
        sa.Column("parameters_json", sa.Text(), nullable=False),
        sa.Column("parameters_hash", sa.Text(), nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("provenance_hash", sa.Text(), nullable=False),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("length(observation_spec_hash) = 64",
                           name="ck_doa_spec_hash_len"),
        sa.CheckConstraint("artifact_role = 'observation.world_depth'",
                           name="ck_doa_role"),
        sa.CheckConstraint("materializer_version > 0",
                           name="ck_doa_materializer_version"),
        sa.CheckConstraint("length(materializer_contract_hash) = 64",
                           name="ck_doa_contract_hash_len"),
        sa.CheckConstraint("length(parameters_hash) = 64",
                           name="ck_doa_parameters_hash_len"),
        sa.CheckConstraint("length(provenance_hash) = 64",
                           name="ck_doa_provenance_hash_len"),
        sa.CheckConstraint("length(blob_hash) = 64",
                           name="ck_doa_blob_hash_len"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_doa_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["blob_hash"], ["blobs.hash"],
                                name="fk_doa_blob", ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "project_id", "observation_spec_hash", "artifact_role",
            "materializer_id", "materializer_version",
            "materializer_contract_hash", "parameters_hash",
            name="uq_doa_coordinate"),
        sa.UniqueConstraint("id", "blob_hash", name="uq_doa_id_blob"),
    )
    op.create_index("ix_doa_spec", "derived_observation_artifacts",
                    ["observation_spec_hash"])
    op.create_index("ix_doa_blob", "derived_observation_artifacts",
                    ["blob_hash"])
    op.create_index("ix_doa_coordinate", "derived_observation_artifacts",
                    ["project_id", "observation_spec_hash",
                     "materializer_contract_hash"])

    op.create_table(
        "generation_derived_observation_inputs",
        sa.Column("generation_id", sa.String(36), primary_key=True),
        sa.Column("input_key", sa.Text(), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("artifact_role", sa.Text(), nullable=False),
        sa.Column("derived_observation_artifact_id", sa.String(36),
                  nullable=False),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("artifact_role = 'observation.world_depth'",
                           name="ck_gdoi_role"),
        sa.CheckConstraint("position >= 0", name="ck_gdoi_position"),
        sa.CheckConstraint("length(blob_hash) = 64",
                           name="ck_gdoi_blob_hash_len"),
        sa.ForeignKeyConstraint(
            ["generation_id"], ["generations.id"],
            name="fk_gdoi_generation", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["derived_observation_artifact_id", "blob_hash"],
            ["derived_observation_artifacts.id",
             "derived_observation_artifacts.blob_hash"],
            name="fk_gdoi_artifact", ondelete="RESTRICT"),
        sa.UniqueConstraint("generation_id", "input_key",
                            name="uq_gdoi_generation_input_key"),
    )
    op.create_index("ix_gdoi_artifact",
                    "generation_derived_observation_inputs",
                    ["derived_observation_artifact_id"])
    op.create_index("ix_gdoi_blob",
                    "generation_derived_observation_inputs",
                    ["blob_hash"])


def downgrade() -> None:
    conn = op.get_bind()
    _preflight_clear(conn)
    op.drop_index("ix_gdoi_blob",
                  table_name="generation_derived_observation_inputs")
    op.drop_index("ix_gdoi_artifact",
                  table_name="generation_derived_observation_inputs")
    op.drop_table("generation_derived_observation_inputs")
    op.drop_index("ix_doa_coordinate", table_name="derived_observation_artifacts")
    op.drop_index("ix_doa_blob", table_name="derived_observation_artifacts")
    op.drop_index("ix_doa_spec", table_name="derived_observation_artifacts")
    op.drop_table("derived_observation_artifacts")
