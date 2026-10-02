"""M17C-C RR10 correction (frozen register RR10-M17CC-01) — the
document-bearing VP identity is certified BEFORE canonicalization.

Before RR10, `vocal_performance_revision_id` reached
`canonical_json_str()` without storage-type certification: the
VARCHAR(36)+FK column has no `typeof = 'text'` law, so a BLOB staged
through a raw connection with FK enforcement disabled persisted in
the TEXT-affinity column, returned as Python `bytes`, and
`json.dumps` raised a raw `TypeError: Object of type bytes is not
JSON serializable` — which none of the three consumers normalized
(PF-03 and recovery catch BindingStructuralError only; §12 catches
ValueError, not TypeError).

The correction: `verify_stored_vocal_binding` certifies the id as an
actual NONEMPTY Python `str` BEFORE the canonical document is
constructed — a new STABLE typed category (`vp_identity_storage`;
routing on category only). Deliberately narrow: actual str storage +
nonempty is the whole law (no UUID normalization/case
rewriting/identity grammar — semantic referential validation stays
with the existing VP laws AFTER structural certification). The RR9
sample checks and the five RR8 predecessor category->message
mappings are unchanged; `binding_json`/`binding_hash` need NO new
grammar — they are only ever `!=`-compared, and `bytes != str`
evaluates to TRUE (RR11-M17CC-01 correcting this narrative: the
original said False), so the existing guards' conditions are TRUE
for BLOB/bytes storage and ENTER the typed binding_json/
binding_hash divergence branches (proven executable below).

The frozen battery:
1. unit: every non-str id shape (bytes BLOB, int, None) and the
   empty str refuse at the exact category with the exact PF-03
   message; a lawful str id verifies green;
2. the decisive adversary: the SAME genuine BLOB id on BOTH the
   candidate and revision binding rows (raw SQLite; typeof 'blob'
   proven on both; pair equality preserved; deliberately NOT
   re-signed — certification must refuse before serialization
   becomes possible) refuses live PF-03 PUT authority (the new typed
   message), live readiness (typed 500), live §12 (the typed
   structural-binding invariant, never an unhandled exception), and
   staged M17C recovery (typed RECOVERY_CORRUPTION) — never a raw
   TypeError, and no persistence side effect;
3. the clean control: the lawful str path stays fully green;
4. the RR11 executable-semantics proof: a BLOB/bytes binding_json
   and a BLOB/bytes binding_hash each terminate through their
   EXISTING typed categories (binding_json / binding_hash) and
   PF-03's RR8 predecessor mapping — no new category or grammar.
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
from tests.test_m17c_shot_mapping import _bound_world, _seg_body

_HEAD = "0023_m17cc_capture_closure_preimage"
_REV_BINDINGS = "performance_revision_vocal_bindings"
_CAND_BINDINGS = "performance_candidate_vocal_bindings"
_BLOB_ID = b"00000000-0000-4000-8000-0000000000bb"


def _engine(client):
    return client._transport.app.state.engine


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


def _typeof(client, table, key_col, key) -> str:
    con = _db(client)
    try:
        return con.execute(
            f"SELECT typeof(vocal_performance_revision_id) FROM {table} "
            f"WHERE {key_col} = ?", (key,)).fetchone()[0]
    finally:
        con.close()


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


def _lawful_doc(vp_id="00000000-0000-4000-8000-0000000000aa"):
    return {
        "binding_schema_version": 1,
        "synchronization_basis_version": 1,
        "vocal_performance_revision_id": vp_id,
        "source_start_sample": 48000,
        "source_end_sample_exclusive": 96000,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 0, "den": 1},
    }


# ---------------------------------------------------------------------------
# 1 — the typed category and PF-03 message, pinned
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("vp_id,reason", [
    (_BLOB_ID,
     "vocal_performance_revision_id "
     "b'00000000-0000-4000-8000-0000000000bb' is not a persisted "
     "text value (BLOB/non-text SQLite storage class)"),
    (12345,
     "vocal_performance_revision_id 12345 is not a persisted text "
     "value (BLOB/non-text SQLite storage class)"),
    (None,
     "vocal_performance_revision_id None is not a persisted text "
     "value (BLOB/non-text SQLite storage class)"),
    ("",
     "vocal_performance_revision_id is empty"),
])
def test_rr10_vp_identity_storage_refusal_typed(vp_id, reason):
    """Every malformed persisted VP-identity shape refuses at the
    shared law with the EXACT stable category, BEFORE document
    construction — and PF-03 surfaces the new typed message
    (category-routed, never diagnostic text)."""
    from soloring.errors import SoloRingError
    from soloring.performance.m17c_binding import (
        BindingStructuralError, _verify_binding_bytes,
        verify_stored_vocal_binding,
    )

    doc = _lawful_doc()

    class _Row:
        pass

    row = _Row()
    row.binding_schema_version = 1
    row.synchronization_basis_version = 1
    row.vocal_performance_revision_id = vp_id
    row.source_start_sample = doc["source_start_sample"]
    row.source_end_sample_exclusive = doc["source_end_sample_exclusive"]
    row.sample_rate_hz = doc["sample_rate_hz"]
    row.performance_origin_num = 0
    row.performance_origin_den = 1
    row.binding_json = _cj(doc)
    row.binding_hash = _ch(doc)

    with pytest.raises(BindingStructuralError) as excinfo:
        verify_stored_vocal_binding(
            binding_schema_version=1, synchronization_basis_version=1,
            vocal_performance_revision_id=vp_id,
            source_start_sample=row.source_start_sample,
            source_end_sample_exclusive=(
                row.source_end_sample_exclusive),
            sample_rate_hz=row.sample_rate_hz,
            performance_origin_num=0, performance_origin_den=1,
            binding_json=row.binding_json,
            binding_hash=row.binding_hash)
    assert excinfo.value.category == \
        BindingStructuralError.CATEGORY_VP_IDENTITY_STORAGE
    assert excinfo.value.reason == reason

    with pytest.raises(SoloRingError) as pf03:
        _verify_binding_bytes(row)
    assert pf03.value.status_code == 500
    # the exact new typed message — equality, not fragment
    assert pf03.value.message == (
        "M17C vocal binding stores a malformed persisted VP revision "
        f"id: {reason}")


def test_rr10_lawful_str_identity_passes():
    """The certification refuses nothing lawful: a canonical row with
    an actual nonempty str id self-authenticates and returns the
    canonical document (the RR9 numeric boundary shapes included)."""
    from soloring.performance.m17c_binding import (
        verify_stored_vocal_binding,
    )

    for start, end, rate in ((48000, 96000, 48000), (0, 1, 1)):
        doc = _lawful_doc()
        doc["source_start_sample"] = start
        doc["source_end_sample_exclusive"] = end
        doc["sample_rate_hz"] = rate
        verified = verify_stored_vocal_binding(
            binding_schema_version=1, synchronization_basis_version=1,
            vocal_performance_revision_id=doc[
                "vocal_performance_revision_id"],
            source_start_sample=start,
            source_end_sample_exclusive=end,
            sample_rate_hz=rate,
            performance_origin_num=0, performance_origin_den=1,
            binding_json=_cj(doc), binding_hash=_ch(doc))
        assert verified == doc


# ---------------------------------------------------------------------------
# 2 — the decisive BLOB-identity adversary (live + recovery)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr10_blob_vp_id_refuses_typed_everywhere(
        client, tmp_path):
    """A genuine SQLite BLOB vocal_performance_revision_id (the SAME
    bytes on BOTH the candidate and revision binding rows, written
    with a raw connection; typeof 'blob' proven on both; pair
    equality preserved; deliberately NOT re-signed — a BLOB document
    cannot be canonically serialized at all, which is the point)
    refuses live PF-03 PUT authority, live readiness, live §12, and
    staged M17C recovery — each TYPED, never a raw TypeError, and
    with no persistence side effect."""
    from soloring.errors import SoloRingError
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )

    world, revision = await _stage_lawful(client)

    # the storage class is genuinely text before the tamper
    assert _typeof(client, _REV_BINDINGS, "performance_revision_id",
                   world["pr"]["id"]) == "text"
    assert _typeof(client, _CAND_BINDINGS, "performance_candidate_id",
                   world["candidate"]["id"]) == "text"

    # the raw-connection BLOB rewrite (sqlite3 binds bytes as BLOB;
    # raw connections enforce no FK by default) — NO re-sign
    con = _db(client)
    try:
        con.execute(
            f"UPDATE {_REV_BINDINGS} SET "
            "vocal_performance_revision_id = ? "
            "WHERE performance_revision_id = ?",
            (_BLOB_ID, world["pr"]["id"]))
        con.execute(
            f"UPDATE {_CAND_BINDINGS} SET "
            "vocal_performance_revision_id = ? "
            "WHERE performance_candidate_id = ?",
            (_BLOB_ID, world["candidate"]["id"]))
        con.commit()
    finally:
        con.close()

    # the values are stored by SQLite as BLOB — proven on both tables
    assert _typeof(client, _REV_BINDINGS, "performance_revision_id",
                   world["pr"]["id"]) == "blob"
    assert _typeof(client, _CAND_BINDINGS, "performance_candidate_id",
                   world["candidate"]["id"]) == "blob"

    from soloring.performance.m17c_contract import BINDING_FIELDS
    rev = await _row(client, (
        f"SELECT * FROM {_REV_BINDINGS} WHERE "
        "performance_revision_id = :p"), {"p": world["pr"]["id"]})
    cand_row = await _row(client, (
        f"SELECT * FROM {_CAND_BINDINGS} WHERE "
        "performance_candidate_id = :p"),
        {"p": world["candidate"]["id"]})
    # pair equality is INTACT (the same BLOB on both rows) — no
    # pair-divergence law can mask the structural failure
    assert all(rev[f] == cand_row[f] for f in BINDING_FIELDS)

    before = await _binding_counts(client)

    # live PF-03 authority (PUT — media-grade seam): the NEW typed
    # message, byte-for-byte — never a raw TypeError
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 250, 750, 250, vp=0))
    assert r.status_code == 500, r.text
    assert r.json()["message"] == (
        "M17C vocal binding stores a malformed persisted VP revision "
        "id: vocal_performance_revision_id "
        "b'00000000-0000-4000-8000-0000000000bb' is not a persisted "
        "text value (BLOB/non-text SQLite storage class)"), r.text

    # live readiness: typed 500 (the read-grade seam surfaces its own
    # typed VP law — fail-closed, never an uncontrolled exception)
    r = await client.get(
        f"/shots/{world['shot']}/performance-readiness")
    assert r.status_code == 500, r.text
    assert "vocal binding" in r.json()["message"], r.text

    # live §12 history: the shared structural law's typed invariant
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    message = r.json()["message"]
    assert ("names an immutable synchronization binding that fails "
            "its own canonical structural law" in message), message
    assert ("vocal_performance_revision_id "
            "b'00000000-0000-4000-8000-0000000000bb' is not a "
            "persisted text value" in message), message
    # NOT the captured-hash branch (no re-sign happened at all)
    assert "captured vocal closure disagrees" not in message, message

    # no mutation escaped the refusals
    assert await _binding_counts(client) == before

    # staged M17C recovery independently refuses the same state —
    # typed RECOVERY_CORRUPTION, never a raw TypeError
    data_dir = client._transport.app.state.settings.data_dir
    root = tmp_path / "rr10-blob-id-staged"
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
    assert ("vocal_performance_revision_id "
            "b'00000000-0000-4000-8000-0000000000bb' is not a "
            "persisted text value" in rec.value.message), \
        rec.value.message


# ---------------------------------------------------------------------------
# 3 — the clean control: the lawful str path stays green
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr10_clean_control_lawful_path_green(client):
    """The certification refuses nothing lawful: a canonical str-id
    binding world stays READY, captures, reads green through §12
    (exposed binding_hash == the canonical hash of the lawful
    document), and passes backup + M17A + M17C recovery."""
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
    root = await _backup_m17c(client, tmp, "rr10-clean")
    verify_m17a_dialogue_vocal_state(
        root / "soloring.db", blob_root=root / "blobs")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD)


# ---------------------------------------------------------------------------
# 4 — the RR11 executable-semantics proof (proof-only; no product change)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,category", [
    ("binding_json", "binding_json"),
    ("binding_hash", "binding_hash"),
])
def test_rr11_blob_serialized_inputs_diverge_typed(field, category):
    """RR11-M17CC-01 — the corrected law stated executably: a BLOB/
    bytes `binding_json` and a BLOB/bytes `binding_hash` each make the
    shared verifier's `!=` condition TRUE (bytes != str is True), so
    each ENTERS its EXISTING typed divergence branch —
    CATEGORY_BINDING_JSON / CATEGORY_BINDING_HASH — and PF-03 maps
    both to the exact RR8 predecessor message (the predecessor merged
    json+hash divergence into one form). No new category, no new
    grammar, no product change."""
    from soloring.errors import SoloRingError
    from soloring.performance.m17c_binding import (
        BindingStructuralError, _verify_binding_bytes,
        verify_stored_vocal_binding,
    )

    doc = _lawful_doc()
    binding_json = _cj(doc)
    binding_hash = _ch(doc)

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
    row.binding_json = binding_json
    row.binding_hash = binding_hash

    # the BLOB/bytes storage class for exactly ONE serialized input,
    # the other kept lawful — the exact Python-semantics premise
    if field == "binding_json":
        row.binding_json = binding_json.encode("ascii")
    else:
        row.binding_hash = binding_hash.encode("ascii")
    # bytes != str is True — the premise, verified in-band
    assert (row.binding_json if field == "binding_json"
            else row.binding_hash) != (
        binding_json if field == "binding_json" else binding_hash)

    with pytest.raises(BindingStructuralError) as excinfo:
        verify_stored_vocal_binding(
            binding_schema_version=1, synchronization_basis_version=1,
            vocal_performance_revision_id=doc[
                "vocal_performance_revision_id"],
            source_start_sample=row.source_start_sample,
            source_end_sample_exclusive=(
                row.source_end_sample_exclusive),
            sample_rate_hz=row.sample_rate_hz,
            performance_origin_num=0, performance_origin_den=1,
            binding_json=row.binding_json,
            binding_hash=row.binding_hash)
    # the EXISTING typed category — no new category introduced
    assert excinfo.value.category == category

    with pytest.raises(SoloRingError) as pf03:
        _verify_binding_bytes(row)
    assert pf03.value.status_code == 500
    # the EXACT RR8 predecessor message (json+hash merged), unchanged
    assert pf03.value.message == \
        "M17C vocal binding canonical bytes/hash diverge"
