"""M15 UI:05 — the HTTP surface exposes the backend verdict trace."""

from __future__ import annotations

import json

from sqlalchemy import text

from soloring.compatibility.service import create_assessment
from tests.m15_seed import seed_a4_use


def _sess(client):
    class _S:
        bind = client._transport.app.state.engine

    return _S()


async def test_http_surface_uses_backend_verdict_trace_not_frontend_reinterpretation(
        client):
    """M15-UI:05 — every per-use verdict/dimension on the HTTP surface
    is the backend's stored trace byte-for-byte; the response exposes
    no recomputed or renamed verdict, and no frontend-oriented
    simplification of the four-verdict vocabulary."""
    base = await seed_a4_use(client, tag=b"ui05")
    result = await create_assessment(
        _sess(client), from_revision_id=base["production_revision_id"],
        to_revision_id=base["r2"])
    aid = result["assessment_id"]
    r = await client.get(
        f"/production-compatibility-assessments/{aid}/uses")
    assert r.status_code == 200, r.text
    http_use = r.json()["uses"][0]

    # the HTTP trace must equal the stored normalized rows exactly
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        stored = (await conn.execute(text(
            "SELECT verdict, dimension_results_json, "
            "use_contract_hash, translator_output_hash "
            "FROM production_compatibility_uses "
            "WHERE assessment_id = :a AND position = 0"),
            {"a": aid})).one()
    assert http_use["verdict"] == stored.verdict
    assert http_use["use_contract_hash"] == stored.use_contract_hash
    assert http_use["translator_output_hash"] == (
        stored.translator_output_hash)
    stored_dims = json.loads(stored.dimension_results_json)
    for dimension, status in http_use["dimensions"].items():
        assert stored_dims[dimension]["status"] == status, dimension

    # the closed four-verdict vocabulary is exposed verbatim, never a
    # renamed or folded frontend variant
    assert http_use["verdict"] in (
        "COMPATIBLE_AS_IS",
        "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION",
        "REQUIRES_REVIEW",
        "INCOMPATIBLE")
    detail = await client.get(
        f"/production-compatibility-assessments/{aid}")
    assert detail.json()["overall_verdict"] in (
        "COMPATIBLE_AS_IS",
        "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION",
        "REQUIRES_REVIEW",
        "INCOMPATIBLE")
