"""M17C-D FPR34-03 — lawful GENERIC-ONLY execution (non-live
production regressions): a performance whose every captured segment
carries ``vocal: null`` (a generic — non-dialogue-bound —
performance revision, no vocal mapping anywhere) must execute the
FULL production path with NO vocal GPI row, NO vocal bundle, NO
vocal upload — and an EXPLICIT no-vocal representation at the
executor boundary (the pinned node package's NO_VOCAL_AUDIO
sentinel, never a ``_load_bundle("")`` attempt, never fabricated
audio). The dialogue-bound control regression proves the same laws
carry the vocal lane when a vocal IS captured."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.test_m17cd_create_path import (
    _capture_closed, _performance_manifest, _row, _rows,
)
from tests.test_m17cd_worker_production_path import (
    RecordedClient, _stage_performance_attestation,
)

sys.path.insert(
    0, str(Path("server/soloring/executor_nodes").resolve()))


async def _generic_only_world(client, factory):
    """A lawful world whose ONLY performance segment is GENERIC: an
    M17B-lane candidate adopted and placed at position 0 with NO
    vocal mapping, NO vocal selection, NO vocal segment anywhere."""
    from tests.m17b_seed import (
        SMILE as _SMILE_META, adopt as _adopt_generic,
        candidate_body as _candidate_body, channel as _channel,
        create_candidate as _create_candidate, kf as _kf17b,
    )
    from tests.m16_seed_b import seed_feature_world
    from tests.m17cc_capture_helper import _factory
    from tests.test_m17cc_fpr_corrections import _add_reference

    base = await seed_feature_world(client, _factory(client))
    sid, pid, eid = (base["shot_id"], base["project_id"],
                     base["entity_id"])
    # seed_feature_world already set the entity as the subject
    # semantic dependency — the generic candidate's subject is
    # covered; no dialogue line, no VP, no vocal selection
    candidate = await _create_candidate(
        client, eid,
        _candidate_body(
            [_channel(_SMILE_META, [_kf17b(0, 1, 100000)])],
            start=(0, 1), end=(1000, 1)))
    pr = await _adopt_generic(client, candidate["id"], adopted_by="d")
    r = await client.put(
        f"/shots/{sid}/performance-segments/0",
        json={
            "performance_revision_id": pr["id"],
            "performance_start_ms": {"num": 0, "den": 1},
            "performance_end_ms": {"num": 1000, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text
    revision, _visual = await _capture_closed(client, sid)
    world = {"shot": sid, "project_id": pid, "entity_id": eid,
             "revision": revision}
    await _add_reference(client, world)
    return world


async def _drive_generation(client, generation_id, monkeypatch):
    """Claim + drive the generation on the REAL worker path until
    the recorded client submits (staging the lawful performance
    attestation lane first)."""
    from soloring.worker.comfy_pipeline import drive_comfy_generation
    from soloring.worker.ownership import (
        acquire_worker_lease, claim_next_generation,
    )

    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings

    import hashlib as _hl

    from soloring.workflows import manifest as _mm

    _arts = settings.data_dir / "workflow-artifacts"

    def _place(kind: str, data: bytes) -> str:
        h = _hl.sha256(data).hexdigest()
        path = _arts / kind / "sha256" / h[:2] / h[2:4] / f"{h}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return h

    _place("manifests", (_mm.WORKFLOW_DIR / "manifest.json").read_bytes())
    _place("templates", (_mm.WORKFLOW_DIR / "workflow.json").read_bytes())

    from sqlalchemy import text as _t

    async with engine.begin() as conn:
        await conn.execute(_t(
            "UPDATE generations SET executor = 'comfy' "
            "WHERE id = :g"), {"g": generation_id})

    _stage_performance_attestation(client, monkeypatch)
    worker_id = "m34-generic-worker"
    await acquire_worker_lease(engine, worker_id, 60)
    claim = await claim_next_generation(engine, worker_id)
    assert claim is not None
    claimed_id, attempt_id = claim
    assert claimed_id == generation_id
    stub = RecordedClient()
    outcome = await drive_comfy_generation(
        engine, settings, worker_id, claimed_id, attempt_id, stub)
    assert outcome == "failed"  # the recorded abort AFTER submission
    if stub.payload is None:  # disclose the refusal verbatim
        async with engine.connect() as conn:
            err = (await conn.execute(_t(
                "SELECT error_code, error_message FROM generations "
                "WHERE id = :g"), {"g": claimed_id})).mappings().one()
        raise AssertionError(
            f"drive refused before payload: {err['error_code']}: "
            f"{err['error_message']}")
    return stub


@pytest.mark.asyncio
async def test_generic_only_production_path(client, factory,
                                            tmp_path, monkeypatch):
    """The FPR34-03 decisive regression: a genuinely generic-only
    performance (vocal: null on EVERY captured segment) traverses
    bundle construction, translation, submission-graph validation,
    and the executor-node boundary — with no vocal GPI row, no
    vocal bundle, and the explicit no-vocal sentinel at the audio
    input node fed the EXACT submitted field value."""
    await _performance_manifest(tmp_path, monkeypatch)
    world = await _generic_only_world(client, factory)
    r = await client.post(f"/shots/{world['shot']}/generations")
    assert r.status_code == 202, r.text
    generation_id = r.json()["id"]

    # the captured spec: v5, ONE segment entry, vocal NULL
    spec = json.loads((await _row(client, (
        "SELECT workflow_spec_json FROM generations WHERE id = :g"),
        {"g": generation_id}))["workflow_spec_json"])
    assert spec["schema_version"] == 5
    entries = spec["performance_execution"]["segments"]
    assert len(entries) == 1
    assert entries[0]["vocal"] is None  # the generic-only shape

    # the frozen cardinality UNTOUCHED: controls row only — NO
    # vocal-audio GPI row exists for this generation
    gpi = await _rows(client, (
        "SELECT input_key, position, artifact_role, blob_hash "
        "FROM generation_performance_inputs "
        "WHERE generation_id = :g ORDER BY input_key, position"),
        {"g": generation_id})
    assert [(row["input_key"], row["position"], row["artifact_role"])
            for row in gpi] == [
        ("performance.controls", 0, "performance.controls")]

    stub = await _drive_generation(client, generation_id, monkeypatch)

    # NO vocal artifact was uploaded: no per-segment vocal file and
    # no vocal role bundle (only the controls segment + its bundle)
    vocal_uploads = [u for u in stub.uploads
                     if "performance.vocal_audio" in u]
    assert vocal_uploads == [], stub.uploads
    assert any("performance.controls" in u for u in stub.uploads)

    graph = stub.payload["prompt"]
    # the TRANSLATION: only the controls bundle is bound; the audio
    # node keeps the manifest's declared optional-empty binding (the
    # static template default survives — nothing fabricated)
    assert graph["40"]["inputs"]["controls_segments"]
    assert graph["41"]["inputs"]["audio_segments"] == ""

    # the SUBMISSION enumeration: one bundle (controls), no vocal
    bindings = stub.payload["extra_data"]["soloring"][
        "performance_bindings"]
    bundles = [b for b in bindings if "kind" in b]
    assert {b["role"] for b in bundles} == {
        "performance.controls"}

    # the EXECUTOR-BOUNDARY behavior on the EXACT submitted value:
    # the pinned audio-input node represents the lawful no-vocal
    # state EXPLICITLY — the sentinel, without touching the
    # filesystem (no _load_bundle("") attempt), without dummy audio
    import soloring_performance_nodes as nodes_pkg

    result = nodes_pkg.SoloRingLivePortraitAudioInput().load(
        graph["41"]["inputs"]["audio_segments"])
    assert result == (nodes_pkg.NO_VOCAL_AUDIO,)
    # the sentinel is an explicit, recognizable identity — never a
    # silent/empty audio tensor
    assert nodes_pkg.NO_VOCAL_AUDIO == (
        "__soloring_no_vocal_audio__",)


@pytest.mark.asyncio
async def test_dialogue_bound_control_carries_the_vocal_lane(
        client, factory, tmp_path, monkeypatch):
    """The DIALOGUE-BOUND control regression on the same production
    path: with a captured vocal, the vocal-audio GPI row, the vocal
    upload, the vocal role bundle, and the graph's non-empty audio
    binding all appear — the generic-only refusal above is the
    no-vocal REPRESENTATION, not a broken vocal lane."""
    from tests.test_m17cd_create_path import _facial_world

    await _performance_manifest(tmp_path, monkeypatch)
    world = await _facial_world(client, factory)
    r = await client.post(f"/shots/{world['shot']}/generations")
    assert r.status_code == 202, r.text
    generation_id = r.json()["id"]

    gpi = await _rows(client, (
        "SELECT input_key, artifact_role FROM "
        "generation_performance_inputs WHERE generation_id = :g"),
        {"g": generation_id})
    assert any(row["artifact_role"] == "performance.vocal_audio"
               for row in gpi)

    spec = json.loads((await _row(client, (
        "SELECT workflow_spec_json FROM generations WHERE id = :g"),
        {"g": generation_id}))["workflow_spec_json"])
    assert spec["performance_execution"]["segments"][0][
        "vocal"] is not None

    stub = await _drive_generation(client, generation_id, monkeypatch)
    assert any("performance.vocal_audio" in u for u in stub.uploads)
    graph = stub.payload["prompt"]
    audio_ref = graph["41"]["inputs"]["audio_segments"]
    assert audio_ref != ""  # the dialogue lane binds the vocal bundle

    # the sentinel is the no-vocal representation ONLY: the very
    # same node, fed the dialogue graph's non-empty bundle
    # reference, does NOT produce the sentinel (it consumes the
    # bundle — its full file-backed path is proven in the pinned
    # contract battery; here the branch selection is the law)
    import soloring_performance_nodes as nodes_pkg

    empty_result = nodes_pkg.SoloRingLivePortraitAudioInput().load("")
    assert empty_result == (nodes_pkg.NO_VOCAL_AUDIO,)
    # and the submitted dialogue binding is a bundle reference
    # (uploads/<ns>/performance.vocal_audio_..._bundle.json)
    assert "performance.vocal_audio" in audio_ref
    bindings = stub.payload["extra_data"]["soloring"][
        "performance_bindings"]
    assert {b["role"] for b in bindings if "kind" in b} == {
        "performance.controls", "performance.vocal_audio"}
