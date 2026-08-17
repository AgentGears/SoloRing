"""Project Asset listing tests (M2 plan §3.3, §6.3)."""

from __future__ import annotations

from uuid import uuid4

from tests.conftest import create_project

PNG = b"\x89PNG\r\n\x1a\n" + b"asset-listing" * 5
OTHER = b"arbitrary-bytes-no-known-signature"


async def _upload(client, pid: str, data: bytes, name="f.png"):
    r = await client.post(
        f"/projects/{pid}/assets", files={"file": (name, data, "image/png")}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _keys(body: dict) -> set[str]:
    return set(body.keys())


async def test_list_default_returns_reference_assets(client) -> None:
    p = await create_project(client, name="P")
    a = await _upload(client, p["id"], PNG)
    items = (await client.get(f"/projects/{p['id']}/assets")).json()
    assert [x["id"] for x in items] == [a["id"]]
    assert items[0]["kind"] == "reference"


async def test_explicit_kind_filters(client) -> None:
    p = await create_project(client, name="P")
    a = await _upload(client, p["id"], PNG)
    ref = (await client.get(f"/projects/{p['id']}/assets?kind=reference")).json()
    out = (await client.get(f"/projects/{p['id']}/assets?kind=output")).json()
    assert [x["id"] for x in ref] == [a["id"]]
    assert out == []  # M2 produces no output assets


async def test_invalid_kind_422_envelope(client) -> None:
    p = await create_project(client, name="P")
    r = await client.get(f"/projects/{p['id']}/assets?kind=bogus")
    assert r.status_code == 422
    body = r.json()
    assert body["error_code"] == "VALIDATION_ERROR"
    assert set(body.keys()) == {"error_code", "message", "details"}


async def test_deterministic_created_ordering(client) -> None:
    p = await create_project(client, name="P")
    a1 = await _upload(client, p["id"], PNG + b"1", name="one.png")
    a2 = await _upload(client, p["id"], PNG + b"2", name="two.png")
    a3 = await _upload(client, p["id"], PNG + b"3", name="three.png")
    items = (await client.get(f"/projects/{p['id']}/assets")).json()
    # Contract: ORDER BY (created_at, id). Same-millisecond uploads tie on
    # created_at and fall back to id, so exact insertion order is NOT
    # guaranteed — assert set equality + non-decreasing timestamps instead.
    assert {x["id"] for x in items} == {a1["id"], a2["id"], a3["id"]}
    created = [x["created_at"] for x in items]
    assert created == sorted(created)


async def test_ordering_tiebreak_on_id(client, engine, factory) -> None:
    """ORDER BY (created_at, id): with identical created_at values and rows
    inserted in REVERSE id order, the list must return ascending id order."""
    import hashlib

    from soloring.db.models import Asset, Blob, Project

    p = await create_project(client, name="P")
    same_ts = "2026-01-01T00:00:00.000Z"
    ids = sorted(str(uuid4()) for _ in range(3))
    async with factory() as s:
        for aid in reversed(ids):  # reverse insertion order
            bh = hashlib.sha256(aid.encode()).hexdigest()
            s.add(Blob(hash=bh, path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                       size_bytes=1, created_at=same_ts))
            await s.flush()
            s.add(Asset(id=aid, project_id=p["id"], blob_hash=bh,
                        kind="reference", created_at=same_ts))
        await s.commit()
    items = (await client.get(f"/projects/{p['id']}/assets")).json()
    assert [x["id"] for x in items] == ids  # ascending id tiebreak


async def test_project_scoping(client) -> None:
    pa = await create_project(client, name="A")
    pb = await create_project(client, name="B")
    a_asset = await _upload(client, pa["id"], PNG)
    b_items = (await client.get(f"/projects/{pb['id']}/assets")).json()
    assert b_items == []
    a_items = (await client.get(f"/projects/{pa['id']}/assets")).json()
    assert a_asset["id"] not in {x["id"] for x in b_items}
    assert [x["id"] for x in a_items] == [a_asset["id"]]


async def test_deleted_or_missing_project_404(client) -> None:
    p = await create_project(client, name="P")
    await client.delete(f"/projects/{p['id']}")
    r1 = await client.get(f"/projects/{p['id']}/assets")
    assert r1.status_code == 404 and r1.json()["error_code"] == "PROJECT_NOT_FOUND"
    r2 = await client.get("/projects/not-a-uuid/assets")
    assert r2.status_code == 404 and r2.json()["error_code"] == "PROJECT_NOT_FOUND"


async def test_blob_url_canonical_and_detected_from_blob(client) -> None:
    p = await create_project(client, name="P")
    png = await _upload(client, p["id"], PNG)
    other = await _upload(client, p["id"], OTHER, name="raw.bin")

    h = png["blob_hash"]
    assert png["blob_url"] == f"/blobs/{h[:2]}/{h[2:4]}/{h}"
    assert not png["blob_url"].startswith("/api")
    assert "localhost" not in png["blob_url"] and "127.0.0.1" not in png["blob_url"]

    # detected from magic bytes, NOT from the declared image/png MIME
    assert png["detected_media_type"] == "image/png"
    assert other["detected_media_type"] is None


async def test_upload_detail_list_share_one_shape(client) -> None:
    p = await create_project(client, name="P")
    up = await _upload(client, p["id"], PNG)
    detail = (await client.get(f"/assets/{up['id']}")).json()
    items = (await client.get(f"/projects/{p['id']}/assets")).json()
    assert _keys(up) == _keys(detail) == _keys(items[0])


async def test_repeated_filenames_distinct(client) -> None:
    p = await create_project(client, name="P")
    a1 = await _upload(client, p["id"], PNG + b"x", name="same.png")
    a2 = await _upload(client, p["id"], PNG + b"y", name="same.png")
    assert a1["id"] != a2["id"]
    items = (await client.get(f"/projects/{p['id']}/assets")).json()
    assert len(items) == 2
    assert len({x["id"] for x in items}) == 2
    assert items[0]["original_filename"] == items[1]["original_filename"]
