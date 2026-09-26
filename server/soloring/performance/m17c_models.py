"""M17C additive dialogue-bound Performance synchronization companions.

These tables do not alter M17B PerformanceCandidate/PerformanceRevision
semantics.  A row is present only for dialogue-bound FACIAL/BODY_FACIAL
performance.  Candidate and adopted-revision bindings are immutable semantic
companions whose canonical bytes/hash are revalidated at every authority
transition.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from soloring.db.base import Base


class PerformanceCandidateVocalBinding(Base):
    __tablename__ = "performance_candidate_vocal_bindings"
    __table_args__ = (
        CheckConstraint("source_start_sample >= 0",
                        name="ck_pcvb_start_nonneg"),
        CheckConstraint(
            "source_start_sample < source_end_sample_exclusive",
            name="ck_pcvb_sample_order"),
        CheckConstraint("sample_rate_hz > 0",
                        name="ck_pcvb_rate_positive"),
        CheckConstraint("performance_origin_den > 0",
                        name="ck_pcvb_origin_den_positive"),
        CheckConstraint("synchronization_basis_version = 1",
                        name="ck_pcvb_sync_basis"),
        CheckConstraint("binding_schema_version = 1",
                        name="ck_pcvb_schema"),
        CheckConstraint(
            "length(binding_hash) = 64 AND "
            "binding_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_pcvb_hash_hex"),
        ForeignKeyConstraint(
            ["performance_candidate_id"], ["performance_candidates.id"],
            name="fk_pcvb_candidate", ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["vocal_performance_revision_id"],
            ["vocal_performance_revisions.id"],
            name="fk_pcvb_vp", ondelete="RESTRICT"),
    )

    performance_candidate_id: Mapped[str] = mapped_column(
        String(36), primary_key=True)
    vocal_performance_revision_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    source_start_sample: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end_sample_exclusive: Mapped[int] = mapped_column(
        Integer, nullable=False)
    sample_rate_hz: Mapped[int] = mapped_column(Integer, nullable=False)
    performance_origin_num: Mapped[int] = mapped_column(Integer, nullable=False)
    performance_origin_den: Mapped[int] = mapped_column(Integer, nullable=False)
    synchronization_basis_version: Mapped[int] = mapped_column(
        Integer, nullable=False)
    binding_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_json: Mapped[str] = mapped_column(Text, nullable=False)
    binding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class PerformanceRevisionVocalBinding(Base):
    __tablename__ = "performance_revision_vocal_bindings"
    __table_args__ = (
        CheckConstraint("source_start_sample >= 0",
                        name="ck_prvb_start_nonneg"),
        CheckConstraint(
            "source_start_sample < source_end_sample_exclusive",
            name="ck_prvb_sample_order"),
        CheckConstraint("sample_rate_hz > 0",
                        name="ck_prvb_rate_positive"),
        CheckConstraint("performance_origin_den > 0",
                        name="ck_prvb_origin_den_positive"),
        CheckConstraint("synchronization_basis_version = 1",
                        name="ck_prvb_sync_basis"),
        CheckConstraint("binding_schema_version = 1",
                        name="ck_prvb_schema"),
        CheckConstraint(
            "length(binding_hash) = 64 AND "
            "binding_hash NOT GLOB '*[^0-9a-f]*'",
            name="ck_prvb_hash_hex"),
        ForeignKeyConstraint(
            ["performance_revision_id"], ["performance_revisions.id"],
            name="fk_prvb_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["vocal_performance_revision_id"],
            ["vocal_performance_revisions.id"],
            name="fk_prvb_vp", ondelete="RESTRICT"),
    )

    performance_revision_id: Mapped[str] = mapped_column(
        String(36), primary_key=True)
    vocal_performance_revision_id: Mapped[str] = mapped_column(
        String(36), nullable=False)
    source_start_sample: Mapped[int] = mapped_column(Integer, nullable=False)
    source_end_sample_exclusive: Mapped[int] = mapped_column(
        Integer, nullable=False)
    sample_rate_hz: Mapped[int] = mapped_column(Integer, nullable=False)
    performance_origin_num: Mapped[int] = mapped_column(Integer, nullable=False)
    performance_origin_den: Mapped[int] = mapped_column(Integer, nullable=False)
    synchronization_basis_version: Mapped[int] = mapped_column(
        Integer, nullable=False)
    binding_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_json: Mapped[str] = mapped_column(Text, nullable=False)
    binding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class PerformanceCandidateSyncClassification(Base):
    """SR26-01 corrective: immutable PF-03 applicability discriminator.

    One row per PerformanceCandidate, independent of the optional
    binding payload, so total companion loss can never be reinterpreted
    as generic M17B history. NONE prohibits a binding row; VOCAL_V1
    requires exactly one.
    """

    __tablename__ = "performance_candidate_sync_classifications"
    __table_args__ = (
        CheckConstraint("sync_mode IN ('NONE', 'VOCAL_V1')",
                        name="ck_pcsc_mode"),
        CheckConstraint("classification_schema_version = 1",
                        name="ck_pcsc_schema"),
        ForeignKeyConstraint(
            ["performance_candidate_id"], ["performance_candidates.id"],
            name="fk_pcsc_parent", ondelete='RESTRICT'),
    )

    performance_candidate_id: Mapped[str] = mapped_column(
        String(36), primary_key=True)
    sync_mode: Mapped[str] = mapped_column(Text, nullable=False)
    classification_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class PerformanceRevisionSyncClassification(Base):
    """SR26-01 corrective: revision-side applicability discriminator.

    Copied from the adopted candidate classification at adoption,
    independently of the binding payload.
    """

    __tablename__ = "performance_revision_sync_classifications"
    __table_args__ = (
        CheckConstraint("sync_mode IN ('NONE', 'VOCAL_V1')",
                        name="ck_prsc_mode"),
        CheckConstraint("classification_schema_version = 1",
                        name="ck_prsc_schema"),
        ForeignKeyConstraint(
            ["performance_revision_id"], ["performance_revisions.id"],
            name="fk_prsc_parent", ondelete='RESTRICT'),
    )

    performance_revision_id: Mapped[str] = mapped_column(
        String(36), primary_key=True)
    sync_mode: Mapped[str] = mapped_column(Text, nullable=False)
    classification_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
