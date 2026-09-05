"""ORM models: reusable production authority (frozen R3 plan §5).

Four tables, exactly as frozen:

- ``production_objects``                 stable reusable identity (mutable
                                          display metadata only)
- ``production_revisions``               immutable published schema-1 snapshots
- ``production_revision_closures``       permanent retained_blob/v1 projection
- ``production_revision_source_assets``  append-only provenance links

No predecessor table is rebuilt or widened. Immutable tables carry no
``updated_at``/``deleted_at`` (house shape discipline).
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


class ProductionObject(Base):
    """Stable filmmaker-facing reusable production identity (plan §3.1).

    The UUID is the identity; name/description are display metadata and are
    deliberately not unique.
    """

    __tablename__ = "production_objects"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_production_objects"),
        ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_production_objects_project_id_projects", ondelete="RESTRICT",
        ),
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 500",
            name="ck_production_objects_name_len",
        ),
        Index(
            "ix_production_objects_project_created", "project_id", "created_at"
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    project_id: Mapped[str] = mapped_column(UUID, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class ProductionRevision(Base):
    """One immutable published state under exactly one Production Object.

    ``(production_object_id, snapshot_hash)`` is the schema-1 semantic
    convergence identity; source Asset identity never enters the snapshot.
    """

    __tablename__ = "production_revisions"

    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_production_revisions"),
        ForeignKeyConstraint(
            ["production_object_id"], ["production_objects.id"],
            name="fk_production_revisions_object_id", ondelete="RESTRICT",
        ),
        CheckConstraint("revision_number >= 1", name="ck_production_revisions_number_pos"),
        CheckConstraint("length(snapshot_hash) = 64", name="ck_production_revisions_hash_len"),
        UniqueConstraint(
            "production_object_id", "revision_number",
            name="uq_production_revisions_object_number",
        ),
        UniqueConstraint(
            "production_object_id", "snapshot_hash",
            name="uq_production_revisions_object_hash",
        ),
        Index(
            "ix_production_revisions_object_created",
            "production_object_id", "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(UUID)
    production_object_id: Mapped[str] = mapped_column(UUID, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )


class ProductionRevisionClosure(Base):
    """Permanent normalized ``retained_blob/v1`` projection (plan §§3.3/5.3).

    Exactly one row per M11 Production Revision. The CHECKs hard-freeze the
    schema-1 meaning; future consumer contracts evolve additively elsewhere.
    """

    __tablename__ = "production_revision_closures"

    __table_args__ = (
        PrimaryKeyConstraint("production_revision_id", name="pk_production_revision_closures"),
        ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_production_revision_closures_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_production_revision_closures_blob", ondelete="RESTRICT",
        ),
        CheckConstraint("contract_key = 'retained_blob'", name="ck_prc_contract_key"),
        CheckConstraint("contract_version = 1", name="ck_prc_contract_version"),
        CheckConstraint("length(blob_hash) = 64", name="ck_prc_blob_hash_len"),
        CheckConstraint("size_bytes > 0", name="ck_prc_size_pos"),
        CheckConstraint(
            "media_type IS NULL OR ("
            "length(trim(media_type)) BETWEEN 1 AND 255 "
            "AND media_type = trim(media_type))",
            name="ck_prc_media_type_grammar",
        ),
        Index("ix_production_revision_closures_blob", "blob_hash"),
    )

    production_revision_id: Mapped[str] = mapped_column(UUID)
    contract_key: Mapped[str] = mapped_column(Text, nullable=False)
    contract_version: Mapped[int] = mapped_column(Integer, nullable=False)
    blob_hash: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str | None] = mapped_column(Text)


class ProductionRevisionSourceAsset(Base):
    """Append-only provenance edge (plan §4.5).

    Excluded from Production Revision canonical identity; the service and
    verifiers prove Project and Blob agreement with the owning closure.
    """

    __tablename__ = "production_revision_source_assets"

    __table_args__ = (
        PrimaryKeyConstraint(
            "production_revision_id", "asset_id",
            name="pk_production_revision_source_assets",
        ),
        ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_production_revision_source_assets_revision", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_production_revision_source_assets_asset", ondelete="RESTRICT",
        ),
        Index("ix_production_revision_source_assets_asset", "asset_id"),
    )

    production_revision_id: Mapped[str] = mapped_column(UUID)
    asset_id: Mapped[str] = mapped_column(UUID)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(DB_NOW_SQL)
    )
