"""ORM models: Story World identity, revisions, approval, dependencies (M6 §16–§23, §43, §49).

Every constraint carries a deterministic explicit name so the hand-written
0006 migration and the ORM ``__table_args__`` compare cleanly (the 0002
lesson: anonymous rendered constraints would mismatch the ORM).

Design rules pinned by the M6 plan:

* ``CreativeEntity`` is identity only — name/description are display
  metadata and never participate in any hash.
* ``EntityRevision`` rows are immutable: no updated_at, no deleted_at, and
  no service ever updates or deletes them.
* ``UNIQUE(id, entity_id)`` on ``entity_revisions`` exists so the composite
  foreign keys from ``entity_approved_revisions`` and
  ``shot_revision_entity_dependencies`` are legal; it mechanically
  guarantees an entity can only approve / depend on its own revisions.
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

from soloring.continuity.enums import ENTITY_KINDS
from soloring.db.base import Base
from soloring.db.timeutil import DB_NOW_SQL

UUID = String(36)

_KINDS_SQL = ", ".join(f"'{k}'" for k in ENTITY_KINDS)


class CreativeEntity(Base):
    __tablename__ = "creative_entities"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_creative_entities"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_creative_entities_project_id_projects", ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"kind IN ({_KINDS_SQL})", name="ck_creative_entities_kind"
        ),
        CheckConstraint(
            "length(trim(name)) > 0", name="ck_creative_entities_name_nonempty"
        ),
        CheckConstraint(
            "length(name) <= 500", name="ck_creative_entities_name_maxlen"
        ),
        Index(
            "ix_creative_entities_project_kind",
            "project_id", "kind", "deleted_at", "name",
        ),
        Index(
            "ix_creative_entities_project_created",
            "project_id", "deleted_at", "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    project_id: Mapped[str] = mapped_column(UUID, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)


class EntityRevision(Base):
    __tablename__ = "entity_revisions"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_entity_revisions"),
        ForeignKeyConstraint(
            ["entity_id"], ["creative_entities.id"],
            name="fk_entity_revisions_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "entity_id", "revision_number",
            name="uq_entity_revisions_entity_id_revision_number",
        ),
        UniqueConstraint(
            "entity_id", "spec_hash", name="uq_entity_revisions_entity_id_spec_hash"
        ),
        # Composite-FK target for entity_approved_revisions and
        # shot_revision_entity_dependencies (M6 §23, §49).
        UniqueConstraint("id", "entity_id", name="uq_entity_revisions_id_entity_id"),
        CheckConstraint(
            "revision_number >= 1", name="ck_entity_revisions_revision_number_positive"
        ),
        CheckConstraint(
            "schema_version >= 1", name="ck_entity_revisions_schema_version_positive"
        ),
        CheckConstraint(
            "length(spec_hash) = 64", name="ck_entity_revisions_spec_hash_len"
        ),
        Index("ix_entity_revisions_entity_id_created", "entity_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(UUID)
    entity_id: Mapped[str] = mapped_column(UUID, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    spec_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    # No updated_at / deleted_at: EntityRevision rows are immutable (M6-F3).


class CharacterRevisionSpec(Base):
    """Typed revision payload for kind=character (M6 §20).

    Five separate tables/classes are deliberate: Character and Location
    design semantics diverge in later schema versions without a generic
    metadata swamp. Each stores the canonical spec_json accepted only
    through its kind-specific versioned Pydantic schema.
    """

    __tablename__ = "character_revision_specs"

    __table_args__ = (
        PrimaryKeyConstraint("revision_id", name="pk_character_revision_specs"),
        ForeignKeyConstraint(
            ["revision_id"], ["entity_revisions.id"],
            name="fk_character_revision_specs_revision_id_entity_revisions",
            ondelete="RESTRICT",
        ),
    )

    revision_id: Mapped[str] = mapped_column(UUID)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)


class LocationRevisionSpec(Base):
    __tablename__ = "location_revision_specs"

    __table_args__ = (
        PrimaryKeyConstraint("revision_id", name="pk_location_revision_specs"),
        ForeignKeyConstraint(
            ["revision_id"], ["entity_revisions.id"],
            name="fk_location_revision_specs_revision_id_entity_revisions",
            ondelete="RESTRICT",
        ),
    )

    revision_id: Mapped[str] = mapped_column(UUID)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)


class PropRevisionSpec(Base):
    __tablename__ = "prop_revision_specs"

    __table_args__ = (
        PrimaryKeyConstraint("revision_id", name="pk_prop_revision_specs"),
        ForeignKeyConstraint(
            ["revision_id"], ["entity_revisions.id"],
            name="fk_prop_revision_specs_revision_id_entity_revisions",
            ondelete="RESTRICT",
        ),
    )

    revision_id: Mapped[str] = mapped_column(UUID)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)


class CostumeRevisionSpec(Base):
    __tablename__ = "costume_revision_specs"

    __table_args__ = (
        PrimaryKeyConstraint("revision_id", name="pk_costume_revision_specs"),
        ForeignKeyConstraint(
            ["revision_id"], ["entity_revisions.id"],
            name="fk_costume_revision_specs_revision_id_entity_revisions",
            ondelete="RESTRICT",
        ),
    )

    revision_id: Mapped[str] = mapped_column(UUID)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)


class VehicleRevisionSpec(Base):
    __tablename__ = "vehicle_revision_specs"

    __table_args__ = (
        PrimaryKeyConstraint("revision_id", name="pk_vehicle_revision_specs"),
        ForeignKeyConstraint(
            ["revision_id"], ["entity_revisions.id"],
            name="fk_vehicle_revision_specs_revision_id_entity_revisions",
            ondelete="RESTRICT",
        ),
    )

    revision_id: Mapped[str] = mapped_column(UUID)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)


class EntityApprovedRevision(Base):
    """Current-pointer table: an entity's explicitly approved revision (M6 §23).

    PK on entity_id makes the pointer singular; the composite FK guarantees
    the approved revision belongs to THIS entity. No unapprove operation
    exists (M6-F5): a legal working dependency therefore always resolves.
    """

    __tablename__ = "entity_approved_revisions"

    __table_args__ = (
        PrimaryKeyConstraint("entity_id", name="pk_entity_approved_revisions"),
        ForeignKeyConstraint(
            ["entity_id"], ["creative_entities.id"],
            name="fk_entity_approved_revisions_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["revision_id", "entity_id"],
            ["entity_revisions.id", "entity_revisions.entity_id"],
            name="fk_entity_approved_revisions_revision_id_entity_revisions",
            ondelete="RESTRICT",
        ),
    )

    entity_id: Mapped[str] = mapped_column(UUID)
    revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    approved_at: Mapped[str] = mapped_column(Text, nullable=False)


class ShotEntityDependency(Base):
    """Shot WORKING dependency on Entity identity — never a revision (M6 §43).

    Resolution to the approved EntityRevision happens at ShotRevision capture
    time; this table stores only the semantic identity + role.
    """

    __tablename__ = "shot_entity_dependencies"

    __table_args__ = (
        PrimaryKeyConstraint(
            "shot_id", "entity_id", "role", name="pk_shot_entity_dependencies"
        ),
        ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_shot_entity_dependencies_shot_id_shots", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["entity_id"], ["creative_entities.id"],
            name="fk_shot_entity_dependencies_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "shot_id", "role", "position",
            name="uq_shot_entity_dependencies_shot_id_role_position",
        ),
        CheckConstraint(
            "position >= 0", name="ck_shot_entity_dependencies_position_nonneg"
        ),
        CheckConstraint(
            "length(role) BETWEEN 1 AND 64 AND length(trim(role)) > 0",
            name="ck_shot_entity_dependencies_role",
        ),
        Index("ix_shot_entity_dependencies_entity_id", "entity_id"),
    )

    shot_id: Mapped[str] = mapped_column(UUID, nullable=False)
    entity_id: Mapped[str] = mapped_column(UUID, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class ShotRevisionEntityDependency(Base):
    """Immutable historical dependency snapshot on a ShotRevision (M6 §49).

    ``entity_revision_id`` is pinned at capture; the composite FK guarantees
    the captured revision belongs to the recorded entity. ``source`` is
    CHECK-constrained to the M6 domain.
    """

    __tablename__ = "shot_revision_entity_dependencies"

    __table_args__ = (
        PrimaryKeyConstraint(
            "shot_revision_id", "role", "position",
            name="pk_shot_revision_entity_dependencies",
        ),
        ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_shot_revision_entity_dependencies_shot_revision_id_shot_revisions",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["entity_revision_id", "entity_id"],
            ["entity_revisions.id", "entity_revisions.entity_id"],
            name="fk_shot_revision_entity_dependencies_entity_revision_id_entity_revisions",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "shot_revision_id", "entity_revision_id", "role",
            name="uq_shot_revision_entity_dependencies_revision_entity_role",
        ),
        CheckConstraint(
            "position >= 0",
            name="ck_shot_revision_entity_dependencies_position_nonneg",
        ),
        CheckConstraint(
            "length(role) BETWEEN 1 AND 64 AND length(trim(role)) > 0",
            name="ck_shot_revision_entity_dependencies_role",
        ),
        CheckConstraint(
            "source IN ('shot_explicit')",
            name="ck_shot_revision_entity_dependencies_source",
        ),
        Index(
            "ix_shot_revision_entity_dependencies_entity_revision_id",
            "entity_revision_id",
        ),
        Index(
            "ix_shot_revision_entity_dependencies_entity_id", "entity_id"
        ),
    )

    shot_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    entity_id: Mapped[str] = mapped_column(UUID, nullable=False)
    entity_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
