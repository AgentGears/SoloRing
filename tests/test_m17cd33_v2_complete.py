"""M17C-D FPR33-03/04 — the complete v2 reconstruction + type-exact
discriminators: the ENTIRE RealizationSpec compared against the
retained-facts reconstruction (nested model + fingerprint,
visual-reference-pack identity, channels, omitted-optionals — never
seeded from the projection), re-sign adversaries beyond
parameter_overrides, and the type-exact synchronization-basis law.
"""

from __future__ import annotations

import pytest

from soloring.errors import SoloRingError
from soloring.performance.execution_spec import compare_lower_v2


class _Profile:
    """The typed-API stand-in mirroring the fields the law reads."""

    class _Model:
        id = "m1"
        version = 2

    class _Channel:
        def __init__(self, input_key):
            self.input_key = input_key

    model = _Model()
    profile_id = "soloring-realization/1"
    profile_version = 1
    parameter_overrides = {"cfg": 1.0}
    channels = {
        "reference.depth": _Channel("reference_image"),
        "reference.detail": _Channel("reference_detail"),
    }


class _Gen(dict):
    model = "m1"
    model_version = 2
    realization_profile_hash = "a" * 64
    visual_reference_pack_hash = "b" * 64

    def __init__(self):
        super().__init__(
            model="m1", model_version=2,
            realization_profile_hash="a" * 64,
            visual_reference_pack_hash="b" * 64,
            manifest_hash="8" * 64,
            compiled_prompt="p",
            parameters_json='{"cfg": 1.0}')


_INPUT_ROWS = [
    {"input_key": "reference_image", "position": 0,
     "asset_id": "as", "blob_hash": "c" * 64,
     "reference_role": "reference"},
]


def _expected():
    from soloring.performance.execution_spec import (
        expected_lower_from_retained,
    )

    return expected_lower_from_retained(
        _Gen(), _INPUT_ROWS, None if False else _MANIFEST,
        v2_profile=_Profile(),
        v2_model_fingerprint_hash="d" * 64)


class _Manifest:
    workflow_id = "w"
    version = 1

    class _Out:
        kind = "video"
        expected_count = 1
        accepted_media_types = None

    outputs = {"video": _Out()}


_MANIFEST = _Manifest()


def test_complete_reconstruction_shape():
    expected = _expected()
    realization = expected["realization"]
    # the COMPLETE RealizationSpec coordinates are reconstructed
    assert set(realization) == {
        "schema_version", "profile", "model",
        "visual_reference_pack_hash", "parameter_overrides",
        "channels", "omitted_optional"}
    assert realization["model"]["execution_model_fingerprint_hash"] \
        == "d" * 64
    assert realization["visual_reference_pack_hash"] == "b" * 64
    # the bound channel carries the retained input; the unbound one
    # is omitted-optional
    assert [c["channel"] for c in realization["channels"]] == [
        "reference.depth"]
    assert [o["facet_key"]
            for o in realization["omitted_optional"]] == [
        "reference.detail"]


def _projection():
    import copy

    return copy.deepcopy(_expected())


def test_resign_adversaries_beyond_overrides():
    compare_lower_v2(_projection(), _expected(), "unit")

    # nested realization.model fingerprint tamper
    bad = _projection()
    bad["realization"]["model"][
        "execution_model_fingerprint_hash"] = "e" * 64
    with pytest.raises(SoloRingError) as exc:
        compare_lower_v2(bad, _expected(), "unit")
    assert "model identity" in exc.value.message

    # visual-reference-pack tamper
    bad2 = _projection()
    bad2["realization"][
        "visual_reference_pack_hash"] = "f" * 64
    with pytest.raises(SoloRingError) as exc2:
        compare_lower_v2(bad2, _expected(), "unit")
    assert "visual_reference_pack_hash" in exc2.value.message

    # channels tamper (a forged binding)
    bad3 = _projection()
    bad3["realization"]["channels"][0]["bindings"].append(
        {"asset_id": "forged", "blob_hash": "0" * 64,
         "position": 1})
    with pytest.raises(SoloRingError) as exc3:
        compare_lower_v2(bad3, _expected(), "unit")
    assert "channels" in exc3.value.message

    # omitted_optional tamper (hiding the unbound channel)
    bad4 = _projection()
    bad4["realization"]["omitted_optional"] = []
    with pytest.raises(SoloRingError):
        compare_lower_v2(bad4, _expected(), "unit")


def test_type_exact_sync_basis():
    """FPR33-04: the frozen discriminator accepts ONLY the actual
    non-bool integer 1 — JSON true, 1.0, and strings all refuse."""
    from soloring.errors import ErrorCode
    from soloring.performance.execution_spec import (
        validate_workflow_spec_v5,
    )

    spec = _projection()
    spec["schema_version"] = 5
    spec["performance_translation"] = "soloring-executor-translation-facial-liveportrait/1"
    spec["performance_execution"] = _container()

    for bad_value in (True, 1.0, "1", 2, None, 0):
        spec["performance_execution"]["segments"][0]["vocal"][
            "synchronization_basis_version"] = bad_value
        with pytest.raises(SoloRingError) as exc:
            validate_workflow_spec_v5(
                spec, captured_children=[_child()])
        assert "synchronization_basis_version" in exc.value.message
    # the lawful value passes the coordinate (fails later only on
    # missing captured children — not on this law)
    spec["performance_execution"]["segments"][0]["vocal"][
        "synchronization_basis_version"] = 1
    # the lawful exact integer passes the grounded validation
    validate_workflow_spec_v5(spec, captured_children=[_child()])


def _container():
    vocal = {
        "vocal_performance_revision_id": "vp",
        "vocal_audio_blob_hash": "1" * 64,
        "source_start_sample": 0,
        "source_end_sample_exclusive": 48000,
        "sample_rate_hz": 48000,
        "vocal_binding_hash": "2" * 64,
        "synchronization_basis_version": 1,
        "materialized_audio_track_blob_hash": "3" * 64,
    }
    return {
        "rasterization": {"fps": {"num": 25, "den": 1},
                          "frame_count": 25},
        "segments": [{
            "shot_revision_segment_position": 0,
            "segment_hash": "4" * 64,
            "subject_id": "s",
            "performance_revision_id": "pr",
            "payload_blob_hash": "5" * 64,
            "payload_sha256": "6" * 64,
            "performance_profile_id": "profile-1",
            "performance_kind": "FACIAL",
            "performance_start": {"num": 0, "den": 1},
            "performance_end": {"num": 1000, "den": 1},
            "shot_anchor": {"num": 0, "den": 1},
            "control_schedule_blob_hash": "7" * 64,
            "vocal": vocal,
        }],
    }


def _child():
    class _C(dict):
        def keys(self):
            return ["shot_revision_segment_position",
                    "position", "performance_revision_id",
                    "segment_hash", "subject_id",
                    "performance_payload_blob_hash",
                    "performance_payload_sha256",
                    "performance_profile_id",
                    "performance_kind",
                    "performance_start_num",
                    "performance_start_den",
                    "performance_end_num", "performance_end_den",
                    "shot_anchor_num", "shot_anchor_den",
                    "vocal_performance_revision_id",
                    "vocal_binding_hash",
                    "source_start_sample",
                    "source_end_sample_exclusive",
                    "sample_rate_hz"]

        def __getitem__(self, key):
            values = {
                "shot_revision_segment_position": 0,
                "position": 0,
                "performance_revision_id": "pr",
                "segment_hash": "4" * 64,
                "subject_id": "s",
                "performance_payload_blob_hash": "5" * 64,
                "performance_payload_sha256": "6" * 64,
                "performance_profile_id": "profile-1",
                "performance_kind": "FACIAL",
                "performance_start_num": 0,
                "performance_start_den": 1,
                "performance_end_num": 1000,
                "performance_end_den": 1,
                "shot_anchor_num": 0,
                "shot_anchor_den": 1,
                "vocal_performance_revision_id": "vp",
                "vocal_binding_hash": "2" * 64,
                "source_start_sample": 0,
                "source_end_sample_exclusive": 48000,
                "sample_rate_hz": 48000,
            }
            return values[key]

    return _C()
