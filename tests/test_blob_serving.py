"""Blob serving + integrity tests (plan §27, §28, §29, §30, §50.9, §50.10)."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from sqlalchemy import text

from tests.conftest import create_project

PNG = b"\x89PNG\r\n\x1a\n" + b"0123456789abcdef" * 10  # 168 bytes
SIZE = len(PNG)


async def _upload(client, pid: str, data: bytes = PNG) -> str:
    r = await client.post(f"/projects/{pid}/assets", files={"file": ("f.png", data, "image/png")})
    assert r.status_code == 201, r.text
    return r.json()["blob_url"]


async def _project(client) -> str:
    return (await create_project(client, name="P"))["id"]


def _phys(settings, blob_hash: str) -> Path:
    return Path(settings.blob_dir) / "sha256" / blob_hash[:2] / blob_hash[2:4] / blob_hash


# --- basic serving ----------------------------------------------------------


async def test_full_get_headers_and_bytes(client) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    r = await client.get(url)
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["etag"] == f'"{hashlib.sha256(PNG).hexdigest()}"'
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers["accept-ranges"] == "bytes"
    assert int(r.headers["content-length"]) == SIZE


async def test_range_bounded(client) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    r = await client.get(url, headers={"Range": "bytes=4-15"})
    assert r.status_code == 206
    assert r.content == PNG[4:16]
    assert r.headers["content-range"] == f"bytes 4-15/{SIZE}"
    assert int(r.headers["content-length"]) == 12
    assert r.headers["accept-ranges"] == "bytes"


async def test_range_open_ended(client) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    r = await client.get(url, headers={"Range": "bytes=100-"})
    assert r.status_code == 206
    assert r.content == PNG[100:]
    assert r.headers["content-range"] == f"bytes 100-{SIZE-1}/{SIZE}"


async def test_range_suffix(client) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    r = await client.get(url, headers={"Range": "bytes=-10"})
    assert r.status_code == 206
    assert r.content == PNG[-10:]
    assert r.headers["content-range"] == f"bytes {SIZE-10}-{SIZE-1}/{SIZE}"


async def test_range_suffix_larger_than_file_is_whole_file(client) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    r = await client.get(url, headers={"Range": "bytes=-99999"})
    assert r.status_code == 206
    assert r.content == PNG
    assert r.headers["content-range"] == f"bytes 0-{SIZE-1}/{SIZE}"


async def test_range_clamps_end_to_eof(client) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    r = await client.get(url, headers={"Range": "bytes=0-999999"})
    assert r.status_code == 206
    assert r.content == PNG
    assert r.headers["content-range"] == f"bytes 0-{SIZE-1}/{SIZE}"


async def test_malformed_ranges_416(client) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    for bad in ("bytes=5-2", "bytes=abc", "bytes=", "bytes=-", "units=0-5", "bytes=0-1,5-9"):
        r = await client.get(url, headers={"Range": bad})
        assert r.status_code == 416, bad
        assert r.headers["content-range"] == f"bytes */{SIZE}"


async def test_range_start_past_eof_416(client) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    r = await client.get(url, headers={"Range": f"bytes={SIZE}-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{SIZE}"


async def test_head_returns_headers_without_body(client) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    r = await client.head(url)
    assert r.status_code == 200
    assert r.content == b""
    assert int(r.headers["content-length"]) == SIZE
    assert r.headers["accept-ranges"] == "bytes"
    rh = await client.head(url, headers={"Range": "bytes=4-15"})
    assert rh.status_code == 206
    assert rh.headers["content-range"] == f"bytes 4-15/{SIZE}"


# --- address validation (before any lookup) --------------------------------


async def test_malformed_hash_400(client) -> None:
    for url in ("/blobs/ab/cd/short", "/blobs/ab/cd/" + "A" * 64, "/blobs/ab/cd/" + "g" * 64):
        r = await client.get(url)
        assert r.status_code == 400, url
        assert r.json()["error_code"] == "VALIDATION_ERROR"
    assert (await client.head("/blobs/ab/cd/notahash")).status_code == 400


async def test_prefix_mismatch_400(client) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    bh = url.rsplit("/", 1)[-1]
    r = await client.get(f"/blobs/zz/zz/{bh}")
    assert r.status_code == 400
    assert r.json()["error_code"] == "VALIDATION_ERROR"


async def test_unknown_blob_404(client) -> None:
    r = await client.get("/blobs/00/00/" + "0" * 64)
    assert r.status_code == 404
    assert r.json()["error_code"] == "BLOB_NOT_FOUND"
    assert (await client.head("/blobs/00/00/" + "0" * 64)).status_code == 404


# --- integrity anomalies (§27) ---------------------------------------------


async def test_registered_missing_file_404_and_logs(client, settings, caplog) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    bh = url.rsplit("/", 1)[-1]
    _phys(settings, bh).unlink()  # lose the physical bytes

    with caplog.at_level(logging.ERROR, logger="soloring.api.blobs"):
        r = await client.get(url)
    assert r.status_code == 404
    assert r.json()["error_code"] == "BLOB_NOT_FOUND"
    assert bh in caplog.text
    assert "missing" in caplog.text.lower()


async def test_verified_upload_repairs_missing_bytes(client, settings, caplog) -> None:
    pid = await _project(client)
    r1 = await client.post(f"/projects/{pid}/assets", files={"file": ("f.png", PNG, "image/png")})
    bh = r1.json()["blob_hash"]
    _phys(settings, bh).unlink()  # registered row now missing bytes

    with caplog.at_level(logging.ERROR, logger="soloring.assets.upload"):
        r2 = await client.post(f"/projects/{pid}/assets", files={"file": ("f.png", PNG, "image/png")})
    assert r2.status_code == 201
    assert r2.json()["blob_hash"] == bh  # converged to the same Blob
    assert _phys(settings, bh).read_bytes() == PNG  # bytes restored
    assert "BLOB REPAIR" in caplog.text
    assert bh in caplog.text


async def test_unregistered_physical_file_not_served(client, settings) -> None:
    # A file merely existing on disk does not make it API-visible (§27.3).
    data = b"\x89PNG\r\n\x1a\norphan"
    bh = hashlib.sha256(data).hexdigest()
    phys = _phys(settings, bh)
    phys.parent.mkdir(parents=True, exist_ok=True)
    phys.write_bytes(data)
    r = await client.get(f"/blobs/{bh[:2]}/{bh[2:4]}/{bh}")
    assert r.status_code == 404
    assert r.json()["error_code"] == "BLOB_NOT_FOUND"


async def test_upload_registers_existing_unregistered_file(client, settings, engine) -> None:
    data = b"\x89PNG\r\n\x1a\npreexisting"
    bh = hashlib.sha256(data).hexdigest()
    phys = _phys(settings, bh)
    phys.parent.mkdir(parents=True, exist_ok=True)
    phys.write_bytes(data)  # file exists, no DB row

    pid = await _project(client)
    r = await client.post(f"/projects/{pid}/assets", files={"file": ("f.png", data, "image/png")})
    assert r.status_code == 201
    assert r.json()["blob_hash"] == bh
    g = await client.get(f"/blobs/{bh[:2]}/{bh[2:4]}/{bh}")
    assert g.status_code == 200 and g.content == data

    # exactly one blob row for that hash
    async with engine.connect() as c:
        n = (await c.execute(text("SELECT count(*) FROM blobs WHERE hash=:h"), {"h": bh})).scalar()
    assert n == 1


async def test_serving_never_exposes_storage_paths(client, settings) -> None:
    pid = await _project(client)
    url = await _upload(client, pid)
    r = await client.get(url)
    for header_value in r.headers.values():
        assert str(settings.blob_dir) not in header_value
        assert str(settings.data_dir) not in header_value
    assert b"sha256/" not in r.content  # body is raw bytes, not a path
