"""M3A — FakeExecutor happy path behind Hard Gate A.

Covers the reviewer-pinned invariants: capture-at-creation (incl. the strict
freeze test), transactional/exclusive claim, FakeExecutor-only boundary,
staging-vs-import authority, complete Take provenance, approval that never
rewrites creative state, idempotent import/approval, distinguishable failure
states, and the first real-provenance exercise of the M2A comparison.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate, ShotPatch
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.base import ExecutionStatus
from soloring.executors.fake import FakeExecutor, fake_output_bytes
from soloring.settings import Settings
from soloring.worker import execution as worker_execution
from soloring.worker.ownership import claim_next_generation
from tests.conftest import create_project, create_shot, seed_reference_asset

PNG = b"\x89PNG\r\n\x1a\n" + b"reference-for-generation"


async def _seed(factory, engine, client_factory=None):
    """Project + shot + one reference attached; returns (shot_id, asset_id)."""
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva enters"))
    aid, bh = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")]
        )
    return shot.id, aid, pid


async def _create_generation(client, shot_id: str):
    r = await client.post(f"/shots/{shot_id}/generations")
    assert r.status_code == 202, r.text
    return r.json()


async def _run_with(engine, settings: Settings, worker_id: str, executor) -> str | None:
    from soloring.worker.ownership import acquire_worker_lease

    await acquire_worker_lease(engine, worker_id, 30)  # claim needs authority
    return await worker_execution.process_next_generation(
        engine, settings, worker_id, executor
    )


async def _run_one(engine, settings: Settings, worker_id="w-test") -> str | None:
    return await _run_with(engine, settings, worker_id, FakeExecutor())


# --- generation creation: capture semantics ---------------------------------


async def test_generation_captures_everything_at_creation(client, factory, engine):
    sid, aid, pid = await _seed(factory, engine)
    gen = await _create_generation(client, sid)

    assert gen["status"] == "queued"
    assert gen["executor"] == "fake"
    assert gen["operation"] == "generate"
    assert gen["generation_number"] == 1
    assert gen["compiled_prompt"] == "Subject: Eva enters"

    async with factory() as s:
        rows = (await s.execute(text(
            "SELECT compiled_prompt, prompt_compiler_version, parameters_json, "
            "workflow_spec_json, workflow_spec_hash, manifest_hash, "
            "workflow_template_hash FROM generations WHERE id=:g"
        ), {"g": gen["id"]})).mappings().one()
        inputs = (await s.execute(text(
            "SELECT input_key, asset_id, position FROM generation_inputs "
            "WHERE generation_id=:g"
        ), {"g": gen["id"]})).all()

    assert rows.prompt_compiler_version == "1"
    assert json.loads(rows.parameters_json) == {"cfg": 1.0, "steps": 30}
    spec = json.loads(rows.workflow_spec_json)
    assert spec["schema_version"] == 1
    assert spec["prompt"] == "Subject: Eva enters"
    assert spec["inputs"]["reference_image"]["bindings"][0]["asset_id"] == aid
    assert len(rows.workflow_spec_hash) == 64
    assert len(rows.manifest_hash) == 64
    assert len(rows.workflow_template_hash) == 64
    assert [(i.input_key, i.asset_id, i.position) for i in inputs] == [
        ("reference_image", aid, 0)
    ]


async def test_cardinality_rejected_without_references(client, factory, engine):
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="no refs"))
    r = await client.post(f"/shots/{shot.id}/generations")
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == ErrorCode.WORKFLOW_INPUT_CARDINALITY_INVALID


async def test_second_generation_reuses_identical_revision(client, factory, engine):
    sid, aid, pid = await _seed(factory, engine)
    g1 = await _create_generation(client, sid)
    g2 = await _create_generation(client, sid)
    assert g1["shot_revision_id"] == g2["shot_revision_id"]
    assert g2["generation_number"] == 2


# --- STRICT freeze test (reviewer-pinned) ------------------------------------


async def test_take_derives_from_captured_revision_not_current_state(
    client, factory, engine, settings
):
    """Freeze: create the Generation, mutate the Shot BEFORE execution runs,
    then prove the produced Take derives exclusively from the captured
    revision and original compiler output."""
    sid, aid, pid = await _seed(factory, engine)
    gen = await _create_generation(client, sid)

    # Capture the execution identity at creation time.
    async with factory() as s:
        captured = (await s.execute(text(
            "SELECT shot_revision_id, compiled_prompt, workflow_spec_hash "
            "FROM generations WHERE id=:g"
        ), {"g": gen["id"]})).mappings().one()

    # MUTATE the mutable Shot AFTER creation, BEFORE the worker runs.
    other_aid, _ = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await shots.patch_shot(s, sid, ShotPatch(subject="TOTALLY DIFFERENT"))
        await references.replace_references(
            s, sid, [ReferenceInput(asset_id=other_aid, role="style")]
        )

    # Execute the claimed generation with the worker.
    outcome = await _run_one(engine, settings)
    assert outcome == "succeeded"

    async with factory() as s:
        after = (await s.execute(text(
            "SELECT shot_revision_id, compiled_prompt, status FROM generations "
            "WHERE id=:g"
        ), {"g": gen["id"]})).mappings().one()
        take = (await s.execute(text(
            "SELECT id, output_key FROM takes WHERE generation_id=:g"
        ), {"g": gen["id"]})).mappings().one()
        asset_blob = (await s.execute(text(
            "SELECT b.hash FROM takes t "
            "JOIN assets a ON a.take_id = t.id "
            "JOIN blobs b ON b.hash = a.blob_hash "
            "WHERE t.id = :t"
        ), {"t": take.id})).mappings().one()

    # Execution consumed the CAPTURED identity, untouched by the mutation.
    assert after.shot_revision_id == captured.shot_revision_id
    assert after.compiled_prompt == captured.compiled_prompt == "Subject: Eva enters"
    assert after.status == "succeeded"
    assert take.output_key == "video:0"

    # Output bytes are a pure function of the captured workflow spec hash.
    import hashlib

    from soloring.assets.blob_store import BlobStore

    store = BlobStore(settings)
    physical = store.path_for_hash(asset_blob.hash)
    assert physical.exists()
    content = physical.read_bytes()
    assert content == fake_output_bytes(captured.workflow_spec_hash)
    assert content != fake_output_bytes("0" * 64)  # derived from THIS spec

    # The captured revision does NOT match the mutated working state.
    async with factory() as s:
        rev_hash = (await s.execute(text(
            "SELECT snapshot_hash FROM shot_revisions WHERE id=:r"
        ), {"r": captured.shot_revision_id})).scalar()
    from soloring.domain.shots import read_shot_detail
    from soloring.domain.snapshots import working_snapshot_hash

    shot_map, refs, _, _resolved, _eff, _ready = await read_shot_detail(engine, sid)
    assert working_snapshot_hash(shot_map, refs) != rev_hash


# --- worker happy path + claim exclusivity -----------------------------------


async def test_full_happy_path_status_sequence(client, factory, engine, settings):
    sid, aid, pid = await _seed(factory, engine)
    gen = await _create_generation(client, sid)

    assert await _run_one(engine, settings) == "succeeded"

    detail = (await client.get(f"/generations/{gen['id']}")).json()
    assert detail["status"] == "succeeded"
    assert detail["executor_job_id"].startswith("fake-")
    assert detail["progress_current"] == detail["progress_total"]
    assert detail["completed_at"] is not None
    assert detail["error_code"] is None

    takes = (await client.get(f"/shots/{sid}/takes")).json()
    assert len(takes) == 1
    assert takes[0]["output_key"] == "video:0"
    assert takes[0]["blob_url"].startswith("/blobs/")
    assert takes[0]["detected_media_type"] == "image/png"
    assert takes[0]["is_approved"] is False

    # Blob is servable with immutable cache headers and its bytes are the
    # deterministic function of the captured workflow spec hash.
    async with factory() as s:
        spec_hash = (await s.execute(text(
            "SELECT workflow_spec_hash FROM generations WHERE id=:g"
        ), {"g": gen["id"]})).scalar()
    r = await client.get(takes[0]["blob_url"])
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.content == fake_output_bytes(spec_hash)


async def test_claim_is_exclusive_between_workers(engine, settings, client, factory):
    sid, aid, pid = await _seed(factory, engine)
    await _create_generation(client, sid)

    # Two concurrent claims: exactly one gets the generation.
    from soloring.worker.ownership import acquire_worker_lease

    await acquire_worker_lease(engine, "worker-A", 30)
    a, b = await asyncio.gather(
        claim_next_generation(engine, "worker-A"),
        claim_next_generation(engine, "worker-A"),
    )
    assert sorted(x is not None for x in (a, b)) == [False, True]
    winner = a or b
    assert isinstance(winner[1], str) and len(winner[1]) == 36  # attempt id

    async with factory() as s:
        row = (await s.execute(text(
            "SELECT status, worker_id FROM generations WHERE shot_id=:s"
        ), {"s": sid})).mappings().one()
    assert row.status == "preparing"
    assert row.worker_id == "worker-A"


# --- import idempotency ------------------------------------------------------


async def test_reimport_creates_no_duplicates(client, factory, engine, settings):
    sid, aid, pid = await _seed(factory, engine)
    gen = await _create_generation(client, sid)
    assert await _run_one(engine, settings) == "succeeded"

    async with factory() as s:
        takes_before = (await s.execute(text("SELECT count(*) FROM takes"))).scalar()
        assets_before = (await s.execute(text("SELECT count(*) FROM assets"))).scalar()
        blobs_before = (await s.execute(text("SELECT count(*) FROM blobs"))).scalar()

    # Re-run import against freshly staged outputs (simulated retry).
    from soloring.assets.blob_store import BlobStore
    from soloring.executors.base import StagedOutput
    from soloring.generation.importer import import_staged_outputs
    from soloring.generation.repository import get_generation_full
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory2() as s:
        generation = await get_generation_full(s, gen["id"])
    staged = [StagedOutput(
        output_key="video:0",
        path=_restage(settings, gen["id"], generation.workflow_spec_hash),
        kind="video",
    )]
    imported = await import_staged_outputs(factory2, BlobStore(settings), generation, staged)
    assert imported == ["video:0"]

    async with factory() as s:
        takes_after = (await s.execute(text("SELECT count(*) FROM takes"))).scalar()
        assets_after = (await s.execute(text("SELECT count(*) FROM assets"))).scalar()
        blobs_after = (await s.execute(text("SELECT count(*) FROM blobs"))).scalar()
    assert takes_after == takes_before
    assert assets_after == assets_before
    assert blobs_after == blobs_before


def _restage(settings, generation_id: str, spec_hash: str):
    from pathlib import Path

    p = Path(settings.staging_dir) / generation_id / "video-0.tmp"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(fake_output_bytes(spec_hash))
    return p


# --- approval / canon — first REAL provenance for the M2A comparison --------


async def test_approve_edit_restore_canon_semantics(client, factory, engine, settings):
    sid, aid, pid = await _seed(factory, engine)
    await _create_generation(client, sid)
    assert await _run_one(engine, settings) == "succeeded"

    takes = (await client.get(f"/shots/{sid}/takes")).json()
    take_id = takes[0]["id"]

    # Approve real FakeExecutor take -> differs=false
    r = await client.post(f"/takes/{take_id}/approve")
    assert r.status_code == 200
    body = (await client.get(f"/shots/{sid}")).json()
    assert body["approved_take_id"] == take_id
    assert body["working_state_differs_from_approved"] is False

    # Approval did not rewrite creative state.
    assert body["subject"] == "Eva enters"

    # Idempotent approval.
    await client.post(f"/takes/{take_id}/approve")
    assert (await client.get(f"/shots/{sid}")).json()["approved_take_id"] == take_id

    # Edit -> differs=true
    async with factory() as s:
        await shots.patch_shot(s, sid, ShotPatch(subject="edited"))
    assert (await client.get(f"/shots/{sid}")).json()[
        "working_state_differs_from_approved"
    ] is True

    # Restore the EXACT approved canonical state -> differs=false again.
    async with factory() as s:
        await shots.patch_shot(s, sid, ShotPatch(subject="Eva enters"))
    assert (await client.get(f"/shots/{sid}")).json()[
        "working_state_differs_from_approved"
    ] is False


async def test_reject_clears_canon_atomically(client, factory, engine, settings):
    sid, aid, pid = await _seed(factory, engine)
    await _create_generation(client, sid)
    assert await _run_one(engine, settings) == "succeeded"
    takes = (await client.get(f"/shots/{sid}/takes")).json()
    take_id = takes[0]["id"]
    await client.post(f"/takes/{take_id}/approve")

    r = await client.post(f"/takes/{take_id}/reject")
    assert r.status_code == 200
    assert r.json()["approved_take_id"] is None
    body = (await client.get(f"/shots/{sid}")).json()
    assert body["approved_take_id"] is None
    assert body["working_state_differs_from_approved"] is False  # no canon again
    takes = (await client.get(f"/shots/{sid}/takes")).json()
    assert takes[0]["rejected_at"] is not None
    assert takes[0]["is_approved"] is False

    # Idempotent reject.
    await client.post(f"/takes/{take_id}/reject")
    assert (await client.get(f"/shots/{sid}")).json()["approved_take_id"] is None


async def test_take_missing_404(client):
    r = await client.post("/takes/00000000-0000-0000-0000-000000000000/approve")
    assert r.status_code == 404
    assert r.json()["error_code"] == "TAKE_NOT_FOUND"


# --- explicit approve/reject orderings (M3A review) --------------------------


async def test_reject_then_approve_is_conflict(client, factory, engine, settings):
    """reject → approve: AMENDED in M3B (explicit amendment to v0.1 §92,
    resolving the M3A-review disagreement): approving a rejected Take is a
    409 TAKE_REJECTED conflict — rejection and approval never silently
    reverse each other. Canon is untouched by the failed approve."""
    sid, aid, pid = await _seed(factory, engine)
    await _create_generation(client, sid)
    assert await _run_one(engine, settings) == "succeeded"
    take_id = (await client.get(f"/shots/{sid}/takes")).json()[0]["id"]

    await client.post(f"/takes/{take_id}/reject")
    assert (await client.get(f"/shots/{sid}/takes")).json()[0]["rejected_at"]

    r = await client.post(f"/takes/{take_id}/approve")
    assert r.status_code == 409
    assert r.json()["error_code"] == "TAKE_REJECTED"
    body = (await client.get(f"/shots/{sid}")).json()
    assert body["approved_take_id"] is None  # canon untouched by failed approve
    takes = (await client.get(f"/shots/{sid}/takes")).json()
    assert takes[0]["rejected_at"] is not None
    assert takes[0]["is_approved"] is False


async def test_approve_then_reject_unpromotes_atomically(client, factory, engine, settings):
    """approve → reject: the reviewer's allowed option — an explicit
    transactional unapprove + reject; canon is never left pointing at a
    rejected Take."""
    sid, aid, pid = await _seed(factory, engine)
    await _create_generation(client, sid)
    assert await _run_one(engine, settings) == "succeeded"
    take_id = (await client.get(f"/shots/{sid}/takes")).json()[0]["id"]
    await client.post(f"/takes/{take_id}/approve")

    r = await client.post(f"/takes/{take_id}/reject")
    assert r.status_code == 200
    body = (await client.get(f"/shots/{sid}")).json()
    assert body["approved_take_id"] is None  # canon cleared atomically
    takes = (await client.get(f"/shots/{sid}/takes")).json()
    assert takes[0]["rejected_at"] is not None
    assert takes[0]["is_approved"] is False  # no contradictory canon


async def test_concurrent_approval_ends_on_one_complete_valid_take(
    client, factory, engine, settings
):
    """Two concurrent approvals of different Takes: last-writer-wins is the
    accepted v0.1 policy, but the final canon must always identify exactly
    one complete valid Take of this Shot."""
    sid, aid, pid = await _seed(factory, engine)
    await _create_generation(client, sid)
    assert await _run_one(engine, settings) == "succeeded"
    await _create_generation(client, sid)
    assert await _run_one(engine, settings) == "succeeded"
    takes = (await client.get(f"/shots/{sid}/takes")).json()
    t1, t2 = takes[0]["id"], takes[1]["id"]

    r1, r2 = await asyncio.gather(
        client.post(f"/takes/{t1}/approve"),
        client.post(f"/takes/{t2}/approve"),
    )
    assert r1.status_code == r2.status_code == 200
    body = (await client.get(f"/shots/{sid}")).json()
    final = body["approved_take_id"]
    assert final in (t1, t2)  # exactly one winner, never a mixed state
    take_ids = {t["id"] for t in (await client.get(f"/shots/{sid}/takes")).json()}
    assert final in take_ids  # canon identifies a complete persisted Take
    assert body["working_state_differs_from_approved"] is False


# --- HTTP-level SSE wiring (finite terminal response) -------------------------


async def test_sse_endpoint_http_wiring(client, factory, engine, settings):
    sid, aid, pid = await _seed(factory, engine)
    gen = await _create_generation(client, sid)
    assert await _run_one(engine, settings) == "succeeded"

    # Terminal generations produce a finite SSE response the test transport
    # can buffer fully — proving the actual FastAPI wiring.
    r = await client.get(f"/generations/{gen['id']}/events")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-accel-buffering"] == "no"
    data_lines = [line for line in r.text.splitlines() if line.startswith("data: ")]
    assert len(data_lines) == 1  # one terminal event
    payload = json.loads(data_lines[0][6:])
    assert payload["status"] == "succeeded"
    assert payload["id"] == gen["id"]


# --- failure states distinguishable ------------------------------------------


async def test_executor_failure_is_explicit(client, factory, engine, settings):
    sid, aid, pid = await _seed(factory, engine)
    gen = await _create_generation(client, sid)

    # Fault: an executor whose job disappears mid-run -> interrupted,
    # distinguishable from validation/failed states.
    class LostExecutor(FakeExecutor):
        async def inspect(self, handle):
            from soloring.executors.base import ExecutionObservation

            return ExecutionObservation(status=ExecutionStatus.LOST)

    outcome = await _run_with(engine, settings, "w-lost", LostExecutor())
    assert outcome == "interrupted"
    detail = (await client.get(f"/generations/{gen['id']}")).json()
    assert detail["status"] == "interrupted"
    assert detail["error_code"] == "EXECUTOR_JOB_LOST"


# --- SSE is observation only --------------------------------------------------


async def _drain(generator, max_events: int | None = None, timeout: float = 5.0):
    """Consume an SSE generator with a hard deadline; None = until it ends."""
    events: list[dict] = []

    async def consume():
        async for raw in generator:
            for line in raw.splitlines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
                    if max_events is not None and len(events) >= max_events:
                        return

    await asyncio.wait_for(consume(), timeout=timeout)
    return events


async def test_sse_emits_immediately_then_terminal_event(client, factory, engine, settings):
    from soloring.api.generations import sse_events
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    sid, aid, pid = await _seed(factory, engine)
    gen = await _create_generation(client, sid)

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    # Non-terminal generation: the first event arrives immediately (no wait).
    first = await _drain(sse_events(factory2, 0.05, gen["id"]), max_events=1)
    assert first[0]["status"] == "queued"
    assert first[0]["id"] == gen["id"]

    # Terminal generation: exactly one final event, then the stream closes.
    assert await _run_one(engine, settings) == "succeeded"
    terminal = await _drain(sse_events(factory2, 0.05, gen["id"]))
    assert len(terminal) == 1
    assert terminal[0]["status"] == "succeeded"
    assert terminal[0]["progress_current"] == terminal[0]["progress_total"]


async def test_sse_unknown_generation(engine):
    from soloring.api.generations import sse_events
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    factory2 = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    events = await _drain(sse_events(factory2, 0.05, "00000000-0000-0000-0000-000000000000"))
    assert events[0]["error_code"] == "GENERATION_NOT_FOUND"
