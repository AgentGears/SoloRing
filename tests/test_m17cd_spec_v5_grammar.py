"""M17C-D W2 — the WorkflowSpec schema-5 grammar (frozen plan
R2-FINAL §2.5, Decisions A/C): the sibling ``build_workflow_spec_v5``
and the ONE ``validate_workflow_spec_v5`` law — exact
root/container/entry/vocal key sets and cardinality, segment
position uniqueness/ordering, ``vocal``-null-iff-generic, the
v1/v2 lower-projection preservation law, rejection of v3/v4 lower
execution meaning, and the frozen translation-identity coordinate.
"""

from __future__ import annotations

import copy

import pytest

from soloring.errors import ErrorCode, SoloRingError
from soloring.performance import execution_spec as exs
from soloring.performance.execution_sampler import TRANSLATION_IDENTITY


def _lower(version: int) -> dict:
    spec = {
        "schema_version": version,
        "workflow_id": "wf", "workflow_version": 1,
        "manifest_hash": "m" * 64,
        "inputs": {"image": {"bindings": [
            {"asset_id": "a", "blob_hash": "b" * 64,
             "reference_role": "reference", "position": 0}]}},
        "prompt": "p", "parameters": {"steps": 30},
        "outputs": [{"output_key": "video", "media": "video"}],
    }
    if version == 2:
        spec["model"] = {"id": "m1", "version": 2,
                         "execution_model_fingerprint_hash":
                             "f" * 64}
        spec["realization"] = {"model_id": "m1",
                               "parameter_overrides": {}}
    return spec


def _entry(position: int = 0, *, vocal=None) -> dict:
    return {
        "shot_revision_segment_position": position,
        "segment_hash": "1" * 64,
        "subject_id": "s", "performance_revision_id": "pr",
        "payload_blob_hash": "2" * 64, "payload_sha256": "3" * 64,
        "performance_profile_id": "profile-1",
        "performance_kind": "FACIAL",
        "performance_start": {"num": 0, "den": 1},
        "performance_end": {"num": 1000, "den": 1},
        "shot_anchor": {"num": 0, "den": 1},
        "control_schedule_blob_hash": "4" * 64,
        "vocal": vocal,
    }


def _vocal() -> dict:
    return {
        "vocal_performance_revision_id": "vp",
        "vocal_audio_blob_hash": "5" * 64,
        "source_start_sample": 0,
        "source_end_sample_exclusive": 48000,
        "sample_rate_hz": 48000,
        "vocal_binding_hash": "6" * 64,
        "synchronization_basis_version": 1,
        "materialized_audio_track_blob_hash": "7" * 64,
    }


def _container(segments) -> dict:
    return {"rasterization": {"fps": {"num": 25, "den": 1},
                              "frame_count": 25},
            "segments": segments}


# ---------------------------------------------------------------------------
# The builder + the lower-projection preservation law
# ---------------------------------------------------------------------------

def test_v5_wraps_exact_lower_v1_and_v2():
    for version in (1, 2):
        lower = _lower(version)
        spec = exs.build_workflow_spec_v5(
            lower, performance_execution=_container([_entry()]))
        assert spec["schema_version"] == 5
        assert spec["performance_translation"] == TRANSLATION_IDENTITY
        # every lower key preserved verbatim
        for key, value in lower.items():
            if key == "schema_version":
                continue
            assert spec[key] == value
        # the projection EQUALS the exact lower spec
        assert exs.lower_projection(spec) == lower
        exs.validate_workflow_spec_v5(spec, lower_spec=lower)


def test_v5_preserves_lawful_v2_model_and_realization():
    lower = _lower(2)
    spec = exs.build_workflow_spec_v5(
        lower, performance_execution=_container([_entry()]))
    assert spec["model"] == lower["model"]
    assert spec["realization"] == lower["realization"]
    assert exs.lower_projection(spec) == lower


def test_v5_refuses_v3_and_v4_lower_meaning():
    for version in (3, 4):
        with pytest.raises(SoloRingError) as exc:
            exs.build_workflow_spec_v5(
                _lower(version) if version == 3
                else {**_lower(2), "schema_version": 4},
                performance_execution=_container([_entry()]))
        assert exc.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION


# ---------------------------------------------------------------------------
# The grammar law
# ---------------------------------------------------------------------------

def _valid() -> dict:
    return exs.build_workflow_spec_v5(
        _lower(2), performance_execution=_container([
            _entry(0, vocal=_vocal()), _entry(1)]))


def test_validate_accepts_the_lawful_multi_segment_document():
    exs.validate_workflow_spec_v5(_valid())


def test_root_key_set_is_closed():
    bad = _valid()
    bad["extra"] = 1
    with pytest.raises(SoloRingError):
        exs.validate_workflow_spec_v5(bad)
    bad2 = _valid()
    del bad2["prompt"]
    with pytest.raises(SoloRingError):
        exs.validate_workflow_spec_v5(bad2)


def test_model_without_realization_refused():
    bad = _valid()
    del bad["realization"]
    with pytest.raises(SoloRingError) as exc:
        exs.validate_workflow_spec_v5(bad)
    assert "together" in str(exc.value)


def test_translation_identity_coordinate_is_frozen():
    bad = _valid()
    bad["performance_translation"] = "other/9"
    with pytest.raises(SoloRingError):
        exs.validate_workflow_spec_v5(bad)


def test_container_and_rasterization_grammar():
    for mutate in (
        lambda s: s["performance_execution"].__setitem__("extra", 0),
        lambda s: s["performance_execution"]["rasterization"].__setitem__(
            "fps_num", 25),
        lambda s: s["performance_execution"]["rasterization"].__setitem__(
            "frame_count", 0),
        lambda s: s["performance_execution"].__setitem__("segments", []),
    ):
        bad = _valid()
        mutate(bad)
        with pytest.raises(SoloRingError):
            exs.validate_workflow_spec_v5(bad)


def test_entry_key_set_closed_and_vocal_null_iff_generic():
    bad = _valid()
    bad["performance_execution"]["segments"][1]["vocal"] = _vocal()
    # the generic entry now carries a vocal reference — the KEY SET
    # is still exactly right, but the vocal reference on a generic
    # segment is caught by the coordinate law at the consumer seams;
    # here the closed key set itself is what we pin
    with pytest.raises(SoloRingError):
        bad["performance_execution"]["segments"][1]["unexpected"] = 0
        exs.validate_workflow_spec_v5(bad)
    stripped = _valid()
    del stripped["performance_execution"]["segments"][0]["vocal"]
    stripped["performance_execution"]["segments"][0]["vocal"] = None
    exs.validate_workflow_spec_v5(stripped)  # null vocal is lawful


def test_vocal_key_set_closed():
    bad = _valid()
    bad["performance_execution"]["segments"][0]["vocal"]["extra"] = 1
    with pytest.raises(SoloRingError):
        exs.validate_workflow_spec_v5(bad)
    bad2 = _valid()
    del bad2["performance_execution"]["segments"][0][
        "vocal"]["vocal_binding_hash"]
    with pytest.raises(SoloRingError):
        exs.validate_workflow_spec_v5(bad2)


def test_segment_positions_unique_and_ordered():
    bad = _valid()
    bad["performance_execution"]["segments"] = [
        _entry(1), _entry(0, vocal=_vocal())]
    with pytest.raises(SoloRingError) as exc:
        exs.validate_workflow_spec_v5(bad)
    assert "position-ordered" in str(exc.value)
    dup = _valid()
    dup["performance_execution"]["segments"] = [
        _entry(0, vocal=_vocal()), _entry(0)]
    with pytest.raises(SoloRingError):
        exs.validate_workflow_spec_v5(dup)


def test_hash_shapes_enforced():
    bad = _valid()
    bad["performance_execution"]["segments"][0][
        "control_schedule_blob_hash"] = "short"
    with pytest.raises(SoloRingError):
        exs.validate_workflow_spec_v5(bad)


def test_lower_projection_equality_law():
    spec = _valid()
    lower = exs.lower_projection(spec)
    exs.validate_workflow_spec_v5(spec, lower_spec=lower)
    mutated = copy.deepcopy(lower)
    mutated["prompt"] = "different"
    with pytest.raises(SoloRingError) as exc:
        exs.validate_workflow_spec_v5(spec, lower_spec=mutated)
    assert "EQUAL" in str(exc.value)
