"""M17C-D FPR32-03..06 — the integrity-chain closure battery: the
vocal source-audio/sync-basis grounding, the stored-spec hash
authentication on every schema-5 worker path, and the exact
lower-v2 reconstruction (the realization parameter_overrides
tamper caught independently by the worker-side law)."""

from __future__ import annotations

import json

import pytest

from tests.test_m17cd_create_path import (
    _facial_world, _performance_manifest, _row, _rows,
)


async def _schema5_generation(client, factory, tmp_path, monkeypatch):
    await _performance_manifest(tmp_path, monkeypatch)
    world = await _facial_world(client, factory)
    r = await client.post(f"/shots/{world['shot']}/generations")
    assert r.status_code == 202, r.text
    spec = json.loads((await _row(client, (
        "SELECT workflow_spec_json FROM generations WHERE id = :g"),
        {"g": r.json()["id"]})).scalar() if False else
        (await _row(client, (
            "SELECT workflow_spec_json FROM generations "
            "WHERE id = :g"),
            {"g": r.json()["id"]}))["workflow_spec_json"])
    return world, r.json()["id"], spec


def _session_factory(client):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(
        client._transport.app.state.engine, expire_on_commit=False)


def _resign(spec):
    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )

    return cj(spec), ch(spec)


def _rewrite_spec(client, generation_id, spec):
    from sqlalchemy import text

    body, digest = _resign(spec)

    async def _run():
        engine = client._transport.app.state.engine
        async with engine.begin() as conn:
            await conn.execute(text(
                "UPDATE generations SET workflow_spec_json = :b, "
                "workflow_spec_hash = :h WHERE id = :g"),
                {"b": body, "h": digest, "g": generation_id})

    import asyncio

    return asyncio.get_event_loop().run_until_complete(_run()) \
        if False else _run()


class _NoUpload:
    async def upload(self, **kwargs):
        raise AssertionError("no upload may precede the refusal")

    async def upload_bytes(self, **kwargs):
        raise AssertionError("no upload may precede the refusal")


# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vocal_audio_blob_tamper_refused(client, factory,
                                               tmp_path, monkeypatch):
    """FPR32-05: a coherently rehashed spec carrying a WRONG
    source-audio identity refuses before any upload."""
    from soloring.errors import ErrorCode, SoloRingError
    from soloring.performance.worker_inputs import (
        execute_schema5_performance_inputs,
    )

    world, generation_id, spec = await _schema5_generation(
        client, factory, tmp_path, monkeypatch)
    vocal = spec["performance_execution"]["segments"][0]["vocal"]
    vocal["vocal_audio_blob_hash"] = "e" * 64
    await _rewrite_spec(client, generation_id, spec)

    from soloring.assets.blob_store import BlobStore

    factory_session = _session_factory(client)
    async with factory_session() as session:
        with pytest.raises(SoloRingError) as exc:
            await execute_schema5_performance_inputs(
                session, BlobStore(
                    client._transport.app.state.settings),
                generation_id=generation_id, attempt_id="a",
                workflow_spec=spec, client=_NoUpload())
    assert "vocal_audio_blob_hash" in exc.value.message or \
        "audio authority" in exc.value.message


@pytest.mark.asyncio
async def test_sync_basis_tamper_refused(client, factory, tmp_path,
                                         monkeypatch):
    from soloring.errors import ErrorCode, SoloRingError
    from soloring.performance.worker_inputs import (
        execute_schema5_performance_inputs,
    )

    world, generation_id, spec = await _schema5_generation(
        client, factory, tmp_path, monkeypatch)
    vocal = spec["performance_execution"]["segments"][0]["vocal"]
    vocal["synchronization_basis_version"] = 2
    await _rewrite_spec(client, generation_id, spec)

    from soloring.assets.blob_store import BlobStore

    factory_session = _session_factory(client)
    async with factory_session() as session:
        with pytest.raises(SoloRingError) as exc:
            await execute_schema5_performance_inputs(
                session, BlobStore(
                    client._transport.app.state.settings),
                generation_id=generation_id, attempt_id="a",
                workflow_spec=spec, client=_NoUpload())
    assert "synchronization_basis_version" in exc.value.message


@pytest.mark.asyncio
async def test_stored_spec_hash_refused_before_submission(
        client, factory, tmp_path, monkeypatch):
    """FPR32-06: a schema-5 Generation whose stored spec bytes/hash
    disagree refuses BEFORE upload, translation, or submission —
    on the REAL drive path."""
    from soloring.worker.comfy_pipeline import drive_comfy_generation
    from soloring.worker.ownership import (
        acquire_worker_lease, claim_next_generation,
    )

    world, generation_id, spec = await _schema5_generation(
        client, factory, tmp_path, monkeypatch)
    # a coherent spec rewrite whose BYTES were never persisted
    # (the row keeps the ORIGINAL hash)
    from soloring.domain.canonical import canonical_json_str

    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings
    from sqlalchemy import text

    # stage the retained pinned-package artifacts (the drive fetches
    # them by captured hash BEFORE the spec check)
    import hashlib as _hl

    from soloring.workflows import manifest as _mm

    _arts = (settings.data_dir / "workflow-artifacts")

    def _place(kind, data):
        h = _hl.sha256(data).hexdigest()
        path = _arts / kind / "sha256" / h[:2] / h[2:4] / f"{h}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    _place("manifests", (_mm.WORKFLOW_DIR /
                        "manifest.json").read_bytes())
    _place("templates", (_mm.WORKFLOW_DIR /
                         "workflow.json").read_bytes())

    mutated = json.loads(json.dumps(spec))
    mutated["performance_execution"]["rasterization"][
        "frame_count"] = 99
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE generations SET workflow_spec_json = :b "
            "WHERE id = :g"),
            {"b": canonical_json_str(mutated), "g": generation_id})
    async with engine.begin() as conn:
        await conn.execute(text(
            "UPDATE generations SET executor = 'comfy' "
            "WHERE id = :g"), {"g": generation_id})

    worker_id = "m17cd32-hash-worker"
    await acquire_worker_lease(engine, worker_id, 60)
    claim = await claim_next_generation(engine, worker_id)
    assert claim is not None
    claimed_id, attempt_id = claim

    class _Explode:
        async def upload(self, **kwargs):
            raise AssertionError("upload reached despite bad hash")

        async def upload_bytes(self, **kwargs):
            raise AssertionError("upload reached despite bad hash")

    outcome = await drive_comfy_generation(
        engine, settings, worker_id, claimed_id, attempt_id,
        _Explode())
    assert outcome == "failed"
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT error_message FROM generations WHERE id = :g"),
            {"g": claimed_id})).scalar_one()
    assert "workflow spec bytes/hash" in str(row), row


@pytest.mark.asyncio
async def test_lower_v2_overrides_tamper_caught_by_law(
        tmp_path):
    """FPR32-04: the exact lower-v2 comparison law — a coherent
    mutation of realization.parameter_overrides refuses (never
    deleted-to-equality)."""
    from soloring.errors import SoloRingError
    from soloring.performance.execution_spec import compare_lower_v2

    def _pair():
        expected = {
            "schema_version": 2,
            "model": {"id": "m1", "version": 2,
                      "execution_model_fingerprint_hash":
                          "f" * 64},
            "realization": {
                "schema_version": 1,
                "profile": {"id": "p", "version": 1,
                            "hash": "a" * 64},
                "model": {"id": "m1", "version": 2,
                          "execution_model_fingerprint_hash":
                              "f" * 64},
                "parameter_overrides": {"cfg": 1.0},
            },
        }
        projection = json.loads(json.dumps(expected))
        return projection, expected

    projection, expected = _pair()
    compare_lower_v2(projection, expected, "unit")

    # a coherent mutation of the overrides
    bad = json.loads(json.dumps(projection))
    bad["realization"]["parameter_overrides"] = {"cfg": 9.0}
    with pytest.raises(SoloRingError) as exc:
        compare_lower_v2(bad, expected, "unit")
    assert "parameter_overrides" in exc.value.message

    # a profile-identity mutation
    bad2 = json.loads(json.dumps(projection))
    bad2["realization"]["profile"]["hash"] = "b" * 64
    with pytest.raises(SoloRingError):
        compare_lower_v2(bad2, expected, "unit")

    # a model-identity mutation
    bad3 = json.loads(json.dumps(projection))
    bad3["model"]["id"] = "other"
    with pytest.raises(SoloRingError):
        compare_lower_v2(bad3, expected, "unit")
