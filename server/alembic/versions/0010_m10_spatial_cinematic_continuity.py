"""m10 spatial cinematic continuity

Revision ID: 0010_m10_spatial_cinematic_continuity
Revises: 0009_m8_visual_identity
Create Date: 2026-08-23

Frozen r3 plan §7: creates ONLY the 15 M10 authority tables/indexes. No
existing table is rebuilt or altered; historical rows remain byte-for-byte
unchanged.

Downgrade contract (§7.4): fail-closed preflight BEFORE any DDL refuses when
any M10 table holds any row (soft-deleted included), any ShotRevision
snapshot is malformed or declares schema >= 5, or any Generation
workflow_spec is malformed or declares workflow-spec schema >= 3. Only a
provably unused M10 schema may be dropped, in reverse dependency order.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_m10_spatial_cinematic_continuity"
down_revision: Union[str, None] = "0009_m8_visual_identity"

M10_TABLES = [
    "shot_revision_spatial_plans",
    "shot_revision_spatial_track_states",
    "shot_revision_spatial_worlds",
    "spatial_world_revision_axes",
    "spatial_world_revision_frames",
    "spatial_world_revisions",
    "shot_spatial_plans",
    "spatial_transitions",
    "spatial_tracks",
    "spatial_world_state_axes",
    "spatial_world_state_frames",
    "spatial_axes",
    "spatial_frames",
    "spatial_world_states",
    "spatial_worlds",
]


def _count(conn, sql: str, what: str) -> int:
    try:
        return conn.execute(sa.text(sql)).scalar()
    except Exception as exc:  # malformed JSON during the scan is itself refusal
        raise RuntimeError(f"M10 downgrade refused: {what} ({exc})") from exc


def _preflight_clear(conn) -> None:
    for table in M10_TABLES:
        n = _count(conn, f"SELECT COUNT(*) FROM {table}",
                   f"table {table} unreadable")
        if n:
            raise RuntimeError(
                f"M10 downgrade refused: table {table} contains {n} row(s); "
                "M10 authority/history is never intentionally destroyed"
            )
    bad_snap = _count(conn,
                      "SELECT COUNT(*) FROM shot_revisions WHERE snapshot_json IS NULL "
                      "OR json_extract(snapshot_json, '$.schema_version') >= 5",
                      "malformed ShotRevision snapshot JSON")
    if bad_snap:
        raise RuntimeError(
            f"M10 downgrade refused: {bad_snap} ShotRevision snapshot(s) "
            "malformed or schema >= 5"
        )
    bad_spec = _count(conn,
                      "SELECT COUNT(*) FROM generations WHERE workflow_spec_json IS NULL "
                      "OR json_extract(workflow_spec_json, '$.schema_version') >= 3",
                      "malformed workflow-spec JSON")
    if bad_spec:
        raise RuntimeError(
            f"M10 downgrade refused: {bad_spec} workflow_spec(s) malformed "
            "or schema >= 3"
        )


def upgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        "spatial_worlds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("location_entity_id", sa.String(36), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint("requirement IN ('required','optional')",
                           name="ck_spatial_worlds_requirement"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name="fk_spatial_worlds_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_entity_id"], ["creative_entities.id"],
                                name="fk_spatial_worlds_location", ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "key", name="uq_spatial_worlds_project_key"),
    )
    op.execute("CREATE UNIQUE INDEX uq_spatial_worlds_active_location "
               "ON spatial_worlds (location_entity_id) WHERE deleted_at IS NULL")
    op.create_index("ix_spatial_worlds_project", "spatial_worlds", ["project_id", "deleted_at"])
    op.create_index("ix_spatial_worlds_location", "spatial_worlds", ["location_entity_id", "deleted_at"])

    op.create_table(
        "spatial_world_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("spatial_world_id", sa.String(36), nullable=False),
        sa.Column("location_entity_revision_id", sa.String(36), nullable=False),
        sa.Column("approved_revision_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"],
                                name="fk_sws_world", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_entity_revision_id"], ["entity_revisions.id"],
                                name="fk_sws_location_rev", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_revision_id"], ["spatial_world_revisions.id"],
                                name="fk_sws_approved_rev", ondelete="RESTRICT"),
        sa.UniqueConstraint("spatial_world_id", "location_entity_revision_id",
                            name="uq_sws_world_location_rev"),
    )
    op.create_index("ix_sws_world", "spatial_world_states", ["spatial_world_id"])
    op.create_index("ix_sws_approved", "spatial_world_states", ["approved_revision_id"])

    op.create_table(
        "spatial_frames",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("spatial_world_id", sa.String(36), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_spatial_frame_id", sa.String(36), nullable=True),
        sa.Column("bound_entity_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"],
                                name="fk_sf_world", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_spatial_frame_id"], ["spatial_frames.id"],
                                name="fk_sf_parent", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bound_entity_id"], ["creative_entities.id"],
                                name="fk_sf_bound_entity", ondelete="RESTRICT"),
        sa.UniqueConstraint("spatial_world_id", "key", name="uq_sf_world_key"),
    )
    op.create_index("ix_sf_world", "spatial_frames", ["spatial_world_id", "deleted_at"])
    op.create_index("ix_sf_bound_entity", "spatial_frames", ["bound_entity_id"])

    op.create_table(
        "spatial_world_state_frames",
        sa.Column("spatial_world_state_id", sa.String(36), primary_key=True),
        sa.Column("spatial_frame_id", sa.String(36), primary_key=True),
        sa.Column("bound_entity_id", sa.String(36), nullable=True),
        sa.Column("bound_entity_revision_id", sa.String(36), nullable=True),
        sa.Column("x_mm", sa.Integer(), nullable=False),
        sa.Column("y_mm", sa.Integer(), nullable=False),
        sa.Column("z_mm", sa.Integer(), nullable=False),
        sa.Column("yaw_udeg", sa.Integer(), nullable=False),
        sa.Column("pitch_udeg", sa.Integer(), nullable=False),
        sa.Column("roll_udeg", sa.Integer(), nullable=False),
        sa.Column("half_x_mm", sa.Integer(), nullable=True),
        sa.Column("half_y_mm", sa.Integer(), nullable=True),
        sa.Column("half_z_mm", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "(bound_entity_id IS NULL AND bound_entity_revision_id IS NULL) OR "
            "(bound_entity_id IS NOT NULL AND bound_entity_revision_id IS NOT NULL)",
            name="ck_swsf_binding"),
        sa.CheckConstraint(
            "(half_x_mm IS NULL AND half_y_mm IS NULL AND half_z_mm IS NULL) OR "
            "(half_x_mm > 0 AND half_y_mm > 0 AND half_z_mm > 0)",
            name="ck_swsf_extents"),
        sa.ForeignKeyConstraint(["spatial_world_state_id"], ["spatial_world_states.id"],
                                name="fk_swsf_state", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spatial_frame_id"], ["spatial_frames.id"],
                                name="fk_swsf_frame", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bound_entity_id"], ["creative_entities.id"],
                                name="fk_swsf_bound_entity", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bound_entity_revision_id"], ["entity_revisions.id"],
                                name="fk_swsf_bound_rev", ondelete="RESTRICT"),
    )
    op.execute("CREATE UNIQUE INDEX uq_swsf_one_bound_entity "
               "ON spatial_world_state_frames (spatial_world_state_id, bound_entity_id) "
               "WHERE bound_entity_id IS NOT NULL")

    op.create_table(
        "spatial_axes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("spatial_world_id", sa.String(36), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"],
                                name="fk_sa_world", ondelete="RESTRICT"),
        sa.UniqueConstraint("spatial_world_id", "key", name="uq_sa_world_key"),
    )
    op.create_index("ix_sa_world", "spatial_axes", ["spatial_world_id", "deleted_at"])

    op.create_table(
        "spatial_world_state_axes",
        sa.Column("spatial_world_state_id", sa.String(36), primary_key=True),
        sa.Column("spatial_axis_id", sa.String(36), primary_key=True),
        sa.Column("a_frame_id", sa.String(36), nullable=False),
        sa.Column("b_frame_id", sa.String(36), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("a_frame_id <> b_frame_id", name="ck_swsa_endpoints_differ"),
        sa.ForeignKeyConstraint(["spatial_world_state_id"], ["spatial_world_states.id"],
                                name="fk_swsa_state", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spatial_axis_id"], ["spatial_axes.id"],
                                name="fk_swsa_axis", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["spatial_world_state_id", "a_frame_id"],
            ["spatial_world_state_frames.spatial_world_state_id",
             "spatial_world_state_frames.spatial_frame_id"],
            name="fk_swsa_a_endpoint", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["spatial_world_state_id", "b_frame_id"],
            ["spatial_world_state_frames.spatial_world_state_id",
             "spatial_world_state_frames.spatial_frame_id"],
            name="fk_swsa_b_endpoint", ondelete="RESTRICT"),
    )

    op.create_table(
        "spatial_world_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("spatial_world_state_id", sa.String(36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("revision_number > 0", name="ck_swr_number_pos"),
        sa.CheckConstraint("length(snapshot_hash) = 64", name="ck_swr_hash_len"),
        sa.ForeignKeyConstraint(["spatial_world_state_id"], ["spatial_world_states.id"],
                                name="fk_swr_state", ondelete="RESTRICT"),
        sa.UniqueConstraint("spatial_world_state_id", "revision_number",
                            name="uq_swr_state_number"),
        sa.UniqueConstraint("spatial_world_state_id", "snapshot_hash",
                            name="uq_swr_state_hash"),
    )
    op.create_index("ix_swr_state", "spatial_world_revisions", ["spatial_world_state_id"])

    op.create_table(
        "spatial_world_revision_frames",
        sa.Column("spatial_world_revision_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("spatial_frame_id", sa.String(36), nullable=False),
        sa.Column("frame_key", sa.Text(), nullable=False),
        sa.Column("parent_spatial_frame_id", sa.String(36), nullable=True),
        sa.Column("bound_entity_id", sa.String(36), nullable=True),
        sa.Column("bound_entity_revision_id", sa.String(36), nullable=True),
        sa.Column("x_mm", sa.Integer(), nullable=False),
        sa.Column("y_mm", sa.Integer(), nullable=False),
        sa.Column("z_mm", sa.Integer(), nullable=False),
        sa.Column("yaw_udeg", sa.Integer(), nullable=False),
        sa.Column("pitch_udeg", sa.Integer(), nullable=False),
        sa.Column("roll_udeg", sa.Integer(), nullable=False),
        sa.Column("half_x_mm", sa.Integer(), nullable=True),
        sa.Column("half_y_mm", sa.Integer(), nullable=True),
        sa.Column("half_z_mm", sa.Integer(), nullable=True),
        sa.CheckConstraint("position >= 0", name="ck_swrf_position"),
        sa.CheckConstraint(
            "(half_x_mm IS NULL AND half_y_mm IS NULL AND half_z_mm IS NULL) OR "
            "(half_x_mm > 0 AND half_y_mm > 0 AND half_z_mm > 0)",
            name="ck_swrf_extents"),
        sa.ForeignKeyConstraint(["spatial_world_revision_id"], ["spatial_world_revisions.id"],
                                name="fk_swrf_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spatial_frame_id"], ["spatial_frames.id"],
                                name="fk_swrf_frame", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_spatial_frame_id"], ["spatial_frames.id"],
                                name="fk_swrf_parent", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bound_entity_id"], ["creative_entities.id"],
                                name="fk_swrf_bound_entity", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["bound_entity_revision_id"], ["entity_revisions.id"],
                                name="fk_swrf_bound_rev", ondelete="RESTRICT"),
        sa.UniqueConstraint("spatial_world_revision_id", "spatial_frame_id",
                            name="uq_swrf_revision_frame"),
        sa.UniqueConstraint("spatial_world_revision_id", "frame_key",
                            name="uq_swrf_revision_key"),
    )

    op.create_table(
        "spatial_world_revision_axes",
        sa.Column("spatial_world_revision_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("spatial_axis_id", sa.String(36), nullable=False),
        sa.Column("axis_key", sa.Text(), nullable=False),
        sa.Column("a_frame_id", sa.String(36), nullable=False),
        sa.Column("b_frame_id", sa.String(36), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_swra_position"),
        sa.CheckConstraint("a_frame_id <> b_frame_id", name="ck_swra_endpoints_differ"),
        sa.ForeignKeyConstraint(["spatial_world_revision_id"], ["spatial_world_revisions.id"],
                                name="fk_swra_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spatial_axis_id"], ["spatial_axes.id"],
                                name="fk_swra_axis", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["spatial_world_revision_id", "a_frame_id"],
            ["spatial_world_revision_frames.spatial_world_revision_id",
             "spatial_world_revision_frames.spatial_frame_id"],
            name="fk_swra_a_endpoint", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["spatial_world_revision_id", "b_frame_id"],
            ["spatial_world_revision_frames.spatial_world_revision_id",
             "spatial_world_revision_frames.spatial_frame_id"],
            name="fk_swra_b_endpoint", ondelete="RESTRICT"),
        sa.UniqueConstraint("spatial_world_revision_id", "spatial_axis_id",
                            name="uq_swra_revision_axis"),
        sa.UniqueConstraint("spatial_world_revision_id", "axis_key",
                            name="uq_swra_revision_key"),
    )

    op.create_table(
        "spatial_tracks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("spatial_world_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint("requirement IN ('required','optional')",
                           name="ck_spatial_tracks_requirement"),
        sa.ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"],
                                name="fk_st_world", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["creative_entities.id"],
                                name="fk_st_entity", ondelete="RESTRICT"),
    )
    op.execute("CREATE UNIQUE INDEX uq_st_active_world_entity "
               "ON spatial_tracks (spatial_world_id, entity_id) WHERE deleted_at IS NULL")
    op.create_index("ix_st_world", "spatial_tracks", ["spatial_world_id", "deleted_at"])
    op.create_index("ix_st_entity", "spatial_tracks", ["entity_id", "deleted_at"])

    op.create_table(
        "spatial_transitions",
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
        sa.CheckConstraint("anchor_type IN ('sequence','scene','shot')",
                           name="ck_str_anchor_type"),
        sa.CheckConstraint("boundary IN ('start','end')", name="ck_str_boundary"),
        sa.CheckConstraint("operation IN ('set','clear')", name="ck_str_operation"),
        sa.CheckConstraint(
            "(operation = 'set' AND x_mm IS NOT NULL AND y_mm IS NOT NULL AND z_mm IS NOT NULL "
            "AND yaw_udeg IS NOT NULL AND pitch_udeg IS NOT NULL AND roll_udeg IS NOT NULL) OR "
            "(operation = 'clear' AND x_mm IS NULL AND y_mm IS NULL AND z_mm IS NULL "
            "AND yaw_udeg IS NULL AND pitch_udeg IS NULL AND roll_udeg IS NULL)",
            name="ck_str_operation_transforms"),
        sa.ForeignKeyConstraint(["spatial_track_id"], ["spatial_tracks.id"],
                                name="fk_str_track", ondelete="RESTRICT"),
    )
    op.execute("CREATE UNIQUE INDEX uq_str_active_coordinate "
               "ON spatial_transitions (spatial_track_id, anchor_type, anchor_id, boundary) "
               "WHERE deleted_at IS NULL")
    op.create_index("ix_str_track", "spatial_transitions", ["spatial_track_id", "deleted_at"])
    op.create_index("ix_str_anchor", "spatial_transitions",
                    ["anchor_type", "anchor_id", "boundary", "deleted_at"])

    op.create_table(
        "shot_spatial_plans",
        sa.Column("shot_id", sa.String(36), primary_key=True),
        sa.Column("spatial_world_id", sa.String(36), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("plan_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.CheckConstraint("length(plan_hash) = 64", name="ck_ssp_hash_len"),
        sa.ForeignKeyConstraint(["shot_id"], ["shots.id"],
                                name="fk_ssp_shot", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"],
                                name="fk_ssp_world", ondelete="RESTRICT"),
    )
    op.create_index("ix_ssp_world", "shot_spatial_plans", ["spatial_world_id"])

    op.create_table(
        "shot_revision_spatial_worlds",
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("spatial_continuity_hash", sa.Text(), nullable=False),
        sa.Column("spatial_world_id", sa.String(36), nullable=False),
        sa.Column("spatial_world_state_id", sa.String(36), nullable=False),
        sa.Column("spatial_world_revision_id", sa.String(36), nullable=False),
        sa.Column("spatial_world_revision_hash", sa.Text(), nullable=False),
        sa.Column("location_entity_id", sa.String(36), nullable=False),
        sa.Column("location_entity_revision_id", sa.String(36), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.CheckConstraint("length(spatial_continuity_hash) = 64",
                           name="ck_srsw_continuity_hash_len"),
        sa.CheckConstraint("length(spatial_world_revision_hash) = 64",
                           name="ck_srsw_revision_hash_len"),
        sa.CheckConstraint("requirement IN ('required','optional')",
                           name="ck_srsw_requirement"),
        sa.ForeignKeyConstraint(["shot_revision_id"], ["shot_revisions.id"],
                                name="fk_srsw_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"],
                                name="fk_srsw_world", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spatial_world_state_id"], ["spatial_world_states.id"],
                                name="fk_srsw_state", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spatial_world_revision_id"], ["spatial_world_revisions.id"],
                                name="fk_srsw_world_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_entity_id"], ["creative_entities.id"],
                                name="fk_srsw_location", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_entity_revision_id"], ["entity_revisions.id"],
                                name="fk_srsw_location_rev", ondelete="RESTRICT"),
    )

    op.create_table(
        "shot_revision_spatial_track_states",
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("spatial_track_id", sa.String(36), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("entity_revision_id", sa.String(36), nullable=False),
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
        sa.CheckConstraint("position >= 0", name="ck_srsts_position"),
        sa.CheckConstraint("requirement IN ('required','optional')",
                           name="ck_srsts_requirement"),
        sa.CheckConstraint("source_anchor_type IN ('sequence','scene','shot')",
                           name="ck_srsts_anchor_type"),
        sa.CheckConstraint("source_boundary IN ('start','end')",
                           name="ck_srsts_boundary"),
        sa.ForeignKeyConstraint(["shot_revision_id"], ["shot_revisions.id"],
                                name="fk_srsts_revision", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["spatial_track_id"], ["spatial_tracks.id"],
                                name="fk_srsts_track", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["creative_entities.id"],
                                name="fk_srsts_entity", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_revision_id"], ["entity_revisions.id"],
                                name="fk_srsts_entity_rev", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_transition_id"], ["spatial_transitions.id"],
                                name="fk_srsts_source_transition", ondelete="RESTRICT"),
        sa.UniqueConstraint("shot_revision_id", "spatial_track_id",
                            name="uq_srsts_revision_track"),
    )

    op.create_table(
        "shot_revision_spatial_plans",
        sa.Column("shot_revision_id", sa.String(36), primary_key=True),
        sa.Column("plan_hash", sa.Text(), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.CheckConstraint("length(plan_hash) = 64", name="ck_srsp_hash_len"),
        sa.ForeignKeyConstraint(["shot_revision_id"], ["shot_revisions.id"],
                                name="fk_srsp_revision", ondelete="RESTRICT"),
    )

    # composite-FK parity proof hook point (§7.3): the swsa/swra endpoint FKs
    # above target the declared composite keys, not table PKs.


def downgrade() -> None:
    conn = op.get_bind()
    _preflight_clear(conn)
    for table in M10_TABLES:
        op.drop_table(table)
    # partial indexes are dropped with their tables by SQLite/alembic; the
    # CREATE INDEX statements above were table-scoped by name.
