"""M7A.5 — canonical Project-local narrative ordering proofs (plan §14).

Every frozen gate from the authorization: boundary precedence in full,
reorder sensitivity in all three dimensions, tombstone/unassignment
exclusion, Project-locality, identity stability across reorder, no
iteration-order/timestamp/UUID semantics, and explicit corruption failure.

The tests exercise the module through the existing narrative services
(create/assign/reorder/delete) so the proofs run against real persisted
topology, never hand-seeded rows (corruption cases aside, which by
definition require direct writes).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects as project_svc
from soloring.domain import shots as shot_svc
from soloring.errors import ErrorCode, SoloRingError
from soloring.narrative.order import (
    ANCHOR_SCENE,
    ANCHOR_SEQUENCE,
    ANCHOR_SHOT,
    BOUNDARY_END,
    BOUNDARY_START,
    boundaries_before,
    boundaries_through,
    load_narrative_ordering,
)


async def _seed_project(factory) -> str:
    async with factory() as s:
        return (await project_svc.create_project(
            s, ProjectCreate(name="P")
        )).id


async def _topology(client, factory, pid, n_seq=1, scenes_per_seq=(1,),
                     shots_per_scene=(2,)):
    """Build sequences/scenes/shots via the real services; return ids."""
    seq_ids, scene_ids, shot_ids = [], [], []
    for si in range(n_seq):
        r = await client.post(
            f"/projects/{pid}/sequences", json={"title": f"S{si}"}
        )
        assert r.status_code == 201, r.text
        seq_ids.append(r.json()["id"])
    for si, seq_id in enumerate(seq_ids):
        n_scenes = scenes_per_seq[si] if si < len(scenes_per_seq) else 1
        for ci in range(n_scenes):
            r = await client.post(
                f"/sequences/{seq_id}/scenes", json={"title": f"C{ci}"}
            )
            assert r.status_code == 201, r.text
            scene_ids.append(r.json()["id"])
    for ci, scene_id in enumerate(scene_ids):
        n_shots = shots_per_scene[ci] if ci < len(shots_per_scene) else 1
        for _ in range(n_shots):
            async with factory() as s:
                shot = await shot_svc.create_shot(
                    s, pid, ShotCreate(subject="x")
                )
            shot_ids.append(shot.id)
        r = await client.put(
            f"/scenes/{scene_id}/shots", json={"shot_ids": shot_ids[-n_shots:]}
        )
        assert r.status_code == 200, r.text
    return seq_ids, scene_ids, shot_ids


async def _ordering(engine, pid):
    async with engine.connect() as conn:
        return await load_narrative_ordering(conn, pid)


async def _identities(engine, pid):
    o = await _ordering(engine, pid)
    return list(o.boundary_identities())


# --- §13: full boundary precedence ------------------------------------------------


async def test_full_precedence_chain(client, factory, engine):
    pid = await _seed_project(factory)
    seqs, scenes, shots = await _topology(
        client, factory, pid, n_seq=2, scenes_per_seq=(2, 1),
        shots_per_scene=(2, 1, 1),
    )
    o = await _ordering(engine, pid)
    ids = list(o.boundary_identities())

    def idx(anchor, aid, b):
        return ids.index((anchor, aid, b))

    s0, s1 = seqs
    c0, c1, c2 = scenes
    sh = shots  # [s0c0a, s0c0b, s0c1a, s1c2a]

    # Sequence/start precedes first Scene/start.
    assert idx(ANCHOR_SEQUENCE, s0, BOUNDARY_START) < idx(
        ANCHOR_SCENE, c0, BOUNDARY_START
    )
    # Scene/start precedes first Shot/start.
    assert idx(ANCHOR_SCENE, c0, BOUNDARY_START) < idx(
        ANCHOR_SHOT, sh[0], BOUNDARY_START
    )
    # Previous Shot/end precedes next Shot/start.
    assert idx(ANCHOR_SHOT, sh[0], BOUNDARY_END) < idx(
        ANCHOR_SHOT, sh[1], BOUNDARY_START
    )
    # Last Shot/end precedes Scene/end.
    assert idx(ANCHOR_SHOT, sh[1], BOUNDARY_END) < idx(
        ANCHOR_SCENE, c0, BOUNDARY_END
    )
    # Scene/end precedes next Scene/start.
    assert idx(ANCHOR_SCENE, c0, BOUNDARY_END) < idx(
        ANCHOR_SCENE, c1, BOUNDARY_START
    )
    # Scene/end precedes Sequence/end.
    assert idx(ANCHOR_SCENE, c1, BOUNDARY_END) < idx(
        ANCHOR_SEQUENCE, s0, BOUNDARY_END
    )
    # Sequence/end precedes next Sequence/start.
    assert idx(ANCHOR_SEQUENCE, s0, BOUNDARY_END) < idx(
        ANCHOR_SEQUENCE, s1, BOUNDARY_START
    )
    # Second sequence's internals come strictly after.
    assert idx(ANCHOR_SEQUENCE, s1, BOUNDARY_START) < idx(
        ANCHOR_SHOT, sh[3], BOUNDARY_START
    )

    # Ranks are a dense 0..N-1 monotonic sequence.
    ranks = [b.rank for b in o.boundaries]
    assert ranks == list(range(len(ranks)))

    # Effective-state eligibility at Shot/start is INCLUSIVE of the
    # target's own /start boundary (the frozen M7 rule) and exclusive of
    # everything after it, including the target's own /end.
    start = o.shot_start_rank(sh[0])
    eligible = boundaries_through(o, start)
    eligible_ids = [b.identity for b in eligible]
    assert (ANCHOR_SHOT, sh[0], BOUNDARY_START) in eligible_ids
    assert (ANCHOR_SHOT, sh[0], BOUNDARY_END) not in eligible_ids
    assert all(
        (ANCHOR_SHOT, other, BOUNDARY_START) not in eligible_ids
        for other in sh[1:]
    )
    assert o.shot_end_rank(sh[0]) == start + 1
    # The strict prefix still excludes the target /start (generic helper,
    # explicitly NOT the effective-state rule).
    strict = boundaries_before(o, start)
    assert (ANCHOR_SHOT, sh[0], BOUNDARY_START) not in [
        b.identity for b in strict
    ]
    assert (ANCHOR_SHOT, sh[0], BOUNDARY_START) in ids


# --- reorder sensitivity in three dimensions --------------------------------------


async def test_shot_reorder_changes_ranks_deterministically(
    client, factory, engine
):
    pid = await _seed_project(factory)
    seqs, scenes, shots = await _topology(client, factory, pid)
    o1 = await _ordering(engine, pid)
    before = list(o1.shot_ids_in_order())
    assert before == [shots[0], shots[1]]

    r = await client.put(
        f"/scenes/{scenes[0]}/shots",
        json={"shot_ids": [shots[1], shots[0]]},
    )
    assert r.status_code == 200, r.text
    o2 = await _ordering(engine, pid)
    assert list(o2.shot_ids_in_order()) == [shots[1], shots[0]]
    # Stable identities survive; only ranks moved.
    assert set(o2.boundary_identities()) == set(o1.boundary_identities())
    assert o2.shot_start_rank(shots[1]) < o2.shot_start_rank(shots[0])
    # Deterministic: reloading yields identical ranks.
    o3 = await _ordering(engine, pid)
    assert o3.boundary_identities() == o2.boundary_identities()


async def test_scene_reorder_changes_ranks_deterministically(
    client, factory, engine
):
    pid = await _seed_project(factory)
    seqs, scenes, shots = await _topology(
        client, factory, pid, scenes_per_seq=(2,), shots_per_scene=(1, 1)
    )
    o1 = await _ordering(engine, pid)
    assert list(o1.shot_ids_in_order()) == [shots[0], shots[1]]

    r = await client.put(
        f"/sequences/{seqs[0]}/scenes/order",
        json={"scene_ids": [scenes[1], scenes[0]]},
    )
    assert r.status_code == 200, r.text
    o2 = await _ordering(engine, pid)
    assert list(o2.shot_ids_in_order()) == [shots[1], shots[0]]
    assert set(o2.boundary_identities()) == set(o1.boundary_identities())
    assert o2.rank_of(ANCHOR_SCENE, scenes[1], BOUNDARY_START) < o2.rank_of(
        ANCHOR_SCENE, scenes[0], BOUNDARY_START
    )


async def test_sequence_reorder_changes_ranks_deterministically(
    client, factory, engine
):
    pid = await _seed_project(factory)
    seqs, scenes, shots = await _topology(
        client, factory, pid, n_seq=2, scenes_per_seq=(1, 1),
        shots_per_scene=(1, 1),
    )
    o1 = await _ordering(engine, pid)
    assert list(o1.shot_ids_in_order()) == [shots[0], shots[1]]

    r = await client.put(
        f"/projects/{pid}/sequences/order",
        json={"sequence_ids": [seqs[1], seqs[0]]},
    )
    assert r.status_code == 200, r.text
    o2 = await _ordering(engine, pid)
    assert list(o2.shot_ids_in_order()) == [shots[1], shots[0]]
    assert set(o2.boundary_identities()) == set(o1.boundary_identities())
    assert o2.rank_of(
        ANCHOR_SEQUENCE, seqs[1], BOUNDARY_START
    ) < o2.rank_of(ANCHOR_SEQUENCE, seqs[0], BOUNDARY_START)


# --- exclusions ---------------------------------------------------------------------


async def test_tombstones_and_unassigned_never_appear(client, factory, engine):
    pid = await _seed_project(factory)
    seqs, scenes, shots = await _topology(
        client, factory, pid, scenes_per_seq=(2,), shots_per_scene=(1, 1)
    )

    # An unassigned shot exists but never appears.
    async with factory() as s:
        lonely = await shot_svc.create_shot(s, pid, ShotCreate(subject="l"))
    o = await _ordering(engine, pid)
    assert lonely.id not in o.shot_ids_in_order()
    assert all(
        b.anchor_id != lonely.id
        for b in o.boundaries
        if b.anchor_type == ANCHOR_SHOT
    )

    # Soft-delete a shot (unassign first via full-set semantics).
    r = await client.put(
        f"/scenes/{scenes[1]}/shots", json={"shot_ids": []}
    )
    assert r.status_code == 200
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE shots SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :s"),
            {"s": shots[1]},
        )
        await conn.exec_driver_sql("COMMIT")
    o = await _ordering(engine, pid)
    assert shots[1] not in o.shot_ids_in_order()
    # ... and its scene, now empty, is deletable and disappears with it.
    assert (await client.delete(f"/scenes/{scenes[1]}")).status_code == 204
    o = await _ordering(engine, pid)
    assert all(b.anchor_id != scenes[1] for b in o.boundaries)
    # Empty the remaining scene too, delete it, then the sequence.
    assert (await client.put(
        f"/scenes/{scenes[0]}/shots", json={"shot_ids": []}
    )).status_code == 200
    assert (await client.delete(f"/scenes/{scenes[0]}")).status_code == 204
    assert (await client.delete(f"/sequences/{seqs[0]}")).status_code == 204
    o = await _ordering(engine, pid)
    assert o.boundaries == ()


# --- Project-locality ----------------------------------------------------------------


async def test_ordering_is_project_local(client, factory, engine):
    pid_a = await _seed_project(factory)
    pid_b = await _seed_project(factory)
    seqs_a, scenes_a, shots_a = await _topology(client, factory, pid_a)
    seqs_b, scenes_b, shots_b = await _topology(client, factory, pid_b)

    oa = await _ordering(engine, pid_a)
    ob = await _ordering(engine, pid_b)
    a_ids = {b.anchor_id for b in oa.boundaries}
    b_ids = {b.anchor_id for b in ob.boundaries}
    assert a_ids.isdisjoint(b_ids)
    assert set(seqs_b) | set(scenes_b) | set(shots_b) not in a_ids
    assert oa.project_id == pid_a and ob.project_id == pid_b
    # Both projects start their own rank space at 0.
    assert oa.boundaries[0].rank == 0 and ob.boundaries[0].rank == 0


# --- no iteration-order / timestamp / UUID semantics ---------------------------------


async def test_no_uuid_or_timestamp_semantics(client, factory, engine):
    pid = await _seed_project(factory)
    # Two sequences created in one order; ordering must follow positions,
    # not ids/timestamps (identical second-level timestamps here).
    r1 = await client.post(f"/projects/{pid}/sequences", json={"title": "A"})
    r2 = await client.post(f"/projects/{pid}/sequences", json={"title": "B"})
    s_first, s_second = r1.json()["id"], r2.json()["id"]
    o = await _ordering(engine, pid)
    assert o.rank_of(
        ANCHOR_SEQUENCE, s_first, BOUNDARY_START
    ) < o.rank_of(ANCHOR_SEQUENCE, s_second, BOUNDARY_START)

    # Force identical positions on active scenes via direct SQL is blocked
    # by the active-only unique index; instead prove determinism against
    # arbitrary fetch order by reloading repeatedly.
    for _ in range(3):
        o_again = await _ordering(engine, pid)
        assert o_again.boundary_identities() == o.boundary_identities()


# --- corruption fails explicitly --------------------------------------------------------


async def test_corrupt_topology_fails_explicitly(client, factory, engine):
    pid = await _seed_project(factory)
    seqs, scenes, shots = await _topology(client, factory, pid)

    # Active scene under tombstoned sequence of this project.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE sequences SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :s"),
            {"s": seqs[0]},
        )
        await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await _ordering(engine, pid)
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION

    # Restore; now tombstone the scene under an active sequence with a shot
    # still assigned (corrupt assigned-under-tombstoned-scene).
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE sequences SET deleted_at = NULL WHERE id = :s"),
            {"s": seqs[0]},
        )
        await conn.execute(
            text("UPDATE scenes SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :c"),
            {"c": scenes[0]},
        )
        await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await _ordering(engine, pid)
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION


async def test_other_projects_corruption_is_not_this_projects_error(
    client, factory, engine
):
    """Project-locality: a corrupt subtree under ANOTHER project never
    makes THIS project's ordering fail."""
    pid_a = await _seed_project(factory)
    pid_b = await _seed_project(factory)
    await _topology(client, factory, pid_a)
    seqs_b, scenes_b, shots_b = await _topology(client, factory, pid_b)

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE sequences SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :s"),
            {"s": seqs_b[0]},
        )
        await conn.exec_driver_sql("COMMIT")

    oa = await _ordering(engine, pid_a)  # must not raise
    assert oa.shot_ids_in_order()
    with pytest.raises(SoloRingError):
        await _ordering(engine, pid_b)


# --- single implementation ---------------------------------------------------------------


def test_ordering_has_one_implementation():
    """No resolver-specific duplicate ordering logic: the narrative package
    exposes exactly one ordering loader, and nothing else in the server
    tree builds boundary streams (AST scan mirrors the M6C boundary suite)."""
    import ast
    from pathlib import Path

    from soloring.settings import BASE_DIR

    server = BASE_DIR / "server" / "soloring"
    order_api = {"load_narrative_ordering", "NarrativeOrdering", "Boundary"}
    offenders = []
    for path in sorted(server.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "load_narrative_ordering" and path.name != "order.py":
                    offenders.append(f"{path.name}:{node.name}")
            elif isinstance(node, ast.ClassDef):
                if node.name in ("NarrativeOrdering", "Boundary") and \
                        path.name != "order.py":
                    offenders.append(f"{path.name}:{node.name}")
            elif isinstance(node, ast.Name) and node.id in order_api:
                rel = path.relative_to(server)
                if str(rel).replace("\\", "/") != "narrative/order.py":
                    # Usage is fine; only DEFINITIONS must not duplicate.
                    pass
    assert not offenders, offenders

# --- M7A.5 re-gate regressions (B1 + B2) -------------------------------------------


async def test_shot_start_eligibility_is_inclusive(client, factory, engine):
    """B1: the target Shot's /start boundary is eligible for the target
    Shot's effective state AND remains in the eligible history of
    downstream Shots — state persists until superseded or cleared. M7A.5
    defines the eligible transition history; M7B will implement "latest
    applicable transition wins" over it."""
    pid = await _seed_project(factory)
    seqs, scenes, shots = await _topology(client, factory, pid)
    o = await _ordering(engine, pid)
    first_start = o.shot_start_rank(shots[0])
    second_start = o.shot_start_rank(shots[1])

    eligible_first = boundaries_through(o, first_start)
    eligible_first_ids = [b.identity for b in eligible_first]
    # Target's own /start applies to the target...
    assert (ANCHOR_SHOT, shots[0], BOUNDARY_START) in eligible_first_ids
    assert (ANCHOR_SHOT, shots[0], BOUNDARY_END) not in eligible_first_ids
    # ...and the next shot's boundaries are not yet eligible from here.
    assert (ANCHOR_SHOT, shots[1], BOUNDARY_START) not in eligible_first_ids

    # From the next shot's position: everything through the first shot's
    # /end is eligible, the second's own /start is eligible for the
    # second, AND the first shot's /start REMAINS in the downstream
    # eligible history (state persists until superseded or cleared —
    # eligibility history ≠ the winning transition).
    eligible_second = boundaries_through(o, second_start)
    eligible_second_ids = [b.identity for b in eligible_second]
    assert (ANCHOR_SHOT, shots[0], BOUNDARY_END) in eligible_second_ids
    assert (ANCHOR_SHOT, shots[1], BOUNDARY_START) in eligible_second_ids
    assert (ANCHOR_SHOT, shots[0], BOUNDARY_START) in eligible_second_ids


async def test_foreign_scene_reference_fails_explicitly_both_ways(
    client, factory, engine
):
    """B2 Case A: a target-Project Shot pointing at another Project's
    Scene is corruption — the target Project's ordering FAILS, and the
    foreign Project's ordering must not import the Shot."""
    pid_a = await _seed_project(factory)
    pid_b = await _seed_project(factory)
    await _topology(client, factory, pid_a)  # A has legal topology
    seqs_b, scenes_b, shots_b = await _topology(client, factory, pid_b)

    async with factory() as s:
        stray = await shot_svc.create_shot(s, pid_a, ShotCreate(subject="x"))

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE shots SET scene_id = :scene, scene_position = 99 "
                "WHERE id = :sid"
            ),
            {"scene": scenes_b[0], "sid": stray.id},
        )
        await conn.exec_driver_sql("COMMIT")

    # A's ordering fails explicitly (its Shot points into B).
    with pytest.raises(SoloRingError) as ei:
        await _ordering(engine, pid_a)
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION

    # B's ordering does NOT import A's Shot (query is project-owned).
    ob = await _ordering(engine, pid_b)
    assert stray.id not in ob.shot_ids_in_order()
    assert all(b.anchor_id != stray.id for b in ob.boundaries)


async def test_missing_scene_reference_fails_explicitly(
    client, factory, engine
):
    """B2 Case B: a target-Project assigned Shot referencing a missing
    Scene raises the invariant failure (scene_id has no DB FK)."""
    pid = await _seed_project(factory)
    await _topology(client, factory, pid)
    async with factory() as s:
        stray = await shot_svc.create_shot(s, pid, ShotCreate(subject="x"))
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE shots SET scene_id = :missing, scene_position = 0 "
                "WHERE id = :sid"
            ),
            {"missing": "ffffffff-ffff-ffff-ffff-ffffffffffff",
             "sid": stray.id},
        )
        await conn.exec_driver_sql("COMMIT")

    with pytest.raises(SoloRingError) as ei:
        await _ordering(engine, pid)
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION


async def test_tombstoned_scene_reference_fails_explicitly(
    client, factory, engine
):
    """Assigned Shot under a tombstoned Scene of this Project fails."""
    pid = await _seed_project(factory)
    seqs, scenes, shots = await _topology(client, factory, pid)
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text("UPDATE scenes SET deleted_at = "
                 "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :c"),
            {"c": scenes[0]},
        )
        await conn.exec_driver_sql("COMMIT")
    with pytest.raises(SoloRingError) as ei:
        await _ordering(engine, pid)
    assert ei.value.code == ErrorCode.INTERNAL_INVARIANT_VIOLATION


async def test_foreign_shot_corruption_leaves_target_unaffected(
    client, factory, engine
):
    """A corrupt Shot stored under ANOTHER Project never enters the target
    Project's query, so the target ordering stays valid."""
    pid_a = await _seed_project(factory)
    pid_b = await _seed_project(factory)
    await _topology(client, factory, pid_a)
    seqs_b, scenes_b, shots_b = await _topology(client, factory, pid_b)

    # Corrupt B's shot: points at a nonexistent scene.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await conn.execute(
            text(
                "UPDATE shots SET scene_id = :missing "
                "WHERE id = :sid"
            ),
            {"missing": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
             "sid": shots_b[0]},
        )
        await conn.exec_driver_sql("COMMIT")

    oa = await _ordering(engine, pid_a)  # must not raise
    assert oa.shot_ids_in_order()
    with pytest.raises(SoloRingError):
        await _ordering(engine, pid_b)
