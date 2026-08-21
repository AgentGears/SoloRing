"""M8F — failure, race, scale, and source gate (frozen plan §§64–66, 82).

§82.1 race mechanics: every race in this file mechanically proves its
interleaving with asyncio.Event barriers fired from inside REAL driver
statements on the competitor's connection — ``begin_immediate_entered``
is set immediately before awaiting the competitor's actual BEGIN
IMMEDIATE (the statement that acquires the write lock) and
``competitor_committed`` immediately after its actual COMMIT returns.
No sleeps are used as synchronization anywhere.

§66/§82.2 scale mechanics: the designated target Shot stresses the
dependency/facet dimension (multi-entity, multi-feature, multi-facet,
multi-view, not-applicable, optional-missing) through the PRODUCTION
resolver; query count is compared against a small fixture with the same
dimension shape and must be equal — bounded by query class, independent
of cardinality.

Direct-SQL bulk wiring is used ONLY for scale scaffolding, disclosed
here per §66: ``shots`` (volume), ``entity_revisions`` (historical,
unapproved), ``visual_facets`` (optional, no anchors), ``visual_anchors``
+ ``visual_anchor_revisions`` (noise, bound to historical revisions,
never applicable, never approved), and ``shot_revisions`` (schema-4
history rows never re-captured). Every frozen constraint is preserved;
the designated target Shot's semantic/visual state is built through the
real services so the production resolver performs the actual
applicability work.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid as _uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.test_m8a_visual import (
    _entity_with_revision,
    _facet,
    _feature,
    _seed_project,
)
from tests.test_m8b_curation import _assets, _put_payload
from tests.test_m8c_resolver import (
    _approve_anchor,
    _depend,
    _resolver_result,
    _topology,
)


async def _approved_fixture(client, factory, engine, pid, n_facets=1):
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 2)
    anchor_ids = []
    for k in range(n_facets):
        f = await _facet(
            client, pid, "entity", entity_id=eva["id"],
            facet_key=f"facet{k}",
        )
        r = await client.post(
            f"/visual-facets/{f['id']}/anchors",
            json={"entity_revision_id": rev1},
        )
        anchor_ids.append(r.json()["id"])
        await _approve_anchor(client, r.json()["id"], assets, ["front"])
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])
    return eva, rev1, assets, anchor_ids, (seq, scene, shots)


# --- §82.1 race driver -----------------------------------------------------------


class _Events:
    """§82.1 barriers: fired from inside the real driver statements."""

    __slots__ = (
        "begin_immediate_entered", "competitor_committed",
        "snapshot_established",
    )

    def __init__(self):
        self.begin_immediate_entered = asyncio.Event()
        self.competitor_committed = asyncio.Event()
        self.snapshot_established = asyncio.Event()


def _stmt_upper(statement) -> str:
    if isinstance(statement, str):
        return statement.strip().upper()
    return ""


async def _reader_vs_competitor(reader, competitor, *, form):
    """Force one of the two §82.1 pinned-read interleavings.

    form='before_first_read':
        reader enters its read unit and blocks before its first semantic
        SELECT; the competitor reaches BEGIN IMMEDIATE (event), mutates,
        and COMMITs (event); only then does the reader's first SELECT
        execute — the reader must observe the complete AFTER state.

    form='after_snapshot':
        the reader's first SELECT executes and returns
        (snapshot_established); the competitor then reaches BEGIN
        IMMEDIATE (event), mutates, and COMMITs (event) before any
        further reader statement — the reader must observe the complete
        BEFORE state, never a hybrid.
    """
    assert form in ("before_first_read", "after_snapshot")
    ev = _Events()
    state: dict = {}
    original_exec = AsyncConnection.exec_driver_sql
    original_execute = AsyncConnection.execute

    async def wrapped_exec(self, statement, *a, **kw):
        if asyncio.current_task() is state.get("competitor"):
            up = _stmt_upper(statement)
            if up == "BEGIN IMMEDIATE":
                ev.begin_immediate_entered.set()
            result = await original_exec(self, statement, *a, **kw)
            if up == "COMMIT":
                ev.competitor_committed.set()
            return result
        return await original_exec(self, statement, *a, **kw)

    async def gated_execute(self, *a, **kw):
        if (
            asyncio.current_task() is state.get("reader")
            and not state.get("first_done")
        ):
            state["first_done"] = True
            if form == "before_first_read":
                comp = asyncio.create_task(competitor())
                state["competitor"] = comp
                await ev.competitor_committed.wait()
                state["competitor_outcome"] = await comp
                return await original_execute(self, *a, **kw)
            result = await original_execute(self, *a, **kw)
            ev.snapshot_established.set()
            comp = asyncio.create_task(competitor())
            state["competitor"] = comp
            await ev.competitor_committed.wait()
            state["competitor_outcome"] = await comp
            return result
        return await original_execute(self, *a, **kw)

    AsyncConnection.exec_driver_sql = wrapped_exec
    AsyncConnection.execute = gated_execute
    try:
        reader_task = asyncio.create_task(reader())
        state["reader"] = reader_task
        state["first_done"] = False
        reader_out = await reader_task
        return reader_out, state.get("competitor_outcome"), ev
    finally:
        AsyncConnection.exec_driver_sql = original_exec
        AsyncConnection.execute = original_execute


async def _parked_on_write_lock(creator, competitor):
    """The M7B-proven parked interleaving, §82.1-compatible.

    The creator's fenced unit executes its real BEGIN IMMEDIATE and
    ACQUIRES the write lock; while the creator holds it, the competitor
    is launched and is observed executing its own real BEGIN IMMEDIATE
    — provably parked on the lock the creator holds right now (the event
    fires from inside that statement). The creator then proceeds and
    commits; the competitor acquires only afterward and must observe the
    creator's fully committed state.
    """
    ev = _Events()
    state: dict = {}
    original_exec = AsyncConnection.exec_driver_sql

    async def wrapped_exec(self, statement, *a, **kw):
        task = asyncio.current_task()
        up = _stmt_upper(statement)
        if up == "BEGIN IMMEDIATE":
            if task is state.get("competitor"):
                ev.begin_immediate_entered.set()  # parked on held lock
                return await original_exec(self, statement, *a, **kw)
            if task is state.get("creator"):
                result = await original_exec(self, statement, *a, **kw)
                # Lock HELD: launch the competitor and wait until it is
                # executing its BEGIN IMMEDIATE against our lock.
                state["competitor_task"] = asyncio.create_task(competitor())
                state["competitor"] = state["competitor_task"]
                # Defensive bound only — a competitor that dies before
                # its BEGIN IMMEDIATE must FAIL the test, not hang it.
                await asyncio.wait_for(
                    ev.begin_immediate_entered.wait(), timeout=10
                )
                return result
        if up == "COMMIT" and task is state.get("competitor"):
            result = await original_exec(self, statement, *a, **kw)
            ev.competitor_committed.set()
            return result
        return await original_exec(self, statement, *a, **kw)

    AsyncConnection.exec_driver_sql = wrapped_exec
    try:
        creator_task = asyncio.create_task(creator())
        state["creator"] = creator_task
        creator_out = await creator_task
        competitor_out = await state["competitor_task"]
        return creator_out, competitor_out, ev
    finally:
        AsyncConnection.exec_driver_sql = original_exec


async def _capture_reader(factory, anchor_id):
    from soloring.visual import anchors as anchor_svc

    async with factory() as s:
        return await anchor_svc.capture_revision(s, anchor_id)


async def _capture_snapshot(engine, revision_id) -> dict:
    async with engine.connect() as conn:
        snap = (
            await conn.execute(
                text(
                    "SELECT snapshot_json FROM visual_anchor_revisions "
                    "WHERE id = :r"
                ),
                {"r": revision_id},
            )
        ).scalar()
    return json.loads(snap)


# --- §82.1 VisualAnchor working-set edit during revision capture ------------------


async def test_race_working_edit_before_first_pinned_read_shows_after(
    client, factory, engine,
):
    """Form A: the competitor's working-set PUT commits (BEGIN IMMEDIATE
    event → COMMIT event) before the capture's first pinned SELECT — the
    captured revision must reflect the complete AFTER state."""
    pid = await _seed_project(factory)
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )

    async def competitor():
        return await client.put(
            f"/visual-anchors/{anchor_id}/items",
            json=_put_payload(
                [assets[1]], roles=["primary"], view_keys=["solo"]
            ),
        )

    rid, comp, ev = await _reader_vs_competitor(
        lambda: _capture_reader(factory, anchor_id), competitor,
        form="before_first_read",
    )
    assert comp.status_code == 200, comp.text
    assert ev.begin_immediate_entered.is_set()
    assert ev.competitor_committed.is_set()

    parsed = await _capture_snapshot(engine, rid)
    views = [it["view_key"] for it in parsed["items"]]
    assert views == ["solo"]  # complete AFTER state


async def test_race_working_edit_after_snapshot_shows_before(
    client, factory, engine,
):
    """Form B: the capture's first pinned read establishes the snapshot
    (snapshot_established), THEN the competitor's working-set PUT commits
    (BEGIN IMMEDIATE event → COMMIT event) before any further capture
    read — the captured revision must reflect the complete BEFORE state,
    never a hybrid; the next capture observes AFTER."""
    pid = await _seed_project(factory)
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )
    # Move the working set away from the approved revision first.
    await client.put(
        f"/visual-anchors/{anchor_id}/items",
        json=_put_payload(assets, view_keys=["front", "alt"]),
    )

    async def competitor():
        return await client.put(
            f"/visual-anchors/{anchor_id}/items",
            json=_put_payload(
                [assets[1]], roles=["primary"], view_keys=["solo"]
            ),
        )

    rid, comp, ev = await _reader_vs_competitor(
        lambda: _capture_reader(factory, anchor_id), competitor,
        form="after_snapshot",
    )
    assert comp.status_code == 200, comp.text
    assert ev.snapshot_established.is_set()
    assert ev.begin_immediate_entered.is_set()
    assert ev.competitor_committed.is_set()

    parsed = await _capture_snapshot(engine, rid)
    views = sorted(it["view_key"] for it in parsed["items"])
    assert views == ["alt", "front"]  # complete BEFORE state, no hybrid

    rid2 = await _capture_reader(factory, anchor_id)
    parsed2 = await _capture_snapshot(engine, rid2)
    assert [it["view_key"] for it in parsed2["items"]] == ["solo"]  # AFTER


# --- §82.1 VisualFacet requirement mutation during the pinned resolver read -------


async def _requirement_race_fixture(client, factory, engine, pid):
    """Required facet + approved anchor → ready; an optional facet with
    no anchor whose requirement can be flipped either way."""
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )
    f_opt = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="extra",
        requirement="optional",
    )
    return eva, rev1, assets, anchor_id, f_opt, shots


async def test_race_requirement_optional_to_required_before_first_read(
    client, factory, engine,
):
    """Form A: optional→required commits before the resolver's first
    pinned SELECT → the read observes complete AFTER (NOT ready with
    VISUAL_REALIZATION_REQUIRED)."""
    pid = await _seed_project(factory)
    eva, rev1, assets, anchor_id, f_opt, shots = (
        await _requirement_race_fixture(client, factory, engine, pid)
    )
    assert (await _resolver_result(engine, shots[0])).visual_continuity_ready

    async def competitor():
        return await client.patch(
            f"/visual-facets/{f_opt['id']}", json={"requirement": "required"}
        )

    result, comp, ev = await _reader_vs_competitor(
        lambda: _resolver_result(engine, shots[0]), competitor,
        form="before_first_read",
    )
    assert comp.status_code == 200, comp.text
    assert ev.competitor_committed.is_set()
    assert result.visual_continuity_ready is False  # AFTER
    codes = {i["error_code"] for i in result.issues}
    assert codes == {"VISUAL_REALIZATION_REQUIRED"}
    assert result.visual_reference_pack_hash is None


async def test_race_requirement_required_to_optional_after_snapshot(
    client, factory, engine,
):
    """Form B: the pinned read establishes its snapshot while the facet
    is still required-with-no-anchor (NOT ready); required→optional
    commits after (BEGIN IMMEDIATE → COMMIT events) → the SAME read
    stays NOT ready — complete BEFORE state, never a hybrid that drops
    the blocker mid-read."""
    pid = await _seed_project(factory)
    eva, rev1, assets, anchor_id, f_opt, shots = (
        await _requirement_race_fixture(client, factory, engine, pid)
    )
    await client.patch(
        f"/visual-facets/{f_opt['id']}", json={"requirement": "required"}
    )
    assert (
        await _resolver_result(engine, shots[0])
    ).visual_continuity_ready is False

    async def competitor():
        return await client.patch(
            f"/visual-facets/{f_opt['id']}", json={"requirement": "optional"}
        )

    result, comp, ev = await _reader_vs_competitor(
        lambda: _resolver_result(engine, shots[0]), competitor,
        form="after_snapshot",
    )
    assert comp.status_code == 200, comp.text
    assert ev.snapshot_established.is_set()
    assert ev.competitor_committed.is_set()
    assert result.visual_continuity_ready is False  # BEFORE holds
    codes = {i["error_code"] for i in result.issues}
    assert codes == {"VISUAL_REALIZATION_REQUIRED"}

    # A fresh read observes AFTER (ready once the requirement is gone).
    assert (await _resolver_result(engine, shots[0])).visual_continuity_ready


# --- §82.1 VisualAnchor approval change during the pinned resolver read ----------


async def test_race_unapprove_after_snapshot_pack_survives(
    client, factory, engine,
):
    """Form B: snapshot pinned with the approval present; unapproval
    commits inside the pinned read → the SAME read still yields the
    complete BEFORE pack/hash."""
    pid = await _seed_project(factory)
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )
    before = await _resolver_result(engine, shots[0])
    assert before.visual_continuity_ready

    detail = (await client.get(f"/visual-anchors/{anchor_id}")).json()
    approved = detail["approved_revision_id"]

    async def competitor():
        return await client.post(
            f"/visual-anchors/{anchor_id}/unapprove",
            json={"expected_approved_revision_id": approved},
        )

    result, comp, ev = await _reader_vs_competitor(
        lambda: _resolver_result(engine, shots[0]), competitor,
        form="after_snapshot",
    )
    assert comp.status_code == 200, comp.text
    assert ev.snapshot_established.is_set()
    assert ev.competitor_committed.is_set()
    assert result.visual_continuity_ready is True  # BEFORE holds
    assert result.visual_reference_pack_hash == (
        before.visual_reference_pack_hash
    )
    assert len(result.pack["anchors"]) == 1

    # A fresh read observes AFTER: required anchor now unapproved.
    after = await _resolver_result(engine, shots[0])
    assert after.visual_continuity_ready is False
    codes = {i["error_code"] for i in after.issues}
    assert codes == {"VISUAL_ANCHOR_APPROVAL_REQUIRED"}


async def test_race_unapprove_before_first_read_blocks(
    client, factory, engine,
):
    """Form A: unapproval commits before the resolver's first pinned
    SELECT → the read observes complete AFTER (NOT ready)."""
    pid = await _seed_project(factory)
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )
    detail = (await client.get(f"/visual-anchors/{anchor_id}")).json()
    approved = detail["approved_revision_id"]

    async def competitor():
        return await client.post(
            f"/visual-anchors/{anchor_id}/unapprove",
            json={"expected_approved_revision_id": approved},
        )

    result, comp, ev = await _reader_vs_competitor(
        lambda: _resolver_result(engine, shots[0]), competitor,
        form="before_first_read",
    )
    assert comp.status_code == 200, comp.text
    assert ev.competitor_committed.is_set()
    assert result.visual_continuity_ready is False  # AFTER
    codes = {i["error_code"] for i in result.issues}
    assert codes == {"VISUAL_ANCHOR_APPROVAL_REQUIRED"}


# --- §82.1 M7 semantic source mutation during the pinned resolver read ------------


async def test_race_entity_revision_approval_after_snapshot(
    client, factory, engine,
):
    """Form B (M7 dimension): the pinned read resolves deps against the
    approved rev1; approving rev2 commits inside the pinned read → the
    SAME read still binds rev1 (complete BEFORE pack); a fresh read
    binds rev2 → required realization missing (AFTER)."""
    pid = await _seed_project(factory)
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )
    r = await client.post(
        f"/entities/{eva['id']}/revisions",
        json={"spec": {"description": "second"}},
    )
    rev2 = r.json()["id"]
    before = await _resolver_result(engine, shots[0])
    assert before.visual_continuity_ready

    async def competitor():
        return await client.put(
            f"/entities/{eva['id']}/approved-revision",
            json={
                "revision_id": rev2,
                "expected_approved_revision_id": rev1,
            },
        )

    result, comp, ev = await _reader_vs_competitor(
        lambda: _resolver_result(engine, shots[0]), competitor,
        form="after_snapshot",
    )
    assert comp.status_code == 200, comp.text
    assert ev.snapshot_established.is_set()
    assert ev.competitor_committed.is_set()
    assert result.visual_continuity_ready is True  # BEFORE holds
    assert result.visual_reference_pack_hash == (
        before.visual_reference_pack_hash
    )

    after = await _resolver_result(engine, shots[0])
    assert after.visual_continuity_ready is False  # AFTER
    codes = {i["error_code"] for i in after.issues}
    assert codes == {"VISUAL_REALIZATION_REQUIRED"}


async def test_race_entity_revision_approval_before_first_read(
    client, factory, engine,
):
    """Form A (M7 dimension): rev2 approval commits before the first
    pinned SELECT → the read observes complete AFTER (missing required
    realization bound to rev2)."""
    pid = await _seed_project(factory)
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )
    r = await client.post(
        f"/entities/{eva['id']}/revisions",
        json={"spec": {"description": "second"}},
    )
    rev2 = r.json()["id"]

    async def competitor():
        return await client.put(
            f"/entities/{eva['id']}/approved-revision",
            json={
                "revision_id": rev2,
                "expected_approved_revision_id": rev1,
            },
        )

    result, comp, ev = await _reader_vs_competitor(
        lambda: _resolver_result(engine, shots[0]), competitor,
        form="before_first_read",
    )
    assert comp.status_code == 200, comp.text
    assert ev.competitor_committed.is_set()
    assert result.visual_continuity_ready is False  # AFTER
    codes = {i["error_code"] for i in result.issues}
    assert codes == {"VISUAL_REALIZATION_REQUIRED"}


# --- §82.1 parked-on-lock races ----------------------------------------------------


async def test_race_concurrent_identical_revision_captures_converge(
    client, factory, engine,
):
    """Parked form: the second capture's write-phase BEGIN IMMEDIATE is
    observed EXECUTING against the first capture's held lock; after the
    first commits, the second acquires and converges on the SAME
    revision id via the (anchor, hash) reuse path."""
    pid = await _seed_project(factory)
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )
    await client.put(
        f"/visual-anchors/{anchor_id}/items",
        json=_put_payload(assets, view_keys=["front", "v2"]),
    )

    rid1, rid2, ev = await _parked_on_write_lock(
        lambda: _capture_reader(factory, anchor_id),
        lambda: _capture_reader(factory, anchor_id),
    )
    assert ev.begin_immediate_entered.is_set()
    assert ev.competitor_committed.is_set()
    assert rid1 == rid2  # one revision, both callers

    async with engine.connect() as conn:
        n = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM visual_anchor_revisions "
                    "WHERE visual_anchor_id = :a"
                ),
                {"a": anchor_id},
            )
        ).scalar()
    # approved r1 + exactly ONE new revision from the converged pair.
    assert n == 2


async def _two_candidate_revisions(client, anchor_id, assets):
    await client.put(
        f"/visual-anchors/{anchor_id}/items",
        json=_put_payload(assets, view_keys=["front", "v3"]),
    )
    rev2 = (await client.post(
        f"/visual-anchors/{anchor_id}/revisions")).json()["id"]
    await client.put(
        f"/visual-anchors/{anchor_id}/items",
        json=_put_payload(assets, view_keys=["front", "v4"]),
    )
    rev3 = (await client.post(
        f"/visual-anchors/{anchor_id}/revisions")).json()["id"]
    return rev2, rev3


async def _approve_via_service(factory, revision_id, expected):
    from soloring.visual import anchors as anchor_svc

    async with factory() as s:
        try:
            await anchor_svc.approve_revision(s, revision_id, expected)
            return "ok"
        except Exception as exc:  # noqa: BLE001 — outcome capture
            return getattr(exc, "code", type(exc).__name__)


async def test_race_approval_conflict_two_revisions_parked(
    client, factory, engine,
):
    """Parked form: the second approval's BEGIN IMMEDIATE is observed
    executing against the first approval's held lock; after the first
    commits, the second sees the moved pointer → exactly one winner, the
    loser gets 409 VISUAL_ANCHOR_APPROVAL_CONFLICT."""
    pid = await _seed_project(factory)
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )
    approved = (await client.get(f"/visual-anchors/{anchor_id}")).json()[
        "approved_revision_id"
    ]
    rev2, rev3 = await _two_candidate_revisions(client, anchor_id, assets)

    winner, loser, ev = await _parked_on_write_lock(
        lambda: _approve_via_service(factory, rev2, approved),
        lambda: _approve_via_service(factory, rev3, approved),
    )
    assert ev.begin_immediate_entered.is_set()
    assert sorted([winner, loser]) == [
        "VISUAL_ANCHOR_APPROVAL_CONFLICT", "ok",
    ]
    pointer = (await client.get(f"/visual-anchors/{anchor_id}")).json()[
        "approved_revision_id"
    ]
    assert pointer in (rev2, rev3)


async def test_race_unapproval_vs_approval_parked(
    client, factory, engine,
):
    """Parked form (§82 unapproval race): approval of a successor
    commits while the competitor's unapproval is parked on the held
    lock; the unapproval's expected pointer no longer matches → 409."""
    pid = await _seed_project(factory)
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )
    approved = (await client.get(f"/visual-anchors/{anchor_id}")).json()[
        "approved_revision_id"
    ]
    rev2, _rev3 = await _two_candidate_revisions(client, anchor_id, assets)

    async def unapprove_via_service():
        from soloring.visual import anchors as anchor_svc

        async with factory() as s:
            try:
                await anchor_svc.unapprove_anchor(s, anchor_id, approved)
                return "ok"
            except Exception as exc:  # noqa: BLE001
                return getattr(exc, "code", type(exc).__name__)

    approve_out, unapprove_out, ev = await _parked_on_write_lock(
        lambda: _approve_via_service(factory, rev2, approved),
        unapprove_via_service,
    )
    assert ev.begin_immediate_entered.is_set()
    assert approve_out == "ok"
    assert unapprove_out == "VISUAL_ANCHOR_APPROVAL_CONFLICT"


# --- §66/§82.2 scale gate -----------------------------------------------------------
# Named target-dimension fixture constants (§66: freeze and report these).

SCALE_TOTAL_SHOTS = 2_500            # ~2,500 total Shots in the Project
SCALE_RECURRING_ENTITIES = 6         # 3 characters + 3 locations
SCALE_REVISIONS_PER_ENTITY = 3       # 1 approved (service) + 2 bulk
SCALE_FEATURES = 4                   # ContinuityFeatures on 2 characters
SCALE_FEATURE_VALUES = 3             # enum transitions across the timeline
SCALE_BULK_OPTIONAL_FACETS = 60      # direct SQL, dependency entities
SCALE_BULK_NOISE_ANCHORS = 120       # direct SQL, historical revisions
SCALE_BULK_SCHEMA4_REVISIONS = 200   # direct SQL history, never re-captured


async def _scale_target_fixture(client, factory, engine, pid):
    """Build the §66 representative state: the designated target Shot is
    constructed through the REAL services (entities, revisions,
    features, transitions, facets, anchors, captures, approvals,
    requirement flip, not-applicable override, multi-view items), so the
    production resolver performs the actual applicability work."""
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    # Narrative topology: sceneA (2 shots — transition timeline) then
    # sceneB (target shot last).
    r = await client.post(f"/projects/{pid}/sequences", json={"title": "S"})
    seq = r.json()["id"]
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "A"})
    scene_a = r.json()["id"]
    r = await client.post(f"/sequences/{seq}/scenes", json={"title": "B"})
    scene_b = r.json()["id"]
    timeline, target_list = [], []
    for _ in range(2):
        async with factory() as s:
            timeline.append(
                (await shot_svc.create_shot(
                    s, pid, ShotCreate(subject="t"))).id
            )
    async with factory() as s:
        target_list.append(
            (await shot_svc.create_shot(
                s, pid, ShotCreate(subject="target"))).id
        )
    await client.put(
        f"/scenes/{scene_a}/shots", json={"shot_ids": timeline}
    )
    await client.put(
        f"/scenes/{scene_b}/shots", json={"shot_ids": target_list}
    )
    target = target_list[0]

    # 6 recurring entities (3 characters + 3 locations), approved rev1.
    entities = []
    rev_of = {}
    for i in range(3):
        e, rev = await _entity_with_revision(
            client, factory, pid, name=f"Char{i}", kind="character",
        )
        entities.append(e)
        rev_of[e["id"]] = rev
    for i in range(3):
        e, rev = await _entity_with_revision(
            client, factory, pid, name=f"Loc{i}", kind="location",
        )
        entities.append(e)
        rev_of[e["id"]] = rev
    assets = await _assets(engine, pid, 3)
    ev_ids = [e["id"] for e in entities]
    await _depend(client, target, ev_ids)

    # 4 ContinuityFeatures on characters 0/1, each with 3 enum values
    # transitioned across the timeline; the target's effective value is
    # the LAST one ("scarred").
    features = []
    for k in range(SCALE_FEATURES):
        owner = entities[k % 2]
        features.append((await _feature(
            client, owner["id"], key=f"scale_feat_{k}",
        ), owner))
    values = ("fresh", "healing", "scarred")
    for feat, owner in features:
        await client.post(
            f"/continuity-features/{feat['id']}/transitions",
            json={"anchor_type": "scene", "anchor_id": scene_a,
                  "boundary": "start", "operation": "set",
                  "value": values[0]},
        )
        await client.post(
            f"/continuity-features/{feat['id']}/transitions",
            json={"anchor_type": "shot", "anchor_id": timeline[0],
                  "boundary": "start", "operation": "set",
                  "value": values[1]},
        )
        await client.post(
            f"/continuity-features/{feat['id']}/transitions",
            json={"anchor_type": "shot", "anchor_id": timeline[1],
                  "boundary": "start", "operation": "set",
                  "value": values[2]},
        )

    # Entity facets through the service:
    #   - every entity: 1 required facet + approved multi-view anchor
    #   - entities 0/1: +1 optional approved
    #   - entities 2/3: +1 optional missing (no anchor)
    #   - entity 4: requirement CHANGE — created optional, flipped to
    #     required after approval
    #   - entity 5 anchor gets a second revision (realization change)
    anchors = []
    for i, e in enumerate(entities):
        f = await _facet(
            client, pid, "entity", entity_id=e["id"],
            facet_key=f"core{i}", requirement="required",
        )
        r = await client.post(
            f"/visual-facets/{f['id']}/anchors",
            json={"entity_revision_id": rev_of[e["id"]]},
        )
        anchor_id = r.json()["id"]
        views = ["front", "left-profile", "back"] if i == 0 else ["front"]
        await _approve_anchor(client, anchor_id, assets, views)
        anchors.append(anchor_id)
    for i in (0, 1):
        e = entities[i]
        f = await _facet(
            client, pid, "entity", entity_id=e["id"],
            facet_key=f"opt{i}", requirement="optional",
        )
        r = await client.post(
            f"/visual-facets/{f['id']}/anchors",
            json={"entity_revision_id": rev_of[e["id"]]},
        )
        await _approve_anchor(
            client, r.json()["id"], assets, ["front"]
        )
    for i in (2, 3):
        await _facet(
            client, pid, "entity", entity_id=entities[i]["id"],
            facet_key=f"optmiss{i}", requirement="optional",
        )
    f_flip = await _facet(
        client, pid, "entity", entity_id=entities[4]["id"],
        facet_key="flipped", requirement="optional",
    )
    r = await client.post(
        f"/visual-facets/{f_flip['id']}/anchors",
        json={"entity_revision_id": rev_of[entities[4]["id"]]},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front"])
    await client.patch(
        f"/visual-facets/{f_flip['id']}", json={"requirement": "required"}
    )
    # Realization change: entity 5's anchor captures a second revision.
    await client.put(
        f"/visual-anchors/{anchors[5]}/items",
        json=_put_payload(assets, view_keys=["front", "detail-shot"]),
    )
    r2 = await client.post(f"/visual-anchors/{anchors[5]}/revisions")
    await client.post(
        f"/visual-anchor-revisions/{r2.json()['id']}/approve",
        json={"expected_approved_revision_id": (
            (await client.get(f"/visual-anchors/{anchors[5]}")).json()[
                "approved_revision_id"
            ]
        )},
    )

    # Feature facets: one required approved (current effective value),
    # one optional missing, one not_applicable via value policy.
    feat_req, owner0 = features[0]
    f = await _facet(
        client, pid, "feature", feature_id=feat_req["id"],
        facet_key="realization", requirement="required",
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors",
        json={
            "value": "scarred",
            "visual_context_entity_revision_id": rev_of[owner0["id"]],
        },
    )
    await _approve_anchor(client, r.json()["id"], assets, ["macro"])
    feat_opt, _owner1 = features[1]
    await _facet(
        client, pid, "feature", feature_id=feat_opt["id"],
        facet_key="optfeat", requirement="optional",
    )
    feat_na, owner_na = features[2]
    f_na = await _facet(
        client, pid, "feature", feature_id=feat_na["id"],
        facet_key="nafeat", requirement="required",
    )
    await client.put(
        f"/visual-facets/{f_na['id']}/value-policies",
        json={"policies": [{"value": "scarred",
                            "policy": "not_applicable"}]},
    )
    assert (await client.get(
        f"/visual-facets/{f_na['id']}/value-policies"
    )).status_code == 200

    # One REAL schema-4 historical capture for the target (§66).
    from soloring.domain import revisions as revision_svc

    async with factory() as s:
        captured = await revision_svc.capture_revision(s, target)
    return {
        "target": target, "entities": entities, "features": features,
        "captured": captured, "anchors": anchors,
    }


async def _resolver_phase_measurement(engine, shot_id):
    """Run the composed pinned read; count queries ONLY inside the M8
    resolver phase (the M7 dependency/feature resolution runs first and
    the counter is zeroed before the resolver call). Returns
    (result, resolver_queries, wall_seconds)."""
    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.continuity.state import resolve_effective_feature_state
    from soloring.visual.resolver import resolve_visual_reference_pack_async

    counter = {"n": 0}

    def before_cursor_execute(conn, cursor, statement, params, ctx, many):
        counter["n"] += 1

    async with engine.connect() as conn:
        event.listen(
            conn.sync_connection, "before_cursor_execute",
            before_cursor_execute,
        )
        try:
            await conn.exec_driver_sql("BEGIN")
            deps = await resolve_working_dependencies(conn, shot_id)
            states = await resolve_effective_feature_state(conn, shot_id)
            counter["n"] = 0  # resolver phase starts HERE
            t0 = time.perf_counter()
            result = await resolve_visual_reference_pack_async(
                shot_id, (deps, states.states), conn=conn
            )
            wall = time.perf_counter() - t0
            queries = counter["n"]
            await conn.commit()
        finally:
            event.remove(
                conn.sync_connection, "before_cursor_execute",
                before_cursor_execute,
            )
    return result, queries, wall


async def test_scale_representative_target_fixture_bounded_queries(
    client, factory, engine,
):
    """§65/§66/§82.2: small and representative fixtures resolve through
    the SAME production resolver; the query count is bounded by query
    CLASS, not by target cardinality — asserted equal across fixtures
    whose facet/anchor/item cardinality differs by an order of
    magnitude."""
    # --- small fixture: same dimension SHAPE (entity + feature facets,
    # approved anchors), minimal cardinality.
    pid_small = await _seed_project(factory, name="Small")
    eva, rev1 = await _entity_with_revision(client, factory, pid_small)
    assets = await _assets(engine, pid_small, 1)
    f_e = await _facet(
        client, pid_small, "entity", entity_id=eva["id"], facet_key="face",
    )
    r = await client.post(
        f"/visual-facets/{f_e['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front"])
    feat = await _feature(client, eva["id"], key="small_feat")
    seq, scene, shots = await _topology(client, factory, pid_small)
    await _depend(client, shots[0], [eva["id"]])
    await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )
    f_f = await _facet(
        client, pid_small, "feature", feature_id=feat["id"],
        facet_key="cut",
    )
    r = await client.post(
        f"/visual-facets/{f_f['id']}/anchors",
        json={"value": "fresh",
              "visual_context_entity_revision_id": rev1},
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front"])

    small, small_q, small_wall = await _resolver_phase_measurement(
        engine, shots[0]
    )
    assert small.visual_continuity_ready is True
    assert len(small.pack["anchors"]) == 2

    # --- representative fixture.
    pid = await _seed_project(factory, name="Scale")
    fix = await _scale_target_fixture(client, factory, engine, pid)
    target = fix["target"]

    result, big_q, big_wall = await _resolver_phase_measurement(
        engine, target
    )
    assert result.visual_continuity_ready is True
    pack = result.pack
    approved_anchors = len(pack["anchors"])
    multi_item = [a for a in pack["anchors"] if len(a["items"]) >= 3]
    statuses = result.facet_statuses
    missing = [s for s in statuses if s.resolved == "missing"]
    not_applicable = [s for s in statuses if s.resolved == "not_applicable"]

    # Target-dimension assertions (§66 exercise list). Pre-bulk: the
    # three optional-missing facets (2 entity optmiss + 1 feature opt).
    assert approved_anchors == 10  # 6 core + 2 optional + 1 flipped + 1 feat
    assert multi_item, "multi-item approved pack must be exercised"
    assert len(missing) == 3
    assert len(statuses) == 14
    assert len(not_applicable) == 1  # the value-policy override
    assert any(a["visual_anchor_revision_id"] for a in pack["anchors"])

    # Determinism across two full resolutions.
    again, _, _ = await _resolver_phase_measurement(engine, target)
    assert again.visual_reference_pack_hash == (
        result.visual_reference_pack_hash
    )
    assert json.dumps(again.pack, sort_keys=True) == json.dumps(
        pack, sort_keys=True
    )

    # THE gate: equal query count across an order-of-magnitude
    # cardinality difference — bounded by class, not by volume.
    assert big_q == small_q, (big_q, small_q)

    # Recorded observations (no invented wall-clock threshold, §65).
    async with engine.connect() as conn:
        counts = {}
        for table in (
            "shots", "entity_revisions", "visual_facets",
            "visual_anchors", "visual_anchor_revisions", "shot_revisions",
        ):
            counts[table] = (await conn.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            )).scalar()
    print(
        "\n[§66 evidence] resolver queries: small="
        f"{small_q} representative={big_q} | wall: small="
        f"{small_wall * 1000:.1f}ms representative={big_wall * 1000:.1f}ms"
        f" | pack anchors={approved_anchors} statuses={len(statuses)} "
        f"missing={len(missing)} not_applicable={len(not_applicable)} "
        f"| table rows={counts}"
    )


async def test_scale_bulk_wiring_disclosed_invariants(
    client, factory, engine,
):
    """§66 direct-SQL bulk wiring with full disclosure: the ~2,500-Shot
    volume, historical entity revisions, optional facets, noise anchors
    (bound to historical revisions, never applicable), and bulk
    schema-4 history rows — all preserving frozen constraints, measured
    through the production resolver."""
    pid = await _seed_project(factory, name="Bulk")
    fix = await _scale_target_fixture(client, factory, engine, pid)
    target = fix["target"]
    entities = fix["entities"]

    now = "2026-01-01T00:00:00.000Z"
    async with engine.begin() as conn:
        # ~2,500 total Shots (service already created 3).
        bulk_shots = SCALE_TOTAL_SHOTS - 3
        shot_rows = [
            {
                "id": str(_uuid.uuid4()),
                "project_id": pid,
                "shot_number": 1000 + k,
                "title": None, "subject": f"bulk {k}", "action": None,
                "environment": None, "framing": None, "camera_motion": None,
                "lens": None, "mood": None, "duration_ms": None,
                "created_at": now, "updated_at": now,
            }
            for k in range(bulk_shots)
        ]
        await conn.execute(
            text(
                "INSERT INTO shots (id, project_id, shot_number, title, "
                "subject, action, environment, framing, camera_motion, "
                "lens, mood, duration_ms, created_at, updated_at) "
                "VALUES (:id, :project_id, :shot_number, :title, "
                ":subject, :action, :environment, :framing, "
                ":camera_motion, :lens, :mood, :duration_ms, "
                ":created_at, :updated_at)"
            ),
            shot_rows,
        )

        # Historical (unapproved) entity revisions: 2 per entity, with
        # their kind-specific spec companions (the frozen shape stores
        # spec_json in character_/location_revision_specs, never on the
        # immutable revision row itself).
        hist_revs = []
        char_specs = []
        loc_specs = []
        for e in entities:
            is_location = e["kind"] == "location"
            for j in range(SCALE_REVISIONS_PER_ENTITY - 1):
                spec = {"description": f"history {j}"}
                spec_bytes = json.dumps(
                    spec, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
                row = {
                    "id": str(_uuid.uuid4()),
                    "entity_id": e["id"],
                    "revision_number": 10 + j,
                    "schema_version": 1,
                    "spec_hash": hashlib.sha256(spec_bytes).hexdigest(),
                    "spec_json": spec_bytes.decode("utf-8"),
                    "created_at": now,
                }
                hist_revs.append(row)
                (loc_specs if is_location else char_specs).append({
                    "revision_id": row["id"],
                    "spec_json": row["spec_json"],
                })
        await conn.execute(
            text(
                "INSERT INTO entity_revisions (id, entity_id, "
                "revision_number, schema_version, spec_hash, created_at) "
                "VALUES (:id, :entity_id, :revision_number, "
                ":schema_version, :spec_hash, :created_at)"
            ),
            [
                {k: r[k] for k in (
                    "id", "entity_id", "revision_number", "schema_version",
                    "spec_hash", "created_at",
                )}
                for r in hist_revs
            ],
        )
        await conn.execute(
            text(
                "INSERT INTO character_revision_specs (revision_id, "
                "spec_json) VALUES (:revision_id, :spec_json)"
            ),
            char_specs,
        )
        await conn.execute(
            text(
                "INSERT INTO location_revision_specs (revision_id, "
                "spec_json) VALUES (:revision_id, :spec_json)"
            ),
            loc_specs,
        )

        # Optional facets on the dependency entities (no anchors).
        facet_rows = [
            {
                "id": f"a2000000-0000-4000-8000-{k:012d}",
                "project_id": pid,
                "target_kind": "entity",
                "entity_id": entities[k % len(entities)]["id"],
                "feature_id": None,
                "facet_key": f"bulk{k:03d}",
                "label": None, "description": None,
                "requirement": "optional",
                "created_at": now, "updated_at": now,
            }
            for k in range(SCALE_BULK_OPTIONAL_FACETS)
        ]
        await conn.execute(
            text(
                "INSERT INTO visual_facets (id, project_id, target_kind, "
                "entity_id, feature_id, facet_key, label, description, "
                "requirement, created_at, updated_at) VALUES (:id, "
                ":project_id, :target_kind, :entity_id, :feature_id, "
                ":facet_key, :label, :description, :requirement, "
                ":created_at, :updated_at)"
            ),
            facet_rows,
        )

        # Noise anchors bound to HISTORICAL revisions (never applicable
        # to the target's approved revisions), each with one structurally
        # valid revision row (never approved — integrity never invoked).
        noise_anchors = []
        for k in range(SCALE_BULK_NOISE_ANCHORS):
            # Injective pairing: k and k + |facets| share the facet but
            # take different historical revisions — the partial unique
            # index on (visual_facet_id, entity_revision_id) stays clean.
            hist = hist_revs[(k // len(facet_rows)) % len(hist_revs)]
            facet = facet_rows[k % len(facet_rows)]
            snap = {"schema_version": 1, "binding": {
                "visual_facet_id": facet["id"],
                "facet_key": facet["facet_key"],
                "target_kind": "entity",
            }, "items": []}
            snap_bytes = json.dumps(
                snap, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            noise_anchors.append({
                "id": str(_uuid.uuid4()),
                "visual_facet_id": facet["id"],
                "entity_revision_id": hist["id"],
                "revision_id": str(_uuid.uuid4()),
                "snapshot_json": snap_bytes.decode("utf-8"),
                "snapshot_hash": hashlib.sha256(snap_bytes).hexdigest(),
                "created_at": now, "updated_at": now,
            })
        await conn.execute(
            text(
                "INSERT INTO visual_anchors (id, visual_facet_id, "
                "entity_revision_id, created_at, updated_at) VALUES "
                "(:id, :visual_facet_id, :entity_revision_id, "
                ":created_at, :updated_at)"
            ),
            [
                {k: a[k] for k in (
                    "id", "visual_facet_id", "entity_revision_id",
                    "created_at", "updated_at",
                )}
                for a in noise_anchors
            ],
        )
        await conn.execute(
            text(
                "INSERT INTO visual_anchor_revisions (id, "
                "visual_anchor_id, revision_number, snapshot_json, "
                "snapshot_hash, created_at) VALUES (:revision_id, :id, "
                "1, :snapshot_json, :snapshot_hash, :created_at)"
            ),
            noise_anchors,
        )

        # Bulk schema-4 history rows (minimal valid snapshots, unique
        # hashes; never re-captured so reuse integrity never fires).
        rev_rows = []
        for k in range(SCALE_BULK_SCHEMA4_REVISIONS):
            snap = {"schema_version": 4, "k": k}
            snap_bytes = json.dumps(
                snap, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            rev_rows.append({
                "id": str(_uuid.uuid4()),
                "shot_id": shot_rows[k]["id"],
                "snapshot_json": snap_bytes.decode("utf-8"),
                "snapshot_hash": hashlib.sha256(snap_bytes).hexdigest(),
                "created_at": now,
            })
        await conn.execute(
            text(
                "INSERT INTO shot_revisions (id, shot_id, revision_number,"
                " snapshot_json, snapshot_hash, created_at) VALUES "
                "(:id, :shot_id, 1, :snapshot_json, :snapshot_hash, "
                ":created_at)"
            ),
            rev_rows,
        )

    # The production resolver performs the actual applicability work
    # over the bulk-laden database and stays deterministic + bounded.
    result, queries, wall = await _resolver_phase_measurement(
        engine, target
    )
    assert result.visual_continuity_ready is True
    assert len(result.pack["anchors"]) == 10
    missing = [s for s in result.facet_statuses if s.resolved == "missing"]
    # bulk optional facets + 2 entity optmiss + 1 optional feature facet
    assert len(missing) == SCALE_BULK_OPTIONAL_FACETS + 3
    assert len(result.facet_statuses) == 14 + SCALE_BULK_OPTIONAL_FACETS

    async with engine.connect() as conn:
        total_shots = (await conn.execute(
            text("SELECT COUNT(*) FROM shots WHERE project_id = :p"),
            {"p": pid},
        )).scalar()
    assert total_shots == SCALE_TOTAL_SHOTS
    print(
        f"\n[§66 bulk evidence] resolver queries={queries} "
        f"wall={wall * 1000:.1f}ms total_shots={total_shots}"
    )


# --- §82 Exact Rerun current-table query spy ---------------------------------------


async def test_exact_rerun_query_spy_current_table_prohibition(
    client, factory, engine, settings,
):
    """§82/§59: during Exact Rerun creation the CURRENT mutable M8
    tables (visual_facets, visual_facet_value_policies, visual_anchors,
    visual_anchor_items) are never queried — historical generation
    inputs only."""
    import re

    from soloring.executors.fake import FakeExecutor
    from soloring.worker import execution as worker_execution
    from soloring.worker.ownership import acquire_worker_lease
    from tests.conftest import seed_reference_asset
    from soloring.api.schemas.references import ReferenceInput
    from soloring.domain import references as ref_svc

    pid = await _seed_project(factory)
    eva, rev1, assets, (anchor_id,), (seq, scene, shots) = (
        await _approved_fixture(client, factory, engine, pid)
    )
    aid, _bh = await seed_reference_asset(engine, pid)
    async with factory() as s:
        await ref_svc.replace_references(
            s, shots[0], [ReferenceInput(asset_id=aid, role="reference")]
        )

    await acquire_worker_lease(engine, "w-m8f", 30)
    genA = (await client.post(f"/shots/{shots[0]}/generations")).json()
    assert (await worker_execution.process_next_generation(
        engine, settings, "w-m8f", FakeExecutor())) == "succeeded"
    revX = genA["shot_revision_id"]
    snap = json.loads(
        (await _fetch_one(
            engine, "SELECT snapshot_json FROM shot_revisions "
            "WHERE id = :r", {"r": revX},
        ))["snapshot_json"]
    )
    assert snap["schema_version"] == 4  # visual provenance exists

    # The app builds its OWN engine over the shared DB file, so the spy
    # listens on the base Engine class — every connection in the process.
    from sqlalchemy.engine import Engine as SyncEngine

    captured: list[str] = []

    def before_cursor_execute(conn, cursor, statement, params, ctx, many):
        captured.append(statement)

    event.listen(
        SyncEngine, "before_cursor_execute", before_cursor_execute
    )
    try:
        r = await client.post(f"/generations/{genA['id']}/rerun")
        assert r.status_code == 202, r.text
        assert r.json()["shot_revision_id"] == revX
    finally:
        event.remove(
            SyncEngine, "before_cursor_execute", before_cursor_execute,
        )
    assert captured, "the rerun must have executed queries to observe"

    current_tables = (
        "visual_facets", "visual_facet_value_policies",
        "visual_anchors", "visual_anchor_items",
    )
    pattern = re.compile(
        r"\b(?:FROM|JOIN|UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+("
        + "|".join(current_tables)
        + r")\b",
        re.IGNORECASE,
    )
    offenders = [s for s in captured if pattern.search(s)]
    assert offenders == [], offenders
    # The rerun read historical inputs (generations/generation_inputs).
    assert any("FROM generations" in s for s in captured)
    assert any("generation_inputs" in s for s in captured)


async def _fetch_one(engine, sql, params=None):
    async with engine.connect() as conn:
        return dict(
            (await conn.execute(
                text(sql), params or {}
            )).mappings().one()
        )


# --- §82 source-audit prohibitions -------------------------------------------------


async def test_no_asset_delete_route_or_blob_gc_added():
    """§82: M8 adds no Asset/Blob deletion surface; no GC exists."""
    import inspect

    import soloring.api.assets as assets_api
    import soloring.api.blobs as blobs_api

    for module in (assets_api, blobs_api):
        src = inspect.getsource(module)
        assert "@router.delete" not in src, module.__name__
