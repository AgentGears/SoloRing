"""m8 visual identity

Revision ID: 0009_m8_visual_identity
Revises: 0008_narrative_continuity_state
Create Date: 2026-08-20

Creates ONLY the new M8 tables and indexes (frozen plan §74). No existing
table is rebuilt or altered; existing ShotRevision rows remain
byte-for-byte unchanged.

Downgrade contract (§75): lossless-or-refused. The preflight runs BEFORE
any DDL and refuses when ANY row exists in ANY M8 table (soft-deleted rows
count; data is never disposable) or any ShotRevision snapshot parses to
schema_version >= 4. Malformed snapshot JSON during the scan is itself
refusal. An empty never-used M8 schema may downgrade normally.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_m8_visual_identity"
down_revision: Union[str, None] = "0008_narrative_continuity_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"

_M8_TARGET_KINDS = "'entity', 'feature'"
_M8_REQUIREMENTS = "'required', 'optional'"
_M8_POLICIES = "'required', 'optional', 'not_applicable'"
_M8_ROLES = "'primary', 'supporting', 'detail', 'context'"
_FACET_KEY_CHECK = (
    "length(facet_key) BETWEEN 1 AND 128 "
    "AND facet_key NOT GLOB '*[^a-z0-9._-]*'"
)

_M8_TABLES = (
    "visual_facets",
    "visual_facet_value_policies",
    "visual_anchors",
    "visual_anchor_items",
    "visual_anchor_revisions",
    "visual_anchor_revision_items",
    "shot_revision_visual_anchors",
    "shot_revision_visual_anchor_items",
)


def upgrade() -> None:
    op.create_table(
        "visual_facets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("feature_id", sa.String(36), nullable=True),
        sa.Column("facet_key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_visual_facets"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_visual_facets_project_id_projects",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["creative_entities.id"],
            name="fk_visual_facets_entity_id_creative_entities",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["continuity_features.id"],
            name="fk_visual_facets_feature_id_continuity_features",
            ondelete="RESTRICT"),
        sa.CheckConstraint(
            f"target_kind IN ({_M8_TARGET_KINDS})",
            name="ck_visual_facets_target_kind"),
        sa.CheckConstraint(
            f"requirement IN ({_M8_REQUIREMENTS})",
            name="ck_visual_facets_requirement"),
        sa.CheckConstraint(_FACET_KEY_CHECK,
                           name="ck_visual_facets_facet_key"),
        sa.CheckConstraint(
            "(target_kind = 'entity' AND entity_id IS NOT NULL "
            "AND feature_id IS NULL) OR "
            "(target_kind = 'feature' AND feature_id IS NOT NULL "
            "AND entity_id IS NULL)",
            name="ck_visual_facets_target_shape"),
    )
    op.create_index(
        "ix_visual_facets_project", "visual_facets",
        ["project_id", "deleted_at"])
    op.create_index(
        "ix_visual_facets_entity_target", "visual_facets",
        ["entity_id", "facet_key", "deleted_at"])
    op.create_index(
        "ix_visual_facets_feature_target", "visual_facets",
        ["feature_id", "facet_key", "deleted_at"])
    op.create_index(
        "uq_visual_facets_entity_active", "visual_facets",
        ["entity_id", "facet_key"], unique=True,
        sqlite_where=sa.text(
            "target_kind = 'entity' AND deleted_at IS NULL"))
    op.create_index(
        "uq_visual_facets_feature_active", "visual_facets",
        ["feature_id", "facet_key"], unique=True,
        sqlite_where=sa.text(
            "target_kind = 'feature' AND deleted_at IS NULL"))

    op.create_table(
        "visual_facet_value_policies",
        sa.Column("visual_facet_id", sa.String(36), nullable=False),
        sa.Column("feature_value_hash", sa.Text(), nullable=False),
        sa.Column("feature_value_json", sa.Text(), nullable=False),
        sa.Column("policy", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.PrimaryKeyConstraint(
            "visual_facet_id", "feature_value_hash",
            name="pk_visual_facet_value_policies"),
        sa.ForeignKeyConstraint(
            ["visual_facet_id"], ["visual_facets.id"],
            name="fk_visual_facet_value_policies_visual_facet_id_"
                 "visual_facets",
            ondelete="RESTRICT"),
        sa.CheckConstraint(
            f"policy IN ({_M8_POLICIES})",
            name="ck_visual_facet_value_policies_policy"),
        sa.CheckConstraint(
            "length(feature_value_hash) = 64",
            name="ck_visual_facet_value_policies_value_hash_len"),
        sa.CheckConstraint(
            "length(feature_value_json) > 0",
            name="ck_visual_facet_value_policies_value_json_nonempty"),
    )

    op.create_table(
        "visual_anchors",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("visual_facet_id", sa.String(36), nullable=False),
        sa.Column("entity_revision_id", sa.String(36), nullable=True),
        sa.Column("feature_value_hash", sa.Text(), nullable=True),
        sa.Column("feature_value_json", sa.Text(), nullable=True),
        sa.Column("visual_context_entity_revision_id", sa.String(36),
                  nullable=True),
        sa.Column("approved_revision_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_visual_anchors"),
        sa.ForeignKeyConstraint(
            ["visual_facet_id"], ["visual_facets.id"],
            name="fk_visual_anchors_visual_facet_id_visual_facets",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["entity_revision_id"], ["entity_revisions.id"],
            name="fk_visual_anchors_entity_revision_id_entity_revisions",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["visual_context_entity_revision_id"], ["entity_revisions.id"],
            name="fk_visual_anchors_visual_context_entity_revision_id_"
                 "entity_revisions",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["approved_revision_id"], ["visual_anchor_revisions.id"],
            name="fk_visual_anchors_approved_revision_id_"
                 "visual_anchor_revisions",
            ondelete="RESTRICT", use_alter=True),
        sa.CheckConstraint(
            "length(feature_value_hash) = 64 OR feature_value_hash IS NULL",
            name="ck_visual_anchors_feature_value_hash_len"),
        sa.CheckConstraint(
            "(entity_revision_id IS NOT NULL "
            "AND feature_value_hash IS NULL AND feature_value_json IS NULL "
            "AND visual_context_entity_revision_id IS NULL) OR "
            "(entity_revision_id IS NULL AND feature_value_hash IS NOT NULL "
            "AND feature_value_json IS NOT NULL "
            "AND visual_context_entity_revision_id IS NOT NULL)",
            name="ck_visual_anchors_binding_shape"),
    )
    op.create_index(
        "uq_visual_anchors_entity_state_active", "visual_anchors",
        ["visual_facet_id", "entity_revision_id"], unique=True,
        sqlite_where=sa.text(
            "entity_revision_id IS NOT NULL AND deleted_at IS NULL"))
    op.create_index(
        "uq_visual_anchors_feature_state_active", "visual_anchors",
        ["visual_facet_id", "feature_value_hash",
         "visual_context_entity_revision_id"], unique=True,
        sqlite_where=sa.text(
            "feature_value_hash IS NOT NULL "
            "AND visual_context_entity_revision_id IS NOT NULL "
            "AND deleted_at IS NULL"))
    op.create_index(
        "ix_visual_anchors_entity_state", "visual_anchors",
        ["visual_facet_id", "entity_revision_id", "deleted_at"])
    op.create_index(
        "ix_visual_anchors_feature_state", "visual_anchors",
        ["visual_facet_id", "feature_value_hash",
         "visual_context_entity_revision_id", "deleted_at"])
    op.create_index(
        "ix_visual_anchors_approved_revision", "visual_anchors",
        ["approved_revision_id"])

    op.create_table(
        "visual_anchor_items",
        sa.Column("visual_anchor_id", sa.String(36), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("view_key", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.PrimaryKeyConstraint(
            "visual_anchor_id", "asset_id", name="pk_visual_anchor_items"),
        sa.ForeignKeyConstraint(
            ["visual_anchor_id"], ["visual_anchors.id"],
            name="fk_visual_anchor_items_visual_anchor_id_visual_anchors",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_visual_anchor_items_asset_id_assets",
            ondelete="RESTRICT"),
        sa.CheckConstraint(
            f"role IN ({_M8_ROLES})",
            name="ck_visual_anchor_items_role"),
        sa.CheckConstraint(
            "position >= 0", name="ck_visual_anchor_items_position_nonneg"),
        sa.CheckConstraint(
            "view_key IS NULL OR (length(view_key) BETWEEN 1 AND 64 "
            "AND view_key = trim(view_key))",
            name="ck_visual_anchor_items_view_key"),
        sa.UniqueConstraint(
            "visual_anchor_id", "position",
            name="uq_visual_anchor_items_anchor_position"),
    )
    op.create_index(
        "ix_visual_anchor_items_asset", "visual_anchor_items", ["asset_id"])

    op.create_table(
        "visual_anchor_revisions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("visual_anchor_id", sa.String(36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.PrimaryKeyConstraint("id", name="pk_visual_anchor_revisions"),
        sa.ForeignKeyConstraint(
            ["visual_anchor_id"], ["visual_anchors.id"],
            name="fk_visual_anchor_revisions_visual_anchor_id_"
                 "visual_anchors",
            ondelete="RESTRICT"),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_visual_anchor_revisions_number_positive"),
        sa.CheckConstraint(
            "length(snapshot_hash) = 64",
            name="ck_visual_anchor_revisions_snapshot_hash_len"),
        sa.UniqueConstraint(
            "visual_anchor_id", "revision_number",
            name="uq_visual_anchor_revisions_anchor_number"),
        sa.UniqueConstraint(
            "visual_anchor_id", "snapshot_hash",
            name="uq_visual_anchor_revisions_anchor_hash"),
    )

    op.create_table(
        "visual_anchor_revision_items",
        sa.Column("visual_anchor_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("view_key", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "visual_anchor_revision_id", "position",
            name="pk_visual_anchor_revision_items"),
        sa.ForeignKeyConstraint(
            ["visual_anchor_revision_id"], ["visual_anchor_revisions.id"],
            name="fk_visual_anchor_revision_items_visual_anchor_revision_"
                 "id_visual_anchor_revisions",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_visual_anchor_revision_items_asset_id_assets",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_visual_anchor_revision_items_blob_hash_blobs",
            ondelete="RESTRICT"),
        sa.CheckConstraint(
            f"role IN ({_M8_ROLES})",
            name="ck_visual_anchor_revision_items_role"),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_visual_anchor_revision_items_position_nonneg"),
        sa.UniqueConstraint(
            "visual_anchor_revision_id", "asset_id",
            name="uq_visual_anchor_revision_items_asset"),
    )
    op.create_index(
        "ix_visual_anchor_revision_items_asset",
        "visual_anchor_revision_items", ["asset_id"])
    op.create_index(
        "ix_visual_anchor_revision_items_blob",
        "visual_anchor_revision_items", ["blob_hash"])

    op.create_table(
        "shot_revision_visual_anchors",
        sa.Column("shot_revision_id", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("visual_facet_id", sa.String(36), nullable=False),
        sa.Column("facet_key", sa.Text(), nullable=False),
        sa.Column("visual_anchor_id", sa.String(36), nullable=False),
        sa.Column("visual_anchor_revision_id", sa.String(36),
                  nullable=False),
        sa.Column("visual_anchor_snapshot_hash", sa.Text(),
                  nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("entity_revision_id", sa.String(36), nullable=True),
        sa.Column("feature_id", sa.String(36), nullable=True),
        sa.Column("feature_value_hash", sa.Text(), nullable=True),
        sa.Column("feature_value_json", sa.Text(), nullable=True),
        sa.Column("visual_context_entity_revision_id", sa.String(36),
                  nullable=True),
        sa.PrimaryKeyConstraint(
            "shot_revision_id", "position",
            name="pk_shot_revision_visual_anchors"),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_shot_revision_visual_anchors_shot_revision_id_"
                 "shot_revisions",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["visual_facet_id"], ["visual_facets.id"],
            name="fk_shot_revision_visual_anchors_visual_facet_id_"
                 "visual_facets",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["visual_anchor_id"], ["visual_anchors.id"],
            name="fk_shot_revision_visual_anchors_visual_anchor_id_"
                 "visual_anchors",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["visual_anchor_revision_id"], ["visual_anchor_revisions.id"],
            name="fk_shot_revision_visual_anchors_visual_anchor_revision_"
                 "id_visual_anchor_revisions",
            ondelete="RESTRICT"),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_shot_revision_visual_anchors_position_nonneg"),
        sa.CheckConstraint(
            "length(visual_anchor_snapshot_hash) = 64",
            name="ck_shot_revision_visual_anchors_hash_len"),
        sa.CheckConstraint(
            f"target_kind IN ({_M8_TARGET_KINDS})",
            name="ck_shot_revision_visual_anchors_target_kind"),
        sa.CheckConstraint(
            "length(feature_value_hash) = 64 "
            "OR feature_value_hash IS NULL",
            name="ck_shot_revision_visual_anchors_value_hash_len"),
    )
    op.create_index(
        "ix_shot_revision_visual_anchors_facet",
        "shot_revision_visual_anchors", ["visual_facet_id"])

    op.create_table(
        "shot_revision_visual_anchor_items",
        sa.Column("shot_revision_id", sa.String(36), nullable=False),
        sa.Column("anchor_position", sa.Integer(), nullable=False),
        sa.Column("item_position", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.String(36), nullable=False),
        sa.Column("blob_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("view_key", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "shot_revision_id", "anchor_position", "item_position",
            name="pk_shot_revision_visual_anchor_items"),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_shot_revision_visual_anchor_items_shot_revision_id_"
                 "shot_revisions",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["assets.id"],
            name="fk_shot_revision_visual_anchor_items_asset_id_assets",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["blob_hash"], ["blobs.hash"],
            name="fk_shot_revision_visual_anchor_items_blob_hash_blobs",
            ondelete="RESTRICT"),
        sa.CheckConstraint(
            f"role IN ({_M8_ROLES})",
            name="ck_shot_revision_visual_anchor_items_role"),
        sa.CheckConstraint(
            "anchor_position >= 0 AND item_position >= 0",
            name="ck_shot_revision_visual_anchor_items_positions"),
    )
    op.create_index(
        "ix_shot_revision_visual_anchor_items_asset",
        "shot_revision_visual_anchor_items", ["asset_id"])
    op.create_index(
        "ix_shot_revision_visual_anchor_items_blob",
        "shot_revision_visual_anchor_items", ["blob_hash"])


def downgrade() -> None:
    import json

    conn = op.get_bind()

    # Preflight BEFORE any DDL (§75): refuse when any M8 state exists.
    for table in _M8_TABLES:
        n = conn.execute(sa.text(
            f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"Cannot downgrade 0009: {table} has {n} row(s). M8 state "
                "is production authority and is never destroyed by a "
                "downgrade."
            )

    snapshots = conn.execute(sa.text(
        "SELECT snapshot_json FROM shot_revisions")).fetchall()
    for (snapshot_json,) in snapshots:
        try:
            version = json.loads(snapshot_json).get("schema_version")
        except (ValueError, TypeError, AttributeError):
            raise RuntimeError(
                "Cannot downgrade 0009: a ShotRevision snapshot_json is "
                "malformed; failure to prove safety IS refusal."
            )
        if not isinstance(version, int) or version >= 4:
            raise RuntimeError(
                "Cannot downgrade 0009: schema-4 ShotRevision state "
                "exists (or version unreadable); visual history is never "
                "destroyed."
            )

    op.drop_index(
        "ix_shot_revision_visual_anchor_items_blob",
        table_name="shot_revision_visual_anchor_items")
    op.drop_index(
        "ix_shot_revision_visual_anchor_items_asset",
        table_name="shot_revision_visual_anchor_items")
    op.drop_table("shot_revision_visual_anchor_items")
    op.drop_index(
        "ix_shot_revision_visual_anchors_facet",
        table_name="shot_revision_visual_anchors")
    op.drop_table("shot_revision_visual_anchors")
    op.drop_index(
        "ix_visual_anchor_revision_items_blob",
        table_name="visual_anchor_revision_items")
    op.drop_index(
        "ix_visual_anchor_revision_items_asset",
        table_name="visual_anchor_revision_items")
    op.drop_table("visual_anchor_revision_items")
    op.drop_table("visual_anchor_revisions")
    op.drop_index(
        "ix_visual_anchor_items_asset", table_name="visual_anchor_items")
    op.drop_table("visual_anchor_items")
    op.drop_index(
        "ix_visual_anchors_approved_revision", table_name="visual_anchors")
    op.drop_index(
        "ix_visual_anchors_feature_state", table_name="visual_anchors")
    op.drop_index(
        "ix_visual_anchors_entity_state", table_name="visual_anchors")
    op.drop_index(
        "uq_visual_anchors_feature_state_active", table_name="visual_anchors")
    op.drop_index(
        "uq_visual_anchors_entity_state_active", table_name="visual_anchors")
    op.drop_table("visual_anchors")
    op.drop_table("visual_facet_value_policies")
    op.drop_index(
        "uq_visual_facets_feature_active", table_name="visual_facets")
    op.drop_index(
        "uq_visual_facets_entity_active", table_name="visual_facets")
    op.drop_index(
        "ix_visual_facets_feature_target", table_name="visual_facets")
    op.drop_index(
        "ix_visual_facets_entity_target", table_name="visual_facets")
    op.drop_index(
        "ix_visual_facets_project", table_name="visual_facets")
    op.drop_table("visual_facets")
