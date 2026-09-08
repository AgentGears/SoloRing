"""m13 authority complete world

Revision ID: 0014_m13_authority_complete_world
Revises: 0013_m12_composition_occurrences
Create Date: 2026-09-07

Frozen M13 R3 §5-§6: exactly thirteen additive tables with deterministic
convention-resolved constraint/index names matching ORM metadata exactly.
No predecessor table is rebuilt, widened, or backfilled. No Blob FK is
introduced (recovery's Blob inventory stays seven paths). No adoption,
interpretation, PI state/track, binding, selection, or schema-6 history is
backfilled or invented.

Downgrade (§6.2): fail-closed preflight BEFORE any DDL refuses when any of
the thirteen M13 tables has rows — including bare subject adoptions, bare
interpretations, and never-selected bindings.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_m13_authority_complete_world"
down_revision: Union[str, None] = "0013_m12_composition_occurrences"

_M13_TABLES = (
    "shot_revision_production_instance_spatial_states",
    "shot_revision_production_instance_feature_states",
    "shot_revision_production_worlds",
    "shot_production_world_selections",
    "composition_spatial_binding_entries",
    "composition_spatial_binding_subjects",
    "composition_spatial_bindings",
    "production_instance_spatial_transitions",
    "production_instance_spatial_tracks",
    "production_instance_feature_transitions",
    "production_instance_features",
    "production_revision_spatial_interpretations",
    "composition_occurrence_authority_subjects",
)

_SUBJECT_KIND_CHECK = (
    "(subject_kind = 'creative_entity' AND creative_entity_id IS NOT NULL) "
    "OR (subject_kind = 'production_instance' AND creative_entity_id IS NULL)"
)

_SUBJECT_IDENTITY = (
    "(subject_kind = 'production_instance' "
    "AND creative_entity_id IS NULL AND subject_id = occurrence_id) OR "
    "(subject_kind = 'creative_entity' "
    "AND creative_entity_id IS NOT NULL "
    "AND subject_id = creative_entity_id)"
)

_PLACEMENT_XOR = (
    "(placement_kind = 'entity_fixed_frame' "
    "AND spatial_frame_id IS NOT NULL AND spatial_track_id IS NULL "
    "AND production_instance_track_id IS NULL) OR "
    "(placement_kind = 'entity_track' "
    "AND spatial_frame_id IS NULL AND spatial_track_id IS NOT NULL "
    "AND production_instance_track_id IS NULL) OR "
    "(placement_kind = 'production_instance_track' "
    "AND spatial_frame_id IS NULL AND spatial_track_id IS NULL "
    "AND production_instance_track_id IS NOT NULL)"
)

_M7_KINDS = "'injury', 'surface_condition', 'damage', 'wardrobe_condition', " \
            "'configuration', 'status', 'custom'"
_M7_VALUE_TYPES = "'boolean', 'enum', 'integer', 'decimal', 'text'"
_M7_ANCHOR_TYPES = "'sequence', 'scene', 'shot'"
_M7_BOUNDARIES = "'start', 'end'"
_M7_OPERATIONS = "'set', 'clear'"

_KEY_CHECK = (
    "length(key) BETWEEN 1 AND 64 "
    "AND key GLOB '[a-z]*' AND key NOT GLOB '*[^a-z0-9_]*'"
)


def _preflight_clear(conn) -> None:
    for table in _M13_TABLES:
        n = conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if n:
            raise RuntimeError(
                f"0014 downgrade refused: {table} contains {n} row(s); "
                "authored M13 production-world state is never destroyed"
            )


def upgrade() -> None:
    op.create_table(
        "composition_occurrence_authority_subjects",
        sa.Column("composition_id", sa.String(36), primary_key=True),
        sa.Column("occurrence_id", sa.String(36), primary_key=True),
        sa.Column("subject_kind", sa.Text(), nullable=False),
        sa.Column("creative_entity_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "subject_kind IN ('creative_entity','production_instance')",
            name="subject_kind_domain"),
        sa.CheckConstraint(_SUBJECT_KIND_CHECK, name="subject_kind_entity"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_coas_occurrence", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["creative_entity_id"], ["creative_entities.id"],
            name="fk_coas_creative_entity", ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_coas_active_entity_claim",
        "composition_occurrence_authority_subjects",
        ["composition_id", "creative_entity_id"],
        sqlite_where=sa.text("creative_entity_id IS NOT NULL"))

    op.create_table(
        "production_revision_spatial_interpretations",
        sa.Column("production_revision_id", sa.String(36), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("x_mm", sa.Integer(), nullable=False),
        sa.Column("y_mm", sa.Integer(), nullable=False),
        sa.Column("z_mm", sa.Integer(), nullable=False),
        sa.Column("yaw_udeg", sa.Integer(), nullable=False),
        sa.Column("pitch_udeg", sa.Integer(), nullable=False),
        sa.Column("roll_udeg", sa.Integer(), nullable=False),
        sa.Column("interpretation_json", sa.Text(), nullable=False),
        sa.Column("interpretation_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("schema_version = 1", name="schema_version"),
        sa.CheckConstraint("length(interpretation_hash) = 64", name="hash_len"),
        sa.ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_prsi_production_revision", ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "production_revision_id", "interpretation_hash",
            name="uq_prsi_revision_hash"),
    )

    op.create_table(
        "production_instance_features",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("occurrence_id", sa.String(36), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("value_type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enum_values_json", sa.Text(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=True),
        sa.Column("supersedes_feature_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint(f"kind IN ({_M7_KINDS})", name="kind_domain"),
        sa.CheckConstraint(
            f"value_type IN ({_M7_VALUE_TYPES})", name="value_type"),
        sa.CheckConstraint(_KEY_CHECK, name="key"),
        sa.CheckConstraint("length(trim(name)) > 0", name="name_nonempty"),
        sa.CheckConstraint(
            "(value_type = 'enum' AND enum_values_json IS NOT NULL) OR "
            "(value_type <> 'enum' AND enum_values_json IS NULL)",
            name="enum_presence"),
        sa.CheckConstraint(
            "unit IS NULL OR value_type IN ('integer', 'decimal')",
            name="unit_numeric_only"),
        sa.CheckConstraint(
            "unit IS NULL OR (length(unit) BETWEEN 1 AND 64 "
            "AND unit = trim(unit))",
            name="unit_form"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_pif_occurrence", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supersedes_feature_id"], ["production_instance_features.id"],
            name="fk_pif_supersedes", ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "composition_id", "occurrence_id", "key",
            name="uq_pif_occurrence_key"),
    )
    op.create_index(
        "uq_pif_supersedes", "production_instance_features",
        ["supersedes_feature_id"], unique=True,
        sqlite_where=sa.text("supersedes_feature_id IS NOT NULL"))
    op.create_index(
        "ix_pif_occurrence", "production_instance_features",
        ["composition_id", "occurrence_id", "deleted_at", "key"])

    op.create_table(
        "production_instance_feature_transitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("feature_id", sa.String(36), nullable=False),
        sa.Column("anchor_type", sa.Text(), nullable=False),
        sa.Column("anchor_id", sa.String(36), nullable=False),
        sa.Column("boundary", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.Column("value_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"anchor_type IN ({_M7_ANCHOR_TYPES})", name="anchor_type"),
        sa.CheckConstraint(f"boundary IN ({_M7_BOUNDARIES})", name="boundary"),
        sa.CheckConstraint(
            f"operation IN ({_M7_OPERATIONS})", name="operation"),
        sa.CheckConstraint(
            "(operation = 'set' AND value_json IS NOT NULL "
            "AND value_hash IS NOT NULL) OR "
            "(operation = 'clear' AND value_json IS NULL "
            "AND value_hash IS NULL)",
            name="operation_value"),
        sa.CheckConstraint(
            "value_hash IS NULL OR length(value_hash) = 64",
            name="value_hash_len"),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["production_instance_features.id"],
            name="fk_pift_feature", ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_pift_active_coordinate", "production_instance_feature_transitions",
        ["feature_id", "anchor_type", "anchor_id", "boundary"], unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"))
    op.create_index(
        "ix_pift_feature", "production_instance_feature_transitions",
        ["feature_id", "deleted_at"])
    op.create_index(
        "ix_pift_anchor", "production_instance_feature_transitions",
        ["anchor_type", "anchor_id", "deleted_at"])

    op.create_table(
        "production_instance_spatial_tracks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("spatial_world_id", sa.String(36), nullable=False),
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("occurrence_id", sa.String(36), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "requirement IN ('required','optional')", name="requirement"),
        sa.ForeignKeyConstraint(
            ["spatial_world_id"], ["spatial_worlds.id"],
            name="fk_pist_world", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_pist_occurrence", ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_pist_active_world_occurrence",
        "production_instance_spatial_tracks",
        ["spatial_world_id", "occurrence_id"], unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"))
    op.create_index(
        "ix_pist_world", "production_instance_spatial_tracks",
        ["spatial_world_id", "deleted_at"])
    op.create_index(
        "ix_pist_occurrence", "production_instance_spatial_tracks",
        ["composition_id", "occurrence_id", "deleted_at"])

    op.create_table(
        "production_instance_spatial_transitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("spatial_track_id", sa.String(36), nullable=False),
        sa.Column("anchor_type", sa.Text(), nullable=False),
        sa.Column("anchor_id", sa.String(36), nullable=False),
        sa.Column("boundary", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("x_mm", sa.Integer(), nullable=True),
        sa.Column("y_mm", sa.Integer(), nullable=True),
        sa.Column("z_mm", sa.Integer(), nullable=True),
        sa.Column("yaw_udeg", sa.Integer(), nullable=True),
        sa.Column("pitch_udeg", sa.Integer(), nullable=True),
        sa.Column("roll_udeg", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            f"anchor_type IN ({_M7_ANCHOR_TYPES})", name="anchor_type"),
        sa.CheckConstraint(f"boundary IN ({_M7_BOUNDARIES})", name="boundary"),
        sa.CheckConstraint(
            f"operation IN ({_M7_OPERATIONS})", name="operation"),
        sa.CheckConstraint(
            "(operation = 'set' AND x_mm IS NOT NULL AND y_mm IS NOT NULL "
            "AND z_mm IS NOT NULL AND yaw_udeg IS NOT NULL "
            "AND pitch_udeg IS NOT NULL AND roll_udeg IS NOT NULL) OR "
            "(operation = 'clear' AND x_mm IS NULL AND y_mm IS NULL "
            "AND z_mm IS NULL AND yaw_udeg IS NULL AND pitch_udeg IS NULL "
            "AND roll_udeg IS NULL)",
            name="operation_transforms"),
        sa.ForeignKeyConstraint(
            ["spatial_track_id"], ["production_instance_spatial_tracks.id"],
            name="fk_pistt_track", ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_pistt_active_coordinate",
        "production_instance_spatial_transitions",
        ["spatial_track_id", "anchor_type", "anchor_id", "boundary"],
        unique=True, sqlite_where=sa.text("deleted_at IS NULL"))
    op.create_index(
        "ix_pistt_track", "production_instance_spatial_transitions",
        ["spatial_track_id", "deleted_at"])
    op.create_index(
        "ix_pistt_anchor", "production_instance_spatial_transitions",
        ["anchor_type", "anchor_id", "deleted_at"])

    op.create_table(
        "composition_spatial_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("composition_revision_id", sa.String(36), nullable=False),
        sa.Column("composition_revision_hash", sa.Text(), nullable=False),
        sa.Column("spatial_world_revision_id", sa.String(36), nullable=False),
        sa.Column("spatial_world_revision_hash", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("binding_json", sa.Text(), nullable=False),
        sa.Column("binding_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("schema_version = 1", name="schema_version"),
        sa.CheckConstraint(
            "length(composition_revision_hash) = 64",
            name="composition_hash_len"),
        sa.CheckConstraint(
            "length(spatial_world_revision_hash) = 64",
            name="world_hash_len"),
        sa.CheckConstraint("length(binding_hash) = 64", name="binding_hash_len"),
        sa.ForeignKeyConstraint(
            ["composition_revision_id"], ["composition_revisions.id"],
            name="fk_csb_composition_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["spatial_world_revision_id"], ["spatial_world_revisions.id"],
            name="fk_csb_spatial_world_revision", ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "composition_revision_id", "spatial_world_revision_id",
            "binding_hash", name="uq_csb_revision_pair_hash"),
    )
    op.create_index(
        "ix_csb_composition_revision", "composition_spatial_bindings",
        ["composition_revision_id"])
    op.create_index(
        "ix_csb_world_revision", "composition_spatial_bindings",
        ["spatial_world_revision_id"])

    op.create_table(
        "composition_spatial_binding_subjects",
        sa.Column("binding_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("occurrence_id", sa.String(36), nullable=False),
        sa.Column("production_revision_id", sa.String(36), nullable=False),
        sa.Column("production_revision_hash", sa.Text(), nullable=False),
        sa.Column("subject_kind", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("creative_entity_id", sa.String(36), nullable=True),
        sa.CheckConstraint("position >= 0", name="position_nonneg"),
        sa.CheckConstraint(
            "subject_kind IN ('creative_entity','production_instance')",
            name="subject_kind_domain"),
        sa.CheckConstraint(_SUBJECT_IDENTITY, name="subject_identity"),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["composition_spatial_bindings.id"],
            name="fk_csbs_binding", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_csbs_production_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["creative_entity_id"], ["creative_entities.id"],
            name="fk_csbs_creative_entity", ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "binding_id", "occurrence_id", name="uq_csbs_occurrence"),
        sa.UniqueConstraint(
            "binding_id", "subject_kind", "subject_id", name="uq_csbs_subject"),
    )

    op.create_table(
        "composition_spatial_binding_entries",
        sa.Column("binding_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("occurrence_id", sa.String(36), nullable=False),
        sa.Column("production_revision_id", sa.String(36), nullable=False),
        sa.Column("production_revision_hash", sa.Text(), nullable=False),
        sa.Column("subject_kind", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.String(36), nullable=False),
        sa.Column("creative_entity_id", sa.String(36), nullable=True),
        sa.Column("placement_kind", sa.Text(), nullable=False),
        sa.Column("spatial_frame_id", sa.String(36), nullable=True),
        sa.Column("spatial_track_id", sa.String(36), nullable=True),
        sa.Column("production_instance_track_id", sa.String(36), nullable=True),
        sa.Column("spatial_interpretation_hash", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name="position_nonneg"),
        sa.CheckConstraint(
            "placement_kind IN ('entity_fixed_frame','entity_track',"
            "'production_instance_track')",
            name="placement_kind_domain"),
        sa.CheckConstraint(_PLACEMENT_XOR, name="placement_xor"),
        sa.CheckConstraint(
            "length(spatial_interpretation_hash) = 64",
            name="interpretation_hash_len"),
        sa.CheckConstraint(
            "subject_kind IN ('creative_entity','production_instance')",
            name="subject_kind_domain"),
        sa.CheckConstraint(_SUBJECT_IDENTITY, name="subject_identity"),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["composition_spatial_bindings.id"],
            name="fk_csbe_binding", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["production_revision_id"], ["production_revisions.id"],
            name="fk_csbe_production_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["creative_entity_id"], ["creative_entities.id"],
            name="fk_csbe_creative_entity", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["spatial_frame_id"], ["spatial_frames.id"],
            name="fk_csbe_spatial_frame", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["spatial_track_id"], ["spatial_tracks.id"],
            name="fk_csbe_spatial_track", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["production_instance_track_id"],
            ["production_instance_spatial_tracks.id"],
            name="fk_csbe_pi_track", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["production_revision_id", "spatial_interpretation_hash"],
            ["production_revision_spatial_interpretations.production_revision_id",
             "production_revision_spatial_interpretations.interpretation_hash"],
            name="fk_csbe_interpretation", ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "binding_id", "occurrence_id", name="uq_csbe_occurrence"),
        sa.UniqueConstraint(
            "binding_id", "subject_kind", "subject_id", name="uq_csbe_subject"),
    )

    op.create_table(
        "shot_production_world_selections",
        sa.Column("shot_id", sa.String(36), primary_key=True),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["shot_id"], ["shots.id"],
            name="fk_spws_shot", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["composition_spatial_bindings.id"],
            name="fk_spws_binding", ondelete="RESTRICT"),
    )

    op.create_table(
        "shot_revision_production_worlds",
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("production_world_hash", sa.Text(), nullable=False),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("binding_hash", sa.Text(), nullable=False),
        sa.Column("composition_revision_id", sa.String(36), nullable=False),
        sa.Column("composition_revision_hash", sa.Text(), nullable=False),
        sa.Column("spatial_world_revision_id", sa.String(36), nullable=False),
        sa.Column("spatial_world_revision_hash", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "length(production_world_hash) = 64", name="world_hash_len"),
        sa.CheckConstraint("length(binding_hash) = 64", name="binding_hash_len"),
        sa.CheckConstraint(
            "length(composition_revision_hash) = 64",
            name="composition_hash_len"),
        sa.CheckConstraint(
            "length(spatial_world_revision_hash) = 64",
            name="revision_hash_len"),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpw_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["composition_spatial_bindings.id"],
            name="fk_srpw_binding", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["composition_revision_id"], ["composition_revisions.id"],
            name="fk_srpw_composition_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["spatial_world_revision_id"], ["spatial_world_revisions.id"],
            name="fk_srpw_world_revision", ondelete="RESTRICT"),
    )

    op.create_table(
        "shot_revision_production_instance_feature_states",
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("occurrence_id", sa.String(36), nullable=False),
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
        sa.CheckConstraint("position >= 0", name="position_nonneg"),
        sa.CheckConstraint("length(value_hash) = 64", name="value_hash_len"),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpifs_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_srpifs_occurrence", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["feature_id"], ["production_instance_features.id"],
            name="fk_srpifs_feature", ondelete="RESTRICT"),
    )

    op.create_table(
        "shot_revision_production_instance_spatial_states",
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("composition_id", sa.String(36), nullable=False),
        sa.Column("occurrence_id", sa.String(36), nullable=False),
        sa.Column("production_instance_track_id", sa.String(36),
                  nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("x_mm", sa.Integer(), nullable=False),
        sa.Column("y_mm", sa.Integer(), nullable=False),
        sa.Column("z_mm", sa.Integer(), nullable=False),
        sa.Column("yaw_udeg", sa.Integer(), nullable=False),
        sa.Column("pitch_udeg", sa.Integer(), nullable=False),
        sa.Column("roll_udeg", sa.Integer(), nullable=False),
        sa.Column("source_transition_id", sa.String(36), nullable=False),
        sa.Column("source_anchor_type", sa.Text(), nullable=False),
        sa.Column("source_anchor_id", sa.String(36), nullable=False),
        sa.Column("source_boundary", sa.Text(), nullable=False),
        sa.CheckConstraint("position >= 0", name="position_nonneg"),
        sa.CheckConstraint(
            "requirement IN ('required','optional')", name="requirement"),
        sa.ForeignKeyConstraint(
            ["shot_revision_id"], ["shot_revisions.id"],
            name="fk_srpiss_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["occurrence_id", "composition_id"],
            ["composition_occurrences.id", "composition_occurrences.composition_id"],
            name="fk_srpiss_occurrence", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["production_instance_track_id"],
            ["production_instance_spatial_tracks.id"],
            name="fk_srpiss_track", ondelete="RESTRICT"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    _preflight_clear(conn)
    for table in (
        "shot_revision_production_instance_spatial_states",
        "shot_revision_production_instance_feature_states",
        "shot_revision_production_worlds",
        "shot_production_world_selections",
        "composition_spatial_binding_entries",
        "composition_spatial_binding_subjects",
        "composition_spatial_bindings",
        "production_instance_spatial_transitions",
        "production_instance_spatial_tracks",
        "production_instance_feature_transitions",
        "production_instance_features",
        "production_revision_spatial_interpretations",
        "composition_occurrence_authority_subjects",
    ):
        op.drop_table(table)
