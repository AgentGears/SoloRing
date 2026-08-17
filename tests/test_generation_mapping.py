"""GenerationDraft + deterministic input-mapping tests (plan §36, §39, §50.11, §50.13)."""

from __future__ import annotations

import dataclasses
import inspect
import json

import pytest

from soloring.generation.drafts import GenerationDraft
from soloring.generation.enums import GenerationOperation
from soloring.generation.input_mapping import (
    GenerationInputRule,
    ResolvedGenerationInput,
    resolve_generation_inputs,
)

HEX64 = "ab" * 32


def _draft(**overrides) -> GenerationDraft:
    base = dict(
        shot_id="s" * 36,
        shot_revision_id="r" * 36,
        operation=GenerationOperation.GENERATE,
        executor="fake",
        workflow_id="hunyuan_i2v",
        workflow_version=1,
        workflow_template_hash=HEX64,
        manifest_hash=HEX64,
        model=None,
        model_version=None,
        compiled_prompt="a b c",
        negative_prompt=None,
        prompt_compiler_version="1",
        seed=12345,
        parameters_json='{"steps":30}',
        workflow_spec_json='{"schema_version":1}',
        workflow_spec_hash=HEX64,
    )
    base.update(overrides)
    return GenerationDraft(**base)


# --- draft validation (§50.11) ----------------------------------------------


def test_valid_draft_constructs() -> None:
    d = _draft()
    assert d.operation is GenerationOperation.GENERATE
    assert json.loads(d.parameters_json) == {"steps": 30}


def test_draft_is_frozen() -> None:
    d = _draft()
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.compiled_prompt = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    "field,value",
    [
        ("compiled_prompt", ""),
        ("compiled_prompt", "   "),
        ("workflow_id", ""),
        ("prompt_compiler_version", ""),
        ("executor", ""),
    ],
)
def test_draft_rejects_empty_required_strings(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        _draft(**{field: value})


@pytest.mark.parametrize("field", ["workflow_template_hash", "manifest_hash", "workflow_spec_hash"])
def test_draft_rejects_bad_hash_length(field: str) -> None:
    with pytest.raises(ValueError):
        _draft(**{field: "short"})


def test_draft_rejects_invalid_json() -> None:
    with pytest.raises(ValueError):
        _draft(parameters_json="{not json")
    with pytest.raises(ValueError):
        _draft(workflow_spec_json="")


# --- mapping (§50.13) --------------------------------------------------------


def _snap(refs: list[dict]) -> dict:
    return {"schema_version": 1, "intent": {"subject": "x"}, "references": refs}


def _ref(role: str, n: int) -> dict:
    return {
        "asset_id": f"{n:032x}"[:32].ljust(32, "0"),
        "blob_hash": f"{n:064x}"[:64],
        "role": role,
        "position": 0,  # snapshot order re-derived by the mapper
    }


def test_duplicate_input_key_rejected() -> None:
    rules = [
        GenerationInputRule(input_key="reference_image", source_role="reference"),
        GenerationInputRule(input_key="reference_image", source_role="style"),
    ]
    with pytest.raises(ValueError):
        resolve_generation_inputs(_snap([]), rules)


def test_empty_input_key_rejected() -> None:
    with pytest.raises(ValueError):
        resolve_generation_inputs(_snap([]), [GenerationInputRule("", "reference")])


@pytest.mark.parametrize("bad_role", ["", "   ", "x" * 65])
def test_invalid_source_role_rejected(bad_role: str) -> None:
    with pytest.raises(ValueError):
        resolve_generation_inputs(
            _snap([]), [GenerationInputRule("reference_image", bad_role)]
        )


def test_duplicate_source_role_across_input_keys_allowed() -> None:
    refs = [
        {"asset_id": "a", "blob_hash": "b" * 64, "role": "reference", "position": 0},
    ]
    rules = [
        GenerationInputRule(input_key="reference_image", source_role="reference"),
        GenerationInputRule(input_key="character_image", source_role="reference"),
    ]
    out = resolve_generation_inputs(_snap(refs), rules)
    assert len(out) == 2
    assert {r.input_key for r in out} == {"reference_image", "character_image"}
    assert all(r.asset_id == "a" for r in out)


def test_zero_matches_emits_zero_bindings() -> None:
    out = resolve_generation_inputs(_snap([]), [GenerationInputRule("k", "reference")])
    assert out == []


def test_reversed_rule_order_yields_identical_output() -> None:
    refs = [
        {"asset_id": "a1", "blob_hash": "1" * 64, "role": "reference", "position": 0},
        {"asset_id": "a2", "blob_hash": "2" * 64, "role": "character", "position": 0},
    ]
    r1 = GenerationInputRule("character_image", "character")
    r2 = GenerationInputRule("reference_image", "reference")
    forward = resolve_generation_inputs(_snap(refs), [r2, r1])
    reverse = resolve_generation_inputs(_snap(refs), [r1, r2])
    assert forward == reverse
    assert [r.input_key for r in forward] == ["character_image", "reference_image"]
    assert all(r.position == 0 for r in forward)


def test_snapshot_reference_permutations_do_not_affect_mapping() -> None:
    refs = [
        {"asset_id": "a3", "blob_hash": "3" * 64, "role": "reference", "position": 2},
        {"asset_id": "a1", "blob_hash": "1" * 64, "role": "reference", "position": 0},
        {"asset_id": "a2", "blob_hash": "2" * 64, "role": "reference", "position": 1},
    ]
    rules = [GenerationInputRule("reference_image", "reference")]
    out = resolve_generation_inputs(_snap(refs), rules)
    assert [r.asset_id for r in out] == ["a1", "a2", "a3"]
    assert [r.position for r in out] == [0, 1, 2]

    shuffled = [refs[1], refs[2], refs[0]]
    out2 = resolve_generation_inputs(_snap(shuffled), rules)
    assert out2 == out  # input list order is irrelevant


def test_positions_are_zero_based_per_input_key() -> None:
    refs = [
        {"asset_id": "a1", "blob_hash": "1" * 64, "role": "reference", "position": 0},
        {"asset_id": "a2", "blob_hash": "2" * 64, "role": "style", "position": 0},
        {"asset_id": "a3", "blob_hash": "3" * 64, "role": "reference", "position": 1},
    ]
    rules = [
        GenerationInputRule("reference_image", "reference"),
        GenerationInputRule("style_image", "style"),
    ]
    out = resolve_generation_inputs(_snap(refs), rules)
    by_key: dict[str, list[ResolvedGenerationInput]] = {}
    for r in out:
        by_key.setdefault(r.input_key, []).append(r)
    assert [r.asset_id for r in by_key["reference_image"]] == ["a1", "a3"]
    assert [r.position for r in by_key["reference_image"]] == [0, 1]
    assert [r.position for r in by_key["style_image"]] == [0]


def test_mapping_is_pure_and_session_free() -> None:
    """The mapper must not accept (or transitively use) any DB/session handle."""
    sig = inspect.signature(resolve_generation_inputs)
    params = list(sig.parameters.values())
    assert len(params) == 2
    for p in params:
        name = p.annotation if isinstance(p.annotation, str) else getattr(p.annotation, "__name__", "")
        assert "session" not in str(name).lower()
        assert "engine" not in str(name).lower()
