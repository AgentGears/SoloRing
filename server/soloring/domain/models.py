"""ORM models: Projects, Shots, ShotReferences, ShotRevisions (plan §8–§14).

Every constraint carries a deterministic explicit name (plan §4.2) so future
SQLite batch migrations compare cleanly. `db/models.py` is the metadata
registration point; these classes are imported there to populate Base.metadata.
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

# Canonical lowercase UUID TEXT (plan §12: UUIDs use lowercase canonical form).
UUID = String(36)


class Project(Base):
    __tablename__ = "projects"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_projects"),
        CheckConstraint("length(trim(name)) > 0", name="ck_projects_name_nonempty"),
        CheckConstraint("length(name) <= 500", name="ck_projects_name_maxlen"),
    )

    id: Mapped[str] = mapped_column(UUID)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)


class Shot(Base):
    __tablename__ = "shots"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_shots"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_shots_project_id_projects", ondelete="RESTRICT",
        ),
        # scene_id is NOT a database FK (mirrors approved_take_id): an
        # ALTER-added column cannot carry a named REFERENCES clause without
        # breaking migration/ORM name parity, and rebuilding the populated
        # shots table is forbidden (plan §35). Scene validity is enforced by
        # the M6B assignment transaction (plan §39).
        UniqueConstraint(
            "project_id", "shot_number", name="uq_shots_project_id_shot_number"
        ),
        CheckConstraint("length(trim(subject)) > 0", name="ck_shots_subject_nonempty"),
        CheckConstraint("length(subject) <= 20000", name="ck_shots_subject_maxlen"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_shots_duration_nonneg"
        ),
        # M6 narrative context (plan §34–§35): both nullable, always paired.
        # Bare names: the Base naming_convention renders the final
        # ck_<table>_<name>, exactly matching the names migration 0006 adds
        # through ALTER TABLE ADD COLUMN (parity proven by strict set
        # comparison in tests/test_migration_m6.py).
        CheckConstraint(
            "(scene_id IS NULL) = (scene_position IS NULL)",
            name="scene_pair",
        ),
        CheckConstraint(
            "scene_position IS NULL OR scene_position >= 0",
            name="scene_position_nonneg",
        ),
        Index("ix_shots_project_active_number", "project_id", "deleted_at", "shot_number"),
        Index("ix_shots_approved_take_id", "approved_take_id"),
        # Active-only uniqueness (M6B re-gate): partial unique index — a
        # soft-deleted Shot keeps its last narrative coordinates forever;
        # uniqueness applies to ACTIVE assigned rows only. (Also: a table
        # constraint would force a batch rebuild of populated shots, §35.)
        Index(
            "uq_shots_scene_position", "scene_id", "scene_position",
            unique=True,
            sqlite_where=text("deleted_at IS NULL AND scene_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    project_id: Mapped[str] = mapped_column(UUID, nullable=False)
    shot_number: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str | None] = mapped_column(Text)
    framing: Mapped[str | None] = mapped_column(Text)
    camera_motion: Mapped[str | None] = mapped_column(Text)
    lens: Mapped[str | None] = mapped_column(Text)
    mood: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    # NOT a database FK (plan §5.1): avoids a cyclic shots<->takes dependency.
    approved_take_id: Mapped[str | None] = mapped_column(UUID)

    # M6 narrative assignment (plan §34): NULL/NULL = unassigned. No
    # database FK by design (same reasoning as the __table_args__ comment);
    # Scene validity is enforced transactionally by M6B assignment.
    scene_id: Mapped[str | None] = mapped_column(UUID)
    scene_position: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)


class ShotReference(Base):
    __tablename__ = "shot_references"

    __table_args__ = (
        PrimaryKeyConstraint("shot_id", "asset_id", "role", name="pk_shot_references"),
        ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_shot_references_shot_id_shots", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_shot_references_asset_id_assets", ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "shot_id", "role", "position", name="uq_shot_references_shot_id_role_position"
        ),
        CheckConstraint("position >= 0", name="ck_shot_references_position_nonneg"),
        CheckConstraint(
            "length(role) BETWEEN 1 AND 64 AND length(trim(role)) > 0",
            name="ck_shot_references_role",
        ),
        Index("ix_shot_references_asset_id", "asset_id"),
    )

    shot_id: Mapped[str] = mapped_column(UUID, nullable=False)
    asset_id: Mapped[str] = mapped_column(UUID, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class ShotRevision(Base):
    __tablename__ = "shot_revisions"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_shot_revisions"),
        ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_shot_revisions_shot_id_shots", ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "shot_id", "revision_number", name="uq_shot_revisions_shot_id_revision_number"
        ),
        UniqueConstraint(
            "shot_id", "snapshot_hash", name="uq_shot_revisions_shot_id_snapshot_hash"
        ),
        CheckConstraint(
            "length(snapshot_hash) = 64", name="ck_shot_revisions_snapshot_hash_len"
        ),
        # M6 (plan §52): NULL/NULL for every legacy v1 revision and for any
        # current Shot with zero semantic dependencies (M6-F14); 64-char
        # SHA-256 whenever a continuity spec exists. Bare name so the naming
        # convention renders the same name the 0006 ALTER stores.
        CheckConstraint(
            "continuity_spec_hash IS NULL OR length(continuity_spec_hash) = 64",
            name="continuity_spec_hash_len",
        ),
        Index(
            "ix_shot_revisions_continuity_spec_hash", "continuity_spec_hash"
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    shot_id: Mapped[str] = mapped_column(UUID, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    continuity_spec_json: Mapped[str | None] = mapped_column(Text)
    continuity_spec_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
