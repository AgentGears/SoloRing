"""M17C-D §14.6 executor translation and materialization laws —
the ONE shared sampler (frozen plan R2-FINAL W1/Decision D).

This module is a PURE, session-free implementation of the frozen
R4 §14.6 laws:

(a) keyframe step sampling with EXACT rational time — for output
    frame ``k``, compute the frame-left Performance time and
    consume the most recent channel keyframe whose exact time is
    ``<=`` that sample time; no floating-point time comparison, no
    mutation of authority;
(b) segment activity — a segment contributes controls only for
    ``shot_anchor <= frame_left_shot_time < shot_anchor +
    (performance_end - performance_start)``; outside that window
    its keyframes are never sampled;
(c) J/L-cut audio materialization — the exact source-sample→Shot
    mapping intersected with the picture window in INTEGER sample
    arithmetic; a negative anchor is never realized as positive
    leading silence; the tail past picture end is excluded; the
    remainder past the segment's Shot end is silence to picture
    length.

Plus the frozen execution-side refusals: anchor representability
(``PERFORMANCE_EXECUTION_ANCHOR_UNREPRESENTABLE``), channel
readiness (``PERFORMANCE_EXECUTION_BINDING_INVALID`` — each
consumed channel must have a keyframe at or before its first
sampled Performance time; never a zero default), the §14.7
FACIAL-only lane (kind gate + body-channel gate), and direct
keyframe-list evaluation (no cumulative ramp; no authority-side
frame-grid law).

Exactly THREE consumers import from here — the create-path
translation, the worker pre-submit proof, and the recovery
verifier (the ``expected_mapping_hashes`` one-law precedent) — and
the module also owns the ONE pure ``expected_gpi_rows`` shape law
and the frozen ``derived_input_hash`` v1 record. Float arithmetic
never appears in the law path; executor-native conversion happens
only at the worker payload edge. The normative contract is the
frozen R4 text; the qualification adapter bytes (R2-FINAL §0b,
sha256 7084e499b00a973efa764417b7ec075df58acf11fcf4a3a1164c74ae
a358f335) are non-normative transplant evidence.
"""

from __future__ import annotations

import struct
from fractions import Fraction

from soloring.domain.canonical import canonical_hash
from soloring.errors import ErrorCode, SoloRingError

ADAPTER_IDENTITY = "soloring.m17c.adapter.facial_liveportrait"
TRANSLATION_IDENTITY = (
    "soloring-executor-translation-facial-liveportrait/1")

# the frozen Decision-B v1 semantic identity record
DERIVED_INPUT_RECORD_SCHEMA_VERSION = 1
# the derived control-schedule document grammar
CONTROL_SCHEDULE_SCHEMA_VERSION = 1

CONTROL_INPUT_KEY = "performance.controls"
VOCAL_AUDIO_INPUT_KEY = "performance.vocal_audio"


def _execution_refusal(code: ErrorCode, message: str) -> SoloRingError:
    return SoloRingError(code, message, status_code=422)


def _capability_refusal(code: ErrorCode, message: str) -> SoloRingError:
    return SoloRingError(code, message, status_code=409)


def _rational(value, what: str) -> Fraction:
    """Exact ``{num, den}`` → Fraction (the closed rational grammar
    every captured timing coordinate carries)."""
    if not isinstance(value, dict) \
            or set(value) != {"num", "den"} \
            or type(value["num"]) is not int \
            or type(value["den"]) is not int \
            or value["den"] <= 0:
        raise _execution_refusal(
            ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
            f"{what} is not an exact {{num, den}} rational")
    return Fraction(value["num"], value["den"])


def _rat(value: Fraction) -> dict:
    return {"num": value.numerator, "den": value.denominator}


def assert_facial_lane(payload: dict) -> None:
    """§14.7 first-lane gate: the payload must carry facial channels
    only. Any body-domain channel — or any non-FACIAL kind — is
    refused BEFORE Generation publication/queue/submission; body
    authority is never partially consumed or silently discarded."""
    for channel in payload["channels"]:
        if channel["domain"] == "body":
            raise _capability_refusal(
                ErrorCode.PERFORMANCE_EXECUTION_BODY_CHANNEL_UNSUPPORTED,
                f"channel {channel['channel_key']!r} is body-domain — "
                "the first execution package consumes facial channels "
                "only (§14.7); body authority is never partially "
                "consumed")


def assert_supported_kind(performance_kind: str) -> None:
    """The R2-FINAL §0a/E kind gate: the first execution lane
    realizes FACIAL performance only (BODY/BODY_FACIAL authority,
    mapping, and capture stay fully lawful — only this execution
    package refuses them)."""
    if performance_kind != "FACIAL":
        raise _capability_refusal(
            ErrorCode.PERFORMANCE_EXECUTION_KIND_UNSUPPORTED,
            f"performance kind {performance_kind!r} is outside the "
            "first FACIAL-only execution lane (§14.7)")


def step_value(keyframes, t: Fraction, channel_key: str) -> int:
    """Law (a): the most recent keyframe whose exact time is ``<=``
    ``t`` — direct keyframe-list evaluation, no ramp arithmetic.
    Readiness (frozen corollary): a consumed channel with no
    keyframe at or before the sampled time refuses with the typed
    binding error rather than assuming a zero default."""
    chosen = None
    previous = None
    for keyframe in keyframes:
        kt = _rational(keyframe["time_ms"], "keyframe time_ms")
        if previous is not None and kt < previous:
            raise _execution_refusal(
                ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
                f"channel {channel_key!r} keyframes are not in "
                "non-decreasing canonical time order")
        previous = kt
        if kt <= t:
            chosen = keyframe["value"]
        else:
            break
    if chosen is None:
        raise _execution_refusal(
            ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
            f"channel {channel_key!r} has no keyframe at or before "
            f"its first sampled Performance time {t} — execution "
            "refuses rather than assuming a zero default")
    return chosen


def rasterize_segment(
    *,
    channels: list,
    performance_start: Fraction,
    performance_end: Fraction,
    shot_anchor: Fraction,
    fps: Fraction,
    frame_count: int,
) -> list[dict]:
    """Laws (a)+(b): the per-output-frame control schedule for ONE
    captured segment. Frame-left Shot time is ``k · 1000/fps`` as
    an exact Fraction; the frame-left Performance time is
    ``performance_start + (shot_left − shot_anchor)``; a frame is
    active exactly when that time lies inside
    ``[performance_start, performance_end)`` (the §14.6b
    equivalence), and inactive frames sample NOTHING (their
    channel map is empty — the segment renders neutral with
    respect to them)."""
    if performance_start >= performance_end:
        raise _execution_refusal(
            ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
            "captured performance interval is empty or inverted")
    if fps <= 0 or type(frame_count) is not int or frame_count < 1:
        raise _execution_refusal(
            ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
            "rasterization facts are not a lawful picture grid")
    frame_ms = Fraction(1000) / fps
    frames: list[dict] = []
    first_active_checked = set()
    for k in range(frame_count):
        shot_left = k * frame_ms
        perf_left = performance_start + (shot_left - shot_anchor)
        active = performance_start <= perf_left < performance_end
        consumed: dict[str, int] = {}
        if active:
            for channel in channels:
                key = channel["channel_key"]
                if key not in first_active_checked:
                    # readiness fires on the FIRST sampled time of
                    # each consumed channel (step_value enforces it)
                    first_active_checked.add(key)
                consumed[key] = step_value(
                    channel["keyframes"], perf_left, key)
        frames.append({
            "frame": k,
            "shot_left_ms": _rat(shot_left),
            "performance_left_ms": _rat(perf_left),
            "segment_active": active,
            "channels": consumed,
        })
    return frames


def anchor_samples(anchor: Fraction, rate: int) -> int:
    """The frozen anchor-representability refusal: the exact audio
    anchor must sit on the package's sample grid
    (``anchor·rate/1000 ∈ Z``) or execution refuses — the simplest
    fail-closed contract; authority never restricts anchors."""
    scaled = (anchor * rate) / 1000
    if scaled.denominator != 1:
        raise _execution_refusal(
            ErrorCode.PERFORMANCE_EXECUTION_ANCHOR_UNREPRESENTABLE,
            f"audio anchor {anchor} ms is not representable on the "
            f"{rate} Hz sample grid (anchor·rate/1000 ∉ Z)")
    return int(scaled)


def _wave_layout(data: bytes) -> tuple[bytes, int, int, int, int, int]:
    """Validate the retained VP audio with the ONE frozen inspector
    and locate the raw PCM span: returns (fmt-chunk bytes, data
    offset, frame bytes, sample rate, channels, bits)."""
    from soloring.performance.audio_inspection import inspect_wave

    facts = inspect_wave(data)
    pos = 12
    fmt_bytes = None
    data_offset = None
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        (chunk_size,) = struct.unpack_from("<I", data, pos + 4)
        if chunk_id == b"fmt ":
            fmt_bytes = data[pos:pos + 8 + chunk_size]
        elif chunk_id == b"data":
            data_offset = pos + 8
        pos += 8 + chunk_size + (chunk_size & 1)
    if fmt_bytes is None or data_offset is None:  # pragma: no cover
        # inspect_wave already refuses missing fmt/data chunks
        raise _execution_refusal(
            ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
            "retained audio container lacks its fmt/data chunks")
    frame_bytes = (facts["channels"] * facts["bits_per_sample"]) // 8
    return (fmt_bytes, data_offset, frame_bytes,
            facts["sample_rate_hz"], facts["channels"],
            facts["bits_per_sample"])


def materialize_audio_track(
    *,
    wav_bytes: bytes,
    source_start: int,
    source_end_exclusive: int,
    sample_rate_hz: int,
    anchor: Fraction,
    fps: Fraction,
    frame_count: int,
) -> bytes:
    """Law (c): the exact materialized audio track — the retained
    VP samples intersected with the picture window in INTEGER
    sample arithmetic. A negative anchor is NEVER positive leading
    silence: the pre-picture portion of the segment is simply
    absent (picture time 0 begins at source sample ``source_start
    + max(0, −anchor)·rate/1000``); a positive anchor is lawful
    leading silence until the segment enters; the tail past picture
    end is excluded; the remainder past the segment's Shot end is
    silence to picture length."""
    if not 0 <= source_start < source_end_exclusive:
        raise _execution_refusal(
            ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
            "captured vocal source interval is empty or inverted")
    (fmt_bytes, data_offset, frame_bytes, container_rate,
     _channels, _bits) = _wave_layout(wav_bytes)
    if container_rate != sample_rate_hz:
        raise _execution_refusal(
            ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
            f"retained audio container rate {container_rate} != the "
            f"captured binding rate {sample_rate_hz}")
    a = anchor_samples(anchor, sample_rate_hz)
    seg_len = source_end_exclusive - source_start
    # picture length in samples: frame_count · 1000/fps · rate/1000
    picture = int(Fraction(frame_count * sample_rate_hz) / fps)
    # the segment's audible window in TRACK coordinates
    track_start = max(0, a)
    track_end = min(a + seg_len, picture)
    pcm = bytearray()
    if track_end > track_start:
        pcm += b"\x00" * (track_start * frame_bytes)
        audible_from = source_start + max(0, -a)
        audible_frames = track_end - track_start
        begin = data_offset + audible_from * frame_bytes
        pcm += wav_bytes[begin:begin + audible_frames * frame_bytes]
    if len(pcm) < picture * frame_bytes:
        pcm += b"\x00" * (picture * frame_bytes - len(pcm))
    body = fmt_bytes + b"data" + struct.pack("<I", len(pcm)) \
        + bytes(pcm) + (b"\x00" if len(pcm) & 1 else b"")
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body


def control_schedule_document(
    *,
    segment: dict,
    channels: list,
    performance_start: Fraction,
    performance_end: Fraction,
    shot_anchor: Fraction,
    fps: Fraction,
    frame_count: int,
) -> dict:
    """The canonical §10.6 derived control-schedule record: per
    output frame — the frame index, the exact rational frame-left
    Shot AND Performance times, the activity flag, and the
    per-channel consumed values — plus the translation identity and
    the rasterization facts. Deterministic and canonical: identical
    captured inputs produce byte-identical serialized schedules."""
    frames = rasterize_segment(
        channels=channels,
        performance_start=performance_start,
        performance_end=performance_end,
        shot_anchor=shot_anchor,
        fps=fps,
        frame_count=frame_count,
    )
    return {
        "schema_version": CONTROL_SCHEDULE_SCHEMA_VERSION,
        "adapter_identity": ADAPTER_IDENTITY,
        "translation_identity": TRANSLATION_IDENTITY,
        "segment": {
            "shot_revision_segment_position":
                segment["shot_revision_segment_position"],
            "segment_hash": segment["segment_hash"],
            "performance_revision_id":
                segment["performance_revision_id"],
        },
        "rasterization": {"fps": _rat(fps),
                          "frame_count": frame_count},
        "performance_interval": {
            "start": _rat(performance_start),
            "end": _rat(performance_end)},
        "shot_anchor": _rat(shot_anchor),
        "frames": frames,
    }


def derived_input_record(
    *,
    input_key: str,
    position: int,
    artifact_role: str,
    shot_revision_segment_position: int,
    performance_revision_id: str,
    vocal_performance_revision_id,
    binding_hash,
    segment_hash: str,
    translation_identity: str,
    blob_hash: str,
) -> dict:
    """The frozen Decision-B v1 semantic identity record. The
    parent/lifecycle coordinates (generation_id, created_at,
    derived_input_hash itself) are EXCLUDED so duplicate
    Generations over identical captured inputs keep identical
    derived identities."""
    return {
        "schema_version": DERIVED_INPUT_RECORD_SCHEMA_VERSION,
        "input_key": input_key,
        "position": position,
        "artifact_role": artifact_role,
        "shot_revision_segment_position":
            shot_revision_segment_position,
        "performance_revision_id": performance_revision_id,
        "vocal_performance_revision_id": vocal_performance_revision_id,
        "binding_hash": binding_hash,
        "segment_hash": segment_hash,
        "translation_identity": translation_identity,
        "blob_hash": blob_hash,
    }


def derived_input_hash(record: dict) -> str:
    return canonical_hash(record)


def expected_gpi_rows(captured_children, translation_identity: str):
    """The ONE expected-shape law (frozen plan R2-FINAL W5): given
    the captured schema-8 child segments (canonical position
    order), yield the complete expected ``generation_performance_
    inputs`` row shape — exactly ONE ``performance.controls`` row
    per captured segment and, iff the segment is dialogue-bound,
    exactly ONE ``performance.vocal_audio`` row — under the
    D-frozen grouped-key convention (role-named keys, zero-based
    per-group ordinals in captured-segment order). Hash-free by
    design: blob/derived hashes are the byte laws' concern, so the
    SAME law governs shape in the writer, the worker, and
    recovery."""
    controls_position = 0
    vocal_position = 0
    for child in sorted(
            captured_children,
            key=lambda c: c["shot_revision_segment_position"]):
        base = {
            "shot_revision_segment_position":
                child["shot_revision_segment_position"],
            "performance_revision_id":
                child["performance_revision_id"],
            "segment_hash": child["segment_hash"],
            "translation_identity": translation_identity,
        }
        yield {
            **base,
            "input_key": CONTROL_INPUT_KEY,
            "position": controls_position,
            "artifact_role": "performance.controls",
            "vocal_performance_revision_id": None,
            "binding_hash": None,
        }
        controls_position += 1
        if child.get("vocal_performance_revision_id") is not None:
            yield {
                **base,
                "input_key": VOCAL_AUDIO_INPUT_KEY,
                "position": vocal_position,
                "artifact_role": "performance.vocal_audio",
                "vocal_performance_revision_id":
                    child["vocal_performance_revision_id"],
                "binding_hash": child["vocal_binding_hash"],
            }
            vocal_position += 1
