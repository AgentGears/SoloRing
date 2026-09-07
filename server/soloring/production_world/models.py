"""ORM models: M13 authority-complete reusable world (frozen R3 §5).

Exactly thirteen additive tables. CheckConstraint names are BARE literals
(the naming_convention renders the final ck_<table>_<name>, matching
migration 0014 byte-for-byte). Composite FKs to
composition_occurrences(id, composition_id) prove lineage coherence in
every live occurrence consumer, mirroring the M12 pattern.
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

# Shared M7 grammar constants (frozen §5.3/§5.4 mirror the M7 domains).
_M7_KINDS = "'injury', 'surface_condition', 'damage', 'wardrobe_condition', " \
            "'configuration', 'status', 'custom'"
_M7_VALUE_TYPES = "'boolean', 'enum', 'integer', 'decimal', 'text'"
_M7_ANCHOR_TYPES = "'sequence', 'scene', 'shot'"
_M7_BOUNDARIES = "'start', 'end'"
_M7_OPERATIONS = "'set', 'clear'"

_KEY_CHECK = (
    "length(key) BETWEEN 1 AND 64 "
    "AND key GLOB '[a-z]*' AND key NOT GLOB '*[^a-z0-9_]*'"
)

_SUBJECT_KIND_CHECK = (
    "(subject_kind = 'creative_entity' AND creative_entity_id IS NOT NULL) "
    "OR (subject_kind = 'production_instance' AND creative_entity_id IS NULL)"
)

_PLACEMENT_XOR = (
    "(placement_kind = 'entity_fixed_frame' "
    "AND spatial_frame_id IS NOT NULL AND spatial_track_id IS NULL "
    "AND production_instance_track_id IS NULL) OR "
    "(placement_kind = 'entity_track' "
    "AND spatial_frame_id IS NULL AND spatial_track_id IS NOT NULL "
    "AND production_instance_track_id IS NULL) OR "
    "(placement_kind = 'production_instance_track' "
    "AND spatial_frame_id IS NULL AND spatial_track_id IS NULL "
    "AND production_instance_track_id IS NOT NULL)"
)


class CompositionOccurrenceAuthoritySubject(Base):
    """Append-only subject adoption for a stable M12 occurrence (§5.1).

    No updated_at/deleted_at/reassignment exists. There is deliberately NO
    database UNIQUE over (composition_id, creative_entity_id): terminated
    historical claims must survive while a later active occurrence reclaims
    the CreativeEntity; the service enforces active-liveness uniqueness
    under a writer fence.
    """

    __tablename__ = "composition_occurrence_authority_subjects"

    __table_args__ = (
        PrimaryKeyConstraint(
            "composition_id", "occurrence_id",
            name="pk_composition_occurrence_authority_subjects",
        ),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_coas_occurrence", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["creative_entity_id"], ["creative_entities.id"],
            name="fk_coas_creative_entity", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "subject_kind IN ('creative_entity','production_instance')",
            name="subject_kind_domain",
        ),
        CheckConstraint(_SUBJECT_KIND_CHECK, name="subject_kind_entity"),
        Index(
            "ix_coas_active_entity_claim", "composition_id", "creative_entity_id",
            sqlite_where=text("creative_entity_id IS NOT NULL"),
        ),
    )

    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    subject_kind: Mapped[str] = mapped_column(Text, nullable=False)
    creative_entity_id: Mapped[str | None] = mapped_column(UUID)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class ProductionRevisionSpatialInterpretation(Base):
    """Immutable M13 schema-1 interpretation companion (§5.2).

    The composite UNIQUE(production_revision_id, interpretation_hash) is
    intentionally redundant with the PK: binding entries FK onto it to
    prove the pinned hash belongs to that exact Production Revision.
    """

    __tablename__ = "production_revision_spatial_interpretations"

    __table_args__ = (
        PrimaryKeyConstraint(
            "production_revision_id",
            name="pk_production_revision_spatial_interpretations",
        ),
        ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_prsi_production_revision", ondelete="RESTRICT",
        ),
        CheckConstraint("schema_version = 1", name="schema_version"),
        CheckConstraint("length(interpretation_hash) = 64", name="hash_len"),
        UniqueConstraint(
            "production_revision_id", "interpretation_hash",
            name="uq_prsi_revision_hash",
        ),
    )

    production_revision_id: Mapped[str] = mapped_column(UUID)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    x_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    y_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    z_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    yaw_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    pitch_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    roll_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    interpretation_json: Mapped[str] = mapped_column(Text, nullable=False)
    interpretation_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class ProductionInstanceFeature(Base):
    """M7-equivalent persistent state owned by one occurrence (§5.3)."""

    __tablename__ = "production_instance_features"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_production_instance_features"),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_pif_occurrence", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supersedes_feature_id"], ["production_instance_features.id"],
            name="fk_pif_supersedes", ondelete="RESTRICT",
        ),
        CheckConstraint(f"kind IN ({_M7_KINDS})", name="kind_domain"),
        CheckConstraint(f"value_type IN ({_M7_VALUE_TYPES})", name="value_type"),
        CheckConstraint(_KEY_CHECK, name="key"),
        CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        CheckConstraint(
            "(value_type = 'enum' AND enum_values_json IS NOT NULL) OR "
            "(value_type <> 'enum' AND enum_values_json IS NULL)",
            name="enum_presence",
        ),
        CheckConstraint(
            "unit IS NULL OR value_type IN ('integer', 'decimal')",
            name="unit_numeric_only",
        ),
        CheckConstraint(
            "unit IS NULL OR (length(unit) BETWEEN 1 AND 64 "
            "AND unit = trim(unit))",
            name="unit_form",
        ),
        # Tombstone-inclusive: a deleted key is never recycled.
        UniqueConstraint(
            "composition_id", "occurrence_id", "key",
            name="uq_pif_occurrence_key",
        ),
        Index(
            "uq_pif_supersedes", "supersedes_feature_id", unique=True,
            sqlite_where=text("supersedes_feature_id IS NOT NULL"),
        ),
        Index("ix_pif_occurrence", "composition_id", "occurrence_id",
              "deleted_at", "key"),
    )

    id: Mapped[str] = mapped_column(UUID)
    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enum_values_json: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)
    supersedes_feature_id: Mapped[str | None] = mapped_column(UUID)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)


class ProductionInstanceFeatureTransition(Base):
    """Story-boundary persistent state change (§5.4)."""

    __tablename__ = "production_instance_feature_transitions"

    __table_args__ = (
        PrimaryKeyConstraint(
            "id", name="pk_production_instance_feature_transitions",
        ),
        ForeignKeyConstraint(
            ["feature_id"], ["production_instance_features.id"],
            name="fk_pift_feature", ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"anchor_type IN ({_M7_ANCHOR_TYPES})", name="anchor_type",
        ),
        CheckConstraint(f"boundary IN ({_M7_BOUNDARIES})", name="boundary"),
        CheckConstraint(f"operation IN ({_M7_OPERATIONS})", name="operation"),
        CheckConstraint(
            "(operation = 'set' AND value_json IS NOT NULL "
            "AND value_hash IS NOT NULL) OR "
            "(operation = 'clear' AND value_json IS NULL AND value_hash IS NULL)",
            name="operation_value",
        ),
        CheckConstraint(
            "value_hash IS NULL OR length(value_hash) = 64",
            name="value_hash_len",
        ),
        Index(
            "uq_pift_active_coordinate",
            "feature_id", "anchor_type", "anchor_id", "boundary",
            unique=True, sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_pift_feature", "feature_id", "deleted_at"),
        Index("ix_pift_anchor", "anchor_type", "anchor_id", "deleted_at"),
    )

    id: Mapped[str] = mapped_column(UUID)
    feature_id: Mapped[str] = mapped_column(UUID, nullable=False)
    anchor_type: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_id: Mapped[str] = mapped_column(UUID, nullable=False)
    boundary: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    value_json: Mapped[str | None] = mapped_column(Text)
    value_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)


class ProductionInstanceSpatialTrack(Base):
    """A4 placement identity for a Production Instance subject (§5.5)."""

    __tablename__ = "production_instance_spatial_tracks"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_production_instance_spatial_tracks"),
        ForeignKeyConstraint(
            ["spatial_world_id"], ["spatial_worlds.id"],
            name="fk_pist_world", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_pist_occurrence", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "requirement IN ('required','optional')", name="requirement",
        ),
        Index(
            "uq_pist_active_world_occurrence",
            "spatial_world_id", "occurrence_id",
            unique=True, sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_pist_world", "spatial_world_id", "deleted_at"),
        Index("ix_pist_occurrence",
              "composition_id", "occurrence_id", "deleted_at"),
    )

    id: Mapped[str] = mapped_column(UUID)
    spatial_world_id: Mapped[str] = mapped_column(UUID, nullable=False)
    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)


class ProductionInstanceSpatialTransition(Base):
    """Sparse persistent staging for PI tracks (§5.6)."""

    __tablename__ = "production_instance_spatial_transitions"

    __table_args__ = (
        PrimaryKeyConstraint(
            "id", name="pk_production_instance_spatial_transitions",
        ),
        ForeignKeyConstraint(
            ["spatial_track_id"], ["production_instance_spatial_tracks.id"],
            name="fk_pistt_track", ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"anchor_type IN ({_M7_ANCHOR_TYPES})", name="anchor_type",
        ),
        CheckConstraint(f"boundary IN ({_M7_BOUNDARIES})", name="boundary"),
        CheckConstraint(f"operation IN ({_M7_OPERATIONS})", name="operation"),
        CheckConstraint(
            "(operation = 'set' AND x_mm IS NOT NULL AND y_mm IS NOT NULL "
            "AND z_mm IS NOT NULL AND yaw_udeg IS NOT NULL "
            "AND pitch_udeg IS NOT NULL AND roll_udeg IS NOT NULL) OR "
            "(operation = 'clear' AND x_mm IS NULL AND y_mm IS NULL "
            "AND z_mm IS NULL AND yaw_udeg IS NULL AND pitch_udeg IS NULL "
            "AND roll_udeg IS NULL)",
            name="operation_transforms",
        ),
        Index(
            "uq_pistt_active_coordinate",
            "spatial_track_id", "anchor_type", "anchor_id", "boundary",
            unique=True, sqlite_where=text("deleted_at IS NULL"),
        ),
        Index("ix_pistt_track", "spatial_track_id", "deleted_at"),
        Index("ix_pistt_anchor", "anchor_type", "anchor_id", "deleted_at"),
    )

    id: Mapped[str] = mapped_column(UUID)
    spatial_track_id: Mapped[str] = mapped_column(UUID, nullable=False)
    anchor_type: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_id: Mapped[str] = mapped_column(UUID, nullable=False)
    boundary: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    x_mm: Mapped[int | None] = mapped_column(Integer)
    y_mm: Mapped[int | None] = mapped_column(Integer)
    z_mm: Mapped[int | None] = mapped_column(Integer)
    yaw_udeg: Mapped[int | None] = mapped_column(Integer)
    pitch_udeg: Mapped[int | None] = mapped_column(Integer)
    roll_udeg: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)


class CompositionSpatialBinding(Base):
    """Immutable first-class C2 binding parent (§5.7)."""

    __tablename__ = "composition_spatial_bindings"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_composition_spatial_bindings"),
        ForeignKeyConstraint(
            ["composition_revision_id"], ["composition_revisions.id"],
            name="fk_csb_composition_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["spatial_world_revision_id"], ["spatial_world_revisions.id"],
            name="fk_csb_spatial_world_revision", ondelete="RESTRICT",
        ),
        CheckConstraint("schema_version = 1", name="schema_version"),
        CheckConstraint("length(composition_revision_hash) = 64",
                        name="composition_hash_len"),
        CheckConstraint("length(spatial_world_revision_hash) = 64",
                        name="world_hash_len"),
        CheckConstraint("length(binding_hash) = 64", name="binding_hash_len"),
        UniqueConstraint(
            "composition_revision_id", "spatial_world_revision_id",
            "binding_hash", name="uq_csb_revision_pair_hash",
        ),
        Index("ix_csb_composition_revision", "composition_revision_id"),
        Index("ix_csb_world_revision", "spatial_world_revision_id"),
    )

    id: Mapped[str] = mapped_column(UUID)
    composition_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    composition_revision_hash: Mapped[str] = mapped_column(Text, nullable=False)
    spatial_world_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    spatial_world_revision_hash: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_json: Mapped[str] = mapped_column(Text, nullable=False)
    binding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class CompositionSpatialBindingSubject(Base):
    """Normalized immutable subject-map projection (§5.8)."""

    __tablename__ = "composition_spatial_binding_subjects"

    __table_args__ = (
        PrimaryKeyConstraint(
            "binding_id", "position",
            name="pk_composition_spatial_binding_subjects",
        ),
        ForeignKeyConstraint(
            ["binding_id"], ["composition_spatial_bindings.id"],
            name="fk_csbs_binding", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_csbs_production_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["creative_entity_id"], ["creative_entities.id"],
            name="fk_csbs_creative_entity", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "subject_kind IN ('creative_entity','production_instance')",
            name="subject_kind_domain",
        ),
        CheckConstraint(
            "(subject_kind = 'production_instance' "
            "AND creative_entity_id IS NULL AND subject_id = occurrence_id) OR "
            "(subject_kind = 'creative_entity' "
            "AND creative_entity_id IS NOT NULL "
            "AND subject_id = creative_entity_id)",
            name="subject_identity",
        ),
        UniqueConstraint("binding_id", "occurrence_id",
                          name="uq_csbs_occurrence"),
        UniqueConstraint("binding_id", "subject_kind", "subject_id",
                          name="uq_csbs_subject"),
        CheckConstraint("position >= 0", name="position_nonneg"),
    )

    binding_id: Mapped[str] = mapped_column(UUID, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    production_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    production_revision_hash: Mapped[str] = mapped_column(Text, nullable=False)
    subject_kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(UUID, nullable=False)
    creative_entity_id: Mapped[str | None] = mapped_column(UUID)


class CompositionSpatialBindingEntry(Base):
    """Normalized immutable A4 placement-binding projection (§5.9)."""

    __tablename__ = "composition_spatial_binding_entries"

    __table_args__ = (
        PrimaryKeyConstraint(
            "binding_id", "position",
            name="pk_composition_spatial_binding_entries",
        ),
        ForeignKeyConstraint(
            ["binding_id"], ["composition_spatial_bindings.id"],
            name="fk_csbe_binding", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_csbe_production_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["creative_entity_id"], ["creative_entities.id"],
            name="fk_csbe_creative_entity", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["spatial_frame_id"], ["spatial_frames.id"],
            name="fk_csbe_spatial_frame", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["spatial_track_id"], ["spatial_tracks.id"],
            name="fk_csbe_spatial_track", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["production_instance_track_id"],
            ["production_instance_spatial_tracks.id"],
            name="fk_csbe_pi_track", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["production_revision_id", "spatial_interpretation_hash"],
            ["production_revision_spatial_interpretations.production_revision_id",
             "production_revision_spatial_interpretations.interpretation_hash"],
            name="fk_csbe_interpretation", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "placement_kind IN ('entity_fixed_frame','entity_track',"
            "'production_instance_track')",
            name="placement_kind_domain",
        ),
        CheckConstraint(_PLACEMENT_XOR, name="placement_xor"),
        CheckConstraint(
            "length(spatial_interpretation_hash) = 64",
            name="interpretation_hash_len",
        ),
        CheckConstraint(
            "subject_kind IN ('creative_entity','production_instance')",
            name="subject_kind_domain",
        ),
        CheckConstraint(
            "(subject_kind = 'production_instance' "
            "AND creative_entity_id IS NULL AND subject_id = occurrence_id) OR "
            "(subject_kind = 'creative_entity' "
            "AND creative_entity_id IS NOT NULL "
            "AND subject_id = creative_entity_id)",
            name="subject_identity",
        ),
        UniqueConstraint("binding_id", "occurrence_id",
                          name="uq_csbe_occurrence"),
        UniqueConstraint("binding_id", "subject_kind", "subject_id",
                          name="uq_csbe_subject"),
        CheckConstraint("position >= 0", name="position_nonneg"),
    )

    binding_id: Mapped[str] = mapped_column(UUID, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    production_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    production_revision_hash: Mapped[str] = mapped_column(Text, nullable=False)
    subject_kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[str] = mapped_column(UUID, nullable=False)
    creative_entity_id: Mapped[str | None] = mapped_column(UUID)
    placement_kind: Mapped[str] = mapped_column(Text, nullable=False)
    spatial_frame_id: Mapped[str | None] = mapped_column(UUID)
    spatial_track_id: Mapped[str | None] = mapped_column(UUID)
    production_instance_track_id: Mapped[str | None] = mapped_column(UUID)
    spatial_interpretation_hash: Mapped[str] = mapped_column(
        Text, nullable=False)


class ShotProductionWorldSelection(Base):
    """Mutable current Shot pointer to one exact binding (§5.10)."""

    __tablename__ = "shot_production_world_selections"

    __table_args__ = (
        PrimaryKeyConstraint("shot_id", name="pk_shot_production_world_selections"),
        ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_spws_shot", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["binding_id"], ["composition_spatial_bindings.id"],
            name="fk_spws_binding", ondelete="RESTRICT",
        ),
    )

    shot_id: Mapped[str] = mapped_column(UUID)
    binding_id: Mapped[str] = mapped_column(UUID, nullable=False)
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class ShotRevisionProductionWorld(Base):
    """Immutable normalized schema-6 parent projection (§5.11)."""

    __tablename__ = "shot_revision_production_worlds"

    __table_args__ = (
        PrimaryKeyConstraint(
            "shot_revision_id", name="pk_shot_revision_production_worlds",
        ),
        ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpw_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["binding_id"], ["composition_spatial_bindings.id"],
            name="fk_srpw_binding", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["composition_revision_id"], ["composition_revisions.id"],
            name="fk_srpw_composition_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["spatial_world_revision_id"], ["spatial_world_revisions.id"],
            name="fk_srpw_world_revision", ondelete="RESTRICT",
        ),
        CheckConstraint("length(production_world_hash) = 64",
                        name="world_hash_len"),
        CheckConstraint("length(binding_hash) = 64", name="binding_hash_len"),
        CheckConstraint("length(composition_revision_hash) = 64",
                        name="composition_hash_len"),
        CheckConstraint("length(spatial_world_revision_hash) = 64",
                        name="revision_hash_len"),
    )

    shot_revision_id: Mapped[str] = mapped_column(UUID)
    production_world_hash: Mapped[str] = mapped_column(Text, nullable=False)
    binding_id: Mapped[str] = mapped_column(UUID, nullable=False)
    binding_hash: Mapped[str] = mapped_column(Text, nullable=False)
    composition_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    composition_revision_hash: Mapped[str] = mapped_column(Text, nullable=False)
    spatial_world_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    spatial_world_revision_hash: Mapped[str] = mapped_column(
        Text, nullable=False)


class ShotRevisionProductionInstanceFeatureState(Base):
    """Immutable historical PI state projection (§5.12).

    position is zero-based contiguous and equals the index in the canonical
    instance_feature_states array (§16.2); it is not a second ordering
    authority.
    """

    __tablename__ = "shot_revision_production_instance_feature_states"

    __table_args__ = (
        PrimaryKeyConstraint(
            "shot_revision_id", "position",
            name="pk_shot_revision_production_instance_feature_states",
        ),
        ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpifs_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_srpifs_occurrence", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["feature_id"], ["production_instance_features.id"],
            name="fk_srpifs_feature", ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 0", name="position_nonneg"),
        CheckConstraint("length(value_hash) = 64", name="value_hash_len"),
    )

    shot_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    feature_id: Mapped[str] = mapped_column(UUID, nullable=False)
    feature_key: Mapped[str] = mapped_column(Text, nullable=False)
    feature_kind: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    value_hash: Mapped[str] = mapped_column(Text, nullable=False)
    source_transition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    source_anchor_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_anchor_id: Mapped[str] = mapped_column(UUID, nullable=False)
    source_boundary: Mapped[str] = mapped_column(Text, nullable=False)


class ShotRevisionProductionInstanceSpatialState(Base):
    """Immutable historical PI staging projection (§5.13)."""

    __tablename__ = "shot_revision_production_instance_spatial_states"

    __table_args__ = (
        PrimaryKeyConstraint(
            "shot_revision_id", "position",
            name="pk_shot_revision_production_instance_spatial_states",
        ),
        ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpiss_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_srpiss_occurrence", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["production_instance_track_id"],
            ["production_instance_spatial_tracks.id"],
            name="fk_srpiss_track", ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 0", name="position_nonneg"),
        CheckConstraint(
            "requirement IN ('required','optional')", name="requirement",
        ),
    )

    shot_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    composition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    occurrence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    production_instance_track_id: Mapped[str] = mapped_column(
        UUID, nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    x_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    y_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    z_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    yaw_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    pitch_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    roll_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    source_transition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    source_anchor_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_anchor_id: Mapped[str] = mapped_column(UUID, nullable=False)
    source_boundary: Mapped[str] = mapped_column(Text, nullable=False)
