"""M17C-B IND corrective regressions (IND-01..04, frozen under the
PR #26 protocol cycle of 2026-09-29; product base f84e6f9).

- IND-01: exact rational PF-02 interval ordering — 3/4 -> 1/1 is
  lawful end-to-end; 1/2 -> 2/5 is INVERTED and refuses live reads and
  recovery even with a coherent canonical rehash (denominator-
  sensitive values, never denominator-1 stand-ins).
- IND-02: UNIQUE-constraint autoindexes are certified — an unexpected
  origin-'u' index (anonymous UNIQUE or a named CONSTRAINT ... UNIQUE)
  refuses at the physical-schema phase on a frozen-0020 PF-03 table
  and the successor-0021 PF-02 table; the expected PK autoindex is
  proven to index exactly the frozen PK columns.
- IND-03: the ONE shared historical retarget-evidence verifier runs
  BEFORE any candidate is constructed — a 13-shape corruption matrix
  on a generic NONE source (plus a dialogue-bound spot-check) refuses
  creation with the historical 500, the targeted diagnostic, and ZERO
  new candidates/classifications/bindings; lawful creation unchanged.
- IND-04: M17B recovery error normalization — PermissionError /
  representative OSError during the blob read (monkeypatched at the
  recovery seam, cross-platform) and malformed persisted provenance
  JSON all refuse through the stable recovery-corruption contract
  with branch-specific diagnostics.
"""

from __future__ import annotations

import pathlib
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.errors import SoloRingError
from tests.test_m17c_shot_mapping import (
    _bound_world,
    _generic_world,
    _seg_body,
)

_TABLE = "shot_performance_segment_mappings"


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


async def _backup_0021(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, tag)


async def _backup_0020(client, tmp_path, tag):
    from soloring.recovery.backup import M17C_A_ALEMBIC_HEAD
    from tests.test_m17c_sr2_regressions import _retarget_backup
    root = await _backup_0021(client, tmp_path, tag + "-src")
    _retarget_backup(root, M17C_A_ALEMBIC_HEAD, drop_pf02=True)
    return root


def _blob_path_for(root, blob_hash: str) -> Path:
    return (root / "blobs" / "sha256" / blob_hash[:2]
            / blob_hash[2:4] / blob_hash)


async def _restore_refuses(backup_root, tmp_path, tag):
    from tests.test_m17c_sr2_regressions import (
        _restore_refuses as sr2_refuses)
    return await sr2_refuses(backup_root, tmp_path, tag)


def _rebuild(root: Path, table: str, transform=None, after=None) -> None:
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


def _remap_mapping_row(root: Path, shot_id: str, *, mutate) -> None:
    """Coherently rewrite the stored mapping row with the canonical
    json/hash recomputed from the RESULTING row — a stale-hash failure
    can never satisfy the intended ordering regression."""
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
        "performance_end_den = :ed, mapping_json = :j, mapping_hash = :h "
        "WHERE shot_id = :s AND position = 0",
        {"sn": values["performance_start_num"],
         "sd": values["performance_start_den"],
         "en": values["performance_end_num"],
         "ed": values["performance_end_den"],
         "j": canonical_json_str(doc), "h": canonical_hash(doc),
         "s": shot_id})
    con.commit()
    con.close()


async def _coherent_live_remap(client, shot_id: str, *, sn, sd, en, ed):
    """Same coherent remap on the LIVE database (recompute json/hash
    from the resulting values) so live reads exercise the exact law."""
    from soloring.domain.canonical import (
        canonical_hash, canonical_json_str)
    row = await _one(
        client,
        f"SELECT * FROM {_TABLE} WHERE shot_id = :s AND position = 0",
        {"s": shot_id})
    doc = {
        "mapping_schema_version": 1,
        "performance_revision_id": row["performance_revision_id"],
        "performance_start_ms": {"num": sn, "den": sd},
        "performance_end_ms": {"num": en, "den": ed},
        "shot_anchor_ms": {"num": row["shot_anchor_num"],
                           "den": row["shot_anchor_den"]},
        "vocal_mapping_position": row["vocal_mapping_position"],
    }
    await _sql(
        client,
        f"UPDATE {_TABLE} SET performance_start_num = :sn, "
        "performance_start_den = :sd, performance_end_num = :en, "
        "performance_end_den = :ed, mapping_json = :j, "
        "mapping_hash = :h WHERE shot_id = :s AND position = 0",
        {"sn": sn, "sd": sd, "en": en, "ed": ed,
         "j": canonical_json_str(doc), "h": canonical_hash(doc),
         "s": shot_id})


# ---------------------------------------------------------------------------
# IND-01 — exact rational interval ordering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ind01_three_quarts_to_one_lawful_end_to_end(
        client, tmp_path):
    """3/4 -> 1/1 (0.75 < 1) is lawful with REAL denominators: live
    PUT/list/readiness accept it and it survives backup/restore."""
    from soloring.recovery import restore as rb_restore
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, 0))
    assert r.status_code == 200, r.text
    # replace with the denominator-sensitive lawful interval 3/4 -> 1/1
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json={"performance_revision_id": world["pr"]["id"],
              "performance_start_ms": {"num": 3, "den": 4},
              "performance_end_ms": {"num": 1, "den": 1},
              "shot_anchor_ms": {"num": 0, "den": 1},
              "vocal_mapping_position": None})
    assert r.status_code == 200, r.text
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True
    seg = readiness["segments"][0]
    assert seg["performance_start_ms"] == {"num": 3, "den": 4}
    assert seg["performance_end_ms"] == {"num": 1, "den": 1}
    rows = (await client.get(
        f"/shots/{world['shot']}/performance-segments")).json()
    assert rows[0]["performance_start_ms"] == {"num": 3, "den": 4}
    root = await _backup_0021(client, tmp_path, "ind01-pos")
    dest = tmp_path / "restored-pos"
    await rb_restore(root, dest)
    con = sqlite3.connect(dest / "soloring.db")
    try:
        row = con.execute(
            f"SELECT performance_start_num, performance_start_den, "
            f"performance_end_num, performance_end_den FROM {_TABLE}"
        ).fetchone()
        assert row == (3, 4, 1, 1)
    finally:
        con.close()


@pytest.mark.asyncio
async def test_ind01_one_half_to_two_fifths_inverted_refuses_live(
        client):
    """1/2 -> 2/5 (0.5 > 0.4) is INVERTED: the live PUT admission law
    refuses it (exact Fractions, numerator-only logic would pass since
    1 < 2)."""
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json={"performance_revision_id": world["pr"]["id"],
              "performance_start_ms": {"num": 1, "den": 2},
              "performance_end_ms": {"num": 2, "den": 5},
              "shot_anchor_ms": {"num": 0, "den": 1},
              "vocal_mapping_position": None})
    assert r.status_code == 422, r.text
    assert "empty or inverted" in r.json()["message"], r.text


@pytest.mark.asyncio
async def test_ind01_one_half_to_two_fifths_persisted_refuses_everywhere(
        client, tmp_path):
    """The persisted 1/2 -> 2/5 row (coherently rehashed so hash
    failure cannot satisfy the regression) refuses live list/readiness
    AND recovery through the shared persisted law."""
    world = await _generic_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, 0))
    assert r.status_code == 200, r.text
    # back up the LAWFUL state first (the backup enumeration runs
    # the verifier chain on the source and would refuse the tamper)
    root = await _backup_0021(client, tmp_path, "ind01-neg")
    await _coherent_live_remap(client, world["shot"],
                               sn=1, sd=2, en=2, ed=5)
    for path in (f"/shots/{world['shot']}/performance-readiness",
                 f"/shots/{world['shot']}/performance-segments"):
        got = await client.get(path)
        _corrupt(got)
        assert "empty or inverted" in got.json()["message"], path
    _remap_mapping_row(
        root, world["shot"],
        mutate=lambda row: {**row, "performance_start_num": 1,
                            "performance_start_den": 2,
                            "performance_end_num": 2,
                            "performance_end_den": 5})
    exc = await _restore_refuses(root, tmp_path, "ind01-neg")
    assert "empty or inverted" in str(exc), exc


# ---------------------------------------------------------------------------
# IND-02 — UNIQUE-constraint autoindex certification
# ---------------------------------------------------------------------------

def _append_constraint(sql: str, clause: str) -> str:
    return sql.rstrip()[:-1].rstrip().rstrip(",") + ", \n\t" + clause \
        + "\n)"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,clause", [
    ("anonymous_unique", "UNIQUE (sample_rate_hz)"),
    ("named_unique", "CONSTRAINT uq_extra UNIQUE (sample_rate_hz)"),
])
async def test_ind02_unexpected_unique_refuses_at_0020(
        client, tmp_path, kind, clause):
    """An unexpected origin-'u' autoindex on a frozen-0020 PF-03 table
    refuses in the physical-schema phase (before row semantics) on an
    otherwise exact EMPTY schema."""
    world = await _bound_world(client)
    root = await _backup_0020(client, tmp_path, f"ind02-{kind}")
    _rebuild(
        root, "performance_candidate_vocal_bindings",
        transform=lambda sql: _append_constraint(sql, clause))
    exc = await _restore_refuses(root, tmp_path, f"ind02-{kind}")
    assert "unexpected UNIQUE-constraint autoindexes" in str(exc), exc


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,clause", [
    ("anonymous_unique", "UNIQUE (position)"),
    ("named_unique", "CONSTRAINT uq_extra UNIQUE (position)"),
])
async def test_ind02_unexpected_unique_refuses_at_0021(
        client, tmp_path, kind, clause):
    """Same law on the successor-0021 PF-02 table."""
    world = await _bound_world(client)
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text
    root = await _backup_0021(client, tmp_path, f"ind02x-{kind}")
    _rebuild(
        root, _TABLE,
        transform=lambda sql: _append_constraint(sql, clause),
        after=f"CREATE INDEX ix_spsm_pr ON {_TABLE} "
              "(performance_revision_id)")
    exc = await _restore_refuses(root, tmp_path, f"ind02x-{kind}")
    assert "unexpected UNIQUE-constraint autoindexes" in str(exc), exc


# ---------------------------------------------------------------------------
# IND-03 — shared historical retarget-evidence verifier BEFORE creation
# ---------------------------------------------------------------------------

async def _retarget_fixture(client, *, dialogue_bound=False):
    """A lawful generic (or dialogue-bound) NONE/VOCAL source with a
    REQUIRES_REVIEW assessment and an ACCEPT review."""
    from tests.m17b_seed import (make_entity, make_project,
                                 seed_production_object,
                                 seed_production_revision)
    if dialogue_bound:
        world = await _bound_world(client)
    else:
        world = await _generic_world(client)
        world["candidate"] = {"id": (await _one(
            client,
            "SELECT adopted_candidate_id AS id FROM "
            "performance_revisions WHERE id = :r",
            {"r": world["pr"]["id"]}))["id"]}
    obj = await seed_production_object(
        client, world["project_id"], "IND obj", b"ind")
    p1 = await seed_production_revision(client, obj, b"ind-1", 1)
    p2 = await seed_production_revision(client, obj, b"ind-2", 2)
    a = (await client.post(
        f"/performance-revisions/{world['pr']['id']}/"
        "retarget-assessments",
        json={"from_production_revision_id":
              p1["production_revision_id"],
              "to_production_revision_id":
              p2["production_revision_id"]})).json()
    acc = (await client.post(
        f"/performance-retarget-assessments/{a['id']}/reviews",
        json={"decision": "ACCEPT_FOR_NEW_CANDIDATE",
              "reviewed_by": "ind", "rationale": None})).json()
    world["assessment"] = a
    world["accept"] = acc
    return world


async def _counts(client):
    cands = (await _one(
        client, "SELECT COUNT(*) AS n FROM performance_candidates"))["n"]
    cls = (await _one(
        client,
        "SELECT COUNT(*) AS n FROM "
        "performance_candidate_sync_classifications"))["n"]
    binds = (await _one(
        client,
        "SELECT COUNT(*) AS n FROM "
        "performance_candidate_vocal_bindings"))["n"]
    return cands, cls, binds


async def _retarget_post(client, world):
    return await client.post(
        f"/performance-revisions/{world['pr']['id']}/"
        "retarget-candidates",
        json={"assessment_id": world["assessment"]["id"],
              "accepted_review_id": world["accept"]["id"],
              "producer_id": "ind", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})


@pytest.mark.asyncio
@pytest.mark.parametrize("name,stmt,params,fragment", [
    ("assessment project",
     "UPDATE performance_retarget_assessments SET project_id = :v "
     "WHERE id = :a", {"v": None},
     "assessment project != performance revision project"),
    ("duplicated from snapshot hash",
     "UPDATE performance_retarget_assessments SET "
     "from_production_revision_hash = :v WHERE id = :a",
     {"v": "1" * 64}, "snapshot-hash"),
    ("duplicated to snapshot hash",
     "UPDATE performance_retarget_assessments SET "
     "to_production_revision_hash = :v WHERE id = :a",
     {"v": "2" * 64}, "snapshot-hash"),
    ("scope json (coherent hash)",
     "UPDATE performance_retarget_assessments SET scope_json = :v "
     "WHERE id = :a", {"v": None},
     "scope does not recompute"),
    ("scope hash",
     "UPDATE performance_retarget_assessments SET scope_hash = :v "
     "WHERE id = :a", {"v": "3" * 64},
     "scope does not recompute"),
    ("report json (coherent hash)",
     "UPDATE performance_retarget_assessments SET report_json = :v "
     "WHERE id = :a", {"v": None},
     "stored report != evaluator recomputation"),
    ("report hash",
     "UPDATE performance_retarget_assessments SET report_hash = :v "
     "WHERE id = :a", {"v": "4" * 64},
     "stored report != evaluator recomputation"),
    ("stored verdict superficially acceptable",
     "UPDATE performance_retarget_assessments SET overall_verdict = "
     "'COMPATIBLE_AS_IS' WHERE id = :a", {},
     "stored verdict != evaluator recomputation"),
    ("accepted review rationale grammar",
     "UPDATE performance_retarget_reviews SET rationale = :v "
     "WHERE id = :r", {"v": "x" * 5000}, "rationale"),
])
async def test_ind03_retarget_evidence_corruption_matrix(
        client, name, stmt, params, fragment):
    world = await _retarget_fixture(client)
    full = dict(params)
    full.setdefault("a", world["assessment"]["id"])
    full.setdefault("r", world["accept"]["id"])
    # fill the coherent-rehash variants (scope/report json) so only the
    # TARGETED divergence remains
    if name == "assessment project":
        other = (await client.post(
            "/projects", json={"name": "IND-other"})).json()["id"]
        full["v"] = other
    if name == "scope json (coherent hash)":
        from soloring.domain.canonical import (
            canonical_hash, canonical_json_str)
        stored = (await _one(
            client,
            "SELECT scope_json, scope_hash FROM "
            "performance_retarget_assessments WHERE id = :a",
            {"a": world["assessment"]["id"]}))
        import json as _json
        doc = _json.loads(stored["scope_json"])
        doc["subject_id"] = "tampered"
        full["v"] = canonical_json_str(doc)
        await _sql(
            client,
            "UPDATE performance_retarget_assessments SET "
            "scope_hash = :h WHERE id = :a",
            {"h": canonical_hash(doc),
             "a": world["assessment"]["id"]})
    if name == "report json (coherent hash)":
        from soloring.domain.canonical import (
            canonical_hash, canonical_json_str)
        doc = {
            "schema_version": 1,
            "evaluator_id": "soloring.performance_physical_retarget",
            "evaluator_version": 1,
            "scope_hash": (await _one(
                client,
                "SELECT scope_hash FROM "
                "performance_retarget_assessments WHERE id = :a",
                {"a": world["assessment"]["id"]}))["scope_hash"],
            "performance_revision_id": world["pr"]["id"],
            "from_production_revision_id":
                world["assessment"]["from_production_revision_id"],
            "to_production_revision_id":
                world["assessment"]["to_production_revision_id"],
            "verdict": "REQUIRES_REVIEW",
            "reason_code": "SAME_PRODUCTION_OBJECT_DIFFERENT_REVISION",
            "from_production_object_id": "tampered",
            "to_production_object_id": "tampered",
        }
        full["v"] = canonical_json_str(doc)
        await _sql(
            client,
            "UPDATE performance_retarget_assessments SET "
            "report_hash = :h WHERE id = :a",
            {"h": canonical_hash(doc),
             "a": world["assessment"]["id"]})
    before = await _counts(client)
    await _sql(client, stmt, full)
    r = await _retarget_post(client, world)
    _corrupt(r)
    assert fragment in r.json()["message"], (name, r.text)
    after = await _counts(client)
    assert after == before, \
        f"{name}: retarget created rows {before} -> {after}"


@pytest.mark.asyncio
async def test_ind03_review_ownership_corruption(client):
    """Review ownership: the accepted review is repointed at ANOTHER
    assessment (FK-permitted) — creation refuses with zero new rows."""
    world = await _retarget_fixture(client)
    from tests.m17b_seed import (seed_production_object,
                                 seed_production_revision)
    obj2 = await seed_production_object(
        client, world["project_id"], "IND obj2", b"ind2")
    p3 = await seed_production_revision(client, obj2, b"ind2-3", 3)
    a2 = (await client.post(
        f"/performance-revisions/{world['pr']['id']}/"
        "retarget-assessments",
        json={"from_production_revision_id":
              world["assessment"]["to_production_revision_id"],
              "to_production_revision_id":
                  p3["production_revision_id"]})).json()
    before = await _counts(client)
    await _sql(
        client,
        "UPDATE performance_retarget_reviews SET assessment_id = :v "
        "WHERE id = :r",
        {"v": a2["id"], "r": world["accept"]["id"]})
    r = await _retarget_post(client, world)
    _corrupt(r)
    assert "different assessment" in r.json()["message"], r.text
    after = await _counts(client)
    assert after == before


@pytest.mark.asyncio
async def test_ind03_dialogue_bound_source_spot_check(client):
    """The pre-existing PF-03 closure composes with the shared
    verifier: a scope corruption on a DIALOGUE-BOUND source refuses at
    creation with zero new rows (the wrapper's classification/binding
    checks run first and pass on the lawful companion state)."""
    world = await _retarget_fixture(client, dialogue_bound=True)
    before = await _counts(client)
    await _sql(
        client,
        "UPDATE performance_retarget_assessments SET scope_hash = :v "
        "WHERE id = :a",
        {"v": "5" * 64, "a": world["assessment"]["id"]})
    r = await _retarget_post(client, world)
    _corrupt(r)
    assert "scope does not recompute" in r.json()["message"], r.text
    after = await _counts(client)
    assert after == before


@pytest.mark.asyncio
async def test_ind03_lawful_retarget_creation_unchanged(client):
    world = await _retarget_fixture(client)
    before = await _counts(client)
    r = await _retarget_post(client, world)
    assert r.status_code == 201, r.text
    after = await _counts(client)
    assert after[0] == before[0] + 1
    assert after[1] == before[1] + 1  # the new candidate classification
    assert after[2] == before[2]      # NONE source: no binding row


@pytest.mark.asyncio
@pytest.mark.parametrize("error,fragment", [
    (PermissionError("denied"), "unreadable (permission denied)"),
    (OSError(5, "I/O control error"),
     "unreadable through a storage error"),
])
async def test_ind04_blob_read_os_errors_normalized(
        client, tmp_path, monkeypatch, error, fragment):
    """Blob DB row retained; the physical read raises PermissionError
    / a representative OSError (monkeypatched at the recovery seam —
    never OS-ACL dependent). Restore refuses through the stable
    recovery-corruption contract with the branch-specific diagnostic."""
    world = await _bound_world(client)
    root = await _backup_0021(client, tmp_path, "ind04-%s" % type(error).__name__)
    blob_hash = (await _one(
        client,
        "SELECT canonical_channel_payload_blob_hash AS h FROM "
        "performance_candidates WHERE id = :c",
        {"c": world["candidate"]["id"]}))["h"]
    target = _blob_path_for(root, blob_hash)
    assert target.is_file()
    real_read_bytes = pathlib.Path.read_bytes

    def selective_read_bytes(self):
        # match by NAME (the blob hash): restore verifies a STAGED COPY
        # of the backup tree, so the physical path differs from `target`
        if self.name == blob_hash:
            raise error
        return real_read_bytes(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes",
                        selective_read_bytes)
    exc = await _restore_refuses(root, tmp_path, "ind04-%s" % type(error).__name__)
    monkeypatch.setattr(pathlib.Path, "read_bytes", real_read_bytes)
    assert isinstance(exc, SoloRingError), exc
    assert exc.code == "RECOVERY_CORRUPTION", exc
    assert fragment in str(exc), (fragment, exc)


@pytest.mark.asyncio
async def test_ind04_malformed_provenance_json_normalized(
        client, tmp_path):
    world = await _bound_world(client)
    root = await _backup_0021(client, tmp_path, "ind04-prov")
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "UPDATE performance_candidates SET provenance_json = '{nope' "
        "WHERE id = ?", (world["candidate"]["id"],))
    con.commit()
    con.close()
    exc = await _restore_refuses(root, tmp_path, "ind04-prov")
    assert isinstance(exc, SoloRingError), exc
    assert exc.code == "RECOVERY_CORRUPTION", exc
    assert "provenance is not JSON" in str(exc), exc


@pytest.mark.asyncio
@pytest.mark.parametrize("name,stmt,params", [
    ("evaluator id",
     "UPDATE performance_retarget_assessments SET evaluator_id = :v "
     "WHERE id = :a", {"v": "other-evaluator"}),
    ("evaluator version",
     "UPDATE performance_retarget_assessments SET "
     "evaluator_version = 2 WHERE id = :a", {}),
    ("assessment schema version",
     "UPDATE performance_retarget_assessments SET schema_version = 2 "
     "WHERE id = :a", {}),
    ("accepted review reviewed_by whitespace",
     "UPDATE performance_retarget_reviews SET reviewed_by = '   ' "
     "WHERE id = :r", {}),
])
async def test_ind03_db_check_pinned_shapes(client, name, stmt, params):
    """IND-03 recorded fact: these evidence-corruption shapes are
    DB-CHECK-pinned — the schema's own CHECK constraints refuse the
    column writes mechanically (ck_pra_* / ck_prr_*), so the corrupted
    state cannot exist at this schema at all. The shared verifier's
    corresponding laws (evaluator identity, schema version, review
    metadata grammar) remain the recovery-parity mirror and fire for
    any database that ever carried them; here we prove the writes are
    impossible."""
    from sqlalchemy.exc import IntegrityError
    world = await _retarget_fixture(client)
    full = dict(params)
    full.setdefault("a", world["assessment"]["id"])
    full.setdefault("r", world["accept"]["id"])
    with pytest.raises(IntegrityError):
        await _sql(client, stmt, full)
