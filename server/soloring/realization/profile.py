"""RealizationProfile schema 1 (frozen plan §7).

A versioned SoloRing-native execution-configuration artifact shipped
with a workflow package. Strict recursive unknown-field rejection; the
document describes capability, never current Shot/anchor state.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from soloring.errors import ErrorCode, SoloRingError

PROFILE_SCHEMA_VERSION = 1
TARGET_KINDS = ("entity", "feature_value")
M8_ROLE_VOCABULARY = ("primary", "supporting", "detail", "context")

# The frozen M8 facet_key grammar (M9 introduces no second naming system).
FACET_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


class ProfileError(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(
            ErrorCode.REALIZATION_PROFILE_INVALID, message, status_code=422
        )


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileModelIdentity(_Strict):
    id: str
    version: str


class ProfileChannel(_Strict):
    input_key: str
    min_items: int = Field(ge=0)
    max_items: int = Field(ge=1)
    allowed_roles: list[str] = Field(min_length=1)


class ProfileRule(_Strict):
    target_kind: str
    facet_key: str
    channel: str


class RealizationProfileDocument(_Strict):
    schema_version: int
    profile_id: str
    profile_version: int = Field(ge=1)
    workflow_id: str
    workflow_version: int = Field(ge=1)
    model: ProfileModelIdentity
    channels: dict[str, ProfileChannel]
    rules: list[ProfileRule]
    parameter_overrides: dict[str, float | int | str | bool]


def parse_profile(raw: str | dict) -> RealizationProfileDocument:
    """Strict parse; raises REALIZATION_PROFILE_INVALID on any shape error."""
    import json

    from soloring.domain.normalize import normalize_required_text

    try:
        doc = raw if isinstance(raw, dict) else json.loads(raw)
    except ValueError as exc:
        raise ProfileError(f"RealizationProfile is not valid JSON: {exc}")
    try:
        parsed = RealizationProfileDocument.model_validate(doc)
    except ValidationError as exc:
        raise ProfileError(f"Invalid RealizationProfile: {exc}") from exc
    _validate_semantics(parsed)
    return parsed


def _norm(value: str) -> str:
    return value.strip()


def _validate_semantics(doc: RealizationProfileDocument) -> None:
    if doc.schema_version != PROFILE_SCHEMA_VERSION:
        raise ProfileError(
            f"RealizationProfile schema_version must be "
            f"{PROFILE_SCHEMA_VERSION}."
        )
    for label, value in (
        ("profile_id", doc.profile_id),
        ("workflow_id", doc.workflow_id),
        ("model.id", doc.model.id),
        ("model.version", doc.model.version),
    ):
        if not _norm(value):
            raise ProfileError(f"RealizationProfile {label} is empty.")
    if not doc.channels:
        raise ProfileError("RealizationProfile declares no channels.")

    seen_input_keys: dict[str, str] = {}
    for channel_key, channel in doc.channels.items():
        if not _norm(channel_key):
            raise ProfileError("RealizationProfile channel key is empty.")
        if not _norm(channel.input_key):
            raise ProfileError(
                f"Channel {channel_key!r} has an empty input_key."
            )
        if channel.input_key in seen_input_keys:
            raise ProfileError(
                f"Channels {seen_input_keys[channel.input_key]!r} and "
                f"{channel_key!r} share input_key {channel.input_key!r}."
            )
        seen_input_keys[channel.input_key] = channel_key
        if channel.min_items > channel.max_items:
            raise ProfileError(
                f"Channel {channel_key!r}: min_items "
                f"{channel.min_items} exceeds max_items "
                f"{channel.max_items}."
            )
        if len(set(channel.allowed_roles)) != len(channel.allowed_roles):
            raise ProfileError(
                f"Channel {channel_key!r} allowed_roles has duplicates."
            )
        for role in channel.allowed_roles:
            if role not in M8_ROLE_VOCABULARY:
                raise ProfileError(
                    f"Channel {channel_key!r} allows unknown M8 role "
                    f"{role!r}."
                )

    selectors: set[tuple[str, str]] = set()
    for rule in doc.rules:
        if rule.target_kind not in TARGET_KINDS:
            raise ProfileError(
                f"Rule target_kind {rule.target_kind!r} is not one of "
                f"{TARGET_KINDS}."
            )
        if not FACET_KEY_RE.match(rule.facet_key):
            raise ProfileError(
                f"Rule facet_key {rule.facet_key!r} violates the frozen M8 "
                "grammar."
            )
        if rule.channel not in doc.channels:
            raise ProfileError(
                f"Rule ({rule.target_kind}, {rule.facet_key}) references "
                f"unknown channel {rule.channel!r}."
            )
        selector = (rule.target_kind, rule.facet_key)
        if selector in selectors:
            raise ProfileError(
                f"Duplicate profile selector {selector}: no order-based "
                "winner exists."
            )
        selectors.add(selector)

    # Every min_items > 0 channel must be reachable from at least one rule
    # (§7.6) — otherwise the package is statically invalid.
    targeted = {rule.channel for rule in doc.rules}
    for channel_key, channel in doc.channels.items():
        if channel.min_items > 0 and channel_key not in targeted:
            raise ProfileError(
                f"Channel {channel_key!r} declares min_items "
                f"{channel.min_items} but no rule targets it."
            )
