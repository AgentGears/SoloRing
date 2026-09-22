"""M17A persistence models (frozen R5 §4; migration 0018 parity).

Seven additive tables; every constraint name mirrors the migration
exactly (ORM/migration parity is a plan gate). Rationals are stored as
canonical-reduced (num, den) integer pairs with den > 0; service code
reduces before persistence and the recovery verifier re-validates
canonical form.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from soloring.db.base import Base

_SOURCE_KINDS = "('recorded','adr','imported','generated')"


class DialogueLine(Base):
    __tablename__ = "dialogue_lines"
    __table_args__ = (
        ForeignKeyConstraint(["project_id"], ["projects.id"],
                             name="fk_dl_project", ondelete="RESTRICT"),
        Index("ix_dl_project_created", "project_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class DialogueLineRevision(Base):
    __tablename__ = "dialogue_line_revisions"
    __table_args__ = (
        CheckConstraint("revision_number >= 1",
                        name="ck_dlr_revision_number"),
        CheckConstraint("schema_version = 1", name="ck_dlr_schema"),
        CheckConstraint("length(trim(wording)) > 0",
                        name="ck_dlr_wording_nonempty"),
        CheckConstraint("length(spec_hash) = 64",
                        name="ck_dlr_spec_hash_len"),
        CheckConstraint("length(language) <= 64",
                        name="ck_dlr_language_len"),
        UniqueConstraint("dialogue_line_id", "revision_number",
                         name="uq_dlr_line_revision"),
        UniqueConstraint("dialogue_line_id", "spec_hash",
                         name="uq_dlr_line_spec_hash"),
        UniqueConstraint("id", "dialogue_line_id", name="uq_dlr_id_line"),
        ForeignKeyConstraint(["dialogue_line_id"], ["dialogue_lines.id"],
                             name="fk_dlr_line", ondelete="RESTRICT"),
        ForeignKeyConstraint(["speaker_subject_id"],
                             ["creative_entities.id"],
                             name="fk_dlr_speaker", ondelete="RESTRICT"),
        Index("ix_dlr_line_number", "dialogue_line_id",
              "revision_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dialogue_line_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer,
                                                  nullable=False)
    speaker_subject_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    wording: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer,
                                                 nullable=False)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)
    spec_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class VocalCandidate(Base):
    __tablename__ = "vocal_candidates"
    __table_args__ = (
        CheckConstraint(f"source_kind IN {_SOURCE_KINDS}",
                        name="ck_vc_source_kind"),
        CheckConstraint("native_sample_rate_hz > 0",
                        name="ck_vc_rate_positive"),
        CheckConstraint("retained_sample_count > 0",
                        name="ck_vc_samples_positive"),
        CheckConstraint("trim_start_sample >= 0",
                        name="ck_vc_trim_start_nonneg"),
        CheckConstraint("trim_start_sample < trim_end_sample_exclusive",
                        name="ck_vc_trim_order"),
        CheckConstraint(
            "trim_end_sample_exclusive <= retained_sample_count",
            name="ck_vc_trim_within_retained"),
        CheckConstraint("length(retained_audio_blob_hash) = 64",
                        name="ck_vc_blob_hash_len"),
        CheckConstraint("length(provenance_hash) = 64",
                        name="ck_vc_provenance_hash_len"),
        CheckConstraint("provenance_schema_version = 1",
                        name="ck_vc_provenance_schema"),
        ForeignKeyConstraint(["dialogue_line_revision_id"],
                             ["dialogue_line_revisions.id"],
                             name="fk_vc_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(["retained_audio_blob_hash"], ["blobs.hash"],
                             name="fk_vc_blob", ondelete="RESTRICT"),
        Index("ix_vc_revision_created", "dialogue_line_revision_id",
              "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dialogue_line_revision_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    retained_audio_blob_hash: Mapped[str] = mapped_column(
        Text, nullable=False)
    native_sample_rate_hz: Mapped[int] = mapped_column(
        Integer, nullable=False)
    retained_sample_count: Mapped[int] = mapped_column(
        Integer, nullable=False)
    trim_start_sample: Mapped[int] = mapped_column(Integer,
                                                    nullable=False)
    trim_end_sample_exclusive: Mapped[int] = mapped_column(
        Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text,
                                                  nullable=False)
    provenance_hash: Mapped[str] = mapped_column(Text,
                                                  nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class VocalPerformanceRevision(Base):
    __tablename__ = "vocal_performance_revisions"
    __table_args__ = (
        CheckConstraint("revision_number >= 1",
                        name="ck_vpr_revision_number"),
        CheckConstraint(f"source_kind IN {_SOURCE_KINDS}",
                        name="ck_vpr_source_kind"),
        CheckConstraint("native_sample_rate_hz > 0",
                        name="ck_vpr_rate_positive"),
        CheckConstraint("retained_sample_count > 0",
                        name="ck_vpr_samples_positive"),
        CheckConstraint("trim_start_sample >= 0",
                        name="ck_vpr_trim_start_nonneg"),
        CheckConstraint("trim_start_sample < trim_end_sample_exclusive",
                        name="ck_vpr_trim_order"),
        CheckConstraint(
            "trim_end_sample_exclusive <= retained_sample_count",
            name="ck_vpr_trim_within_retained"),
        CheckConstraint("length(retained_audio_blob_hash) = 64",
                        name="ck_vpr_blob_hash_len"),
        CheckConstraint("length(provenance_hash) = 64",
                        name="ck_vpr_provenance_hash_len"),
        CheckConstraint("length(trim(adopted_by)) > 0",
                        name="ck_vpr_adopted_by_nonempty"),
        CheckConstraint("provenance_schema_version = 1",
                        name="ck_vpr_provenance_schema"),
        UniqueConstraint("dialogue_line_revision_id", "revision_number",
                         name="uq_vpr_revision_number"),
        UniqueConstraint("adopted_candidate_id",
                         name="uq_vpr_adopted_candidate"),
        UniqueConstraint("adoption_id", name="uq_vpr_adoption_id"),
        UniqueConstraint("id", "dialogue_line_revision_id",
                         name="uq_vpr_id_revision"),
        ForeignKeyConstraint(["dialogue_line_revision_id"],
                             ["dialogue_line_revisions.id"],
                             name="fk_vpr_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(["speaker_subject_id"],
                             ["creative_entities.id"],
                             name="fk_vpr_speaker", ondelete="RESTRICT"),
        ForeignKeyConstraint(["retained_audio_blob_hash"], ["blobs.hash"],
                             name="fk_vpr_blob", ondelete="RESTRICT"),
        ForeignKeyConstraint(["adopted_candidate_id"],
                             ["vocal_candidates.id"],
                             name="fk_vpr_candidate", ondelete="RESTRICT"),
        Index("ix_vpr_revision_number", "dialogue_line_revision_id",
              "revision_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dialogue_line_revision_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer,
                                                  nullable=False)
    speaker_subject_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    retained_audio_blob_hash: Mapped[str] = mapped_column(
        Text, nullable=False)
    native_sample_rate_hz: Mapped[int] = mapped_column(
        Integer, nullable=False)
    retained_sample_count: Mapped[int] = mapped_column(
        Integer, nullable=False)
    trim_start_sample: Mapped[int] = mapped_column(Integer,
                                                    nullable=False)
    trim_end_sample_exclusive: Mapped[int] = mapped_column(
        Integer, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text,
                                                  nullable=False)
    provenance_hash: Mapped[str] = mapped_column(Text,
                                                  nullable=False)
    adopted_candidate_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    adoption_id: Mapped[str] = mapped_column(String(36),
                                              nullable=False)
    adopted_by: Mapped[str] = mapped_column(Text, nullable=False)
    adopted_at: Mapped[str] = mapped_column(Text, nullable=False)


class VocalPerformanceSelection(Base):
    __tablename__ = "vocal_performance_selections"
    __table_args__ = (
        CheckConstraint(
            "(selected_vocal_performance_revision_id IS NULL "
            "AND selected_by IS NULL AND selected_at IS NULL) OR "
            "(selected_vocal_performance_revision_id IS NOT NULL "
            "AND selected_by IS NOT NULL AND selected_at IS NOT NULL)",
            name="ck_vps_selection_shape"),
        ForeignKeyConstraint(["dialogue_line_revision_id"],
                             ["dialogue_line_revisions.id"],
                             name="fk_vps_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["selected_vocal_performance_revision_id",
             "dialogue_line_revision_id"],
            ["vocal_performance_revisions.id",
             "vocal_performance_revisions.dialogue_line_revision_id"],
            name="fk_vps_same_line_vp", ondelete="RESTRICT"),
    )

    dialogue_line_revision_id: Mapped[str] = mapped_column(
        String(36), primary_key=True)
    selected_vocal_performance_revision_id: Mapped[str | None] = \
        mapped_column(String(36), nullable=True)
    selected_by: Mapped[str | None] = mapped_column(Text,
                                                     nullable=True)
    selected_at: Mapped[str | None] = mapped_column(Text,
                                                     nullable=True)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class ShotVocalSegmentMapping(Base):
    __tablename__ = "shot_vocal_segment_mappings"
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_svsm_position"),
        CheckConstraint("sample_rate_hz > 0",
                        name="ck_svsm_rate_positive"),
        CheckConstraint("performance_origin_den > 0",
                        name="ck_svsm_origin_den_positive"),
        CheckConstraint("shot_anchor_den > 0",
                        name="ck_svsm_anchor_den_positive"),
        CheckConstraint("source_start_sample >= 0",
                        name="ck_svsm_start_nonneg"),
        CheckConstraint(
            "source_start_sample < source_end_sample_exclusive",
            name="ck_svsm_sample_order"),
        CheckConstraint("mapping_schema_version = 1",
                        name="ck_svsm_mapping_schema"),
        CheckConstraint("length(mapping_hash) = 64",
                        name="ck_svsm_mapping_hash_len"),
        ForeignKeyConstraint(["shot_id"], ["shots.id"],
                             name="fk_svsm_shot", ondelete="RESTRICT"),
        ForeignKeyConstraint(["vocal_performance_revision_id"],
                             ["vocal_performance_revisions.id"],
                             name="fk_svsm_vp", ondelete="RESTRICT"),
        Index("ix_svsm_vp", "vocal_performance_revision_id"),
    )

    shot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    vocal_performance_revision_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    source_start_sample: Mapped[int] = mapped_column(
        Integer, nullable=False)
    source_end_sample_exclusive: Mapped[int] = mapped_column(
        Integer, nullable=False)
    sample_rate_hz: Mapped[int] = mapped_column(Integer,
                                                 nullable=False)
    performance_origin_num: Mapped[int] = mapped_column(
        Integer, nullable=False)
    performance_origin_den: Mapped[int] = mapped_column(
        Integer, nullable=False)
    shot_anchor_num: Mapped[int] = mapped_column(Integer,
                                                  nullable=False)
    shot_anchor_den: Mapped[int] = mapped_column(Integer,
                                                  nullable=False)
    mapping_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False)
    mapping_json: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class DialogueAlignment(Base):
    __tablename__ = "dialogue_alignments"
    __table_args__ = (
        CheckConstraint("alignment_schema_version = 1",
                        name="ck_da_alignment_schema"),
        CheckConstraint("length(parameters_sha256) = 64",
                        name="ck_da_parameters_hash_len"),
        CheckConstraint("parameters_sha256 NOT GLOB '*[^0-9a-f]*'",
                        name="ck_da_parameters_hash_hex"),
        CheckConstraint("length(retained_blob_hash) = 64",
                        name="ck_da_blob_hash_len"),
        CheckConstraint("length(retained_sha256) = 64",
                        name="ck_da_retained_hash_len"),
        CheckConstraint("retained_sha256 = retained_blob_hash",
                        name="ck_da_retained_equals_blob"),
        CheckConstraint("length(derivation_run_hash) = 64",
                        name="ck_da_run_hash_len"),
        CheckConstraint("length(derivation_run_identity) = 64",
                        name="ck_da_run_identity_len"),
        CheckConstraint("derivation_run_identity = derivation_run_hash",
                        name="ck_da_run_identity_equals_hash"),
        CheckConstraint("length(trim(analyzer_id)) > 0",
                        name="ck_da_analyzer_id_nonempty"),
        CheckConstraint("length(trim(analyzer_version)) > 0",
                        name="ck_da_analyzer_version_nonempty"),
        CheckConstraint("length(trim(model_identity)) > 0",
                        name="ck_da_model_identity_nonempty"),
        CheckConstraint("length(trim(runtime_identity)) > 0",
                        name="ck_da_runtime_identity_nonempty"),
        ForeignKeyConstraint(["vocal_performance_revision_id"],
                             ["vocal_performance_revisions.id"],
                             name="fk_da_vp", ondelete="RESTRICT"),
        ForeignKeyConstraint(["retained_blob_hash"], ["blobs.hash"],
                             name="fk_da_blob", ondelete="RESTRICT"),
        Index("ix_da_vp_created", "vocal_performance_revision_id",
              "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    vocal_performance_revision_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    analyzer_id: Mapped[str] = mapped_column(Text, nullable=False)
    analyzer_version: Mapped[str] = mapped_column(Text,
                                                   nullable=False)
    model_identity: Mapped[str] = mapped_column(Text,
                                                  nullable=False)
    runtime_identity: Mapped[str] = mapped_column(Text,
                                                    nullable=False)
    parameters_sha256: Mapped[str] = mapped_column(Text,
                                                    nullable=False)
    alignment_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False)
    retained_blob_hash: Mapped[str] = mapped_column(Text,
                                                     nullable=False)
    retained_sha256: Mapped[str] = mapped_column(Text,
                                                  nullable=False)
    derivation_run_json: Mapped[str] = mapped_column(Text,
                                                      nullable=False)
    derivation_run_hash: Mapped[str] = mapped_column(Text,
                                                     nullable=False)
    derivation_run_identity: Mapped[str] = mapped_column(Text,
                                                         nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
