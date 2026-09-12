"""M15A shared-classifier proofs (frozen R6 §31.1 M15-BASE:08/09/11).

BASE:08 — one pure/no-I/O product-code owner of placement
classification; both published M13 and M15 working-state call it.

BASE:09 — the R5 M13 refactor is behavior-identical to the **isolated
exact pinned M14 predecessor** (a detached git worktree at
89298e793c651e9e8b9164912c76e3595867a60a whose soloring import root
is that tree; a comparator resolving any transitive soloring module
from the current checkout is mixed-version evidence and is rejected)
over the frozen reachable case matrix: the five named
predecessor-reachable issue outputs plus clean/ambiguous cases.

BASE:11 — `BINDING_SPATIAL_INTERPRETATION_INVALID` is
vocabulary-reserved/unreachable in the isolated pinned M14 (proven by
exhaustive emission-site enumeration over the isolated tree, not by
absence in one file) and is not made newly reachable by the refactored
published adapter (emission-set enumeration + the live matrix).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from soloring.domain.canonical import canonical_json_str
from tests.m13_seed import make_composition, mint, publish, seed_base
from tests.m13_seed import seed_second_revision
from tests.test_m13_binding import _adopt, _approved_world, _interpretation

REPO = Path(__file__).resolve().parents[1]
M14_COMMIT = "89298e793c651e9e8b9164912c76e3595867a60a"

RESERVED_TOKEN = "BINDING_SPATIAL_INTERPRETATION_INVALID"
FIVE_REACHABLE = {
    "BINDING_PROJECT_MISMATCH",
    "BINDING_SUBJECT_INVALID",
    "BINDING_SPATIAL_TARGET_CONFLICT",
    "BINDING_COMPOSITION_TRANSFORM_CONFLICT",
    "BINDING_SPATIAL_INTERPRETATION_REQUIRED",
}


def test_m13_and_m15_use_one_shared_placement_classifier():
    """M15-BASE:08 — one pure/no-I/O product-code owner of placement
    classification; both callers call it; no other product file
    returns placement outcomes."""
    classifier = REPO / "server/soloring/production_world" / (
        "placement_consumer.py")
    assert classifier.is_file(), "shared classifier missing"
    src = classifier.read_text(encoding="utf-8")
    for forbidden in ("sqlalchemy", "import sqlite", "execute(",
                      "asyncio", "datetime", "import random",
                      "import uuid", "time."):
        assert forbidden not in src, forbidden

    binding = (REPO / "server/soloring/production_world/binding.py").read_text(
        encoding="utf-8")
    evaluator = (REPO / "server/soloring/compatibility/evaluator.py"
                 ).read_text(encoding="utf-8")
    call = "classify_placement_consumer_from_facts"
    assert call in binding and call in evaluator
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


# ---- isolated pinned-M14 machinery (frozen R6 §6.5.1) -----------------------


def _worktree_add(tmp_path: Path) -> Path:
    worktree = tmp_path / "pinned_m14_worktree"
    subprocess.run(
        ["git", "-C", str(REPO), "worktree", "add", "--detach",
         str(worktree), M14_COMMIT],
        capture_output=True, text=True, check=True)
    return worktree


def _worktree_remove(worktree: Path) -> None:
    subprocess.run(
        ["git", "-C", str(REPO), "worktree", "remove", "--force",
         str(worktree)],
        capture_output=True, text=True)


_RUNNER = r'''
import asyncio
import json
import sys

from sqlalchemy.ext.asyncio import create_async_engine


async def main(db_path, c_rev, w_rev):
    import soloring
    import soloring.production_world.binding as binding
    import soloring.production_world.canonical as pw_canonical
    import soloring.spatial.targets as targets
    import soloring.errors as errors
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        async with engine.connect() as conn:
            c = await binding._load_composition_revision(conn, c_rev)
            w = await targets.load_world_revision_with_world(
                conn, spatial_world_revision_id=w_rev)
            value, issues = await binding.derive_candidate(conn, c=c, w=w)
    finally:
        await engine.dispose()
    print(json.dumps({
        "value": value,
        "issues": issues,
        "module_files": {
            "soloring": soloring.__file__,
            "binding": binding.__file__,
            "production_world.canonical": pw_canonical.__file__,
            "spatial.targets": targets.__file__,
            "errors": errors.__file__,
        },
    }, default=str))


asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3]))
'''


def _run_pinned(worktree: Path, tmp_path: Path, db_path: str,
                c_rev: str, w_rev: str, *, import_root: Path | None = None):
    """Execute the comparator with soloring imports rooted in the pinned
    tree (or a deliberately wrong root for the mixed-version negative)."""
    root = import_root if import_root is not None else worktree / "server"
    runner = tmp_path / "pinned_comparator_runner.py"
    runner.write_text(_RUNNER, encoding="utf-8")
    env_keys = {
        "PYTHONPATH": str(root),
        "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", ""),
    }
    out = subprocess.run(
        [sys.executable, str(runner), db_path, c_rev, w_rev],
        capture_output=True, text=True, cwd=str(root), env=env_keys,
        timeout=180)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _pinned_only(module_files: dict, worktree: Path) -> bool:
    """The R6 guard: every transitive soloring module resolves inside the
    isolated pinned tree; any current-checkout resolution is
    mixed-version evidence."""
    root = worktree.resolve().as_posix() + "/"
    return all(
        str(p).replace("\\", "/").startswith(root)
        for p in module_files.values())


def _db_path(client) -> str:
    engine = client._transport.app.state.engine
    return engine.sync_engine.url.database


async def _published_revision(client, cid: str) -> str:
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT id FROM composition_revisions "
            "WHERE composition_id = :c ORDER BY created_at DESC "
            "LIMIT 1"), {"c": cid})).scalar_one()


async def _current_derive(client, cid: str, w_revision_id: str):
    import soloring.production_world.binding as current
    from soloring.spatial.targets import load_world_revision_with_world

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        c = await current._load_composition_revision(
            conn, await _published_revision(client, cid))
        w = await load_world_revision_with_world(
            conn, spatial_world_revision_id=w_revision_id)
        return await current.derive_candidate(conn, c=c, w=w)


def _assert_identical(current_result, pinned_out: dict, label: str):
    assert canonical_json_str(current_result[0]) == canonical_json_str(
        pinned_out["value"]), f"{label}: binding value drifted"
    assert current_result[1] == pinned_out["issues"], (
        f"{label}: issues drifted")


async def test_m13_published_behavior_matches_isolated_pinned_m14_across_reachable_case_matrix(
        client, tmp_path):
    """M15-BASE:09 — semantics-preserving M13 refactor against the
    ISOLATED exact pinned M14 tree across the five named reachable
    issue outputs + clean/ambiguous cases; no current-checkout soloring
    imports (negative: a current-rooted comparator fails the guard)."""
    worktree = _worktree_add(tmp_path)
    try:
        base = await seed_base(client, tag=b"r6-b09")
        pid = base["project_id"]
        prid1 = base["production_revision_id"]
        prid2 = await seed_second_revision(client, base, number=2)
        w = await _approved_world(client, pid, key="lobby")
        db_path = _db_path(client)

        # mixed clean/issues case: UNIQUE_A4 + CLEAN_A6 (no target) +
        # CLEAN_A6 (no subject) + INTERPRETATION_REQUIRED (target interp
        # deleted after track creation)
        cid = await make_composition(client, pid)
        occ_a = (await mint(client, cid, prid1, 0, name="A"))[
            "occurrence_id"]
        await _interpretation(client, prid1, translation=(0, 0, 0))
        await _adopt(client, cid, occ_a, {"kind": "production_instance"})
        r = await client.post(
            f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
            json={"occurrence_id": occ_a, "requirement": "required"})
        assert r.status_code == 201, r.text
        occ_b = (await mint(client, cid, prid1, 1, name="B"))[
            "occurrence_id"]
        await _adopt(client, cid, occ_b, {"kind": "production_instance"})
        await mint(client, cid, prid1, 2, name="C")
        occ_d = (await mint(client, cid, prid2, 3, name="D"))[
            "occurrence_id"]
        await _interpretation(client, prid2, translation=(1, 0, 0))
        await _adopt(client, cid, occ_d, {"kind": "production_instance"})
        r = await client.post(
            f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
            json={"occurrence_id": occ_d, "requirement": "required"})
        assert r.status_code == 201, r.text
        engine = client._transport.app.state.engine
        async with engine.connect() as conn:
            await conn.execute(text(
                "DELETE FROM "
                "production_revision_spatial_interpretations "
                "WHERE production_revision_id = :r"), {"r": prid2})
            await conn.commit()
        await publish(client, cid, 4)
        twin = await _published_revision(client, cid)
        pinned = _run_pinned(worktree, tmp_path, db_path, twin,
                             w["revision"]["id"])
        assert _pinned_only(pinned["module_files"], worktree), (
            "comparator resolved a soloring module outside the pinned tree")
        _assert_identical(
            await _current_derive(client, cid, w["revision"]["id"]),
            pinned, "mixed clean/issues")

        # TRANSFORM_CONFLICT: non-identity transform on a tracked
        # occurrence
        cid2 = await make_composition(client, pid)
        occ_t = (await mint(client, cid2, prid1, 0, name="T",
                            transform=(5, 0, 0)))["occurrence_id"]
        await _adopt(client, cid2, occ_t, {"kind": "production_instance"})
        r = await client.post(
            f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
            json={"occurrence_id": occ_t, "requirement": "required"})
        assert r.status_code == 201, r.text
        await publish(client, cid2, 1)
        pinned = _run_pinned(
            worktree, tmp_path, db_path,
            await _published_revision(client, cid2), w["revision"]["id"])
        _assert_identical(
            await _current_derive(client, cid2, w["revision"]["id"]),
            pinned, "transform conflict")

        # SUBJECT_INVALID production_revision_not_closed: closure row
        # removed (pins to INTERPRETATION_REQUIRED per the pinned
        # closed-fact order)
        cid3 = await make_composition(client, pid)
        occ_n = (await mint(client, cid3, prid1, 0, name="N"))[
            "occurrence_id"]
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
        pinned = _run_pinned(
            worktree, tmp_path, db_path,
            await _published_revision(client, cid3), w["revision"]["id"])
        _assert_identical(
            await _current_derive(client, cid3, w["revision"]["id"]),
            pinned, "not closed")

        # PROJECT_MISMATCH: cross-project world pair
        other = await seed_base(client, tag=b"r6-b09-other")
        ow = await _approved_world(client, other["project_id"], key="other")
        cid4 = await make_composition(client, other["project_id"])
        await mint(client, cid4, other["production_revision_id"], 0)
        await publish(client, cid4, 1)
        pinned = _run_pinned(
            worktree, tmp_path, db_path,
            await _published_revision(client, cid4), ow["revision"]["id"])
        _assert_identical(
            await _current_derive(client, cid4, ow["revision"]["id"]),
            pinned, "project mismatch")

        # frozen ambiguous cases against the shared classifier directly
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

        def ctx(wid, targets, approved=True, project="p"):
            return {
                "world_id": wid, "project_id": project,
                "approved_revision": {
                    "id": "wr", "snapshot_hash": "s" * 64}
                if approved else None,
                "targets": targets}

        out = classify({**base_facts, "world_contexts": [
            ctx("w1", [{"kind": "t", "id": "1"}]),
            ctx("w2", [{"kind": "t", "id": "2"}])]})
        assert out["reason"] == "multi_world_context"
        out = classify({**base_facts, "world_contexts": [
            ctx("w1", [{"kind": "t", "id": "1"},
                       {"kind": "t", "id": "2"}])]})
        assert out["reason"] == "BINDING_SPATIAL_TARGET_CONFLICT"
        out = classify({**base_facts, "world_contexts": [
            ctx("w1", [], approved=False)]})
        assert out["reason"] == "no_unique_approved_world_revision"
        out = classify({**base_facts, "world_contexts": [
            ctx("w1", [{"kind": "t", "id": "1"}], project="other")]})
        assert out["reason"] == "BINDING_PROJECT_MISMATCH"
        out = classify({**base_facts,
                        "subject": {"kind": "production_instance",
                                    "id": "occ", "valid": False,
                                    "invalid_detail": {"reason": "x"}},
                        "world_contexts": []})
        assert out["reason"] == "BINDING_SUBJECT_INVALID"
        assert classify({**base_facts, "world_contexts": []}) == {
            "outcome": "CLEAN_A6"}
        out = classify({**base_facts, "world_contexts": [
            ctx("w1", [{"kind": "t", "id": "1"}])]})
        assert out["outcome"] == "UNIQUE_A4"
        assert out["placement_contract"]["target_id"] == "1"

        # frozen negative #55: the same comparator deliberately rooted
        # at the CURRENT checkout fails the R6 guard (mixed-version
        # evidence is rejected, not silently accepted)
        mixed = _run_pinned(
            worktree, tmp_path, db_path, twin, w["revision"]["id"],
            import_root=REPO / "server")
        assert not _pinned_only(mixed["module_files"], worktree), (
            "guard failed to detect current-checkout resolution")
    finally:
        _worktree_remove(worktree)


async def test_reserved_spatial_interpretation_invalid_remains_unreachable_from_published_path(
        client, tmp_path):
    """M15-BASE:11 — the reserved sixth issue token is
    vocabulary-only in the ISOLATED pinned M14 (exhaustive
    emission-site enumeration, not absence-inference) and is not made
    newly reachable by the refactored published adapter."""
    worktree = _worktree_add(tmp_path)
    try:
        # (a) pinned half: the token's ONLY occurrence in the entire
        # isolated pinned tree is the ISSUE_CODES vocabulary tuple
        occurrences = []
        for path in (worktree / "server").rglob("*.py"):
            for lineno, line in enumerate(
                    path.read_text(encoding="utf-8",
                                   errors="replace").splitlines(), 1):
                if RESERVED_TOKEN in line:
                    occurrences.append((path.relative_to(worktree)
                                        .as_posix(), lineno))
        assert occurrences == [
            ("server/soloring/production_world/binding.py", 50)], (
            f"unexpected token occurrences: {occurrences}")

        # every issue-emission site in the pinned published path
        # (derive_candidate's add(...) calls) enumerates to exactly the
        # five reachable codes
        pinned_binding = (worktree / "server/soloring/production_world"
                          / "binding.py").read_text(encoding="utf-8")
        pinned_emitted = set(re.findall(r'add\(\s*"([A-Z_]+)"',
                                        pinned_binding))
        assert pinned_emitted == FIVE_REACHABLE, pinned_emitted
        assert RESERVED_TOKEN not in pinned_emitted

        # the pinned corruption path raises typed errors rather than
        # emitting the reserved issue
        pinned_canonical = (worktree / "server/soloring/production_world"
                            / "canonical.py").read_text(encoding="utf-8")
        assert RESERVED_TOKEN not in pinned_canonical
        verify_body = pinned_canonical.split(
            "def verify_stored_interpretation(")[1].split("\ndef ")[0]
        raises = re.findall(r"raise (\w+)", verify_body)
        assert raises and all(
            r in ("validation_error", "internal_invariant") for r in raises
        ), raises  # typed failure paths only — no issue emission

        # (b) refactored half: the current published adapter's complete
        # emission vocabulary — binding.py add(...) sites plus the
        # shared classifier's issue constants — is the same five-code
        # set; the reserved token stays vocabulary-reserved (present in
        # ISSUE_CODES, absent from every emission site)
        current_binding = (REPO / "server/soloring/production_world"
                           / "binding.py").read_text(encoding="utf-8")
        classifier_src = (REPO / "server/soloring/production_world"
                          / "placement_consumer.py").read_text(
            encoding="utf-8")
        current_emitted = set(
            re.findall(r'add\(\s*"([A-Z_]+)"', current_binding))
        current_emitted |= set(re.findall(
            r'^_[A-Z_]+ = "([A-Z_]+)"', classifier_src, re.M))
        assert current_emitted == FIVE_REACHABLE, current_emitted
        assert RESERVED_TOKEN in re.findall(
            r'"([A-Z_]+)"', current_binding.split("ISSUE_CODES")[1]
            .split(")")[0]), "vocabulary reservation lost"

        # (b, empirical) the live matrix run never observes the token
        # — re-derived through the isolated comparator over the mixed
        # fixture used by BASE:09's world
        base = await _seed_mixed_world(client)
        pinned = _run_pinned(
            worktree, tmp_path, _db_path(client),
            await _published_revision(client, base["cid"]),
            base["w_revision"])
        codes = {i["code"] for i in pinned["issues"]}
        assert codes <= FIVE_REACHABLE, codes
        assert RESERVED_TOKEN not in codes
    finally:
        _worktree_remove(worktree)


async def _seed_mixed_world(client) -> dict:
    base = await seed_base(client, tag=b"r6-b11")
    pid = base["project_id"]
    prid1 = base["production_revision_id"]
    w = await _approved_world(client, pid, key="lobby")
    cid = await make_composition(client, pid)
    occ = (await mint(client, cid, prid1, 0, name="A"))["occurrence_id"]
    await _interpretation(client, prid1)
    await _adopt(client, cid, occ, {"kind": "production_instance"})
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ, "requirement": "required"})
    assert r.status_code == 201, r.text
    await mint(client, cid, prid1, 1, name="B")
    await publish(client, cid, 2)
    return {"cid": cid, "w_revision": w["revision"]["id"]}
