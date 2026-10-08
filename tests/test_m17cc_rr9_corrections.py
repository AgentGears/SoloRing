"""M17C-C RR9 correction (frozen register RR9-M17CC-01) — the shared
PF-03 binding structural law and the M17C recovery binding verifier
are TOTAL over SQLite storage classes.

Before RR9, a storage-valid non-integral REAL binding scalar (SQLite
INTEGER affinity persists REALs — 48000.5 stays 'real') escaped the
typed corruption contract: the shared law serialized/hashed floats
lawfully (a coherent re-sign passes the byte laws by construction)
and the raw TypeError surfaced only later, at Fraction/subtraction
time on the live seam and at math.gcd time in recovery.

The correction: `verify_stored_vocal_binding` certifies
source_start_sample / source_end_sample_exclusive / sample_rate_hz as
actual non-bool Python integers with 0 <= start < end and rate > 0
BEFORE any canonical serialization, hashing, comparison, or
arithmetic — new STABLE typed categories (sample_storage /
sample_domain; the five RR8 category->message mappings are
untouched); M17C recovery consumes the SAME law (its local schema /
_check_rational / doc-reconstruction grammar is replaced), and
`_check_rational` is itself total, so no unchecked gcd/Fraction path
can receive a malformed storage class under any pass ordering.

The frozen battery:
1. unit: lawful rows verify green; storage-class and domain refusals
   carry the exact typed categories and PF-03 messages;
2. the decisive adversary: a coherently re-signed genuine SQLite REAL
   coordinate (source_start_sample = 48000.5) on BOTH the candidate
   and revision binding rows (pair equality preserved, canonical
   bytes/hash recomputed so the byte laws pass by construction, the
   values demonstrably stored as typeof 'real') refuses LIVE
   PF-03/readiness and §12 authority as typed 500 corruption and
   staged M17C recovery as typed RECOVERY_CORRUPTION — never a raw
   TypeError, never successful verification;
3. the genuine non-integral origin 0.5/1 (the exact math.gcd
   raw-TypeError site) refuses typed on the same surfaces;
4. the clean control: the lawful integer path stays fully green
   (readiness READY, capture, §12 read, backup + M17A + M17C
   recovery) — the certification refuses nothing lawful.
"""

from __future__ import annotations

import json
import shutil
import sqlite3

import pytest

from soloring.domain.canonical import (
    canonical_hash as _ch, canonical_json_str as _cj,
)
from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world

_HEAD = "0023_m17cc_capture_closure_preimage"
_REV_BINDINGS = "performance_revision_vocal_bindings"
_CAND_BINDINGS = "performance_candidate_vocal_bindings"


def _engine(client):
    return client._transport.app.state.engine


async def _sql(client, stmt, params=None):
    from sqlalchemy import text
    async with _engine(client).begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _row(client, stmt, params=None):
    from sqlalchemy import text
    async with _engine(client).connect() as conn:
        return dict((await conn.execute(
            text(stmt), params or {})).mappings().one())


async def _stage_lawful(client):
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    return world, revision


def _db(client):
    return sqlite3.connect(
        client._transport.app.state.settings.data_dir / "soloring.db")


async def _binding_counts(client):
    from sqlalchemy import text
    async with _engine(client).connect() as conn:
        return [dict(r) for r in (await conn.execute(text(
            "SELECT (SELECT COUNT(*) FROM "
            "performance_revision_vocal_bindings) AS rb, "
            "(SELECT COUNT(*) FROM "
            "performance_candidate_vocal_bindings) AS cb, "
            "(SELECT COUNT(*) FROM shot_vocal_segment_mappings) "
            "AS vm, "
            "(SELECT COUNT(*) FROM shot_performance_segment_mappings) "
            "AS pm"))).mappings()]


def _coherently_resign(client, world, column, value):
    """Rewrite BOTH binding rows coherently: the scalar column takes a
    genuine non-integral REAL and binding_json/binding_hash are
    recomputed from the row's own post-tamper fields, so the canonical
    byte laws pass BY CONSTRUCTION and pair equality is preserved —
    only the storage-class structural law can refuse. Returns the
    tampered document (for byte-law assertions)."""
    con = _db(client)
    try:
        row = con.execute(
            f"SELECT * FROM {_REV_BINDINGS} WHERE "
            "performance_revision_id = ?",
            (world["pr"]["id"],)).fetchone()
        cols = [d[0] for d in con.execute(
            f"SELECT * FROM {_REV_BINDINGS} LIMIT 0").description]
        r = dict(zip(cols, row))
        doc = {
            "binding_schema_version": r["binding_schema_version"],
            "synchronization_basis_version":
                r["synchronization_basis_version"],
            "vocal_performance_revision_id":
                r["vocal_performance_revision_id"],
            "source_start_sample": r["source_start_sample"],
            "source_end_sample_exclusive":
                r["source_end_sample_exclusive"],
            "sample_rate_hz": r["sample_rate_hz"],
            "performance_origin_ms": {
                "num": r["performance_origin_num"],
                "den": r["performance_origin_den"]},
        }
        # splice the tampered scalar into the exact persisted shape
        if column == "source_start_sample":
            doc["source_start_sample"] = value
        elif column == "performance_origin_num":
            doc["performance_origin_ms"]["num"] = value
        else:  # pragma: no cover - battery-local dispatch
            raise AssertionError(column)
        binding_json, binding_hash = _cj(doc), _ch(doc)
        con.execute(
            f"UPDATE {_REV_BINDINGS} SET {column} = ?, "
            "binding_json = ?, binding_hash = ? "
            "WHERE performance_revision_id = ?",
            (value, binding_json, binding_hash, world["pr"]["id"]))
        con.execute(
            f"UPDATE {_CAND_BINDINGS} SET {column} = ?, "
            "binding_json = ?, binding_hash = ? "
            "WHERE performance_candidate_id = ?",
            (value, binding_json, binding_hash,
             world["candidate"]["id"]))
        con.commit()
        return doc
    finally:
        con.close()


def _typeof(client, table, key_col, key, column) -> str:
    con = _db(client)
    try:
        return con.execute(
            f"SELECT typeof({column}) FROM {table} "
            f"WHERE {key_col} = ?", (key,)).fetchone()[0]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 1 — the typed categories and PF-03 messages, pinned
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("column,value,category", [
    ("source_start_sample", 48000.5, "sample_storage"),
    ("source_end_sample_exclusive", 96000.5, "sample_storage"),
    ("sample_rate_hz", 48000.5, "sample_storage"),
    ("source_start_sample", True, "sample_storage"),
    ("source_end_sample_exclusive", "96000", "sample_storage"),
    ("sample_rate_hz", None, "sample_storage"),
    ("source_start_sample", 96000, "sample_domain"),
    ("source_end_sample_exclusive", 48000, "sample_domain"),
    ("source_start_sample", -1, "sample_domain"),
    ("sample_rate_hz", 0, "sample_domain"),
    ("sample_rate_hz", -48000, "sample_domain"),
])
def test_rr9_storage_and_domain_refusals_typed(column, value, category):
    """Every malformed sample-scalar shape refuses at the shared law
    with the EXACT stable category, BEFORE serialization/hashing —
    and PF-03 surfaces the two new typed messages (category-routed,
    never diagnostic text)."""
    from soloring.errors import SoloRingError
    from soloring.performance.m17c_binding import (
        BindingStructuralError, _verify_binding_bytes,
        verify_stored_vocal_binding,
    )

    doc = {
        "binding_schema_version": 1,
        "synchronization_basis_version": 1,
        "vocal_performance_revision_id":
            "00000000-0000-4000-8000-0000000000aa",
        "source_start_sample": 48000,
        "source_end_sample_exclusive": 96000,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 0, "den": 1},
    }
    if column in ("source_start_sample", "source_end_sample_exclusive",
                  "sample_rate_hz"):
        doc[column] = value

    class _Row:
        pass

    row = _Row()
    row.binding_schema_version = 1
    row.synchronization_basis_version = 1
    row.vocal_performance_revision_id = doc[
        "vocal_performance_revision_id"]
    row.source_start_sample = doc["source_start_sample"]
    row.source_end_sample_exclusive = doc["source_end_sample_exclusive"]
    row.sample_rate_hz = doc["sample_rate_hz"]
    row.performance_origin_num = 0
    row.performance_origin_den = 1
    # the canonical bytes/hash of the ROW'S OWN (tampered) fields —
    # the byte laws pass by construction; only the typed scalar law
    # can refuse
    row.binding_json = _cj(doc)
    row.binding_hash = _ch(doc)

    with pytest.raises(BindingStructuralError) as excinfo:
        verify_stored_vocal_binding(
            binding_schema_version=row.binding_schema_version,
            synchronization_basis_version=(
                row.synchronization_basis_version),
            vocal_performance_revision_id=(
                row.vocal_performance_revision_id),
            source_start_sample=row.source_start_sample,
            source_end_sample_exclusive=(
                row.source_end_sample_exclusive),
            sample_rate_hz=row.sample_rate_hz,
            performance_origin_num=row.performance_origin_num,
            performance_origin_den=row.performance_origin_den,
            binding_json=row.binding_json,
            binding_hash=row.binding_hash)
    assert excinfo.value.category == category

    with pytest.raises(SoloRingError) as pf03:
        _verify_binding_bytes(row)
    assert pf03.value.status_code == 500
    if category == "sample_storage":
        assert pf03.value.message == (
            "M17C vocal binding stores a non-integer sample scalar: "
            f"{excinfo.value.reason}")
    else:
        assert pf03.value.message == (
            "M17C vocal binding stores an illegal sample interval/rate: "
            f"{excinfo.value.reason}")


def test_rr9_lawful_rows_verify_green():
    """The certification refuses nothing lawful: canonical integer
    rows (including the boundary shapes start == 0 and a positive
    origin) self-authenticate and return the canonical document."""
    from soloring.performance.m17c_binding import (
        verify_stored_vocal_binding,
    )

    for start, end, rate, on, od in (
            (48000, 96000, 48000, 0, 1),
            (0, 1, 1, 2**63 - 1, 2**63 - 2),
            (0, 48000, 48000, 250, 3)):
        doc = {
            "binding_schema_version": 1,
            "synchronization_basis_version": 1,
            "vocal_performance_revision_id":
                "00000000-0000-4000-8000-0000000000aa",
            "source_start_sample": start,
            "source_end_sample_exclusive": end,
            "sample_rate_hz": rate,
            "performance_origin_ms": {"num": on, "den": od},
        }
        verified = verify_stored_vocal_binding(
            binding_schema_version=1, synchronization_basis_version=1,
            vocal_performance_revision_id=doc[
                "vocal_performance_revision_id"],
            source_start_sample=start,
            source_end_sample_exclusive=end,
            sample_rate_hz=rate,
            performance_origin_num=on, performance_origin_den=od,
            binding_json=_cj(doc), binding_hash=_ch(doc))
        assert verified == doc


# ---------------------------------------------------------------------------
# 2 — the decisive REAL coordinate adversary (live + recovery)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr9_real_coordinate_coherent_resign_refuses_typed(
        client, tmp_path):
    """A genuine SQLite REAL coordinate (source_start_sample = 48000.5,
    demonstrably typeof 'real') coherently re-signed on BOTH the
    candidate and revision binding rows: pair equality preserved, the
    canonical byte/hash laws pass by construction — live PF-03
    readiness, live §12 history, and staged M17C recovery each refuse
    as TYPED corruption, never a raw TypeError, never green."""
    from soloring.errors import SoloRingError
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )

    world, revision = await _stage_lawful(client)

    # the storage class is genuinely integer before the tamper
    assert _typeof(client, _REV_BINDINGS, "performance_revision_id",
                   world["pr"]["id"],
                   "source_start_sample") == "integer"
    assert _typeof(client, _CAND_BINDINGS, "performance_candidate_id",
                   world["candidate"]["id"],
                   "source_start_sample") == "integer"

    doc = _coherently_resign(
        client, world, "source_start_sample", 48000.5)

    # the values are stored by SQLite as REAL — INTEGER affinity
    # keeps a non-integral value in the real storage class
    assert _typeof(client, _REV_BINDINGS, "performance_revision_id",
                   world["pr"]["id"],
                   "source_start_sample") == "real"
    assert _typeof(client, _CAND_BINDINGS, "performance_candidate_id",
                   world["candidate"]["id"],
                   "source_start_sample") == "real"

    con = _db(client)
    try:
        stored = con.execute(
            f"SELECT binding_json FROM {_REV_BINDINGS} WHERE "
            "performance_revision_id = ?",
            (world["pr"]["id"],)).fetchone()[0]
        cand = con.execute(
            f"SELECT binding_json FROM {_CAND_BINDINGS} WHERE "
            "performance_candidate_id = ?",
            (world["candidate"]["id"],)).fetchone()[0]
    finally:
        con.close()
    # the byte law passes BY CONSTRUCTION: the stored bytes are the
    # canonical serialization of the row's own (REAL-bearing) fields
    assert stored == _cj(doc)
    assert cand == stored

    from soloring.performance.m17c_contract import BINDING_FIELDS
    rev = await _row(client, (
        f"SELECT * FROM {_REV_BINDINGS} WHERE "
        "performance_revision_id = :p"), {"p": world["pr"]["id"]})
    cand_row = await _row(client, (
        f"SELECT * FROM {_CAND_BINDINGS} WHERE "
        "performance_candidate_id = :p"),
        {"p": world["candidate"]["id"]})
    # pair equality is INTACT — only the structural law can refuse
    assert all(rev[f] == cand_row[f] for f in BINDING_FIELDS)

    before = await _binding_counts(client)

    # live PF-03/readiness authority: the TYPED corruption, exactly the
    # new pinned message — never a raw TypeError through Fraction
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert r.json()["message"] == (
        "M17C vocal binding stores a non-integer sample scalar: "
        "source_start_sample 48000.5 is not a persisted integer "
        "(non-integral SQLite storage class)"), r.text

    # live §12 history read: the shared structural law's rich reason
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    message = r.json()["message"]
    assert ("names an immutable synchronization binding that fails "
            "its own canonical structural law" in message), message
    assert ("source_start_sample 48000.5 is not a persisted integer"
            in message), message
    # NOT the captured-hash branch (the bytes were coherently re-signed)
    assert "captured vocal closure disagrees" not in message, message

    # no mutation escaped the refusals
    assert await _binding_counts(client) == before

    # staged M17C recovery independently refuses the same state —
    # typed RECOVERY_CORRUPTION, never a raw TypeError
    data_dir = client._transport.app.state.settings.data_dir
    root = tmp_path / "rr9-real-coordinate-staged"
    root.mkdir()
    src_db = data_dir / "soloring.db"
    con = sqlite3.connect(src_db)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    shutil.copy(src_db, root / "soloring.db")
    shutil.copytree(data_dir / "blobs", root / "blobs")
    with pytest.raises(SoloRingError) as rec:
        verify_m17c_binding_state(
            root / "soloring.db", root / "blobs", head=_HEAD)
    assert rec.value.code == "RECOVERY_CORRUPTION"
    assert "binding fails its own canonical structural law" \
        in rec.value.message, rec.value.message
    assert ("source_start_sample 48000.5 is not a persisted integer"
            in rec.value.message), rec.value.message


# ---------------------------------------------------------------------------
# 3 — the genuine non-integral origin 0.5/1 (the math.gcd escape site)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr9_real_origin_refuses_typed(client, tmp_path):
    """A genuine non-integral REAL origin (performance_origin_num =
    0.5, typeof 'real') coherently re-signed on both rows — the exact
    shape that previously reached recovery's math.gcd as a raw
    TypeError — now refuses typed on the recovery chain AND on the
    live seams (PF-03 keeps the RR8-pinned predecessor vocabulary)."""
    from soloring.errors import SoloRingError
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )

    world, revision = await _stage_lawful(client)

    assert _typeof(client, _REV_BINDINGS, "performance_revision_id",
                   world["pr"]["id"],
                   "performance_origin_num") == "integer"
    doc = _coherently_resign(
        client, world, "performance_origin_num", 0.5)
    assert _typeof(client, _REV_BINDINGS, "performance_revision_id",
                   world["pr"]["id"],
                   "performance_origin_num") == "real"
    con = _db(client)
    try:
        stored = con.execute(
            f"SELECT binding_json FROM {_REV_BINDINGS} WHERE "
            "performance_revision_id = ?",
            (world["pr"]["id"],)).fetchone()[0]
    finally:
        con.close()
    assert stored == _cj(doc)

    # live PF-03/readiness: the RR8-pinned predecessor message for the
    # malformed-rational category, byte-for-byte
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert r.json()["message"] == (
        "M17C vocal binding stores an invalid persisted rational: "
        "INVALID_RATIONAL: numerator and denominator must be "
        "integers"), r.text

    # live §12 history: the rich structural reason
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    message = r.json()["message"]
    assert ("fails its own canonical structural law" in message), message
    assert "the persisted origin is not an integer pair" in message, \
        message

    # recovery: typed RECOVERY_CORRUPTION — the raw math.gcd
    # TypeError path is gone
    data_dir = client._transport.app.state.settings.data_dir
    root = tmp_path / "rr9-real-origin-staged"
    root.mkdir()
    src_db = data_dir / "soloring.db"
    con = sqlite3.connect(src_db)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    shutil.copy(src_db, root / "soloring.db")
    shutil.copytree(data_dir / "blobs", root / "blobs")
    with pytest.raises(SoloRingError) as rec:
        verify_m17c_binding_state(
            root / "soloring.db", root / "blobs", head=_HEAD)
    assert rec.value.code == "RECOVERY_CORRUPTION"
    assert "binding fails its own canonical structural law" \
        in rec.value.message, rec.value.message
    assert "the persisted origin is not an integer pair" \
        in rec.value.message, rec.value.message


# ---------------------------------------------------------------------------
# 4 — the clean control: the lawful integer path stays green
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr9_clean_control_lawful_path_green(client):
    """The certification refuses nothing lawful: a canonical integer
    binding world stays READY, captures, reads green through §12, and
    passes backup + M17A + M17C recovery under the now-total law."""
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    from tests.test_m17c_sr26_regressions import _backup_m17c
    import tempfile
    from pathlib import Path

    world, revision = await _stage_lawful(client)

    red = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert red["ready"] is True, red

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    seg = r.json()["performance"]["segments"][0]
    exposed = seg["vocal"]["synchronization_binding"]["binding_hash"]
    assert exposed == _ch(json.loads(
        (await _row(client, (
            f"SELECT binding_json AS binding_json FROM "
            f"{_REV_BINDINGS} WHERE performance_revision_id = :p"),
            {"p": world["pr"]["id"]}))["binding_json"]))

    tmp = Path(tempfile.mkdtemp())
    root = await _backup_m17c(client, tmp, "rr9-clean")
    verify_m17a_dialogue_vocal_state(
        root / "soloring.db", blob_root=root / "blobs")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD)
