"""M14B-5 — HIST:12 test (kept in its own module to avoid heredoc
mangling of the main history file)."""
from __future__ import annotations

from soloring.generation.service import create_generation_request
from sqlalchemy import text

from tests.test_m14_execution import (
    _comfy,
    _factory,
    _observation_package,
    _schema6_world,
    _stored_spec,
)


async def test_m14_hist_12_captured_contract_not_current(client, tmp_path):
    """HIST:12: historical provenance validates against the CAPTURED
    materializer contract; mutating the CURRENT contract builder does
    not invalidate the otherwise-valid historical load."""
    from soloring.observation.worker_inputs import (
        execute_schema4_derived_inputs,
    )

    b, _sel, revision, snapshot = await _schema6_world(
        client, tag=b"m14b5-hist12")
    pkg = await _observation_package(tmp_path)
    settings = _comfy(client, pkg)
    engine = client._transport.app.state.engine
    async with _factory(client)() as session:
        generation = await create_generation_request(
            session, b["shot"], settings=settings)
    spec = await _stored_spec(engine, generation.id)
    from soloring.observation.workflow_spec import parse_workflow_spec_v4

    spec4 = parse_workflow_spec_v4(spec)
    import json

    manifest_v3 = json.loads(
        (pkg / "manifest.json").read_text(encoding="utf-8"))

    class _Uploader:
        def __init__(self):
            self.uploads = []

        async def upload_bytes(self, *, data, filename, subfolder):
            self.uploads.append(filename)
            return filename, subfolder

        async def upload(self, *, source_path, filename, subfolder):
            self.uploads.append(filename)
            return filename, subfolder

    import soloring.observation.materializer as materializer_module

    original = materializer_module.build_materializer_contract

    def _changed_contract():
        base = original()
        base["runtime"]["numpy"] = "99.99.99-changed"
        return base

    materializer_module.build_materializer_contract = _changed_contract
    try:
        from soloring.assets.blob_store import BlobStore

        async with _factory(client)() as session:
            verified = await execute_schema4_derived_inputs(
                session, BlobStore(settings),
                generation_id=generation.id,
                attempt_id="attempt-hist12",
                workflow_spec_v4=spec4,
                manifest_v3=manifest_v3,
                client=_Uploader())
        assert verified, (
            "the historical load succeeds - the CAPTURED contract is "
            "the validity oracle, not today's")
    finally:
        materializer_module.build_materializer_contract = original
