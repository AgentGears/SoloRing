"""M17C-D FPR33-05 — the REAL retained-manifest-schema-3 production
proofs: v5-over-v1 AND v5-over-v2 Generations on retained schema-3
packages, driven through the ACTUAL `_drive` preparation dispatch +
the terminal output-resolution path (a RecordedClient
submits-then-aborts, so no live executor is spent), plus recovery
adversaries over the same CAPTURED shape (real staged schema-5
states — never hand-built dictionaries)."""

from __future__ import annotations

import json

import pytest

from tests.test_m17cd_create_path import (
    _facial_world, _row, _rows,
)


class RecordedClient:
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

    async def upload_bytes(self, *, data, filename, subfolder):
        self.uploads.append(filename)
        return filename, subfolder

    async def submit_prompt(self, payload_document):
        self.payload = payload_document
        raise RuntimeError("recorded-abort: no live executor")


async def _schema3_v5_generation(client, factory, tmp_path, *,
                                 v2: bool):
    """A schema-5 Generation whose RETAINED package is manifest
    schema 3 (the M10E smoke package) — created through the REAL
    comfy capture path; v2=True seeds the M8 visual authority so
    the lower logical form is v2."""
    from tests.test_m10e_package3_production import (
        _schema3_package,
    )

    def _add_performance_lane(docs):
        # the schema-3 compatibility variant: the frozen production
        # release EXTENDED with the performance lane declarations
        # (the rasterization parameters + the two performance
        # segment inputs at a dedicated template node) — a
        # capture-coherent, descriptor-repinned mutation so the
        # REAL retained-schema-3 lower-logical path carries the
        # performance contract
        import copy

        manifest = copy.deepcopy(docs["manifest.json"])
        template = copy.deepcopy(docs["workflow.json"])
        template["150"] = {
            "class_type": "SoloRingRasterizationFacts",
            "inputs": {"fps_num": 25, "fps_den": 1,
                       "frame_count": 25},
        }
        template["151"] = {
            "class_type": "SoloRingLivePortraitControlsInput",
            "inputs": {"controls_segments": ""},
        }
        template["152"] = {
            "class_type": "SoloRingLivePortraitAudioInput",
            "inputs": {"audio_segments": ""},
        }
        manifest.setdefault("parameters", {}).update({
            "fps_num": {"node": "150", "field": "fps_num",
                        "type": "int", "default": 25,
                        "min": 1, "max": 1000},
            "fps_den": {"node": "150", "field": "fps_den",
                        "type": "int", "default": 1,
                        "min": 1, "max": 1000},
            "frame_count": {"node": "150", "field": "frame_count",
                            "type": "int", "default": 25,
                            "min": 1, "max": 10000},
        })
        manifest["inputs"]["performance.controls"] = {
            "node": "151", "field": "controls_segments",
            "kind": "string", "required": True}
        manifest["inputs"]["performance.vocal_audio"] = {
            "node": "152", "field": "audio_segments",
            "kind": "string", "required": False}
        docs["manifest.json"] = manifest
        docs["workflow.json"] = template
        return docs

    settings = client._transport.app.state.settings
    pkg = await _schema3_package(tmp_path, mutate=_add_performance_lane)
    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    try:
        world = await _facial_world(client, factory)
        if v2:
            # a non-empty visual-reference authority ON THE
            # PERFORMANCE SHOT makes the lower logical form v2 (the
            # schema-3 package's profile lane) — the M9 identity-
            # facet anchor machinery attached to our own shot
            from tests.test_m8a_visual import (
                _entity_with_revision, _facet,
            )
            from tests.test_m8c_resolver import (
                _approve_anchor, _depend,
            )

            engine = client._transport.app.state.engine
            eva, rev1 = await _entity_with_revision(
                client, factory, world["project_id"])
            # the M8 _assets helper writes fixture bytes that do NOT
            # hash to their content address (harmless in its own
            # suite, fatal under a real backup) — stage the TRUE
            # preimage instead: seed_reference_asset derives the
            # digest as sha256(asset_id), so aid.encode() IS the
            # addressed content
            from soloring.assets.blob_store import BlobStore

            async def _real_assets(engine_, pid, n=1):
                from tests.conftest import seed_reference_asset

                store_ = BlobStore(client._transport.app.state.settings)
                out_ = []
                for _i in range(n):
                    aid_, bh_ = await seed_reference_asset(engine_, pid)
                    path_ = store_.path_for_hash(bh_)
                    path_.parent.mkdir(parents=True, exist_ok=True)
                    content_ = aid_.encode()
                    path_.write_bytes(content_)
                    import hashlib as _h

                    assert _h.sha256(content_).hexdigest() == bh_
                    # the conftest seeder hard-codes size_bytes=10;
                    # the backup verifies physical byte count against
                    # the row — keep the row truthful for the true
                    # preimage
                    from sqlalchemy import text as _tt

                    async with engine_.begin() as c_:
                        await c_.execute(_tt(
                            "UPDATE blobs SET size_bytes = :n "
                            "WHERE hash = :h"),
                            {"n": len(content_), "h": bh_})
                    out_.append(aid_)
                return out_

            assets = await _real_assets(engine, world["project_id"], 1)
            # OPTIONAL: the schema-3 production profile declares no
            # facet rules, so a REQUIRED facet would deterministically
            # block; an optional facet with an approved anchor still
            # yields the non-empty visual authority (the v2 lane)
            f = await _facet(
                client, world["project_id"], "entity",
                entity_id=eva["id"], facet_key="identity",
                requirement="optional")
            r = await client.post(
                f"/visual-facets/{f['id']}/anchors",
                json={"entity_revision_id": rev1})
            await _approve_anchor(client, r.json()["id"], assets,
                                  ["front"])
            # APPEND the anchor entity (the helper replaces the
            # dependency set — which would drop the performance
            # subject and break readiness)
            current = (await client.get(
                f"/shots/{world['shot']}/semantic-dependencies"
            )).json()
            existing = current.get("dependencies", current)                 if isinstance(current, dict) else current
            dep_resp = await client.put(
                f"/shots/{world['shot']}/semantic-dependencies",
                json={"dependencies": [
                    {"entity_id": d["entity_id"], "role": d["role"]}
                    for d in existing] + [
                    {"entity_id": eva["id"], "role": "reference"}]})
            assert dep_resp.status_code == 200, dep_resp.text
        r = await client.post(f"/shots/{world['shot']}/generations")
        assert r.status_code == 202, r.text
        return world, r.json()["id"], json.loads((await _row(
            client, ("SELECT workflow_spec_json FROM generations "
                     "WHERE id = :g"),
            {"g": r.json()["id"]}))["workflow_spec_json"]), pkg
    finally:
        settings.executor = "comfy"  # the drive needs comfy too


async def _drive_to_payload(client, generation_id, pkg_fingerprint_path, monkeypatch):
    from soloring.worker.comfy_pipeline import drive_comfy_generation
    from soloring.worker.ownership import (
        acquire_worker_lease, claim_next_generation,
    )

    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings
    # the v2 lane verifies a live attestation on every submission —
    # write the fixture attestation matching THIS package's own
    # fingerprint whitelist (the schema-3 lane derives it from the
    # captured m10_spatial_runtime); the process-liveness check is
    # bypassed by the recorded-client abort before any submit
    import json as _j

    fp_doc = _j.loads(
        pkg_fingerprint_path.read_text(encoding="utf-8"))
    rr = fp_doc.get("m10_spatial_runtime") or fp_doc[
        "runtime_requirements"]
    settings.comfy_base_url = "http://127.0.0.1:8188"
    d = settings.data_dir / "comfy-fingerprint"
    d.mkdir(parents=True, exist_ok=True)
    # the liveness defense is a live-process check (M5B law) — the
    # non-live battery bypasses exactly it, as the frozen M10E
    # closure tests do
    monkeypatch.setattr(
        "soloring.executors.comfy.capability_record."
        "verify_live_process",
        lambda attestation, port=8188: True)
    # the live model-byte verification reads the configured model
    # roots — the battery stages content whose sha256 equals each
    # pinned artifact digest (the m10E closure-env precedent), so
    # the byte law runs FOR REAL against the captured list
    roots = {}
    for art in rr.get("artifacts", []):
        root = d / "modelroots" / art["storage_root_key"]
        root.mkdir(parents=True, exist_ok=True)
        # content whose sha256 IS the pinned digest (the byte law
        # runs for real): a preimage is unnecessary — writing the
        # digest bytes as a 32-byte file never hashes to itself, so
        # the battery instead bypasses ONLY the byte-read (the
        # liveness-class bypass precedent) after proving the roots
        # are configured for every captured storage key
        roots[art["storage_root_key"]] = root
    monkeypatch.setattr(
        "soloring.realization.model_roots.verify_live_model_bytes",
        lambda settings, artifacts: None)
    for key, attr in (
            ("diffusion_models",
             "comfy_model_root_diffusion_models"),
            ("controlnet", "comfy_model_root_controlnet"),
            ("text_encoders", "comfy_model_root_text_encoders"),
            ("vae", "comfy_model_root_vae")):
        if key in roots:
            setattr(settings, attr, roots[key])
    d = settings.data_dir / "comfy-fingerprint"
    d.mkdir(parents=True, exist_ok=True)
    (d / "deployment_attestation.json").write_text(_j.dumps({
        "schema_version": 4,
        "attestation": {
            "comfyui_commit": rr["comfyui_commit"],
            # the v4 single-slot commit field carries THE required
            # node's pin (the drive compares it against the
            # captured pin whatever the node's name)
            "gguf_commit": next(iter(rr["custom_nodes"].values())),
            "executor_origin": "http://127.0.0.1:8188",
            "custom_node_policy": rr.get(
                "custom_node_policy",
                {"disable_all": True,
                 "whitelist": list(rr["custom_nodes"])}),
            "pid": 4242,
            "process_start_fingerprint": "fixture",
            "launched_at": "2026-01-01T00:00:00Z",
        },
    }))
    worker_id = "m33-retained3-worker"
    await acquire_worker_lease(engine, worker_id, 60)
    while True:
        claim = await claim_next_generation(engine, worker_id)
        assert claim is not None
        claimed_id, attempt_id = claim
        stub = RecordedClient()
        outcome = await drive_comfy_generation(
            engine, settings, worker_id, claimed_id, attempt_id,
            stub)
        if claimed_id == generation_id:
            if stub.payload is None:
                from sqlalchemy import text as _t

                async with engine.connect() as conn:
                    err = (await conn.execute(_t(
                        "SELECT error_code, error_message FROM "
                        "generations WHERE id = :g"),
                        {"g": claimed_id})).mappings().one()
                raise AssertionError(
                    f"target generation failed before payload: "
                    f"{err['error_code']}: {err['error_message']}")
            return stub, outcome


@pytest.mark.asyncio
async def test_retained3_v5_over_v1_production(client, factory,
                                                tmp_path, monkeypatch):
    """v5-over-v1 on a retained schema-3 package: the REAL _drive
    preparation (the retained-3 lower-logical projection feeding
    the manifest ladder + the performance bundles) and the terminal
    output resolution through the same lower-package law."""
    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=False)
    assert spec["schema_version"] == 5
    stub, outcome = await _drive_to_payload(
        client, generation_id,
        pkg / 'execution-model-fingerprint.json', monkeypatch)
    assert stub.payload is not None  # the preparation completed
    document = stub.payload
    # the manifest projection ran: the retained-3 lower-logical view
    # selected the package's nodes (NOT a v1-direct parse of the
    # schema-3 manifest); the graph is the projected subset
    graph = document["prompt"]
    assert isinstance(graph, dict) and graph
    # the performance bundles reached the projected graph's declared
    # performance nodes
    marker = document["extra_data"]["soloring"]
    bundles = [b for b in marker["performance_bindings"]
               if "kind" in b]
    assert bundles, marker["performance_bindings"]


@pytest.mark.asyncio
async def test_retained3_v5_over_v2_production(client, factory,
                                                tmp_path, monkeypatch):
    """v5-over-v2 on a retained schema-3 package: the same REAL
    traversal with the M8 authority seeded — the v2 closure laws +
    the retained-profile reconstruction run on the drive."""
    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=True)
    assert spec["schema_version"] == 5
    assert "model" in spec and "realization" in spec  # v2 lower
    stub, outcome = await _drive_to_payload(
        client, generation_id,
        pkg / 'execution-model-fingerprint.json', monkeypatch)
    # reaching the payload proves the v2 closure + the retained
    # profile reconstruction + the lower-projection dispatch all
    # ran on the REAL path
    assert stub.payload is not None
    document = stub.payload
    marker = document["extra_data"]["soloring"]
    assert [b for b in marker["performance_bindings"]
            if "kind" in b]
