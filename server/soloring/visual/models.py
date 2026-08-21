"""ORM models: M8 visual identity (frozen plan §§14–19, 26–27, 57).

Every constraint carries a deterministic explicit name so the hand-written
0009 migration and the ORM ``__table_args__`` compare cleanly (the 0002
lesson, continued from continuity/models.py).

Design rules pinned by the frozen M8 plan:

* ``VisualFacet`` is the stable production concern; target identity
  (target_kind + entity_id/feature_id + facet_key) is immutable after
  creation. Only label/description/requirement are mutable (§37).
* Feature VisualFacets are the only facets that may own value-policy rows
  (§16), and every Feature realization is entity-scoped under 0008, so
  ``visual_context_entity_revision_id`` is NOT NULL on feature anchors
  (§17) — there is no non-entity feature branch in M8.
* ``VisualAnchor`` semantic binding fields are immutable after creation
  (§17); working items are the only mutable membership (§19).
* ``visual_anchor_revisions`` / ``visual_anchor_revision_items`` /
  ``shot_revision_visual_anchors`` / ``shot_revision_visual_anchor_items``
  are immutable history: no updated_at, no deleted_at, no service ever
  updates or deletes them (§26–27, 57).
* Active-only partial uniqueness where soft deletion frees the coordinate
  (facets, anchors); the revision uniqueness dimensions are total (§26).
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

_M8_TARGET_KINDS = "'entity', 'feature'"
_M8_REQUIREMENTS = "'required', 'optional'"
_M8_POLICIES = "'required', 'optional', 'not_applicable'"
_M8_ROLES = "'primary', 'supporting', 'detail', 'context'"

# App-level regex is authoritative; the GLOB checks are defense in depth
# (first char [a-z0-9]; chars from [a-z0-9._-]).
_FACET_KEY_CHECK = (
    "length(facet_key) BETWEEN 1 AND 128 "
    "AND facet_key NOT GLOB '*[^a-z0-9._-]*'"
)


class VisualFacet(Base):
    __tablename__ = "visual_facets"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_visual_facets"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_visual_facets_project_id_projects", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["entity_id"], ["creative_entities.id"],
            name="fk_visual_facets_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["feature_id"], ["continuity_features.id"],
            name="fk_visual_facets_feature_id_continuity_features",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"target_kind IN ({_M8_TARGET_KINDS})",
            name="ck_visual_facets_target_kind",
        ),
        CheckConstraint(
            f"requirement IN ({_M8_REQUIREMENTS})",
            name="ck_visual_facets_requirement",
        ),
        CheckConstraint(
            _FACET_KEY_CHECK, name="ck_visual_facets_facet_key",
        ),
        # Row-shape: exactly one target id, matching the kind (§14).
        CheckConstraint(
            "(target_kind = 'entity' AND entity_id IS NOT NULL "
            "AND feature_id IS NULL) OR "
            "(target_kind = 'feature' AND feature_id IS NOT NULL "
            "AND entity_id IS NULL)",
            name="ck_visual_facets_target_shape",
        ),
        # Active uniqueness per target (§15) — partial unique indexes
        # declared below (sqlite_where).
        Index(
            "ix_visual_facets_project", "project_id", "deleted_at",
        ),
        Index(
            "ix_visual_facets_entity_target",
            "entity_id", "facet_key", "deleted_at",
        ),
        Index(
            "ix_visual_facets_feature_target",
            "feature_id", "facet_key", "deleted_at",
        ),
        Index(
            "uq_visual_facets_entity_active",
            "entity_id", "facet_key", unique=True,
            sqlite_where=text(
                "target_kind = 'entity' AND deleted_at IS NULL"
            ),
        ),
        Index(
            "uq_visual_facets_feature_active",
            "feature_id", "facet_key", unique=True,
            sqlite_where=text(
                "target_kind = 'feature' AND deleted_at IS NULL"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    project_id: Mapped[str] = mapped_column(UUID, nullable=False)
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(UUID)
    feature_id: Mapped[str | None] = mapped_column(UUID)
    facet_key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)


class VisualFacetValuePolicy(Base):
    """Feature-value policy overrides (§16). Immutable per (facet, value);
    replaced only through the atomic full-set PUT."""

    __tablename__ = "visual_facet_value_policies"

    __table_args__ = (
        PrimaryKeyConstraint(
            "visual_facet_id", "feature_value_hash",
            name="pk_visual_facet_value_policies",
        ),
        ForeignKeyConstraint(
            ["visual_facet_id"], ["visual_facets.id"],
            name="fk_visual_facet_value_policies_visual_facet_id_"
                 "visual_facets",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"policy IN ({_M8_POLICIES})",
            name="ck_visual_facet_value_policies_policy",
        ),
        CheckConstraint(
            "length(feature_value_hash) = 64",
            name="ck_visual_facet_value_policies_value_hash_len",
        ),
        CheckConstraint(
            "length(feature_value_json) > 0",
            name="ck_visual_facet_value_policies_value_json_nonempty",
        ),
    )

    visual_facet_id: Mapped[str] = mapped_column(UUID, nullable=False)
    feature_value_hash: Mapped[str] = mapped_column(Text, nullable=False)
    feature_value_json: Mapped[str] = mapped_column(Text, nullable=False)
    policy: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class VisualAnchor(Base):
    __tablename__ = "visual_anchors"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_visual_anchors"),
        ForeignKeyConstraint(
            ["visual_facet_id"], ["visual_facets.id"],
            name="fk_visual_anchors_visual_facet_id_visual_facets",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["entity_revision_id"], ["entity_revisions.id"],
            name="fk_visual_anchors_entity_revision_id_entity_revisions",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["visual_context_entity_revision_id"], ["entity_revisions.id"],
            name="fk_visual_anchors_visual_context_entity_revision_id_"
                 "entity_revisions",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["approved_revision_id"], ["visual_anchor_revisions.id"],
            name="fk_visual_anchors_approved_revision_id_"
                 "visual_anchor_revisions",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(feature_value_hash) = 64 OR feature_value_hash IS NULL",
            name="ck_visual_anchors_feature_value_hash_len",
        ),
        # Binding shape is determined by the owning facet kind and enforced
        # in CHECK form as defense in depth (§17); the fenced service is
        # the primary validator of same-Project/semantic ownership.
        CheckConstraint(
            "(entity_revision_id IS NOT NULL "
            "AND feature_value_hash IS NULL AND feature_value_json IS NULL "
            "AND visual_context_entity_revision_id IS NULL) OR "
            "(entity_revision_id IS NULL AND feature_value_hash IS NOT NULL "
            "AND feature_value_json IS NOT NULL "
            "AND visual_context_entity_revision_id IS NOT NULL)",
            name="ck_visual_anchors_binding_shape",
        ),
        Index(
            "uq_visual_anchors_entity_state_active",
            "visual_facet_id", "entity_revision_id", unique=True,
            sqlite_where=text(
                "entity_revision_id IS NOT NULL AND deleted_at IS NULL"
            ),
        ),
        Index(
            "uq_visual_anchors_feature_state_active",
            "visual_facet_id", "feature_value_hash",
            "visual_context_entity_revision_id", unique=True,
            sqlite_where=text(
                "feature_value_hash IS NOT NULL "
                "AND visual_context_entity_revision_id IS NOT NULL "
                "AND deleted_at IS NULL"
            ),
        ),
        Index(
            "ix_visual_anchors_entity_state",
            "visual_facet_id", "entity_revision_id", "deleted_at",
        ),
        Index(
            "ix_visual_anchors_feature_state",
            "visual_facet_id", "feature_value_hash",
            "visual_context_entity_revision_id", "deleted_at",
        ),
        Index(
            "ix_visual_anchors_approved_revision", "approved_revision_id",
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    visual_facet_id: Mapped[str] = mapped_column(UUID, nullable=False)
    entity_revision_id: Mapped[str | None] = mapped_column(UUID)
    feature_value_hash: Mapped[str | None] = mapped_column(Text)
    feature_value_json: Mapped[str | None] = mapped_column(Text)
    visual_context_entity_revision_id: Mapped[str | None] = mapped_column(
        UUID
    )
    approved_revision_id: Mapped[str | None] = mapped_column(UUID)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)


class VisualAnchorItem(Base):
    """Mutable working membership (§19). Positions are global, contiguous,
    server-assigned; same Asset appears at most once per anchor."""

    __tablename__ = "visual_anchor_items"

    __table_args__ = (
        PrimaryKeyConstraint(
            "visual_anchor_id", "asset_id",
            name="pk_visual_anchor_items",
        ),
        ForeignKeyConstraint(
            ["visual_anchor_id"], ["visual_anchors.id"],
            name="fk_visual_anchor_items_visual_anchor_id_visual_anchors",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_visual_anchor_items_asset_id_assets",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"role IN ({_M8_ROLES})",
            name="ck_visual_anchor_items_role",
        ),
        CheckConstraint(
            "position >= 0", name="ck_visual_anchor_items_position_nonneg",
        ),
        CheckConstraint(
            "view_key IS NULL OR (length(view_key) BETWEEN 1 AND 64 "
            "AND view_key = trim(view_key))",
            name="ck_visual_anchor_items_view_key",
        ),
        UniqueConstraint(
            "visual_anchor_id", "position",
            name="uq_visual_anchor_items_anchor_position",
        ),
        Index("ix_visual_anchor_items_asset", "asset_id"),
    )

    visual_anchor_id: Mapped[str] = mapped_column(UUID, nullable=False)
    asset_id: Mapped[str] = mapped_column(UUID, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    view_key: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class VisualAnchorRevision(Base):
    """Immutable canonical snapshot of one anchor's curated pack (§26)."""

    __tablename__ = "visual_anchor_revisions"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_visual_anchor_revisions"),
        ForeignKeyConstraint(
            ["visual_anchor_id"], ["visual_anchors.id"],
            name="fk_visual_anchor_revisions_visual_anchor_id_"
                 "visual_anchors",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "revision_number >= 1",
            name="ck_visual_anchor_revisions_number_positive",
        ),
        CheckConstraint(
            "length(snapshot_hash) = 64",
            name="ck_visual_anchor_revisions_snapshot_hash_len",
        ),
        UniqueConstraint(
            "visual_anchor_id", "revision_number",
            name="uq_visual_anchor_revisions_anchor_number",
        ),
        UniqueConstraint(
            "visual_anchor_id", "snapshot_hash",
            name="uq_visual_anchor_revisions_anchor_hash",
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    visual_anchor_id: Mapped[str] = mapped_column(UUID, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    # No updated_at / deleted_at: revisions are append-only (§26).


class VisualAnchorRevisionItem(Base):
    """Immutable normalized projection of revision bytes (§27)."""

    __tablename__ = "visual_anchor_revision_items"

    __table_args__ = (
        PrimaryKeyConstraint(
            "visual_anchor_revision_id", "position",
            name="pk_visual_anchor_revision_items",
        ),
        ForeignKeyConstraint(
            ["visual_anchor_revision_id"], ["visual_anchor_revisions.id"],
            name="fk_visual_anchor_revision_items_visual_anchor_revision_"
                 "id_visual_anchor_revisions",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_visual_anchor_revision_items_asset_id_assets",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_visual_anchor_revision_items_blob_hash_blobs",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"role IN ({_M8_ROLES})",
            name="ck_visual_anchor_revision_items_role",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_visual_anchor_revision_items_position_nonneg",
        ),
        UniqueConstraint(
            "visual_anchor_revision_id", "asset_id",
            name="uq_visual_anchor_revision_items_asset",
        ),
        Index(
            "ix_visual_anchor_revision_items_asset", "asset_id",
        ),
        Index(
            "ix_visual_anchor_revision_items_blob", "blob_hash",
        ),
    )

    visual_anchor_revision_id: Mapped[str] = mapped_column(
        UUID, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_id: Mapped[str] = mapped_column(UUID, nullable=False)
    blob_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    view_key: Mapped[str | None] = mapped_column(Text)


class ShotRevisionVisualAnchor(Base):
    """Immutable historical visual provenance, anchor rows (§57)."""

    __tablename__ = "shot_revision_visual_anchors"

    __table_args__ = (
        PrimaryKeyConstraint(
            "shot_revision_id", "position",
            name="pk_shot_revision_visual_anchors",
        ),
        ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_shot_revision_visual_anchors_shot_revision_id_"
                 "shot_revisions",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["visual_facet_id"], ["visual_facets.id"],
            name="fk_shot_revision_visual_anchors_visual_facet_id_"
                 "visual_facets",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["visual_anchor_id"], ["visual_anchors.id"],
            name="fk_shot_revision_visual_anchors_visual_anchor_id_"
                 "visual_anchors",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["visual_anchor_revision_id"], ["visual_anchor_revisions.id"],
            name="fk_shot_revision_visual_anchors_visual_anchor_revision_"
                 "id_visual_anchor_revisions",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_shot_revision_visual_anchors_position_nonneg",
        ),
        CheckConstraint(
            "length(visual_anchor_snapshot_hash) = 64",
            name="ck_shot_revision_visual_anchors_hash_len",
        ),
        CheckConstraint(
            f"target_kind IN ({_M8_TARGET_KINDS})",
            name="ck_shot_revision_visual_anchors_target_kind",
        ),
        CheckConstraint(
            "length(feature_value_hash) = 64 "
            "OR feature_value_hash IS NULL",
            name="ck_shot_revision_visual_anchors_value_hash_len",
        ),
        Index(
            "ix_shot_revision_visual_anchors_facet", "visual_facet_id",
        ),
    )

    shot_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    visual_facet_id: Mapped[str] = mapped_column(UUID, nullable=False)
    facet_key: Mapped[str] = mapped_column(Text, nullable=False)
    visual_anchor_id: Mapped[str] = mapped_column(UUID, nullable=False)
    visual_anchor_revision_id: Mapped[str] = mapped_column(
        UUID, nullable=False
    )
    visual_anchor_snapshot_hash: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    target_kind: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(UUID)
    entity_revision_id: Mapped[str | None] = mapped_column(UUID)
    feature_id: Mapped[str | None] = mapped_column(UUID)
    feature_value_hash: Mapped[str | None] = mapped_column(Text)
    feature_value_json: Mapped[str | None] = mapped_column(Text)
    visual_context_entity_revision_id: Mapped[str | None] = mapped_column(
        UUID
    )


class ShotRevisionVisualAnchorItem(Base):
    """Immutable historical visual provenance, item rows (§57)."""

    __tablename__ = "shot_revision_visual_anchor_items"

    __table_args__ = (
        PrimaryKeyConstraint(
            "shot_revision_id", "anchor_position", "item_position",
            name="pk_shot_revision_visual_anchor_items",
        ),
        ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_shot_revision_visual_anchor_items_shot_revision_id_"
                 "shot_revisions",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_shot_revision_visual_anchor_items_asset_id_assets",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_shot_revision_visual_anchor_items_blob_hash_blobs",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"role IN ({_M8_ROLES})",
            name="ck_shot_revision_visual_anchor_items_role",
        ),
        CheckConstraint(
            "anchor_position >= 0 AND item_position >= 0",
            name="ck_shot_revision_visual_anchor_items_positions",
        ),
        Index(
            "ix_shot_revision_visual_anchor_items_asset", "asset_id",
        ),
        Index(
            "ix_shot_revision_visual_anchor_items_blob", "blob_hash",
        ),
    )

    shot_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    anchor_position: Mapped[int] = mapped_column(Integer, nullable=False)
    item_position: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_id: Mapped[str] = mapped_column(UUID, nullable=False)
    blob_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    view_key: Mapped[str | None] = mapped_column(Text)
