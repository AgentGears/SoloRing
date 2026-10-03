"""M17C-C: schema-8 Shot capture storage (frozen R4 sections 10.4-10.6).

Slice 1 is SCHEMA/STORAGE-ONLY by the sequencing contract: this
migration creates the immutable capture companion parent
("shot_revision_performance_specs" section 10.4), the canonical-order
immutable children ("shot_revision_performance_segments" section 10.5), and
the Generation-owned durable derived-input sibling table
("generation_performance_inputs" section 10.6). No capture behavior, no
current-read behavior, no derived-input production, and no sampler
semantics live here - those land with their own slices (section 11/section 12 and
M17C-D).

One new Blob-FK path is introduced (section 13.5):
"generation_performance_inputs.blob_hash -> blobs.hash"; the segment
payload-hash columns are capture-closure duplicates of hashes already
FK-pinned by "performance_candidates"/"performance_revisions" and
carry no independent FK (the section 13.4 verifier resolves them instead).

Downgrade refuses when any of the three tables still carries rows
(captured history and durable derived inputs are not deleted by schema
downgrade).
"""

from alembic import op
import sqlalchemy as sa

revision = "0022_m17c_schema8_capture"
down_revision = "0021_m17c_shot_performance_mappings"
branch_labels = None
depends_on = None

_M17CC_TABLES = (
    "shot_revision_performance_specs",
    "shot_revision_performance_segments",
    "generation_performance_inputs",
)


def upgrade() -> None:
    # section 10.4 - one schema-8 companion parent per ShotRevision
    op.create_table(
        "shot_revision_performance_specs",
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("spec_json", sa.Text(), nullable=False),
        sa.Column("spec_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("schema_version = 1",
                           name="ck_srpfs_schema"),
        sa.CheckConstraint("length(spec_hash) = 64",
                           name="ck_srpfs_hash_len"),
        sa.CheckConstraint("spec_hash NOT GLOB '*[^0-9a-f]*'",
                           name="ck_srpfs_hash_hex"),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpfs_revision", ondelete="RESTRICT"),
    )
    # section 10.5 - immutable canonical-order children; the dialogue-bound
    # vocal group is nullable as ONE all-or-none group
    op.create_table(
        "shot_revision_performance_segments",
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("performance_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("performance_payload_blob_hash", sa.Text(),
                  nullable=False),
        sa.Column("performance_payload_sha256", sa.Text(),
                  nullable=False),
        sa.Column("performance_profile_id", sa.Text(), nullable=False),
        sa.Column("performance_kind", sa.Text(), nullable=False),
        sa.Column("performance_start_num", sa.Integer(), nullable=False),
        sa.Column("performance_start_den", sa.Integer(), nullable=False),
        sa.Column("performance_end_num", sa.Integer(), nullable=False),
        sa.Column("performance_end_den", sa.Integer(), nullable=False),
        sa.Column("shot_anchor_num", sa.Integer(), nullable=False),
        sa.Column("shot_anchor_den", sa.Integer(), nullable=False),
        sa.Column("performance_mapping_hash", sa.Text(), nullable=False),
        sa.Column("vocal_performance_revision_id", sa.String(36),
                  nullable=True),
        sa.Column("vocal_binding_hash", sa.Text(), nullable=True),
        sa.Column("vocal_mapping_hash", sa.Text(), nullable=True),
        sa.Column("source_start_sample", sa.Integer(), nullable=True),
        sa.Column("source_end_sample_exclusive", sa.Integer(),
                  nullable=True),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=True),
        sa.Column("segment_json", sa.Text(), nullable=False),
        sa.Column("segment_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_srpss_position"),
        sa.CheckConstraint(
            "(vocal_performance_revision_id IS NULL "
            "AND vocal_binding_hash IS NULL "
            "AND vocal_mapping_hash IS NULL "
            "AND source_start_sample IS NULL "
            "AND source_end_sample_exclusive IS NULL "
            "AND sample_rate_hz IS NULL) OR "
            "(vocal_performance_revision_id IS NOT NULL "
            "AND vocal_binding_hash IS NOT NULL "
            "AND vocal_mapping_hash IS NOT NULL "
            "AND source_start_sample IS NOT NULL "
            "AND source_end_sample_exclusive IS NOT NULL "
            "AND sample_rate_hz IS NOT NULL)",
            name="ck_srpss_vocal_group_all_or_none"),
        sa.CheckConstraint("length(performance_payload_blob_hash) = 64",
                           name="ck_srpss_payload_hash_len"),
        sa.CheckConstraint("length(vocal_binding_hash) = 64 OR "
                           "vocal_binding_hash IS NULL",
                           name="ck_srpss_binding_hash_len"),
        sa.CheckConstraint("length(segment_hash) = 64",
                           name="ck_srpss_segment_hash_len"),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpss_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["performance_revision_id"], ["performance_revisions.id"],
            name="fk_srpss_pr", ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_srpss_pr", "shot_revision_performance_segments",
        ["performance_revision_id"])
    # section 10.6 - durable Generation-owned derived execution inputs
    op.create_table(
        "generation_performance_inputs",
        sa.Column("generation_id", sa.String(36), primary_key=True),
        sa.Column("input_key", sa.Text(), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("artifact_role", sa.Text(), nullable=False),
        sa.Column("shot_revision_segment_position", sa.Integer(),
                  nullable=False),
        sa.Column("performance_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("vocal_performance_revision_id", sa.String(36),
                  nullable=True),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.Column("binding_hash", sa.Text(), nullable=True),
        sa.Column("segment_hash", sa.Text(), nullable=False),
        sa.Column("translation_identity", sa.Text(), nullable=False),
        sa.Column("derived_input_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "artifact_role IN "
            "('performance.controls', 'performance.vocal_audio')",
            name="ck_gpi_role"),
        sa.CheckConstraint("position >= 0", name="ck_gpi_position"),
        sa.CheckConstraint("length(blob_hash) = 64",
                           name="ck_gpi_blob_hash_len"),
        sa.CheckConstraint("length(binding_hash) = 64 OR "
                           "binding_hash IS NULL",
                           name="ck_gpi_binding_hash_len"),
        sa.CheckConstraint("length(segment_hash) = 64",
                           name="ck_gpi_segment_hash_len"),
        sa.CheckConstraint("length(derived_input_hash) = 64",
                           name="ck_gpi_derived_hash_len"),
        sa.ForeignKeyConstraint(
            ["generation_id"], ["generations.id"],
            name="fk_gpi_generation", ondelete="RESTRICT"),
        # section 13.5: the ONE new Blob-FK path of this migration
        sa.ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_gpi_blob", ondelete="RESTRICT"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    for table in _M17CC_TABLES:
        n = conn.execute(sa.text(
            f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0022 downgrade refused: {table} contains {n} row(s); "
                "M17C-C captured history and durable derived inputs are "
                "not deleted by schema downgrade")
    op.drop_table("generation_performance_inputs")
    op.drop_index("ix_srpss_pr",
                  table_name="shot_revision_performance_segments")
    op.drop_table("shot_revision_performance_segments")
    op.drop_table("shot_revision_performance_specs")
