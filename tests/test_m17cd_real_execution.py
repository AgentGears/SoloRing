"""M17C-D W6 — G06, the decoded-pixel material-consumption
regression (frozen plan R2-FINAL W6 + the FPR31-M17CD-03
correction): the pinned A/B causal design implemented as the frozen
contract demands.

ONE pinned world: A and B share the same source media (the same
reference asset + the same VP retained audio), the same workflow
package (the same captured manifest/template hashes), the same
model/runtime, the same ordinary parameters and seed, the same
subject/performance authority — ONLY the frozen timing authority
that deterministically changes the derived controls/audio differs
(the vocal mapping + its paired performance segment re-PUT with a
lawful positive anchor between the two captures).

The test acquires worker ownership through the REAL claim/lease
path, drives each Generation through the actual production worker
against the pinned LivePortrait executor, reads the PERSISTED
submission document and proves its GRAPH bindings correspond to the
exact GPI/derived Blob identities, retrieves the generated media,
decodes comparable frames, and compares decoded-pixel hashes.
Terminal-status strings are never consumption evidence.

ENVIRONMENT-GATED: requires SOLORING_G06_LIVE=1, the pinned
LivePortrait stack installed at the local ComfyUI executor, and a
reachable origin. When absent the battery SKIPS with an explicit
reason — the environmental gate stays OPEN and is never translated
into a pass.
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SOLORING_G06_LIVE") != "1",
    reason="G06 live-execution lane: set SOLORING_G06_LIVE=1 with the "
           "pinned LivePortrait stack installed at the local ComfyUI "
           "executor to run the A/B decoded-pixel regression")


def _pixel_hash(png_bytes: bytes) -> str:
    """Decode one PNG to raw RGBA and hash the pixels — comparable
    frames must hash identically iff their decoded pixels do."""
    import io

    from PIL import Image

    with Image.open(io.BytesIO(png_bytes)) as image:
        rgba = image.convert("RGBA").tobytes()
    return hashlib.sha256(rgba).hexdigest()


@pytest.mark.asyncio
async def test_g06_ab_timing_drives_submitted_controls(client, factory,
                                                        tmp_path,
                                                        monkeypatch):
    from sqlalchemy import text

    from tests.test_m17cd_create_path import (
        _facial_world, _performance_manifest,
    )

    await _performance_manifest(tmp_path, monkeypatch)
    # ONE pinned world — everything except the timing authority is
    # created once and never varied
    world = await _facial_world(client, factory)
    sid, pid = world["shot"], world["project_id"]
    settings = client._transport.app.state.settings
    engine = client._transport.app.state.engine

    async def _snapshot_of(generation_id):
        async with engine.connect() as conn:
            return (await conn.execute(text(
                "SELECT workflow_spec_json, manifest_hash, "
                "workflow_template_hash, parameters_json, seed "
                "FROM generations WHERE id = :g"),
                {"g": generation_id})).mappings().one()

    # A: the original timing (anchor 0)
    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 202, r.text
    gen_a = r.json()["id"]

    # B: ONLY the timing authority changes — the same VP + mapping
    # position, re-PUT with a lawful positive anchor (+500 ms), the
    # paired performance segment re-PUT to match; re-capture
    r = await client.put(
        f"/shots/{sid}/vocal-segments/0",
        json={
            "vocal_performance_revision_id":
                world["vp"]["vp"]["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 500, "den": 1},
        })
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{sid}/performance-segments/0",
        json={
            "performance_revision_id": world["pr"]["id"],
            "performance_start_ms": {"num": 0, "den": 1},
            "performance_end_ms": {"num": 1000, "den": 1},
            "shot_anchor_ms": {"num": 500, "den": 1},
            "vocal_mapping_position": 0,
        })
    assert r.status_code == 200, r.text
    from tests.test_m17cd_create_path import _capture_closed

    await _capture_closed(client, sid)
    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 202, r.text
    gen_b = r.json()["id"]

    snap_a, snap_b = await _snapshot_of(gen_a), await _snapshot_of(
        gen_b)
    # the pinned coordinates are IDENTICAL
    assert snap_a["manifest_hash"] == snap_b["manifest_hash"]
    assert snap_a["workflow_template_hash"] == \
        snap_b["workflow_template_hash"]
    assert snap_a["parameters_json"] == snap_b["parameters_json"]
    assert snap_a["seed"] == snap_b["seed"] is None
    # ONLY the timing-derived performance execution differs
    assert snap_a["workflow_spec_json"] != snap_b["workflow_spec_json"]

    # the derived blobs differ deterministically
    async def _gpi(generation_id):
        async with engine.connect() as conn:
            return (await conn.execute(text(
                "SELECT artifact_role, blob_hash FROM "
                "generation_performance_inputs WHERE generation_id = "
                ":g"), {"g": generation_id})).mappings().all()

    gpi_a = {row["artifact_role"]: row["blob_hash"]
             for row in await _gpi(gen_a)}
    gpi_b = {row["artifact_role"]: row["blob_hash"]
             for row in await _gpi(gen_b)}
    assert set(gpi_a) == set(gpi_b)
    assert gpi_a != gpi_b

    # ---- the live lane: real ownership + production worker ----
    origin = os.environ.get("SOLORING_G06_ORIGIN") or getattr(
        settings, "comfy_origin", None)
    if not origin:  # pragma: no cover — environment-dependent
        pytest.skip("no ComfyUI origin configured for the live lane")
    import httpx

    try:
        async with httpx.AsyncClient(
                base_url=str(origin), timeout=5) as probe:
            (await probe.get("/system_stats")).raise_for_status()
    except Exception as exc:  # pragma: no cover — environment
        pytest.skip(f"local executor unreachable: {exc}")

    from soloring.executors.comfy.client import ComfyClient
    from soloring.worker.comfy_pipeline import drive_comfy_generation
    from soloring.worker.ownership import (
        acquire_worker_lease, claim_next_generation,
    )

    worker_id = "g06-worker"
    await acquire_worker_lease(engine, worker_id, 600)
    frames = {}
    for label, expected_id in (("A", gen_a), ("B", gen_b)):
        claim = await claim_next_generation(engine, worker_id)
        assert claim is not None
        claimed_id, attempt_id = claim
        assert claimed_id == expected_id
        async with httpx.AsyncClient(
                base_url=str(origin), timeout=1800) as http:
            comfy = ComfyClient(str(origin))
            comfy._client = http  # the real client over this session
            outcome = await drive_comfy_generation(
                engine, settings, worker_id, claimed_id, attempt_id,
                comfy)
        assert outcome == "succeeded", (label, outcome)

        # the PERSISTED submission document: its graph bindings
        # correspond to the exact GPI/derived identities
        async with engine.connect() as conn:
            submission = (await conn.execute(text(
                "SELECT submission_json FROM "
                "executor_submissions WHERE generation_id = :g"),
                {"g": claimed_id})).scalar_one()
        document = json.loads(submission)
        marker = document["extra_data"]["soloring"]
        bindings = marker["performance_bindings"]
        expected_blobs = gpi_a if label == "A" else gpi_b
        assert {b["blob_hash"] for b in bindings} == \
            set(expected_blobs.values())
        graph = document["prompt"]
        from soloring.workflows import manifest as _mm

        mdoc = json.loads((_mm.WORKFLOW_DIR /
                           "manifest.json").read_text())
        for key in ("performance.controls",
                    "performance.vocal_audio"):
            decl = mdoc["inputs"][key]
            reference = graph[decl["node"]]["inputs"][decl["field"]]
            assert expected_blobs[key][:16] in reference, \
                (label, key, reference)

        # the generated media: decode comparable frames + hashes
        async with engine.connect() as conn:
            take_rows = (await conn.execute(text(
                "SELECT output_key, blob_hash FROM takes WHERE "
                "generation_id = :g"), {"g": claimed_id})).mappings(
                ).all()
        first = sorted(take_rows, key=lambda t: t["output_key"])[0]
        blob_path = settings.blob_dir_parent if hasattr(
            settings, "blob_dir_parent") else settings.data_dir
        from soloring.assets.blob_store import BlobStore

        data = BlobStore(settings).path_for_hash(
            first["blob_hash"]).read_bytes()
        import io as _io

        from PIL import Image

        with Image.open(_io.BytesIO(data)) as video_probe:
            frame_count = getattr(video_probe, "n_frames", 1)
            mid = frame_count // 2
            video_probe.seek(mid)
            frames[label] = hashlib.sha256(
                video_probe.convert("RGBA").tobytes()).hexdigest()

    assert frames["A"] != frames["B"], \
        "identical decoded pixels under different timing-derived " \
        "controls would mean the controls were never materially " \
        "consumed"
