"""M17C-D FPR34-06 — the terminal output resolution beyond
submission for BOTH lower forms on retained schema-3 packages
(non-live): a hermetic executor client ACCEPTS the submission
(persisting a recorded prompt id), reports a deterministic terminal
history carrying exactly ONE output at the LOWER-VIEW manifest's
declared video node/field (the real output-manifest projection of
the retained package — node 80/images under both v1 and v2 lower
forms), and streams deterministic bytes — driving the REAL
observation → history → ``resolve_comfy_outputs`` → output-import
path to a succeeded generation with the imported video:0 take."""

from __future__ import annotations

import hashlib
import json

import pytest

from tests.test_m17cd33_retained3 import (
    _schema3_v5_generation, _stage_schema5_runtime,
)

_OUTPUT_BYTES = (
    b"FPR34-06 deterministic terminal output bytes - the hermetic "
    b"/view stream for the retained-3 lower video contract")


class CompletingClient:
    """Hermetic Comfy client for the schema-5 retained-3 drives:
    uploads succeed locally-referenced, the submission is accepted
    exactly once with a deterministic prompt id, history reports
    the terminal record carrying the manifest's declared output,
    and /view streams deterministic bytes."""

    def __init__(self, output_node: str, output_field: str):
        self.prompt_id = "m34-terminal-prompt-1"
        self.payload = None
        self.uploads: list[str] = []
        self._node = output_node
        self._field = output_field
        self._marker = None

    async def aclose(self) -> None:
        return None

    async def system_stats(self) -> dict:
        return {}

    async def queue(self):
        return ()

    async def submit_prompt(self, payload_document):
        from soloring.executors.comfy.client import PromptAccepted

        self.payload = payload_document
        self._marker = (payload_document.get("extra_data")
                        or {}).get("soloring")
        return PromptAccepted(prompt_id=self.prompt_id)

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

    async def history(self, prompt_id=None):
        from soloring.executors.comfy.models import (
            JobState, NormalizedHistoryRecord,
            NormalizedOutputReference, SoloringMarker,
        )

        if prompt_id != self.prompt_id:
            return {}
        marker = None
        if self._marker:
            marker = SoloringMarker(
                generation_id=self._marker.get("generation_id"),
                attempt_id=self._marker.get("attempt_id"))
        return {self.prompt_id: NormalizedHistoryRecord(
            prompt_id=self.prompt_id,
            terminal_state=JobState.SUCCEEDED,
            outputs=(NormalizedOutputReference(
                node=self._node, output_field=self._field,
                filename="SoloringVideo_00001.webp", subfolder="",
                type="output"),),
            marker=marker,
        )}

    async def stream_view(self, filename, subfolder, output_type="output",
                          chunk_size=1 << 20):
        yield _OUTPUT_BYTES

    async def fetch_view(self, filename, subfolder, output_type="output"):
        return _OUTPUT_BYTES


async def _drive_to_completion(client, factory, tmp_path, monkeypatch,
                               *, v2: bool):
    from soloring.worker import ownership
    from soloring.worker.comfy_pipeline import drive_comfy_generation

    world, generation_id, spec, pkg = await _schema3_v5_generation(
        client, factory, tmp_path, v2=v2)
    fingerprint = pkg / "execution-model-fingerprint.json"
    await _stage_schema5_runtime(client, monkeypatch, fingerprint)

    # the lower-view manifest's DECLARED output contract (the real
    # projection of the retained package — not an assumption): the
    # completing client serves exactly this node/field
    from soloring.spatial.package3 import (
        parse_manifest_v3, project_lower_logical_execution_view,
    )

    # the RETAINED package's own documents (the pkg dir the capture
    # consumed), not the currently-installed workflow dir
    manifest_bytes = (pkg / "manifest.json").read_bytes()
    template_graph = json.loads(
        (pkg / "workflow.json").read_text(encoding="utf-8"))
    lower = project_lower_logical_execution_view(
        parse_manifest_v3(manifest_bytes.decode("utf-8")),
        template_graph, "0" * 64, "1" * 64,
        logical_schema_version=(2 if v2 else 1))
    (output_name, contract), = lower.manifest.outputs.items()
    assert output_name == "video" and contract.field == "images"

    import soloring.worker.comfy_pipeline as pipeline

    async def _cap(*a, **k):
        return object()  # the M10F hermetic precedent

    monkeypatch.setattr(pipeline, "resolve_capability", _cap)

    engine = client._transport.app.state.engine
    settings = client._transport.app.state.settings
    stub = CompletingClient(contract.node, contract.field)
    worker_id = "m34-terminal-worker"
    await ownership.acquire_worker_lease(engine, worker_id, 60)
    claim = await ownership.claim_next_generation(engine, worker_id)
    assert claim is not None
    claimed_id, attempt_id = claim
    assert claimed_id == generation_id
    outcome = await drive_comfy_generation(
        engine, settings, worker_id, claimed_id, attempt_id, stub)
    if outcome != "succeeded":  # disclose the refusal verbatim
        from sqlalchemy import text as _t

        async with engine.connect() as conn:
            err = (await conn.execute(_t(
                "SELECT error_code, error_message FROM generations "
                "WHERE id = :g"),
                {"g": claimed_id})).mappings().one()
        raise AssertionError(
            f"drive did not succeed ({outcome!r}): "
            f"{err['error_code']}: {err['error_message']}")
    return world, generation_id, spec, stub, outcome


async def _assert_terminal_import(client, generation_id, stub,
                                  outcome):
    from sqlalchemy import text

    assert outcome == "succeeded"
    engine = client._transport.app.state.engine
    async with engine.connect() as c:
        row = (await c.execute(text(
            "SELECT status, executor_job_id FROM generations "
            "WHERE id = :g"),
            {"g": generation_id})).mappings().one()
        take = (await c.execute(text(
            "SELECT t.output_key, a.blob_hash FROM takes t "
            "JOIN assets a ON a.take_id = t.id "
            "WHERE t.generation_id = :g"),
            {"g": generation_id})).first()
    # the RECORDED prompt id persisted on the generation row
    assert row["status"] == "succeeded"
    assert row["executor_job_id"] == stub.prompt_id
    # the output import: exactly the declared video contract, with
    # the streamed bytes' content address
    assert take is not None
    assert take.output_key == "video:0"
    assert take.blob_hash == hashlib.sha256(_OUTPUT_BYTES).hexdigest()
    # the submission document (the projected graph + the performance
    # bindings) was accepted by the executor
    assert stub.payload is not None
    bindings = stub.payload["extra_data"]["soloring"][
        "performance_bindings"]
    assert [b for b in bindings if "kind" in b]


@pytest.mark.asyncio
async def test_retained3_v5_over_v1_terminal_output_resolution(
        client, factory, tmp_path, monkeypatch):
    """v5-over-v1 on a retained schema-3 package driven BEYOND
    submission: the recorded prompt id persists, the terminal
    history resolves through the REAL lower-view output-manifest
    projection (node 80/images), and the output imports as the
    video:0 take with the streamed bytes' content address."""
    world, generation_id, spec, stub, outcome = (
        await _drive_to_completion(
            client, factory, tmp_path, monkeypatch, v2=False))
    assert spec["schema_version"] == 5
    assert "model" not in spec and "realization" not in spec  # v1
    await _assert_terminal_import(client, generation_id, stub, outcome)


@pytest.mark.asyncio
async def test_retained3_v5_over_v2_terminal_output_resolution(
        client, factory, tmp_path, monkeypatch):
    """v5-over-v2 on a retained schema-3 package — the SAME
    terminal-resolution law on the v2 lower form (the pointer
    reconstruction + the closure laws + the composed attestation
    all pass, then the submission → history → resolve → import)."""
    world, generation_id, spec, stub, outcome = (
        await _drive_to_completion(
            client, factory, tmp_path, monkeypatch, v2=True))
    assert spec["schema_version"] == 5
    assert "model" in spec and "realization" in spec  # v2 lower
    await _assert_terminal_import(client, generation_id, stub, outcome)
