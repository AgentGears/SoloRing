"""ContinuityPredicate + ContinuityRelation API schemas (M7D §4–§5).

extra=forbid everywhere. Predicates expose only display-mutable metadata
(``key`` is immutable identity and absent from PredicatePatch). Relations
have NO mutable columns (0008) — therefore no RelationPatch exists.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PredicateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    description: str | None = None


class PredicatePatch(BaseModel):
    """Display metadata only — ``key`` is immutable identity (§4.1)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None


class PredicateRead(BaseModel):
    id: str
    project_id: str
    key: str
    name: str
    description: str | None
    created_at: str
    updated_at: str


class RelationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_entity_id: str
    predicate_id: str
    object_entity_id: str


class RelationRead(BaseModel):
    """``predicate_key`` is denormalized for display (list order is the
    frozen display order subject, predicate_key, object, relation_id)."""

    id: str
    project_id: str
    subject_entity_id: str
    predicate_id: str
    predicate_key: str
    object_entity_id: str
    created_at: str


class RelationTransitionCreate(BaseModel):
    """Relation temporal state: ``state`` replaces the feature set/clear
    operation vocabulary — `active` is presence, `inactive` is canonical
    absence (M7D §6.1). No value fields exist."""

    model_config = ConfigDict(extra="forbid")

    anchor_type: str
    anchor_id: str
    boundary: str
    state: str


class RelationTransitionPatch(BaseModel):
    """Prospective-row semantics (§6.2): every field omitted → preserve.
    There is no value matrix — nothing to inherit or clear."""

    model_config = ConfigDict(extra="forbid")

    anchor_type: str | None = None
    anchor_id: str | None = None
    boundary: str | None = None
    state: str | None = None


class RelationTransitionRead(BaseModel):
    id: str
    relation_id: str
    anchor_type: str
    anchor_id: str
    boundary: str
    state: str
    created_at: str
    updated_at: str
