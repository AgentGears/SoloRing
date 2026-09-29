"""DR26 corrective regressions: coordinated classification-downgrade
matrix (DR26-01), articulation-in-reads (DR26-02), admission-vs-history
error contracts (DR26-03), and the superseded-draft-0020 migration
policy (DR26-04)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from tests.m17c_seed import ARTICULATION, dialogue_bound_body, make_vp
from tests.test_m17c_binding_transitions import (
    _create_bound,
    _adopt,
    _physical_pair,
    _reviewed_assessment,
    _retarget,
)


async def _sql(client, stmt, params=None):
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _scalar(client, stmt, params=None):
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(stmt), params or {})).scalar()


async def _world(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])
    return world, candidate, revision


# ---------------------------------------------------------------------------
# DR26-01 — coordinated classification-downgrade matrix
# ---------------------------------------------------------------------------

async def _retarget_refuses_zero(client, revision):
    p1, p2 = await _physical_pair(client, revision["project_id"], b"dr26")
    assessment, review = await _reviewed_assessment(client, revision["id"],
                                                    p1, p2)
    before = await _scalar(client, "SELECT COUNT(*) FROM "
                           "performance_candidates")
    response = await _retarget(client, revision["id"], assessment, review)
    assert response.status_code == 500, response.text
    assert response.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    after = await _scalar(client, "SELECT COUNT(*) FROM "
                          "performance_candidates")
    assert after == before


@pytest.mark.asyncio
async def test_dr26_01_candidate_v1_revision_downgraded_to_none(client):
    """Direction A: candidate VOCAL_V1, revision corrupted to NONE with
    its binding deleted. The revision GET must refuse rather than 404;
    replay and retarget refuse; recovery refuses."""
    world, candidate, revision = await _world(client)
    await _sql(
        client,
        "UPDATE performance_revision_sync_classifications "
        "SET sync_mode = 'NONE' WHERE performance_revision_id = :r",
        {"r": revision["id"]})
    await _sql(
        client,
        "DELETE FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = :r",
        {"r": revision["id"]})

    got = await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding")
    assert got.status_code == 500, got.text
    assert got.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"

    replay = await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "again"})
    assert replay.status_code == 500, replay.text

    cand_get = await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding")
    assert cand_get.status_code == 500, cand_get.text

    await _retarget_refuses_zero(client, revision)


@pytest.mark.asyncio
async def test_dr26_01_revision_v1_candidate_downgraded_to_none(client):
    """Direction B: revision VOCAL_V1, adopted candidate corrupted to
    NONE with its binding deleted. Both GETs refuse; replay and retarget
    refuse."""
    world, candidate, revision = await _world(client)
    await _sql(
        client,
        "UPDATE performance_candidate_sync_classifications "
        "SET sync_mode = 'NONE' WHERE performance_candidate_id = :c",
        {"c": candidate["id"]})
    await _sql(
        client,
        "DELETE FROM performance_candidate_vocal_bindings "
        "WHERE performance_candidate_id = :c",
        {"c": candidate["id"]})

    got = await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding")
    assert got.status_code == 500, got.text
    assert got.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"

    rev_get = await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding")
    assert rev_get.status_code == 500, rev_get.text

    replay = await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "again"})
    assert replay.status_code == 500, replay.text

    await _retarget_refuses_zero(client, revision)


@pytest.mark.asyncio
async def test_dr26_01_both_bindings_deleted_one_side_downgraded(client):
    """Both companions deleted while only the revision classification is
    downgraded — the closure still refuses every consumer."""
    world, candidate, revision = await _world(client)
    await _sql(
        client,
        "UPDATE performance_revision_sync_classifications "
        "SET sync_mode = 'NONE' WHERE performance_revision_id = :r",
        {"r": revision["id"]})
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

    for path in (
        f"/performance-candidates/{candidate['id']}/vocal-binding",
        f"/performance-revisions/{revision['id']}/vocal-binding",
    ):
        got = await client.get(path)
        assert got.status_code == 500, (path, got.text)

    replay = await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "again"})
    assert replay.status_code == 500
    await _retarget_refuses_zero(client, revision)


@pytest.mark.asyncio
async def test_dr26_01_recovery_refuses_coordinated_downgrade(client,
                                                              tmp_path):
    from tests.test_m17c_sr26_regressions import (
        _backup_m17c, _restore_refuses)
    world, candidate, revision = await _world(client)
    root = await _backup_m17c(client, tmp_path, "dr26a")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "UPDATE performance_revision_sync_classifications "
        "SET sync_mode = 'NONE' WHERE performance_revision_id = ?",
        (revision["id"],))
    con.execute(
        "DELETE FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = ?", (revision["id"],))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "dr26a")


@pytest.mark.asyncio
async def test_dr26_01_recovery_refuses_inverse_downgrade(client, tmp_path):
    """C2-04: the inverse state is constructed so BOTH sides are
    locally valid — candidate classification NONE with its binding
    deleted (candidate-local law satisfied), revision VOCAL_V1 with its
    binding intact (revision-local law satisfied). Recovery must refuse
    on the cross-pair disagreement itself, so the proof cannot be made
    vacuous by an earlier local cardinality check."""
    from tests.test_m17c_sr26_regressions import (
        _backup_m17c, _restore_refuses)
    world, candidate, revision = await _world(client)
    root = await _backup_m17c(client, tmp_path, "dr26b")
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "UPDATE performance_candidate_sync_classifications "
        "SET sync_mode = 'NONE' WHERE performance_candidate_id = ?",
        (candidate["id"],))
    con.execute(
        "DELETE FROM performance_candidate_vocal_bindings "
        "WHERE performance_candidate_id = ?",
        (candidate["id"],))
    con.commit()
    con.close()
    exc = await _restore_refuses(root, tmp_path, "dr26b")
    # C3-02: branch-specific proof — the stable marker names the
    # cross-pair disagreement, and both conflicting modes identify this
    # exact fixture (revision VOCAL_V1 vs adopted candidate NONE). Not
    # satisfiable by missing/malformed classifications or by any local
    # cardinality failure (both sides are locally valid by
    # construction).
    msg = str(exc)
    assert "PAIR-CLASSIFICATION-DISAGREEMENT" in msg, exc
    assert "adopted candidate" in msg, exc
    assert "'VOCAL_V1'" in msg and "'NONE'" in msg, exc


# ---------------------------------------------------------------------------
# DR26-02 — articulation law in authoritative reads
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dr26_02_read_rejects_persisted_articulation_loss(client):
    """Coherently re-hash the retained payload with the jaw_open
    keyframe moved outside the bound interval: every persisted-hash
    check passes, and the read's articulation law refuses."""
    import hashlib
    from soloring.domain.canonical import canonical_json_str
    world, candidate, revision = await _world(client)
    settings = client._transport.app.state.settings

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        blob_hash = (await conn.execute(
            text("SELECT canonical_channel_payload_blob_hash FROM "
                 "performance_candidates WHERE id = :c"),
            {"c": candidate["id"]})).scalar()
    blob_path = (settings.blob_dir / "sha256" / blob_hash[:2]
                 / blob_hash[2:4] / blob_hash)
    doc = json.loads(blob_path.read_text(encoding="utf-8"))
    for channel in doc["channels"]:
        if channel["channel_key"].endswith("jaw_open"):
            channel["keyframes"][0]["time_ms"] = {"num": -250, "den": 1}
    body = canonical_json_str(doc).encode("utf-8")
    new_hash = hashlib.sha256(body).hexdigest()
    new_path = (settings.blob_dir / "sha256" / new_hash[:2]
                / new_hash[2:4] / new_hash)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_bytes(body)
    await _sql(
        client,
        "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
        "detected_media_type, created_at) VALUES (:h, :p, :s, "
        "'application/json', '2026-01-01T00:00:00.000Z')",
        {"h": new_hash,
         "p": f"sha256/{new_hash[:2]}/{new_hash[2:4]}/{new_hash}",
         "s": len(body)})
    await _sql(
        client,
        "UPDATE performance_candidates SET "
        "canonical_channel_payload_blob_hash = :h, "
        "canonical_channel_payload_sha256 = :h WHERE id = :c",
        {"h": new_hash, "c": candidate["id"]})
    await _sql(
        client,
        "UPDATE performance_revisions SET "
        "canonical_channel_payload_blob_hash = :h, "
        "canonical_channel_payload_sha256 = :h WHERE id = :r",
        {"h": new_hash, "r": revision["id"]})

    for path in (
        f"/performance-candidates/{candidate['id']}/vocal-binding",
        f"/performance-revisions/{revision['id']}/vocal-binding",
    ):
        got = await client.get(path)
        assert got.status_code == 500, (path, got.text)
        assert got.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


# ---------------------------------------------------------------------------
# DR26-03 — admission vs history error contracts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dr26_03_fresh_request_missing_alignment_is_404(client):
    """A NEW request citing a nonexistent alignment is an admission
    error, never a 500."""
    world = await make_vp(client)
    response = await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            world["vp"]["id"],
            alignment_by_channel={
                key: "00000000-0000-4000-8000-00000000dead"
                for key in ARTICULATION},
            articulation_time={key: (2, 1) for key in ARTICULATION},
        ),
    )
    assert response.status_code == 404, response.text
    assert response.json()["error_code"] == "PERFORMANCE_ALIGNMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_dr26_03_fresh_request_missing_vp_is_404(client):
    world = await make_vp(client)
    response = await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            "00000000-0000-4000-8000-00000000beef",
            articulation_time={key: (2, 1) for key in ARTICULATION}),
    )
    assert response.status_code == 404, response.text
    assert response.json()["error_code"] == "VOCAL_PERFORMANCE_NOT_FOUND"


@pytest.mark.asyncio
async def test_dr26_03_history_wrong_vp_alignment_is_corruption(client):
    from tests.m17c_seed import make_alignment
    world = await make_vp(client)
    alignment = await make_alignment(client, world["vp"]["id"],
                                     world["blob_hash"])
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
    from tests.test_m17c_binding_transitions import _same_line_alternate_vp
    alternate = await _same_line_alternate_vp(client, world)
    # post-adoption tamper: the cited alignment is re-pointed at a
    # different VP — persisted-history verification must corrupt
    await _sql(
        client,
        "UPDATE dialogue_alignments SET vocal_performance_revision_id = "
        ":v WHERE id = :a",
        {"v": alternate["id"], "a": alignment["id"]})
    got = await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding")
    assert got.status_code == 500, got.text
    assert got.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


# ---------------------------------------------------------------------------
# DR26-04 — superseded draft-0020 migration identity
# ---------------------------------------------------------------------------

def test_dr26_04_superseded_draft_identity_rejected(tmp_path):
    """A database stamped with the superseded draft-0020 identity is
    mechanically rejected: alembic cannot upgrade it, and recovery
    refuses the unknown head. It must be rebuilt from 0019."""
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    db = tmp_path / "superseded.db"
    env = {
        "SystemRoot": "C:\\Windows",
        "SOLORING_DATABASE_URL": f"sqlite:///{db.as_posix()}",
        "SOLORING_DATA_DIR": db.parent.as_posix(),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade",
         "0019_m17b_performance_revisions"],
        cwd=str(repo / "server"), capture_output=True, text=True, env=env)
    assert up.returncode == 0, up.stderr[-800:]

    con = sqlite3.connect(db)
    con.execute(
        "UPDATE alembic_version SET version_num = "
        "'0020_m17c_performance_capture'")
    con.commit()
    con.close()

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(repo / "server"), capture_output=True, text=True, env=env)
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert ("0020_m17c_performance_capture" in combined
            or "Can't locate revision" in combined
            or "can't locate revision" in combined), combined[-800:]

    from soloring.recovery.backup import EXPECTED_ALEMBIC_HEAD
    assert EXPECTED_ALEMBIC_HEAD == "0022_m17c_schema8_capture"
    staged_head = "0020_m17c_performance_capture"
    assert staged_head != EXPECTED_ALEMBIC_HEAD
    assert staged_head not in {
        "0019_m17b_performance_revisions", "0020_m17c_perf_capture_r2", EXPECTED_ALEMBIC_HEAD}


def test_dr26_04_fresh_0019_to_r2_succeeds(tmp_path):
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    db = tmp_path / "fresh.db"
    env = {
        "SystemRoot": "C:\\Windows",
        "SOLORING_DATABASE_URL": f"sqlite:///{db.as_posix()}",
        "SOLORING_DATA_DIR": db.parent.as_posix(),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    # DR26-04's reachability claim is about the FROZEN r2 identity
    # itself: a fresh database must be able to stop exactly at
    # 0020_m17c_perf_capture_r2 (B-F1 froze it there; successor 0021 is
    # a separate step). At 0020 the PF-02 working-mapping table is
    # lawfully absent — the premise the B-F7 staged-upgrade battery
    # upgrades from.
    up = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade",
         "0020_m17c_perf_capture_r2"],
        cwd=str(repo / "server"), capture_output=True, text=True, env=env)
    assert up.returncode == 0, up.stderr[-800:]
    con = sqlite3.connect(db)
    head = con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0]
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert head == "0020_m17c_perf_capture_r2"
    assert {
        "performance_candidate_vocal_bindings",
        "performance_revision_vocal_bindings",
        "performance_candidate_sync_classifications",
        "performance_revision_sync_classifications",
    } <= tables
    assert "shot_performance_segment_mappings" not in tables
