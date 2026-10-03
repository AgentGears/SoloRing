"""SR26 corrective regressions: applicability discriminator (SR26-01),
fail-closed authoritative reads (SR26-03), corruption-contract
normalization (SR26-05), centralized error codes (SR26-06), and the
PF-03 recovery verifier at head 0020 (SR26-02).
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.errors import ErrorCode
from tests.m17c_seed import ARTICULATION, dialogue_bound_body, make_vp
from tests.test_m17c_binding_transitions import (
    _create_bound,
    _adopt,
    _physical_pair,
    _reviewed_assessment,
    _retarget,
)

PROJECT = "soloring"


async def _sql(client, stmt, params=None):
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _scalar(client, stmt, params=None):
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(stmt), params or {})).scalar()


# ---------------------------------------------------------------------------
# SR26-01 — total PF-03 companion loss can never become generic M17B
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_total_loss_before_first_adoption_refuses(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    await _sql(
        client,
        "DELETE FROM performance_candidate_vocal_bindings "
        "WHERE performance_candidate_id = :c",
        {"c": candidate["id"]})
    response = await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "director"},
    )
    assert response.status_code == 500, response.text
    assert response.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    revisions = await _scalar(
        client,
        "SELECT COUNT(*) FROM performance_revisions "
        "WHERE adopted_candidate_id = :c",
        {"c": candidate["id"]})
    assert revisions == 0


@pytest.mark.asyncio
async def test_total_loss_after_adoption_refuses_replay_and_read(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])
    await _sql(
        client,
        "DELETE FROM performance_candidate_vocal_bindings "
        "WHERE performance_candidate_id = :c",
        {"c": candidate["id"]})
    await _sql(
        client,
        "DELETE FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = :r",
        {"r": revision["id"]})

    replay = await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "again"},
    )
    assert replay.status_code == 500
    assert replay.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"

    for path in (
        f"/performance-candidates/{candidate['id']}/vocal-binding",
        f"/performance-revisions/{revision['id']}/vocal-binding",
    ):
        got = await client.get(path)
        assert got.status_code == 500, (path, got.text)
        assert got.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


@pytest.mark.asyncio
async def test_total_loss_after_adoption_refuses_retarget(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])
    p1, p2 = await _physical_pair(client, world["project_id"], b"sr26-tl")
    assessment, review = await _reviewed_assessment(
        client, revision["id"], p1, p2)
    await _sql(
        client,
        "DELETE FROM performance_candidate_vocal_bindings "
        "WHERE performance_candidate_id = :c",
        {"c": candidate["id"]})
    await _sql(
        client,
        "DELETE FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = :r",
        {"r": revision["id"]})
    before = await _scalar(
        client, "SELECT COUNT(*) FROM performance_candidates")

    response = await _retarget(client, revision["id"], assessment, review)
    assert response.status_code == 500, response.text
    assert response.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    after = await _scalar(
        client, "SELECT COUNT(*) FROM performance_candidates")
    assert after == before


@pytest.mark.asyncio
async def test_none_classification_with_binding_refuses(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    await _sql(
        client,
        "UPDATE performance_candidate_sync_classifications "
        "SET sync_mode = 'NONE' WHERE performance_candidate_id = :c",
        {"c": candidate["id"]})
    response = await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "director"},
    )
    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


@pytest.mark.asyncio
async def test_missing_classification_refuses(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    await _sql(
        client,
        "DELETE FROM performance_candidate_sync_classifications "
        "WHERE performance_candidate_id = :c",
        {"c": candidate["id"]})
    response = await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "director"},
    )
    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


@pytest.mark.asyncio
async def test_adoption_and_retarget_copy_classification_independently(
        client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])
    mode = await _scalar(
        client,
        "SELECT sync_mode FROM performance_revision_sync_classifications "
        "WHERE performance_revision_id = :r",
        {"r": revision["id"]})
    assert mode == "VOCAL_V1"

    p1, p2 = await _physical_pair(client, world["project_id"], b"sr26-cc")
    assessment, review = await _reviewed_assessment(
        client, revision["id"], p1, p2)
    retarget = await _retarget(client, revision["id"], assessment, review)
    assert retarget.status_code == 201, retarget.text
    child_mode = await _scalar(
        client,
        "SELECT sync_mode FROM performance_candidate_sync_classifications "
        "WHERE performance_candidate_id = :c",
        {"c": retarget.json()["id"]})
    assert child_mode == "VOCAL_V1"

    # deleting BOTH companions of the child still refuses further
    # authority (classification survives independently)
    await _sql(
        client,
        "DELETE FROM performance_candidate_vocal_bindings "
        "WHERE performance_candidate_id = :c",
        {"c": retarget.json()["id"]})
    child = await client.post(
        f"/performance-candidates/{retarget.json()['id']}/adopt",
        json={"adopted_by": "director"},
    )
    assert child.status_code == 500
    assert child.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


@pytest.mark.asyncio
async def test_generic_candidates_are_classified_none(client):
    from tests.m17b_seed import SMILE, candidate_body
    from tests.m17b_seed import channel as m17b_channel
    from tests.m17b_seed import kf as m17b_kf
    world = await make_vp(client)
    response = await client.post(
        f"/creative-entities/{world['subject_id']}/performance-candidates",
        json=candidate_body([m17b_channel(SMILE, [m17b_kf(0, 1, 0)])]),
    )
    assert response.status_code == 201, response.text
    mode = await _scalar(
        client,
        "SELECT sync_mode FROM performance_candidate_sync_classifications "
        "WHERE performance_candidate_id = :c",
        {"c": response.json()["id"]})
    assert mode == "NONE"
    revision = await _adopt(client, response.json()["id"])
    rev_mode = await _scalar(
        client,
        "SELECT sync_mode FROM performance_revision_sync_classifications "
        "WHERE performance_revision_id = :r",
        {"r": revision["id"]})
    assert rev_mode == "NONE"


# ---------------------------------------------------------------------------
# SR26-03 — authoritative reads fail closed on damaged PF-03 closure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_tamper_refuses_with_corruption_contract(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])

    # (label, tamper stmt, restore stmt, params)
    cases = [
        ("candidate hash",
         "UPDATE performance_candidate_vocal_bindings "
         "SET binding_hash = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
         "aaaaaaaaaaaaaaaaaaaaaaaa' "
         "WHERE performance_candidate_id = :c",
         "UPDATE performance_candidate_vocal_bindings "
         "SET binding_hash = (SELECT binding_hash FROM "
         "performance_revision_vocal_bindings "
         "WHERE performance_revision_id = :r) "
         "WHERE performance_candidate_id = :c"),
        ("candidate json",
         "UPDATE performance_candidate_vocal_bindings "
         "SET binding_json = '{}' "
         "WHERE performance_candidate_id = :c",
         "UPDATE performance_candidate_vocal_bindings "
         "SET binding_json = (SELECT binding_json FROM "
         "performance_revision_vocal_bindings "
         "WHERE performance_revision_id = :r) "
         "WHERE performance_candidate_id = :c"),
        ("candidate rational",
         "UPDATE performance_candidate_vocal_bindings "
         "SET performance_origin_num = 2, performance_origin_den = 2 "
         "WHERE performance_candidate_id = :c",
         "UPDATE performance_candidate_vocal_bindings "
         "SET performance_origin_num = "
         "(SELECT performance_origin_num FROM "
         "performance_revision_vocal_bindings "
         "WHERE performance_revision_id = :r), "
         "performance_origin_den = "
         "(SELECT performance_origin_den FROM "
         "performance_revision_vocal_bindings "
         "WHERE performance_revision_id = :r) "
         "WHERE performance_candidate_id = :c"),
        ("revision rate divergence",
         "UPDATE performance_revision_vocal_bindings "
         "SET sample_rate_hz = 44100 "
         "WHERE performance_revision_id = :r",
         "UPDATE performance_revision_vocal_bindings "
         "SET sample_rate_hz = (SELECT sample_rate_hz FROM "
         "performance_candidate_vocal_bindings "
         "WHERE performance_candidate_id = :c) "
         "WHERE performance_revision_id = :r"),
    ]
    params = {"c": candidate["id"], "r": revision["id"]}
    cand_path = f"/performance-candidates/{candidate['id']}/vocal-binding"
    rev_path = f"/performance-revisions/{revision['id']}/vocal-binding"
    for label, tamper, restore in cases:
        await _sql(client, tamper, params)
        # candidate-side tampers break the candidate read directly and
        # the revision read through closure; revision-side tampers break
        # only the revision read (the candidate row stays lawful).
        paths = [cand_path, rev_path] if "candidate" in label else [rev_path]
        for path in paths:
            got = await client.get(path)
            assert got.status_code == 500, (label, path, got.text)
            assert got.json()["error_code"] == \
                "INTERNAL_INVARIANT_VIOLATION", (label, path)
        await _sql(client, restore, params)
    # the restored closure reads cleanly again
    ok = await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding")
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_read_vp_substitution_refuses(client):
    from tests.test_m17c_binding_transitions import _same_line_alternate_vp
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])
    alternate = await _same_line_alternate_vp(client, world)
    await _sql(
        client,
        "UPDATE performance_revision_vocal_bindings "
        "SET vocal_performance_revision_id = :v "
        "WHERE performance_revision_id = :r",
        {"v": alternate["id"], "r": revision["id"]})
    got = await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding")
    assert got.status_code == 500, got.text
    assert got.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


# ---------------------------------------------------------------------------
# SR26-05 — persisted-history failures use the corruption contract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_vp_in_staged_backup_is_corruption(client, tmp_path):
    """SR26-05 (missing-VP dimension): the live app DB cannot reach a
    missing-VP binding (FK RESTRICT blocks the delete), so the
    corruption-contract proof runs at the recovery layer where raw
    staged-DB edits are possible."""
    world, candidate, revision = await _m17c_world(client)
    root = await _backup_m17c(client, tmp_path, "missvp")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute("PRAGMA foreign_keys = OFF")
    # a missing-VP reference inherently violates the physical FK, so
    # any shape of this tamper trips the staged-DB FK gate — the
    # corruption contract — before the semantic layer; that IS the
    # fail-closed outcome this proof pins (the verifier's own
    # missing-VP branch is defense-in-depth beneath it).
    con.execute(
        "UPDATE performance_candidate_vocal_bindings "
        "SET vocal_performance_revision_id = '55555555-5555-4555-8555-"
        "555555555555' WHERE performance_candidate_id = ?",
        (candidate["id"],))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "missvp")


@pytest.mark.asyncio
async def test_missing_cited_alignment_is_corruption(client):
    from tests.m17c_seed import make_alignment
    world = await make_vp(client)
    alignment = await make_alignment(
        client, world["vp"]["id"], world["blob_hash"])
    response = await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            world["vp"]["id"],
            alignment_by_channel={key: alignment["id"]
                                  for key in ARTICULATION},
            articulation_time={key: (2, 1) for key in ARTICULATION},
        ),
    )
    assert response.status_code == 201, response.text
    candidate = response.json()
    await _sql(
        client, "DELETE FROM dialogue_alignments WHERE id = :a",
        {"a": alignment["id"]})
    adopt = await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "director"},
    )
    assert adopt.status_code == 500, adopt.text
    assert adopt.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


# ---------------------------------------------------------------------------
# SR26-06 — centralized error vocabulary
# ---------------------------------------------------------------------------

def test_m17c_error_codes_are_centrally_registered():
    for code in (
        "PERFORMANCE_VOCAL_BINDING_NOT_FOUND",
        "PERFORMANCE_VOCAL_BINDING_INVALID",
        "PERFORMANCE_VOCAL_SUBJECT_MISMATCH",
        "PERFORMANCE_VOCAL_PROJECT_MISMATCH",
        "PERFORMANCE_VOCAL_INTERVAL_INVALID",
        "PERFORMANCE_VOCAL_ALIGNMENT_MISMATCH",
        "PERFORMANCE_REQUIRED_ARTICULATION_MISSING",
    ):
        member = getattr(ErrorCode, code)
        assert member == code
        from soloring.performance import m17c_contract
        assert getattr(m17c_contract, code) == member


# ---------------------------------------------------------------------------
# SR26-02 — PF-03 recovery verifier at head 0020
# ---------------------------------------------------------------------------

def _rehash_manifest(backup_root):
    import hashlib
    from soloring.domain.canonical import canonical_json_bytes
    manifest_path = backup_root / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_sha256"] = hashlib.sha256(
        (backup_root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


async def _m17c_world(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])
    return world, candidate, revision


async def _backup_m17c(client, tmp_path, tag):
    from soloring.recovery import backup as rb_backup
    from tests.test_m16_recovery import _settings, _stamp_alembic
    await _stamp_alembic(client)
    root = tmp_path / f"sr26-{tag}"
    await rb_backup(await _settings(client), root)
    return root


async def _restore_refuses(backup_root, tmp_path, tag):
    from soloring.recovery import restore as rb_restore
    _rehash_manifest(backup_root)
    dest = tmp_path / f"refused-{tag}"
    with pytest.raises(Exception) as excinfo:
        await rb_restore(backup_root, dest)
    code = getattr(excinfo.value, "code", None) or getattr(
        excinfo.value, "error_code", None)
    kind = type(excinfo.value).__name__
    assert code in ("RECOVERY_CORRUPTION",
                    "INTERNAL_INVARIANT_VIOLATION") or \
        kind in ("RecoveryCorruption",), \
        (code, kind, excinfo.value)
    assert not dest.exists()
    return excinfo.value


@pytest.mark.asyncio
async def test_recovery_clean_roundtrip_preserves_pf03_rows(client, tmp_path):
    from soloring.recovery import restore as rb_restore
    world, candidate, revision = await _m17c_world(client)
    root = await _backup_m17c(client, tmp_path, "clean")
    dest = tmp_path / "restored"
    await rb_restore(root, dest)

    import sqlite3
    con = sqlite3.connect(dest / "soloring.db")
    con.row_factory = sqlite3.Row
    try:
        cb = con.execute(
            "SELECT * FROM performance_candidate_vocal_bindings "
            "WHERE performance_candidate_id = ?", (candidate["id"],)
        ).fetchone()
        rb = con.execute(
            "SELECT * FROM performance_revision_vocal_bindings "
            "WHERE performance_revision_id = ?", (revision["id"],)
        ).fetchone()
        cc = con.execute(
            "SELECT sync_mode FROM "
            "performance_candidate_sync_classifications "
            "WHERE performance_candidate_id = ?",
            (candidate["id"],)).fetchone()[0]
        rc = con.execute(
            "SELECT sync_mode FROM "
            "performance_revision_sync_classifications "
            "WHERE performance_revision_id = ?",
            (revision["id"],)).fetchone()[0]
    finally:
        con.close()
    assert cb is not None and rb is not None
    assert cc == "VOCAL_V1" and rc == "VOCAL_V1"
    binding_cols = (
        "vocal_performance_revision_id", "source_start_sample",
        "source_end_sample_exclusive", "sample_rate_hz",
        "performance_origin_num", "performance_origin_den",
        "synchronization_basis_version", "binding_schema_version",
        "binding_json", "binding_hash")
    assert all(cb[c] == rb[c] for c in binding_cols)


@pytest.mark.asyncio
async def test_recovery_total_loss_refuses(client, tmp_path):
    world, candidate, revision = await _m17c_world(client)
    root = await _backup_m17c(client, tmp_path, "total")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "DELETE FROM performance_candidate_vocal_bindings "
        "WHERE performance_candidate_id = ?", (candidate["id"],))
    con.execute(
        "DELETE FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = ?", (revision["id"],))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "total")


@pytest.mark.asyncio
async def test_recovery_one_sided_loss_refuses(client, tmp_path):
    world, candidate, revision = await _m17c_world(client)
    root = await _backup_m17c(client, tmp_path, "onesided")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "DELETE FROM performance_candidate_vocal_bindings "
        "WHERE performance_candidate_id = ?", (candidate["id"],))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "onesided")


@pytest.mark.asyncio
async def test_recovery_missing_classification_refuses(client, tmp_path):
    world, candidate, revision = await _m17c_world(client)
    root = await _backup_m17c(client, tmp_path, "cls")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "DELETE FROM performance_candidate_sync_classifications "
        "WHERE performance_candidate_id = ?", (candidate["id"],))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "cls")


@pytest.mark.asyncio
async def test_recovery_none_with_binding_refuses(client, tmp_path):
    world, candidate, revision = await _m17c_world(client)
    root = await _backup_m17c(client, tmp_path, "nonebind")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "UPDATE performance_candidate_sync_classifications "
        "SET sync_mode = 'NONE' WHERE performance_candidate_id = ?",
        (candidate["id"],))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "nonebind")


@pytest.mark.asyncio
async def test_recovery_binding_hash_divergence_refuses(client, tmp_path):
    world, candidate, revision = await _m17c_world(client)
    root = await _backup_m17c(client, tmp_path, "hash")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "UPDATE performance_candidate_vocal_bindings "
        "SET binding_hash = ? WHERE performance_candidate_id = ?",
        ("0" * 64, candidate["id"]))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "hash")


@pytest.mark.asyncio
async def test_recovery_binding_json_divergence_refuses(client, tmp_path):
    world, candidate, revision = await _m17c_world(client)
    root = await _backup_m17c(client, tmp_path, "json")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "UPDATE performance_candidate_vocal_bindings "
        "SET binding_json = ? WHERE performance_candidate_id = ?",
        ('{"binding_schema_version": 1}', candidate["id"]))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "json")


@pytest.mark.asyncio
async def test_recovery_one_sided_vp_substitution_refuses(client, tmp_path):
    from tests.test_m17c_binding_transitions import _same_line_alternate_vp
    world, candidate, revision = await _m17c_world(client)
    alternate = await _same_line_alternate_vp(client, world)
    root = await _backup_m17c(client, tmp_path, "vpsub")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "UPDATE performance_revision_vocal_bindings "
        "SET vocal_performance_revision_id = ? "
        "WHERE performance_revision_id = ?",
        (alternate["id"], revision["id"]))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "vpsub")


@pytest.mark.asyncio
async def test_recovery_retarget_lineage_loss_refuses(client, tmp_path):
    world, candidate, revision = await _m17c_world(client)
    p1, p2 = await _physical_pair(client, world["project_id"], b"sr26-rl")
    assessment, review = await _reviewed_assessment(
        client, revision["id"], p1, p2)
    retarget = await _retarget(client, revision["id"], assessment, review)
    assert retarget.status_code == 201, retarget.text
    root = await _backup_m17c(client, tmp_path, "lineage")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "DELETE FROM performance_candidate_vocal_bindings "
        "WHERE performance_candidate_id = ?",
        (retarget.json()["id"],))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "lineage")
