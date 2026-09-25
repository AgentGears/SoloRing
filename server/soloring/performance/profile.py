"""M17B `performance-profile/1` registry and canonical channel payload
v1 (frozen R7 §§5–6).

The profile grammar is transcribed exactly from the frozen G8
co-design: 13 channels (4 face articulation, 5 face expression, 4 body
local pose). No root/world trajectory channel exists in profile/1, so
an M17B payload cannot silently claim A4 world placement.

The payload grammar is CLOSED at every layer — payload, channel,
keyframe, rational and keyframe-provenance — unknown or missing keys
reject. Canonicalization uses the repository canonical JSON serializer
with channels sorted by channel_key and keyframes sorted by exact
rational timestamp; rationals are reduced before hashing; no float and
no Python bool participates in authority.
"""

from __future__ import annotations

from fractions import Fraction

from soloring.domain.canonical import canonical_json_str
from soloring.errors import ErrorCode, SoloRingError
from soloring.performance.temporal import (RationalError,
                                           canonical_rational)

PROFILE_ID = "performance-profile/1"

PPM = "bounded_scalar_ppm"
UDEG = "bounded_scalar_microdeg"

# frozen G8 profile-1 channel registry — exact keys, domains, roles,
# semantic keys, value grammars and integer bounds
CHANNELS = {
    "profile-1/face.articulation.jaw_open":
        ("face", "articulation", "jaw_open", PPM, 0, 1_000_000),
    "profile-1/face.articulation.lip_round":
        ("face", "articulation", "lip_round", PPM, 0, 1_000_000),
    "profile-1/face.articulation.lip_press":
        ("face", "articulation", "lip_press", PPM, 0, 1_000_000),
    "profile-1/face.articulation.mouth_width":
        ("face", "articulation", "mouth_width", PPM, -1_000_000,
         1_000_000),
    "profile-1/face.expression.brow_raise":
        ("face", "expression", "brow_raise", PPM, -1_000_000, 1_000_000),
    "profile-1/face.expression.brow_furrow":
        ("face", "expression", "brow_furrow", PPM, -1_000_000,
         1_000_000),
    "profile-1/face.expression.smile":
        ("face", "expression", "smile", PPM, -1_000_000, 1_000_000),
    "profile-1/face.expression.eye_squint":
        ("face", "expression", "eye_squint", PPM, 0, 1_000_000),
    "profile-1/face.expression.eye_wide":
        ("face", "expression", "eye_wide", PPM, 0, 1_000_000),
    "profile-1/body.pose.head_yaw_udeg":
        ("body", "pose", "head_yaw", UDEG, -30_000_000, 30_000_000),
    "profile-1/body.pose.head_pitch_udeg":
        ("body", "pose", "head_pitch", UDEG, -30_000_000, 30_000_000),
    "profile-1/body.pose.head_roll_udeg":
        ("body", "pose", "head_roll", UDEG, -30_000_000, 30_000_000),
    "profile-1/body.pose.torso_lean_udeg":
        ("body", "pose", "torso_lean", UDEG, -15_000_000, 15_000_000),
}

PERFORMANCE_KINDS = ("BODY", "FACIAL", "BODY_FACIAL")
PROVENANCE_KINDS = ("AUTHORED", "DERIVED", "DERIVED_THEN_EDITED")

_PAYLOAD_KEYS = {"schema_version", "performance_profile_id", "channels"}
_CHANNEL_KEYS = {"channel_key", "domain", "role", "semantic_key",
                 "value_grammar", "keyframes"}
_KEYFRAME_KEYS = {"time_ms", "value", "provenance"}
_RATIONAL_KEYS = {"num", "den"}
_KP_KEYS = {"kind", "source_alignment_id"}


def _invalid(code: ErrorCode, message: str) -> SoloRingError:
    return SoloRingError(code, message, status_code=422)


def _require_exact_keys(obj, expected: set, what: str,
                        code: ErrorCode) -> None:
    if not isinstance(obj, dict):
        raise _invalid(code, f"{what} must be a JSON object")
    keys = set(obj)
    if keys != expected:
        raise _invalid(
            code,
            f"{what} keys must be exactly {sorted(expected)} — the "
            f"schema is closed (got {sorted(keys)}; unknown="
            f"{sorted(keys - expected)}, missing="
            f"{sorted(expected - keys)})")


def validate_temporal_domain(start_num: int, start_den: int,
                             end_num: int, end_den: int
                             ) -> tuple[int, int, int, int]:
    """Canonicalize and validate PerformanceTemporalDomainV1 (frozen
    R7 §7). Rational grammar failures raise INVALID_RATIONAL (the M17A
    code); a well-formed domain with start >= end raises
    PERFORMANCE_TEMPORAL_DOMAIN_INVALID."""
    try:
        sn, sd = canonical_rational(start_num, start_den)
        en, ed = canonical_rational(end_num, end_den)
    except RationalError:
        raise
    if Fraction(sn, sd) >= Fraction(en, ed):
        raise _invalid(
            ErrorCode.PERFORMANCE_TEMPORAL_DOMAIN_INVALID,
            f"temporal domain [{sn}/{sd}, {en}/{ed}) is empty or "
            "inverted: start must be strictly less than end")
    return sn, sd, en, ed


def _validate_keyframe_provenance(prov, what: str) -> dict:
    _require_exact_keys(prov, _KP_KEYS, f"{what} provenance",
                        ErrorCode.PERFORMANCE_PAYLOAD_INVALID)
    kind = prov["kind"]
    if kind not in PROVENANCE_KINDS:
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            f"{what} provenance kind must be one of "
            f"{PROVENANCE_KINDS}")
    alignment = prov["source_alignment_id"]
    if kind == "AUTHORED" and alignment is not None:
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            f"{what} AUTHORED provenance requires source_alignment_id "
            "= null")
    if alignment is not None and not isinstance(alignment, str):
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
            f"{what} source_alignment_id must be null or an exact "
            "alignment id string")
    return {"kind": kind, "source_alignment_id": alignment}


def build_canonical_payload(payload: dict, *, performance_kind: str,
                            performance_profile_id: str,
                            start_num: int, start_den: int,
                            end_num: int, end_den: int
                            ) -> tuple[bytes, list[dict]]:
    """Validate the closed payload grammar against the frozen profile
    registry and return (exact canonical UTF-8 JSON bytes, normalized
    logical channels).

    The caller's dict may present channels/keyframes in any order; the
    canonical output sorts channels lexicographically by channel_key
    and keyframes by exact rational timestamp. Rationals are reduced
    before serialization. No float and no Python bool participates.
    """
    _require_exact_keys(payload, _PAYLOAD_KEYS, "payload",
                        ErrorCode.PERFORMANCE_PAYLOAD_INVALID)
    if payload["schema_version"] != 1:
        raise _invalid(
            ErrorCode.PERFORMANCE_PAYLOAD_SCHEMA_UNSUPPORTED,
            "payload schema_version must be exactly 1")
    if payload["performance_profile_id"] != PROFILE_ID:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROFILE_UNSUPPORTED,
            f"performance_profile_id must be exactly '{PROFILE_ID}' "
            f"(got {payload['performance_profile_id']!r})")
    if performance_profile_id != PROFILE_ID:
        raise _invalid(
            ErrorCode.PERFORMANCE_PROFILE_UNSUPPORTED,
            f"row performance_profile_id must be exactly '{PROFILE_ID}'")
    if performance_kind not in PERFORMANCE_KINDS:
        raise _invalid(
            ErrorCode.PERFORMANCE_KIND_INVALID,
            f"performance_kind must be one of {PERFORMANCE_KINDS}")

    sn, sd, en, ed = validate_temporal_domain(
        start_num, start_den, end_num, end_den)
    start_ms = Fraction(sn, sd)
    end_ms = Fraction(en, ed)

    channels_in = payload["channels"]
    if not isinstance(channels_in, list) or not channels_in:
        raise _invalid(ErrorCode.PERFORMANCE_EMPTY_PAYLOAD,
                       "payload must declare at least one channel")

    seen_keys = set()
    face = body = 0
    normalized: list[dict] = []
    alignment_ids: set[str] = set()

    for ch in channels_in:
        _require_exact_keys(ch, _CHANNEL_KEYS, "channel",
                            ErrorCode.PERFORMANCE_PAYLOAD_INVALID)
        key = ch["channel_key"]
        if not isinstance(key, str) or key not in CHANNELS:
            raise _invalid(
                ErrorCode.PERFORMANCE_CHANNEL_UNKNOWN,
                f"channel {key!r} is not in {PROFILE_ID}")
        if key in seen_keys:
            raise _invalid(ErrorCode.PERFORMANCE_DUPLICATE_CHANNEL,
                           f"channel {key!r} declared more than once")
        seen_keys.add(key)

        domain, role, semantic, grammar, lo, hi = CHANNELS[key]
        for field, value in (("domain", ch["domain"]),
                             ("role", ch["role"]),
                             ("semantic_key", ch["semantic_key"]),
                             ("value_grammar", ch["value_grammar"])):
            expected = {"domain": domain, "role": role,
                        "semantic_key": semantic,
                        "value_grammar": grammar}[field]
            if value != expected:
                raise _invalid(
                    ErrorCode.PERFORMANCE_CHANNEL_DESCRIPTOR_MISMATCH,
                    f"channel {key!r} {field} must be {expected!r} "
                    f"(got {value!r})")

        keyframes_in = ch["keyframes"]
        if not isinstance(keyframes_in, list) or not keyframes_in:
            raise _invalid(
                ErrorCode.PERFORMANCE_EMPTY_CHANNEL,
                f"channel {key!r} must contain at least one keyframe")

        kfs = []
        for kf in keyframes_in:
            _require_exact_keys(kf, _KEYFRAME_KEYS, "keyframe",
                                ErrorCode.PERFORMANCE_PAYLOAD_INVALID)
            t = kf["time_ms"]
            _require_exact_keys(t, _RATIONAL_KEYS, "time_ms",
                                ErrorCode.PERFORMANCE_PAYLOAD_INVALID)
            try:
                tn, td = canonical_rational(t["num"], t["den"])
            except RationalError:
                raise
            t_ms = Fraction(tn, td)
            if not (start_ms <= t_ms < end_ms):
                raise _invalid(
                    ErrorCode.PERFORMANCE_KEYFRAME_OUTSIDE_DOMAIN,
                    f"keyframe {tn}/{td} ms outside the temporal domain "
                    f"[{sn}/{sd}, {en}/{ed})")
            v = kf["value"]
            if isinstance(v, bool) or not isinstance(v, int):
                raise _invalid(
                    ErrorCode.PERFORMANCE_VALUE_NOT_INTEGER,
                    f"channel {key!r} keyframe value must be an "
                    "integer (bool is not an integer)")
            if not (lo <= v <= hi):
                raise _invalid(
                    ErrorCode.PERFORMANCE_VALUE_OUT_OF_RANGE,
                    f"channel {key!r} value {v} outside "
                    f"[{lo}, {hi}] for grammar {grammar}")
            prov = _validate_keyframe_provenance(
                kf["provenance"], f"channel {key!r}")
            if prov["source_alignment_id"] is not None:
                alignment_ids.add(prov["source_alignment_id"])
            kfs.append({"time_ms": {"num": tn, "den": td},
                        "value": v, "provenance": prov})

        kfs.sort(key=lambda k: Fraction(k["time_ms"]["num"],
                                        k["time_ms"]["den"]))
        for a, b in zip(kfs, kfs[1:]):
            if Fraction(a["time_ms"]["num"], a["time_ms"]["den"]) == \
                    Fraction(b["time_ms"]["num"], b["time_ms"]["den"]):
                raise _invalid(
                    ErrorCode.PERFORMANCE_DUPLICATE_KEYFRAME_TIME,
                    f"channel {key!r} has duplicate canonical keyframe "
                    "timestamps")

        if domain == "face":
            face += 1
        else:
            body += 1
        normalized.append({"channel_key": key, "domain": domain,
                           "role": role, "semantic_key": semantic,
                           "value_grammar": grammar, "keyframes": kfs})

    # performance-kind channel law (frozen §5.4)
    if performance_kind == "BODY" and face:
        raise _invalid(
            ErrorCode.PERFORMANCE_CHANNEL_KIND_MISMATCH,
            "BODY performance must contain zero face channels")
    if performance_kind == "FACIAL" and body:
        raise _invalid(
            ErrorCode.PERFORMANCE_CHANNEL_KIND_MISMATCH,
            "FACIAL performance must contain zero body channels")
    if performance_kind == "BODY_FACIAL" and (not body or not face):
        raise _invalid(
            ErrorCode.PERFORMANCE_CHANNEL_KIND_MISMATCH,
            "BODY_FACIAL performance needs >=1 body and >=1 face "
            "channel")

    normalized.sort(key=lambda c: c["channel_key"])
    canonical = {"schema_version": 1,
                 "performance_profile_id": PROFILE_ID,
                 "channels": normalized}
    body_bytes = canonical_json_str(canonical).encode("utf-8")
    return body_bytes, normalized
