"""M8 VisualFacet/VisualAnchor API schemas (frozen plan §67).

extra=forbid everywhere. Feature values arrive in their M7-native typed
form (e.g. an enum member string); the server derives the canonical
`(feature_value_json, feature_value_hash)` through M7 `canonicalize_value`
— clients never author that pair (frozen plan §11).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

TARGET_KINDS = ("entity", "feature")
REQUIREMENTS = ("required", "optional")
POLICIES = ("required", "optional", "not_applicable")
ROLES = ("primary", "supporting", "detail", "context")


class VisualFacetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_kind: str
    entity_id: str | None = None
    feature_id: str | None = None
    facet_key: str
    label: str | None = None
    description: str | None = None
    requirement: str = "required"


class VisualFacetPatch(BaseModel):
    """Display/requirement metadata only; target identity is immutable."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None
    requirement: str | None = None


class VisualFacetRead(BaseModel):
    id: str
    project_id: str
    target_kind: str
    entity_id: str | None
    feature_id: str | None
    facet_key: str
    label: str | None
    description: str | None
    requirement: str
    created_at: str
    updated_at: str


class ValuePolicyItem(BaseModel):
    """One feature-value policy. ``value`` is M7-native typed form."""

    model_config = ConfigDict(extra="forbid")

    value: object
    policy: str


class ValuePolicyPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policies: list[ValuePolicyItem]


class ValuePolicyRead(BaseModel):
    feature_value_json: str
    feature_value_hash: str
    policy: str


class VisualAnchorCreate(BaseModel):
    """State binding, expressed semantically. The server resolves:

    * entity facet -> the submitted EntityRevision id;
    * feature facet -> the M7-native ``value`` + the visual-context
      EntityRevision id (required: every feature is entity-scoped in 0008).
    """

    model_config = ConfigDict(extra="forbid")

    entity_revision_id: str | None = None
    value: object = None
    visual_context_entity_revision_id: str | None = None


class VisualAnchorRead(BaseModel):
    id: str
    visual_facet_id: str
    entity_revision_id: str | None
    feature_value_hash: str | None
    feature_value_json: str | None
    visual_context_entity_revision_id: str | None
    approved_revision_id: str | None
    created_at: str
    updated_at: str
