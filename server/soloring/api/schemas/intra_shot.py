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
