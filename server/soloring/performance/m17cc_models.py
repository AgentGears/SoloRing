"""M17C-C schema-8 capture storage models (frozen R4 §§10.4-10.6).

Slice 1 is SCHEMA/STORAGE-ONLY: the immutable capture companion parent,
the canonical-order immutable segment children, and the Generation-owned
durable derived-input sibling rows. No capture/read/production behavior
lives here (later slices own §11 capture, §12 history, and M17C-D the
derived-input writer).
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from soloring.db.base import Base


class ShotRevisionPerformanceSpec(Base):
    """§10.4: one schema-8 companion parent per ShotRevision containing
    a Performance plane (canonical spec bytes/hash)."""

    __tablename__ = "shot_revision_performance_specs"
    __table_args__ = (
        CheckConstraint("schema_version = 1", name="ck_srpfs_schema"),
        CheckConstraint("length(spec_hash) = 64",
                        name="ck_srpfs_hash_len"),
        CheckConstraint("spec_hash NOT GLOB '*[^0-9a-f]*'",
                        name="ck_srpfs_hash_hex"),
        ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpfs_revision", ondelete="RESTRICT"),
    )

    shot_revision_id: Mapped[str] = mapped_column(
        String(36), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer,
                                                nullable=False)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)
    spec_hash: Mapped[str] = mapped_column(Text, nullable=False)


class ShotRevisionPerformanceSegment(Base):
    """§10.5: immutable canonical-order capture children. The
    duplicated immutable hashes are capture closure, not new authority;
    the dialogue-bound vocal group is nullable as ONE all-or-none
    group."""

    __tablename__ = "shot_revision_performance_segments"
    # ISR2-M17CC-02: the CHECK declarations follow the EXACT order of
    # the 0023 migration's DDL so the stored sqlite_master form is
    # deterministic across the ORM (create_all) and alembic engines —
    # the ordered CHECK multiset is part of the frozen physical
    # contract the recovery verifier proves
    __table_args__ = (
        CheckConstraint("position >= 0", name="ck_srpss_position"),
        CheckConstraint(
            "(vocal_performance_revision_id IS NULL "
            "AND vocal_binding_hash IS NULL "
            "AND vocal_mapping_hash IS NULL "
            "AND source_start_sample IS NULL "
            "AND source_end_sample_exclusive IS NULL "
            "AND sample_rate_hz IS NULL "
            "AND vocal_performance_origin_num IS NULL "
            "AND vocal_performance_origin_den IS NULL "
            "AND vocal_mapping_position IS NULL) OR "
            "(vocal_performance_revision_id IS NOT NULL "
            "AND vocal_binding_hash IS NOT NULL "
            "AND vocal_mapping_hash IS NOT NULL "
            "AND source_start_sample IS NOT NULL "
            "AND source_end_sample_exclusive IS NOT NULL "
            "AND sample_rate_hz IS NOT NULL "
            "AND vocal_performance_origin_num IS NOT NULL "
            "AND vocal_performance_origin_den IS NOT NULL "
            "AND vocal_mapping_position IS NOT NULL)",
            name="ck_srpss_vocal_group_all_or_none"),
        CheckConstraint(
            "length(performance_payload_blob_hash) = 64",
            name="ck_srpss_payload_hash_len"),
        CheckConstraint(
            "length(vocal_binding_hash) = 64 OR vocal_binding_hash IS "
            "NULL", name="ck_srpss_binding_hash_len"),
        CheckConstraint("length(segment_hash) = 64",
                        name="ck_srpss_segment_hash_len"),
        # FPR-M17CC-04: the captured mapping-document preimage
        CheckConstraint(
            "vocal_mapping_position >= 0 OR vocal_mapping_position "
            "IS NULL", name="ck_srpss_vocal_position"),
        CheckConstraint(
            "vocal_performance_origin_den > 0 OR "
            "vocal_performance_origin_den IS NULL",
            name="ck_srpss_vocal_origin_den"),
        ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpss_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["performance_revision_id"], ["performance_revisions.id"],
            name="fk_srpss_pr", ondelete="RESTRICT"),
        Index("ix_srpss_pr", "performance_revision_id"),
    )

    shot_revision_id: Mapped[str] = mapped_column(
        String(36), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(36),
                                            nullable=False)
    performance_revision_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    performance_payload_blob_hash: Mapped[str] = mapped_column(
        Text, nullable=False)
    performance_payload_sha256: Mapped[str] = mapped_column(
        Text, nullable=False)
    performance_profile_id: Mapped[str] = mapped_column(
        Text, nullable=False)
    performance_kind: Mapped[str] = mapped_column(Text,
                                                  nullable=False)
    performance_start_num: Mapped[int] = mapped_column(
        Integer, nullable=False)
    performance_start_den: Mapped[int] = mapped_column(
        Integer, nullable=False)
    performance_end_num: Mapped[int] = mapped_column(
        Integer, nullable=False)
    performance_end_den: Mapped[int] = mapped_column(
        Integer, nullable=False)
    shot_anchor_num: Mapped[int] = mapped_column(Integer,
                                                  nullable=False)
    shot_anchor_den: Mapped[int] = mapped_column(Integer,
                                                  nullable=False)
    performance_mapping_hash: Mapped[str] = mapped_column(
        Text, nullable=False)
    vocal_performance_revision_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True)
    vocal_binding_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True)
    vocal_mapping_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True)
    source_start_sample: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    source_end_sample_exclusive: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    sample_rate_hz: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    vocal_performance_origin_num: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    vocal_performance_origin_den: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    vocal_mapping_position: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    segment_json: Mapped[str] = mapped_column(Text, nullable=False)
    segment_hash: Mapped[str] = mapped_column(Text, nullable=False)


class GenerationPerformanceInput(Base):
    """§10.6: durable Generation-owned derived execution inputs — the
    translated control schedule and the exact materialized audio track
    as hash-pinned sibling bindings tying back to the captured schema-8
    segment. Derivation/execution data, never A7 authority. The WRITER
    is M17C-D work; this slice owns storage only."""

    __tablename__ = "generation_performance_inputs"
    __table_args__ = (
        CheckConstraint(
            "artifact_role IN "
            "('performance.controls', 'performance.vocal_audio')",
            name="ck_gpi_role"),
        CheckConstraint("position >= 0", name="ck_gpi_position"),
        CheckConstraint("length(blob_hash) = 64",
                        name="ck_gpi_blob_hash_len"),
        CheckConstraint(
            "length(binding_hash) = 64 OR binding_hash IS NULL",
            name="ck_gpi_binding_hash_len"),
        CheckConstraint("length(segment_hash) = 64",
                        name="ck_gpi_segment_hash_len"),
        CheckConstraint("length(derived_input_hash) = 64",
                        name="ck_gpi_derived_hash_len"),
        ForeignKeyConstraint(
            ["generation_id"], ["generations.id"],
            name="fk_gpi_generation", ondelete="RESTRICT"),
        # §13.5: the ONE new Blob-FK path introduced by this migration
        ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_gpi_blob", ondelete="RESTRICT"),
    )

    generation_id: Mapped[str] = mapped_column(
        String(36), primary_key=True)
    input_key: Mapped[str] = mapped_column(Text, primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    artifact_role: Mapped[str] = mapped_column(Text, nullable=False)
    shot_revision_segment_position: Mapped[int] = mapped_column(
        Integer, nullable=False)
    performance_revision_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    vocal_performance_revision_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True)
    blob_hash: Mapped[str] = mapped_column(Text, nullable=False)
    binding_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True)
    segment_hash: Mapped[str] = mapped_column(Text, nullable=False)
    translation_identity: Mapped[str] = mapped_column(
        Text, nullable=False)
    derived_input_hash: Mapped[str] = mapped_column(
        Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
