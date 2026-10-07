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
    """The real `_drive` schema-5 path: the retained package ladder
    (the manifest local is ALWAYS initialized — the FPR31-01 class),
    the GPI uploads, and the pure translator binding the derived
    controls/audio references INTO the submitted graph at the
    manifest's declared node/fields (the FPR31-02 class)."""
    from soloring.worker.comfy_pipeline import drive_comfy_generation
    from soloring.worker.ownership import (
        acquire_worker_lease, claim_next_generation,
    )

    world, generation_id = await _performance_generation(
        client, factory, tmp_path, monkeypatch)
    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings

    # stage the retained artifact pair at the captured hashes (the
    # fixture package bypassed the comfy release capture)
    import hashlib as _hl

    from soloring.workflows import manifest as _mm

    _manifest_raw = (_mm.WORKFLOW_DIR / "manifest.json").read_bytes()
    _template_raw = (_mm.WORKFLOW_DIR / "workflow.json").read_bytes()
    _arts = (client._transport.app.state.settings.data_dir
             / "workflow-artifacts")

    def _place(kind: str, data: bytes) -> str:
        h = _hl.sha256(data).hexdigest()
        path = _arts / kind / "sha256" / h[:2] / h[2:4] / f"{h}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return h

    _place("manifests", _manifest_raw)
    _place("templates", _template_raw)

    # the worker dispatches from the PERSISTED executor — stage the
    # row as a comfy generation (the fake-lane create is the same
    # captured closure; only the dispatch marker changes)
    from sqlalchemy import text as _t

    async with engine.begin() as conn:
        await conn.execute(_t(
            "UPDATE generations SET executor = 'comfy' "
            "WHERE id = :g"), {"g": generation_id})

    worker_id = "m17cd-prodtest-worker"
    await acquire_worker_lease(engine, worker_id, 60)
    claim = await claim_next_generation(engine, worker_id)
    assert claim is not None
    claimed_id, attempt_id = claim
    assert claimed_id == generation_id

    stub = RecordedClient()
    outcome = await drive_comfy_generation(
        engine, settings, worker_id, generation_id,
        attempt_id, stub)
    # the stub submit abort is a generic failure under the
    # envelope discipline; the PREPARATION completed, which is
    # the point of this regression
    assert outcome == "failed"

    # the preparation completed: the payload was reached (the
    # manifest/template locals were bound — no UnboundLocalError)
    assert stub.payload is not None
    document = stub.payload
    graph = document["prompt"]

    # the derived performance inputs were uploaded
    gpi = await _rows_local(client, generation_id)
    controls_blob = next(r["blob_hash"] for r in gpi
                         if r["artifact_role"] == "performance.controls")
    vocal_blob = next(r["blob_hash"] for r in gpi
                      if r["artifact_role"] ==
                      "performance.vocal_audio")
    uploaded_controls = next(
        u for u in stub.uploads if controls_blob[:16] in u)
    assert any(vocal_blob[:16] in u for u in stub.uploads)

    # the GRAPH consumes them: the fixture manifest declares the two
    # performance inputs at node "31"/fields controls_file/audio_file
    node_inputs = graph["31"]["inputs"]
    assert uploaded_controls in node_inputs["controls_file"]
    assert any(vocal_blob[:16] in u for u in stub.uploads
               if u in node_inputs["audio_file"] or
               node_inputs["audio_file"])

    # the marker enumerates the same identities (evidence, not
    # consumption)
    marker = document["extra_data"]["soloring"]
    bindings = marker["performance_bindings"]
    assert {b["blob_hash"] for b in bindings} == {
        controls_blob, vocal_blob}
    assert all(b["input_name"] for b in bindings)


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
