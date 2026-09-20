"""m17a dialogue/vocal foundation

Revision ID: 0018_m17a_dialogue_vocal_foundation
Revises: 0017_m16_intra_shot_consequences
Create Date: 2026-09-19

Frozen M17A R5 §4: exactly seven additive authority/evidence tables.
No predecessor table is altered or rebuilt; no row is backfilled.
Adds exactly three physical Blob-FK paths (candidate audio, VP audio,
alignment evidence). Downgrade refuses before DDL when any M17A row
exists — including a bare DialogueLine with zero revisions.
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_m17a_dialogue_vocal_foundation"
down_revision: Union[str, None] = "0017_m16_intra_shot_consequences"

_M17A_TABLES = (
    "dialogue_alignments",
    "shot_vocal_segment_mappings",
    "vocal_performance_selections",
    "vocal_performance_revisions",
    "vocal_candidates",
    "dialogue_line_revisions",
    "dialogue_lines",
)

_SOURCE_KINDS = "('recorded','adr','imported','generated')"


def _preflight_empty(conn) -> None:
    for table in _M17A_TABLES:
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0018 downgrade refused: {table} contains {n} row(s); "
                "M17A identity intent, authority revisions, candidate "
                "evidence, adoption decisions, current selection, working "
                "timing decisions, and derived evidence are never "
                "destroyed as an incidental schema downgrade")


def upgrade() -> None:
    op.create_table(
        "dialogue_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_dl_project", ondelete="RESTRICT"),
    )
    op.create_index("ix_dl_project_created", "dialogue_lines",
                    ["project_id", "created_at", "id"])

    op.create_table(
        "dialogue_line_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dialogue_line_id", sa.String(36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("speaker_subject_id", sa.String(36), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("wording", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("spec_json", sa.Text(), nullable=False),
        sa.Column("spec_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("revision_number >= 1",
                           name="ck_dlr_revision_number"),
        sa.CheckConstraint("schema_version = 1", name="ck_dlr_schema"),
        sa.CheckConstraint("length(trim(wording)) > 0",
                           name="ck_dlr_wording_nonempty"),
        sa.CheckConstraint("length(spec_hash) = 64",
                           name="ck_dlr_spec_hash_len"),
        sa.CheckConstraint("length(language) <= 64",
                           name="ck_dlr_language_len"),
        sa.UniqueConstraint("dialogue_line_id", "revision_number",
                            name="uq_dlr_line_revision"),
        sa.UniqueConstraint("dialogue_line_id", "spec_hash",
                            name="uq_dlr_line_spec_hash"),
        sa.UniqueConstraint("id", "dialogue_line_id",
                            name="uq_dlr_id_line"),
        sa.ForeignKeyConstraint(["dialogue_line_id"], ["dialogue_lines.id"],
                                name="fk_dlr_line", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["speaker_subject_id"],
                                ["creative_entities.id"],
                                name="fk_dlr_speaker", ondelete="RESTRICT"),
    )
    op.create_index("ix_dlr_line_number", "dialogue_line_revisions",
                    ["dialogue_line_id", "revision_number"])

    op.create_table(
        "vocal_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dialogue_line_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("retained_audio_blob_hash", sa.Text(), nullable=False),
        sa.Column("native_sample_rate_hz", sa.Integer(), nullable=False),
        sa.Column("retained_sample_count", sa.Integer(), nullable=False),
        sa.Column("trim_start_sample", sa.Integer(), nullable=False),
        sa.Column("trim_end_sample_exclusive", sa.Integer(),
                  nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("provenance_schema_version", sa.Integer(),
                  nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("provenance_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(f"source_kind IN {_SOURCE_KINDS}",
                           name="ck_vc_source_kind"),
        sa.CheckConstraint("native_sample_rate_hz > 0",
                           name="ck_vc_rate_positive"),
        sa.CheckConstraint("retained_sample_count > 0",
                           name="ck_vc_samples_positive"),
        sa.CheckConstraint("trim_start_sample >= 0",
                           name="ck_vc_trim_start_nonneg"),
        sa.CheckConstraint(
            "trim_start_sample < trim_end_sample_exclusive",
            name="ck_vc_trim_order"),
        sa.CheckConstraint(
            "trim_end_sample_exclusive <= retained_sample_count",
            name="ck_vc_trim_within_retained"),
        sa.CheckConstraint("length(retained_audio_blob_hash) = 64",
                           name="ck_vc_blob_hash_len"),
        sa.CheckConstraint("length(provenance_hash) = 64",
                           name="ck_vc_provenance_hash_len"),
        sa.CheckConstraint("provenance_schema_version = 1",
                           name="ck_vc_provenance_schema"),
        sa.ForeignKeyConstraint(["dialogue_line_revision_id"],
                                ["dialogue_line_revisions.id"],
                                name="fk_vc_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retained_audio_blob_hash"],
                                ["blobs.hash"],
                                name="fk_vc_blob", ondelete="RESTRICT"),
    )
    op.create_index("ix_vc_revision_created", "vocal_candidates",
                    ["dialogue_line_revision_id", "created_at", "id"])

    op.create_table(
        "vocal_performance_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dialogue_line_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("speaker_subject_id", sa.String(36), nullable=False),
        sa.Column("retained_audio_blob_hash", sa.Text(), nullable=False),
        sa.Column("native_sample_rate_hz", sa.Integer(), nullable=False),
        sa.Column("retained_sample_count", sa.Integer(), nullable=False),
        sa.Column("trim_start_sample", sa.Integer(), nullable=False),
        sa.Column("trim_end_sample_exclusive", sa.Integer(),
                  nullable=False),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("provenance_schema_version", sa.Integer(),
                  nullable=False),
        sa.Column("provenance_json", sa.Text(), nullable=False),
        sa.Column("provenance_hash", sa.Text(), nullable=False),
        sa.Column("adopted_candidate_id", sa.String(36), nullable=False),
        sa.Column("adoption_id", sa.String(36), nullable=False),
        sa.Column("adopted_by", sa.Text(), nullable=False),
        sa.Column("adopted_at", sa.Text(), nullable=False),
        sa.CheckConstraint("revision_number >= 1",
                           name="ck_vpr_revision_number"),
        sa.CheckConstraint(f"source_kind IN {_SOURCE_KINDS}",
                           name="ck_vpr_source_kind"),
        sa.CheckConstraint("native_sample_rate_hz > 0",
                           name="ck_vpr_rate_positive"),
        sa.CheckConstraint("retained_sample_count > 0",
                           name="ck_vpr_samples_positive"),
        sa.CheckConstraint("trim_start_sample >= 0",
                           name="ck_vpr_trim_start_nonneg"),
        sa.CheckConstraint(
            "trim_start_sample < trim_end_sample_exclusive",
            name="ck_vpr_trim_order"),
        sa.CheckConstraint(
            "trim_end_sample_exclusive <= retained_sample_count",
            name="ck_vpr_trim_within_retained"),
        sa.CheckConstraint("length(retained_audio_blob_hash) = 64",
                           name="ck_vpr_blob_hash_len"),
        sa.CheckConstraint("length(provenance_hash) = 64",
                           name="ck_vpr_provenance_hash_len"),
        sa.CheckConstraint("length(trim(adopted_by)) > 0",
                           name="ck_vpr_adopted_by_nonempty"),
        sa.CheckConstraint("provenance_schema_version = 1",
                           name="ck_vpr_provenance_schema"),
        sa.UniqueConstraint("dialogue_line_revision_id", "revision_number",
                            name="uq_vpr_revision_number"),
        sa.UniqueConstraint("adopted_candidate_id",
                            name="uq_vpr_adopted_candidate"),
        sa.UniqueConstraint("adoption_id", name="uq_vpr_adoption_id"),
        sa.UniqueConstraint("id", "dialogue_line_revision_id",
                            name="uq_vpr_id_revision"),
        sa.ForeignKeyConstraint(["dialogue_line_revision_id"],
                                ["dialogue_line_revisions.id"],
                                name="fk_vpr_revision",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["speaker_subject_id"],
                                ["creative_entities.id"],
                                name="fk_vpr_speaker", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retained_audio_blob_hash"],
                                ["blobs.hash"],
                                name="fk_vpr_blob", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["adopted_candidate_id"],
                                ["vocal_candidates.id"],
                                name="fk_vpr_candidate",
                                ondelete="RESTRICT"),
    )
    op.create_index("ix_vpr_revision_number", "vocal_performance_revisions",
                    ["dialogue_line_revision_id", "revision_number"])

    op.create_table(
        "vocal_performance_selections",
        sa.Column("dialogue_line_revision_id", sa.String(36),
                  primary_key=True),
        sa.Column("selected_vocal_performance_revision_id", sa.String(36),
                  nullable=True),
        sa.Column("selected_by", sa.Text(), nullable=True),
        sa.Column("selected_at", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(selected_vocal_performance_revision_id IS NULL "
            "AND selected_by IS NULL AND selected_at IS NULL) OR "
            "(selected_vocal_performance_revision_id IS NOT NULL "
            "AND selected_by IS NOT NULL AND selected_at IS NOT NULL)",
            name="ck_vps_selection_shape"),
        sa.ForeignKeyConstraint(["dialogue_line_revision_id"],
                                ["dialogue_line_revisions.id"],
                                name="fk_vps_revision",
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["selected_vocal_performance_revision_id",
             "dialogue_line_revision_id"],
            ["vocal_performance_revisions.id",
             "vocal_performance_revisions.dialogue_line_revision_id"],
            name="fk_vps_same_line_vp", ondelete="RESTRICT"),
    )

    op.create_table(
        "shot_vocal_segment_mappings",
        sa.Column("shot_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("vocal_performance_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("source_start_sample", sa.Integer(), nullable=False),
        sa.Column("source_end_sample_exclusive", sa.Integer(),
                  nullable=False),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=False),
        sa.Column("performance_origin_num", sa.Integer(),
                  nullable=False),
        sa.Column("performance_origin_den", sa.Integer(),
                  nullable=False),
        sa.Column("shot_anchor_num", sa.Integer(), nullable=False),
        sa.Column("shot_anchor_den", sa.Integer(), nullable=False),
        sa.Column("mapping_schema_version", sa.Integer(), nullable=False),
        sa.Column("mapping_json", sa.Text(), nullable=False),
        sa.Column("mapping_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_svsm_position"),
        sa.CheckConstraint("sample_rate_hz > 0",
                           name="ck_svsm_rate_positive"),
        sa.CheckConstraint("performance_origin_den > 0",
                           name="ck_svsm_origin_den_positive"),
        sa.CheckConstraint("shot_anchor_den > 0",
                           name="ck_svsm_anchor_den_positive"),
        sa.CheckConstraint("source_start_sample >= 0",
                           name="ck_svsm_start_nonneg"),
        sa.CheckConstraint(
            "source_start_sample < source_end_sample_exclusive",
            name="ck_svsm_sample_order"),
        sa.CheckConstraint("mapping_schema_version = 1",
                           name="ck_svsm_mapping_schema"),
        sa.CheckConstraint("length(mapping_hash) = 64",
                           name="ck_svsm_mapping_hash_len"),
        sa.ForeignKeyConstraint(["shot_id"], ["shots.id"],
                                name="fk_svsm_shot", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vocal_performance_revision_id"],
                                ["vocal_performance_revisions.id"],
                                name="fk_svsm_vp", ondelete="RESTRICT"),
    )
    op.create_index("ix_svsm_vp", "shot_vocal_segment_mappings",
                    ["vocal_performance_revision_id"])

    op.create_table(
        "dialogue_alignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("vocal_performance_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("analyzer_id", sa.Text(), nullable=False),
        sa.Column("analyzer_version", sa.Text(), nullable=False),
        sa.Column("model_identity", sa.Text(), nullable=False),
        sa.Column("runtime_identity", sa.Text(), nullable=False),
        sa.Column("parameters_sha256", sa.Text(), nullable=False),
        sa.Column("alignment_schema_version", sa.Integer(),
                  nullable=False),
        sa.Column("retained_blob_hash", sa.Text(), nullable=False),
        sa.Column("retained_sha256", sa.Text(), nullable=False),
        sa.Column("derivation_run_json", sa.Text(), nullable=False),
        sa.Column("derivation_run_hash", sa.Text(), nullable=False),
        sa.Column("derivation_run_identity", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("alignment_schema_version = 1",
                           name="ck_da_alignment_schema"),
        sa.CheckConstraint("length(parameters_sha256) = 64",
                           name="ck_da_parameters_hash_len"),
        sa.CheckConstraint(
            "parameters_sha256 NOT GLOB '*[^0-9a-f]*'",
            name="ck_da_parameters_hash_hex"),
        sa.CheckConstraint("length(retained_blob_hash) = 64",
                           name="ck_da_blob_hash_len"),
        sa.CheckConstraint("length(retained_sha256) = 64",
                           name="ck_da_retained_hash_len"),
        sa.CheckConstraint("retained_sha256 = retained_blob_hash",
                           name="ck_da_retained_equals_blob"),
        sa.CheckConstraint("length(derivation_run_hash) = 64",
                           name="ck_da_run_hash_len"),
        sa.CheckConstraint(
            "length(derivation_run_identity) = 64",
            name="ck_da_run_identity_len"),
        sa.CheckConstraint(
            "derivation_run_identity = derivation_run_hash",
            name="ck_da_run_identity_equals_hash"),
        sa.CheckConstraint("length(trim(analyzer_id)) > 0",
                           name="ck_da_analyzer_id_nonempty"),
        sa.CheckConstraint("length(trim(analyzer_version)) > 0",
                           name="ck_da_analyzer_version_nonempty"),
        sa.CheckConstraint("length(trim(model_identity)) > 0",
                           name="ck_da_model_identity_nonempty"),
        sa.CheckConstraint("length(trim(runtime_identity)) > 0",
                           name="ck_da_runtime_identity_nonempty"),
        sa.ForeignKeyConstraint(["vocal_performance_revision_id"],
                                ["vocal_performance_revisions.id"],
                                name="fk_da_vp", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retained_blob_hash"], ["blobs.hash"],
                                name="fk_da_blob", ondelete="RESTRICT"),
    )
    op.create_index("ix_da_vp_created", "dialogue_alignments",
                    ["vocal_performance_revision_id", "created_at", "id"])


def downgrade() -> None:
    conn = op.get_bind()
    _preflight_empty(conn)
    op.drop_table("dialogue_alignments")
    op.drop_table("shot_vocal_segment_mappings")
    op.drop_table("vocal_performance_selections")
    op.drop_table("vocal_performance_revisions")
    op.drop_table("vocal_candidates")
    op.drop_table("dialogue_line_revisions")
    op.drop_table("dialogue_lines")
