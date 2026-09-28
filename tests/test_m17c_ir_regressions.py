"""M17C-B IR corrective regressions (IR-01..IR-04, frozen under the
PR #26 protocol cycle of 2026-09-28 evening; product base a5f9d2d).

- IR-01: the 0021 physical-schema certification is EXACT — declared
  types, full FK contract, non-unique/non-partial CREATE-INDEX origin,
  and CHECK name+semantic-expression pairs (a right-named CHECK(1) is
  refused); six surgical DDL refusals + the malformed-table case
  retained in the SR2 battery.
- IR-02: the four frozen-0020 PF-03 tables are physically certified at
  BOTH heads (0021 inherits 0020 and does not weaken it); schema runs
  BEFORE row traversal with corruption translation; 4x5 weakening
  matrix at 0020 plus representative predecessor-schema tampering at
  claimed 0021.
- IR-03: ONE shared persisted-history candidate-integrity seam; the
  candidate-side tamper matrix (revision untouched) refuses PF-02 PUT
  (500, zero rows), readiness/list (500), both binding GETs (500), and
  recovery — while FRESH candidate creation keeps the admission 4xx.
- IR-04: ONE SQLite-safe position domain shared by BOTH mapping
  services (PUT and DELETE), validated before any ORM/SQLite access.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.test_m17c_binding_transitions import _same_line_alternate_vp
from tests.test_m17c_shot_mapping import (
    _bound_world,
    _generic_world,
    _seg_body,
)

_TABLE = "shot_performance_segment_mappings"
_LIMIT = 2 ** 63 - 1


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


def _rebuild(root: Path, table: str, transform=None, after=None) -> None:
    """DDL surgery on a staged backup: read the stored CREATE TABLE,
    optionally transform its text, drop + recreate the table (rows are
    immaterial to the schema contract), and optionally execute extra
    statements (index reshaping)."""
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
    from tests.test_m17c_sr26_regressions import _backup_m17c
    from tests.test_m17c_sr2_regressions import _retarget_backup
    root = await _backup_m17c(client, tmp_path, tag + "-src")
    _retarget_backup(root, M17C_A_ALEMBIC_HEAD, drop_pf02=True)
    return root


# ---------------------------------------------------------------------------
# IR-01 — exact 0021 physical-schema certification
# ---------------------------------------------------------------------------

_IR01_CASES = [
    ("check1_position",
     lambda sql: sql.replace("CHECK (position >= 0)", "CHECK (1)"),
     None, "CHECK-contract diverges"),
    ("check1_denominator",
     lambda sql: sql.replace("CHECK (performance_start_den > 0)",
                             "CHECK (1)"),
     None, "CHECK-contract diverges"),
    ("unique_index_replacement",
     None,
     f"CREATE UNIQUE INDEX ix_spsm_pr ON {_TABLE} "
     "(performance_revision_id)",
     "index contract diverges"),
    ("partial_index_replacement",
     None,
     f"CREATE INDEX ix_spsm_pr ON {_TABLE} "
     "(performance_revision_id) WHERE position >= 0",
     "index contract diverges"),
    ("integer_column_to_text",
     lambda sql: sql.replace("position INTEGER NOT NULL",
                             "position TEXT NOT NULL"),
     None, "column contract diverges"),
    ("varchar_column_materially_wrong",
     lambda sql: sql.replace("shot_id VARCHAR(36) NOT NULL",
                             "shot_id VARCHAR(64) NOT NULL"),
     None, "column contract diverges"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,transform,after,fragment", _IR01_CASES)
async def test_ir01_exact_spsm_schema_refusals(
        client, tmp_path, name, transform, after, fragment):
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_0021(client, tmp_path, f"ir01-{name}")
    _rebuild(root, _TABLE, transform=transform, after=after)
    exc = await _restore_refuses(root, tmp_path, f"ir01-{name}")
    assert fragment in str(exc), (name, exc)


# ---------------------------------------------------------------------------
# IR-02 — frozen 0020 PF-03 schema certification at BOTH heads
# ---------------------------------------------------------------------------

def _check1(sql: str) -> str:
    """Replace the FIRST CHECK expression with (1), preserving the
    constraint name — balanced-paren + quote-aware so nested
    expressions like IN ('NONE', 'VOCAL_V1') survive the edit."""
    c = sql.upper().find("CHECK")
    p = sql.find("(", c)
    depth = 0
    in_string = False
    j = p
    while j < len(sql):
        ch = sql[j]
        if in_string:
            if ch == "'":
                in_string = False
        elif ch == "'":
            in_string = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return sql[:p + 1] + "1" + sql[j:]


def _missing_fk(sql: str) -> str:
    return re.sub(
        r",\s*\n\s*CONSTRAINT fk_\w+ FOREIGN KEY\([^)]*\) "
        r"REFERENCES \w+ \([^)]*\) ON DELETE RESTRICT", "", sql)


def _wrong_type(sql: str) -> str:
    return sql.replace("INTEGER NOT NULL", "TEXT NOT NULL", 1)


def _wrong_pk(sql: str) -> str:
    return re.sub(
        r",\s*\n\s*CONSTRAINT pk_\w+ PRIMARY KEY \([^)]*\)", "", sql)


def _missing_column(sql: str) -> str:
    return re.sub(r",\s*\n\s*created_at TEXT NOT NULL", "", sql)


_IR02_WEAKENINGS = {
    "check1": (_check1, "CHECK-contract diverges"),
    "missing_fk": (_missing_fk, "foreign-key contract diverges"),
    "wrong_type": (_wrong_type, "column contract diverges"),
    "wrong_pk": (_wrong_pk, "column contract diverges"),
    "missing_column": (_missing_column, "column contract diverges"),
}

_PF03_TABLES = (
    "performance_candidate_vocal_bindings",
    "performance_revision_vocal_bindings",
    "performance_candidate_sync_classifications",
    "performance_revision_sync_classifications",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("table", _PF03_TABLES)
@pytest.mark.parametrize("weakening", list(_IR02_WEAKENINGS))
async def test_ir02_pf03_schema_weakening_matrix_at_0020(
        client, tmp_path, table, weakening):
    world = await _bound_world(client)
    root = await _backup_0020(client, tmp_path, f"ir02-{table}-{weakening}")
    transform, fragment = _IR02_WEAKENINGS[weakening]
    _rebuild(root, table, transform=transform)
    exc = await _restore_refuses(
        root, tmp_path, f"ir02-{table}-{weakening}")
    assert fragment in str(exc), (table, weakening, exc)


@pytest.mark.asyncio
@pytest.mark.parametrize("table,weakening", [
    ("performance_revision_sync_classifications", "check1"),
    ("performance_candidate_vocal_bindings", "missing_fk"),
])
async def test_ir02_predecessor_schema_tampering_at_0021(
        client, tmp_path, table, weakening):
    """Head 0021 inherits the frozen 0020 schemas physically — the
    successor verifies them too."""
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_0021(client, tmp_path, f"ir02x-{table}")
    transform, fragment = _IR02_WEAKENINGS[weakening]
    _rebuild(root, table, transform=transform)
    exc = await _restore_refuses(root, tmp_path, f"ir02x-{table}")
    assert fragment in str(exc), (table, weakening, exc)


@pytest.mark.asyncio
async def test_ir02_clean_0020_and_0021_restore_paths_preserved(client,
                                                                 tmp_path):
    """The four SR2 restore behaviors are preserved (IR-02 explicit
    requirement): genuine 0020 restores; genuine 0021 restores; 0020
    rejects the successor-only PF-02 table; 0021 requires the exact
    PF-02 table (the SR2 battery owns the deep versions; this anchors
    the pair against verifier-refactor regressions)."""
    from soloring.recovery import restore as rb_restore
    from soloring.recovery.backup import M17C_A_ALEMBIC_HEAD
    from tests.test_m17c_sr2_regressions import _retarget_backup
    world = await _bound_world(client)
    await _lawful_put(client, world)

    root20 = await _backup_0021(client, tmp_path, "ir02-clean20")
    _retarget_backup(root20, M17C_A_ALEMBIC_HEAD, drop_pf02=True)
    dest20 = tmp_path / "restored-20"
    await rb_restore(root20, dest20)
    con = sqlite3.connect(dest20 / "soloring.db")
    assert con.execute(
        "SELECT version_num FROM alembic_version").fetchone()[0] \
        == M17C_A_ALEMBIC_HEAD
    con.close()

    root21 = await _backup_0021(client, tmp_path, "ir02-clean21")
    dest21 = tmp_path / "restored-21"
    await rb_restore(root21, dest21)
    con = sqlite3.connect(dest21 / "soloring.db")
    assert con.execute(
        "SELECT COUNT(*) FROM " + _TABLE).fetchone()[0] == 1
    con.close()


# ---------------------------------------------------------------------------
# IR-03 — shared persisted-history candidate-integrity seam
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("name,stmt_builder,needs_alternate", [
    ("payload dual-hash disagreement",
     lambda w, extra: (
         "UPDATE performance_candidates SET "
         "canonical_channel_payload_sha256 = :v WHERE id = :c",
         {"v": "a" * 64, "c": w["candidate"]["id"]}), False),
    ("payload identity coherent real-blob swap",
     lambda w, extra: (
         "UPDATE performance_candidates SET "
         "canonical_channel_payload_blob_hash = :v, "
         "canonical_channel_payload_sha256 = :v WHERE id = :c",
         {"v": extra, "c": w["candidate"]["id"]}), False),
    ("provenance hash",
     lambda w, extra: (
         "UPDATE performance_candidates SET provenance_hash = :v "
         "WHERE id = :c", {"v": "f" * 64, "c": w["candidate"]["id"]}),
     False),
    ("provenance json canonicality",
     lambda w, extra: (
         "UPDATE performance_candidates SET provenance_json = '{}' "
         "WHERE id = :c", {"c": w["candidate"]["id"]}), False),
    ("temporal domain law",
     lambda w, extra: (
         "UPDATE performance_candidates SET temporal_end_num = 0 "
         "WHERE id = :c", {"c": w["candidate"]["id"]}), False),
    ("subject disagreement",
     lambda w, extra: (
         "UPDATE performance_candidates SET subject_id = :v "
         "WHERE id = :c", {"v": extra, "c": w["candidate"]["id"]}),
     True),
])
async def test_ir03_candidate_tamper_matrix(
        client, tmp_path, name, stmt_builder, needs_alternate):
    from tests.m17b_seed import make_entity
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    await _lawful_put(client, world)
    vp_audio_hash = (await _one(
        client,
        "SELECT retained_audio_blob_hash FROM "
        "vocal_performance_revisions WHERE id = :v",
        {"v": world["vp"]["id"]}))["retained_audio_blob_hash"]
    other_entity = await make_entity(
        client, world["project_id"], "IREntity")
    stmt, params = stmt_builder(
        world, other_entity if needs_alternate else vp_audio_hash)
    # the revision stays untouched — only the adopted candidate is
    # corrupted, so every refusal must come from the candidate laws
    await _sql(client, stmt, params)

    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/1",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    _corrupt(r)
    rows = await _one(
        client,
        f"SELECT COUNT(*) AS n FROM {_TABLE} WHERE shot_id = :s",
        {"s": world["shot"]})
    assert rows["n"] == 1
    for path in (f"/shots/{world['shot']}/performance-readiness",
                 f"/shots/{world['shot']}/performance-segments"):
        _corrupt(await client.get(path))
    got = await client.get(
        f"/performance-candidates/{world['candidate']['id']}/"
        "vocal-binding")
    _corrupt(got)
    got = await client.get(
        f"/performance-revisions/{world['pr']['id']}/vocal-binding")
    _corrupt(got)
    # recovery agrees: the backup-side enumeration runs the same
    # candidate core and refuses the corrupted row (the refusal itself
    # is the verdict; the firing law varies per tamper)
    with pytest.raises(Exception):
        await _backup_m17c(client, tmp_path, "ir03")


@pytest.mark.asyncio
async def test_ir03_fresh_admission_keeps_4xx(client):
    """Fresh candidate creation never inherits the historical 500
    contract — both admission layers keep their 4xx: the closed-schema
    layer (unknown key) and the semantic binding-grammar layer
    (inverted sample interval)."""
    from tests.m17c_seed import ARTICULATION, dialogue_bound_body
    world = await _bound_world(client)
    body = dialogue_bound_body(
        world["vp"]["id"],
        articulation_time={key: (600, 1) for key in ARTICULATION})
    bad_keys = dict(body)
    bad_keys["vocal_binding"] = {"unexpected_key": True}
    r = await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates", json=bad_keys)
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == "VALIDATION_ERROR"

    bad_interval = dict(body)
    bad_interval["vocal_binding"] = {
        "vocal_performance_revision_id": world["vp"]["id"],
        "source_start_sample": 5,
        "source_end_sample_exclusive": 5,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 0, "den": 1},
    }
    r = await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates", json=bad_interval)
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == "PERFORMANCE_VOCAL_INTERVAL_INVALID"


# ---------------------------------------------------------------------------
# IR-04 — one shared position domain across BOTH mapping services
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ir04_m17a_vocal_put_position_domain(client):
    world = await _bound_world(client)
    body = {
        "vocal_performance_revision_id": world["vp"]["id"],
        "source_start_sample": 48000,
        "source_end_sample_exclusive": 96000,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 0, "den": 1},
        "shot_anchor_ms": {"num": 0, "den": 1},
    }
    for bad in (-1, 2 ** 63):
        r = await client.put(
            f"/shots/{world['shot']}/vocal-segments/{bad}", json=body)
        assert r.status_code == 422, r.text
        assert r.json()["error_code"] == "INVALID_SAMPLE_INTERVAL"
    # 2^63-1 is DB-safe: a lawful PUT at the domain edge succeeds
    r = await client.put(
        f"/shots/{world['shot']}/vocal-segments/{_LIMIT}", json=body)
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_ir04_m17a_vocal_delete_position_domain(client):
    world = await _bound_world(client)
    for bad in (-1, 2 ** 63):
        r = await client.delete(
            f"/shots/{world['shot']}/vocal-segments/{bad}")
        assert r.status_code == 422, r.text
        assert r.json()["error_code"] == "INVALID_SAMPLE_INTERVAL"
    # 2^63-1 is DB-safe and idempotent on DELETE
    for _ in range(2):
        r = await client.delete(
            f"/shots/{world['shot']}/vocal-segments/{_LIMIT}")
        assert r.status_code == 204, r.text


@pytest.mark.asyncio
async def test_ir04_direct_service_bool_rejected():
    """The shared primitive rejects bool BEFORE any session/ORM use
    (session=None proves no ORM access precedes the law)."""
    from soloring.errors import SoloRingError
    from soloring.performance import mapping as m17a_mapping
    from soloring.performance.m17c_shot_mapping import _validate_position
    from soloring.performance.temporal import (
        PositionError, validate_mapping_position)
    for bad in (True, False):
        with pytest.raises(PositionError):
            validate_mapping_position(bad)
        with pytest.raises(SoloRingError) as excinfo:
            await m17a_mapping.put_shot_vocal_segment_mapping(
                None, shot_id="s", position=bad,
                vocal_performance_revision_id="v",
                source_start_sample=0, source_end_sample_exclusive=1,
                sample_rate_hz=48000,
                performance_origin_num=0, performance_origin_den=1,
                shot_anchor_num=0, shot_anchor_den=1)
        assert excinfo.value.status_code == 422
        with pytest.raises(SoloRingError) as excinfo:
            await m17a_mapping.delete_shot_vocal_segment_mapping(
                None, shot_id="s", position=bad)
        assert excinfo.value.status_code == 422
        with pytest.raises(SoloRingError) as excinfo:
            _validate_position(bad)
        assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_ir04_pf02_bound_tests_regression(client):
    """The PF-02 position-domain behavior is unchanged by the shared
    primitive (SR2-09 contract re-proven)."""
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, 0))
    assert r.status_code == 200, r.text
    for bad in (-1, 2 ** 63):
        d = await client.delete(
            f"/shots/{world['shot']}/performance-segments/{bad}")
        assert d.status_code == 422, d.text
        assert d.json()["error_code"] == \
            "PERFORMANCE_SHOT_MAPPING_INVALID"
    for _ in range(2):
        d = await client.delete(
            f"/shots/{world['shot']}/performance-segments/{_LIMIT}")
        assert d.status_code == 204, d.text
