"""story world and semantic dependencies (M6)

Revision ID: 0006_story_world_semantic_dependencies
Revises: 0005_soft_cancel_selection
Create Date: 2026-08-17

One migration for the whole M6 milestone (plan §67–§68), in the plan's
creation order. Behavior lands slice by slice (M6A entities, M6B narrative,
M6C dependencies); the schema is frozen once here.

Structural decision (plan §35, §70): NO populated table is rebuilt.
``shots`` gains its narrative columns via plain ``ALTER TABLE ADD COLUMN``
with NAMED CHECK constraints — the pinned SQLite accepts the named pair
CHECK through ADD COLUMN when ``scene_id`` is added first, and preserves the
constraint names in stored DDL (proven by tests/test_migration_m6.py). The
(scene_id, scene_position) uniqueness is a standalone UNIQUE INDEX (NULLs
are distinct in SQLite, so unassigned Shots never clash) rather than a
table constraint that would force a batch rebuild. ``scene_id`` carries no
REFERENCES clause for the same parity reason (mirrors approved_take_id);
scene validity is enforced by the M6B assignment transaction.

Existing data: zero semantic inference (plan §69). New columns default
NULL; legacy ShotRevisions keep NULL continuity columns; nothing is
recomputed, promoted, or placed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_story_world_semantic_dependencies"
down_revision: Union[str, None] = "0005_soft_cancel_selection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"

_KINDS = "'character', 'location', 'prop', 'costume', 'vehicle'"

_SPEC_TABLES = (
    "character_revision_specs",
    "location_revision_specs",
    "prop_revision_specs",
    "costume_revision_specs",
    "vehicle_revision_specs",
)


def upgrade() -> None:
    # --- Story World identity ------------------------------------------------
    op.create_table(
        "creative_entities",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_creative_entities"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_creative_entities_project_id_projects", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"kind IN ({_KINDS})", name="ck_creative_entities_kind"
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0", name="ck_creative_entities_name_nonempty"
        ),
        sa.CheckConstraint(
            "length(name) <= 500", name="ck_creative_entities_name_maxlen"
        ),
    )
    op.create_index(
        "ix_creative_entities_project_kind", "creative_entities",
        ["project_id", "kind", "deleted_at", "name"],
    )
    op.create_index(
        "ix_creative_entities_project_created", "creative_entities",
        ["project_id", "deleted_at", "created_at"],
    )

    # --- Immutable design revisions ------------------------------------------
    op.create_table(
        "entity_revisions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("spec_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.PrimaryKeyConstraint("id", name="pk_entity_revisions"),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["creative_entities.id"],
            name="fk_entity_revisions_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "entity_id", "revision_number",
            name="uq_entity_revisions_entity_id_revision_number",
        ),
        sa.UniqueConstraint(
            "entity_id", "spec_hash",
            name="uq_entity_revisions_entity_id_spec_hash",
        ),
        sa.UniqueConstraint(
            "id", "entity_id", name="uq_entity_revisions_id_entity_id"
        ),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_entity_revisions_revision_number_positive",
        ),
        sa.CheckConstraint(
            "schema_version >= 1",
            name="ck_entity_revisions_schema_version_positive",
        ),
        sa.CheckConstraint(
            "length(spec_hash) = 64", name="ck_entity_revisions_spec_hash_len"
        ),
    )
    op.create_index(
        "ix_entity_revisions_entity_id_created", "entity_revisions",
        ["entity_id", "created_at"],
    )

    # --- Kind-specific revision payloads (M6 §20) -----------------------------
    for table in _SPEC_TABLES:
        op.create_table(
            table,
            sa.Column("revision_id", sa.String(36), nullable=False),
            sa.Column("spec_json", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("revision_id", name=f"pk_{table}"),
            sa.ForeignKeyConstraint(
                ["revision_id"], ["entity_revisions.id"],
                name=f"fk_{table}_revision_id_entity_revisions",
                ondelete="RESTRICT",
            ),
        )

    # --- Explicit approved revision (composite FK → own revisions only) ------
    op.create_table(
        "entity_approved_revisions",
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("approved_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("entity_id", name="pk_entity_approved_revisions"),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["creative_entities.id"],
            name="fk_entity_approved_revisions_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id", "entity_id"],
            ["entity_revisions.id", "entity_revisions.entity_id"],
            name="fk_entity_approved_revisions_revision_id_entity_revisions",
            ondelete="RESTRICT",
        ),
    )

    # --- Narrative topology (behavior lands in M6B) ---------------------------
    op.create_table(
        "sequences",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_sequences"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_sequences_project_id_projects", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "project_id", "position", name="uq_sequences_project_id_position"
        ),
        sa.CheckConstraint("position >= 0", name="ck_sequences_position_nonneg"),
    )
    op.create_index(
        "ix_sequences_project_active", "sequences",
        ["project_id", "deleted_at", "position"],
    )

    op.create_table(
        "scenes",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("sequence_id", sa.String(36), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_scenes"),
        sa.ForeignKeyConstraint(
            ["sequence_id"], ["sequences.id"],
            name="fk_scenes_sequence_id_sequences", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "sequence_id", "position", name="uq_scenes_sequence_id_position"
        ),
        sa.CheckConstraint("position >= 0", name="ck_scenes_position_nonneg"),
    )
    op.create_index(
        "ix_scenes_sequence_active", "scenes",
        ["sequence_id", "deleted_at", "position"],
    )

    # --- shots: narrative assignment, NO rebuild (plan §35) -------------------
    # scene_id first: the pair CHECK on scene_position references it.
    op.execute("ALTER TABLE shots ADD COLUMN scene_id VARCHAR(36)")
    op.execute(
        "ALTER TABLE shots ADD COLUMN scene_position INTEGER "
        "CONSTRAINT ck_shots_scene_pair "
        "CHECK ((scene_id IS NULL) = (scene_position IS NULL)) "
        "CONSTRAINT ck_shots_scene_position_nonneg "
        "CHECK (scene_position IS NULL OR scene_position >= 0)"
    )
    op.create_index(
        "uq_shots_scene_position", "shots",
        ["scene_id", "scene_position"], unique=True,
    )

    # --- Shot WORKING dependencies (behavior lands in M6C) --------------------
    op.create_table(
        "shot_entity_dependencies",
        sa.Column("shot_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.PrimaryKeyConstraint(
            "shot_id", "entity_id", "role", name="pk_shot_entity_dependencies"
        ),
        sa.ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_shot_entity_dependencies_shot_id_shots", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["creative_entities.id"],
            name="fk_shot_entity_dependencies_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "shot_id", "role", "position",
            name="uq_shot_entity_dependencies_shot_id_role_position",
        ),
        sa.CheckConstraint(
            "position >= 0", name="ck_shot_entity_dependencies_position_nonneg"
        ),
        sa.CheckConstraint(
            "length(role) BETWEEN 1 AND 64 AND length(trim(role)) > 0",
            name="ck_shot_entity_dependencies_role",
        ),
    )
    op.create_index(
        "ix_shot_entity_dependencies_entity_id", "shot_entity_dependencies",
        ["entity_id"],
    )

    # --- shot_revisions: continuity specification (schema v2, M6C) ------------
    op.execute(
        "ALTER TABLE shot_revisions ADD COLUMN continuity_spec_json TEXT"
    )
    op.execute(
        "ALTER TABLE shot_revisions ADD COLUMN continuity_spec_hash TEXT "
        "CONSTRAINT ck_shot_revisions_continuity_spec_hash_len "
        "CHECK (continuity_spec_hash IS NULL "
        "OR length(continuity_spec_hash) = 64)"
    )
    op.create_index(
        "ix_shot_revisions_continuity_spec_hash", "shot_revisions",
        ["continuity_spec_hash"],
    )

    # --- Immutable ShotRevision dependency snapshot (M6C) ---------------------
    op.create_table(
        "shot_revision_entity_dependencies",
        sa.Column("shot_revision_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("entity_revision_id", sa.String(36), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "shot_revision_id", "role", "position",
            name="pk_shot_revision_entity_dependencies",
        ),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_shot_revision_entity_dependencies_shot_revision_id_shot_revisions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["entity_revision_id", "entity_id"],
            ["entity_revisions.id", "entity_revisions.entity_id"],
            name="fk_shot_revision_entity_dependencies_entity_revision_id_entity_revisions",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "shot_revision_id", "entity_revision_id", "role",
            name="uq_shot_revision_entity_dependencies_revision_entity_role",
        ),
        sa.CheckConstraint(
            "position >= 0",
            name="ck_shot_revision_entity_dependencies_position_nonneg",
        ),
        sa.CheckConstraint(
            "length(role) BETWEEN 1 AND 64 AND length(trim(role)) > 0",
            name="ck_shot_revision_entity_dependencies_role",
        ),
        sa.CheckConstraint(
            "source IN ('shot_explicit')",
            name="ck_shot_revision_entity_dependencies_source",
        ),
    )
    op.create_index(
        "ix_shot_revision_entity_dependencies_entity_revision_id",
        "shot_revision_entity_dependencies", ["entity_revision_id"],
    )
    op.create_index(
        "ix_shot_revision_entity_dependencies_entity_id",
        "shot_revision_entity_dependencies", ["entity_id"],
    )


def downgrade() -> None:
    op.drop_table("shot_revision_entity_dependencies")
    op.drop_index("ix_shot_revisions_continuity_spec_hash",
                  table_name="shot_revisions")
    # Column-level CHECKs go with their columns; drop hashed column first.
    op.execute("ALTER TABLE shot_revisions DROP COLUMN continuity_spec_hash")
    op.execute("ALTER TABLE shot_revisions DROP COLUMN continuity_spec_json")
    op.drop_table("shot_entity_dependencies")
    op.drop_index("uq_shots_scene_position", table_name="shots")
    # scene_position first: its pair CHECK references scene_id.
    op.execute("ALTER TABLE shots DROP COLUMN scene_position")
    op.execute("ALTER TABLE shots DROP COLUMN scene_id")
    op.drop_table("scenes")
    op.drop_table("sequences")
    op.drop_table("entity_approved_revisions")
    for table in reversed(_SPEC_TABLES):
        op.drop_table(table)
    op.drop_index("ix_entity_revisions_entity_id_created",
                  table_name="entity_revisions")
    op.drop_table("entity_revisions")
    op.drop_index("ix_creative_entities_project_created",
                  table_name="creative_entities")
    op.drop_index("ix_creative_entities_project_kind",
                  table_name="creative_entities")
    op.drop_table("creative_entities")
