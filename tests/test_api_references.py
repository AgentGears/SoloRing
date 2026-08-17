"""Reference API tests (plan §11, §50.5)."""

from __future__ import annotations

from tests.conftest import create_project, create_shot, seed_reference_asset


async def _shot_with_project(client, engine):
    p = await create_project(client, name="P")
    s = await create_shot(client, p["id"], subject="subj")
    return p, s


async def _put(client, shot_id, refs):
    return await client.put(f"/shots/{shot_id}/references", json={"references": refs})


async def test_roles_are_exact_and_case_sensitive(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    a1, _ = await seed_reference_asset(engine, s["project_id"])
    r = await _put(client, s["id"], [{"asset_id": a1, "role": "Character"}])
    assert r.status_code == 200
    assert r.json()[0]["role"] == "Character"


async def test_whitespace_only_role_rejected(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    a1, _ = await seed_reference_asset(engine, s["project_id"])
    r = await _put(client, s["id"], [{"asset_id": a1, "role": "   "}])
    assert r.status_code == 400
    assert r.json()["error_code"] == "REFERENCE_SET_INVALID"


async def test_overlong_role_rejected(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    a1, _ = await seed_reference_asset(engine, s["project_id"])
    r = await _put(client, s["id"], [{"asset_id": a1, "role": "x" * 65}])
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"


async def test_server_assigns_contiguous_positions_per_role(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    pid = s["project_id"]
    a1, a2, a3 = (
        (await seed_reference_asset(engine, pid))[0],
        (await seed_reference_asset(engine, pid))[0],
        (await seed_reference_asset(engine, pid))[0],
    )
    r = await _put(
        client,
        s["id"],
        [
            {"asset_id": a1, "role": "reference"},
            {"asset_id": a2, "role": "reference"},
            {"asset_id": a3, "role": "character"},
        ],
    )
    assert r.status_code == 200
    by_key = {(x["role"], x["asset_id"]): x["position"] for x in r.json()}
    assert by_key[("reference", a1)] == 0
    assert by_key[("reference", a2)] == 1
    assert by_key[("character", a3)] == 0


async def test_duplicate_asset_role_rejected(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    a1, _ = await seed_reference_asset(engine, s["project_id"])
    r = await _put(
        client,
        s["id"],
        [
            {"asset_id": a1, "role": "reference"},
            {"asset_id": a1, "role": "reference"},
        ],
    )
    assert r.status_code == 400 and r.json()["error_code"] == "REFERENCE_SET_INVALID"


async def test_same_asset_under_different_roles_allowed(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    a1, _ = await seed_reference_asset(engine, s["project_id"])
    r = await _put(
        client,
        s["id"],
        [
            {"asset_id": a1, "role": "reference"},
            {"asset_id": a1, "role": "character"},
        ],
    )
    assert r.status_code == 200
    assert {x["role"] for x in r.json()} == {"reference", "character"}


async def test_cross_project_asset_rejected(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    other = await create_project(client, name="Other")
    a_other, _ = await seed_reference_asset(engine, other["id"])
    r = await _put(client, s["id"], [{"asset_id": a_other, "role": "reference"}])
    assert r.status_code == 400 and r.json()["error_code"] == "REFERENCE_SET_INVALID"


async def test_unknown_asset_rejected(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    r = await _put(
        client,
        s["id"],
        [{"asset_id": "00000000-0000-0000-0000-000000000000", "role": "reference"}],
    )
    assert r.status_code == 400 and r.json()["error_code"] == "REFERENCE_SET_INVALID"


async def test_invalid_replacement_rolls_back_entirely(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    a1, _ = await seed_reference_asset(engine, s["project_id"])
    # Establish a valid set.
    await _put(client, s["id"], [{"asset_id": a1, "role": "reference"}])
    before = (await client.get(f"/shots/{s['id']}")).json()["working_snapshot_hash"]
    # A set with one bad (cross-project) reference must not partially apply.
    other = await create_project(client, name="Other")
    a_other, _ = await seed_reference_asset(engine, other["id"])
    r = await _put(
        client,
        s["id"],
        [
            {"asset_id": a1, "role": "reference"},
            {"asset_id": a_other, "role": "reference"},
        ],
    )
    assert r.status_code == 400
    after = (await client.get(f"/shots/{s['id']}")).json()["working_snapshot_hash"]
    assert after == before  # unchanged -> rolled back


async def test_identical_put_returns_normalized_set(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    a1, _ = await seed_reference_asset(engine, s["project_id"])
    body = [{"asset_id": a1, "role": "reference"}]
    r1 = await _put(client, s["id"], body)
    r2 = await _put(client, s["id"], body)
    assert r1.status_code == 200 and r2.status_code == 200
    # created_at changes on delete+reinsert, but the semantic set is stable.
    triple = lambda x: (x["asset_id"], x["role"], x["position"])  # noqa: E731
    assert {triple(x) for x in r1.json()} == {triple(x) for x in r2.json()}


async def test_replacement_updates_shot_updated_at(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    a1, _ = await seed_reference_asset(engine, s["project_id"])
    before = s["updated_at"]
    await _put(client, s["id"], [{"asset_id": a1, "role": "reference"}])
    after = (await client.get(f"/shots/{s['id']}")).json()["updated_at"]
    assert after >= before


async def test_client_cannot_supply_position(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    a1, _ = await seed_reference_asset(engine, s["project_id"])
    r = await client.put(
        f"/shots/{s['id']}/references",
        json={"references": [{"asset_id": a1, "role": "reference", "position": 5}]},
    )
    assert r.status_code == 422 and r.json()["error_code"] == "VALIDATION_ERROR"


async def test_references_affect_working_snapshot_hash(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    a1, _ = await seed_reference_asset(engine, s["project_id"])
    before = (await client.get(f"/shots/{s['id']}")).json()["working_snapshot_hash"]
    await _put(client, s["id"], [{"asset_id": a1, "role": "reference"}])
    after = (await client.get(f"/shots/{s['id']}")).json()["working_snapshot_hash"]
    assert before != after


async def test_references_on_missing_shot_rejected(client) -> None:
    r = await _put(client, "00000000-0000-0000-0000-000000000000", [])
    assert r.status_code == 404 and r.json()["error_code"] == "SHOT_NOT_FOUND"


# --- M2C: GET endpoint + failed-PUT atomicity -------------------------------


async def test_get_references_returns_canonical_server_order(client, engine) -> None:
    _, s = await _shot_with_project(client, engine)
    pid = s["project_id"]
    a1, _ = await seed_reference_asset(engine, pid)
    a2, _ = await seed_reference_asset(engine, pid)
    a3, _ = await seed_reference_asset(engine, pid)
    await _put(
        client,
        s["id"],
        [
            {"asset_id": a3, "role": "reference"},
            {"asset_id": a1, "role": "reference"},
            {"asset_id": a2, "role": "character"},
        ],
    )
    r = await client.get(f"/shots/{s['id']}/references")
    assert r.status_code == 200
    got = [(x["asset_id"], x["role"], x["position"]) for x in r.json()]
    assert got == [
        (a2, "character", 0),
        (a3, "reference", 0),  # request order under "reference": a3 then a1
        (a1, "reference", 1),
    ]


async def test_get_references_missing_shot_404(client) -> None:
    r = await client.get("/shots/not-a-uuid/references")
    assert r.status_code == 404 and r.json()["error_code"] == "SHOT_NOT_FOUND"


async def test_failed_put_leaves_references_and_hash_unchanged(client, engine) -> None:
    """M2C acceptance: after a rejected full-set PUT, GET proves BOTH the
    reference set and the working hash are untouched (M1 atomicity coupled to
    visible creative identity)."""
    _, s = await _shot_with_project(client, engine)
    pid = s["project_id"]
    a1, _ = await seed_reference_asset(engine, pid)
    await _put(client, s["id"], [{"asset_id": a1, "role": "reference"}])

    refs_before = (await client.get(f"/shots/{s['id']}/references")).json()
    hash_before = (await client.get(f"/shots/{s['id']}")).json()[
        "working_snapshot_hash"
    ]

    other = await create_project(client, name="Other")
    a_other, _ = await seed_reference_asset(engine, other["id"])
    bad = await _put(
        client,
        s["id"],
        [
            {"asset_id": a1, "role": "reference"},
            {"asset_id": a_other, "role": "reference"},  # cross-project -> reject
        ],
    )
    assert bad.status_code == 400 and bad.json()["error_code"] == "REFERENCE_SET_INVALID"

    refs_after = (await client.get(f"/shots/{s['id']}/references")).json()
    hash_after = (await client.get(f"/shots/{s['id']}")).json()[
        "working_snapshot_hash"
    ]
    assert refs_after == refs_before
    assert hash_after == hash_before


async def test_role_change_renormalizes_both_role_groups(client, engine) -> None:
    """After a role change via full-set PUT, server positions are contiguous
    in BOTH the source and destination role groups."""
    _, s = await _shot_with_project(client, engine)
    pid = s["project_id"]
    a1, a2, a3 = (
        (await seed_reference_asset(engine, pid))[0],
        (await seed_reference_asset(engine, pid))[0],
        (await seed_reference_asset(engine, pid))[0],
    )
    await _put(
        client,
        s["id"],
        [
            {"asset_id": a1, "role": "reference"},
            {"asset_id": a2, "role": "reference"},
            {"asset_id": a3, "role": "character"},
        ],
    )
    # Move a2 from "reference" (position 1) to "character".
    r = await _put(
        client,
        s["id"],
        [
            {"asset_id": a1, "role": "reference"},
            {"asset_id": a3, "role": "character"},
            {"asset_id": a2, "role": "character"},
        ],
    )
    assert r.status_code == 200
    got = {(x["asset_id"], x["role"]): x["position"] for x in r.json()}
    assert got[(a1, "reference")] == 0  # source group re-normalized
    assert got[(a3, "character")] == 0  # destination group re-normalized
    assert got[(a2, "character")] == 1
