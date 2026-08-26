"""ORM models for M10 spatial authority and derived execution provenance.

The hand-written 0010/0011 migrations are the storage contract. This module
mirrors those tables exactly so Base.metadata/create_all and Alembic-upgraded
schema stay mechanically comparable. Relationships are intentionally omitted:
M10 services perform explicit, fenced reads/writes and no ORM cascade may gain
creative-authority semantics accidentally.
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

UUID = String(36)


class SpatialWorld(Base):
    __tablename__ = "spatial_worlds"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_spatial_worlds"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_spatial_worlds_project", ondelete="RESTRICT"),
        ForeignKeyConstraint(["location_entity_id"], ["creative_entities.id"], name="fk_spatial_worlds_location", ondelete="RESTRICT"),
        UniqueConstraint("project_id", "key", name="uq_spatial_worlds_project_key"),
        CheckConstraint("requirement IN ('required','optional')", name="ck_spatial_worlds_requirement"),
        Index("uq_spatial_worlds_active_location", "location_entity_id", unique=True, sqlite_where=text("deleted_at IS NULL")),
        Index("ix_spatial_worlds_project", "project_id", "deleted_at"),
        Index("ix_spatial_worlds_location", "location_entity_id", "deleted_at"),
    )
    id: Mapped[str] = mapped_column(UUID)
    project_id: Mapped[str] = mapped_column(UUID, nullable=False)
    location_entity_id: Mapped[str] = mapped_column(UUID, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(Text)


class SpatialWorldState(Base):
    __tablename__ = "spatial_world_states"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_spatial_world_states"),
        ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"], name="fk_sws_world", ondelete="RESTRICT"),
        ForeignKeyConstraint(["location_entity_revision_id"], ["entity_revisions.id"], name="fk_sws_location_rev", ondelete="RESTRICT"),
        ForeignKeyConstraint(["approved_revision_id"], ["spatial_world_revisions.id"], name="fk_sws_approved_rev", ondelete="RESTRICT"),
        UniqueConstraint("spatial_world_id", "location_entity_revision_id", name="uq_sws_world_location_rev"),
        Index("ix_sws_world", "spatial_world_id"),
        Index("ix_sws_approved", "approved_revision_id"),
    )
    id: Mapped[str] = mapped_column(UUID)
    spatial_world_id: Mapped[str] = mapped_column(UUID, nullable=False)
    location_entity_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    approved_revision_id: Mapped[str | None] = mapped_column(UUID)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class SpatialFrame(Base):
    __tablename__ = "spatial_frames"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_spatial_frames"),
        ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"], name="fk_sf_world", ondelete="RESTRICT"),
        ForeignKeyConstraint(["parent_spatial_frame_id"], ["spatial_frames.id"], name="fk_sf_parent", ondelete="RESTRICT"),
        ForeignKeyConstraint(["bound_entity_id"], ["creative_entities.id"], name="fk_sf_bound_entity", ondelete="RESTRICT"),
        UniqueConstraint("spatial_world_id", "key", name="uq_sf_world_key"),
        Index("ix_sf_world", "spatial_world_id", "deleted_at"),
        Index("ix_sf_bound_entity", "bound_entity_id"),
    )
    id: Mapped[str] = mapped_column(UUID)
    spatial_world_id: Mapped[str] = mapped_column(UUID, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_spatial_frame_id: Mapped[str | None] = mapped_column(UUID)
    bound_entity_id: Mapped[str | None] = mapped_column(UUID)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(Text)


class SpatialWorldStateFrame(Base):
    __tablename__ = "spatial_world_state_frames"
    __table_args__ = (
        PrimaryKeyConstraint("spatial_world_state_id", "spatial_frame_id", name="pk_spatial_world_state_frames"),
        ForeignKeyConstraint(["spatial_world_state_id"], ["spatial_world_states.id"], name="fk_swsf_state", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_frame_id"], ["spatial_frames.id"], name="fk_swsf_frame", ondelete="RESTRICT"),
        ForeignKeyConstraint(["bound_entity_id"], ["creative_entities.id"], name="fk_swsf_bound_entity", ondelete="RESTRICT"),
        ForeignKeyConstraint(["bound_entity_revision_id"], ["entity_revisions.id"], name="fk_swsf_bound_rev", ondelete="RESTRICT"),
        CheckConstraint("(bound_entity_id IS NULL AND bound_entity_revision_id IS NULL) OR (bound_entity_id IS NOT NULL AND bound_entity_revision_id IS NOT NULL)", name="ck_swsf_binding"),
        CheckConstraint("(half_x_mm IS NULL AND half_y_mm IS NULL AND half_z_mm IS NULL) OR (half_x_mm > 0 AND half_y_mm > 0 AND half_z_mm > 0)", name="ck_swsf_extents"),
        Index("uq_swsf_one_bound_entity", "spatial_world_state_id", "bound_entity_id", unique=True, sqlite_where=text("bound_entity_id IS NOT NULL")),
    )
    spatial_world_state_id: Mapped[str] = mapped_column(UUID, nullable=False)
    spatial_frame_id: Mapped[str] = mapped_column(UUID, nullable=False)
    bound_entity_id: Mapped[str | None] = mapped_column(UUID)
    bound_entity_revision_id: Mapped[str | None] = mapped_column(UUID)
    x_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    y_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    z_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    yaw_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    pitch_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    roll_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    half_x_mm: Mapped[int | None] = mapped_column(Integer)
    half_y_mm: Mapped[int | None] = mapped_column(Integer)
    half_z_mm: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class SpatialAxis(Base):
    __tablename__ = "spatial_axes"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_spatial_axes"),
        ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"], name="fk_sa_world", ondelete="RESTRICT"),
        UniqueConstraint("spatial_world_id", "key", name="uq_sa_world_key"),
        Index("ix_sa_world", "spatial_world_id", "deleted_at"),
    )
    id: Mapped[str] = mapped_column(UUID)
    spatial_world_id: Mapped[str] = mapped_column(UUID, nullable=False)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(Text)


class SpatialWorldStateAxis(Base):
    __tablename__ = "spatial_world_state_axes"
    __table_args__ = (
        PrimaryKeyConstraint("spatial_world_state_id", "spatial_axis_id", name="pk_spatial_world_state_axes"),
        ForeignKeyConstraint(["spatial_world_state_id"], ["spatial_world_states.id"], name="fk_swsa_state", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_axis_id"], ["spatial_axes.id"], name="fk_swsa_axis", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_world_state_id", "a_frame_id"], ["spatial_world_state_frames.spatial_world_state_id", "spatial_world_state_frames.spatial_frame_id"], name="fk_swsa_a_endpoint", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_world_state_id", "b_frame_id"], ["spatial_world_state_frames.spatial_world_state_id", "spatial_world_state_frames.spatial_frame_id"], name="fk_swsa_b_endpoint", ondelete="RESTRICT"),
        CheckConstraint("a_frame_id <> b_frame_id", name="ck_swsa_endpoints_differ"),
    )
    spatial_world_state_id: Mapped[str] = mapped_column(UUID, nullable=False)
    spatial_axis_id: Mapped[str] = mapped_column(UUID, nullable=False)
    a_frame_id: Mapped[str] = mapped_column(UUID, nullable=False)
    b_frame_id: Mapped[str] = mapped_column(UUID, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class SpatialWorldRevision(Base):
    __tablename__ = "spatial_world_revisions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_spatial_world_revisions"),
        ForeignKeyConstraint(["spatial_world_state_id"], ["spatial_world_states.id"], name="fk_swr_state", ondelete="RESTRICT"),
        UniqueConstraint("spatial_world_state_id", "revision_number", name="uq_swr_state_number"),
        UniqueConstraint("spatial_world_state_id", "snapshot_hash", name="uq_swr_state_hash"),
        CheckConstraint("revision_number > 0", name="ck_swr_number_pos"),
        CheckConstraint("length(snapshot_hash) = 64", name="ck_swr_hash_len"),
        Index("ix_swr_state", "spatial_world_state_id"),
    )
    id: Mapped[str] = mapped_column(UUID)
    spatial_world_state_id: Mapped[str] = mapped_column(UUID, nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class SpatialWorldRevisionFrame(Base):
    __tablename__ = "spatial_world_revision_frames"
    __table_args__ = (
        PrimaryKeyConstraint("spatial_world_revision_id", "position", name="pk_spatial_world_revision_frames"),
        ForeignKeyConstraint(["spatial_world_revision_id"], ["spatial_world_revisions.id"], name="fk_swrf_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_frame_id"], ["spatial_frames.id"], name="fk_swrf_frame", ondelete="RESTRICT"),
        ForeignKeyConstraint(["parent_spatial_frame_id"], ["spatial_frames.id"], name="fk_swrf_parent", ondelete="RESTRICT"),
        ForeignKeyConstraint(["bound_entity_id"], ["creative_entities.id"], name="fk_swrf_bound_entity", ondelete="RESTRICT"),
        ForeignKeyConstraint(["bound_entity_revision_id"], ["entity_revisions.id"], name="fk_swrf_bound_rev", ondelete="RESTRICT"),
        UniqueConstraint("spatial_world_revision_id", "spatial_frame_id", name="uq_swrf_revision_frame"),
        UniqueConstraint("spatial_world_revision_id", "frame_key", name="uq_swrf_revision_key"),
        CheckConstraint("position >= 0", name="ck_swrf_position"),
        CheckConstraint("(half_x_mm IS NULL AND half_y_mm IS NULL AND half_z_mm IS NULL) OR (half_x_mm > 0 AND half_y_mm > 0 AND half_z_mm > 0)", name="ck_swrf_extents"),
    )
    spatial_world_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    spatial_frame_id: Mapped[str] = mapped_column(UUID, nullable=False)
    frame_key: Mapped[str] = mapped_column(Text, nullable=False)
    parent_spatial_frame_id: Mapped[str | None] = mapped_column(UUID)
    bound_entity_id: Mapped[str | None] = mapped_column(UUID)
    bound_entity_revision_id: Mapped[str | None] = mapped_column(UUID)
    x_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    y_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    z_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    yaw_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    pitch_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    roll_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    half_x_mm: Mapped[int | None] = mapped_column(Integer)
    half_y_mm: Mapped[int | None] = mapped_column(Integer)
    half_z_mm: Mapped[int | None] = mapped_column(Integer)


class SpatialWorldRevisionAxis(Base):
    __tablename__ = "spatial_world_revision_axes"
    __table_args__ = (
        PrimaryKeyConstraint("spatial_world_revision_id", "position", name="pk_spatial_world_revision_axes"),
        ForeignKeyConstraint(["spatial_world_revision_id"], ["spatial_world_revisions.id"], name="fk_swra_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_axis_id"], ["spatial_axes.id"], name="fk_swra_axis", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_world_revision_id", "a_frame_id"], ["spatial_world_revision_frames.spatial_world_revision_id", "spatial_world_revision_frames.spatial_frame_id"], name="fk_swra_a_endpoint", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_world_revision_id", "b_frame_id"], ["spatial_world_revision_frames.spatial_world_revision_id", "spatial_world_revision_frames.spatial_frame_id"], name="fk_swra_b_endpoint", ondelete="RESTRICT"),
        UniqueConstraint("spatial_world_revision_id", "spatial_axis_id", name="uq_swra_revision_axis"),
        UniqueConstraint("spatial_world_revision_id", "axis_key", name="uq_swra_revision_key"),
        CheckConstraint("position >= 0", name="ck_swra_position"),
        CheckConstraint("a_frame_id <> b_frame_id", name="ck_swra_endpoints_differ"),
    )
    spatial_world_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    spatial_axis_id: Mapped[str] = mapped_column(UUID, nullable=False)
    axis_key: Mapped[str] = mapped_column(Text, nullable=False)
    a_frame_id: Mapped[str] = mapped_column(UUID, nullable=False)
    b_frame_id: Mapped[str] = mapped_column(UUID, nullable=False)


class SpatialTrack(Base):
    __tablename__ = "spatial_tracks"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_spatial_tracks"),
        ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"], name="fk_st_world", ondelete="RESTRICT"),
        ForeignKeyConstraint(["entity_id"], ["creative_entities.id"], name="fk_st_entity", ondelete="RESTRICT"),
        CheckConstraint("requirement IN ('required','optional')", name="ck_spatial_tracks_requirement"),
        Index("uq_st_active_world_entity", "spatial_world_id", "entity_id", unique=True, sqlite_where=text("deleted_at IS NULL")),
        Index("ix_st_world", "spatial_world_id", "deleted_at"),
        Index("ix_st_entity", "entity_id", "deleted_at"),
    )
    id: Mapped[str] = mapped_column(UUID)
    spatial_world_id: Mapped[str] = mapped_column(UUID, nullable=False)
    entity_id: Mapped[str] = mapped_column(UUID, nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(Text)


class SpatialTransition(Base):
    __tablename__ = "spatial_transitions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_spatial_transitions"),
        ForeignKeyConstraint(["spatial_track_id"], ["spatial_tracks.id"], name="fk_str_track", ondelete="RESTRICT"),
        CheckConstraint("anchor_type IN ('sequence','scene','shot')", name="ck_str_anchor_type"),
        CheckConstraint("boundary IN ('start','end')", name="ck_str_boundary"),
        CheckConstraint("operation IN ('set','clear')", name="ck_str_operation"),
        CheckConstraint("(operation = 'set' AND x_mm IS NOT NULL AND y_mm IS NOT NULL AND z_mm IS NOT NULL AND yaw_udeg IS NOT NULL AND pitch_udeg IS NOT NULL AND roll_udeg IS NOT NULL) OR (operation = 'clear' AND x_mm IS NULL AND y_mm IS NULL AND z_mm IS NULL AND yaw_udeg IS NULL AND pitch_udeg IS NULL AND roll_udeg IS NULL)", name="ck_str_operation_transforms"),
        Index("uq_str_active_coordinate", "spatial_track_id", "anchor_type", "anchor_id", "boundary", unique=True, sqlite_where=text("deleted_at IS NULL")),
        Index("ix_str_track", "spatial_track_id", "deleted_at"),
        Index("ix_str_anchor", "anchor_type", "anchor_id", "boundary", "deleted_at"),
    )
    id: Mapped[str] = mapped_column(UUID)
    spatial_track_id: Mapped[str] = mapped_column(UUID, nullable=False)
    anchor_type: Mapped[str] = mapped_column(Text, nullable=False)
    anchor_id: Mapped[str] = mapped_column(UUID, nullable=False)
    boundary: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    x_mm: Mapped[int | None] = mapped_column(Integer)
    y_mm: Mapped[int | None] = mapped_column(Integer)
    z_mm: Mapped[int | None] = mapped_column(Integer)
    yaw_udeg: Mapped[int | None] = mapped_column(Integer)
    pitch_udeg: Mapped[int | None] = mapped_column(Integer)
    roll_udeg: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(Text)


class ShotSpatialPlan(Base):
    __tablename__ = "shot_spatial_plans"
    __table_args__ = (
        PrimaryKeyConstraint("shot_id", name="pk_shot_spatial_plans"),
        ForeignKeyConstraint(["shot_id"], ["shots.id"], name="fk_ssp_shot", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"], name="fk_ssp_world", ondelete="RESTRICT"),
        CheckConstraint("length(plan_hash) = 64", name="ck_ssp_hash_len"),
        Index("ix_ssp_world", "spatial_world_id"),
    )
    shot_id: Mapped[str] = mapped_column(UUID, nullable=False)
    spatial_world_id: Mapped[str] = mapped_column(UUID, nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    plan_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)


class ShotRevisionSpatialWorld(Base):
    __tablename__ = "shot_revision_spatial_worlds"
    __table_args__ = (
        PrimaryKeyConstraint("shot_revision_id", name="pk_shot_revision_spatial_worlds"),
        ForeignKeyConstraint(["shot_revision_id"], ["shot_revisions.id"], name="fk_srsw_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_world_id"], ["spatial_worlds.id"], name="fk_srsw_world", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_world_state_id"], ["spatial_world_states.id"], name="fk_srsw_state", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_world_revision_id"], ["spatial_world_revisions.id"], name="fk_srsw_world_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(["location_entity_id"], ["creative_entities.id"], name="fk_srsw_location", ondelete="RESTRICT"),
        ForeignKeyConstraint(["location_entity_revision_id"], ["entity_revisions.id"], name="fk_srsw_location_rev", ondelete="RESTRICT"),
        CheckConstraint("length(spatial_continuity_hash) = 64", name="ck_srsw_continuity_hash_len"),
        CheckConstraint("length(spatial_world_revision_hash) = 64", name="ck_srsw_revision_hash_len"),
        CheckConstraint("requirement IN ('required','optional')", name="ck_srsw_requirement"),
    )
    shot_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    spatial_continuity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    spatial_world_id: Mapped[str] = mapped_column(UUID, nullable=False)
    spatial_world_state_id: Mapped[str] = mapped_column(UUID, nullable=False)
    spatial_world_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    spatial_world_revision_hash: Mapped[str] = mapped_column(Text, nullable=False)
    location_entity_id: Mapped[str] = mapped_column(UUID, nullable=False)
    location_entity_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)


class ShotRevisionSpatialTrackState(Base):
    __tablename__ = "shot_revision_spatial_track_states"
    __table_args__ = (
        PrimaryKeyConstraint("shot_revision_id", "position", name="pk_shot_revision_spatial_track_states"),
        ForeignKeyConstraint(["shot_revision_id"], ["shot_revisions.id"], name="fk_srsts_revision", ondelete="RESTRICT"),
        ForeignKeyConstraint(["spatial_track_id"], ["spatial_tracks.id"], name="fk_srsts_track", ondelete="RESTRICT"),
        ForeignKeyConstraint(["entity_id"], ["creative_entities.id"], name="fk_srsts_entity", ondelete="RESTRICT"),
        ForeignKeyConstraint(["entity_revision_id"], ["entity_revisions.id"], name="fk_srsts_entity_rev", ondelete="RESTRICT"),
        ForeignKeyConstraint(["source_transition_id"], ["spatial_transitions.id"], name="fk_srsts_source_transition", ondelete="RESTRICT"),
        UniqueConstraint("shot_revision_id", "spatial_track_id", name="uq_srsts_revision_track"),
        CheckConstraint("position >= 0", name="ck_srsts_position"),
        CheckConstraint("requirement IN ('required','optional')", name="ck_srsts_requirement"),
        CheckConstraint("source_anchor_type IN ('sequence','scene','shot')", name="ck_srsts_anchor_type"),
        CheckConstraint("source_boundary IN ('start','end')", name="ck_srsts_boundary"),
    )
    shot_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    spatial_track_id: Mapped[str] = mapped_column(UUID, nullable=False)
    entity_id: Mapped[str] = mapped_column(UUID, nullable=False)
    entity_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    x_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    y_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    z_mm: Mapped[int] = mapped_column(Integer, nullable=False)
    yaw_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    pitch_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    roll_udeg: Mapped[int] = mapped_column(Integer, nullable=False)
    source_transition_id: Mapped[str] = mapped_column(UUID, nullable=False)
    source_anchor_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_anchor_id: Mapped[str] = mapped_column(UUID, nullable=False)
    source_boundary: Mapped[str] = mapped_column(Text, nullable=False)


class ShotRevisionSpatialPlan(Base):
    __tablename__ = "shot_revision_spatial_plans"
    __table_args__ = (
        PrimaryKeyConstraint("shot_revision_id", name="pk_shot_revision_spatial_plans"),
        ForeignKeyConstraint(["shot_revision_id"], ["shot_revisions.id"], name="fk_srsp_revision", ondelete="RESTRICT"),
        CheckConstraint("length(plan_hash) = 64", name="ck_srsp_hash_len"),
    )
    shot_revision_id: Mapped[str] = mapped_column(UUID, nullable=False)
    plan_hash: Mapped[str] = mapped_column(Text, nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)


class DerivedSpatialArtifact(Base):
    __tablename__ = "derived_spatial_artifacts"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_derived_spatial_artifacts"),
        ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_dsa_project", ondelete="RESTRICT"),
        ForeignKeyConstraint(["blob_hash"], ["blobs.hash"], name="fk_dsa_blob", ondelete="RESTRICT"),
        UniqueConstraint("project_id", "spec_hash", "runtime_fingerprint_hash", name="uq_dsa_project_spec_runtime"),
        UniqueConstraint("id", "blob_hash", name="uq_dsa_id_blob"),
        CheckConstraint("spec_schema_version = 1", name="ck_dsa_spec_schema"),
        CheckConstraint("length(spec_hash) = 64", name="ck_dsa_spec_hash_len"),
        CheckConstraint("spatial_continuity_schema_version = 1", name="ck_dsa_continuity_schema"),
        CheckConstraint("length(spatial_continuity_hash) = 64", name="ck_dsa_continuity_hash_len"),
        CheckConstraint("artifact_schema_version > 0", name="ck_dsa_artifact_schema"),
        CheckConstraint("length(runtime_fingerprint_hash) = 64", name="ck_dsa_fp_hash_len"),
        CheckConstraint("determinism_class = 'D0'", name="ck_dsa_d0_only"),
        CheckConstraint("length(blob_hash) = 64", name="ck_dsa_blob_hash_len"),
        Index("ix_dsa_spec_runtime", "spec_hash", "runtime_fingerprint_hash"),
        Index("ix_dsa_project_continuity", "project_id", "spatial_continuity_hash"),
        Index("ix_dsa_blob", "blob_hash"),
    )
    id: Mapped[str] = mapped_column(UUID)
    project_id: Mapped[str] = mapped_column(UUID, nullable=False)
    spec_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)
    spec_hash: Mapped[str] = mapped_column(Text, nullable=False)
    spatial_continuity_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    spatial_continuity_hash: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_kind: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm_id: Mapped[str] = mapped_column(Text, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False)
    runtime_fingerprint_json: Mapped[str] = mapped_column(Text, nullable=False)
    runtime_fingerprint_hash: Mapped[str] = mapped_column(Text, nullable=False)
    determinism_class: Mapped[str] = mapped_column(Text, nullable=False)
    blob_hash: Mapped[str] = mapped_column(Text, nullable=False)
    media_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class GenerationDerivedSpatialInput(Base):
    __tablename__ = "generation_derived_spatial_inputs"
    __table_args__ = (
        PrimaryKeyConstraint("generation_id", "input_key", "position", name="pk_generation_derived_spatial_inputs"),
        ForeignKeyConstraint(["generation_id"], ["generations.id"], name="fk_gdsi_generation", ondelete="RESTRICT"),
        ForeignKeyConstraint(["derived_spatial_artifact_id", "blob_hash"], ["derived_spatial_artifacts.id", "derived_spatial_artifacts.blob_hash"], name="fk_gdsi_artifact", ondelete="RESTRICT"),
        ForeignKeyConstraint(["blob_hash"], ["blobs.hash"], name="fk_gdsi_blob", ondelete="RESTRICT"),
        UniqueConstraint("generation_id", "artifact_role", "position", name="uq_gdsi_gen_role_position"),
        CheckConstraint("position >= 0", name="ck_gdsi_position"),
        CheckConstraint("length(blob_hash) = 64", name="ck_gdsi_blob_hash_len"),
        Index("ix_gdsi_artifact", "derived_spatial_artifact_id"),
        Index("ix_gdsi_blob", "blob_hash"),
    )
    generation_id: Mapped[str] = mapped_column(UUID, nullable=False)
    input_key: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_role: Mapped[str] = mapped_column(Text, nullable=False)
    derived_spatial_artifact_id: Mapped[str] = mapped_column(UUID, nullable=False)
    blob_hash: Mapped[str] = mapped_column(Text, nullable=False)


__all__ = [
    "SpatialWorld", "SpatialWorldState", "SpatialFrame", "SpatialWorldStateFrame",
    "SpatialAxis", "SpatialWorldStateAxis", "SpatialWorldRevision",
    "SpatialWorldRevisionFrame", "SpatialWorldRevisionAxis", "SpatialTrack",
    "SpatialTransition", "ShotSpatialPlan", "ShotRevisionSpatialWorld",
    "ShotRevisionSpatialTrackState", "ShotRevisionSpatialPlan",
    "DerivedSpatialArtifact", "GenerationDerivedSpatialInput",
]
