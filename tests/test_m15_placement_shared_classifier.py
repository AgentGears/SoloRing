"""M15A shared-classifier proofs (frozen R5 §31.1 M15-BASE:08/09).

BASE:08 — one pure/no-I/O product-code owner of placement
classification; both published M13 and M15 working-state call it.

BASE:09 — the R5 M13 refactor is behavior-identical to the exact
pinned M14 predecessor over the frozen case matrix: all reachable
closed §12 issue codes, clean A6/A4, multi-target, transform cases,
and the working-relevant world-context multiplicity cases (proved
directly against the shared classifier).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import uuid
from pathlib import Path

from sqlalchemy import text

from soloring.domain.canonical import canonical_json_str
from tests.m13_seed import make_composition, mint, publish, seed_base
from tests.m13_seed import seed_second_revision
from tests.test_m13_binding import _adopt, _approved_world, _interpretation

REPO = Path(__file__).resolve().parents[1]
M14_COMMIT = "89298e793c651e9e8b9164912c76e3595867a60a"


def test_m13_and_m15_use_one_shared_placement_classifier():
    """M15-BASE:08 — one pure/no-I/O product-code owner of placement
    classification; both callers call it; no other product file
    returns placement outcomes."""
    classifier = REPO / "server/soloring/production_world" / (
        "placement_consumer.py")
    assert classifier.is_file(), "shared classifier missing"
    src = classifier.read_text(encoding="utf-8")
    for forbidden in ("sqlalchemy", "import sqlite", "session",
                      "execute(", "asyncio", "datetime", "random",
                      "uuid", "time."):
        assert forbidden not in src, forbidden

    binding = (REPO / "server/soloring/production_world/binding.py").read_text(
        encoding="utf-8")
    evaluator = (REPO / "server/soloring/compatibility/evaluator.py"
                 ).read_text(encoding="utf-8")
    call = "classify_placement_consumer_from_facts"
    assert f"import" in binding and call in binding
    assert call in evaluator
    assert "from soloring.production_world.placement_consumer import" in (
        evaluator)

    # no second decision tree: only the shared classifier returns
    # placement outcomes from product code
    for path in (REPO / "server/soloring").rglob("*.py"):
        body = path.read_text(encoding="utf-8", errors="replace")
        if path.name == "placement_consumer.py":
            continue
        assert 'return {"outcome"' not in body, path
        assert "outcome\": \"UNIQUE_A4\"}" not in body, path


def _load_pinned_binding(tmp_path):
    """Load binding.py from the exact pinned M14 commit as a module."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "show",
         f"{M14_COMMIT}:server/soloring/production_world/binding.py"],
        capture_output=True, text=True, check=True)
    pinned_path = tmp_path / f"pinned_m14_binding_{uuid.uuid4().hex}.py"
    pinned_path.write_text(out.stdout, encoding="utf-8")
    name = pinned_path.stem
    spec = importlib.util.spec_from_file_location(name, pinned_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _derive_both(client, tmp_path, cid, w_revision_id):
    """Current vs pinned-M14 derive_candidate over the same DB state."""
    import soloring.production_world.binding as current
    from soloring.spatial.targets import load_world_revision_with_world

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        c = await current._load_composition_revision(
            conn, await _published_revision(client, cid))
        w = await load_world_revision_with_world(
            conn, spatial_world_revision_id=w_revision_id)
        current_result = await current.derive_candidate(conn, c=c, w=w)
    pinned = _load_pinned_binding(tmp_path)
    async with engine.connect() as conn:
        c2 = await pinned._load_composition_revision(
            conn, await _published_revision(client, cid))
        w2 = await pinned.load_world_revision_with_world(
            conn, spatial_world_revision_id=w_revision_id)
        pinned_result = await pinned.derive_candidate(conn, c=c2, w=w2)
    return current_result, pinned_result


async def _published_revision(client, cid: str) -> str:
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT id FROM composition_revisions "
            "WHERE composition_id = :c ORDER BY created_at DESC "
            "LIMIT 1"), {"c": cid})).scalar_one()
    return row


def _assert_identical(current_result, pinned_result, label: str):
    current_value, current_issues = current_result
    pinned_value, pinned_issues = pinned_result
    assert canonical_json_str(current_value) == canonical_json_str(
        pinned_value), f"{label}: binding value drifted"
    assert current_issues == pinned_issues, f"{label}: issues drifted"


async def test_m13_published_behavior_matches_pinned_m14_across_full_case_matrix(
        client, tmp_path):
    """M15-BASE:09 — the shared-classifier refactor changes no
    published derive_candidate result relative to the pinned M14
    baseline across every reachable closed issue code and clean
    case."""
    base = await seed_base(client, tag=b"r5-b09")
    pid = base["project_id"]
    prid1 = base["production_revision_id"]
    prid2 = await seed_second_revision(client, base, number=2)
    w = await _approved_world(client, pid, key="lobby")

    # case: clean UNIQUE_A4 — subject + track + identity + closed +
    # interpretation
    cid = await make_composition(client, pid)
    occ_a = (await mint(client, cid, prid1, 0, name="A"))["occurrence_id"]
    await _interpretation(client, prid1, translation=(0, 0, 0))
    await _adopt(client, cid, occ_a, {"kind": "production_instance"})
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ_a, "requirement": "required"})
    assert r.status_code == 201, r.text
    # case: CLEAN_A6 — subject without any target
    occ_b = (await mint(client, cid, prid1, 1, name="B"))["occurrence_id"]
    await _adopt(client, cid, occ_b, {"kind": "production_instance"})
    # case: no subject at all (composition-owned)
    await mint(client, cid, prid1, 2, name="C")
    # case: BINDING_SPATIAL_INTERPRETATION_REQUIRED — target revision
    # has no interpretation (prid2 interpretation deferred)
    occ_d = (await mint(client, cid, prid2, 3, name="D"))["occurrence_id"]
    await _interpretation(client, prid2, translation=(1, 0, 0))
    await _adopt(client, cid, occ_d, {"kind": "production_instance"})
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ_d, "requirement": "required"})
    assert r.status_code == 201, r.text
    # flip D's interpretation away after the fact for the REQUIRED case
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        await conn.execute(text(
            "DELETE FROM production_revision_spatial_interpretations "
            "WHERE production_revision_id = :r"), {"r": prid2})
        await conn.commit()
    await publish(client, cid, 4)
    _assert_identical(*await _derive_both(
        client, tmp_path, cid, w["revision"]["id"]), "mixed clean/issues")

    # case: BINDING_COMPOSITION_TRANSFORM_CONFLICT — non-identity
    # transform on a tracked occurrence
    cid2 = await make_composition(client, pid)
    occ_t = (await mint(client, cid2, prid1, 0, name="T",
                        transform=(5, 0, 0)))["occurrence_id"]
    await _adopt(client, cid2, occ_t, {"kind": "production_instance"})
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ_t, "requirement": "required"})
    assert r.status_code == 201, r.text
    await publish(client, cid2, 1)
    _assert_identical(*await _derive_both(
        client, tmp_path, cid2, w["revision"]["id"]), "transform conflict")

    # case: BINDING_SUBJECT_INVALID production_revision_not_closed —
    # closure row removed from a tracked occurrence's revision
    cid3 = await make_composition(client, pid)
    occ_n = (await mint(client, cid3, prid1, 0, name="N"))["occurrence_id"]
    await _adopt(client, cid3, occ_n, {"kind": "production_instance"})
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ_n, "requirement": "required"})
    assert r.status_code == 201, r.text
    async with engine.connect() as conn:
        await conn.execute(text(
            "DELETE FROM production_revision_closures "
            "WHERE production_revision_id = :r"), {"r": prid1})
        await conn.commit()
    await publish(client, cid3, 1)
    _assert_identical(*await _derive_both(
        client, tmp_path, cid3, w["revision"]["id"]), "not closed")
    # (prid1's closure stays deleted for the rest of this test; no later
    # case in this function derives over prid1 again)

    # case: BINDING_PROJECT_MISMATCH — cross-project world pair
    other = await seed_base(client, tag=b"r5-b09-other")
    ow = await _approved_world(client, other["project_id"], key="other")
    cid4 = await make_composition(client, other["project_id"])
    await mint(client, cid4, other["production_revision_id"], 0)
    await publish(client, cid4, 1)
    cross_w = ow["revision"]["id"]
    import soloring.production_world.binding as current
    from soloring.spatial.targets import load_world_revision_with_world

    pinned = _load_pinned_binding(tmp_path)
    async with engine.connect() as conn:
        c4 = await current._load_composition_revision(
            conn, await _published_revision(client, cid4))
        w4 = await load_world_revision_with_world(
            conn, spatial_world_revision_id=cross_w)
        cur = await current.derive_candidate(conn, c=c4, w=w4)
        c4p = await pinned._load_composition_revision(
            conn, await _published_revision(client, cid4))
        w4p = await pinned.load_world_revision_with_world(
            conn, spatial_world_revision_id=cross_w)
        pin = await pinned.derive_candidate(conn, c=c4p, w=w4p)
    _assert_identical(cur, pin, "project mismatch")

    # matrix closure for the working-relevant cases the published path
    # cannot reach: multi-world and multi-target behavior of the shared
    # classifier itself (fail-closed, no A6 fallback, no tie-break)
    from soloring.production_world.placement_consumer import (
        classify_placement_consumer_from_facts as classify,
    )

    base_facts = {
        "occurrence_id": "occ",
        "subject": {"kind": "production_instance", "id": "occ",
                    "valid": True},
        "transform_is_identity": True,
        "revision": {"id": "pr", "project_id": "p", "closed": True,
                     "interpretation_hash": "h" * 64},
    }
    ctx = lambda wid, targets, approved=True, project="p": {  # noqa: E731
        "world_id": wid, "project_id": project,
        "approved_revision": {"id": "wr", "snapshot_hash": "s" * 64}
        if approved else None,
        "targets": targets}

    out = classify({**base_facts, "world_contexts": [
        ctx("w1", [{"kind": "t", "id": "1"}]),
        ctx("w2", [{"kind": "t", "id": "2"}])]})
    assert out == {"outcome": "UNRESOLVED", "reason": "multi_world_context",
                   "detail": {"occurrence_id": "occ",
                              "worlds": ["w1", "w2"]}}
    out = classify({**base_facts, "world_contexts": [
        ctx("w1", [{"kind": "t", "id": "1"},
                   {"kind": "t", "id": "2"}])]})
    assert out["reason"] == "BINDING_SPATIAL_TARGET_CONFLICT"
    assert out == {"outcome": "UNRESOLVED",
                   "reason": "BINDING_SPATIAL_TARGET_CONFLICT",
                   "detail": {"occurrence_id": "occ",
                              "targets": [{"kind": "t", "id": "1"},
                                          {"kind": "t", "id": "2"}]}}
    out = classify({**base_facts, "world_contexts": [
        ctx("w1", [], approved=False)]})
    assert out["reason"] == "no_unique_approved_world_revision"
    out = classify({**base_facts, "world_contexts": [
        ctx("w1", [{"kind": "t", "id": "1"}], project="other")]})
    assert out["reason"] == "BINDING_PROJECT_MISMATCH"
    out = classify({**base_facts,
                    "subject": {"kind": "production_instance", "id": "occ",
                                "valid": False,
                                "invalid_detail": {"reason": "x"}},
                    "world_contexts": []})
    assert out["reason"] == "BINDING_SUBJECT_INVALID"
    out = classify({**base_facts, "world_contexts": []})
    assert out == {"outcome": "CLEAN_A6"}
    out = classify({**base_facts, "world_contexts": [
        ctx("w1", [{"kind": "t", "id": "1"}])]})
    assert out["outcome"] == "UNIQUE_A4"
    assert out["placement_contract"]["target_id"] == "1"
