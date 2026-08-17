"""Second re-audit remediation — the required adversarial matrix.

R1: lease lost immediately before /prompt          → POST count == 0
R2: lease lost before Fake cancel                  → cancel count == 0
R2: lease lost before Comfy targeted cancel        → remote cancel count == 0
R3: submission_possible + no prompt_id + user cancel → intent persisted,
    never terminalized as definitely-unsubmitted
R4: two expected outputs, second media-invalid     → zero Takes/Assets
R5: same output_key, concurrent different bytes    → integrity conflict,
    never silent overwrite
R6: long-but-legal remote filename                 → exact round-trip or
    explicit rejection, never truncation
R7: publication fence                              → attempt + importing
    state required
"""

from __future__ import annotations

import asyncio
import hashlib
import json

import httpx
import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.assets.blob_store import BlobStore
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.base import StagedOutput
from soloring.executors.comfy.client import ComfyClient
from soloring.executors.comfy.outputs import (
    OutputInvalid,
    fetch_output_to_staging,
)
from soloring.executors.comfy.wire import (
    ComfyResponseError,
    normalize_history_response,
    normalize_upload_response,
)
from soloring.generation.importer import (
    ImportFailure,
    PublicationNotFenced,
    import_staged_outputs,
)
from soloring.workflows.manifest import ExpectedOutput
from soloring.worker import ownership
from soloring.worker.comfy_cancellation import (
    CancellationConflict,
    reconcile_cancellation,
)
from soloring.worker.comfy_submission import (
    SubmissionConflict,
    run_comfy_submission,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"payload" * 8


async def _seed(client, factory, engine, settings, executor="fake",
                wf=None) -> dict:
    import soloring.api.generations as generations_api

    settings.executor = executor
    if executor == "comfy":
        monkey = wf  # caller handles WORKFLOW_DIR patching
    saved = generations_api.get_settings
    generations_api.get_settings = lambda: settings
    try:
        async with factory() as s:
            pid = (await projects.create_project(
                s, ProjectCreate(name="P"))).id
            shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva"))
        bh = hashlib.sha256(PNG).hexdigest()
        path = BlobStore(settings).path_for_hash(bh)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from soloring.db.models import Asset, Blob
        from soloring.domain.ids import new_uuid

        aid = new_uuid()
        f = async_sessionmaker(bind=engine, expire_on_commit=False,
                               class_=AsyncSession)
        async with f() as s:
            s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                       size_bytes=len(PNG), detected_media_type="image/png"))
            await s.flush()
            s.add(Asset(id=aid, project_id=pid, blob_hash=bh,
                        kind="reference"))
            await s.commit()
        async with f() as s:
            await references.replace_references(
                s, shot.id,
                [ReferenceInput(asset_id=aid, role="reference")],
            )
        r = await client.post(f"/shots/{shot.id}/generations")
        assert r.status_code == 202, r.text
        gid = r.json()["id"]
        async with f() as s:
            rev = (await s.execute(
                text("SELECT id FROM shot_revisions WHERE shot_id=:sid "
                     "ORDER BY revision_number DESC LIMIT 1"),
                {"sid": shot.id},
            )).scalar_one()
        return {"gid": gid, "shot_id": shot.id, "rev": rev}
    finally:
        generations_api.get_settings = saved


class _CancelDouble:
    """Comfy double with cancel instrumentation; prompt stays pending."""

    base_url = "http://comfy.test"

    def __init__(self):
        self.posts = 0
        self.interrupts = 0
        self.queue_deletes = 0
        self.pid = "prompt-0001"

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/upload/image":
            return httpx.Response(200, json={"name": "x.png",
                                             "subfolder": "ns"})
        if path == "/prompt":
            self.posts += 1
            return httpx.Response(200, json={"prompt_id": self.pid})
        if path == "/queue" and request.method == "GET":
            return httpx.Response(200, json={
                "queue_running": [], "queue_pending": [],
            })
        if path == "/queue" and request.method == "POST":
            self.queue_deletes += 1
            return httpx.Response(200, json={})
        if path == "/interrupt":
            self.interrupts += 1
            return httpx.Response(200, json={"accepted": True})
        if path.startswith("/history"):
            return httpx.Response(200, json={})
        return httpx.Response(404)

    def client(self, worker_id):
        return ComfyClient(self.base_url, worker_id, timeout=10.0,
                           transport=httpx.MockTransport(self.handler))


async def _authority_flipped(engine, settings, gid) -> str:
    """Age the lease + generation heartbeat; successor B takes authority."""
    from soloring.db.timeutil import db_now_minus_sql

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE worker_leases SET heartbeat_at = "
            + db_now_minus_sql(9999) + " WHERE name = 'generation-worker'"
        ))
        await conn.execute(text(
            "UPDATE generations SET heartbeat_at = "
            + db_now_minus_sql(9999) + " WHERE id = :g"), {"g": gid})
        await conn.exec_driver_sql("COMMIT")
    b = "w-successor"
    await ownership.acquire_worker_lease(
        engine, b, settings.worker_lease_ttl_seconds
    )
    return b


async def _persist_intent(engine, gid):
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE generations SET cancel_requested_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
            "cancel_reason = 'user request' WHERE id = :g"
        ), {"g": gid})
        await conn.exec_driver_sql("COMMIT")


async def _row(engine, gid, cols="status, cancel_requested_at, "
                                 "executor_submission_state, worker_id"):
    async with engine.connect() as conn:
        return dict((await conn.execute(
            text(f"SELECT {cols} FROM generations WHERE id=:g"),
            {"g": gid},
        )).mappings().one())


# --- R1 ------------------------------------------------------------------


async def test_lost_lease_before_prompt_blocks_post(
    client, factory, engine, settings, monkeypatch, tmp_path,
):
    from tests.test_audit_m4_m5a import _installed_copy
    from soloring.workflows import manifest as mm

    wf = _installed_copy(tmp_path)
    monkeypatch.setattr(mm, "WORKFLOW_DIR", wf)
    seed = await _seed(client, factory, engine, settings, executor="comfy")
    gid = seed["gid"]

    worker = "w-r1"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker)
    _, attempt = claim

    # Authority is lost at the final pre-POST gate.
    import soloring.worker.comfy_submission as sub_mod
    from soloring.worker.ownership import LeaseRetentionResult

    async def lost_refresh(engine_, wid):
        return LeaseRetentionResult.LOST

    monkeypatch.setattr(sub_mod, "refresh_worker_lease", lost_refresh)

    double = _CancelDouble()
    payload = {
        "prompt": {"4": {"class_type": "LoadImage",
                         "inputs": {"image": "x.png"}}},
        "extra_data": {"soloring": {"generation_id": gid,
                                    "attempt_id": attempt}},
        "client_id": worker,
    }
    with pytest.raises(SubmissionConflict):
        await run_comfy_submission(
            engine, settings, worker, gid, attempt, payload,
            double.client(worker),
        )
    await double.client(worker).aclose()

    # THE invariant: zero /prompt calls after lost authority.
    assert double.posts == 0


# --- R2: fake + comfy external cancellation fences -------------------------


async def test_lost_lease_before_fake_cancel_blocks_executor_cancel(
    client, factory, engine, settings,
):
    seed = await _seed(client, factory, engine, settings)
    gid = seed["gid"]

    worker = "w-r2f"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker)
    _, attempt = claim

    from soloring.executors.base import (
        CancelResult,
        ExecutionHandle,
        ExecutionObservation,
        ExecutionStatus,
    )
    from soloring.worker.execution import _cancel_if_requested

    calls = {"cancel": 0}

    class CountingExecutor:
        async def cancel(self, handle):
            calls["cancel"] += 1
            return CancelResult.CANCELLED

    handle = ExecutionHandle(kind="fake", job_id="job-1")
    await ownership.persist_owned_executor_handle(
        engine, worker, gid, handle.job_id, "{}"
    )

    await _authority_flipped(engine, settings, gid)
    await _persist_intent(engine, gid)

    outcome = await _cancel_if_requested(
        engine, worker, gid, CountingExecutor(), handle
    )
    assert outcome == "halt"
    assert calls["cancel"] == 0  # the external effect never happened


async def test_lost_lease_before_comfy_cancel_blocks_remote_cancel(
    client, factory, engine, settings, monkeypatch, tmp_path,
):
    from tests.test_audit_m4_m5a import _installed_copy
    from soloring.workflows import manifest as mm
    wf = _installed_copy(tmp_path)
    monkeypatch.setattr(mm, "WORKFLOW_DIR", wf)
    seed = await _seed(client, factory, engine, settings, executor="comfy")
    gid = seed["gid"]

    worker = "w-r2c"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker)
    _, attempt = claim

    # A submits (the ONE POST) and holds a confirmed pending prompt.
    double = _CancelDouble()
    payload = {
        "prompt": {"4": {"class_type": "LoadImage",
                         "inputs": {"image": "x.png"}}},
        "extra_data": {"soloring": {"generation_id": gid,
                                    "attempt_id": attempt}},
        "client_id": worker,
    }
    c = double.client(worker)
    prompt_id = await run_comfy_submission(
        engine, settings, worker, gid, attempt, payload, c,
    )
    assert prompt_id == double.pid
    assert double.posts == 1

    await _authority_flipped(engine, settings, gid)
    await _persist_intent(engine, gid)

    # Stale A attempts reconciliation under a TARGETED+retry-safe
    # capability (the destructive path): the remote effect must be refused.
    from soloring.executors.comfy.capabilities import (
        CancellationCapability,
        CancellationMode,
    )
    from soloring.executors.comfy.observe import DisappearanceTracker

    capability = CancellationCapability(
        mode=CancellationMode.TARGETED, targeting_key="prompt_id",
        retry_safety="safe",
    )

    with pytest.raises(CancellationConflict):
        await reconcile_cancellation(
            engine, worker, gid, attempt, prompt_id, c, capability,
            DisappearanceTracker(grace_seconds=0.1),
        )
    await c.aclose()

    # ZERO remote cancellation surface activity from the stale worker.
    assert double.interrupts == 0
    assert double.queue_deletes == 0
    assert double.posts == 1  # unchanged


# --- R3 ------------------------------------------------------------------


async def test_submission_possible_cancel_persists_intent_not_terminal(
    client, factory, engine, settings, monkeypatch, tmp_path,
):
    from tests.test_audit_m4_m5a import _installed_copy
    from soloring.workflows import manifest as mm
    from soloring.worker.ownership import (
        mark_submission_possible,
        persist_owned_executor_submission,
    )

    wf = _installed_copy(tmp_path)
    monkeypatch.setattr(mm, "WORKFLOW_DIR", wf)
    seed = await _seed(client, factory, engine, settings, executor="comfy")
    gid = seed["gid"]

    worker = "w-r3"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker)
    _, attempt = claim

    # The permit was durably consumed; the POST response never arrived.
    artifact = json.dumps({"prompt": {}, "extra_data": {}, "client_id": "x"})
    assert await persist_owned_executor_submission(
        engine, worker, gid, attempt, artifact,
        hashlib.sha256(artifact.encode()).hexdigest(),
    ) is ownership.OwnershipMutationResult.OK
    assert await mark_submission_possible(
        engine, worker, gid, attempt
    ) is ownership.SubmissionPermission.MAY_POST

    r = await client.post(f"/generations/{gid}/cancel")
    assert r.status_code == 200, r.text
    body = r.json()

    row = await _row(engine, gid)
    assert body["cancel_requested"] is True
    assert row["status"] == "preparing"  # NOT terminalized
    assert row["cancel_requested_at"] is not None
    assert row["executor_submission_state"] == "submission_possible"


# --- R4 ------------------------------------------------------------------


async def test_second_output_media_invalid_leaves_zero_takes(
    client, factory, engine, settings, tmp_path,
):
    seed = await _seed(client, factory, engine, settings)
    gid = seed["gid"]

    worker = "w-r4"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker)
    _, attempt = claim
    await ownership.transition_owned_generation(
        engine, worker, gid, "importing"
    )

    staging = tmp_path / "staging" / gid / attempt
    staging.mkdir(parents=True)
    good = staging / "video-0.staged"
    good.write_bytes(PNG)  # valid PNG
    bad = staging / "video-1.staged"
    bad.write_bytes(b"\xff\xd8\xff" + b"jpeg-bytes" * 8)  # not a PNG

    outputs = [ExpectedOutput(
        name="video", kind="video", expected_count=2,
        accepted_media_types=("image/png",),
    )]
    staged = [
        StagedOutput(output_key="video:0", path=good, kind="video"),
        StagedOutput(output_key="video:1", path=bad, kind="video"),
    ]
    from soloring.generation.repository import get_generation_full

    async with factory() as s:
        generation = await get_generation_full(s, gid)

    with pytest.raises(ImportFailure):
        await import_staged_outputs(
            factory, BlobStore(settings), generation, staged,
            expected_outputs=outputs, staging_directory=staging,
        )

    async with engine.connect() as conn:
        takes = (await conn.execute(text(
            "SELECT COUNT(*) FROM takes WHERE generation_id=:g"),
            {"g": gid})).scalar_one()
        assets = (await conn.execute(text(
            "SELECT COUNT(*) FROM assets WHERE kind='output'"))).scalar_one()
    assert takes == 0  # zero partial provenance
    assert assets == 0


# --- R5 ------------------------------------------------------------------


async def test_concurrent_conflicting_transfers_conflict_not_overwrite(
    tmp_path,
):
    from soloring.executors.comfy.outputs import ResolvedComfyOutput

    ref = ResolvedComfyOutput(
        output_key="video:0", logical_name="video", expected_kind="video",
        accepted_media_types=None, filename="out.webp", subfolder="",
    )

    def provider(content):
        state = {"pos": 0}

        def fetch(filename, subfolder, _read=1 << 20):
            data = content
            pos = state["pos"]
            if pos >= len(data):
                state["pos"] = 0
                return b""
            chunk = data[pos:pos + _read]
            state["pos"] = pos + len(chunk)
            return chunk

        return fetch

    a = provider(b"RIFF-AAAAAAAAAAAAAAAA")
    b = provider(b"RIFF-BBBBBBBBBBBBBBBB")

    results = await asyncio.gather(
        fetch_output_to_staging(a, ref, tmp_path),
        fetch_output_to_staging(b, ref, tmp_path),
        return_exceptions=True,
    )
    errors = [r for r in results if isinstance(r, OutputInvalid)]
    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(errors) == 1 and len(successes) == 1
    target = successes[0]
    content = target.read_bytes()
    # The staged artifact is EXACTLY the winner's verified bytes — never a
    # silent last-writer-wins blend or overwrite.
    assert content in (b"RIFF-AAAAAAAAAAAAAAAA", b"RIFF-BBBBBBBBBBBBBBBB")

    # Sequential divergence is equally refused; the target is not replaced.
    with pytest.raises(OutputInvalid):
        await fetch_output_to_staging(
            provider(b"RIFF-CCCCCCCCCCCCCCCC"), ref, tmp_path,
        )
    assert target.read_bytes() == content


# --- R6 ------------------------------------------------------------------


def test_long_legal_identity_round_trips_exactly_never_truncated():
    long_name = ("n" * 126) + ".png"  # 130 chars — legal (bound is 190)
    ref = normalize_upload_response({"name": long_name, "subfolder": "ns"})
    assert ref.name == long_name  # EXACT — not name[:120]
    assert ref.subfolder == "ns"

    from soloring.executors.comfy.input_materializer import (
        validate_returned_reference,
    )
    validate_returned_reference(ref.name, ref.subfolder, "ns")  # accepted

    # Oversized identity is rejected, never rewritten.
    with pytest.raises(ComfyResponseError):
        normalize_upload_response({"name": "x" * 2000, "subfolder": "ns"})

    node_key = "9" * 130
    hist = normalize_history_response({"p": {
        "prompt": [0, "p", {}, {}, []],
        "outputs": {node_key: {"gifs": [
            {"filename": "v.webp", "subfolder": "", "type": "output"}]}},
        "status": {"status_str": "completed", "messages": []},
    }})
    assert hist["p"].outputs[0].node == node_key  # binding identity exact


# --- R7 ------------------------------------------------------------------


async def test_publication_fence_requires_attempt_and_importing(
    client, factory, engine, settings, tmp_path,
):
    seed = await _seed(client, factory, engine, settings)
    gid = seed["gid"]

    worker = "w-r7"
    await ownership.acquire_worker_lease(
        engine, worker, settings.worker_lease_ttl_seconds
    )
    claim = await ownership.claim_next_generation(engine, worker)
    _, attempt = claim

    staging = tmp_path / "staging" / gid / attempt
    staging.mkdir(parents=True)
    out_file = staging / "video-0.staged"
    out_file.write_bytes(PNG)
    staged = [StagedOutput(output_key="video:0", path=out_file,
                           kind="video")]

    from soloring.generation.repository import get_generation_full

    async with factory() as s:
        generation = await get_generation_full(s, gid)
    blob_store = BlobStore(settings)
    outputs = [ExpectedOutput(name="video", kind="video",
                              expected_count=1, accepted_media_types=None)]

    # Wrong attempt: refused.
    await ownership.transition_owned_generation(
        engine, worker, gid, "importing"
    )
    with pytest.raises(PublicationNotFenced, match="stale attempt"):
        await import_staged_outputs(
            factory, blob_store, generation, staged,
            expected_outputs=outputs, staging_directory=staging,
            worker_id=worker, attempt_id="not-the-attempt",
        )

    # Wrong lifecycle state (submitted, not importing): refused. (The
    # first call's blob placement legitimately MOVED the staged file —
    # blob placement consumes the staging artifact — so re-stage first.)
    out_file.write_bytes(PNG)
    await ownership.transition_owned_generation(
        engine, worker, gid, "submitted"
    )
    with pytest.raises(PublicationNotFenced, match="importing"):
        await import_staged_outputs(
            factory, blob_store, generation, staged,
            expected_outputs=outputs, staging_directory=staging,
            worker_id=worker, attempt_id=attempt,
        )

    async with engine.connect() as conn:
        takes = (await conn.execute(text(
            "SELECT COUNT(*) FROM takes WHERE generation_id=:g"),
            {"g": gid})).scalar_one()
    assert takes == 0
