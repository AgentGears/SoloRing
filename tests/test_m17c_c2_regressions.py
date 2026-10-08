"""C2 corrective regressions (cycle 3): complete adopted-pair closure
(C2-01), finished ADMISSION/HISTORICAL semantics for kind + project
closure (C2-02), revision-owned temporal-domain law (C2-03), and the
non-vacuous inverse recovery proof (C2-04, in the DR26 file)."""

from __future__ import annotations

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


async def _bound_world(client):
    world = await make_vp(client)
    candidate = await _create_bound(client, world)
    revision = await _adopt(client, candidate["id"])
    return world, candidate, revision


async def _generic_world(client):
    from tests.m17b_seed import SMILE, candidate_body
    from tests.m17b_seed import channel as m17b_channel
    from tests.m17b_seed import kf as m17b_kf
    world = await make_vp(client)
    response = await client.post(
        f"/creative-entities/{world['subject_id']}/performance-candidates",
        json=candidate_body([m17b_channel(SMILE, [m17b_kf(0, 1, 0)])]),
    )
    assert response.status_code == 201, response.text
    revision = await _adopt(client, response.json()["id"])
    return world, response.json(), revision


async def _retarget_zero(client, revision):
    p1, p2 = await _physical_pair(client, revision["project_id"], b"c2")
    assessment, review = await _reviewed_assessment(client, revision["id"],
                                                    p1, p2)
    before = await _scalar(client,
                           "SELECT COUNT(*) FROM performance_candidates")
    response = await _retarget(client, revision["id"], assessment, review)
    assert response.status_code == 500, response.text
    assert response.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    after = await _scalar(client,
                          "SELECT COUNT(*) FROM performance_candidates")
    assert after == before


def _corrupt(resp):
    assert resp.status_code == 500, resp.text
    assert resp.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


# ---------------------------------------------------------------------------
# C2-01 — complete adopted-pair closure in authoritative reads
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_c2_01_v1_pair_missing_revision_binding_refuses_everywhere(
        client):
    """Regression A: candidate/revision both VOCAL_V1, revision binding
    deleted only. The candidate GET must ALSO prove the pair (including
    revision-local cardinality) and refuse — not return the still-lawful
    candidate side."""
    world, candidate, revision = await _bound_world(client)
    await _sql(
        client,
        "DELETE FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = :r", {"r": revision["id"]})

    _corrupt(await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding"))
    _corrupt(await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding"))
    _corrupt(await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "again"}))
    await _retarget_zero(client, revision)


@pytest.mark.asyncio
async def test_c2_01_none_pair_with_injected_candidate_binding_refuses(
        client):
    """Regression B: genuine NONE/NONE M17B history with an injected
    candidate binding. Both GETs refuse; replay refuses; recovery
    refuses."""
    world, candidate, revision = await _generic_world(client)
    # inject a raw binding row for the NONE-classified candidate,
    # referencing a real VP of the same project/speaker so the row is
    # FK-lawful (grammar alone cannot make it lawful)
    await _sql(
        client,
        "INSERT INTO performance_candidate_vocal_bindings "
        "(performance_candidate_id, vocal_performance_revision_id, "
        " source_start_sample, source_end_sample_exclusive, "
        " sample_rate_hz, performance_origin_num, "
        " performance_origin_den, synchronization_basis_version, "
        " binding_schema_version, binding_json, binding_hash, created_at) "
        "SELECT :c, :v, 48000, 96000, 48000, 0, 1, 1, 1, "
        "'{}', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        "aaaaaaaa', '2026-01-01T00:00:00.000Z' ",
        {"c": candidate["id"], "v": world["vp"]["id"]})

    _corrupt(await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding"))
    _corrupt(await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding"))
    _corrupt(await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "again"}))


@pytest.mark.asyncio
async def test_c2_01_lawful_none_pair_keeps_honest_404(client):
    """Lawful genuine NONE/NONE history must NOT be broken by the
    strengthened closure: both GETs stay honest 404s."""
    world, candidate, revision = await _generic_world(client)
    for path in (
        f"/performance-candidates/{candidate['id']}/vocal-binding",
        f"/performance-revisions/{revision['id']}/vocal-binding",
    ):
        got = await client.get(path)
        assert got.status_code == 404, (path, got.text)
        assert got.json()["error_code"] == "PERFORMANCE_VOCAL_BINDING_NOT_FOUND"


@pytest.mark.asyncio
async def test_c2_01_recovery_pair_cardinality_both_directions(client,
                                                               tmp_path):
    from tests.test_m17c_sr26_regressions import (
        _backup_m17c, _restore_refuses)
    import sqlite3

    # Regression A state: V1/V1 pair, revision binding deleted
    world, candidate, revision = await _bound_world(client)
    root = await _backup_m17c(client, tmp_path, "c2a")
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "DELETE FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = ?", (revision["id"],))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "c2a")

    # Regression B state: NONE/NONE pair, injected candidate binding
    world2, candidate2, revision2 = await _generic_world(client)
    root2 = await _backup_m17c(client, tmp_path, "c2b")
    con = sqlite3.connect(root2 / "soloring.db")
    con.execute(
        "INSERT INTO performance_candidate_vocal_bindings "
        "(performance_candidate_id, vocal_performance_revision_id, "
        " source_start_sample, source_end_sample_exclusive, "
        " sample_rate_hz, performance_origin_num, "
        " performance_origin_den, synchronization_basis_version, "
        " binding_schema_version, binding_json, binding_hash, created_at) "
        "VALUES (?, ?, 48000, 96000, 48000, 0, 1, 1, 1, '{}', "
        "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        "aaaaaaaa', '2026-01-01T00:00:00.000Z')",
        (candidate2["id"], world2["vp"]["id"]))
    con.commit()
    con.close()
    await _restore_refuses(root2, tmp_path, "c2b")


# ---------------------------------------------------------------------------
# C2-02 — finished ADMISSION/HISTORICAL semantics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_c2_02_fresh_body_kind_keeps_422(client):
    world = await make_vp(client)
    response = await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(world["vp"]["id"], kind="BODY"),
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_c2_02_persisted_kind_corruption_is_500(client):
    world, candidate, revision = await _bound_world(client)
    await _sql(
        client,
        "UPDATE performance_candidates SET performance_kind = 'BODY' "
        "WHERE id = :c", {"c": candidate["id"]})
    _corrupt(await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "again"}))
    _corrupt(await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding"))


@pytest.mark.asyncio
async def test_c2_02_fresh_cross_project_vp_keeps_422(client):
    world1 = await make_vp(client)
    world2 = await make_vp(client)
    response = await client.post(
        f"/creative-entities/{world1['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            world2["vp"]["id"],
            articulation_time={key: (2, 1) for key in ARTICULATION}),
    )
    assert response.status_code == 422, response.text
    assert response.json()["error_code"] == \
        "PERFORMANCE_VOCAL_PROJECT_MISMATCH", response.text


@pytest.mark.asyncio
async def test_c2_02_persisted_project_disagreement_is_500(client):
    world, candidate, revision = await _bound_world(client)
    other = await make_vp(client)  # second, real project
    await _sql(
        client,
        "UPDATE performance_candidates SET project_id = :p "
        "WHERE id = :c",
        {"p": other["project_id"], "c": candidate["id"]})
    _corrupt(await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding"))
    _corrupt(await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "again"}))


# ---------------------------------------------------------------------------
# C2-03 — the revision owns its temporal-domain law
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_c2_03_revision_domain_tamper_refuses_revision_read_only(
        client, tmp_path):
    world, candidate, revision = await _bound_world(client)
    # back up the LAWFUL state first (backup runs the full verifier
    # chain on the source DB and would refuse the tampered closure)
    from tests.test_m17c_sr26_regressions import (
        _backup_m17c, _restore_refuses)
    root = await _backup_m17c(client, tmp_path, "c2d")

    # shrink ONLY the revision's temporal domain so the persisted vocal
    # interval no longer fits it; the adopted candidate stays lawful
    await _sql(
        client,
        "UPDATE performance_revisions SET temporal_end_num = 100 "
        "WHERE id = :r", {"r": revision["id"]})

    _corrupt(await client.get(
        f"/performance-revisions/{revision['id']}/vocal-binding"))
    # IR-03/IR-04 supersession (recorded): the revision temporal
    # domain columns are COPIED-CLOSURE fields, so under the
    # mode-independent revision authority seam the refusal now fires
    # on the copied-closure branch (which subsumes copied-field
    # tampering); the revision-OWNED domain law itself remains
    # independently proven by the SR2-05 origin-domain case (a
    # coherent binding tamper that keeps the closure intact). The
    # candidate GET now ALSO refuses — an adopted candidate must
    # prove the complete adopted-pair closure before representing
    # authority (IR-04 asymmetric matrix, revision-side case).
    got = await client.get(
        f"/performance-candidates/{candidate['id']}/vocal-binding")
    assert got.status_code == 500, got.text
    assert got.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"

    # recovery refuses the same staged state
    import sqlite3
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "UPDATE performance_revisions SET temporal_end_num = 100 "
        "WHERE id = ?", (revision["id"],))
    con.commit()
    con.close()
    await _restore_refuses(root, tmp_path, "c2d")
