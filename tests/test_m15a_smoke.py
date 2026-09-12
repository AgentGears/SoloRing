"""M15A end-to-end smoke (scratch) — assessment through the real API."""

from __future__ import annotations

import json

from tests.m13_seed import make_composition, mint, seed_base
from tests.m13_seed import seed_second_revision
from tests.test_m13_binding import _adopt, _approved_world, _interpretation


async def test_m15a_smoke_assessment_flow(client):
    engine = client._transport.app.state.engine
    base = await seed_base(client, tag=b"m15a-smoke")
    pid = base["project_id"]
    prid1 = base["production_revision_id"]
    prid2 = await seed_second_revision(client, base, number=2)
    cid = await make_composition(client, pid)
    occ = (await mint(client, cid, prid1, 0, name="Chair 7"))[
        "occurrence_id"]

    w = await _approved_world(client, pid, key="lobby")
    await _interpretation(client, prid1, translation=(0, 0, 0))
    await _interpretation(client, prid2, translation=(10, 0, 0))
    await _adopt(client, cid, occ, {"kind": "production_instance"})
    r = await client.post(
        f"/spatial-worlds/{w['world']['id']}/production-instance-tracks",
        json={"occurrence_id": occ, "requirement": "required"})
    assert r.status_code == 201, r.text

    r = await client.post(
        f"/production-revisions/{prid1}/compatibility-assessments",
        json={"to_revision_id": prid2})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["scope_status"] == "ASSESSED"
    assert body["overall_verdict"] == "REQUIRES_REVIEW", body
    use = body["uses"][0]
    assert use["dimensions"]["spatial_interpretation"] == (
        "TRANSLATION_REQUIRED")
    assert use["translator_output_hash"], body

    aid = body["assessment_id"]
    r = await client.get(f"/production-compatibility-assessments/{aid}")
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["overall_verdict"] == "REQUIRES_REVIEW"

    r = await client.get(
        f"/production-compatibility-assessments/{aid}/uses")
    assert r.status_code == 200, r.text
    assert r.json()["uses"][0]["verdict"] == "REQUIRES_REVIEW"

    # convergence: same coordinate again
    r = await client.post(
        f"/production-revisions/{prid1}/compatibility-assessments",
        json={"to_revision_id": prid2})
    assert r.status_code == 200 and r.json()["converged"] is True

    # stored integrity re-derivation against the persisted rows
    from soloring.compatibility.canonical import verify_stored_assessment
    async with engine.connect() as conn:
        verified = await verify_stored_assessment(conn, aid)
    assert verified["parent"]["report_hash"] == detail["report_hash"]
    assert json.loads(verified["uses"][0]["dimension_results_json"])[
        "retained_consumption"]["status"] == "REVIEW_REQUIRED"
