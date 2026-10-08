"""M17C-D W1 — the §14.6 sampler laws (frozen plan R2-FINAL).

The decisive exactness battery for the ONE shared
``soloring.performance.execution_sampler``: step sampling at
non-grid keyframes (law a), segment activity clipping (law b),
the worked −250 ms / 48 kHz J-cut scenario end-to-end (schedule +
audio bytes against hand-computed integers), the L-cut tail
silence, the anchor-representability / channel-readiness / kind /
body-channel refusals, the Fraction-only law path, and the frozen
expected-GPI-shape + v1 identity-record laws.
"""

from __future__ import annotations

import inspect
from fractions import Fraction

import pytest

from soloring.errors import ErrorCode, SoloRingError
from soloring.performance import execution_sampler as es


def _kf(num, den, value):
    return {"time_ms": {"num": num, "den": den}, "value": value,
            "provenance": {"kind": "AUTHORED",
                           "source_alignment_id": None}}


def _wav(samples: list[int], rate: int = 48000,
         channels: int = 1, bits: int = 16) -> bytes:
    import struct

    if bits == 16:
        pcm = b"".join(struct.pack("<h", s) for s in samples)
    else:
        pcm = bytes(samples)
    frame_bytes = channels * bits // 8
    fmt = struct.pack("<HHIIHH", 1, channels, rate,
                      rate * frame_bytes, frame_bytes, bits)
    body = (b"fmt " + struct.pack("<I", len(fmt)) + fmt
            + b"data" + struct.pack("<I", len(pcm)) + pcm)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body


# ---------------------------------------------------------------------------
# Law (a): exact step sampling, non-grid keyframes, readiness
# ---------------------------------------------------------------------------

def test_step_value_consumes_most_recent_keyframe_at_or_before():
    kfs = [_kf(0, 1, 0), _kf(255, 1, 7), _kf(290, 1, 9)]
    assert es.step_value(kfs, Fraction(0), "c") == 0
    assert es.step_value(kfs, Fraction(250), "c") == 0   # 255 > 250
    assert es.step_value(kfs, Fraction(255), "c") == 7   # at it
    assert es.step_value(kfs, Fraction(289, 1), "c") == 7
    assert es.step_value(kfs, Fraction(290), "c") == 9


def test_step_value_non_grid_keyframe_takes_effect_next_frame_left():
    # the frame-left grid is 40 ms; a keyframe at 255 ms (non-grid)
    # takes effect at the FIRST frame-left time after it (290 ms)
    kfs = [_kf(0, 1, 0), _kf(255, 1, 7)]
    assert es.step_value(kfs, Fraction(250), "c") == 0
    assert es.step_value(kfs, Fraction(290), "c") == 7


def test_step_value_readiness_refuses_no_keyframe_at_or_before():
    with pytest.raises(SoloRingError) as exc:
        es.step_value([_kf(300, 1, 1)], Fraction(250), "smile")
    assert exc.value.code == \
        ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID


def test_step_value_refuses_unordered_keyframes():
    kfs = [_kf(100, 1, 1), _kf(50, 1, 2)]
    with pytest.raises(SoloRingError) as exc:
        es.step_value(kfs, Fraction(200), "c")
    assert exc.value.code == \
        ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID


# ---------------------------------------------------------------------------
# Law (b): the activity window
# ---------------------------------------------------------------------------

def test_rasterize_activity_window_exact():
    frames = es.rasterize_segment(
        channels=[{"channel_key": "smile",
                   "keyframes": [_kf(0, 1, 3)]}],
        performance_start=Fraction(0),
        performance_end=Fraction(2550),
        shot_anchor=Fraction(-250),
        fps=Fraction(25),
        frame_count=75)
    # shot window [-250, 2300): frame-left 40k active for k <= 57
    assert [f["segment_active"] for f in frames[:58]] == [True] * 58
    assert [f["segment_active"] for f in frames[58:]] == [False] * 17
    # inactive frames sample NOTHING (empty channel map)
    assert all(f["channels"] == {} for f in frames[58:])
    assert all(f["channels"] == {"smile": 3} for f in frames[:58])
    # exact rational frame times: frame 0 shot-left 0, perf-left 250
    assert frames[0]["shot_left_ms"] == {"num": 0, "den": 1}
    assert frames[0]["performance_left_ms"] == {"num": 250, "den": 1}
    assert frames[1]["shot_left_ms"] == {"num": 40, "den": 1}


def test_rasterize_refuses_inverted_interval_and_bad_grid():
    for kwargs in (
        dict(performance_start=Fraction(5),
             performance_end=Fraction(5)),
        dict(performance_start=Fraction(5),
             performance_end=Fraction(1)),
    ):
        with pytest.raises(SoloRingError) as exc:
            es.rasterize_segment(
                channels=[{"channel_key": "smile",
                           "keyframes": [_kf(0, 1, 0)]}],
                shot_anchor=Fraction(0), fps=Fraction(25),
                frame_count=10, **kwargs)
        assert exc.value.code == \
            ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID


# ---------------------------------------------------------------------------
# The worked J-cut scenario (plan §16 Scenario 2): anchor −250 ms,
# 48 kHz, source [48000, 170400), picture 3000 ms — hand-computed
# ---------------------------------------------------------------------------

def _worked_world():
    return dict(
        performance_start=Fraction(0),
        performance_end=Fraction(2550),
        shot_anchor=Fraction(-250),
        fps=Fraction(25),
        frame_count=75,
    )


def test_worked_jcut_schedule_values():
    kw = _worked_world()
    frames = es.rasterize_segment(
        channels=[{"channel_key": "smile",
                   "keyframes": [_kf(0, 1, 0), _kf(255, 1, 7)]}],
        **kw)
    # perf-left times run 250, 290, ...; the 255 ms keyframe takes
    # effect at frame 1 (perf-left 290)
    assert frames[0]["channels"] == {"smile": 0}
    assert frames[1]["channels"] == {"smile": 7}
    assert frames[57]["shot_left_ms"] == {"num": 2280, "den": 1}
    assert frames[57]["segment_active"] is True
    assert frames[58]["segment_active"] is False


def test_worked_jcut_audio_bytes_hand_computed():
    # source samples i -> i % 29000 (int16-safe, position-unique);
    # audible source span starts at 48000 + 12000 = 57600
    # (picture 0), runs to source end 170400 → 110400 audible
    # frames = 2300 ms, then zeros to 144000 samples (3000 ms)
    samples = [i % 29000 for i in range(170400)]
    wav = _wav(samples)
    track = es.materialize_audio_track(
        wav_bytes=wav,
        source_start=48000,
        source_end_exclusive=170400,
        sample_rate_hz=48000,
        anchor=Fraction(-250),
        fps=Fraction(25),
        frame_count=75)
    import struct

    from soloring.performance.audio_inspection import inspect_wave

    facts = inspect_wave(track)
    assert facts["sample_frame_count"] == 144000
    assert facts["sample_rate_hz"] == 48000
    # pcm span: locate data chunk
    pos = 12
    data_offset = None
    while pos + 8 <= len(track):
        (size,) = struct.unpack_from("<I", track, pos + 4)
        if track[pos:pos + 4] == b"data":
            data_offset = pos + 8
            break
        pos += 8 + size + (size & 1)
    def s(i):
        (v,) = struct.unpack_from("<h", track, data_offset + 2 * i)
        return v
    # anchor −250 ms at 48 kHz: picture 0 = source sample
    # 48000 + 250·48 = 60000; audible span [60000, 170400) =
    # 110400 frames = 2300 ms; zeros to 144000 samples (3000 ms)
    assert s(0) == 60000 % 29000     # picture 0 = source sample 60000
    assert s(1) == 60001 % 29000
    assert s(110399) == 170399 % 29000   # last audible = source 170399
    assert s(110400) == 0           # [2300, 3000) ms is silence
    assert s(143999) == 0


def test_lcut_positive_anchor_leading_and_tail_silence():
    # anchor +500 ms: lawful leading silence until the segment
    # enters at track sample 24000; tail silence to picture length
    samples = [i % 29000 for i in range(48000)]
    wav = _wav(samples)
    track = es.materialize_audio_track(
        wav_bytes=wav,
        source_start=0,
        source_end_exclusive=48000,
        sample_rate_hz=48000,
        anchor=Fraction(500),
        fps=Fraction(25),
        frame_count=100)          # 4000 ms picture = 192000 samples
    import struct

    pos, data_offset = 12, None
    while pos + 8 <= len(track):
        (size,) = struct.unpack_from("<I", track, pos + 4)
        if track[pos:pos + 4] == b"data":
            data_offset = pos + 8
            break
        pos += 8 + size + (size & 1)
    def s(i):
        (v,) = struct.unpack_from("<h", track, data_offset + 2 * i)
        return v
    assert s(23999) == 0
    assert s(24000) == 0 % 29000
    assert s(71999) == 47999 % 29000
    assert s(72000) == 0
    assert s(191999) == 0


def test_audio_tail_past_picture_end_excluded():
    # the segment extends past picture end: track stops at picture
    samples = [i % 29000 for i in range(96000)]
    track = es.materialize_audio_track(
        wav_bytes=_wav(samples),
        source_start=0,
        source_end_exclusive=96000,
        sample_rate_hz=48000,
        anchor=Fraction(-250),
        fps=Fraction(25),
        frame_count=50)           # 2000 ms picture = 96000 samples
    from soloring.performance.audio_inspection import inspect_wave

    assert inspect_wave(track)["sample_frame_count"] == 96000


def test_anchor_representability_refusal():
    with pytest.raises(SoloRingError) as exc:
        es.anchor_samples(Fraction(1, 7), 48000)
    assert exc.value.code == \
        ErrorCode.PERFORMANCE_EXECUTION_ANCHOR_UNREPRESENTABLE
    # representable anchors: -250 ms and +1/3 ms at 48 kHz
    assert es.anchor_samples(Fraction(-250), 48000) == -12000
    assert es.anchor_samples(Fraction(1, 3), 48000) == 16


def test_audio_rate_disagreement_refuses():
    with pytest.raises(SoloRingError) as exc:
        es.materialize_audio_track(
            wav_bytes=_wav([0, 0, 0, 0], rate=44100),
            source_start=0, source_end_exclusive=4,
            sample_rate_hz=48000,
            anchor=Fraction(0), fps=Fraction(25), frame_count=4)
    assert exc.value.code == \
        ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID


# ---------------------------------------------------------------------------
# §14.7 FACIAL-only lane refusals
# ---------------------------------------------------------------------------

def test_kind_gate_refuses_non_facial():
    with pytest.raises(SoloRingError) as exc:
        es.assert_supported_kind("BODY")
    assert exc.value.code == \
        ErrorCode.PERFORMANCE_EXECUTION_KIND_UNSUPPORTED
    with pytest.raises(SoloRingError):
        es.assert_supported_kind("BODY_FACIAL")
    es.assert_supported_kind("FACIAL")  # the lawful lane


def test_body_channel_gate_refuses_body_domain():
    payload = {"channels": [
        {"channel_key": "face.articulation.smile_udeg",
         "domain": "face"},
        {"channel_key": "body.pose.head_yaw_udeg",
         "domain": "body"},
    ]}
    with pytest.raises(SoloRingError) as exc:
        es.assert_facial_lane(payload)
    assert exc.value.code == \
        ErrorCode.PERFORMANCE_EXECUTION_BODY_CHANNEL_UNSUPPORTED
    es.assert_facial_lane(
        {"channels": [{"channel_key": "smile", "domain": "face"}]})


# ---------------------------------------------------------------------------
# The Fraction-only law path (statically grep-able)
# ---------------------------------------------------------------------------

def test_no_float_construction_in_the_law_module():
    src = inspect.getsource(es)
    assert "float(" not in src, \
        "the §14.6 law path must contain no float construction"
    for token in ("round(", "math.", "numpy"):
        assert token not in src


# ---------------------------------------------------------------------------
# The canonical derived documents + the frozen identity laws
# ---------------------------------------------------------------------------

def test_control_schedule_document_deterministic_and_canonical():
    segment = {"shot_revision_segment_position": 0,
               "segment_hash": "a" * 64,
               "performance_revision_id": "pr-1"}
    doc = es.control_schedule_document(
        segment=segment,
        channels=[{"channel_key": "smile",
                   "keyframes": [_kf(0, 1, 1)]}],
        performance_start=Fraction(0),
        performance_end=Fraction(1000),
        shot_anchor=Fraction(0),
        fps=Fraction(25),
        frame_count=25)
    assert doc["translation_identity"] == es.TRANSLATION_IDENTITY
    assert doc["adapter_identity"] == es.ADAPTER_IDENTITY
    assert doc["rasterization"]["fps"] == {"num": 25, "den": 1}
    assert len(doc["frames"]) == 25
    from soloring.domain.canonical import (
        canonical_hash, canonical_json_str,
    )
    again = es.control_schedule_document(
        segment=segment,
        channels=[{"channel_key": "smile",
                   "keyframes": [_kf(0, 1, 1)]}],
        performance_start=Fraction(0),
        performance_end=Fraction(1000),
        shot_anchor=Fraction(0),
        fps=Fraction(25),
        frame_count=25)
    assert canonical_json_str(doc) == canonical_json_str(again)
    assert canonical_hash(doc) == canonical_hash(again)


def test_derived_input_record_excludes_lifecycle_coordinates():
    base = dict(
        input_key="performance.controls", position=0,
        artifact_role="performance.controls",
        shot_revision_segment_position=0,
        performance_revision_id="pr-1",
        vocal_performance_revision_id=None, binding_hash=None,
        segment_hash="b" * 64,
        translation_identity=es.TRANSLATION_IDENTITY,
        blob_hash="c" * 64)
    record = es.derived_input_record(**base)
    assert set(record) == {
        "schema_version", "input_key", "position", "artifact_role",
        "shot_revision_segment_position", "performance_revision_id",
        "vocal_performance_revision_id", "binding_hash",
        "segment_hash", "translation_identity", "blob_hash"}
    # generation_id / created_at / derived_input_hash never appear
    h1 = es.derived_input_hash(record)
    assert h1 == es.derived_input_hash(
        es.derived_input_record(**base))
    changed = dict(base, blob_hash="d" * 64)
    assert es.derived_input_hash(
        es.derived_input_record(**changed)) != h1


def test_expected_gpi_rows_cardinality_and_grouped_keys():
    children = [
        {"shot_revision_segment_position": 0,
         "performance_revision_id": "pr-a", "segment_hash": "1" * 64,
         "vocal_performance_revision_id": "vp-a",
         "vocal_binding_hash": "9" * 64},
        {"shot_revision_segment_position": 1,
         "performance_revision_id": "pr-b", "segment_hash": "2" * 64,
         "vocal_performance_revision_id": None,
         "vocal_binding_hash": None},
    ]
    rows = list(es.expected_gpi_rows(children, es.TRANSLATION_IDENTITY))
    assert [(r["input_key"], r["position"],
             r["shot_revision_segment_position"]) for r in rows] == [
        ("performance.controls", 0, 0),
        ("performance.vocal_audio", 0, 0),
        ("performance.controls", 1, 1),
    ]
    controls = [r for r in rows
                if r["artifact_role"] == "performance.controls"]
    vocals = [r for r in rows
              if r["artifact_role"] == "performance.vocal_audio"]
    assert len(controls) == 2 and len(vocals) == 1
    assert vocals[0]["vocal_performance_revision_id"] == "vp-a"
    assert vocals[0]["binding_hash"] == "9" * 64
    assert all(r["vocal_performance_revision_id"] is None
               and r["binding_hash"] is None for r in controls)
    assert all(r["translation_identity"] == es.TRANSLATION_IDENTITY
               for r in rows)
    # unsorted input yields the same canonical order
    shuffled = list(reversed(children))
    assert [
        (r["input_key"], r["position"]) for r in es.expected_gpi_rows(
            shuffled, es.TRANSLATION_IDENTITY)
    ] == [(r["input_key"], r["position"]) for r in rows]
