"""Upload pipeline tests (plan §22, §24, §25, §26, §50.8)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from sqlalchemy import text

from tests.conftest import create_project

PNG = b"\x89PNG\r\n\x1a\n" + b"payload" * 20
JPEG = b"\xff\xd8\xff" + b"junkjunk" * 20
OTHER = b"just some arbitrary bytes"


async def _upload(client, pid, data, filename="f.png", ctype="image/png"):
    return await client.post(
        f"/projects/{pid}/assets", files={"file": (filename, data, ctype)}
    )


async def _counts(engine) -> tuple[int, int]:
    async with engine.connect() as c:
        b = (await c.execute(text("SELECT count(*) FROM blobs"))).scalar()
        a = (await c.execute(text("SELECT count(*) FROM assets"))).scalar()
    return b, a


def _tmp_leftovers(settings) -> list[Path]:
    return list(Path(settings.tmp_dir).glob("*.tmp"))


async def test_upload_creates_asset_and_blob(client, engine, settings) -> None:
    p = await create_project(client, name="P")
    r = await _upload(client, p["id"], PNG)
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "reference"
    assert body["blob_hash"] == hashlib.sha256(PNG).hexdigest()
    assert body["original_filename"] == "f.png"
    assert body["upload_mime_type"] == "image/png"
    assert body["blob_url"] == f"/blobs/{body['blob_hash'][:2]}/{body['blob_hash'][2:4]}/{body['blob_hash']}"
    # physical file at the SHA-derived path
    phys = Path(settings.blob_dir) / "sha256" / body["blob_hash"][:2] / body["blob_hash"][2:4] / body["blob_hash"]
    assert phys.exists()
    assert phys.read_bytes() == PNG
    assert await _counts(engine) == (1, 1)
    assert _tmp_leftovers(settings) == []


async def test_detected_media_type_from_magic_bytes(client) -> None:
    p = await create_project(client, name="P")
    h_png = (await _upload(client, p["id"], PNG)).json()["blob_url"]
    h_jpg = (await _upload(client, p["id"], JPEG, filename="j.jpg")).json()["blob_url"]
    h_other = (await _upload(client, p["id"], OTHER, filename="x.bin")).json()["blob_url"]
    assert (await client.get(h_png)).headers["content-type"].startswith("image/png")
    assert (await client.get(h_jpg)).headers["content-type"].startswith("image/jpeg")
    assert (await client.get(h_other)).headers["content-type"] == "application/octet-stream"


async def test_empty_upload_rejected(client, engine, settings) -> None:
    p = await create_project(client, name="P")
    r = await _upload(client, p["id"], b"")
    assert r.status_code == 400
    assert r.json()["error_code"] == "EMPTY_UPLOAD"
    assert await _counts(engine) == (0, 0)
    assert _tmp_leftovers(settings) == []


async def test_oversized_upload_rejected(client, engine, settings) -> None:
    settings.max_upload_bytes = 16
    p = await create_project(client, name="P")
    r = await _upload(client, p["id"], b"x" * 100)
    assert r.status_code == 413
    assert r.json()["error_code"] == "UPLOAD_TOO_LARGE"
    assert await _counts(engine) == (0, 0)
    assert _tmp_leftovers(settings) == []


async def test_multi_chunk_streaming(client, engine, settings) -> None:
    settings.upload_chunk_bytes = 4096
    data = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 64  # > 2 chunks
    p = await create_project(client, name="P")
    r = await _upload(client, p["id"], data)
    assert r.status_code == 201
    assert r.json()["blob_hash"] == hashlib.sha256(data).hexdigest()


async def test_sequential_duplicate_one_blob_two_assets(client, engine) -> None:
    p = await create_project(client, name="P")
    r1 = await _upload(client, p["id"], PNG)
    r2 = await _upload(client, p["id"], PNG, filename="again.png")
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["blob_hash"] == r2.json()["blob_hash"]
    assert r1.json()["id"] != r2.json()["id"]
    assert await _counts(engine) == (1, 2)


async def test_concurrent_duplicate_one_blob_two_assets(client, engine) -> None:
    p = await create_project(client, name="P")
    r1, r2 = await asyncio.gather(
        _upload(client, p["id"], PNG),
        _upload(client, p["id"], PNG, filename="twin.png"),
    )
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["blob_hash"] == r2.json()["blob_hash"]
    assert r1.json()["id"] != r2.json()["id"]
    assert await _counts(engine) == (1, 2)  # one Blob, two provenance Assets


async def test_filename_basename_and_bounded(client) -> None:
    p = await create_project(client, name="P")
    r = await _upload(client, p["id"], PNG, filename="C:\\dir\\sub\\photo.png")
    assert r.json()["original_filename"] == "photo.png"
    long_name = "a" * 600 + ".png"
    r2 = await _upload(client, p["id"], PNG, filename=long_name)
    assert len(r2.json()["original_filename"]) == 512


async def test_upload_to_deleted_project_rejected(client) -> None:
    p = await create_project(client, name="P")
    await client.delete(f"/projects/{p['id']}")
    r = await _upload(client, p["id"], PNG)
    assert r.status_code == 404
    assert r.json()["error_code"] == "PROJECT_NOT_FOUND"


async def test_concurrent_convergence_is_not_reported_as_repair(
    client, engine, monkeypatch, caplog
) -> None:
    """Ordinary concurrent duplicate convergence must NOT log BLOB REPAIR.

    Deterministic interleaving (plan §26 race + audit): a competing upload
    registers the Blob row AFTER this upload's pre-placement row check but
    BEFORE its placement completes. Nothing was ever corrupt: the row was
    absent when the file was observed missing. The buggy `placed && existed`
    detector logged this as repair; the row-visibility discriminator must not.
    """
    p = await create_project(client, name="P")
    data = PNG
    bh = hashlib.sha256(data).hexdigest()
    rel = f"sha256/{bh[:2]}/{bh[2:4]}/{bh}"

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from soloring.assets.blob_store import BlobStore
    from soloring.assets.service import insert_blob_if_absent

    real_place = BlobStore.place

    async def racing_place(self, blob_hash: str, temp_path: Path) -> bool:
        # "Upload A" commits its Blob row now (after B's row check, before
        # B's file check), without the physical file being present yet from
        # B's point of view.
        f = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
        async with f() as s:
            await insert_blob_if_absent(s, blob_hash, rel, len(data), "image/png")
            await s.commit()
        return await real_place(self, blob_hash, temp_path)

    monkeypatch.setattr(BlobStore, "place", racing_place)

    with caplog.at_level(logging.ERROR):
        r = await client.post(
            f"/projects/{p['id']}/assets",
            files={"file": ("f.png", data, "image/png")},
        )
    assert r.status_code == 201
    assert r.json()["blob_hash"] == bh
    # placed=True and insert-conflict occurred, but this was convergence.
    assert "BLOB REPAIR" not in caplog.text


async def test_get_asset_endpoint(client) -> None:
    p = await create_project(client, name="P")
    up = (await _upload(client, p["id"], PNG)).json()
    got = (await client.get(f"/assets/{up['id']}")).json()
    assert got["id"] == up["id"]
    assert got["blob_hash"] == up["blob_hash"]
    assert "path" not in got  # never expose storage paths
