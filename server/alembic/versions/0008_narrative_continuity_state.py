"""narrative continuity state (M7A)

Revision ID: 0008_narrative_continuity_state
Revises: 0007_active_narrative_uniqueness
Create Date: 2026-08-18

Creates ONLY the new M7 tables and indexes (plan §44). No existing table
is rebuilt or altered. The relation/history tables are created now so the
schema and the continuity-spec-v2 grammar are frozen before M7C, even
though their behavior lands in M7C/M7D.

Downgrade contract (plan §46 + frozen contract patch §9):
lossless-or-refused, never best-effort. The preflight runs BEFORE any DDL
and refuses when:

  * ANY row exists in ANY M7 table — soft-deleted rows count; data is
    never treated as disposable;
  * any ShotRevision's snapshot_json parses to schema_version >= 3, or any
    continuity_spec_json parses to schema_version >= 2 — decided by
    PARSING the stored JSON, never inferred from child-table presence;
  * any scanned JSON is malformed, lacks an integer schema_version, or is
    structurally inconsistent — failure to prove safety IS refusal.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_narrative_continuity_state"
down_revision: Union[str, None] = "0007_active_narrative_uniqueness"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"

_KINDS = ("'injury', 'surface_condition', 'damage', 'wardrobe_condition', "
          "'configuration', 'status', 'custom'")
_VALUE_TYPES = "'boolean', 'enum', 'integer', 'decimal', 'text'"
_ANCHOR_TYPES = "'sequence', 'scene', 'shot'"
_BOUNDARIES = "'start', 'end'"
_OPERATIONS = "'set', 'clear'"
_RELATION_STATES = "'active', 'inactive'"
_KEY_CHECK = (
    "length(key) BETWEEN 1 AND 64 "
    "AND key GLOB '[a-z]*' AND key NOT GLOB '*[^a-z0-9_]*'"
)

_M7_TABLES = (
    "continuity_features",
    "continuity_feature_transitions",
    "continuity_predicates",
    "continuity_relations",
    "continuity_relation_transitions",
    "shot_revision_feature_states",
    "shot_revision_relation_states",
)


def upgrade() -> None:
    op.create_table(
        "continuity_features",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("value_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enum_values_json", sa.Text(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("supersedes_feature_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_continuity_features"),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["creative_entities.id"],
            name="fk_continuity_features_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_feature_id"], ["continuity_features.id"],
            name="fk_continuity_features_supersedes_feature_id_continuity_features",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "entity_id", "key", name="uq_continuity_features_entity_id_key"
        ),
        sa.CheckConstraint(
            f"kind IN ({_KINDS})", name="ck_continuity_features_kind"
        ),
        sa.CheckConstraint(
            f"value_type IN ({_VALUE_TYPES})",
            name="ck_continuity_features_value_type",
        ),
        sa.CheckConstraint(
            _KEY_CHECK, name="ck_continuity_features_key",
        ),
        sa.CheckConstraint(
            "(value_type = 'enum' AND enum_values_json IS NOT NULL) OR "
            "(value_type <> 'enum' AND enum_values_json IS NULL)",
            name="ck_continuity_features_enum_presence",
        ),
        sa.CheckConstraint(
            "unit IS NULL OR value_type IN ('integer', 'decimal')",
            name="ck_continuity_features_unit_numeric_only",
        ),
        sa.CheckConstraint(
            "unit IS NULL OR (length(unit) BETWEEN 1 AND 64)",
            name="ck_continuity_features_unit_len",
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_continuity_features_name_nonempty",
        ),
    )
    op.create_index(
        "uq_continuity_features_supersedes", "continuity_features",
        ["supersedes_feature_id"], unique=True,
        sqlite_where=sa.text("supersedes_feature_id IS NOT NULL"),
    )
    op.create_index(
        "ix_continuity_features_entity", "continuity_features",
        ["entity_id", "deleted_at", "key"],
    )

    op.create_table(
        "continuity_feature_transitions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("feature_id", sa.String(36), nullable=False),
        sa.Column("anchor_type", sa.Text(), nullable=False),
        sa.Column("anchor_id", sa.String(36), nullable=False),
        sa.Column("boundary", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.Column("value_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "id", name="pk_continuity_feature_transitions"
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["continuity_features.id"],
            name="fk_continuity_feature_transitions_feature_id_continuity_features",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"anchor_type IN ({_ANCHOR_TYPES})",
            name="ck_continuity_feature_transitions_anchor_type",
        ),
        sa.CheckConstraint(
            f"boundary IN ({_BOUNDARIES})",
            name="ck_continuity_feature_transitions_boundary",
        ),
        sa.CheckConstraint(
            f"operation IN ({_OPERATIONS})",
            name="ck_continuity_feature_transitions_operation",
        ),
        sa.CheckConstraint(
            "(operation = 'set' AND value_json IS NOT NULL "
            "AND value_hash IS NOT NULL) OR "
            "(operation = 'clear' AND value_json IS NULL AND value_hash IS NULL)",
            name="ck_continuity_feature_transitions_operation_value",
        ),
        sa.CheckConstraint(
            "value_hash IS NULL OR length(value_hash) = 64",
            name="ck_continuity_feature_transitions_value_hash_len",
        ),
    )
    op.create_index(
        "uq_continuity_feature_transitions_active_coordinate",
        "continuity_feature_transitions",
        ["feature_id", "anchor_type", "anchor_id", "boundary"],
        unique=True, sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_continuity_feature_transitions_feature",
        "continuity_feature_transitions", ["feature_id", "deleted_at"],
    )
    op.create_index(
        "ix_continuity_feature_transitions_anchor",
        "continuity_feature_transitions",
        ["anchor_type", "anchor_id", "deleted_at"],
    )

    op.create_table(
        "continuity_predicates",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_continuity_predicates"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_continuity_predicates_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "project_id", "key",
            name="uq_continuity_predicates_project_id_key",
        ),
        sa.CheckConstraint(
            _KEY_CHECK, name="ck_continuity_predicates_key",
        ),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_continuity_predicates_name_nonempty",
        ),
    )

    op.create_table(
        "continuity_relations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("subject_entity_id", sa.String(36), nullable=False),
        sa.Column("predicate_id", sa.String(36), nullable=False),
        sa.Column("object_entity_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_continuity_relations"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_continuity_relations_project_id_projects",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subject_entity_id"], ["creative_entities.id"],
            name="fk_continuity_relations_subject_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["predicate_id"], ["continuity_predicates.id"],
            name="fk_continuity_relations_predicate_id_continuity_predicates",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["object_entity_id"], ["creative_entities.id"],
            name="fk_continuity_relations_object_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "subject_entity_id <> object_entity_id",
            name="ck_continuity_relations_no_self_relation",
        ),
    )
    op.create_index(
        "uq_continuity_relations_active_identity", "continuity_relations",
        ["project_id", "subject_entity_id", "predicate_id",
         "object_entity_id"],
        unique=True, sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_continuity_relations_subject", "continuity_relations",
        ["project_id", "subject_entity_id", "deleted_at"],
    )
    op.create_index(
        "ix_continuity_relations_object", "continuity_relations",
        ["project_id", "object_entity_id", "deleted_at"],
    )

    op.create_table(
        "continuity_relation_transitions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("relation_id", sa.String(36), nullable=False),
        sa.Column("anchor_type", sa.Text(), nullable=False),
        sa.Column("anchor_id", sa.String(36), nullable=False),
        sa.Column("boundary", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("updated_at", sa.Text(), nullable=False,
                  server_default=sa.text(_NOW)),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint(
            "id", name="pk_continuity_relation_transitions"
        ),
        sa.ForeignKeyConstraint(
            ["relation_id"], ["continuity_relations.id"],
            name="fk_continuity_relation_transitions_relation_id_continuity_relations",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"anchor_type IN ({_ANCHOR_TYPES})",
            name="ck_continuity_relation_transitions_anchor_type",
        ),
        sa.CheckConstraint(
            f"boundary IN ({_BOUNDARIES})",
            name="ck_continuity_relation_transitions_boundary",
        ),
        sa.CheckConstraint(
            f"state IN ({_RELATION_STATES})",
            name="ck_continuity_relation_transitions_state",
        ),
    )
    op.create_index(
        "uq_continuity_relation_transitions_active_coordinate",
        "continuity_relation_transitions",
        ["relation_id", "anchor_type", "anchor_id", "boundary"],
        unique=True, sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_continuity_relation_transitions_relation",
        "continuity_relation_transitions", ["relation_id", "deleted_at"],
    )
    op.create_index(
        "ix_continuity_relation_transitions_anchor",
        "continuity_relation_transitions",
        ["anchor_type", "anchor_id", "deleted_at"],
    )

    op.create_table(
        "shot_revision_feature_states",
        sa.Column("shot_revision_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("feature_id", sa.String(36), nullable=False),
        sa.Column("feature_key", sa.Text(), nullable=False),
        sa.Column("feature_kind", sa.Text(), nullable=False),
        sa.Column("value_type", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("value_json", sa.Text(), nullable=False),
        sa.Column("value_hash", sa.Text(), nullable=False),
        sa.Column("source_transition_id", sa.String(36), nullable=False),
        sa.Column("source_anchor_type", sa.Text(), nullable=False),
        sa.Column("source_anchor_id", sa.String(36), nullable=False),
        sa.Column("source_boundary", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "shot_revision_id", "feature_id",
            name="pk_shot_revision_feature_states",
        ),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_shot_revision_feature_states_shot_revision_id_shot_revisions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["continuity_features.id"],
            name="fk_shot_revision_feature_states_feature_id_continuity_features",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["creative_entities.id"],
            name="fk_shot_revision_feature_states_entity_id_creative_entities",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "length(value_hash) = 64",
            name="ck_shot_revision_feature_states_value_hash_len",
        ),
        sa.CheckConstraint(
            f"source_anchor_type IN ({_ANCHOR_TYPES})",
            name="ck_shot_revision_feature_states_anchor_type",
        ),
        sa.CheckConstraint(
            f"source_boundary IN ({_BOUNDARIES})",
            name="ck_shot_revision_feature_states_boundary",
        ),
    )
    op.create_index(
        "ix_shot_revision_feature_states_feature",
        "shot_revision_feature_states", ["feature_id"],
    )
    op.create_index(
        "ix_shot_revision_feature_states_entity",
        "shot_revision_feature_states", ["entity_id"],
    )

    op.create_table(
        "shot_revision_relation_states",
        sa.Column("shot_revision_id", sa.String(36), nullable=False),
        sa.Column("relation_id", sa.String(36), nullable=False),
        sa.Column("subject_entity_id", sa.String(36), nullable=False),
        sa.Column("predicate_id", sa.String(36), nullable=False),
        sa.Column("predicate_key", sa.Text(), nullable=False),
        sa.Column("object_entity_id", sa.String(36), nullable=False),
        sa.Column("source_transition_id", sa.String(36), nullable=False),
        sa.Column("source_anchor_type", sa.Text(), nullable=False),
        sa.Column("source_anchor_id", sa.String(36), nullable=False),
        sa.Column("source_boundary", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "shot_revision_id", "relation_id",
            name="pk_shot_revision_relation_states",
        ),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_shot_revision_relation_states_shot_revision_id_shot_revisions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["relation_id"], ["continuity_relations.id"],
            name="fk_shot_revision_relation_states_relation_id_continuity_relations",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"source_anchor_type IN ({_ANCHOR_TYPES})",
            name="ck_shot_revision_relation_states_anchor_type",
        ),
        sa.CheckConstraint(
            f"source_boundary IN ({_BOUNDARIES})",
            name="ck_shot_revision_relation_states_boundary",
        ),
    )
    op.create_index(
        "ix_shot_revision_relation_states_relation",
        "shot_revision_relation_states", ["relation_id"],
    )
    op.create_index(
        "ix_shot_revision_relation_states_subject",
        "shot_revision_relation_states", ["subject_entity_id"],
    )
    op.create_index(
        "ix_shot_revision_relation_states_object",
        "shot_revision_relation_states", ["object_entity_id"],
    )


def _preflight_downgrade_safe() -> None:
    """Refuse BEFORE any DDL unless the M7 schema is provably unused (§46)."""
    import json

    bind = op.get_bind()

    for table in _M7_TABLES:
        count = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table}")
        ).scalar_one()
        if count:
            raise RuntimeError(
                f"Cannot downgrade 0008 -> 0007: table {table} contains "
                f"{count} row(s) (soft-deleted rows count; M7 data is not "
                "disposable). No schema was changed."
            )

    rows = bind.execute(
        sa.text(
            "SELECT id, snapshot_json, continuity_spec_json "
            "FROM shot_revisions"
        )
    ).fetchall()
    for row in rows:
        for column, payload, limit in (
            ("snapshot_json", row.snapshot_json, 3),
            ("continuity_spec_json", row.continuity_spec_json, 2),
        ):
            if payload is None:
                continue
            try:
                parsed = json.loads(payload)
            except (ValueError, TypeError) as exc:
                raise RuntimeError(
                    f"Cannot downgrade 0008 -> 0007: shot_revisions."
                    f"{row.id[:8]}… {column} is malformed JSON; safe "
                    "downgrade cannot be proven. No schema was changed."
                ) from exc
            if not isinstance(parsed, dict):
                raise RuntimeError(
                    f"Cannot downgrade 0008 -> 0007: shot_revisions."
                    f"{row.id[:8]}… {column} is not a JSON object; safe "
                    "downgrade cannot be proven. No schema was changed."
                )
            version = parsed.get("schema_version")
            if not isinstance(version, int) or isinstance(version, bool):
                raise RuntimeError(
                    f"Cannot downgrade 0008 -> 0007: shot_revisions."
                    f"{row.id[:8]}… {column} lacks an integer "
                    "schema_version; safe downgrade cannot be proven. "
                    "No schema was changed."
                )
            if version >= limit:
                raise RuntimeError(
                    f"Cannot downgrade 0008 -> 0007: shot_revisions."
                    f"{row.id[:8]}… {column} declares schema_version "
                    f"{version} (>= {limit}); M7 history cannot be "
                    "represented by 0007. No schema was changed."
                )


def downgrade() -> None:
    _preflight_downgrade_safe()
    # Dependency-safe order: children before parents.
    op.drop_index(
        "ix_shot_revision_relation_states_object",
        table_name="shot_revision_relation_states",
    )
    op.drop_index(
        "ix_shot_revision_relation_states_subject",
        table_name="shot_revision_relation_states",
    )
    op.drop_index(
        "ix_shot_revision_relation_states_relation",
        table_name="shot_revision_relation_states",
    )
    op.drop_table("shot_revision_relation_states")
    op.drop_index(
        "ix_shot_revision_feature_states_entity",
        table_name="shot_revision_feature_states",
    )
    op.drop_index(
        "ix_shot_revision_feature_states_feature",
        table_name="shot_revision_feature_states",
    )
    op.drop_table("shot_revision_feature_states")
    op.drop_index(
        "ix_continuity_relation_transitions_anchor",
        table_name="continuity_relation_transitions",
    )
    op.drop_index(
        "ix_continuity_relation_transitions_relation",
        table_name="continuity_relation_transitions",
    )
    op.drop_index(
        "uq_continuity_relation_transitions_active_coordinate",
        table_name="continuity_relation_transitions",
    )
    op.drop_table("continuity_relation_transitions")
    op.drop_index(
        "ix_continuity_relations_object", table_name="continuity_relations"
    )
    op.drop_index(
        "ix_continuity_relations_subject", table_name="continuity_relations"
    )
    op.drop_index(
        "uq_continuity_relations_active_identity",
        table_name="continuity_relations",
    )
    op.drop_table("continuity_relations")
    op.drop_table("continuity_predicates")
    op.drop_index(
        "ix_continuity_feature_transitions_anchor",
        table_name="continuity_feature_transitions",
    )
    op.drop_index(
        "ix_continuity_feature_transitions_feature",
        table_name="continuity_feature_transitions",
    )
    op.drop_index(
        "uq_continuity_feature_transitions_active_coordinate",
        table_name="continuity_feature_transitions",
    )
    op.drop_table("continuity_feature_transitions")
    op.drop_index(
        "ix_continuity_features_entity", table_name="continuity_features"
    )
    op.drop_index(
        "uq_continuity_features_supersedes", table_name="continuity_features"
    )
    op.drop_table("continuity_features")
