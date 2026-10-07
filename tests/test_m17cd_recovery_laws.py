"""M17C-D W5 — the completed §13.6 recovery laws (frozen plan
R2-FINAL W5): the ONE expected-shape law (the seven adversarial
GPI shapes), the two byte-level laws re-derived under the shared
§14.6 sampler, the v1 identity-record recomputation, the v5
grammar mirror — and the preserved §12 independence (recovery
passes with the historical reader removed)."""

from __future__ import annotations

import pytest

from tests.test_m17cc_recovery import (
    _insert_gpi, _one, _sql, _stage_with_generation, _verify,
    _verify_refuses,
)

_GPI = "generation_performance_inputs"


def _insert_full(root, gen_id, revision_id, translation):
    _insert_gpi(root, gen_id, revision_id, translation.gpi_rows,
                role="performance.controls",
                key="performance.controls", seg_pos=0)
    _insert_gpi(root, gen_id, revision_id, translation.gpi_rows,
                role="performance.vocal_audio",
                key="performance.vocal_audio", seg_pos=0)
    _insert_gpi(root, gen_id, revision_id, translation.gpi_rows,
                role="performance.controls",
                key="performance.controls", position=1, seg_pos=1)


@pytest.mark.asyncio
async def test_recovery_lawful_schema5_state_green(client, tmp_path):
    root, world, revision_id, gen_id, translation = (
        await _stage_with_generation(client, tmp_path, "d-lawful"))
    _insert_full(root, gen_id, revision_id, translation)
    _verify(root)


@pytest.mark.asyncio
async def test_recovery_seven_expected_shape_adversaries(
        client, tmp_path):
    import sqlite3

    cases = [
        ("missing_controls", "is MISSING",
         lambda root, gen, rev, tr: _sql(root, (
             f"DELETE FROM {_GPI} WHERE generation_id = ? AND "
             "input_key = 'performance.controls' AND position = 0"),
             (gen,))),
        ("missing_vocal_audio", "is MISSING",
         lambda root, gen, rev, tr: _sql(root, (
             f"DELETE FROM {_GPI} WHERE generation_id = ? AND "
             "input_key = 'performance.vocal_audio'"), (gen,))),
        ("extra_row", "not in the expected sibling set",
         lambda root, gen, rev, tr: _insert_gpi(
             root, gen, rev,
             [{**next(r for r in tr.gpi_rows
                      if r["artifact_role"] == "performance.controls"
                      and r["shot_revision_segment_position"] == 0),
               "position": 9}],
             role="performance.controls", key="performance.controls",
             position=9, seg_pos=0)),
        ("duplicate_semantic", "disagrees with the expected shape",
         lambda root, gen, rev, tr: (
             _sql(root, (
                 f"UPDATE {_GPI} SET shot_revision_segment_position = "
                 "0, segment_hash = (SELECT segment_hash FROM "
                 "shot_revision_performance_segments WHERE "
                 "shot_revision_id = ? AND position = 0), "
                 "performance_revision_id = (SELECT "
                 "performance_revision_id FROM "
                 "shot_revision_performance_segments WHERE "
                 "shot_revision_id = ? AND position = 0) "
                 "WHERE generation_id = ? AND input_key = "
                 "'performance.controls' AND position = 1"),
                 (rev, rev, gen)))),
        ("wrong_key", "not in the expected sibling set",
         lambda root, gen, rev, tr: _sql(root, (
             f"UPDATE {_GPI} SET input_key = 'performance:0' "
             "WHERE generation_id = ? AND input_key = "
             "'performance.controls' AND position = 0"), (gen,))),
        ("wrong_position", None,  # DB-pinned (below)
         lambda root, gen, rev, tr: None),
        ("wrong_role", "artifact_role",
         lambda root, gen, rev, tr: _sql(root, (
             f"UPDATE {_GPI} SET artifact_role = "
             "'performance.controls' WHERE generation_id = ? AND "
             "input_key = 'performance.vocal_audio'"), (gen,))),
    ]
    for name, fragment, mutate in cases:
        root, world, revision_id, gen_id, translation = (
            await _stage_with_generation(client, tmp_path, f"d-{name}"))
        _insert_full(root, gen_id, revision_id, translation)
        if name == "wrong_position":
            # duplicate (input_key, position) coordinates are
            # PK-pinned — unreachable by UPDATE/INSERT (IntegrityError),
            # with the verifier's duplicate law as the mirror
            with pytest.raises(sqlite3.IntegrityError):
                _sql(root, (
                    f"UPDATE {_GPI} SET position = 0 WHERE "
                    "generation_id = ? AND input_key = "
                    "'performance.controls' AND position = 1"),
                    (gen_id,))
            continue
        mutate(root, gen_id, revision_id, translation)
        _verify_refuses(root, fragment)


@pytest.mark.asyncio
async def test_recovery_byte_laws_and_identity_record(client, tmp_path):
    import hashlib
    import json as _json
    import shutil

    # tampered derived bytes at a new content address, with the spec
    # coordinate kept consistent — the §14.6 re-derivation refuses
    root, world, revision_id, gen_id, translation = (
        await _stage_with_generation(client, tmp_path, "d-bytes"))
    _insert_full(root, gen_id, revision_id, translation)
    controls = _one(root, (
        f"SELECT blob_hash FROM {_GPI} WHERE generation_id = ? AND "
        "input_key = 'performance.controls' AND position = 0"),
        (gen_id,))
    blob_path = root / "blobs" / "sha256" / controls["blob_hash"][:2] \
        / controls["blob_hash"][2:4] / controls["blob_hash"]
    original = blob_path.read_bytes()
    tampered = original.replace(b'"frame":0', b'"frame":9', 1)
    assert tampered != original
    forged = hashlib.sha256(tampered).hexdigest()
    forged_path = root / "blobs" / "sha256" / forged[:2] \
        / forged[2:4] / forged
    forged_path.parent.mkdir(parents=True, exist_ok=True)
    forged_path.write_bytes(tampered)
    _sql(root, (
        f"UPDATE {_GPI} SET blob_hash = ? WHERE generation_id = ? "
        "AND input_key = 'performance.controls' AND position = 0"),
        (forged, gen_id))
    spec = _json.loads(_one(root, (
        "SELECT workflow_spec_json FROM generations WHERE id = ?"),
        (gen_id,))["workflow_spec_json"])
    spec["performance_execution"]["segments"][0][
        "control_schedule_blob_hash"] = forged
    from soloring.domain.canonical import (
        canonical_hash as _ch, canonical_json_str as _cj,
    )
    _sql(root, (
        "UPDATE generations SET workflow_spec_json = ?, "
        "workflow_spec_hash = ? WHERE id = ?"),
        (_cj(spec), _ch(spec), gen_id))
    _verify_refuses(root, "§14.6 re-derived bytes")

    # tampered identity record hash
    root2, world2, rev2, gen2, tr2 = await _stage_with_generation(
        client, tmp_path, "d-identity")
    _insert_full(root2, gen2, rev2, tr2)
    _sql(root2, (
        f"UPDATE {_GPI} SET derived_input_hash = ? WHERE "
        "generation_id = ? AND input_key = 'performance.controls' "
        "AND position = 0"), ("e" * 64, gen2))
    _verify_refuses(root2, "v1 identity record")

    # a non-v5 spec under a performance-bearing Generation refuses
    root3, world3, rev3, gen3, tr3 = await _stage_with_generation(
        client, tmp_path, "d-spec")
    _insert_full(root3, gen3, rev3, tr3)
    spec3 = _json.loads(_one(root3, (
        "SELECT workflow_spec_json FROM generations WHERE id = ?"),
        (gen3,))["workflow_spec_json"])
    spec3["schema_version"] = 1
    _sql(root3, (
        "UPDATE generations SET workflow_spec_json = ?, "
        "workflow_spec_hash = ? WHERE id = ?"),
        (_cj(spec3), _ch(spec3), gen3))
    _verify_refuses(root3, "not WorkflowSpec schema 5")


@pytest.mark.asyncio
async def test_recovery_independent_of_the_history_reader(
        client, tmp_path, monkeypatch):
    """§12-independence preserved under the completed laws: with the
    historical reader monkeypatched to explode, recovery still
    passes the lawful state — the surfaces agree because they share
    the frozen laws, not because one delegates."""
    import soloring.performance.m17cc_history as history

    def _explode(*args, **kwargs):
        raise AssertionError("the §12 reader must not be consulted")

    monkeypatch.setattr(
        history, "verify_performance_history", _explode)
    root, world, revision_id, gen_id, translation = (
        await _stage_with_generation(client, tmp_path, "d-indep"))
    _insert_full(root, gen_id, revision_id, translation)
    _verify(root)
