"""M5A-1 — Schema and one-shot submission authority (M5 plan §6-§11, amended §8).

The full mandatory list: fresh-claim initialization, legacy requeue reset,
modern-attempt POST-permission irreversibility, adoption preservation, fenced
artifact/possible transitions, exactly-one MAY_POST winner, one-way state
machine guards, lease-loser rejection, and FakeExecutor non-participation.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.fake import FakeExecutor
from soloring.settings import Settings
from soloring.worker import execution as worker_execution
from soloring.worker import ownership
from soloring.worker.ownership import (
    OwnershipMutationResult,
    SubmissionPermission,
    adopt_stale_generation,
    acquire_worker_lease,
    claim_next_generation,
    confirm_owned_submission,
    mark_submission_possible,
    mark_submission_uncertain,
    persist_owned_executor_submission,
    requeue_stale_preparing_generation,
)
from tests.conftest import seed_reference_asset


async def _seed(factory, engine):
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva enters"))
    aid, _ = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")]
        )
    return shot.id


async def _create_generation(client, shot_id):
    r = await client.post(f"/shots/{shot_id}/generations")
    assert r.status_code == 202, r.text
    return r.json()["id"]


async def _row(factory, gid):
    async with factory() as s:
        return dict(
            (
                await s.execute(
                    text(
                        "SELECT status, worker_id, attempt_id, "
                        "executor_submission_state, submission_possible_at, "
                        "executor_submission_json, executor_submission_hash, "
                        "executor_job_id, executor_handle_json, queued_at "
                        "FROM generations WHERE id=:g"
                    ),
                    {"g": gid},
                )
            ).mappings().one()
        )


async def _claim_and_prepare(engine, factory, gid, worker="w-A"):
    """Acquire lease + claim; returns (attempt_id,)."""
    await acquire_worker_lease(engine, worker, 30)
    claim = await claim_next_generation(engine, worker)
    assert claim is not None and claim[0] == gid
    return claim[1]


ARTIFACT = ("{}", "f" * 64)


async def _age_lease(engine, seconds=9999):
    """Age the singleton lease so a takeover can succeed (A's TTL is fresh)."""
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE worker_leases SET heartbeat_at = "
                f"strftime('%Y-%m-%dT%H:%M:%fZ','now','-{int(seconds)} seconds')"
            )
        )
        await conn.exec_driver_sql("COMMIT")


# --- creation + claim initialization ------------------------------------------


async def test_new_generation_starts_not_started(client, factory, engine):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    row = await _row(factory, gid)
    assert row["executor_submission_state"] == "not_started"
    assert row["submission_possible_at"] is None
    assert row["attempt_id"] is None


async def test_fresh_claim_initializes_attempt_and_state(client, factory, engine):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    attempt = await _claim_and_prepare(engine, factory, gid)
    row = await _row(factory, gid)
    assert row["attempt_id"] == attempt
    assert row["executor_submission_state"] == "not_started"
    assert row["submission_possible_at"] is None


# --- legacy requeue reset ------------------------------------------------------


async def test_legacy_requeue_resets_submission_state(client, factory, engine):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await acquire_worker_lease(engine, "w-A", 30)
    await claim_next_generation(engine, "w-A")
    # Legacy row: no durable attempt identity, no artifact, no handle — but a
    # stale possible_at timestamp that requeue must clear.
    async with factory() as s:
        await s.execute(
            text(
                "UPDATE generations SET attempt_id = NULL, "
                "submission_possible_at = '2020-01-01T00:00:00.000Z' "
                "WHERE id = :g"
            ).bindparams(g=gid)
        )
        await s.commit()

    r = await requeue_stale_preparing_generation(engine, "w-A", gid)
    assert r is OwnershipMutationResult.OK
    row = await _row(factory, gid)
    assert row["status"] == "queued"
    assert row["executor_submission_state"] == "not_started"
    assert row["submission_possible_at"] is None
    assert row["queued_at"] is not None  # preserved


async def test_modern_attempt_cannot_regain_post_permission_via_requeue(
    client, factory, engine
):
    """A non-null modern attempt_id is not destroyed to regain submission
    permission: requeue refuses (M5 amendment §2), state stays
    submission_possible."""
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    attempt = await _claim_and_prepare(engine, factory, gid)
    assert (
        await persist_owned_executor_submission(
            engine, "w-A", gid, attempt, *ARTIFACT
        )
        is OwnershipMutationResult.OK
    )
    assert (
        await mark_submission_possible(engine, "w-A", gid, attempt)
        is SubmissionPermission.MAY_POST
    )

    r = await requeue_stale_preparing_generation(engine, "w-A", gid)
    assert r is OwnershipMutationResult.GENERATION_STATE_CONFLICT  # refused
    row = await _row(factory, gid)
    assert row["executor_submission_state"] == "submission_possible"
    assert row["attempt_id"] == attempt  # not destroyed


async def test_claim_refuses_queued_row_with_modern_submission_state(
    client, factory, engine, caplog
):
    """A queued row carrying submission_possible/confirmed/uncertain is an
    invariant violation: claim refuses rather than silently resetting."""
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    attempt = await _claim_and_prepare(engine, factory, gid)
    await persist_owned_executor_submission(engine, "w-A", gid, attempt, *ARTIFACT)
    await mark_submission_possible(engine, "w-A", gid, attempt)

    # Force the corrupt state: queued + submission_possible.
    async with factory() as s:
        await s.execute(
            text(
                "UPDATE generations SET status = 'queued' WHERE id = :g"
            ).bindparams(g=gid)
        )
        await s.commit()

    claim = await claim_next_generation(engine, "w-A")
    assert claim is None  # refused
    row = await _row(factory, gid)
    assert row["status"] == "queued"  # untouched
    assert row["executor_submission_state"] == "submission_possible"  # NOT reset


# --- adoption preservation ------------------------------------------------------


async def test_adoption_preserves_submission_state_exactly(
    client, factory, engine, settings
):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    attempt = await _claim_and_prepare(engine, factory, gid)
    await persist_owned_executor_submission(engine, "w-A", gid, attempt, *ARTIFACT)
    await mark_submission_possible(engine, "w-A", gid, attempt)
    before = await _row(factory, gid)

    # Stale + takeover by B.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE generations SET heartbeat_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds') "
                "WHERE id = :g"
            ).bindparams(g=gid)
        )
        await conn.execute(
            text(
                "UPDATE worker_leases SET heartbeat_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds')"
            )
        )
        await conn.exec_driver_sql("COMMIT")
    await acquire_worker_lease(engine, "w-B", 30)
    r = await adopt_stale_generation(engine, "w-B", gid)
    assert r is OwnershipMutationResult.OK

    after = await _row(factory, gid)
    # Adoption changes authority ONLY: every attempt/submission field is
    # preserved byte-for-byte.
    for field in (
        "attempt_id", "executor_submission_state", "submission_possible_at",
        "executor_submission_json", "executor_submission_hash",
        "executor_job_id", "executor_handle_json",
    ):
        assert after[field] == before[field], field
    assert after["worker_id"] == "w-B"

    # And the successor is REDISCOVER_ONLY for the preserved attempt.
    assert (
        await mark_submission_possible(engine, "w-B", gid, after["attempt_id"])
        is SubmissionPermission.REDISCOVER_ONLY
    )


# --- fenced artifact persistence -----------------------------------------------


async def test_persist_submission_artifact_fenced_happy_and_guards(
    client, factory, engine
):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    attempt = await _claim_and_prepare(engine, factory, gid)

    assert (
        await persist_owned_executor_submission(
            engine, "w-A", gid, attempt, *ARTIFACT
        )
        is OwnershipMutationResult.OK
    )
    row = await _row(factory, gid)
    assert row["executor_submission_json"] == "{}"
    assert row["executor_submission_hash"] == "f" * 64

    # Wrong attempt → STATE_CONFLICT.
    assert (
        await persist_owned_executor_submission(
            engine, "w-A", gid, "not-the-attempt", *ARTIFACT
        )
        is OwnershipMutationResult.GENERATION_STATE_CONFLICT
    )
    # Lease loser → LEASE_LOST.
    await _age_lease(engine)
    await acquire_worker_lease(engine, "w-B", 30)
    assert (
        await persist_owned_executor_submission(
            engine, "w-A", gid, attempt, *ARTIFACT
        )
        is OwnershipMutationResult.LEASE_LOST
    )


async def test_mark_possible_requires_artifact_first(client, factory, engine):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    attempt = await _claim_and_prepare(engine, factory, gid)
    assert (
        await mark_submission_possible(engine, "w-A", gid, attempt)
        is SubmissionPermission.SUBMISSION_STATE_CONFLICT
    )
    assert (await _row(factory, gid))["executor_submission_state"] == "not_started"


# --- exactly one MAY_POST winner -------------------------------------------------


async def test_only_transition_winner_receives_may_post(client, factory, engine):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    attempt = await _claim_and_prepare(engine, factory, gid)
    await persist_owned_executor_submission(engine, "w-A", gid, attempt, *ARTIFACT)

    r1, r2 = await asyncio.gather(
        mark_submission_possible(engine, "w-A", gid, attempt),
        mark_submission_possible(engine, "w-A", gid, attempt),
    )
    winners = [r for r in (r1, r2) if r is SubmissionPermission.MAY_POST]
    rediscover = [r for r in (r1, r2) if r is SubmissionPermission.REDISCOVER_ONLY]
    assert len(winners) == 1
    assert len(rediscover) == 1

    row = await _row(factory, gid)
    assert row["executor_submission_state"] == "submission_possible"
    assert row["submission_possible_at"] is not None


async def test_lease_loser_cannot_mark_possible(client, factory, engine):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    attempt = await _claim_and_prepare(engine, factory, gid)
    await persist_owned_executor_submission(engine, "w-A", gid, attempt, *ARTIFACT)
    await _age_lease(engine)
    await acquire_worker_lease(engine, "w-B", 30)
    assert (
        await mark_submission_possible(engine, "w-A", gid, attempt)
        is SubmissionPermission.LEASE_LOST
    )
    assert (await _row(factory, gid))["executor_submission_state"] == "not_started"


# --- one-way state machine guards -------------------------------------------------


async def _at_possible(engine, factory, client, worker="w-A"):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    attempt = await _claim_and_prepare(engine, factory, gid, worker)
    await persist_owned_executor_submission(engine, worker, gid, attempt, *ARTIFACT)
    assert (
        await mark_submission_possible(engine, worker, gid, attempt)
        is SubmissionPermission.MAY_POST
    )
    return gid, attempt


async def test_submission_possible_cannot_return_to_not_started(
    client, factory, engine
):
    gid, attempt = await _at_possible(engine, factory, client)
    # No path back: marking again is REDISCOVER_ONLY; claim refuses if queued.
    assert (
        await mark_submission_possible(engine, "w-A", gid, attempt)
        is SubmissionPermission.REDISCOVER_ONLY
    )
    assert (await _row(factory, gid))["executor_submission_state"] == (
        "submission_possible"
    )


async def test_confirmed_cannot_return_to_submission_possible(
    client, factory, engine
):
    gid, attempt = await _at_possible(engine, factory, client)
    assert (
        await confirm_owned_submission(
            engine, "w-A", gid, attempt, "comfy-prompt-1",
            '{"kind":"comfy","prompt_id":"comfy-prompt-1"}',
        )
        is OwnershipMutationResult.OK
    )
    row = await _row(factory, gid)
    assert row["executor_submission_state"] == "confirmed"
    assert row["executor_job_id"] == "comfy-prompt-1"

    # confirmed → mark again: REDISCOVER_ONLY (never re-POST).
    assert (
        await mark_submission_possible(engine, "w-A", gid, attempt)
        is SubmissionPermission.REDISCOVER_ONLY
    )
    # confirmed → uncertain: STATE_CONFLICT (one-way).
    assert (
        await mark_submission_uncertain(engine, "w-A", gid, attempt)
        is OwnershipMutationResult.GENERATION_STATE_CONFLICT
    )


async def test_uncertain_cannot_return_to_submission_possible(
    client, factory, engine
):
    gid, attempt = await _at_possible(engine, factory, client)
    assert (
        await mark_submission_uncertain(engine, "w-A", gid, attempt)
        is OwnershipMutationResult.OK
    )
    assert (await _row(factory, gid))["executor_submission_state"] == "uncertain"

    # uncertain → mark: REDISCOVER_ONLY; uncertain → confirm: CONFLICT.
    assert (
        await mark_submission_possible(engine, "w-A", gid, attempt)
        is SubmissionPermission.REDISCOVER_ONLY
    )
    assert (
        await confirm_owned_submission(
            engine, "w-A", gid, attempt, "x", "{}"
        )
        is OwnershipMutationResult.GENERATION_STATE_CONFLICT
    )


async def test_confirm_requires_submission_possible(client, factory, engine):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    attempt = await _claim_and_prepare(engine, factory, gid)
    # not_started → confirm: ordering violation.
    assert (
        await confirm_owned_submission(engine, "w-A", gid, attempt, "x", "{}")
        is OwnershipMutationResult.GENERATION_STATE_CONFLICT
    )


# --- DB CHECK enforcement ----------------------------------------------------------


async def test_db_checks_reject_invalid_submission_states(client, factory, engine):
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    async with factory() as s:
        with pytest.raises(Exception):
            await s.execute(
                text(
                    "UPDATE generations SET executor_submission_state = 'bogus' "
                    "WHERE id = :g"
                ).bindparams(g=gid)
            )
            await s.commit()
        await s.rollback()
        # submission_possible requires attempt_id (CHECK).
        with pytest.raises(Exception):
            await s.execute(
                text(
                    "UPDATE generations SET executor_submission_state = "
                    "'submission_possible' WHERE id = :g"
                ).bindparams(g=gid)
            )
            await s.commit()
        await s.rollback()


# --- FakeExecutor non-participation -------------------------------------------------


async def test_fake_executor_never_participates_in_submission_state(
    client, factory, engine, settings
):
    """The full fake happy path runs with executor_submission_state remaining
    not_started throughout — the Comfy protocol is opt-in per executor."""
    sid = await _seed(factory, engine)
    gid = await _create_generation(client, sid)
    await acquire_worker_lease(engine, "w-fake", 30)
    outcome = await worker_execution.process_next_generation(
        engine, settings, "w-fake", FakeExecutor()
    )
    assert outcome == "succeeded"
    row = await _row(factory, gid)
    assert row["executor_submission_state"] == "not_started"
    assert row["submission_possible_at"] is None
    assert row["executor_job_id"] is not None  # fake handle still persisted
    assert row["executor_submission_json"] is None  # no comfy artifact
