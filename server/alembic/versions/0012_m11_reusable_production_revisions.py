"""m11 reusable production revision foundation

Revision ID: 0012_m11_reusable_production_revisions
Revises: 0011_m10_derived_spatial_execution
Create Date: 2026-09-05

Frozen R3 plan §5: exactly four additive authority/provenance tables. No
predecessor table is rebuilt or widened; no backfill of invented Production
Objects/Revisions.

Downgrade (§5.6): fail-closed preflight BEFORE any DDL refuses when any of
the four M11 tables has rows. A bare Production Object is durable
user-authored state; a published revision/closure is immutable authority.
Only a wholly unused 0012 schema may be dropped.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_m11_reusable_production_revisions"
down_revision: Union[str, None] = "0011_m10_derived_spatial_execution"

_M11_TABLES = (
    "production_revision_source_assets",
    "production_revision_closures",
    "production_revisions",
    "production_objects",
)


def _preflight_clear(conn) -> None:
    for table in _M11_TABLES:
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0012 downgrade refused: {table} contains {n} row(s); "
                "authored M11 production state is never destroyed by downgrade"
            )


def upgrade() -> None:
    op.create_table(
        "production_objects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 500",
            name="ck_production_objects_name_len",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_production_objects_project_id_projects", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_production_objects_project_created",
        "production_objects", ["project_id", "created_at"],
    )

    op.create_table(
        "production_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("production_object_id", sa.String(36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("revision_number >= 1", name="ck_production_revisions_number_pos"),
        sa.CheckConstraint("length(snapshot_hash) = 64", name="ck_production_revisions_hash_len"),
        sa.ForeignKeyConstraint(
            ["production_object_id"], ["production_objects.id"],
            name="fk_production_revisions_object_id", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "production_object_id", "revision_number",
            name="uq_production_revisions_object_number",
        ),
        sa.UniqueConstraint(
            "production_object_id", "snapshot_hash",
            name="uq_production_revisions_object_hash",
        ),
    )
    op.create_index(
        "ix_production_revisions_object_created",
        "production_revisions", ["production_object_id", "created_at"],
    )

    op.create_table(
        "production_revision_closures",
        sa.Column("production_revision_id", sa.String(36), primary_key=True),
        sa.Column("contract_key", sa.Text(), nullable=False),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=True),
        sa.CheckConstraint("contract_key = 'retained_blob'", name="ck_prc_contract_key"),
        sa.CheckConstraint("contract_version = 1", name="ck_prc_contract_version"),
        sa.CheckConstraint("length(blob_hash) = 64", name="ck_prc_blob_hash_len"),
        sa.CheckConstraint("size_bytes > 0", name="ck_prc_size_pos"),
        sa.CheckConstraint(
            "media_type IS NULL OR ("
            "length(trim(media_type)) BETWEEN 1 AND 255 "
            "AND media_type = trim(media_type))",
            name="ck_prc_media_type_grammar",
        ),
        sa.ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_production_revision_closures_revision", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_production_revision_closures_blob", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_production_revision_closures_blob",
        "production_revision_closures", ["blob_hash"],
    )

    op.create_table(
        "production_revision_source_assets",
        sa.Column("production_revision_id", sa.String(36), primary_key=True),
        sa.Column("asset_id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_production_revision_source_assets_revision", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_production_revision_source_assets_asset", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_production_revision_source_assets_asset",
        "production_revision_source_assets", ["asset_id"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    _preflight_clear(conn)
    op.drop_table("production_revision_source_assets")
    op.drop_table("production_revision_closures")
    op.drop_table("production_revisions")
    op.drop_table("production_objects")
