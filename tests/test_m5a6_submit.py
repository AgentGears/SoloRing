"""M5A-6 — Client and Submit Recovery (M5 plan §33-§39, headline matrix).

Cases A-G plus malformed-200, conclusive-4xx, rediscovery-failure grace,
never-requeue-uncertain, HTTP-counter negative evidence, and the structural
boundary rules. The double is an httpx.MockTransport-backed Comfy server with
full POST instrumentation.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.references import ReferenceInput
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects, references, shots
from soloring.errors import ErrorCode
from soloring.executors.comfy.client import (
    ComfyAPIError,
    ComfyClient,
    PromptAccepted,
    PromptRejected,
    SubmissionAmbiguous,
)
from soloring.executors.comfy.executor import RediscoveryConflict, find_attempt
from soloring.settings import Settings
from soloring.worker import ownership
from soloring.worker.comfy_submission import SubmissionConflict, run_comfy_submission
from soloring.worker.ownership import (
    OwnershipMutationResult,
    SubmissionPermission,
    acquire_worker_lease,
    claim_next_generation,
    confirm_owned_submission,
    mark_submission_possible,
    mark_submission_uncertain,
    persist_owned_executor_submission,
    refresh_worker_lease,
)


# --- The HTTP double --------------------------------------------------------------


@dataclass
class ComfyDouble:
    """MockTransport-backed Comfy with POST instrumentation."""

    base_url: str = "http://comfy.test"
    prompt_posts: list[tuple[str, str]] = field(default_factory=list)  # (g, a)
    prompts: dict[str, dict] = field(default_factory=dict)  # pid → record
    next_pid: int = 0
    # behaviors
    lose_submit_response: bool = False          # accept, drop the response
    malformed_submit_200: bool = False
    submit_5xx: bool = False
    submit_400_validation: bool = False
    marker_visibility_delay: int = 0            # polls before marker visible
    queue_marker_override: dict | None = None   # pid → marker override
    read_failures_left: int = 0                 # transient /queue+/history 503
    _poll_count: int = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/system_stats":
            return httpx.Response(200, json={
                "system": {"comfyui_version": "0.3.14", "build": "t"}
            })
        if path == "/prompt":
            return self._handle_prompt(request)
        if path == "/queue":
            return self._handle_queue()
        if path.startswith("/history"):
            return self._handle_history()
        if path == "/view":
            return httpx.Response(200, content=b"")
        return httpx.Response(404)

    def _handle_prompt(self, request):
        body = json.loads(request.content.decode())
        marker = body.get("extra_data", {}).get("soloring", {})
        g, a = marker.get("generation_id", "?"), marker.get("attempt_id", "?")
        self.prompt_posts.append((g, a))

        if self.submit_400_validation:
            return httpx.Response(400, json={"error": "bad graph",
                                             "node_errors": {}})
        if self.submit_5xx:
            return httpx.Response(503, text="gateway")
        self.next_pid += 1
        pid = f"prompt-{self.next_pid:04d}"
        record = {
            "prompt": [0, pid, {}, body.get("extra_data", {}), []],
            "outputs": {},
            "status": {"status_str": "completed", "messages": []},
        }
        self.prompts[pid] = record
        if self.lose_submit_response:
            raise httpx.ReadTimeout("response lost after acceptance")
        if self.malformed_submit_200:
            return httpx.Response(200, text="not-json")
        return httpx.Response(200, json={"prompt_id": pid})

    def _handle_queue(self):
        self._poll_count += 1
        if self.read_failures_left > 0:
            self.read_failures_left -= 1
            return httpx.Response(503, text="degraded")
        running, pending = [], []
        for pid, record in self.prompts.items():
            marker = (
                self.queue_marker_override.get(pid)
                if self.queue_marker_override
                else record["prompt"][3]
            )
            if not self._marker_visible():
                marker = {"unrelated": True}
            entry = [0, pid, {}, marker, []]
            (running if pid.endswith(("1", "3", "5", "7", "9")) else pending).append(entry)
        return httpx.Response(200, json={
            "queue_running": running, "queue_pending": pending,
        })

    def _handle_history(self):
        self._poll_count += 1
        if self.read_failures_left > 0:
            self.read_failures_left -= 1
            return httpx.Response(503, text="degraded")
        out = {}
        for pid, record in self.prompts.items():
            if not self._marker_visible():
                out[pid] = {**record, "prompt": [0, pid, {}, {"unrelated": True}, []]}
            else:
                out[pid] = record
        return httpx.Response(200, json=out)

    def _marker_visible(self) -> bool:
        return self._poll_count > self.marker_visibility_delay

    def post_count(self, generation_id: str, attempt_id: str) -> int:
        return sum(1 for g, a in self.prompt_posts if g == generation_id
                   and a == attempt_id)


def _client(double: ComfyDouble) -> ComfyClient:
    return ComfyClient(
        double.base_url, "w-test", timeout=5.0,
        transport=httpx.MockTransport(double.handler),
    )


def _payload(generation_id: str, attempt_id: str) -> dict:
    return {
        "prompt": {"4": {"class_type": "LoadImage",
                          "inputs": {"image": "x.png"}}},
        "extra_data": {"soloring": {"generation_id": generation_id,
                                     "attempt_id": attempt_id}},
        "client_id": "w-test",
    }


def _double_with_marker(generation_id: str, attempt_id: str,
                        **kw) -> ComfyDouble:
    """Double whose prompts carry OUR marker (so rediscovery can match)."""
    d = ComfyDouble(**kw)
    original = d._handle_prompt

    def handle(request):
        # ensure marker matches this attempt regardless of body
        response = original(request)
        return response

    d._handle_prompt = handle
    return d



# --- DB seeding --------------------------------------------------------------------


async def _seed_generation(client_, factory, engine):
    async with factory() as s:
        pid = (await projects.create_project(s, ProjectCreate(name="P"))).id
        shot = await shots.create_shot(s, pid, ShotCreate(subject="Eva"))
    aid, bh = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await references.replace_references(
            s, shot.id, [ReferenceInput(asset_id=aid, role="reference")]
        )
    r = await client_.post(f"/shots/{shot.id}/generations")
    assert r.status_code == 202, r.text
    return r.json()["id"]


async def seed_reference_asset(engine, project_id):
    import hashlib

    from soloring.db.models import Asset, Blob
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from soloring.domain.ids import new_uuid

    aid = new_uuid()
    bh = hashlib.sha256(aid.encode()).hexdigest()
    f = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with f() as s:
        s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                   size_bytes=1))
        await s.flush()
        s.add(Asset(id=aid, project_id=project_id, blob_hash=bh,
                    kind="reference"))
        await s.commit()
    return aid, bh


async def _row(factory, gid):
    async with factory() as s:
        return dict((await s.execute(text(
            "SELECT status, worker_id, attempt_id, executor_submission_state, "
            "executor_job_id, executor_handle_json, error_code FROM generations "
            "WHERE id=:g"
        ), {"g": gid})).mappings().one())


async def _age_both(engine, gid):
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(text(
            "UPDATE worker_leases SET heartbeat_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds')"
        ))
        await conn.execute(text(
            "UPDATE generations SET heartbeat_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now','-9999 seconds') WHERE id=:g"
        ).bindparams(g=gid))
        await conn.exec_driver_sql("COMMIT")


# --- normal path ----------------------------------------------------------------------


async def test_normal_post_to_confirmation(client, factory, engine, settings):
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")

    double = ComfyDouble()
    result = await run_comfy_submission(
        engine, settings, "w-A", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=0.2,
    )
    assert result.startswith("prompt-")
    row = await _row(factory, gid)
    assert row["executor_submission_state"] == "confirmed"
    assert row["executor_job_id"] == result
    assert double.post_count(gid, attempt) == 1
    assert json.loads(row["executor_handle_json"])["kind"] == "comfy"


# --- Case A: accepted, response lost ----------------------------------------------------


async def test_case_a_accepted_response_lost_single_post(
    client, factory, engine, settings
):
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")

    double = ComfyDouble(lose_submit_response=True)
    result = await run_comfy_submission(
        engine, settings, "w-A", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=1.0,
    )
    assert result.startswith("prompt-")  # rediscovered + confirmed
    row = await _row(factory, gid)
    assert row["executor_submission_state"] == "confirmed"
    assert double.post_count(gid, attempt) == 1  # POST count == 1, never 2
    assert len(double.prompts) == 1  # remote execution count == 1


async def test_case_a_delayed_visibility(client, factory, engine, settings):
    """Marker absent for the first polls, then appears → adopted."""
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")

    double = ComfyDouble(lose_submit_response=True, marker_visibility_delay=6)
    result = await run_comfy_submission(
        engine, settings, "w-A", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=3.0,
    )
    assert result.startswith("prompt-")
    assert double.post_count(gid, attempt) == 1


# --- Case B: response received, worker dies before persistence ---------------------------


async def test_case_b_crash_before_persistence_successor_confirms(
    client, factory, engine, settings
):
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")

    double = ComfyDouble()
    c = _client(double)
    # A does everything except confirm: simulate by running the pieces.
    import hashlib

    sj = json.dumps(_payload(gid, attempt), sort_keys=True, separators=(",", ":"))
    sh = hashlib.sha256(sj.encode()).hexdigest()
    await persist_owned_executor_submission(
        engine, "w-A", gid, attempt, sj, sh
    )
    await mark_submission_possible(engine, "w-A", gid, attempt)
    outcome = await c.submit_prompt(_payload(gid, attempt))
    pid = outcome.prompt_id  # A receives P… and dies (no confirm call).

    await _age_both(engine, gid)
    await acquire_worker_lease(engine, "w-B", 30)
    from soloring.worker.ownership import adopt_stale_generation

    assert (await adopt_stale_generation(engine, "w-B", gid)) is (
        OwnershipMutationResult.OK
    )

    # B runs the protocol: REDISCOVER_ONLY → finds P → confirms.
    result = await run_comfy_submission(
        engine, settings, "w-B", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=1.0,
    )
    assert result == pid
    row = await _row(factory, gid)
    assert row["executor_submission_state"] == "confirmed"
    assert double.post_count(gid, attempt) == 1  # B never POSTed


# --- Case C: response received, lease lost before persistence -----------------------------


async def test_case_c_lease_loss_before_persistence(
    client, factory, engine, settings
):
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")

    double = ComfyDouble()
    c = _client(double)
    import hashlib

    sj = json.dumps(_payload(gid, attempt), sort_keys=True, separators=(",", ":"))
    sh = hashlib.sha256(sj.encode()).hexdigest()
    await persist_owned_executor_submission(
        engine, "w-A", gid, attempt, sj, sh
    )
    await mark_submission_possible(engine, "w-A", gid, attempt)
    outcome = await c.submit_prompt(_payload(gid, attempt))
    pid = outcome.prompt_id

    await _age_both(engine, gid)
    await acquire_worker_lease(engine, "w-B", 30)
    from soloring.worker.ownership import adopt_stale_generation

    assert (await adopt_stale_generation(engine, "w-B", gid)) is (
        OwnershipMutationResult.OK
    )

    # Stale A's confirmation is fenced off.
    r = await confirm_owned_submission(
        engine, "w-A", gid, attempt, pid,
        json.dumps({"kind": "comfy", "prompt_id": pid}),
    )
    assert r is OwnershipMutationResult.LEASE_LOST

    # B rediscovers + confirms; A never drove the job further.
    result = await run_comfy_submission(
        engine, settings, "w-B", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=1.0,
    )
    assert result == pid
    assert double.post_count(gid, attempt) == 1


# --- Case D: permit consumed, no POST ever happened ----------------------------------------


async def test_case_d_no_post_uncertain(client, factory, engine, settings):
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")

    import hashlib

    sj = json.dumps(_payload(gid, attempt), sort_keys=True, separators=(",", ":"))
    sh = hashlib.sha256(sj.encode()).hexdigest()
    await persist_owned_executor_submission(
        engine, "w-A", gid, attempt, sj, sh
    )
    await mark_submission_possible(engine, "w-A", gid, attempt)
    # A dies WITHOUT calling submit_prompt.

    await _age_both(engine, gid)
    await acquire_worker_lease(engine, "w-B", 30)
    from soloring.worker.ownership import adopt_stale_generation

    assert (await adopt_stale_generation(engine, "w-B", gid)) is (
        OwnershipMutationResult.OK
    )

    double = ComfyDouble()
    result = await run_comfy_submission(
        engine, settings, "w-B", gid, attempt, _payload(gid, attempt),
        _client(double),
        grace_seconds=0.3,
    )
    assert result == ""  # uncertain
    row = await _row(factory, gid)
    assert row["executor_submission_state"] == "uncertain"
    assert double.post_count(gid, attempt) == 0  # successor NEVER posted


# --- Case E: duplicate marker --------------------------------------------------------------


async def test_case_e_duplicate_attempt(client, factory, engine, settings):
    """Seed TWO remote prompts carrying the same marker → invariant failure,
    no handle persisted."""
    from soloring.executors.comfy.executor import _merge_evidence
    from soloring.executors.comfy.wire import normalize_queue_response

    marker = {"soloring": {"generation_id": "g" * 36, "attempt_id": "a" * 36}}
    raw = {"queue_running": [[0, "P", {}, marker, []]],
           "queue_pending": [[1, "Q", {}, marker, []]]}
    jobs = normalize_queue_response(raw)
    with pytest.raises(RediscoveryConflict) as e:
        _merge_evidence(jobs, {}, ("g" * 36, "a" * 36))
    assert e.value.kind == "COMFY_DUPLICATE_ATTEMPT"

# Full-protocol shape: B detects duplicate during rediscovery.
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-B", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-B")
    import hashlib

    sj = json.dumps(_payload(gid, attempt), sort_keys=True, separators=(",", ":"))
    sh = hashlib.sha256(sj.encode()).hexdigest()
    await persist_owned_executor_submission(
        engine, "w-B", gid, attempt, sj, sh
    )
    await mark_submission_possible(engine, "w-B", gid, attempt)

    class Dup(ComfyDouble):
        def _handle_prompt(self, request):
            # duplicate every submission
            response = super()._handle_prompt(request)
            if response.status_code == 200:
                body = json.loads(response.read())
                self.next_pid += 1
                pid2 = f"prompt-{self.next_pid:04d}"
                marker = json.loads(request.content.decode())["extra_data"]
                self.prompts[pid2] = {"prompt": [0, pid2, {}, marker, []],
                                      "outputs": {},
                                      "status": {"status_str": "completed"}}
            return response

    double = Dup()
    # Simulate duplicate by losing the response then double-seeding.
    double.lose_submit_response = True
    c = _client(double)
    outcome = await c.submit_prompt(_payload(gid, attempt)) if False else None
    # Directly seed a second remote prompt with the same marker:
    double.next_pid += 1
    pid2 = f"prompt-{double.next_pid:04d}"
    double.prompts[pid2] = {"prompt": [0, pid2, {}, _payload(gid, attempt)["extra_data"], []],
                            "outputs": {}, "status": {"status_str": "completed",
                                                      "messages": []}}
    # Wait: the first submit_prompt call hasn't happened; call it:
    

    # Reset: do it properly — A POSTed once, remote double-counted.
    double2 = ComfyDouble()
    c2 = _client(double2)
    accepted = await c2.submit_prompt(_payload(gid, attempt))
    # remote-side duplicate (outside SoloRing's control):
    double2.next_pid += 1
    pid_dup = f"prompt-{double2.next_pid:04d}"
    double2.prompts[pid_dup] = {
        "prompt": [0, pid_dup, {}, _payload(gid, attempt)["extra_data"], []],
        "outputs": {}, "status": {"status_str": "completed", "messages": []},
    }
    with pytest.raises(SubmissionConflict) as err:
        await run_comfy_submission(
            engine, settings, "w-B", gid, attempt, _payload(gid, attempt), c2,
            grace_seconds=0.3,
        )
    assert err.value.code == ErrorCode.COMFY_DUPLICATE_ATTEMPT
    row = await _row(factory, gid)
    assert row["executor_job_id"] is None  # no handle persisted


# --- Case F: conflicting same-prompt evidence ------------------------------------------------


async def test_case_f_conflicting_same_prompt_evidence():
    from soloring.executors.comfy.executor import _merge_evidence
    from soloring.executors.comfy.wire import (
        normalize_history_response, normalize_queue_response,
    )

    m1 = {"soloring": {"generation_id": "g" * 36, "attempt_id": "a" * 36}}
    m2 = {"soloring": {"generation_id": "OTHER", "attempt_id": "X" * 36}}
    jobs = normalize_queue_response(
        {"queue_running": [[0, "P", {}, m1, []]], "queue_pending": []}
    )
    history = normalize_history_response({
        "P": {"prompt": [0, "P", {}, m2, []], "outputs": {},
               "status": {"status_str": "completed", "messages": []}},
    })
    with pytest.raises(RediscoveryConflict) as e:
        _merge_evidence(jobs, history, ("g" * 36, "a" * 36))
    assert e.value.kind == "conflicting_same_prompt_evidence"


async def test_same_prompt_consistent_in_both_surfaces_adopts_once():
    from soloring.executors.comfy.executor import _merge_evidence
    from soloring.executors.comfy.wire import (
        normalize_history_response, normalize_queue_response,
    )

    marker = {"soloring": {"generation_id": "g" * 36, "attempt_id": "a" * 36}}
    jobs = normalize_queue_response(
        {"queue_running": [[0, "P", {}, marker, []]], "queue_pending": []}
    )
    history = normalize_history_response({
        "P": {"prompt": [0, "P", {}, marker, []], "outputs": {},
               "status": {"status_str": "completed", "messages": []}},
    })
    result = _merge_evidence(jobs, history, ("g" * 36, "a" * 36))
    assert result.outcome == "adopt" and result.prompt_id == "P"


# --- Case G: repeated recovery -----------------------------------------------------------------


async def test_case_g_repeated_recovery_idempotent(
    client, factory, engine, settings
):
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")
    double = ComfyDouble()
    pid = await run_comfy_submission(
        engine, settings, "w-A", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=0.2,
    )

    # B/C recover later: P remains authoritative; idempotent.
    await _age_both(engine, gid)
    await acquire_worker_lease(engine, "w-C", 30)
    from soloring.worker.ownership import adopt_stale_generation

    assert (await adopt_stale_generation(engine, "w-C", gid)) is (
        OwnershipMutationResult.OK
    )
    again = await run_comfy_submission(
        engine, settings, "w-C", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=0.2,
    )
    assert again == pid
    assert double.post_count(gid, attempt) == 1


async def test_confirmed_different_prompt_is_invariant_conflict(
    client, factory, engine, settings
):
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")
    double = ComfyDouble()
    pid = await run_comfy_submission(
        engine, settings, "w-A", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=0.2,
    )

    # Remote now ALSO shows a different prompt with the same marker.
    double.next_pid += 1
    q = f"prompt-{double.next_pid:04d}"
    double.prompts[q] = {"prompt": [0, q, {}, _payload(gid, attempt)["extra_data"], []],
                          "outputs": {},
                          "status": {"status_str": "completed", "messages": []}}

    await _age_both(engine, gid)
    await acquire_worker_lease(engine, "w-C", 30)
    from soloring.worker.ownership import adopt_stale_generation

    assert (await adopt_stale_generation(engine, "w-C", gid)) is (
        OwnershipMutationResult.OK
    )
    with pytest.raises(SubmissionConflict) as err:
        await run_comfy_submission(
            engine, settings, "w-C", gid, attempt, _payload(gid, attempt), _client(double),
            grace_seconds=0.2,
        )
    # Either duplicate-attempt (two prompts) or handle-conflict: both are
    # stable invariant failures that never replace the established handle.
    assert err.value.code in (
        ErrorCode.COMFY_DUPLICATE_ATTEMPT, ErrorCode.COMFY_EXECUTOR_HANDLE_CONFLICT,
    )
    row = await _row(factory, gid)
    assert row["executor_job_id"] == pid  # never silently replaced


# --- malformed / rejected responses -----------------------------------------------------------


async def test_malformed_200_rediscovery_never_retry(client, factory, engine, settings):
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")

    double = ComfyDouble(malformed_submit_200=True)
    # The malformed 200 means the prompt WAS accepted server-side.
    result = await run_comfy_submission(
        engine, settings, "w-A", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=1.0,
    )
    assert result.startswith("prompt-")  # rediscovered
    assert double.post_count(gid, attempt) == 1


async def test_5xx_is_ambiguous_not_retried():
    double = ComfyDouble(submit_5xx=True)
    c = _client(double)
    with pytest.raises(SubmissionAmbiguous):
        await c.submit_prompt(_payload("G", "A"))
    assert len(double.prompt_posts) == 1


async def test_conclusive_400_validation_is_rejection():
    double = ComfyDouble(submit_400_validation=True)
    c = _client(double)
    outcome = await c.submit_prompt(_payload("G", "A"))
    assert isinstance(outcome, PromptRejected)
    assert outcome.status_code == 400


async def test_400_without_validation_body_is_ambiguous():
    class NoBody(ComfyDouble):
        def _handle_prompt(self, request):
            super()._handle_prompt(request)
            return httpx.Response(400, text="opaque")

    c = _client(NoBody())
    with pytest.raises(SubmissionAmbiguous):
        await c.submit_prompt(_payload("G", "A"))


async def test_invalid_prompt_id_in_200_is_ambiguous():
    class BadId(ComfyDouble):
        def _handle_prompt(self, request):
            super()._handle_prompt(request)
            return httpx.Response(200, json={"prompt_id": "x" * 300})

    c = _client(BadId())
    with pytest.raises(SubmissionAmbiguous):
        await c.submit_prompt(_payload("G", "A"))


# --- grace behavior ----------------------------------------------------------------------------


async def test_read_failures_do_not_extend_grace(client, factory, engine, settings):
    """Degraded reads: bounded retry inside the ORIGINAL deadline — the
    attempt still resolves uncertain on schedule."""
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")
    import hashlib

    sj = json.dumps(_payload(gid, attempt), sort_keys=True, separators=(",", ":"))
    sh = hashlib.sha256(sj.encode()).hexdigest()
    await persist_owned_executor_submission(
        engine, "w-A", gid, attempt, sj, sh
    )
    await mark_submission_possible(engine, "w-A", gid, attempt)

    double = ComfyDouble(read_failures_left=3)  # a few degraded polls
    t0 = time.monotonic()
    result = await run_comfy_submission(
        engine, settings, "w-A", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=0.5,
    )
    elapsed = time.monotonic() - t0
    assert result == ""  # uncertain within ~grace despite read failures
    assert elapsed < 2.0  # NOT extended by the failures


async def test_uncertain_never_requeues(client, factory, engine, settings):
    """Recovery orchestration never translates uncertain → queued."""
    gid = await _seed_generation(client, factory, engine)
    await acquire_worker_lease(engine, "w-A", 30)
    (gen_id, attempt) = await claim_next_generation(engine, "w-A")
    import hashlib

    sj = json.dumps(_payload(gid, attempt), sort_keys=True, separators=(",", ":"))
    sh = hashlib.sha256(sj.encode()).hexdigest()
    await persist_owned_executor_submission(
        engine, "w-A", gid, attempt, sj, sh
    )
    await mark_submission_possible(engine, "w-A", gid, attempt)

    double = ComfyDouble()
    result = await run_comfy_submission(
        engine, settings, "w-A", gid, attempt, _payload(gid, attempt), _client(double),
        grace_seconds=0.2,
    )
    assert result == ""

    # A successor's full reconciliation (the recovery module path) leaves the
    # row terminal-adjacent and NEVER requeued.
    from soloring.worker import recovery as recovery_mod

    await _age_both(engine, gid)
    await acquire_worker_lease(engine, "w-B", 30)
    await recovery_mod.reconcile_stale_generations(engine, "w-B", settings)

    row = await _row(factory, gid)
    assert row["executor_submission_state"] == "uncertain"
    assert row["status"] != "queued"  # the invariant: never requeued


# --- structural boundaries ------------------------------------------------------------------------


def test_client_and_executor_are_db_free():
    import ast as _ast

    comfy = BASE_DIR / "server" / "soloring" / "executors" / "comfy"
    banned = ("soloring.db", "soloring.worker", "sqlalchemy", "aiosqlite")
    for name in ("client.py", "executor.py"):
        tree = _ast.parse((comfy / name).read_text("utf-8"))
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, _ast.ImportFrom):
                mods = [node.module or ""]
            else:
                continue
            for m in mods:
                for b in banned:
                    assert not (m == b or m.startswith(b + ".")), (
                        f"{name} imports {m!r}"
                    )


def test_comfy_submission_is_the_only_may_post_consumer():
    """Worker orchestration (comfy_submission.py) alone consumes MAY_POST."""
    import ast as _ast

    comfy = BASE_DIR / "server" / "soloring" / "executors" / "comfy"
    for path in comfy.glob("*.py"):
        src = path.read_text("utf-8")
        assert "SubmissionPermission" not in src, (
            f"{path.name} consumes submission permission"
        )
        assert "mark_submission_possible" not in src


from soloring.settings import BASE_DIR  # noqa: E402
