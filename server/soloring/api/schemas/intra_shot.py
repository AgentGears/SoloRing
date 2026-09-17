"""Strict M16 intra-Shot API schemas (frozen R6 §4/§10).

M16 integer fields are strict JavaScript-safe JSON integers. State shape is
closed here; target-specific value semantics are validated by the canonical
service against the exact live target schema.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

SAFE_INT_MAX = 9_007_199_254_740_991
StrictTimeMs = Annotated[int, Field(strict=True, ge=1, le=SAFE_INT_MAX)]
StrictOrdinal = Annotated[int, Field(strict=True, ge=0, le=SAFE_INT_MAX)]
LowerHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntraShotTarget(_ClosedModel):
    kind: Literal[
        "entity_feature", "entity_relation", "production_instance_feature"
    ]
    id: str


class FeatureStateInput(_ClosedModel):
    present: StrictBool
    value: Any = None
    value_hash: LowerHash | None = None

    @model_validator(mode="after")
    def _exact_shape(self):
        provided = self.model_fields_set
        if not self.present:
            if provided != {"present"}:
                raise ValueError("absent feature state is exactly {'present':false}")
        else:
            if provided != {"present", "value", "value_hash"}:
                raise ValueError(
                    "present feature state requires exactly present,value,value_hash"
                )
            if self.value_hash is None:
                raise ValueError("present feature state requires value_hash")
        return self


class RelationStateInput(_ClosedModel):
    active: StrictBool


IntraShotStateInput = FeatureStateInput | RelationStateInput


class IntraShotEventCreate(_ClosedModel):
    time_ms: StrictTimeMs
    ordinal: StrictOrdinal
    target: IntraShotTarget
    before: IntraShotStateInput
    after: IntraShotStateInput
    persistence_mode: Literal["transient", "require_handoff"]


class IntraShotEventPatch(_ClosedModel):
    time_ms: StrictTimeMs | None = None
    ordinal: StrictOrdinal | None = None
    before: IntraShotStateInput | None = None
    after: IntraShotStateInput | None = None
    persistence_mode: Literal["transient", "require_handoff"] | None = None

    @model_validator(mode="after")
    def _nonempty_nonnull(self):
        if not self.model_fields_set:
            raise ValueError("event PATCH requires at least one semantic field")
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} may not be null")
        return self


class IntraShotEventRead(_ClosedModel):
    id: str
    schema_version: Literal[1]
    time_ms: int
    ordinal: int
    target: dict
    before: dict
    after: dict
    persistence_mode: Literal["transient", "require_handoff"]
    event_hash: str
    source_kind: Literal["authored", "proposal_adoption"]
    source_proposal_id: str | None


class IntraShotIssue(_ClosedModel):
    code: str
    message: str
    details: dict = {}


class IntraShotHandoff(_ClosedModel):
    target: dict
    required_state: dict | str
    existing: dict | None
    matched: bool
    reason: str


class IntraShotTerminalTarget(_ClosedModel):
    target: dict
    terminal_event_id: str | None
    time_ms: int
    ordinal: int
    terminal_state: dict | str
    persistence_mode: Literal["transient", "require_handoff"]


class IntraShotRead(_ClosedModel):
    """The one server-side M16 resolver projection (frozen R6 §9.1/§10.1).

    The browser renders this; it never re-folds events or re-compares
    handoffs. ``next_cursor`` pages the ordered events list (default 100,
    maximum 500) — readiness/issues/hash cover the WHOLE active set.
    """

    shot_id: str
    intra_shot_ready: bool
    intra_shot_issues: list[IntraShotIssue]
    duration_ms: int | None
    events: list[IntraShotEventRead]
    terminal_targets: list[IntraShotTerminalTarget]
    handoffs: list[IntraShotHandoff]
    event_set_hash: str | None
    next_cursor: int | None = None


# Proposal Grammar v1 is frozen in M16-A even though proposal ingestion/adoption
# is delivered in M16-D. These schemas make the eventual boundary unambiguous.
class ProposalCandidateEvent(_ClosedModel):
    time_ms: StrictTimeMs
    ordinal: StrictOrdinal
    target: IntraShotTarget
    before: IntraShotStateInput
    after: IntraShotStateInput


class ProposalGrammarV1(_ClosedModel):
    schema_version: Literal[1]
    candidate_event: ProposalCandidateEvent
    persistence_suggestion: Literal["transient", "persist"]


# --------------------------------------------------------------------------
# M16-D proposal + review schemas (frozen R6 §11/§12)
# --------------------------------------------------------------------------


class ProposalCandidate(_ClosedModel):
    time_ms: StrictTimeMs
    ordinal: StrictOrdinal
    target: IntraShotTarget
    before: IntraShotStateInput
    after: IntraShotStateInput


class ProposalCreate(_ClosedModel):
    schema_version: Literal[1] = 1
    source_kind: Literal["generation", "take", "imported"]
    source_shot_revision_id: str
    source_shot_revision_hash: LowerHash
    source_generation_id: str | None = None
    source_take_id: str | None = None
    proposer_kind: Literal["human", "analyzer"]
    analyzer_id: str | None = None
    analyzer_version: str | None = None
    analyzer_parameters_hash: LowerHash | None = None
    candidate_event: ProposalCandidate
    persistence_suggestion: Literal["transient", "persist"]


class ProposalReviewDecision(_ClosedModel):
    """One review decision: for proposal reviews it carries the proposal
    hash + decision; for direct event adopt/decline it carries the
    event hash + event-set hash fences."""

    expected_proposal_hash: LowerHash | None = None
    expected_event_hash: LowerHash | None = None
    expected_event_set_hash: LowerHash | None = None
    decision: Literal[
        "adopt_event_only", "adopt_persistence", "ignore"] | None = None

    @model_validator(mode="after")
    def _exact_shape(self):
        provided = self.model_fields_set
        if self.decision is None:
            # direct event fence form
            if provided != {
                    "expected_event_hash", "expected_event_set_hash"}:
                raise ValueError(
                    "direct event reviews require exactly "
                    "expected_event_hash + expected_event_set_hash")
        else:
            # proposal review form
            need = {"expected_proposal_hash", "decision"}
            if "expected_event_set_hash" in provided:
                need.add("expected_event_set_hash")
            if provided != need:
                raise ValueError(
                    "proposal reviews require exactly "
                    "expected_proposal_hash + decision")
        return self


class ProposalReviewItem(_ClosedModel):
    proposal_id: str
    expected_proposal_hash: LowerHash
    decision: Literal[
        "adopt_event_only", "adopt_persistence", "ignore"]


class ProposalReviewBatch(_ClosedModel):
    reviews: list[ProposalReviewItem] = Field(min_length=1,
                                              max_length=10_000)
