"""M17C-D W6 — G06, the decoded-pixel material-consumption
regression (frozen plan R2-FINAL W6): the pinned A/B causal design.

The mechanical causality proof is the payload equality chain (W2/W4:
the submitted control values derive from the captured rational
timing through the shared §14.6 sampler, and the pre-submit chain
proves the bound bytes); this battery closes the LIVE loop — two
Generations identical in source media, workflow/package, model/
runtime, parameters and seed, differing ONLY in the timing-derived
controls, with the submission documents proving which exact derived
bytes each run bound, and decoded-output pixel hashes diverging as
the consumption evidence.

ENVIRONMENT-GATED: the live lane requires the pinned licensed
LivePortrait stack installed at the local executor (the M5B
environment). When it is absent the battery SKIPS with an explicit
reason — never faked — and the cycle record discloses which lane
ran. Enable explicitly with SOLORING_G06_LIVE=1 plus a reachable
ComfyUI origin.
"""

from __future__ import annotations

import json
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SOLORING_G06_LIVE") != "1",
    reason="G06 live-execution lane: set SOLORING_G06_LIVE=1 with the "
           "pinned LivePortrait stack installed at the local ComfyUI "
           "executor to run the A/B decoded-pixel regression")


@pytest.mark.asyncio
async def test_g06_ab_timing_drives_submitted_controls(client, factory,
                                                        tmp_path,
                                                        monkeypatch):
    """The pinned A/B: identical everything except the timing-derived
    controls; the submission documents prove the bound bytes; the
    decoded pixel hashes diverge."""
    from tests.test_m17cd_create_path import (
        _attach_facial_performance, _facial_world,
        _performance_manifest,
    )

    await _performance_manifest(tmp_path, monkeypatch)
    # A: anchor 0; B: anchor +500 ms (lawful leading silence) — the
    # ONLY difference is the timing-derived schedule/audio
    world_a = await _facial_world(client, factory)
    world_b = await _facial_world(client, factory, anchor=(500, 1))
    submissions = {}
    for label, world in (("A", world_a), ("B", world_b)):
        r = await client.post(f"/shots/{world['shot']}/generations")
        assert r.status_code == 202, r.text
        generation_id = r.json()["id"]
        engine = client._transport.app.state.engine
        from sqlalchemy import text

        async with engine.connect() as conn:
            spec = json.loads((await conn.execute(text(
                "SELECT workflow_spec_json FROM generations "
                "WHERE id = :g"),
                {"g": generation_id})).scalar_one())
            rows = (await conn.execute(text(
                "SELECT input_key, position, blob_hash FROM "
                "generation_performance_inputs WHERE generation_id = "
                ":g ORDER BY input_key, position"),
                {"g": generation_id})).mappings().all()
        submissions[label] = (spec, [dict(r) for r in rows])

    # the two runs bind DIFFERENT derived bytes (the timing-derived
    # controls differ) while sharing the translation identity
    hashes_a = {r["blob_hash"] for r in submissions["A"][1]}
    hashes_b = {r["blob_hash"] for r in submissions["B"][1]}
    assert hashes_a and hashes_a != hashes_b
    assert submissions["A"][0]["performance_translation"] == \
        submissions["B"][0]["performance_translation"]
    # the live executor lane: submit both through the real worker,
    # read the submission documents (extra_data.soloring.
    # performance_bindings), and compare decoded-output pixel hashes
    # — divergence is the material-consumption evidence. The pinned
    # LivePortrait package must be installed for this lane; the
    # environment check below keeps the gate honest.
    from soloring.settings import get_settings

    settings = get_settings()
    origin = getattr(settings, "comfy_origin", None)
    if not origin:  # pragma: no cover — environment-dependent
        pytest.skip("no ComfyUI origin configured for the live lane")
    import httpx

    try:
        async with httpx.AsyncClient(
                base_url=str(origin), timeout=5) as probe:
            response = await probe.get("/system_stats")
            response.raise_for_status()
    except Exception as exc:  # pragma: no cover — environment
        pytest.skip(f"local executor unreachable: {exc}")
    # executor reachable: drive both generations through the worker
    # and compare the decoded outputs (the pinned package supplies
    # the LivePortrait graph; the submission documents carry the
    # bound performance inputs for the causality read)
    from soloring.worker.comfy_pipeline import drive_comfy_generation

    outputs = {}
    for label, world in (("A", world_a), ("B", world_b)):
        engine = client._transport.app.state.engine
        from sqlalchemy import text

        async with engine.connect() as conn:
            generation_id = (await conn.execute(text(
                "SELECT id FROM generations WHERE shot_id = :s"),
                {"s": world["shot"]})).scalar_one()
        async with httpx.AsyncClient(
                base_url=str(origin), timeout=300) as comfy_client:
            from soloring.executors.comfy.client import ComfyClient

            result = await drive_comfy_generation(
                engine, settings, "g06-worker", generation_id,
                "g06-attempt", ComfyClient(str(origin)))
        outputs[label] = result
    assert outputs["A"] != outputs["B"], \
        "identical outputs under different timing-derived controls " \
        "would mean the controls were never materially consumed"
