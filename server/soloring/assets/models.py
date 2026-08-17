"""ORM models: Blobs, Assets (plan §17–§18)."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Float,
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


class Blob(Base):
    """Immutable physical bytes identified by SHA-256 (plan §17)."""

    __tablename__ = "blobs"

    __table_args__ = (
        PrimaryKeyConstraint("hash", name="pk_blobs"),
        UniqueConstraint("path", name="uq_blobs_path"),
        CheckConstraint("length(hash) = 64", name="ck_blobs_hash_len"),
        CheckConstraint("size_bytes >= 0", name="ck_blobs_size_nonneg"),
        Index("ix_blobs_created_at", "created_at"),
    )

    hash: Mapped[str] = mapped_column(Text)  # noqa: A003 - column is literally "hash"
    path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_media_type: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class Asset(Base):
    """One explicit provenance event over a Blob (plan §18, §26)."""

    __tablename__ = "assets"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_assets"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_assets_project_id_projects", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["take_id"], ["takes.id"],
            name="fk_assets_take_id_takes", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_assets_blob_hash_blobs", ondelete="RESTRICT",
        ),
        CheckConstraint("kind IN ('reference', 'output')", name="ck_assets_kind"),
        CheckConstraint(
            "(kind = 'reference' AND take_id IS NULL) "
            "OR (kind = 'output' AND take_id IS NOT NULL)",
            name="ck_assets_kind_take_consistency",
        ),
        CheckConstraint("width IS NULL OR width > 0", name="ck_assets_width_pos"),
        CheckConstraint("height IS NULL OR height > 0", name="ck_assets_height_pos"),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_assets_duration_nonneg"
        ),
        CheckConstraint("fps IS NULL OR fps > 0", name="ck_assets_fps_pos"),
        Index("ix_assets_project_created", "project_id", "created_at"),
        Index("ix_assets_take", "take_id"),
        Index("ix_assets_blob_hash", "blob_hash"),
    )

    id: Mapped[str] = mapped_column(UUID)
    project_id: Mapped[str] = mapped_column(UUID, nullable=False)
    take_id: Mapped[str | None] = mapped_column(UUID)
    blob_hash: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)

    upload_mime_type: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(Text)

    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
