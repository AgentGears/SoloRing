"""Shot request/response schemas (plan §9, §15, §46)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from soloring.domain.normalize import SHOT_SUBJECT_MAX


# Creative intent fields shared by create/patch/read (plan §9.1).
_INTENT_FIELDS = {
    "subject": Field(max_length=SHOT_SUBJECT_MAX),
}


class _CreativeOptional:
    """Mixin marker; actual fields declared per-model below."""


class ShotCreate(BaseModel):
    """Create a Shot. `approved_take_id` is not accepted (plan §9.2)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    subject: str = Field(max_length=SHOT_SUBJECT_MAX)
    action: str | None = None
    environment: str | None = None
    framing: str | None = None
    camera_motion: str | None = None
    lens: str | None = None
    mood: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class ShotPatch(BaseModel):
    """Patch a Shot. Only creative fields; server-controlled fields rejected."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    subject: str | None = Field(default=None, max_length=SHOT_SUBJECT_MAX)
    action: str | None = None
    environment: str | None = None
    framing: str | None = None
    camera_motion: str | None = None
    lens: str | None = None
    mood: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class SemanticDependencyItem(BaseModel):
    """Shot-detail dependency summary (§62). Names/metadata are display
    only; canonical identity is the resolved revision triple."""

    entity_id: str
    entity_kind: str
    role: str
    position: int
    resolved_revision_id: str
    resolved_revision_number: int
    resolved_revision_hash: str


class SemanticDependencyWithEntity(SemanticDependencyItem):
    entity_name: str | None = None


class ShotRead(BaseModel):
    """Detail view: working snapshot hash + canon comparison (§15, §94)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    shot_number: int
    title: str | None
    subject: str
    action: str | None
    environment: str | None
    framing: str | None
    camera_motion: str | None
    lens: str | None
    mood: str | None
    duration_ms: int | None
    approved_take_id: str | None
    scene_id: str | None = None
    scene_position: int | None = None
    created_at: str
    updated_at: str
    working_snapshot_hash: str | None
    working_state_differs_from_approved: bool | None
    semantic_dependencies: list[SemanticDependencyItem] = []
    continuity_ready: bool = False
    continuity_state_ready: bool = True
    # M7D §12.4: the ONE additive ShotRead field. Default-empty; populated
    # only from authoritative current-state resolution — never historical
    # provenance, never fabricated client-side.
    readiness_issues: list = []
    # M8 §52 additive fields: visual readiness/honest NULLs. §52.1: no
    # ready-by-default — an unpopulated projection is not visual readiness.
    visual_continuity_ready: bool = False
    visual_reference_pack_hash: str | None = None
    visual_continuity_issues: list = []
    # M10D §40 additive computed fields. Default-False: an unpopulated
    # projection is not spatial readiness. No column is added to shots.
    spatial_continuity_ready: bool = False
    spatial_continuity_hash: str | None = None
    spatial_continuity_issues: list = []


class ShotListItem(BaseModel):
    """Lightweight list item: no working_snapshot_hash (plan §15)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    shot_number: int
    title: str | None
    subject: str
    scene_id: str | None = None
    scene_position: int | None = None
    created_at: str
    updated_at: str
