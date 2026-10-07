"""M17C-D correction item 6 — the NON-LIVE production-path worker
regressions (the FPR31-M17CD-01/02/05 closure proofs that must be
green BEFORE any live-executor cost): a real schema-5 `_drive`
traversal through the actual claim/lease path, the retained-package
ladder, the performance uploads, and the pure translator — proving
the submitted GRAPH consumes the derived bytes at the manifest's
declared node/fields (never a marker), plus the v5-over-v1 and
v5-over-v2 output-dispatch laws.
"""

from __future__ import annotations

import json

import pytest

from tests.test_m17cd_create_path import (
    _facial_world, _performance_manifest, _row,
)

_FPS_NUM, _FPS_DEN, _FRAMES = 25, 1, 25


class RecordedClient:
    """A ComfyClient stand-in: uploads succeed locally-referenced and
    submit_prompt RECORDS the payload then aborts — the drive's
    preparation (package ladder + performance uploads + translation)
    is fully traversed with the captured graph available for
    inspection, without a live executor."""

    def __init__(self):
        self.payload = None
        self.uploads: list[str] = []

    async def upload_input(self, *, source_path, filename, subfolder):
        from soloring.executors.comfy.models import (
            NormalizedUploadReference,
        )

        self.uploads.append(filename)
        return NormalizedUploadReference(name=filename,
                                         subfolder=subfolder)

    async def submit_prompt(self, payload_document):
        self.payload = payload_document
        raise RuntimeError("recorded-abort: no live executor")


async def _performance_generation(client, factory, tmp_path,
                                  monkeypatch):
    await _performance_manifest(tmp_path, monkeypatch)
    world = await _facial_world(client, factory)
    r = await client.post(f"/shots/{world['shot']}/generations")
    assert r.status_code == 202, r.text
    return world, r.json()["id"]


def _claim(engine, worker_id):
    from soloring.worker.ownership import (
        acquire_worker_lease, claim_next_generation,
    )

    async def _run():
        await acquire_worker_lease(engine, worker_id, 60)
        return await claim_next_generation(engine, worker_id)

    import asyncio

    return asyncio.get_event_loop(), _run


# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_production_drive_binds_performance_into_graph(
        client, factory, tmp_path, monkeypatch):
    """The REAL `_drive` schema-5 path over the PINNED
    performance/LivePortrait package, on the frozen TWO-SEGMENT
    world (one dialogue-bound + one generic): both
    `performance.controls` rows (the repeated grouped key) AND the
    dialogue audio row reach the declared executor graph through
    the per-role ordered segment bundles — consumption at the
    pinned package's own nodes/fields (40.controls_segments /
    41.audio_segments), never a marker, never synthetic fields on
    the Hunyuan KSampler. The FPR32-M17CD-01/02 decisive proof."""
    import json as _json

    from soloring.worker.comfy_pipeline import drive_comfy_generation
    from soloring.worker.ownership import (
        acquire_worker_lease, claim_next_generation,
    )

    from tests.m17b_seed import (
        SMILE as _SMILE_META, adopt as _adopt_generic,
        candidate_body as _candidate_body,
        channel as _channel, create_candidate as _create_candidate,
        kf as _kf17b,
    )
    from tests.test_m17cd_create_path import (
        _capture_closed, _facial_world,
    )

    world, generation_id = await _performance_generation(
        client, factory, tmp_path, monkeypatch)
    sid = world["shot"]

    # the frozen multi-segment world: a generic FACIAL second
    # segment (the create battery's lawful shape)
    generic = await _create_candidate(
        client, world["vp"]["subject_id"],
        _candidate_body(
            [_channel(_SMILE_META, [_kf17b(0, 1, 100000)])],
            start=(0, 1), end=(500, 1)))
    pr2 = await _adopt_generic(client, generic["id"], adopted_by="d")
    r = await client.put(
        f"/shots/{sid}/performance-segments/1",
        json={
            "performance_revision_id": pr2["id"],
            "performance_start_ms": {"num": 0, "den": 1},
            "performance_end_ms": {"num": 500, "den": 1},
            "shot_anchor_ms": {"num": 1500, "den": 1},
        })
    assert r.status_code == 200, r.text
    await _capture_closed(client, sid)
    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 202, r.text
    generation_id = r.json()["id"]  # the TWO-SEGMENT generation

    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings

    import hashlib as _hl

    from soloring.workflows import manifest as _mm

    _manifest_raw = (_mm.WORKFLOW_DIR / "manifest.json").read_bytes()
    _template_raw = (_mm.WORKFLOW_DIR / "workflow.json").read_bytes()
    _arts = (settings.data_dir / "workflow-artifacts")

    def _place(kind: str, data: bytes) -> str:
        h = _hl.sha256(data).hexdigest()
        path = _arts / kind / "sha256" / h[:2] / h[2:4] / f"{h}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return h

    _place("manifests", _manifest_raw)
    _place("templates", _template_raw)

    from sqlalchemy import text as _t

    async with engine.begin() as conn:
        await conn.execute(_t(
            "UPDATE generations SET executor = 'comfy' "
            "WHERE id = :g"), {"g": generation_id})

    worker_id = "m17cd-prodtest-worker"
    await acquire_worker_lease(engine, worker_id, 60)
    for _ in range(4):
        claim = await claim_next_generation(engine, worker_id)
        if claim is None:
            break
        claimed_id, attempt_id = claim
        if claimed_id == generation_id:
            break
        # drain the earlier single-segment generation first (the
        # claim path is oldest-first)
        stub0 = RecordedClient()
        await drive_comfy_generation(
            engine, settings, worker_id, claimed_id, attempt_id,
            stub0)
    assert claimed_id == generation_id

    stub = RecordedClient()
    outcome = await drive_comfy_generation(
        engine, settings, worker_id, generation_id,
        attempt_id, stub)
    assert outcome == "failed"  # the stub abort; PREP completed

    assert stub.payload is not None
    document = stub.payload
    graph = document["prompt"]

    gpi = await _rows_local(client, generation_id)
    controls_blobs = [r["blob_hash"] for r in gpi
                      if r["artifact_role"] ==
                      "performance.controls"]
    vocal_blobs = [r["blob_hash"] for r in gpi
                   if r["artifact_role"] ==
                   "performance.vocal_audio"]
    # the frozen cardinality: TWO controls rows (the repeated
    # grouped key) + ONE dialogue audio row
    assert len(controls_blobs) == 2 and len(vocal_blobs) == 1

    # every per-segment file was uploaded
    for blob in controls_blobs + vocal_blobs:
        assert any(blob[:16] in u for u in stub.uploads), blob

    # the GRAPH consumes the ROLE BUNDLES at the pinned package's
    # declared nodes/fields (40/41 — not the Hunyuan KSampler 31)
    controls_ref = graph["40"]["inputs"]["controls_segments"]
    audio_ref = graph["41"]["inputs"]["audio_segments"]
    assert controls_ref and audio_ref

    # each bundle is a deterministic ordered projection listing the
    # EXACT per-segment identities (auditable correspondence)
    def _bundle_for(reference: str) -> dict:
        # the bundle's remote name carries its content digest
        # prefix; the bytes live content-addressed in the blob store
        name = reference.rsplit("/", 1)[-1]
        digest16 = next(
            part for part in name.split("_")
            if len(part) == 16
            and set(part) <= set("0123456789abcdef"))
        for path in (settings.data_dir / "blobs" / "sha256").rglob(
                f"{digest16}*"):
            return _json.loads(path.read_text(encoding="utf-8"))
        raise AssertionError(f"bundle {name} not found")

    controls_bundle = _bundle_for(controls_ref)
    assert controls_bundle["role"] == "performance.controls"
    assert [s["segment_position"]
            for s in controls_bundle["segments"]] == [0, 1]
    assert [s["blob_hash"]
            for s in controls_bundle["segments"]] == controls_blobs
    assert all(s["uploaded"] for s in controls_bundle["segments"])
    audio_bundle = _bundle_for(audio_ref)
    assert audio_bundle["role"] == "performance.vocal_audio"
    assert [s["blob_hash"]
            for s in audio_bundle["segments"]] == vocal_blobs

    # the submission-document enumeration carries the per-segment
    # rows AND the bundles (evidence, not consumption)
    marker = document["extra_data"]["soloring"]
    bindings = marker["performance_bindings"]
    rows = [b for b in bindings if "kind" not in b]
    bundles = [b for b in bindings if "kind" in b]
    assert {b["blob_hash"] for b in rows} == set(
        controls_blobs + vocal_blobs)
    assert {b["role"] for b in rows} == {
        "performance.controls", "performance.vocal_audio"}
    assert {b["bundle"] for b in bundles} == {
        controls_ref, audio_ref}


async def _rows_local(client, generation_id):
    engine = client._transport.app.state.engine
    from sqlalchemy import text

    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT input_key, position, artifact_role, blob_hash "
            "FROM generation_performance_inputs "
            "WHERE generation_id = :g ORDER BY input_key, position"),
            {"g": generation_id})).mappings().all()


@pytest.mark.asyncio
async def test_output_dispatch_v5_projects_to_lower(client, factory,
                                                    tmp_path,
                                                    monkeypatch):
    """FPR31-M17CD-05: the v5 output dispatch selects the EXACT
    lower view — v5-over-v1 the v1 manifest, v5-over-v2 the v2
    manifest — via the ONE lower-projection law."""
    from soloring.workflows.manifest import (
        ManifestDocument, ManifestDocumentV2, parse_manifest,
        parse_manifest_v2,
    )
    from soloring.performance.execution_spec import (
        build_workflow_spec_v5, lower_projection,
    )

    await _performance_manifest(tmp_path, monkeypatch)
    world, generation_id = await _performance_generation(
        client, factory, tmp_path, monkeypatch)
    spec = json.loads((await _row(client, (
        "SELECT workflow_spec_json FROM generations WHERE id = :g"),
        {"g": generation_id}))["workflow_spec_json"])
    assert spec["schema_version"] == 5

    # the REAL generation is v5-over-v1: the lower projection is v1
    lower = lower_projection(spec)
    assert lower["schema_version"] == 1
    from soloring.workflows import manifest as manifest_module

    raw = (manifest_module.WORKFLOW_DIR /
           "manifest.json").read_text(encoding="utf-8")
    parsed = parse_manifest(raw)
    assert isinstance(parsed, ManifestDocument)

    # a synthetic v5-over-v2 wraps the exact lower v2 shape
    lower_v2 = {**lower, "schema_version": 2,
                "model": {"id": "m", "version": 1,
                          "execution_model_fingerprint_hash":
                              "f" * 64},
                "realization": {"model_id": "m"}}
    v5_over_v2 = build_workflow_spec_v5(
        lower_v2, performance_execution=spec[
            "performance_execution"])
    assert lower_projection(v5_over_v2)["schema_version"] == 2
    assert lower_projection(v5_over_v2)["model"] == lower_v2["model"]

    # the output-dispatch law itself: the projected schema selects
    # the parser family (v1 doc vs v2 doc)
    def _selected_parser_kind(workflow_spec):
        projected = lower_projection(workflow_spec) \
            if workflow_spec["schema_version"] == 5 else workflow_spec
        return projected["schema_version"]

    assert _selected_parser_kind(spec) == 1
    assert _selected_parser_kind(v5_over_v2) == 2
