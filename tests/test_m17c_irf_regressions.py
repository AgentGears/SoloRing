"""M17C-B IR-final corrective regressions (M17C-IR-01..06, frozen
under the PR #26 protocol cycle of 2026-09-28 night; product base
e0c4e07).

- IR-01: closed-world, multiplicity-preserving physical-schema proof —
  anonymous/lowercase/duplicate CHECKs, duplicate conflicting FKs, and
  extra explicit indexes all refuse at both heads.
- IR-02: the ONE transport-neutral persisted PF-02 mapping law shared
  by live reads and recovery — coherent-rehash corruption matrix plus
  the lawful working-state positives.
- IR-03: mode-independent historical parent authority — a corrupted
  adopted history refuses as 500 corruption on the candidate and
  revision binding GETs, adoption replay, and retarget (zero new
  rows), while lawful NONE history keeps its honest 404s.
- IR-04: complete non-media adopted-pair closure — asymmetric
  one-sided tampering agrees on candidate GET, revision GET, PF-02
  readiness, and recovery.
- IR-05: missing retained payload BYTES are structured domain failures
  everywhere (never a raw OSError), with fresh admission untouched.
- IR-06: branch-specific recovery evidence — the stable
  recovery-corruption contract plus a law-specific diagnostic, never
  pytest.raises(Exception).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.errors import SoloRingError
from tests.test_m17c_binding_transitions import _same_line_alternate_vp
from tests.test_m17c_shot_mapping import (
    _bound_world,
    _generic_world,
    _seg_body,
)

_TABLE = "shot_performance_segment_mappings"
_SPSM = "shot_performance_segment_mappings"


def _engine(client):
    return client._transport.app.state.engine


async def _sql(client, stmt, params=None):
    async with _engine(client).begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _one(client, stmt, params=None):
    async with _engine(client).connect() as conn:
        return dict((await conn.execute(
            text(stmt), params or {})).mappings().one())


def _corrupt(resp):
    assert resp.status_code == 500, resp.text
    assert resp.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def _lawful_put(client, world):
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text


def _ddl(root: Path, table: str) -> str:
    con = sqlite3.connect(root / "soloring.db")
    sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
        (table,)).fetchone()[0]
    con.close()
    return sql


def _rebuild(root: Path, table: str, transform=None, after=None) -> None:
    """DDL surgery on a staged backup: transform the stored CREATE
    TABLE text, drop + recreate, then optional extra statements."""
    con = sqlite3.connect(root / "soloring.db")
    sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
        (table,)).fetchone()[0]
    if transform:
        sql = transform(sql)
    con.execute(f"DROP TABLE {table}")
    con.executescript(sql + ";")
    if after:
        con.executescript(after + ";")
    con.commit()
    con.close()


async def _restore_refuses(backup_root, tmp_path, tag):
    from tests.test_m17c_sr2_regressions import (
        _restore_refuses as sr2_refuses)
    return await sr2_refuses(backup_root, tmp_path, tag)


async def _backup_0021(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, tag)


async def _backup_0020(client, tmp_path, tag):
    from soloring.recovery.backup import M17C_A_ALEMBIC_HEAD
    from tests.test_m17c_sr2_regressions import _retarget_backup
    root = await _backup_0021(client, tmp_path, tag + "-src")
    _retarget_backup(root, M17C_A_ALEMBIC_HEAD, drop_pf02=True)
    return root


def _append_constraint(sql: str, clause: str) -> str:
    """Insert a table-level clause before the closing paren."""
    return sql.rstrip()[:-1].rstrip().rstrip(",") + ", \n\t" + clause \
        + "\n)"


# ---------------------------------------------------------------------------
# IR-01 — closed-world, multiplicity-preserving schema proof
# ---------------------------------------------------------------------------

_IR01_CASES = [
    ("anonymous_extra_check",
     lambda sql: _append_constraint(
         sql, "CHECK (mapping_schema_version = 1)"),
     None, "CHECK-contract diverges"),
    ("lowercase_named_check",
     lambda sql: _append_constraint(
         sql, "constraint ck_extra_bad check (position >= 0)"),
     None, "CHECK-contract diverges"),
    ("duplicate_same_name_bad_plus_good",
     lambda sql: sql.replace(
         "CHECK (position >= 0)",
         "CHECK (1), \n\tCONSTRAINT "
         "ck_shot_performance_segment_mappings_ck_spsm_position "
         "CHECK (position >= 0)"),
     None, "CHECK-contract diverges"),
    ("extra_ordinary_index",
     None,
     f"CREATE INDEX ix_spsm_extra ON {_SPSM} (shot_id)",
     "explicit-index contract diverges"),
    ("extra_unique_index",
     None,
     f"CREATE UNIQUE INDEX ix_spsm_extra ON {_SPSM} (shot_id)",
     "explicit-index contract diverges"),
    ("extra_partial_index",
     None,
     f"CREATE INDEX ix_spsm_extra ON {_SPSM} (shot_id) "
     "WHERE position >= 0",
     "explicit-index contract diverges"),
    ("duplicate_fk_conflicting_on_delete",
     lambda sql: _append_constraint(
         sql, "CONSTRAINT fk_dup FOREIGN KEY(shot_id) REFERENCES "
              "shots (id) ON DELETE CASCADE"),
     None, "foreign-key contract diverges"),
    ("duplicate_fk_conflicting_on_update",
     lambda sql: _append_constraint(
         sql, "CONSTRAINT fk_dup FOREIGN KEY(shot_id) REFERENCES "
              "shots (id) ON UPDATE CASCADE ON DELETE RESTRICT"),
     None, "foreign-key contract diverges"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,transform,after,fragment", _IR01_CASES)
async def test_irf01_closed_world_schema_refusals_at_0021(
        client, tmp_path, name, transform, after, fragment):
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_0021(client, tmp_path, f"irf01-{name}")
    _rebuild(root, _SPSM, transform=transform, after=after)
    exc = await _restore_refuses(root, tmp_path, f"irf01-{name}")
    assert fragment in str(exc), (name, exc)


@pytest.mark.asyncio
@pytest.mark.parametrize("table,transform,after,fragment", [
    # predecessor-schema closed-world at the 0020 head
    ("performance_revision_sync_classifications",
     lambda sql: _append_constraint(
         sql, "CHECK (classification_schema_version = 1)"),
     None, "CHECK-contract diverges"),
    ("performance_candidate_vocal_bindings",
     None,
     "CREATE INDEX ix_pcvb_extra ON performance_candidate_vocal_"
     "bindings (sample_rate_hz)",
     "explicit-index contract diverges"),
])
async def test_irf01_closed_world_schema_refusals_at_0020(
        client, tmp_path, table, transform, after, fragment):
    world = await _bound_world(client)
    root = await _backup_0020(client, tmp_path, f"irf01x-{table}")
    _rebuild(root, table, transform=transform, after=after)
    exc = await _restore_refuses(root, tmp_path, f"irf01x-{table}")
    assert fragment in str(exc), (table, exc)


# ---------------------------------------------------------------------------
# IR-02 — one shared persisted PF-02 mapping law (live + recovery)
# ---------------------------------------------------------------------------

def _remap_mapping_row(root: Path, shot_id: str, *, mutate) -> None:
    """Coherently rewrite the stored mapping row: apply the mutation
    to every column it touches, then recompute the canonical
    mapping_json/mapping_hash from the RESULTING row so a stale-hash
    failure can never satisfy the intended law regression."""
    from soloring.domain.canonical import (
        canonical_hash, canonical_json_str)
    con = sqlite3.connect(root / "soloring.db")
    con.row_factory = sqlite3.Row
    row = dict(con.execute(
        f"SELECT * FROM {_TABLE} WHERE shot_id = ? AND position = 0",
        (shot_id,)).fetchone())
    values = mutate(row)
    doc = {
        "mapping_schema_version": 1,
        "performance_revision_id": values["performance_revision_id"],
        "performance_start_ms": {
            "num": values["performance_start_num"],
            "den": values["performance_start_den"]},
        "performance_end_ms": {
            "num": values["performance_end_num"],
            "den": values["performance_end_den"]},
        "shot_anchor_ms": {
            "num": values["shot_anchor_num"],
            "den": values["shot_anchor_den"]},
        "vocal_mapping_position": values["vocal_mapping_position"],
    }
    con.execute(
        f"UPDATE {_TABLE} SET performance_start_num = :sn, "
        "performance_start_den = :sd, performance_end_num = :en, "
        "performance_end_den = :ed, shot_anchor_num = :an, "
        "shot_anchor_den = :ad, vocal_mapping_position = :vp, "
        "mapping_json = :j, mapping_hash = :h "
        "WHERE shot_id = :s AND position = 0",
        {"sn": values["performance_start_num"],
         "sd": values["performance_start_den"],
         "en": values["performance_end_num"],
         "ed": values["performance_end_den"],
         "an": values["shot_anchor_num"],
         "ad": values["shot_anchor_den"],
         "vp": values["vocal_mapping_position"],
         "j": canonical_json_str(doc), "h": canonical_hash(doc),
         "s": shot_id})
    con.commit()
    con.close()


def _start_end(sn, en):
    def mutate(row):
        row["performance_start_num"] = sn
        row["performance_end_num"] = en
        return row
    return mutate


_IRF02_CASES = [
    ("start_equals_end", _start_end(1000, 1000),
     "empty or inverted"),
    ("start_after_end", _start_end(1500, 1000),
     "empty or inverted"),
    ("before_domain", _start_end(-500, 500),
     "outside the immutable PerformanceRevision domain"),
    ("after_domain", _start_end(50000, 60000),
     "outside the immutable PerformanceRevision domain"),
    ("straddles_domain_boundary", _start_end(-500, 500),
     "outside the immutable PerformanceRevision domain"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,mutate,fragment", _IRF02_CASES)
async def test_irf02_shared_mapping_law_interval_refusals(
        client, tmp_path, name, mutate, fragment):
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_0021(client, tmp_path, f"irf02-{name}")
    _remap_mapping_row(root, world["shot"], mutate=mutate)
    exc = await _restore_refuses(root, tmp_path, f"irf02-{name}")
    assert fragment in str(exc), (name, exc)


@pytest.mark.asyncio
@pytest.mark.parametrize("name,value,fragment", [
    ("negative_vocal_position", -1,
     "not a SQLite-safe mapping position"),
    # SQLite affinity can persist a non-integral value in the INTEGER
    # column; the shared law proves actual integral storage
    ("non_integral_vocal_position", "not-an-int",
     "not a SQLite-safe mapping position"),
])
async def test_irf02_vocal_position_storage_refusals(
        client, tmp_path, name, value, fragment):
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_0021(client, tmp_path, f"irf02v-{name}")

    def mutate(row):
        row["vocal_mapping_position"] = value
        return row
    _remap_mapping_row(root, world["shot"], mutate=mutate)
    exc = await _restore_refuses(root, tmp_path, f"irf02v-{name}")
    assert fragment in str(exc), (name, exc)


@pytest.mark.asyncio
async def test_irf02_beyond_i64_vocal_position_refuses(client, tmp_path):
    """2^63 overflows SQLite's signed-64-bit INTEGER storage and comes
    back as a REAL. Python's sqlite3 driver refuses to BIND the value
    as a parameter, so the tamper is constructed through an in-statement
    SQL literal — constructible in staged SQLite exactly as the finding
    requires — followed by the coherent doc/hash rebuild from the
    stored (REAL) row value."""
    from soloring.domain.canonical import (
        canonical_hash, canonical_json_str)
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_0021(client, tmp_path, "irf02v-beyond")
    con = sqlite3.connect(root / "soloring.db")
    con.row_factory = sqlite3.Row
    con.execute(
        f"UPDATE {_TABLE} SET vocal_mapping_position = "
        "9223372036854775808 WHERE shot_id = ? AND position = 0",
        (world["shot"],))
    row = dict(con.execute(
        f"SELECT * FROM {_TABLE} WHERE shot_id = ? AND position = 0",
        (world["shot"],)).fetchone())
    stored = row["vocal_mapping_position"]
    assert isinstance(stored, float), \
        "expected SQLite to demote 2^63 to REAL storage"
    doc = {
        "mapping_schema_version": 1,
        "performance_revision_id": row["performance_revision_id"],
        "performance_start_ms": {
            "num": row["performance_start_num"],
            "den": row["performance_start_den"]},
        "performance_end_ms": {
            "num": row["performance_end_num"],
            "den": row["performance_end_den"]},
        "shot_anchor_ms": {
            "num": row["shot_anchor_num"],
            "den": row["shot_anchor_den"]},
        "vocal_mapping_position": stored,
    }
    con.execute(
        f"UPDATE {_TABLE} SET mapping_json = ?, mapping_hash = ? "
        "WHERE shot_id = ? AND position = 0",
        (canonical_json_str(doc), canonical_hash(doc), world["shot"]))
    con.commit()
    con.close()
    exc = await _restore_refuses(root, tmp_path, "irf02v-beyond")
    assert "not a SQLite-safe mapping position" in str(exc), exc



@pytest.mark.asyncio
async def test_irf02_lawful_working_states_still_restore(client, tmp_path):
    """IR-02 explicit positives: the shared persisted law certifies
    ONLY stored structure — missing paired mapping, paired VP drift,
    stale selection, zero duration, and non-intersection are lawful
    working states that survive restore (deep versions live in the
    SR2/B-F batteries; this anchors the family against the shared-law
    refactor)."""
    from soloring.recovery import restore as rb_restore
    world = await _bound_world(client)
    await _lawful_put(client, world)
    # working drift: repoint the paired vocal mapping through the
    # supported API and zero the current duration
    alternate = await _same_line_alternate_vp(client, world)
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": alternate["id"],
              "selected_by": "irf"})
    await client.put(
        f"/shots/{world['shot']}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": alternate["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    p = await client.patch(
        f"/shots/{world['shot']}", json={"duration_ms": 0})
    assert p.status_code == 200, p.text
    root = await _backup_0021(client, tmp_path, "irf02-positive")
    dest = tmp_path / "restored-positive"
    await rb_restore(root, dest)
    con = sqlite3.connect(dest / "soloring.db")
    try:
        assert con.execute(
            f"SELECT COUNT(*) FROM {_TABLE}").fetchone()[0] == 1
        assert con.execute(
            "SELECT duration_ms FROM shots WHERE id = ?",
            (world["shot"],)).fetchone()[0] == 0
    finally:
        con.close()


# ---------------------------------------------------------------------------
# IR-03 — historical parent authority before mode interpretation
# ---------------------------------------------------------------------------

_RETARGET_BODY = {
    "assessment_id": "00000000-0000-4000-8000-00000000dead",
    "accepted_review_id": "00000000-0000-4000-8000-00000000beef",
    "producer_id": "irf-producer",
    "producer_version": "1",
}


async def _assert_none_matrix_step(client, world, tmp_path, tag):
    """Common IR-03 assertions for one corruption of a generic adopted
    NONE history: both binding GETs refuse as 500 corruption (not the
    honest NONE 404), adoption replay refuses 500, and retarget
    refuses 500 with ZERO new candidates."""
    before = (await _one(
        client,
        "SELECT COUNT(*) AS n FROM performance_candidates"))["n"]
    r = await client.get(
        f"/performance-candidates/{world['candidate']['id']}/"
        "vocal-binding")
    _corrupt(r)
    r = await client.get(
        f"/performance-revisions/{world['pr']['id']}/vocal-binding")
    _corrupt(r)
    r = await client.post(
        f"/performance-candidates/{world['candidate']['id']}/adopt",
        json={"adopted_by": "irf"})
    _corrupt(r)
    r = await client.post(
        f"/performance-revisions/{world['pr']['id']}/retarget-candidates",
        json=_RETARGET_BODY)
    _corrupt(r)
    after = (await _one(
        client,
        "SELECT COUNT(*) AS n FROM performance_candidates"))["n"]
    assert after == before, "retarget created rows"
    companions = (await _one(
        client,
        "SELECT COUNT(*) AS n FROM "
        "performance_candidate_sync_classifications"))["n"]
    assert companions == before, \
        "a new PF-03 companion appeared for an unverified source"


async def _generic_world_with_candidate(client):
    """`_generic_world` returns only shot/pr — resolve the adopted
    candidate id the corrupt matrix needs."""
    world = await _generic_world(client)
    world["candidate"] = {"id": (await _one(
        client,
        "SELECT adopted_candidate_id AS id FROM performance_revisions "
        "WHERE id = :r", {"r": world["pr"]["id"]}))["id"]}
    return world


@pytest.mark.asyncio
@pytest.mark.parametrize("name,stmt,params", [
    ("candidate payload identity",
     "UPDATE performance_candidates SET "
     "canonical_channel_payload_blob_hash = :v, "
     "canonical_channel_payload_sha256 = :v WHERE id = :c", {}),
    ("candidate provenance hash",
     "UPDATE performance_candidates SET provenance_hash = :v "
     "WHERE id = :c", {"v": "f" * 64}),
    ("candidate temporal law",
     "UPDATE performance_candidates SET temporal_end_num = 0 "
     "WHERE id = :c", {}),
    ("candidate-only copied closure field",
     "UPDATE performance_candidates SET subject_id = :v "
     "WHERE id = :c", {}),
    ("revision-only copied closure field",
     "UPDATE performance_revisions SET subject_id = :v "
     "WHERE id = :r", {}),
    ("revision adoption metadata",
     "UPDATE performance_revisions SET adoption_id = 'not-a-uuid' "
     "WHERE id = :r", {}),
])
async def test_irf03_generic_none_history_corruption_matrix(
        client, tmp_path, name, stmt, params):
    from tests.m17b_seed import make_entity
    world = await _generic_world_with_candidate(client)
    vp_audio_hash = (await _one(
        client,
        "SELECT retained_audio_blob_hash FROM "
        "vocal_performance_revisions WHERE id = :v",
        {"v": world["vp"]["id"]}))["retained_audio_blob_hash"]
    other_entity = await make_entity(
        client, world["project_id"], "IRFEntity")
    full_params = {"c": world["candidate"]["id"],
                   "r": world["pr"]["id"],
                   "v": other_entity if "subject" in stmt
                   else vp_audio_hash}
    full_params.update(params)
    await _sql(client, stmt, full_params)
    await _assert_none_matrix_step(client, world, tmp_path, name)


@pytest.mark.asyncio
async def test_irf03_lawful_none_history_keeps_honest_404(client):
    """Lawful untouched generic adopted history: the binding GETs
    return the honest binding-not-found 404 (historical authority
    proven, mode NONE interpreted)."""
    world = await _generic_world_with_candidate(client)
    r = await client.get(
        f"/performance-candidates/{world['candidate']['id']}/"
        "vocal-binding")
    assert r.status_code == 404, r.text
    assert r.json()["error_code"] == "PERFORMANCE_VOCAL_BINDING_NOT_FOUND"
    r = await client.get(
        f"/performance-revisions/{world['pr']['id']}/vocal-binding")
    assert r.status_code == 404, r.text
    assert r.json()["error_code"] == "PERFORMANCE_VOCAL_BINDING_NOT_FOUND"


# ---------------------------------------------------------------------------
# IR-04 — complete adopted-pair closure on candidate binding reads
# ---------------------------------------------------------------------------

def _rehash_binding(root: Path, table: str, key_col: str, key: str,
                    *, column: str, value) -> None:
    """Coherently rewrite ONE binding row column + canonical json/hash
    so the pair-law regression cannot be satisfied by hash failure."""
    from soloring.domain.canonical import (
        canonical_hash, canonical_json_str)
    con = sqlite3.connect(root / "soloring.db")
    con.row_factory = sqlite3.Row
    row = con.execute(
        f"SELECT * FROM {table} WHERE {key_col} = ?", (key,)).fetchone()
    values = dict(row)
    values[column] = value
    doc = {
        "binding_schema_version": values["binding_schema_version"],
        "synchronization_basis_version":
            values["synchronization_basis_version"],
        "vocal_performance_revision_id":
            values["vocal_performance_revision_id"],
        "source_start_sample": values["source_start_sample"],
        "source_end_sample_exclusive":
            values["source_end_sample_exclusive"],
        "sample_rate_hz": values["sample_rate_hz"],
        "performance_origin_ms": {
            "num": values["performance_origin_num"],
            "den": values["performance_origin_den"]},
    }
    con.execute(
        f"UPDATE {table} SET {column} = :v, binding_json = :j, "
        f"binding_hash = :h WHERE {key_col} = :k",
        {"v": value, "j": canonical_json_str(doc),
         "h": canonical_hash(doc), "k": key})
    con.commit()
    con.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("side,column,value,fragment", [
    # one-sided binding divergence with coherent rehash on the changed
    # side only — the pair equality law must fire, not hash failure
    ("revision", "source_start_sample", 44100,
     "binding != adopted candidate binding closure"),
    ("candidate", "source_start_sample", 44100,
     "binding != adopted candidate binding closure"),
])
async def test_irf04_asymmetric_binding_divergence(client, tmp_path,
                                                   side, column, value,
                                                   fragment):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    await _lawful_put(client, world)
    if side == "revision":
        table, key_col, key = ("performance_revision_vocal_bindings",
                               "performance_revision_id",
                               world["pr"]["id"])
    else:
        table, key_col, key = ("performance_candidate_vocal_bindings",
                               "performance_candidate_id",
                               world["candidate"]["id"])
    # corrupt LIVE (coherent rehash in the live DB) so every live
    # surface refuses, then prove recovery agrees
    _rehash_binding(_live_root(client), table, key_col, key,
                    column=column, value=value)
    _corrupt(await client.get(
        f"/performance-candidates/{world['candidate']['id']}/"
        "vocal-binding"))
    _corrupt(await client.get(
        f"/performance-revisions/{world['pr']['id']}/vocal-binding"))
    _corrupt(await client.get(
        f"/shots/{world['shot']}/performance-readiness"))
    with pytest.raises(SoloRingError) as excinfo:
        await _backup_m17c(client, tmp_path, "irf04-binding")
    assert excinfo.value.code == "RECOVERY_CORRUPTION"
    assert fragment in str(excinfo.value), excinfo.value


def _live_root(client):
    """A Path view of the live test data dir for sqlite3 surgery."""
    return Path(client._transport.app.state.settings.data_dir)


@pytest.mark.asyncio
@pytest.mark.parametrize("side,stmt,fragment", [
    ("revision",
     "UPDATE performance_revisions SET subject_id = :v "
     "WHERE id = :r",
     "closure does not reproduce"),
    ("candidate",
     "UPDATE performance_candidates SET subject_id = :v "
     "WHERE id = :c",
     "closure does not reproduce"),
])
async def test_irf04_asymmetric_copied_field_divergence(
        client, tmp_path, side, stmt, fragment):
    from tests.m17b_seed import make_entity
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    await _lawful_put(client, world)
    other = await make_entity(client, world["project_id"], "IRF4")
    await _sql(client, stmt, {"v": other,
                              "r": world["pr"]["id"],
                              "c": world["candidate"]["id"]})
    _corrupt(await client.get(
        f"/performance-candidates/{world['candidate']['id']}/"
        "vocal-binding"))
    _corrupt(await client.get(
        f"/performance-revisions/{world['pr']['id']}/vocal-binding"))
    _corrupt(await client.get(
        f"/shots/{world['shot']}/performance-readiness"))
    with pytest.raises(SoloRingError) as excinfo:
        await _backup_m17c(client, tmp_path, "irf04-closure")
    assert excinfo.value.code == "RECOVERY_CORRUPTION"
    # recovery layering (IR-06 recorded): the M17B revision verifier's
    # copied-closure law is the intended predecessor branch that fires
    # first for a copied-field divergence
    assert "closure diverges" in str(excinfo.value) or \
        fragment in str(excinfo.value), excinfo.value


# ---------------------------------------------------------------------------
# IR-05 — missing retained payload bytes are structured failures
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_irf05_missing_payload_file_structured_500(client, tmp_path):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    await _lawful_put(client, world)
    settings = client._transport.app.state.settings
    blob_hash = (await _one(
        client,
        "SELECT canonical_channel_payload_blob_hash FROM "
        "performance_candidates WHERE id = :c",
        {"c": world["candidate"]["id"]}))[
        "canonical_channel_payload_blob_hash"]
    payload_path = (settings.blob_dir / "sha256" / blob_hash[:2]
                    / blob_hash[2:4] / blob_hash)
    assert payload_path.is_file()
    payload_path.unlink()  # delete ONLY the physical file; keep the row

    # every authority surface: stable 500 corruption envelope — the
    # structured BLOB_BYTES_MISSING is translated by the historical seam
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/1",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    _corrupt(r)
    assert "missing from storage" in r.json()["message"], r.text
    rows = await _one(
        client,
        f"SELECT COUNT(*) AS n FROM {_TABLE} WHERE shot_id = :s",
        {"s": world["shot"]})
    assert rows["n"] == 1
    for path in (f"/shots/{world['shot']}/performance-readiness",
                 f"/shots/{world['shot']}/performance-segments",
                 f"/performance-candidates/{world['candidate']['id']}/"
                 "vocal-binding",
                 f"/performance-revisions/{world['pr']['id']}/"
                 "vocal-binding"):
        got = await client.get(path)
        _corrupt(got)
        assert "missing from storage" in got.json()["message"], path
    r = await client.post(
        f"/performance-candidates/{world['candidate']['id']}/adopt",
        json={"adopted_by": "irf"})
    _corrupt(r)
    r = await client.post(
        f"/performance-revisions/{world['pr']['id']}/retarget-candidates",
        json=_RETARGET_BODY)
    _corrupt(r)
    after = (await _one(
        client,
        "SELECT COUNT(*) AS n FROM performance_candidates"))["n"]
    assert after == 1, "retarget created rows"
    # recovery refuses through its stable recovery-corruption contract
    # (the M17B verifier's blob-read branch — the intended branch)
    with pytest.raises(SoloRingError) as excinfo:
        await _backup_m17c(client, tmp_path, "irf05")
    assert excinfo.value.code == "RECOVERY_CORRUPTION"
    assert "missing from Blob root" in str(excinfo.value), excinfo.value
