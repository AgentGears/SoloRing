"""Shot request/response schemas (plan §9, §15, §46)."""

from __future__ import annotations

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, WithJsonSchema,
    model_validator,
)
from typing import Annotated

from soloring.domain.normalize import SHOT_SUBJECT_MAX
# RR20-M17CC-01: the ONE shared signed-SQLite-INTEGER authority bound
# (a LOW storage/domain layer — the schema does NOT depend upward on
# the M16 continuity package); duration_ms persists to a SQLite
# INTEGER column, so the public authoring boundary certifies physical
# representability BEFORE any SQLite bind (a raw driver OverflowError
# is never the admission contract)
from soloring.domain.storage import SQLITE_INT_MAX


def _exact_duration(value):
    """RR21/RR22-M17CC-01: the CLOSED exact admission law for Shot
    duration. The web boundary transports authoritative duration as a
    canonical decimal string (the additive ``duration_ms_dec``
    coordinate) because JavaScript ``number`` cannot carry every
    lawful signed-SQLite integer — so the writer path accepts that
    string form as an intentional, validated contract: a bare decimal
    digit string ("0" or [1-9][0-9]*; no sign, exponent, decimal
    point, whitespace, or leading-zero alias) converted to the exact
    backend integer.

    RR22: the gate is now MECHANICALLY CLOSED — this function
    returns ONLY the accepted branches (the exact int, the converted
    canonical string, or None) and raises on EVERY other
    representation. There is deliberately NO catch-all ``return
    value``: a raw JSON float (1.0, 1e3, 9007199254740993.0 — the
    JSON decoder itself rounds the last to ...992.0), a bool, a
    Decimal-like numeric wrapper, a container, and every ambiguous
    string form all refuse here as ordinary request validation —
    NOTHING falls through into Pydantic's non-strict ``int``
    coercion, so an unsafe numeric lexeme can never round into a
    different durable authority."""
    if value is None:
        return None
    # bool is an int subclass — checked BEFORE the int branch
    if isinstance(value, bool):
        raise ValueError(
            "duration_ms must be an integer, a canonical decimal "
            "string, or null")
    exact = None
    if type(value) is int:
        exact = value
    elif type(value) is str:
        import re
        if re.fullmatch(r"0|[1-9][0-9]*", value):
            exact = int(value)
        else:
            raise ValueError(
                "duration_ms must be a canonical decimal string "
                "(bare digits, no sign/exponent/point/whitespace/"
                "leading zeros)")
    else:
        raise ValueError(
            "duration_ms must be an integer, a canonical decimal "
            f"string, or null (got {type(value).__name__})")
    # the RR20 storage bound, enforced INSIDE the closed gate (never
    # delegated to a numeric Field constraint that would also apply
    # to the None branch)
    if not 0 <= exact <= SQLITE_INT_MAX:
        raise ValueError(
            f"duration_ms must be between 0 and {SQLITE_INT_MAX}")
    return exact


# RR23-M17CC-01: the ONE bounded canonical-decimal input-schema
# pattern, GENERATED from SQLITE_INT_MAX (never a hand-typed regex,
# never a duplicated literal) — an anchored alternation admitting
# "0", every shorter non-leading-zero digit string, and every
# same-length decimal strictly below the maximum at each prefix
# position, plus the maximum itself. A bare canonical regex plus
# maxLength would admit "9999999999999999999"; this construction
# excludes EVERY canonical decimal above SQLITE_INT_MAX.
def _bounded_canonical_decimal_regex(max_str: str) -> str:
    parts = ["0"]
    n = len(max_str)
    if n > 1:
        # any shorter canonical form (1..n-1 digits, no leading zero)
        parts.append(f"[1-9][0-9]{{0,{n - 2}}}")
    for i in range(n):
        d = int(max_str[i])
        if d == 0:
            continue
        # equal prefix, digit i strictly below max's digit i, the
        # remaining digits arbitrary
        low = 1 if i == 0 else 0
        rest_count = n - i - 1
        rest = f"[0-9]{{{rest_count}}}" if rest_count else ""
        parts.append(
            f"{max_str[:i]}[{low}-{d - 1}]{rest}")
    parts.append(max_str)
    return "^(?:" + "|".join(parts) + ")$"


# the string-branch contract of the machine-readable input schema
CANONICAL_DURATION_INPUT_PATTERN = _bounded_canonical_decimal_regex(
    str(SQLITE_INT_MAX))


def _exact_duration_input_schema() -> dict:
    """RR23-M17CC-01: the machine-readable input contract that
    EXACTLY describes what the closed runtime gate accepts — a null,
    a bounded integer, or a canonical bounded decimal string —
    attached via Pydantic's WithJsonSchema (validation mode; the
    OpenAPI request bodies consume the same declaration)."""
    return {
        "anyOf": [
            {
                "type": "integer",
                "minimum": 0,
                "maximum": SQLITE_INT_MAX,
            },
            {
                "type": "string",
                "pattern": CANONICAL_DURATION_INPUT_PATTERN,
            },
            {
                "type": "null",
            },
        ],
        "description": (
            "Exact Shot duration: a JSON integer in "
            f"[0, {SQLITE_INT_MAX}], or the same integer as a "
            "canonical decimal string (bare digits, no "
            "sign/exponent/point/whitespace/leading zeros, at most "
            f"{SQLITE_INT_MAX}), or null to unset. Floats and "
            "ambiguous numeric forms are refused."),
    }


# RR22/RR23-M17CC-01: the FIELD TYPE + input-schema declaration.
# The BeforeValidator normalizes the string branch to the exact int
# and enforces the [0, SQLITE_INT_MAX] storage bound (rejecting
# everything else — never letting a float or wrapper reach
# Pydantic's ordinary coercion); WithJsonSchema (validation mode)
# publishes the bounded integer/string/null input contract above so
# the generated validation/OpenAPI schema tells exactly the truth
# the runtime enforces — the model's post-validation value remains
# the integer authority (no semantic widening for documentation).
ExactDuration = Annotated[
    int | str | None,
    BeforeValidator(_exact_duration),
    WithJsonSchema(
        _exact_duration_input_schema(), mode="validation"),
]


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
    duration_ms: ExactDuration = Field(default=None)


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
    duration_ms: ExactDuration = Field(default=None)


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

    @model_validator(mode="before")
    @classmethod
    def _derive_exact_duration(cls, data):
        # RR21-M17CC-01: derive the additive exact transport
        # coordinate from the row's OWN durable integer (never an
        # independently supplied value — transport data, not a
        # second authority domain)
        if isinstance(data, dict) and "duration_ms_dec" not in data:
            duration = data.get("duration_ms")
            data["duration_ms_dec"] = (
                None if duration is None else str(int(duration)))
        elif (not isinstance(data, dict)
                and getattr(data, "duration_ms", None) is not None
                and getattr(data, "duration_ms_dec", None) is None):
            data = {**vars(data),
                    "duration_ms_dec": str(int(data.duration_ms))}
        return data

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
    # RR21-M17CC-01: the additive EXACT transport coordinate — the
    # backend integer's canonical decimal string ("0",
    # "9007199254740993", …; null when unset). Derived transport
    # data, never a second authority domain: its sole source is the
    # same durable duration_ms integer, and it exists because
    # JavaScript number cannot carry every lawful signed-SQLite
    # integer (2^53+1 already rounds). The web boundary MUST use
    # this for authoritative display, edit initialization, equality,
    # and submission.
    duration_ms_dec: str | None = None
    approved_take_id: str | None
    scene_id: str | None = None
    scene_position: int | None = None
    created_at: str
    updated_at: str
    working_snapshot_hash: str | None
    working_state_differs_from_approved: bool | None
    intra_shot_ready: bool = False
    intra_shot_issues: list = []
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
