"""M6P — Exact Rerun closure tests (M6 plan §10–§15, §78; binding §13 rule).

The headline proof (§15): a rerun through the product API copies the source
Generation's historical ShotRevision and GenerationInputs verbatim while the
Shot's CURRENT creative state has demonstrably diverged. The binding §13
test proves the total initialization rule against a maximally poisoned
source: every attempt-scoped column populated on the source must initialize
fresh-queue on the rerun.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate, ShotPatch
from soloring.domain import projects, references, revisions, shots
from soloring.domain.ids import new_uuid
from soloring.executors.fake import FakeExecutor
from soloring.settings import Settings
from soloring.worker import execution as worker_execution
from soloring.worker.ownership import acquire_worker_lease
from tests.conftest import seed_reference_asset

HEX64 = "ab" * 32

# §12 durable historical specification columns (copied verbatim).
SPEC_COLUMNS = (
    "shot_id, shot_revision_id, executor, workflow_id, workflow_version, "
    "workflow_template_hash, manifest_hash, model, model_version, "
    "compiled_prompt, negative_prompt, prompt_compiler_version, seed, "
    "parameters_json, workflow_spec_json, workflow_spec_hash"
)

# The binding §13 total-initialization contract: every attempt-scoped column
# and its required fresh-queue value on a newly created rerun.
FRESH_STATE = {
    "status": "queued",
    "attempt_id": None,
    "executor_submission_state": "not_started",
    "submission_possible_at": None,
    "executor_submission_json": None,
    "executor_submission_hash": None,
    "executor_job_id": None,
    "executor_handle_json": None,
    "soft_cancel_selected_at": None,
    "cancel_requested_at": None,
    "cancel_reason": None,
    "claimed_at": None,
    "heartbeat_at": None,
    "worker_id": None,
    "progress_current": None,
    "progress_total": None,
    "current_node": None,
    "error_code": None,
    "error_message": None,
    "error_details_json": None,
    "started_at": None,
    "completed_at": None,
}


async def _seed(factory, engine, n_refs: int = 2):
    """Project + Shot + n_refs attached reference assets."""
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva enters"))
    refs = [await seed_reference_asset(engine, pid) for _ in range(n_refs)]
    async with factory() as s:
        await references.replace_references(
            s, shot.id,
            [ReferenceInput(asset_id=a, role="reference") for a, _ in refs],
        )
    return shot.id, pid, refs


async def _create_generation(client, shot_id: str) -> dict:
    r = await client.post(f"/shots/{shot_id}/generations")
    assert r.status_code == 202, r.text
    return r.json()


async def _run_one(engine, settings: Settings, worker_id="w-m6p") -> str | None:
    await acquire_worker_lease(engine, worker_id, 30)
    return await worker_execution.process_next_generation(
        engine, settings, worker_id, FakeExecutor()
    )


async def _fetch(engine, sql: str, params: dict) -> dict | None:
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), params)).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _fetch_all(engine, sql: str, params: dict) -> list[dict]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params)).mappings().all()
    return [dict(r) for r in rows]


async def _exec(engine, sql: str, params: dict) -> None:
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(sql), params)
        await conn.exec_driver_sql("COMMIT")


async def _set_status(engine, generation_id: str, status: str) -> None:
    await _exec(
        engine,
        "UPDATE generations SET status = :st, updated_at = "
        "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :gid",
        {"st": status, "gid": generation_id},
    )


async def _rerun(client, generation_id: str):
    return await client.post(f"/generations/{generation_id}/rerun")


def _inputs_of(rows: list[dict]) -> list[tuple]:
    return [
        (r["input_key"], r["reference_role"], r["position"], r["asset_id"],
         r["blob_hash"])
        for r in rows
    ]


# --- §15 headline: history copied, current state ignored ---------------------


async def test_rerun_headline_historical_copy_ignores_current_state(
    client, factory, engine, settings
):
    sid, pid, refs = await _seed(factory, engine, n_refs=1)
    gen_a = await _create_generation(client, sid)
    assert gen_a["status"] == "queued"

    driven = await _run_one(engine, settings)
    assert driven == "succeeded"
    row_a = await _fetch(
        engine,
        f"SELECT status, {SPEC_COLUMNS} FROM generations WHERE id = :g",
        {"g": gen_a["id"]},
    )
    assert row_a["status"] == "succeeded"

    # The revision the generation captured is still the current working one.
    async with factory() as s:
        rev_current = await revisions.capture_revision(s, sid)
    assert rev_current.id == gen_a["shot_revision_id"]

    # Diverge the CURRENT creative state: new subject + new reference set.
    third = await seed_reference_asset(engine, pid)
    r = await client.patch(
        f"/shots/{sid}", json=ShotPatch(subject="Eva leaves, soaked").model_dump(
            exclude_unset=True
        )
    )
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{sid}/references",
        json={"references": [{"asset_id": third[0], "role": "reference"}]},
    )
    assert r.status_code == 200, r.text
    async with factory() as s:
        rev_diverged = await revisions.capture_revision(s, sid)
    assert rev_diverged.id != rev_current.id  # current state genuinely moved

    r = await _rerun(client, gen_a["id"])
    assert r.status_code == 202, r.text
    gen_b = r.json()
    assert gen_b["status"] == "queued"
    assert gen_b["operation"] == "rerun"
    assert gen_b["generation_number"] == gen_a["generation_number"] + 1

    row_b = await _fetch(
        engine,
        f"SELECT {SPEC_COLUMNS}, rerun_of_generation_id FROM generations "
        "WHERE id = :g",
        {"g": gen_b["id"]},
    )
    for col in row_a:
        if col == "status":
            continue
        assert row_b[col] == row_a[col], f"spec column {col} not copied"
    assert row_b["rerun_of_generation_id"] == gen_a["id"]
    # Historical revision, not the diverged current one.
    assert row_b["shot_revision_id"] == rev_current.id
    # Historical prompt: the OLD subject is what executes.
    assert row_b["compiled_prompt"] == "Subject: Eva enters"

    inputs_a = _inputs_of(await _fetch_all(
        engine,
        "SELECT input_key, reference_role, position, asset_id, blob_hash "
        "FROM generation_inputs WHERE generation_id = :g "
        "ORDER BY input_key, position",
        {"g": gen_a["id"]},
    ))
    inputs_b = _inputs_of(await _fetch_all(
        engine,
        "SELECT input_key, reference_role, position, asset_id, blob_hash "
        "FROM generation_inputs WHERE generation_id = :g "
        "ORDER BY input_key, position",
        {"g": gen_b["id"]},
    ))
    assert len(inputs_a) == 1
    assert inputs_b == inputs_a  # exact copy of the historical binding set


# --- binding §13: total fresh-state initialization ---------------------------


async def test_rerun_fresh_state_total_rule_against_poisoned_source(
    client, factory, engine
):
    sid, pid, refs = await _seed(factory, engine, n_refs=1)
    gen_a = await _create_generation(client, sid)

    # A maximally poisoned terminal source: every attempt-scoped column set,
    # with all CHECK constraints satisfied (confirmed needs executor_job_id;
    # soft_cancel needs cancel intent).
    await _exec(
        engine,
        "UPDATE generations SET status='cancelled', attempt_id='attempt-old', "
        "executor_submission_state='confirmed', "
        "submission_possible_at='2026-01-01T00:00:00.000Z', "
        "executor_submission_json=:esj, "
        "executor_submission_hash=:h, executor_job_id='job-old', "
        "executor_handle_json=:ehj, "
        "soft_cancel_selected_at='2026-01-01T00:00:01.000Z', "
        "cancel_requested_at='2026-01-01T00:00:01.000Z', "
        "cancel_reason='user request', claimed_at='2026-01-01T00:00:02.000Z', "
        "heartbeat_at='2026-01-01T00:00:02.000Z', worker_id='w-old', "
        "progress_current=3, progress_total=10, current_node='k_sampler', "
        "error_code='X', error_message='m', error_details_json=:edj, "
        "started_at='2026-01-01T00:00:03.000Z', "
        "completed_at='2026-01-01T00:00:04.000Z' WHERE id = :g",
        {
            "g": gen_a["id"],
            "h": HEX64,
            "esj": '{"poison":1}',
            "ehj": '{"h":1}',
            "edj": '{"e":1}',
        },
    )

    r = await _rerun(client, gen_a["id"])
    assert r.status_code == 202, r.text
    gen_b = r.json()

    row = await _fetch(
        engine,
        "SELECT " + ", ".join(FRESH_STATE) + " FROM generations WHERE id = :g",
        {"g": gen_b["id"]},
    )
    for col, expected in FRESH_STATE.items():
        assert row[col] == expected, (
            f"attempt-scoped column {col} must initialize fresh "
            f"(expected {expected!r}, got {row[col]!r})"
        )


# --- §11 source-state matrix --------------------------------------------------


async def test_rerun_rejects_every_active_source_state(client, factory, engine):
    sid, pid, refs = await _seed(factory, engine, n_refs=1)
    gens = [await _create_generation(client, sid) for _ in range(5)]
    active = ["queued", "preparing", "submitted", "running", "importing"]
    for gen, st in zip(gens, active):
        if st != "queued":
            await _set_status(engine, gen["id"], st)

    for gen, st in zip(gens, active):
        r = await _rerun(client, gen["id"])
        assert r.status_code == 409, (st, r.text)
        assert r.json()["error_code"] == "GENERATION_ACTIVE"

    n = await _fetch(
        engine, "SELECT COUNT(*) AS n FROM generations", {}
    )
    assert n["n"] == 5  # no rerun row was ever created


async def test_rerun_allows_every_terminal_source_state(client, factory, engine):
    sid, pid, refs = await _seed(factory, engine, n_refs=1)
    gens = [await _create_generation(client, sid) for _ in range(4)]
    by_status = {}
    for gen, st in zip(
        gens, ["succeeded", "failed", "interrupted", "cancelled"]
    ):
        await _set_status(engine, gen["id"], st)
        by_status[st] = gen

    for st, gen in by_status.items():
        r = await _rerun(client, gen["id"])
        assert r.status_code == 202, (st, r.text)
        body = r.json()
        assert body["operation"] == "rerun"
        row = await _fetch(
            engine,
            "SELECT rerun_of_generation_id, shot_revision_id FROM generations "
            "WHERE id = :g",
            {"g": body["id"]},
        )
        assert row["rerun_of_generation_id"] == gen["id"]
        assert row["shot_revision_id"] == gen["shot_revision_id"]


# --- lookups ------------------------------------------------------------------


async def test_rerun_not_found_and_malformed(client, factory, engine):
    sid, pid, refs = await _seed(factory, engine, n_refs=1)
    r = await _rerun(client, str(new_uuid()))
    assert r.status_code == 404
    assert r.json()["error_code"] == "GENERATION_NOT_FOUND"

    r = await _rerun(client, "not-a-uuid")
    assert r.status_code == 404
    assert r.json()["error_code"] == "GENERATION_NOT_FOUND"


# --- historical availability under current-lifecycle deletion ------------------
# M6P gate review: rerun depends only on preserved historical state; a
# soft-deleted Shot (or its soft-deleting Project) still has full production
# history, so rerun must remain available.


async def test_rerun_available_after_mutation_and_shot_soft_deletion(
    client, factory, engine
):
    """The re-gate acceptance proof: diverge current state, delete the Shot,
    rerun from preserved history, and assert the full equality contract."""
    sid, pid, refs = await _seed(factory, engine, n_refs=1)
    gen_a = await _create_generation(client, sid)
    await _set_status(engine, gen_a["id"], "succeeded")
    row_a = await _fetch(
        engine,
        f"SELECT {SPEC_COLUMNS} FROM generations WHERE id = :g",
        {"g": gen_a["id"]},
    )

    third = await seed_reference_asset(engine, pid)
    r = await client.patch(
        f"/shots/{sid}", json=ShotPatch(subject="Eva leaves, soaked").model_dump(
            exclude_unset=True
        )
    )
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{sid}/references",
        json={"references": [{"asset_id": third[0], "role": "reference"}]},
    )
    assert r.status_code == 200, r.text
    await _exec(
        engine,
        "UPDATE shots SET deleted_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
        "WHERE id = :sid",
        {"sid": sid},
    )

    r = await _rerun(client, gen_a["id"])
    assert r.status_code == 202, r.text
    gen_b = r.json()
    assert gen_b["shot_id"] == gen_a["shot_id"]
    assert gen_b["generation_number"] == gen_a["generation_number"] + 1

    row_b = await _fetch(
        engine,
        f"SELECT {SPEC_COLUMNS}, rerun_of_generation_id FROM generations "
        "WHERE id = :g",
        {"g": gen_b["id"]},
    )
    for col in row_a:
        assert row_b[col] == row_a[col], f"spec column {col} not copied"
    assert row_b["rerun_of_generation_id"] == gen_a["id"]
    assert row_b["compiled_prompt"] == "Subject: Eva enters"  # historical prompt

    fresh = await _fetch(
        engine,
        "SELECT " + ", ".join(FRESH_STATE) + " FROM generations WHERE id = :g",
        {"g": gen_b["id"]},
    )
    for col, expected in FRESH_STATE.items():
        assert fresh[col] == expected, f"{col} not fresh: {fresh[col]!r}"

    inputs_a = _inputs_of(await _fetch_all(
        engine,
        "SELECT input_key, reference_role, position, asset_id, blob_hash "
        "FROM generation_inputs WHERE generation_id = :g "
        "ORDER BY input_key, position",
        {"g": gen_a["id"]},
    ))
    inputs_b = _inputs_of(await _fetch_all(
        engine,
        "SELECT input_key, reference_role, position, asset_id, blob_hash "
        "FROM generation_inputs WHERE generation_id = :g "
        "ORDER BY input_key, position",
        {"g": gen_b["id"]},
    ))
    assert inputs_b == inputs_a


async def test_rerun_available_after_project_soft_deletion(client, factory, engine):
    sid, pid, refs = await _seed(factory, engine, n_refs=1)
    gen_a = await _create_generation(client, sid)
    await _set_status(engine, gen_a["id"], "succeeded")

    r = await client.delete(f"/projects/{pid}")
    assert r.status_code == 204, r.text
    shot_row = await _fetch(
        engine, "SELECT deleted_at FROM shots WHERE id = :sid", {"sid": sid}
    )
    assert shot_row["deleted_at"] is not None  # cascade soft-deleted the Shot

    r = await _rerun(client, gen_a["id"])
    assert r.status_code == 202, r.text
    row_b = await _fetch(
        engine,
        "SELECT shot_id, shot_revision_id, rerun_of_generation_id, status "
        "FROM generations WHERE id = :g",
        {"g": r.json()["id"]},
    )
    assert row_b["shot_id"] == sid
    assert row_b["shot_revision_id"] == gen_a["shot_revision_id"]
    assert row_b["rerun_of_generation_id"] == gen_a["id"]
    assert row_b["status"] == "queued"


# --- numbering + concurrency ----------------------------------------------------


async def test_concurrent_reruns_get_distinct_numbers_and_full_copies(
    client, factory, engine
):
    sid, pid, refs = await _seed(factory, engine, n_refs=1)
    gen_a = await _create_generation(client, sid)
    await _set_status(engine, gen_a["id"], "succeeded")

    responses = await asyncio.gather(*(_rerun(client, gen_a["id"]) for _ in range(4)))
    assert all(r.status_code == 202 for r in responses), [r.text for r in responses]
    numbers = sorted(r.json()["generation_number"] for r in responses)
    assert numbers == [2, 3, 4, 5]
    ids = [r.json()["id"] for r in responses]
    assert len(set(ids)) == 4

    for gid in ids:
        row = await _fetch(
            engine,
            "SELECT rerun_of_generation_id, status FROM generations "
            "WHERE id = :g",
            {"g": gid},
        )
        assert row["rerun_of_generation_id"] == gen_a["id"]
        assert row["status"] == "queued"
        inputs = _inputs_of(await _fetch_all(
            engine,
            "SELECT input_key, reference_role, position, asset_id, blob_hash "
            "FROM generation_inputs WHERE generation_id = :g",
            {"g": gid},
        ))
        assert len(inputs) == 1  # every winner carries the full copy


async def test_rerun_waits_on_held_write_lock_then_succeeds(client, factory, engine):
    """Forced interleaving: while another connection holds the write lock,
    the rerun's BEGIN IMMEDIATE must block (not fail), then complete with
    the correctly allocated next number after the lock is released."""
    sid, pid, refs = await _seed(factory, engine, n_refs=1)
    gen_a = await _create_generation(client, sid)
    await _set_status(engine, gen_a["id"], "succeeded")

    lock = await engine.connect()
    await lock.exec_driver_sql("BEGIN IMMEDIATE")
    try:
        task = asyncio.create_task(_rerun(client, gen_a["id"]))
        await asyncio.sleep(0.5)
        # The write lock is ours, so the rerun cannot have committed.
        assert not task.done()
    finally:
        await lock.exec_driver_sql("COMMIT")
        await lock.close()

    r = await task
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["generation_number"] == 2
    row = await _fetch(
        engine,
        "SELECT rerun_of_generation_id, status FROM generations WHERE id = :g",
        {"g": body["id"]},
    )
    assert row["rerun_of_generation_id"] == gen_a["id"]
    assert row["status"] == "queued"


# --- end-to-end: the rerun is real executable work ------------------------------


async def test_rerun_executes_end_to_end_through_worker(
    client, factory, engine, settings
):
    sid, pid, refs = await _seed(factory, engine, n_refs=1)
    gen_a = await _create_generation(client, sid)
    driven = await _run_one(engine, settings)
    assert driven == "succeeded"

    r = await _rerun(client, gen_a["id"])
    assert r.status_code == 202, r.text
    gen_b = r.json()

    driven = await _run_one(engine, settings)
    assert driven == "succeeded"
    row_b = await _fetch(
        engine,
        "SELECT status, attempt_id, executor_job_id FROM generations "
        "WHERE id = :g",
        {"g": gen_b["id"]},
    )
    assert row_b["status"] == "succeeded"
    assert row_b["attempt_id"] is not None  # minted at claim, fresh attempt

    takes = await _fetch_all(
        engine, "SELECT id FROM takes WHERE generation_id = :g", {"g": gen_b["id"]}
    )
    assert takes  # the rerun produced its own Take provenance
