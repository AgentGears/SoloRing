"""ORM models: Composition authority (frozen M12 R3 §4).

Ten tables: two mutable authoring tables (compositions,
composition_working_occurrences) and eight immutable authority/history
tables. Composite FKs to composition_occurrences(id, composition_id) prove
lineage coherence; the working table intentionally has NO second direct
scalar FK to compositions.id (frozen §4.4 — preserve, do not "repair").
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

_SOURCE_XOR = (
    "(source_kind='production_revision' "
    "AND production_revision_id IS NOT NULL "
    "AND nested_composition_revision_id IS NULL) "
    "OR (source_kind='composition_revision' "
    "AND production_revision_id IS NULL "
    "AND nested_composition_revision_id IS NOT NULL)"
)


class Composition(Base):
    """Stable reusable assembly identity with independent optimistic tokens."""

    __tablename__ = "compositions"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_compositions"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_compositions_project_id_projects", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 500",
            name="name_len",
        ),
        CheckConstraint("metadata_version >= 0", name="metadata_version"),
        CheckConstraint("working_version >= 0", name="working_version"),
        Index("ix_compositions_project_created", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(UUID)
    project_id: Mapped[str] = mapped_column(UUID, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_version: Mapped[int] = mapped_column(Integer, nullable=False)
    working_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class CompositionOccurrence(Base):
    """Stable occurrence identity; no mutable configuration lives here."""

    __tablename__ = "composition_occurrences"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_composition_occurrences"),
        ForeignKeyConstraint(
            ["composition_id"], ["compositions.id"],
            name="fk_composition_occurrences_composition", ondelete="RESTRICT",
        ),
        # Intentionally redundant with the id PK so child composite FKs can
        # prove lineage coherence (frozen §4.2).
        UniqueConstraint("id", "composition_id", name="uq_composition_occurrences_id_comp"),
        Index(
            "ix_composition_occurrences_comp_created", "composition_id", "created_at"
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class CompositionRevision(Base):
    """Immutable published Composition Revision."""

    __tablename__ = "composition_revisions"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_composition_revisions"),
        ForeignKeyConstraint(
            ["composition_id"], ["compositions.id"],
            name="fk_composition_revisions_composition", ondelete="RESTRICT",
        ),
        CheckConstraint("revision_number >= 1", name="number_pos"),
        CheckConstraint(
            "length(snapshot_hash) = 64", name="hash_len"
        ),
        UniqueConstraint(
            "composition_id", "revision_number",
            name="uq_composition_revisions_comp_number",
        ),
        UniqueConstraint(
            "composition_id", "snapshot_hash",
            name="uq_composition_revisions_comp_hash",
        ),
        UniqueConstraint("id", "composition_id", name="uq_composition_revisions_id_comp"),
        Index(
            "ix_composition_revisions_comp_created", "composition_id", "created_at"
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class CompositionWorkingOccurrence(Base):
    """Current mutable membership/configuration of one stable occurrence."""

    __tablename__ = "composition_working_occurrences"

    __table_args__ = (
        PrimaryKeyConstraint(
            "composition_id", "occurrence_id",
            name="pk_composition_working_occurrences",
        ),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_cwo_occurrence", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_cwo_production_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["nested_composition_revision_id"], ["composition_revisions.id"],
            name="fk_cwo_nested_revision", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(trim(display_name)) BETWEEN 1 AND 500",
            name="display_name_len",
        ),
        CheckConstraint("visible IN (0,1)", name="visible"),
        CheckConstraint(_SOURCE_XOR, name="source_xor"),
        Index(
            "ix_cwo_production_revision", "production_revision_id",
            sqlite_where=text("production_revision_id IS NOT NULL"),
        ),
        Index(
            "ix_cwo_nested_revision", "nested_composition_revision_id",
            sqlite_where=text("nested_composition_revision_id IS NOT NULL"),
        ),
    )

    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    production_revision_id: Mapped[str | None] = mapped_column(UUID)
    nested_composition_revision_id: Mapped[str | None] = mapped_column(UUID)
    visible: Mapped[int] = mapped_column(Integer, nullable=False)
    x_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    y_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    z_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    yaw_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    pitch_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    roll_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class CompositionRevisionOccurrence(Base):
    """Immutable normalized projection of the published occurrence list."""

    __tablename__ = "composition_revision_occurrences"

    __table_args__ = (
        PrimaryKeyConstraint(
            "composition_revision_id", "occurrence_id",
            name="pk_composition_revision_occurrences",
        ),
        ForeignKeyConstraint(
            ["composition_revision_id", "composition_id"],
            ["composition_revisions.id", "composition_revisions.composition_id"],
            name="fk_cro_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_cro_occurrence", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_cro_production_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["nested_composition_revision_id"], ["composition_revisions.id"],
            name="fk_cro_nested_revision", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(trim(display_name)) BETWEEN 1 AND 500",
            name="display_name_len",
        ),
        CheckConstraint("visible IN (0,1)", name="visible"),
        CheckConstraint(_SOURCE_XOR, name="source_xor"),
    )

    composition_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    production_revision_id: Mapped[str | None] = mapped_column(UUID)
    nested_composition_revision_id: Mapped[str | None] = mapped_column(UUID)
    visible: Mapped[int] = mapped_column(Integer, nullable=False)
    x_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    y_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    z_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    yaw_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    pitch_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    roll_udeg: Mapped[int] = mapped_column(Integer, nullable=False)


class CompositionRevisionProductionDependency(Base):
    """Flattened exact Production Revision closure."""

    __tablename__ = "composition_revision_production_dependencies"

    __table_args__ = (
        PrimaryKeyConstraint(
            "composition_revision_id", "production_revision_id",
            name="pk_composition_revision_production_dependencies",
        ),
        ForeignKeyConstraint(
            ["composition_revision_id"], ["composition_revisions.id"],
            name="fk_crpd_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_crpd_production_revision", ondelete="RESTRICT",
        ),
        Index("ix_crpd_production_revision", "production_revision_id"),
    )

    composition_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    production_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)


class CompositionRevisionNestedDependency(Base):
    """Flattened exact nested Composition Revision closure."""

    __tablename__ = "composition_revision_nested_dependencies"

    __table_args__ = (
        PrimaryKeyConstraint(
            "composition_revision_id", "nested_composition_revision_id",
            name="pk_composition_revision_nested_dependencies",
        ),
        ForeignKeyConstraint(
            ["composition_revision_id"], ["composition_revisions.id"],
            name="fk_crnd_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["nested_composition_revision_id"], ["composition_revisions.id"],
            name="fk_crnd_nested_revision", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "composition_revision_id <> nested_composition_revision_id",
            name="no_self",
        ),
        Index("ix_crnd_nested_revision", "nested_composition_revision_id"),
    )

    composition_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    nested_composition_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)


class CompositionIdentityOperation(Base):
    """Immutable occurrence-identity lineage event."""

    __tablename__ = "composition_identity_operations"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_composition_identity_operations"),
        ForeignKeyConstraint(
            ["composition_id"], ["compositions.id"],
            name="fk_cio_composition", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "operation_kind IN ('mint','remove','replace_as_new','split','merge','fork')",
            name="operation_kind_domain",
        ),
        CheckConstraint(
            "working_version_before >= 0", name="before_nonneg"
        ),
        CheckConstraint(
            "working_version_after = working_version_before + 1",
            name="version_step",
        ),
        CheckConstraint(
            "length(request_fingerprint) = 64", name="request_fp_len"
        ),
        CheckConstraint(
            "length(impact_fingerprint) = 64", name="impact_fp_len"
        ),
        CheckConstraint(
            "length(operation_hash) = 64", name="operation_hash_len"
        ),
        UniqueConstraint("id", "composition_id", name="uq_cio_id_comp"),
        UniqueConstraint("composition_id", "operation_hash", name="uq_cio_comp_hash"),
        UniqueConstraint(
            "composition_id", "working_version_before", name="uq_cio_comp_before"
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    operation_kind: Mapped[str] = mapped_column(Text, nullable=False)
    working_version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    working_version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    impact_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    operation_json: Mapped[str] = mapped_column(Text, nullable=False)
    operation_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class CompositionIdentityOperationSource(Base):
    """Normalized source edge; terminating edges are unique per identity."""

    __tablename__ = "composition_identity_operation_sources"

    __table_args__ = (
        PrimaryKeyConstraint(
            "operation_id", "occurrence_id",
            name="pk_composition_identity_operation_sources",
        ),
        ForeignKeyConstraint(
            ["operation_id", "composition_id"],
            ["composition_identity_operations.id",
             "composition_identity_operations.composition_id"],
            name="fk_cios_operation", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_cios_occurrence", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "terminates_identity IN (0,1)", name="terminates"
        ),
        Index("ix_cios_occurrence", "occurrence_id"),
        Index(
            "uq_cios_terminating_occurrence", "occurrence_id",
            sqlite_where=text("terminates_identity = 1"),
        ),
    )

    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    operation_id: Mapped[str] = mapped_column(UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    terminates_identity: Mapped[int] = mapped_column(Integer, nullable=False)


class CompositionIdentityOperationTarget(Base):
    """Normalized target edge; every occurrence has exactly one birth."""

    __tablename__ = "composition_identity_operation_targets"

    __table_args__ = (
        PrimaryKeyConstraint(
            "operation_id", "occurrence_id",
            name="pk_composition_identity_operation_targets",
        ),
        ForeignKeyConstraint(
            ["operation_id", "composition_id"],
            ["composition_identity_operations.id",
             "composition_identity_operations.composition_id"],
            name="fk_ciot_operation", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_ciot_occurrence", ondelete="RESTRICT",
        ),
        UniqueConstraint("occurrence_id", name="uq_ciot_occurrence"),
        Index("ix_ciot_occurrence", "occurrence_id"),
    )

    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    operation_id: Mapped[str] = mapped_column(UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
