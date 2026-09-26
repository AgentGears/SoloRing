"""M17A test helpers: deterministic WAVE generation, content-addressed
Blob placement (physical bytes + blobs row), project/entity/shot
scaffolding, and the alembic stamp."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

from sqlalchemy import text


def wave_bytes(sample_rate_hz: int = 48000, frames: int = 216000,
               channels: int = 1, bits: int = 16) -> bytes:
    """Deterministic RIFF/WAVE uncompressed PCM. The sample sequence is
    a pure function of (rate, frames, channels, bits) — same inputs
    always produce identical bytes (frozen R5 §14.0)."""
    frame_bytes = channels * (bits // 8)
    data = bytearray()
    for i in range(frames):
        for _c in range(channels):
            v = (i * 37) % 8000 - 4000  # deterministic, in 16-bit range
            if bits == 16:
                data += struct.pack("<h", v)
            else:
                data += struct.pack("<B", (v + 4000) // 32)
    payload = bytes(data)
    hdr = b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVE"
    fmt = b"fmt " + struct.pack(
        "<IHHIIHH", 16, 1, channels, sample_rate_hz,
        sample_rate_hz * frame_bytes, frame_bytes, bits)
    dat = b"data" + struct.pack("<I", len(payload))
    return hdr + fmt + dat + payload


async def place_blob(client, data: bytes) -> str:
    """Physical content-addressed bytes + the blobs row, via the
    client's engine (the single session authority of the test)."""
    settings = client._transport.app.state.settings
    h = hashlib.sha256(data).hexdigest()
    rel = Path("sha256") / h[:2] / h[2:4] / h
    target = settings.blob_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    engine = client._transport.app.state.engine
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
            "detected_media_type, created_at) VALUES (:h, :p, :s, "
            "'audio/wav', strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),
            {"h": h, "p": rel.as_posix(), "s": len(data)})
    return h


async def make_project(client) -> str:
    r = await client.post("/projects", json={"name": "m17a"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def make_entity(client, pid: str, name: str = "Eva") -> str:
    r = await client.post(f"/projects/{pid}/entities",
                          json={"kind": "character", "name": name})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    r = await client.post(f"/entities/{eid}/revisions",
                          json={"spec": {"description": name}})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    r = await client.put(f"/entities/{eid}/approved-revision",
                         json={"revision_id": rid,
                               "expected_approved_revision_id": None})
    assert r.status_code == 200, r.text
    return eid


async def make_shot(client, pid: str, duration_ms: int) -> str:
    r = await client.post(f"/projects/{pid}/shots",
                          json={"subject": "s", "duration_ms": duration_ms})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def stamp_alembic(client, head: str =
                        "0020_m17c_performance_capture") -> None:  # M17C-A advances the head
    async with client._transport.app.state.engine.begin() as conn:
        await conn.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        await conn.execute(text("DELETE FROM alembic_version"))
        await conn.execute(text(
            "INSERT INTO alembic_version (version_num) VALUES (:h)"),
            {"h": head})
