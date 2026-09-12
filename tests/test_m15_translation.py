"""M15 translator v1 proofs (frozen R4 §31.5 M15-TRANS:01-09)."""

from __future__ import annotations

import pytest

from soloring.compatibility.translation import (
    TRANSLATOR_ID,
    TRANSLATOR_VERSION,
    UnsupportedTranslation,
    frame_bridge_supported,
    frame_bridge_translate,
)


def _interp(translation=(0, 0, 0), rotation=(0, 0, 0), schema=1) -> dict:
    return {
        "schema_version": schema,
        "realization_local_to_subject_local": {
            "translation_mm": list(translation),
            "rotation_udeg": list(rotation),
        },
    }


def _translate(source, target):
    return frame_bridge_translate(
        source=source, target=target,
        source_interpretation_hash="a" * 64,
        target_interpretation_hash="b" * 64)


def test_frame_bridge_schema_and_identity():
    """M15-TRANS:01 — versioned translator, canonical schema-1 shape."""
    out = _translate(_interp((5, 0, 0)), _interp((2, 0, 0)))
    assert out["translator_id"] == TRANSLATOR_ID == (
        "soloring.compatibility.realization_local_frame_bridge")
    assert out["translator_version"] == TRANSLATOR_VERSION == 1
    params = out["parameters"]
    assert params["schema_version"] == 1
    assert params["translator"] == {"id": TRANSLATOR_ID, "version": 1}
    assert params["source_local_to_target_local"]["rotation_udeg"] == [
        0, 0, 0]


def test_frame_bridge_integer_equivalence():
    """M15-TRANS:02 — exact shared-subset semantics (§7.3): for signed
    canonical points, subject_from_source(p) == subject_from_target(
    translate(p)) exactly."""
    src, tgt = _interp((7, -3, 12)), _interp((1, 4, -2))
    out = _translate(src, tgt)
    delta = out["parameters"]["source_local_to_target_local"][
        "translation_mm"]
    assert delta == [6, -7, 14]
    for p in [(0, 0, 0), (-1000, 500, 1), (123456, -789, 3)]:
        subject_from_source = [p[i] + src["realization_local_to_subject_local"]
                               ["translation_mm"][i] for i in range(3)]
        translated = [p[i] + delta[i] for i in range(3)]
        subject_from_target = [
            translated[i] + tgt["realization_local_to_subject_local"]
            ["translation_mm"][i] for i in range(3)]
        assert subject_from_source == subject_from_target


def test_rotation_outside_v1_refuses_translation():
    """M15-TRANS:03 — non-identity rotation is outside the subset; never
    approximated."""
    source = _interp((0, 0, 0), rotation=(1, 0, 0))
    assert frame_bridge_supported(source, _interp()) == (
        "rotation_non_identity")
    with pytest.raises(UnsupportedTranslation) as ei:
        _translate(source, _interp())
    assert ei.value.reason == "rotation_non_identity"


def test_translation_parameters_and_output_hash_persisted():
    """M15-TRANS:04 — inspectable canonical evidence with exact hashes."""
    out = _translate(_interp((3, 0, 0)), _interp((1, 0, 0)))
    from soloring.domain.canonical import canonical_hash

    assert out["parameters_hash"] == canonical_hash(out["parameters"])
    assert out["output_hash"] == canonical_hash(out["parameters"])
    assert out["parameters"]["source_interpretation_hash"] == "a" * 64
    assert out["parameters"]["target_interpretation_hash"] == "b" * 64


def test_forged_translator_pin_fails_integrity():
    """M15-TRANS:05 — a mutated parameter dict no longer matches its
    hash; pins are anti-forgery by construction."""
    from soloring.domain.canonical import canonical_hash

    out = _translate(_interp((3, 0, 0)), _interp((1, 0, 0)))
    forged = dict(out["parameters"])
    forged["source_local_to_target_local"]["translation_mm"] = [999, 0, 0]
    assert canonical_hash(forged) != out["parameters_hash"]


def test_translation_never_mutates_source_or_target_revision():
    """M15-TRANS:06 — pure bridge: inputs are never modified."""
    source, target = _interp((5, 1, 1)), _interp((2, 1, 1))
    snapshot = (repr(source), repr(target))
    _translate(source, target)
    assert (repr(source), repr(target)) == snapshot


def test_translation_evidence_retained_when_overall_use_requires_review():
    """M15-TRANS:07 — dimension result controls pins, not the folded
    verdict (retained under REQUIRES_REVIEW is proven end-to-end in the
    evaluator cells; here the retained evidence contract itself)."""
    out = _translate(_interp((5, 0, 0)), _interp((2, 0, 0)))
    assert out["translator_id"] and out["parameters_hash"] and out[
        "output_hash"]


def test_frame_bridge_only_applies_to_a4_consumer_and_mutates_no_authority():
    """M15-TRANS:08 — applicability boundary: the translator emits
    evidence only; it exposes no mutation surface at all."""
    out = _translate(_interp(), _interp())
    assert set(out) == {
        "translator_id", "translator_version", "parameters",
        "parameters_hash", "output_hash"}
    import inspect

    source = inspect.getsource(frame_bridge_translate)
    for forbidden in ("UPDATE ", "INSERT ", "DELETE ", "session", "conn"):
        assert forbidden not in source


def test_frame_bridge_overflow_refuses_without_wrap():
    """M15-TRANS:09 — a delta outside signed 64-bit refuses; never
    wraps."""
    limit = 2 ** 63
    source = _interp((limit, 0, 0))
    target = _interp((-limit, 0, 0))
    assert frame_bridge_supported(source, target) == "translation_overflow"
    with pytest.raises(UnsupportedTranslation) as ei:
        _translate(source, target)
    assert ei.value.reason == "translation_overflow"
    # inside the boundary stays supported
    assert frame_bridge_supported(
        _interp((limit - 1, 0, 0)), _interp((0, 0, 0))) is None
