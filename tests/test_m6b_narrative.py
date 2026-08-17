"""M6B — narrative structure tests (M6 plan §31–§42).

Gate proof (§42): existing Shots start unassigned, assignment/reorder never
touches shot_number/ShotRevision/Generation, and invalid reorders roll back
completely. Ordering uses only persisted positions (§37) and never performs
direct swaps under immediate UNIQUE constraints (§38). Deletion guards and
the full-set membership semantics (§39) are pinned, plus the M6A-lesson
lifecycle race regressions for the new fenced mutations.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects as project_svc
from soloring.domain import shots as shot_svc
from soloring.errors import SoloRingError


async def _seed_project(factory) -> str:
    async with factory() as s:
        return (await project_svc.create_project(
            s, ProjectCreate(name="P")
        )).id


async def _seed_shots(factory, pid: str, n: int) -> list[str]:
    ids = []
    async with factory() as s:
        for i in range(n):
            shot = await shot_svc.create_shot(
                s, pid, ShotCreate(subject=f"shot {i}")
            )
            ids.append(shot.id)
    return ids


async def _create_sequence(client, pid: str, title=None) -> dict:
    r = await client.post(f"/projects/{pid}/sequences", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


async def _create_scene(client, sequence_id: str, title=None) -> dict:
    r = await client.post(
        f"/sequences/{sequence_id}/scenes", json={"title": title}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _put_shots(client, scene_id: str, shot_ids: list[str]):
    return await client.put(
        f"/scenes/{scene_id}/shots", json={"shot_ids": shot_ids}
    )


async def _fetch(engine, sql: str, params: dict):
    async with engine.connect() as conn:
        row = (await conn.execute(text(sql), params)).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _fetch_all(engine, sql: str, params: dict | None = None):
    async with engine.connect() as conn:
        rows = (await conn.execute(text(sql), params or {})).mappings().all()
    return [dict(r) for r in rows]


# --- §42 gate proof -------------------------------------------------------------


async def test_m6b_gate_proof(client, factory, engine):
    pid = await _seed_project(factory)
    shot_ids = await _seed_shots(factory, pid, 3)

    # Existing Shots start unassigned (zero narrative inference).
    for sid in shot_ids:
        row = await _fetch(
            engine, "SELECT scene_id, scene_position FROM shots WHERE id = :s",
            {"s": sid},
        )
        assert row["scene_id"] is None and row["scene_position"] is None

    seq = await _create_sequence(client, pid, title="Act I")
    scene = await _create_scene(client, seq["id"], title="Lobby")
    assert seq["position"] == 0 and scene["position"] == 0

    before = await _fetch_all(
        engine,
        "SELECT id, shot_number, subject FROM shots WHERE project_id = :p "
        "ORDER BY shot_number",
        {"p": pid},
    )
    revisions_before = await _fetch_all(
        engine, "SELECT id, snapshot_hash FROM shot_revisions"
    )
    generations_before = await _fetch_all(
        engine, "SELECT COUNT(*) AS n FROM generations"
    )

    # Assign out of shot_number order; narrative position is explicit.
    r = await _put_shots(client, scene["id"], [shot_ids[2], shot_ids[0]])
    assert r.status_code == 200, r.text
    rows = await _fetch_all(
        engine,
        "SELECT id, scene_position, scene_id, shot_number FROM shots "
        "WHERE scene_id = :c ORDER BY scene_position",
        {"c": scene["id"]},
    )
    assert [r_["id"] for r_ in rows] == [shot_ids[2], shot_ids[0]]
    assert [r_["scene_position"] for r_ in rows] == [0, 1]

    # Reorder within the scene (swap under immediate UNIQUE — §38).
    r = await _put_shots(client, scene["id"], [shot_ids[0], shot_ids[2]])
    assert r.status_code == 200, r.text
    rows = await _fetch_all(
        engine,
        "SELECT id, scene_position FROM shots WHERE scene_id = :c "
        "ORDER BY scene_position",
        {"c": scene["id"]},
    )
    assert [r_["id"] for r_ in rows] == [shot_ids[0], shot_ids[2]]

    # Production identity untouched by all narrative activity.
    after = await _fetch_all(
        engine,
        "SELECT id, shot_number, subject FROM shots WHERE project_id = :p "
        "ORDER BY shot_number",
        {"p": pid},
    )
    assert after == before
    assert await _fetch_all(
        engine, "SELECT id, snapshot_hash FROM shot_revisions"
    ) == revisions_before
    assert await _fetch_all(
        engine, "SELECT COUNT(*) AS n FROM generations"
    ) == generations_before


# --- sequence/scene CRUD + ordering ----------------------------------------------


async def test_sequence_and_scene_positions_contiguous(client, factory):
    pid = await _seed_project(factory)
    seqs = [
        await _create_sequence(client, pid, title=f"S{i}") for i in range(3)
    ]
    assert [s["position"] for s in seqs] == [0, 1, 2]

    scenes = [
        await _create_scene(client, seqs[0]["id"], title=f"C{i}")
        for i in range(2)
    ]
    assert [c["position"] for c in scenes] == [0, 1]

    # Blank titles normalize to null.
    blank = await _create_sequence(client, pid, title="   ")
    assert blank["title"] is None


async def test_sequence_reorder_swap_and_rollback(client, factory, engine):
    pid = await _seed_project(factory)
    a = await _create_sequence(client, pid, "A")
    b = await _create_sequence(client, pid, "B")
    c = await _create_sequence(client, pid, "C")

    r = await client.put(
        f"/projects/{pid}/sequences/order",
        json={"sequence_ids": [c["id"], a["id"], b["id"]]},
    )
    assert r.status_code == 200, r.text
    listed = (await client.get(f"/projects/{pid}/sequences")).json()
    assert [s["id"] for s in listed] == [c["id"], a["id"], b["id"]]

    # Missing member -> invalid, nothing changes (complete rollback).
    r = await client.put(
        f"/projects/{pid}/sequences/order",
        json={"sequence_ids": [a["id"], b["id"]]},
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "NARRATIVE_ORDER_INVALID"
    listed = (await client.get(f"/projects/{pid}/sequences")).json()
    assert [s["id"] for s in listed] == [c["id"], a["id"], b["id"]]

    # Duplicates and unknown ids rejected.
    r = await client.put(
        f"/projects/{pid}/sequences/order",
        json={"sequence_ids": [a["id"], a["id"], b["id"], c["id"]]},
    )
    assert r.status_code == 422
    r = await client.put(
        f"/projects/{pid}/sequences/order",
        json={"sequence_ids": [a["id"], b["id"], c["id"], "not-a-uuid"]},
    )
    assert r.status_code == 422


async def test_scene_reorder_under_sequence(client, factory):
    pid = await _seed_project(factory)
    seq = await _create_sequence(client, pid, "S")
    c0 = await _create_scene(client, seq["id"], "0")
    c1 = await _create_scene(client, seq["id"], "1")

    r = await client.put(
        f"/sequences/{seq['id']}/scenes/order",
        json={"scene_ids": [c1["id"], c0["id"]]},
    )
    assert r.status_code == 200, r.text
    listed = (await client.get(f"/sequences/{seq['id']}/scenes")).json()
    assert [c["id"] for c in listed] == [c1["id"], c0["id"]]

    # A scene from another sequence is not a member here.
    other = await _create_sequence(client, pid, "Other")
    foreign = await _create_scene(client, other["id"], "F")
    r = await client.put(
        f"/sequences/{seq['id']}/scenes/order",
        json={"scene_ids": [c0["id"], c1["id"], foreign["id"]]},
    )
    assert r.status_code == 422


async def test_rename_and_not_found(client, factory):
    pid = await _seed_project(factory)
    seq = await _create_sequence(client, pid, "A")
    r = await client.patch(f"/sequences/{seq['id']}", json={"title": "Act II"})
    assert r.status_code == 200 and r.json()["title"] == "Act II"

    scene = await _create_scene(client, seq["id"], "C")
    r = await client.patch(
        f"/scenes/{scene['id']}", json={"title": "Lobby", "description": "d"}
    )
    assert r.status_code == 200 and r.json()["title"] == "Lobby"

    from soloring.domain.ids import new_uuid

    assert (await client.get(
        f"/sequences/{str(new_uuid())}"
    )).status_code == 404
    assert (await client.get(
        f"/scenes/{str(new_uuid())}"
    )).status_code == 404


# --- deletion guards (§41) --------------------------------------------------------


async def test_sequence_and_scene_deletion_guards(client, factory, engine):
    pid = await _seed_project(factory)
    shot_ids = await _seed_shots(factory, pid, 2)
    seq = await _create_sequence(client, pid, "S")
    scene = await _create_scene(client, seq["id"], "C")

    # Sequence with active scene -> IN_USE.
    r = await client.delete(f"/sequences/{seq['id']}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "SEQUENCE_IN_USE"

    # Scene with assigned active shot -> IN_USE.
    assert (await _put_shots(client, scene["id"], [shot_ids[0]])).status_code == 200
    r = await client.delete(f"/scenes/{scene['id']}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "SCENE_IN_USE"

    # Full-set unassignment frees the scene; deletion then succeeds.
    assert (await _put_shots(client, scene["id"], [])).status_code == 200
    assert (await client.delete(f"/scenes/{scene['id']}")).status_code == 204
    # Hidden from lists; idempotent delete.
    assert (await client.get(f"/sequences/{seq['id']}/scenes")).json() == []
    assert (await client.delete(f"/scenes/{scene['id']}")).status_code == 204

    # Soft-deleted assigned Shot does not block scene deletion.
    scene2 = await _create_scene(client, seq["id"], "C2")
    assert (await _put_shots(
        client, scene2["id"], [shot_ids[1]]
    )).status_code == 200
    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE shots SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :s"),
            {"s": shot_ids[1]},
        )
        await conn.commit()
    assert (await client.delete(f"/scenes/{scene2['id']}")).status_code == 204

    # Now empty sequence is deletable.
    assert (await client.delete(f"/sequences/{seq['id']}")).status_code == 204


# --- membership semantics (§39) ----------------------------------------------------


async def test_assignment_full_set_semantics(client, factory, engine):
    pid = await _seed_project(factory)
    shots = await _seed_shots(factory, pid, 3)
    seq = await _create_sequence(client, pid, "S")
    scene = await _create_scene(client, seq["id"], "C")

    assert (await _put_shots(client, scene["id"], shots[:2])).status_code == 200
    # Omitting a member unassigns it; remaining renumbered from 0.
    assert (await _put_shots(client, scene["id"], [shots[1]])).status_code == 200
    rows = await _fetch_all(
        engine,
        "SELECT id, scene_id, scene_position FROM shots "
        "WHERE project_id = :p",
        {"p": pid},
    )
    by_id = {r_["id"]: r_ for r_ in rows}
    assert by_id[shots[0]]["scene_id"] is None
    assert by_id[shots[0]]["scene_position"] is None
    assert by_id[shots[1]]["scene_id"] == scene["id"]
    assert by_id[shots[1]]["scene_position"] == 0
    assert by_id[shots[2]]["scene_id"] is None

    # Empty set unassigns everything.
    assert (await _put_shots(client, scene["id"], [])).status_code == 200
    rows = await _fetch_all(
        engine, "SELECT scene_id FROM shots WHERE project_id = :p", {"p": pid}
    )
    assert all(r_["scene_id"] is None for r_ in rows)


async def test_assignment_rejections(client, factory):
    pid = await _seed_project(factory)
    shots = await _seed_shots(factory, pid, 2)
    seq = await _create_sequence(client, pid, "S")
    scene_a = await _create_scene(client, seq["id"], "A")
    scene_b = await _create_scene(client, seq["id"], "B")

    # Duplicate ids.
    r = await _put_shots(client, scene_a["id"], [shots[0], shots[0]])
    assert r.status_code == 422

    # Missing/deleted shot.
    from soloring.domain.ids import new_uuid

    r = await _put_shots(client, scene_a["id"], [str(new_uuid())])
    assert r.status_code == 422

    # Shot already assigned to another scene is never silently stolen.
    assert (await _put_shots(client, scene_a["id"], [shots[0]])).status_code == 200
    r = await _put_shots(client, scene_b["id"], [shots[0]])
    assert r.status_code == 422
    assert r.json()["error_code"] == "NARRATIVE_ORDER_INVALID"
    # But re-asserting membership in the SAME scene is legal (reorder).
    assert (await _put_shots(client, scene_a["id"], [shots[0]])).status_code == 200

    # Cross-project shot.
    other_pid = await _seed_project(factory)
    other_shot = (await _seed_shots(factory, other_pid, 1))[0]
    r = await _put_shots(client, scene_a["id"], [other_shot])
    assert r.status_code == 422

    # Unknown scene.
    from soloring.domain.ids import new_uuid as _nuuid

    assert (await _put_shots(
        client, str(_nuuid()), [shots[0]]
    )).status_code == 404


async def test_cross_project_scene_and_sequence(client, factory):
    pid = await _seed_project(factory)
    other_pid = await _seed_project(factory)
    seq = await _create_sequence(client, pid, "S")
    other_seq = await _create_sequence(client, other_pid, "OS")

    # Shots of another project cannot be assigned (checked above); scenes
    # belong to their sequence's project by construction. Cross-project
    # sequence ordering requests are simply not a member set.
    r = await client.put(
        f"/projects/{pid}/sequences/order",
        json={"sequence_ids": [seq["id"], other_seq["id"]]},
    )
    assert r.status_code == 422


# --- timestamps never define order (§37) ------------------------------------------


async def test_order_comes_only_from_positions(client, factory):
    pid = await _seed_project(factory)
    seqs = [
        await _create_sequence(client, pid, f"S{i}") for i in range(3)
    ]
    listed = (await client.get(f"/projects/{pid}/sequences")).json()
    assert [s["id"] for s in listed] == [s["id"] for s in seqs]


# --- project cascade now covers real narrative rows ---------------------------------


async def test_project_deletion_cascades_sequences_and_scenes(
    client, factory, engine
):
    pid = await _seed_project(factory)
    seq = await _create_sequence(client, pid, "S")
    scene = await _create_scene(client, seq["id"], "C")

    assert (await client.delete(f"/projects/{pid}")).status_code == 204
    seq_row = await _fetch(
        engine, "SELECT deleted_at FROM sequences WHERE id = :s",
        {"s": seq["id"]},
    )
    scene_row = await _fetch(
        engine, "SELECT deleted_at FROM scenes WHERE id = :c",
        {"c": scene["id"]},
    )
    assert seq_row["deleted_at"] is not None
    assert scene_row["deleted_at"] is not None


# --- M6A-lesson lifecycle races on the new mutations --------------------------------


async def _parked_scene_delete(engine, scene_id: str) -> None:
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE scenes SET deleted_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :cid"
            ),
            {"cid": scene_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def test_sequence_create_delete_first_and_create_first(
    client, factory, engine
):
    pid = await _seed_project(factory)
    from soloring.narrative import sequences as sequence_svc

    # Delete-first: create observes the tombstone.
    async with factory() as s:
        await project_svc.delete_project(s, pid)
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await sequence_svc.create_sequence(s, pid, "S")
    assert ei.value.code == "PROJECT_NOT_FOUND"
    assert (await _fetch(
        engine, "SELECT COUNT(*) AS n FROM sequences", {}
    ))["n"] == 0

    # Create-first: the cascade tombstones the sequence.
    pid2 = await _seed_project(factory)
    async with factory() as s:
        await sequence_svc.create_sequence(s, pid2, "S")
    assert (await client.delete(f"/projects/{pid2}")).status_code == 204
    assert (await _fetch(
        engine, "SELECT COUNT(*) AS n FROM sequences "
        "WHERE deleted_at IS NULL", {}
    ))["n"] == 0


async def test_scene_patch_delete_race_lock_parking(
    client, factory, engine, monkeypatch
):
    """Forced interleaving: the competing DELETE parks on the held write
    lock after the in-unit active re-read; the PATCH commits on the active
    row; the DELETE completes after. Never a post-tombstone mutation."""
    from soloring.narrative import scenes as scene_svc

    pid = await _seed_project(factory)
    seq = await _create_sequence(client, pid, "S")
    scene = await _create_scene(client, seq["id"], "Original")

    original = scene_svc._verify_active_scene
    state: dict = {}

    async def wrap(conn, scene_id):
        await original(conn, scene_id)
        if "task" not in state:
            state["task"] = asyncio.create_task(
                _parked_scene_delete(engine, scene_id)
            )
            await asyncio.sleep(0.3)  # delete parked on our lock

    monkeypatch.setattr(scene_svc, "_verify_active_scene", wrap)
    from soloring.api.schemas.narrative import ScenePatch

    async with factory() as s:
        await scene_svc.patch_scene(
            s, scene["id"], ScenePatch(title="Renamed")
        )
    await state["task"]

    row = await _fetch(
        engine,
        "SELECT title, deleted_at, (updated_at <= deleted_at) AS coherent "
        "FROM scenes WHERE id = :c",
        {"c": scene["id"]},
    )
    assert row["title"] == "Renamed"
    assert row["deleted_at"] is not None
    assert row["coherent"] == 1


async def test_scene_patch_delete_first_tombstone_untouched(
    client, factory, engine
):
    pid = await _seed_project(factory)
    seq = await _create_sequence(client, pid, "S")
    scene = await _create_scene(client, seq["id"], "Original")
    assert (await client.delete(f"/scenes/{scene['id']}")).status_code == 204
    before = await _fetch(
        engine,
        "SELECT title, updated_at, deleted_at FROM scenes WHERE id = :c",
        {"c": scene["id"]},
    )
    r = await client.patch(f"/scenes/{scene['id']}", json={"title": "X"})
    assert r.status_code == 404
    after = await _fetch(
        engine,
        "SELECT title, updated_at, deleted_at FROM scenes WHERE id = :c",
        {"c": scene["id"]},
    )
    assert after == before

# --- M6B re-gate: active-only ordering + partial PATCH ----------------------------


async def test_sequence_delete_compacts_and_append_stays_contiguous(
    client, factory, engine
):
    """Blocker 1 matrix: create A/B/C, delete B -> actives exactly 0/1;
    create D -> actives exactly 0/1/2; tombstone B keeps its coordinates."""
    pid = await _seed_project(factory)
    a = await _create_sequence(client, pid, "A")
    b = await _create_sequence(client, pid, "B")
    c = await _create_sequence(client, pid, "C")

    assert (await client.delete(f"/sequences/{b['id']}")).status_code == 204
    rows = await _fetch_all(
        engine,
        "SELECT id, position, deleted_at FROM sequences "
        "WHERE project_id = :p ORDER BY position",
        {"p": pid},
    )
    active = [(r["id"], r["position"]) for r in rows if r["deleted_at"] is None]
    assert active == [(a["id"], 0), (c["id"], 1)]
    tomb = next(r for r in rows if r["id"] == b["id"])
    assert tomb["deleted_at"] is not None and tomb["position"] == 1

    d = await _create_sequence(client, pid, "D")
    rows = await _fetch_all(
        engine,
        "SELECT id, position, deleted_at FROM sequences "
        "WHERE project_id = :p ORDER BY position",
        {"p": pid},
    )
    active = [(r["id"], r["position"]) for r in rows if r["deleted_at"] is None]
    assert active == [(a["id"], 0), (c["id"], 1), (d["id"], 2)]
    # Tombstone B is still at 1 — D did not extend past it.
    tomb = next(r for r in rows if r["id"] == b["id"])
    assert tomb["position"] == 1


async def test_scene_delete_compacts_actives(client, factory, engine):
    pid = await _seed_project(factory)
    seq = await _create_sequence(client, pid, "S")
    c0 = await _create_scene(client, seq["id"], "0")
    c1 = await _create_scene(client, seq["id"], "1")
    c2 = await _create_scene(client, seq["id"], "2")

    assert (await client.delete(f"/scenes/{c1['id']}")).status_code == 204
    rows = await _fetch_all(
        engine,
        "SELECT id, position, deleted_at FROM scenes "
        "WHERE sequence_id = :s ORDER BY position",
        {"s": seq["id"]},
    )
    active = [(r["id"], r["position"]) for r in rows if r["deleted_at"] is None]
    assert active == [(c0["id"], 0), (c2["id"], 1)]


async def test_reorder_never_touches_tombstones(client, factory, engine):
    pid = await _seed_project(factory)
    a = await _create_sequence(client, pid, "A")
    b = await _create_sequence(client, pid, "B")
    c = await _create_sequence(client, pid, "C")
    assert (await client.delete(f"/sequences/{b['id']}")).status_code == 204
    tomb_before = await _fetch(
        engine,
        "SELECT position, deleted_at, updated_at FROM sequences "
        "WHERE id = :i",
        {"i": b["id"]},
    )

    r = await client.put(
        f"/projects/{pid}/sequences/order",
        json={"sequence_ids": [c["id"], a["id"]]},
    )
    assert r.status_code == 200, r.text

    tomb_after = await _fetch(
        engine,
        "SELECT position, deleted_at, updated_at FROM sequences "
        "WHERE id = :i",
        {"i": b["id"]},
    )
    assert tomb_after == tomb_before  # tombstone untouched by active reorder
    listed = (await client.get(f"/projects/{pid}/sequences")).json()
    assert [s["id"] for s in listed] == [c["id"], a["id"]]
    # An active row legally occupies the tombstone's old position 1.
    positions = {s["id"]: s["position"] for s in listed}
    assert positions[a["id"]] == 1 and positions[c["id"]] == 0


async def test_membership_never_mutates_deleted_shot(
    client, factory, engine
):
    """Blocker 1 (shots): a soft-deleted assigned Shot keeps its narrative
    coordinates through unrelated membership/reorder operations."""
    pid = await _seed_project(factory)
    shots = await _seed_shots(factory, pid, 3)
    seq = await _create_sequence(client, pid, "S")
    scene = await _create_scene(client, seq["id"], "C")

    assert (await _put_shots(
        client, scene["id"], [shots[0], shots[1]]
    )).status_code == 200

    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE shots SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :s"),
            {"s": shots[1]},
        )
        await conn.commit()
    frozen = await _fetch(
        engine,
        "SELECT scene_id, scene_position, deleted_at, updated_at FROM shots "
        "WHERE id = :s",
        {"s": shots[1]},
    )
    assert frozen["scene_id"] == scene["id"]

    # Full-set replacement omitting the deleted shot: it is NOT unassigned.
    assert (await _put_shots(client, scene["id"], [shots[0]])).status_code == 200
    assert await _fetch(
        engine,
        "SELECT scene_id, scene_position, deleted_at, updated_at FROM shots "
        "WHERE id = :s",
        {"s": shots[1]},
    ) == frozen

    # Assigning a new active member and reordering actives: still frozen.
    assert (await _put_shots(
        client, scene["id"], [shots[2], shots[0]]
    )).status_code == 200
    assert await _fetch(
        engine,
        "SELECT scene_id, scene_position, deleted_at, updated_at FROM shots "
        "WHERE id = :s",
        {"s": shots[1]},
    ) == frozen

    # Empty-set unassignment clears ACTIVE members only.
    assert (await _put_shots(client, scene["id"], [])).status_code == 200
    assert await _fetch(
        engine,
        "SELECT scene_id, scene_position, deleted_at, updated_at FROM shots "
        "WHERE id = :s",
        {"s": shots[1]},
    ) == frozen


async def test_patch_is_partial_field_presence(client, factory):
    """Blocker 2 matrix: omitted fields preserved; explicit null clears;
    empty body mutates nothing."""
    pid = await _seed_project(factory)
    seq = await _create_sequence(client, pid, "Act I")
    scene = await _create_scene(client, seq["id"], "Lobby")
    r = await client.patch(
        f"/scenes/{scene['id']}", json={"description": "marble floor"}
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Lobby"  # omitted title preserved
    assert r.json()["description"] == "marble floor"

    r = await client.patch(f"/scenes/{scene['id']}", json={"title": "Roof"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Roof"
    assert body["description"] == "marble floor"  # omitted desc preserved

    r = await client.patch(f"/scenes/{scene['id']}", json={"description": None})
    assert r.status_code == 200 and r.json()["description"] is None
    assert r.json()["title"] == "Roof"

    r = await client.patch(f"/scenes/{scene['id']}", json={})
    assert r.status_code == 200
    assert r.json()["title"] == "Roof"  # {} mutates nothing

    # Sequence: empty body + explicit null distinction.
    r = await client.patch(f"/sequences/{seq['id']}", json={})
    assert r.status_code == 200 and r.json()["title"] == "Act I"
    r = await client.patch(f"/sequences/{seq['id']}", json={"title": None})
    assert r.status_code == 200 and r.json()["title"] is None


async def test_list_sequences_deleted_project_is_404(client, factory):
    pid = await _seed_project(factory)
    assert (await client.get(f"/projects/{pid}/sequences")).status_code == 200
    assert (await client.delete(f"/projects/{pid}")).status_code == 204
    r = await client.get(f"/projects/{pid}/sequences")
    assert r.status_code == 404
    assert r.json()["error_code"] == "PROJECT_NOT_FOUND"
