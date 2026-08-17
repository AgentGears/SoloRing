"""Project API tests (plan §8, §50.3)."""

from __future__ import annotations

from sqlalchemy import text

from tests.conftest import create_project


async def test_create_read_update_list(client) -> None:
    p = await create_project(client, name="Film", description="desc")
    assert p["name"] == "Film" and p["description"] == "desc"
    assert p["id"]

    got = (await client.get(f"/projects/{p['id']}")).json()
    assert got["name"] == "Film"

    patched = (await client.patch(f"/projects/{p['id']}", json={"name": "Renamed"})).json()
    assert patched["name"] == "Renamed"
    assert patched["description"] == "desc"

    listed = (await client.get("/projects")).json()
    assert any(x["id"] == p["id"] for x in listed)


async def test_name_trimmed(client) -> None:
    p = await create_project(client, name="   Spaced   ")
    assert p["name"] == "Spaced"


async def test_blank_name_rejected(client) -> None:
    r = await client.post("/projects", json={"name": "    "})
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"


async def test_overlong_name_rejected(client) -> None:
    r = await client.post("/projects", json={"name": "x" * 501})
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"


async def test_description_blank_becomes_null(client) -> None:
    p = await create_project(client, name="P", description="   ")
    assert p["description"] is None
    p2 = await create_project(client, name="P2")
    assert p2["description"] is None


async def test_delete_cascades_to_active_shots_only(client, engine) -> None:
    from tests.conftest import create_shot

    p = await create_project(client, name="P")
    s1 = await create_shot(client, p["id"], subject="one")
    s2 = await create_shot(client, p["id"], subject="two")

    # Soft-delete s1 first.
    assert (await client.delete(f"/shots/{s1['id']}")).status_code == 204
    s1_deleted_at = await _deleted_at(engine, s1["id"])
    assert s1_deleted_at is not None

    # Deleting the project must cascade to active s2 but leave s1 untouched.
    assert (await client.delete(f"/projects/{p['id']}")).status_code == 204
    assert await _deleted_at(engine, s2["id"]) is not None
    assert await _deleted_at(engine, s1["id"]) == s1_deleted_at  # unchanged


async def test_repeat_delete_is_idempotent(client) -> None:
    p = await create_project(client, name="P")
    assert (await client.delete(f"/projects/{p['id']}")).status_code == 204
    assert (await client.delete(f"/projects/{p['id']}")).status_code == 204


async def test_delete_missing_project_is_404(client) -> None:
    r = await client.delete("/projects/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.json()["error_code"] == "PROJECT_NOT_FOUND"


async def test_delete_malformed_project_is_404(client) -> None:
    r = await client.delete("/projects/not-a-uuid")
    assert r.status_code == 404
    assert r.json()["error_code"] == "PROJECT_NOT_FOUND"


async def test_mutations_against_deleted_project_fail(client) -> None:
    p = await create_project(client, name="P")
    await client.delete(f"/projects/{p['id']}")
    assert (await client.get(f"/projects/{p['id']}")).status_code == 404
    r = await client.post(f"/projects/{p['id']}/shots", json={"subject": "x"})
    assert r.status_code == 404 and r.json()["error_code"] == "PROJECT_NOT_FOUND"
    assert (await client.patch(f"/projects/{p['id']}", json={"name": "Z"})).status_code == 404


async def _deleted_at(engine, shot_id) -> str | None:
    async with engine.connect() as conn:
        return (
            await conn.execute(text("SELECT deleted_at FROM shots WHERE id=:i"), {"i": shot_id})
        ).scalar()
