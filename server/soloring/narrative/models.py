"""ORM models: Sequence and Scene — narrative topology only (M6 §32–§33).

M6B implements the behavior; the tables exist from migration 0006 so the
ORM metadata and the migration head stay in parity. No continuity state
lives here (M6 boundary).
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from soloring.db.base import Base
from soloring.db.timeutil import DB_NOW_SQL

UUID = String(36)

# Active-only uniqueness (M6B re-gate): a soft-deleted row keeps its last
# narrative coordinates forever, and uniqueness applies to ACTIVE rows only,
# so active siblings can compact to 0..N-1 without colliding with tombstones.
_ACTIVE = text("deleted_at IS NULL")


class Sequence(Base):
    __tablename__ = "sequences"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_sequences"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_sequences_project_id_projects", ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 0", name="ck_sequences_position_nonneg"),
        Index(
            "uq_sequences_project_id_position", "project_id", "position",
            unique=True, sqlite_where=_ACTIVE,
        ),
        Index("ix_sequences_project_active", "project_id", "deleted_at", "position"),
    )

    id: Mapped[str] = mapped_column(UUID)
    project_id: Mapped[str] = mapped_column(UUID, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)


class Scene(Base):
    __tablename__ = "scenes"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_scenes"),
        ForeignKeyConstraint(
            ["sequence_id"], ["sequences.id"],
            name="fk_scenes_sequence_id_sequences", ondelete="RESTRICT",
        ),
        CheckConstraint("position >= 0", name="ck_scenes_position_nonneg"),
        Index(
            "uq_scenes_sequence_id_position", "sequence_id", "position",
            unique=True, sqlite_where=_ACTIVE,
        ),
        Index("ix_scenes_sequence_active", "sequence_id", "deleted_at", "position"),
    )

    id: Mapped[str] = mapped_column(UUID)
    sequence_id: Mapped[str] = mapped_column(UUID, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    deleted_at: Mapped[str | None] = mapped_column(Text)
