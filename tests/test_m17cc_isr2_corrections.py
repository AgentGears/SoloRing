"""M17C-C ISR2 corrections (frozen register ISR2-M17CC-01..03).

ISR2-01 — recovery authenticates the outer schema-8 ShotRevision
  envelope. `_verify_m17cc_capture_state` previously classified every
  revision from id/shot_id/snapshot_json only — it never read
  `snapshot_hash` and never required the persisted bytes to be the
  canonical serialization, so a schema-8 snapshot with one predecessor
  field coherently rewritten but a stale hash (or semantically
  identical noncanonical bytes) was certified even though the public
  historical path recomputes both. The schema-8 pass now proves
  `canonical_json_str(decoded) == persisted snapshot_json` and
  `canonical_hash(decoded) == persisted snapshot_hash` BEFORE any
  M17C-C closure interpretation (predecessor posture deliberately
  unchanged).

ISR2-02 — the three M17C-C successor tables carry frozen PHYSICAL
  schema contracts through the same `_verify_table_schema` machinery
  the predecessor tables use, proven BEFORE any semantic row
  traversal (separate lawful segment-table contracts for heads 0022
  and 0023 — 0023 adds the captured mapping-preimage columns and
  their constraints). A staged successor-head database whose CHECKs,
  FKs, indexes, or PK shape were weakened refuses at the physical
  boundary even with EMPTY tables, where quick_check,
  foreign_key_check, presence, and row semantics all stay green.

ISR2-03 — §12's retained Blob `size_bytes` is part of the verified
  closure: an actual nonnegative integer exactly equal to the
  physically read byte count, proven before either is exposed as
  historical truth (recovery/backup liveness already proved the same
  equality — the history/recovery asymmetry is closed).

The battery proves each finding with the review's adversaries at
BOTH surfaces where commissioned (the direct verifier and the full
restore for ISR2-01; the physical boundary for ISR2-02 including a
GENUINE 0022-shaped database built by a real alembic upgrade; §12
for ISR2-03), plus lawful controls.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from soloring.domain.canonical import (
    canonical_hash as _ch, canonical_json_str as _cj,
)
from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world

_HEAD_0022 = "0022_m17c_schema8_capture"
_HEAD_0023 = "0023_m17cc_capture_closure_preimage"
_PARENTS = "shot_revision_performance_specs"
_CHILDREN = "shot_revision_performance_segments"
_GPI = "generation_performance_inputs"


def _live_root(client):
    return client._transport.app.state.settings.data_dir


async def _stage_captured(client):
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    return world, revision


async def _stage_empty_successor(client):
    """A lawful head-0023 world with the three M17C-C tables EMPTY
    (mappings exist, no capture) — the review's otherwise-lawful
    empty state in which only the physical boundary can refuse."""
    world = await _bound_world(client)
    await _lawful(client, world)
    return world


async def _backup(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, f"isr2-{tag}")


def _verify_raises(root, fragment, head=_HEAD_0023):
    from soloring.errors import SoloRingError
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )
    with pytest.raises(SoloRingError) as rec:
        verify_m17c_binding_state(
            root / "soloring.db", root / "blobs", head=head)
    assert rec.value.code == "RECOVERY_CORRUPTION"
    assert fragment in rec.value.message, rec.value.message


def _rebuild_with_ddl(con, table, new_ddl):
    con.execute(f"DROP TABLE {table}")
    con.execute(new_ddl)
    con.commit()


# ---------------------------------------------------------------------------
# ISR2-01 — the outer schema-8 envelope is authenticated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("mode,fragment", [
    ("stale_hash",
     "schema-8 snapshot_hash does not authenticate its snapshot bytes"),
    ("noncanonical",
     "schema-8 snapshot_json is not the canonical serialization of "
     "its decoded snapshot"),
])
async def test_isr201_outer_envelope_authenticated_both_surfaces(
        client, tmp_path, mode, fragment):
    """The review's two outer adversaries, each leaving the complete
    Performance block and every companion row untouched:
    (a) a CANONICAL snapshot_json with one predecessor field changed
    but a STALE hash; (b) semantically identical NONCANONICAL bytes
    with the hash matching the decoded semantics. The direct M17C
    recovery verifier AND the full restore both refuse typed."""
    from tests.test_m17c_sr26_regressions import _restore_refuses

    world, revision = await _stage_captured(client)
    root = await _backup(client, tmp_path, f"outer-{mode}")

    con = sqlite3.connect(root / "soloring.db")
    try:
        snapshot_json, snapshot_hash = con.execute(
            "SELECT snapshot_json, snapshot_hash FROM shot_revisions "
            "WHERE id = ?", (revision.id,)).fetchone()
        snap = json.loads(snapshot_json)
        outer = [k for k in snap
                 if k not in ("performance", "schema_version")]
        assert outer, sorted(snap)
        snap[outer[0]] = "isr2-tampered-value"
        if mode == "stale_hash":
            # canonical bytes over the mutated document, hash untouched
            new_json = _cj(snap)
            new_hash = snapshot_hash
        else:
            # noncanonical bytes, hash matching the decoded semantics
            new_json = json.dumps(snap, indent=2)
            new_hash = _ch(snap)
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ?, "
            "snapshot_hash = ? WHERE id = ?",
            (new_json, new_hash, revision.id))
        con.commit()
    finally:
        con.close()

    _verify_raises(root, fragment)

    # the full restore refuses the same staged state
    await _restore_refuses(root, tmp_path, f"isr2-outer-{mode}")


# ---------------------------------------------------------------------------
# ISR2-02 — physical contracts for the three successor tables
# ---------------------------------------------------------------------------

def _damage_check(con):
    """Weaken ck_srpfs_schema's expression in place (name-preserving
    DDL surgery on the otherwise-frozen specs table)."""
    ddl = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (_PARENTS,)).fetchone()[0]
    assert "CHECK (schema_version = 1)" in ddl, ddl
    _rebuild_with_ddl(con, _PARENTS,
                      ddl.replace("CHECK (schema_version = 1)",
                                  "CHECK (schema_version >= 0)"))


def _damage_fk(con):
    """Weaken fk_srpss_pr from ON DELETE RESTRICT to CASCADE."""
    import re
    ddl = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (_CHILDREN,)).fetchone()[0]
    new_ddl, n = re.subn(
        r"(CONSTRAINT fk_srpss_pr FOREIGN KEY\(performance_revision_id\)"
        r" REFERENCES performance_revisions \(id\) ON DELETE )RESTRICT",
        r"\1CASCADE", ddl)
    assert n == 1, ddl
    _rebuild_with_ddl(con, _CHILDREN, new_ddl)
    # DROP TABLE dropped the migration's index — recreate it so ONLY
    # the FK divergence refuses
    con.execute(
        f"CREATE INDEX ix_srpss_pr ON {_CHILDREN} "
        "(performance_revision_id)")
    con.commit()


def _damage_index(con):
    con.execute("DROP INDEX ix_srpss_pr")
    con.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,fragment", [
    ("check_weakened", f"{_PARENTS} CHECK-contract diverges"),
    ("fk_weakened", f"{_CHILDREN} foreign-key contract diverges"),
    ("index_dropped", f"{_CHILDREN} explicit-index contract diverges"),
])
async def test_isr202_physical_boundary_refuses_damaged_ddl(
        client, tmp_path, mode, fragment):
    """The review's empty-table adversaries on otherwise-lawful head
    0023 state: weaken one CHECK, one non-Blob FK, or drop ix_srpss_pr
    — quick_check, foreign_key_check, presence, and row semantics all
    stay green, and recovery refuses at the PHYSICAL boundary (before
    any semantic row traversal)."""
    world = await _stage_empty_successor(client)
    root = await _backup(client, tmp_path, f"phys-{mode}")

    # the undamaged empty successor state is green — the refusal below
    # comes from the damage, not from the contracts
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD_0023)

    con = sqlite3.connect(root / "soloring.db")
    try:
        if mode == "check_weakened":
            _damage_check(con)
        elif mode == "fk_weakened":
            _damage_fk(con)
        else:
            _damage_index(con)
    finally:
        con.close()

    _verify_raises(root, fragment)


@pytest.mark.asyncio
async def test_isr202_genuine_0022_contract_enforced(client, tmp_path):
    """The genuine 0022 shape: a real alembic 0021→0022 upgrade builds
    the predecessor segment table (no preimage columns); the 0022
    contract certifies it green, and the same CHECK damage refuses at
    the physical boundary at 0022."""
    from tests.test_m17cc_migration import _run
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )

    world = await _stage_empty_successor(client)
    root = await _backup(client, tmp_path, "phys-0022")

    # reshape into a GENUINE 0021 database (the established pattern)
    from soloring.domain.canonical import canonical_json_bytes
    import hashlib
    con = sqlite3.connect(root / "soloring.db")
    for t in (_PARENTS, _CHILDREN, _GPI):
        con.execute(f"DROP TABLE {t}")
    con.execute("UPDATE alembic_version SET version_num = ?",
                ("0021_m17c_shot_performance_mappings",))
    con.commit()
    con.close()
    manifest_path = root / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["alembic_version"] = "0021_m17c_shot_performance_mappings"
    manifest["database_sha256"] = hashlib.sha256(
        (root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    up = _run(root / "soloring.db", "upgrade", _HEAD_0022)
    assert up.returncode == 0, (up.stderr or "")[-800:]

    # the genuine 0022 shape passes the 0022 contracts
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD_0022)

    con = sqlite3.connect(root / "soloring.db")
    try:
        _damage_check(con)
    finally:
        con.close()
    _verify_raises(root, f"{_PARENTS} CHECK-contract diverges",
                   head=_HEAD_0022)


# ---------------------------------------------------------------------------
# ISR2-03 — the retained Blob size is part of §12's verified closure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("mode,value", [
    ("plus_one", 1),          # added to the lawful size in-test
    ("real_storage", 48000.5),
])
async def test_isr203_retained_size_verified(client, mode, value):
    """The review's adversaries: mutate ONLY blobs.size_bytes (the
    physical bytes and hash untouched) — an off-by-one integer, and a
    genuine SQLite REAL (typeof proven). §12 must typed-refuse; the
    lawful payload history was proven green immediately before."""
    world, revision = await _stage_captured(client)

    # the lawful control: green, and the exposed size equals the
    # physically returned byte count
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    import base64
    payload = r.json()["performance"]["segments"][0][
        "performance_payload"]
    assert payload["size_bytes"] == len(base64.b64decode(
        payload["payload_bytes_base64"]))

    blob_hash = payload["blob_hash"]
    con = sqlite3.connect(_live_root(client) / "soloring.db")
    try:
        if mode == "plus_one":
            con.execute(
                "UPDATE blobs SET size_bytes = size_bytes + 1 "
                "WHERE hash = ?", (blob_hash,))
        else:
            con.execute(
                "UPDATE blobs SET size_bytes = ? WHERE hash = ?",
                (value, blob_hash))
        con.commit()
        stored = con.execute(
            "SELECT typeof(size_bytes) FROM blobs WHERE hash = ?",
            (blob_hash,)).fetchone()[0]
    finally:
        con.close()
    if mode == "real_storage":
        assert stored == "real", stored

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    message = r.json()["message"]
    assert "retained Blob size" in message, message
    assert "disagrees with the physically read payload bytes" \
        in message, message
