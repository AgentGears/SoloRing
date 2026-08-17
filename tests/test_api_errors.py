"""API error envelope + validation normalization (plan §42, §43, §44, §50.15)."""

from __future__ import annotations

from tests.conftest import create_project


def _envelope(body: dict) -> None:
    assert set(body.keys()) == {"error_code", "message", "details"}


async def test_domain_error_uses_envelope(client) -> None:
    r = await client.get("/projects/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    body = r.json()
    _envelope(body)
    assert body["error_code"] == "PROJECT_NOT_FOUND"


async def test_malformed_entity_uuid_is_entity_404(client) -> None:
    assert (await client.get("/projects/not-a-uuid")).status_code == 404
    rp = (await client.get("/projects/not-a-uuid")).json()
    assert rp["error_code"] == "PROJECT_NOT_FOUND"
    rs = (await client.get("/shots/not-a-uuid")).json()
    assert rs["error_code"] == "SHOT_NOT_FOUND"


async def test_invalid_pydantic_field_uses_envelope(client) -> None:
    # subject must be a string; a number is invalid.
    r = await client.post("/projects", json={"name": 123})
    assert r.status_code == 422
    body = r.json()
    _envelope(body)
    assert body["error_code"] == "VALIDATION_ERROR"
    assert body["details"]["errors"]


async def test_malformed_json_uses_envelope(client) -> None:
    r = await client.post(
        "/projects",
        content='{"name": ',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422
    body = r.json()
    _envelope(body)
    assert body["error_code"] == "VALIDATION_ERROR"


async def test_unknown_field_rejected(client) -> None:
    # extra="forbid" on the request schema (plan §9.2 boundary).
    r = await client.post("/projects", json={"name": "P", "surprise": 1})
    assert r.status_code == 422 and r.json()["error_code"] == "VALIDATION_ERROR"


async def test_responses_never_expose_internal_paths(client) -> None:
    p = await create_project(client, name="P")
    bodies = [
        (await client.get("/projects")).json(),
        (await client.get(f"/projects/{p['id']}")).json(),
    ]
    for b in bodies:
        for item in (b if isinstance(b, list) else [b]):
            assert "path" not in item
            assert "data/" not in repr(item)
