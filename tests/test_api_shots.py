"""Shot API tests (plan §9, §15, §50.4)."""

from __future__ import annotations

import asyncio

from tests.conftest import create_project, create_shot


async def test_subject_trimmed(client) -> None:
    s = await create_shot(client, (await create_project(client, name="P"))["id"], subject="  Eva  ")
    assert s["subject"] == "Eva"


async def test_blank_subject_rejected(client) -> None:
    pid = (await create_project(client, name="P"))["id"]
    for bad in ("", "   "):
        r = await client.post(f"/projects/{pid}/shots", json={"subject": bad})
        assert r.status_code == 422
        assert r.json()["error_code"] == "VALIDATION_ERROR"


async def test_optional_empty_creative_strings_become_null(client) -> None:
    pid = (await create_project(client, name="P"))["id"]
    s = await create_shot(
        client, pid, subject="x", title="", action="   ",
        environment="", framing="", camera_motion="", lens="", mood="",
    )
    for f in ("title", "action", "environment", "framing", "camera_motion", "lens", "mood"):
        assert s[f] is None, f
    assert s["duration_ms"] is None


async def test_approved_take_id_not_patchable(client) -> None:
    s = await create_shot(client, (await create_project(client, name="P"))["id"], subject="x")
    r = await client.patch(f"/shots/{s['id']}", json={"approved_take_id": s["id"]})
    assert r.status_code == 422 and r.json()["error_code"] == "VALIDATION_ERROR"


async def test_patch_updates_working_hash_and_updated_at(client) -> None:
    s = await create_shot(client, (await create_project(client, name="P"))["id"], subject="a")
    before_hash = s["working_snapshot_hash"]
    before_updated = s["updated_at"]

    patched = (await client.patch(f"/shots/{s['id']}", json={"subject": "b"})).json()
    assert patched["working_snapshot_hash"] != before_hash
    assert patched["updated_at"] >= before_updated


async def test_repeat_delete_is_idempotent(client) -> None:
    s = await create_shot(client, (await create_project(client, name="P"))["id"], subject="x")
    assert (await client.delete(f"/shots/{s['id']}")).status_code == 204
    assert (await client.delete(f"/shots/{s['id']}")).status_code == 204
    assert (await client.get(f"/shots/{s['id']}")).status_code == 404


async def test_delete_missing_shot_is_404(client) -> None:
    r = await client.delete("/shots/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.json()["error_code"] == "SHOT_NOT_FOUND"


async def test_delete_malformed_shot_is_404(client) -> None:
    r = await client.delete("/shots/not-a-uuid")
    assert r.status_code == 404
    assert r.json()["error_code"] == "SHOT_NOT_FOUND"


async def test_first_shot_number_is_one(client) -> None:
    s = await create_shot(client, (await create_project(client, name="P"))["id"], subject="x")
    assert s["shot_number"] == 1


async def test_deleted_number_not_reused(client) -> None:
    pid = (await create_project(client, name="P"))["id"]
    s1 = await create_shot(client, pid, subject="one")
    assert s1["shot_number"] == 1
    await client.delete(f"/shots/{s1['id']}")
    s2 = await create_shot(client, pid, subject="two")
    assert s2["shot_number"] == 2


async def test_concurrent_creation_unique_sequence(client) -> None:
    pid = (await create_project(client, name="P"))["id"]
    n = 8
    results = await asyncio.gather(
        *(client.post(f"/projects/{pid}/shots", json={"subject": f"s{i}"}) for i in range(n))
    )
    nums = sorted(r.json()["shot_number"] for r in results if r.status_code == 201)
    assert nums == list(range(1, n + 1))


async def test_create_shot_in_deleted_project_rejected(client) -> None:
    """Project-deletion race boundary (plan §10, §50.4)."""
    p = await create_project(client, name="P")
    await client.delete(f"/projects/{p['id']}")
    r = await client.post(f"/projects/{p['id']}/shots", json={"subject": "x"})
    assert r.status_code == 404 and r.json()["error_code"] == "PROJECT_NOT_FOUND"


async def test_working_snapshot_hash_changes_on_reference_relevant_edit(client) -> None:
    # In M1B references are empty; subject change must still change the hash.
    s = await create_shot(client, (await create_project(client, name="P"))["id"], subject="a")
    h1 = s["working_snapshot_hash"]
    s2 = (await client.patch(f"/shots/{s['id']}", json={"lens": "50mm"})).json()
    assert s2["working_snapshot_hash"] != h1


async def test_list_shots_lightweight_no_working_hash(client) -> None:
    pid = (await create_project(client, name="P"))["id"]
    await create_shot(client, pid, subject="x")
    items = (await client.get(f"/projects/{pid}/shots")).json()
    assert items and "working_snapshot_hash" not in items[0]
