"""M17C-B SR2 corrective regressions (second-review findings
SR2-01..SR2-10, frozen under the PR #26 reconciliation of 2026-09-28).

- SR2-01: 0020 and 0021 are DISTINCT supported restore heads; a
  genuine 0020-staged database restores successfully; an unknown
  future head refuses.
- SR2-02: the M17C recovery verifier is head-aware — 0021 with the
  PF-02 table dropped (or replaced by a malformed substitute) refuses;
  0020 carrying an illicit successor table refuses.
- SR2-03: paired-vocal VP drift created through the SUPPORTED M17A
  API is a lawful BLOCKED working state — readiness blocks (never
  500), survives backup/restore unchanged, and returns to READY when
  the pair is restored; the PF-02 PUT creation law still requires the
  exact binding VP.
- SR2-04: PerformanceRevision↔adopted-candidate copied closure +
  adoption metadata are proven by the seam — revision-side tamper
  matrix (project, subject, temporal domain, payload identity,
  provenance hash, adoption metadata) refuses PUT with zero new rows,
  fails readiness closed, and recovery agrees.
- SR2-05: the SHARED read-grade binding verifier — coordinated
  binding tampers (both rows coherently rehashed) refuse readiness and
  recovery on the semantic laws (rate, exact-VP via alignments, trim,
  revision-owned domain, wrong-VP cited alignment).
- SR2-06: current Shot-duration drift (zero and shrunken) is a
  BLOCKED working state that survives backup/restore with rows
  unchanged and readiness still blocked afterwards.
- SR2-07: the M17A vocal PUT splits missing-selection (500) from
  lawful UNSET/different-selection (409).
- SR2-08: concurrent first PUTs to the same position both commit as
  ordinary 200s through the atomic upsert — no raw exception escapes,
  no duplicate or torn row.
- SR2-09: the shared DELETE/PUT position domain law.
- SR2-10: git-based migration history proofs.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from soloring.domain.canonical import canonical_hash, canonical_json_str
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


async def _count(client, table=_TABLE):
    async with _engine(client).connect() as conn:
        return (await conn.execute(
            text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()


def _corrupt(resp, message_fragment=None):
    assert resp.status_code == 500, resp.text
    assert resp.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"
    if message_fragment is not None:
        assert message_fragment in resp.json()["message"], resp.text


async def _lawful_put(client, world):
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text


async def _bound_world_with_alignments(client):
    """A lawful dialogue-bound world whose payload CITES real
    alignments (the dr26_03 pattern) — required for the exact-VP
    alignment laws to be reachable by a coordinated binding tamper."""
    from tests.m17a_seed import make_shot
    from tests.m17c_seed import (ARTICULATION, dialogue_bound_body,
                                 make_alignment, make_vp)
    from tests.test_m17c_shot_mapping import _add_dependency
    world = await make_vp(client)
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": world["vp"]["id"],
              "selected_by": "sr2"})
    shot = await make_shot(client, world["project_id"], 3000)
    await _add_dependency(client, shot, world["subject_id"])
    r = await client.put(
        f"/shots/{shot}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": world["vp"]["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text
    alignment = await make_alignment(
        client, world["vp"]["id"], world["blob_hash"])
    candidate = (await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            world["vp"]["id"],
            alignment_by_channel={key: alignment["id"]
                                  for key in ARTICULATION},
            articulation_time={key: (600, 1) for key in ARTICULATION}),
    )).json()
    pr = (await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "sr2"})).json()
    world["shot"] = shot
    world["candidate"] = candidate
    world["pr"] = pr
    await _lawful_put(client, world)
    return world


def _tamper(root: Path, stmt: str, params: tuple) -> None:
    con = sqlite3.connect(root / "soloring.db")
    con.execute(stmt, params)
    con.commit()
    con.close()


async def _backup_at_head(client, tmp_path, tag, head):
    from soloring.recovery import backup as rb_backup
    from tests.test_m16_recovery import _settings, _stamp_alembic
    await _stamp_alembic(client, head=head)
    root = tmp_path / f"sr2-{tag}"
    await rb_backup(await _settings(client), root)
    return root


def _retarget_backup(root: Path, head: str, *, drop_pf02: bool) -> None:
    """Reshape a genuine current-head backup into a genuine
    HISTORICAL-head backup tree (SR2-01/02 fixtures): the staged DB is
    stamped the historical head (optionally dropping the successor
    table that migration did not yet create) and the manifest records
    the same head with a recomputed canonical representation."""
    import hashlib

    from soloring.domain.canonical import canonical_json_bytes
    if drop_pf02:
        _tamper(root, f"DROP TABLE {_TABLE}", ())
    if head != "0023_m17cc_capture_closure_preimage":
        # M17C-C slice 1: reshaping to any pre-0022 head drops the
        # three schema-8 capture-storage tables the create_all backup
        # tree carries (empty in every fixture that reshapes)
        for _t in ("shot_revision_performance_specs",
                   "shot_revision_performance_segments",
                   "generation_performance_inputs"):
            _tamper(root, f"DROP TABLE {_t}", ())
    _tamper(root, "UPDATE alembic_version SET version_num = ?",
            (head,))
    manifest_path = root / "backup-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["alembic_version"] = head
    manifest["database_sha256"] = hashlib.sha256(
        (root / "soloring.db").read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


async def _restore_refuses(backup_root, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import (
        _rehash_manifest, _restore_refuses as sr26_refuses)
    _rehash_manifest(backup_root)
    return await sr26_refuses(backup_root, tmp_path, tag)


async def _restored_readiness(dest: Path, shot_id: str) -> dict:
    """Re-project PF-02 readiness against a RESTORED tree (SR2-03/06:
    blocked-ness must survive restore)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from soloring.db.engine import create_soloring_engine
    from soloring.performance import m17c_shot_mapping as sm
    from soloring.settings import Settings
    settings = Settings(data_dir=dest)
    engine = create_soloring_engine(settings)
    maker = async_sessionmaker(bind=engine, expire_on_commit=False,
                               class_=AsyncSession)
    try:
        async with maker() as session:
            return await sm.project_shot_performance_readiness(
                session, settings, shot_id=shot_id)
    finally:
        await engine.dispose()


def _binding_doc(b: dict) -> dict:
    return {
        "binding_schema_version": b["binding_schema_version"],
        "synchronization_basis_version":
            b["synchronization_basis_version"],
        "vocal_performance_revision_id":
            b["vocal_performance_revision_id"],
        "source_start_sample": b["source_start_sample"],
        "source_end_sample_exclusive":
            b["source_end_sample_exclusive"],
        "sample_rate_hz": b["sample_rate_hz"],
        "performance_origin_ms": {"num": b["performance_origin_num"],
                                  "den": b["performance_origin_den"]},
    }


async def _fetch_bindings(client, pr_id):
    rb = await _one(
        client,
        "SELECT * FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = :r", {"r": pr_id})
    candidate_id = (await _one(
        client,
        "SELECT adopted_candidate_id FROM performance_revisions "
        "WHERE id = :r", {"r": pr_id}))["adopted_candidate_id"]
    cb = await _one(
        client,
        "SELECT * FROM performance_candidate_vocal_bindings "
        "WHERE performance_candidate_id = :c", {"c": candidate_id})
    return cb, rb


async def _coordinated_binding_tamper(client, world, mutate):
    """Coherently rewrite BOTH binding rows (columns AND canonical
    JSON/hash recomputed) so only the targeted semantic law can
    refuse."""
    cb, rb = await _fetch_bindings(client, world["pr"]["id"])
    cdoc, rdoc = mutate(_binding_doc(rb))
    await _sql(
        client,
        "UPDATE performance_candidate_vocal_bindings SET "
        "vocal_performance_revision_id = :v, source_start_sample = :ss, "
        "source_end_sample_exclusive = :se, sample_rate_hz = :sr, "
        "performance_origin_num = :on, performance_origin_den = :od, "
        "binding_json = :j, binding_hash = :h "
        "WHERE performance_candidate_id = :c",
        {"v": cdoc["vocal_performance_revision_id"],
         "ss": cdoc["source_start_sample"],
         "se": cdoc["source_end_sample_exclusive"],
         "sr": cdoc["sample_rate_hz"],
         "on": cdoc["performance_origin_ms"]["num"],
         "od": cdoc["performance_origin_ms"]["den"],
         "j": canonical_json_str(cdoc), "h": canonical_hash(cdoc),
         "c": cb["performance_candidate_id"]})
    await _sql(
        client,
        "UPDATE performance_revision_vocal_bindings SET "
        "vocal_performance_revision_id = :v, source_start_sample = :ss, "
        "source_end_sample_exclusive = :se, sample_rate_hz = :sr, "
        "performance_origin_num = :on, performance_origin_den = :od, "
        "binding_json = :j, binding_hash = :h "
        "WHERE performance_revision_id = :r",
        {"v": rdoc["vocal_performance_revision_id"],
         "ss": rdoc["source_start_sample"],
         "se": rdoc["source_end_sample_exclusive"],
         "sr": rdoc["sample_rate_hz"],
         "on": rdoc["performance_origin_ms"]["num"],
         "od": rdoc["performance_origin_ms"]["den"],
         "j": canonical_json_str(rdoc), "h": canonical_hash(rdoc),
         "r": world["pr"]["id"]})


# ---------------------------------------------------------------------------
# SR2-01 — distinct supported heads; genuine 0020 restores
# ---------------------------------------------------------------------------

def test_sr2_01_distinct_supported_heads():
    from soloring.recovery.backup import (
        EXPECTED_ALEMBIC_HEAD,
        M17C_A_ALEMBIC_HEAD,
        M17C_B_ALEMBIC_HEAD,
        M17C_C_ALEMBIC_HEAD,
        M17C_C2_ALEMBIC_HEAD,
        SUPPORTED_RESTORE_ALEMBIC_HEADS,
    )
    assert M17C_A_ALEMBIC_HEAD == "0020_m17c_perf_capture_r2"
    assert M17C_B_ALEMBIC_HEAD == "0021_m17c_shot_performance_mappings"
    assert M17C_A_ALEMBIC_HEAD != M17C_B_ALEMBIC_HEAD
    # M17C-C: 0022 = schema-8 capture storage; FPR-M17CC-04 advances
    # the expected head to the 0023 closure-preimage successor; every
    # predecessor stays distinct + supported
    assert M17C_C_ALEMBIC_HEAD == "0022_m17c_schema8_capture"
    assert M17C_C2_ALEMBIC_HEAD == "0023_m17cc_capture_closure_preimage"
    assert EXPECTED_ALEMBIC_HEAD == M17C_C2_ALEMBIC_HEAD
    assert M17C_A_ALEMBIC_HEAD in SUPPORTED_RESTORE_ALEMBIC_HEADS
    assert M17C_B_ALEMBIC_HEAD in SUPPORTED_RESTORE_ALEMBIC_HEADS
    assert M17C_C_ALEMBIC_HEAD in SUPPORTED_RESTORE_ALEMBIC_HEADS
    assert M17C_C2_ALEMBIC_HEAD in SUPPORTED_RESTORE_ALEMBIC_HEADS


@pytest.mark.asyncio
async def test_sr2_01_genuine_0020_backup_restores(client, tmp_path):
    from soloring.recovery import restore as rb_restore
    from soloring.recovery.backup import M17C_A_ALEMBIC_HEAD
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    # a genuine 0020 backup tree: a real current backup reshaped to the
    # 0020 identity (the PF-02 table dropped — migration 0021 creates
    # it; no PF-02 rows exist in this world — staged head + manifest
    # both the frozen M17C-A head)
    root = await _backup_m17c(client, tmp_path, "sr2-0020src")
    _retarget_backup(root, M17C_A_ALEMBIC_HEAD, drop_pf02=True)
    dest = tmp_path / "restored-0020"
    await rb_restore(root, dest)
    con = sqlite3.connect(dest / "soloring.db")
    try:
        head = con.execute(
            "SELECT version_num FROM alembic_version").fetchone()[0]
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        bindings = con.execute(
            "SELECT COUNT(*) FROM performance_revision_vocal_bindings "
            "WHERE performance_revision_id = ?",
            (world["pr"]["id"],)).fetchone()[0]
    finally:
        con.close()
    assert head == M17C_A_ALEMBIC_HEAD
    assert _TABLE not in tables
    assert bindings == 1


@pytest.mark.asyncio
async def test_sr2_01_unknown_future_head_refuses(client, tmp_path):
    world = await _bound_world(client)
    # the backup-side staged-head guard keeps the M12-era staleness
    # law: a database stamped at a non-EXPECTED head refuses before any
    # manifest exists (future OR historical — both are "not current")
    with pytest.raises(Exception) as excinfo:
        await _backup_at_head(
            client, tmp_path, "sr2-future", "0022_m17c_future_slice")
    assert "requires exactly" in str(excinfo.value), excinfo.value


# ---------------------------------------------------------------------------
# SR2-02 — head-aware schema verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sr2_02_0021_with_dropped_pf02_table_refuses(
        client, tmp_path):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_m17c(client, tmp_path, "sr2-drop")
    _tamper(root, f"DROP TABLE {_TABLE}", ())
    exc = await _restore_refuses(root, tmp_path, "sr2-drop")
    assert "missing the PF-02 working-mapping table" in str(exc)


@pytest.mark.asyncio
async def test_sr2_02_0021_with_malformed_substitute_refuses(
        client, tmp_path):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    await _lawful_put(client, world)
    root = await _backup_m17c(client, tmp_path, "sr2-malformed")
    _tamper(root, f"DROP TABLE {_TABLE}", ())
    _tamper(
        root,
        f"CREATE TABLE {_TABLE} (shot_id TEXT, junk TEXT)",
        ())
    exc = await _restore_refuses(root, tmp_path, "sr2-malformed")
    assert "column contract diverges" in str(exc)


@pytest.mark.asyncio
async def test_sr2_02_0020_with_illicit_successor_table_refuses(
        client, tmp_path):
    """A genuine 0020 backup tree carrying the PF-02 table is refused
    at RESTORE — the head-aware M17C verifier requires its absence at
    0020."""
    from soloring.recovery.backup import M17C_A_ALEMBIC_HEAD
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    root = await _backup_m17c(client, tmp_path, "sr2-illicit")
    # reshape to 0020 but KEEP the (empty) PF-02 table — the illicit shape
    _retarget_backup(root, M17C_A_ALEMBIC_HEAD, drop_pf02=False)
    exc = await _restore_refuses(root, tmp_path, "sr2-illicit")
    assert "carries the PF-02 working-mapping table" in str(exc)


# ---------------------------------------------------------------------------
# SR2-03 — paired-vocal VP drift is a lawful blocked working state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sr2_03_paired_vp_drift_lifecycle(client, tmp_path):
    from soloring.recovery import restore as rb_restore
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    await _lawful_put(client, world)
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True

    alternate = await _same_line_alternate_vp(client, world)
    # repoint the paired working vocal position through the SUPPORTED
    # M17A API: select VP-B, then PUT the existing position to VP-B
    r = await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": alternate["id"],
              "selected_by": "sr2"})
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{world['shot']}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": alternate["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text

    # readiness BLOCKS (never 500): mutable working drift against the
    # immutable revision binding
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is False
    seg = readiness["segments"][0]
    assert seg["readiness"] == "BLOCKED_BINDING_INTEGRITY"
    assert seg["readiness_diagnostics"][
        "paired_vocal_performance_revision_id"] == alternate["id"]
    assert seg["readiness_diagnostics"][
        "bound_vocal_performance_revision_id"] == world["vp"]["id"]

    # backup/restore preserves the drifted working state byte-for-byte
    root = await _backup_m17c(client, tmp_path, "sr2-drift")
    before = sqlite3.connect(root / "soloring.db")
    before.row_factory = sqlite3.Row
    mapping_before = dict(before.execute(
        f"SELECT * FROM {_TABLE} WHERE shot_id = ? AND position = 0",
        (world["shot"],)).fetchone())
    vocal_before = dict(before.execute(
        "SELECT * FROM shot_vocal_segment_mappings "
        "WHERE shot_id = ? AND position = 0",
        (world["shot"],)).fetchone())
    before.close()
    dest = tmp_path / "restored-drift"
    await rb_restore(root, dest)
    con = sqlite3.connect(dest / "soloring.db")
    con.row_factory = sqlite3.Row
    mapping_after = dict(con.execute(
        f"SELECT * FROM {_TABLE} WHERE shot_id = ? AND position = 0",
        (world["shot"],)).fetchone())
    vocal_after = dict(con.execute(
        "SELECT * FROM shot_vocal_segment_mappings "
        "WHERE shot_id = ? AND position = 0",
        (world["shot"],)).fetchone())
    con.close()
    assert mapping_after == mapping_before
    assert vocal_after == vocal_before
    restored = await _restored_readiness(dest, world["shot"])
    assert restored["segments"][0]["readiness"] == \
        "BLOCKED_BINDING_INTEGRITY"

    # returning the pair to the exact immutable binding VP restores
    # readiness
    r = await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": world["vp"]["id"],
              "selected_by": "sr2"})
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{world['shot']}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": world["vp"]["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text
    readiness = (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()
    assert readiness["ready"] is True


@pytest.mark.asyncio
async def test_sr2_03_creation_still_requires_exact_binding_vp(client):
    """The PUT creation law is NOT weakened by the drift semantics: a
    FRESH PF-02 PUT pairing a vocal position currently bound to a
    different VP still refuses with the admission 422."""
    world = await _bound_world(client)
    await _lawful_put(client, world)
    alternate = await _same_line_alternate_vp(client, world)
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": alternate["id"],
              "selected_by": "sr2"})
    r = await client.put(
        f"/shots/{world['shot']}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": alternate["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/1",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == "PERFORMANCE_VOCAL_MAPPING_MISMATCH"


# ---------------------------------------------------------------------------
# SR2-04 — revision copied-closure + adoption metadata tamper matrix
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sr2_04_revision_closure_tamper_matrix(client, tmp_path):
    from tests.m17b_seed import make_entity
    from tests.test_m17c_sr26_regressions import _backup_m17c
    base_world = await _bound_world(client)
    other_project = (await client.post(
        "/projects", json={"name": "SR2Other"})).json()
    other_entity = await make_entity(
        client, base_world["project_id"], "SR2Entity")
    vp_audio_hash = (await _one(
        client,
        "SELECT retained_audio_blob_hash FROM "
        "vocal_performance_revisions WHERE id = :v",
        {"v": base_world["vp"]["id"]}))["retained_audio_blob_hash"]

    tampers = [
        ("project_id",
         "UPDATE performance_revisions SET project_id = :v "
         "WHERE id = :r", other_project["id"], "closure"),
        ("subject_id",
         "UPDATE performance_revisions SET subject_id = :v "
         "WHERE id = :r", other_entity, "closure"),
        ("temporal domain",
         "UPDATE performance_revisions SET temporal_end_num = 999999 "
         "WHERE id = :r", None, "closure"),
        ("payload identity",
         "UPDATE performance_revisions SET "
         "canonical_channel_payload_blob_hash = :v, "
         "canonical_channel_payload_sha256 = :v WHERE id = :r",
         vp_audio_hash, "closure"),
        ("provenance hash",
         "UPDATE performance_revisions SET provenance_hash = :v "
         "WHERE id = :r", "f" * 64, "closure"),
        ("adoption metadata",
         "UPDATE performance_revisions SET adoption_id = 'not-a-uuid' "
         "WHERE id = :r", None, "adoption"),
    ]
    for i, (what, stmt, value, kind) in enumerate(tampers):
        world = await _bound_world(client)
        await _lawful_put(client, world)
        params = {"v": value, "r": world["pr"]["id"]} if value else \
            {"r": world["pr"]["id"]}
        await _sql(client, stmt, params)
        # PUT refuses 500 with zero new rows (per-shot: the matrix
        # shares one database across its six worlds)
        r = await client.put(
            f"/shots/{world['shot']}/performance-segments/1",
            json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
        fragment = ("closure does not reproduce" if kind == "closure"
                    else "adoption_id must be an exact UUID")
        _corrupt(r, fragment)
        shot_rows = await _one(
            client,
            f"SELECT COUNT(*) AS n FROM {_TABLE} WHERE shot_id = :s",
            {"s": world["shot"]})
        assert shot_rows["n"] == 1
        # readiness/list fail closed
        for path in (f"/shots/{world['shot']}/performance-readiness",
                     f"/shots/{world['shot']}/performance-segments"):
            _corrupt(await client.get(path), fragment)
        # recovery agrees: the backup-side enumeration runs the M17B
        # revision verifier over the live tree and refuses the tampered
        # row before any backup is written
        with pytest.raises(Exception) as excinfo:
            await _backup_m17c(client, tmp_path, f"sr2-closure-{i}")
        assert ("closure diverges" in str(excinfo.value)
                or "adoption metadata" in str(excinfo.value)), \
            (what, excinfo.value)


# ---------------------------------------------------------------------------
# SR2-05 — shared read-grade verifier; coordinated binding tampers
# ---------------------------------------------------------------------------

async def _read_and_backup_refuse(client, tmp_path, world, read_fragment,
                                  backup_fragment, tag):
    """Shared SR2-05 expectation: readiness fails closed as corruption
    with the targeted live law's fragment, and the backup-side recovery
    enumeration refuses with the SAME law's recovery fragment (the
    recovery verdict agrees — branch-specific, not family-loose)."""
    from tests.test_m17c_sr26_regressions import _backup_m17c
    _corrupt(await client.get(
        f"/shots/{world['shot']}/performance-readiness"), read_fragment)
    with pytest.raises(Exception) as excinfo:
        await _backup_m17c(client, tmp_path, tag)
    assert backup_fragment in str(excinfo.value), excinfo.value


@pytest.mark.asyncio
async def test_sr2_05_coordinated_wrong_sample_rate(client, tmp_path):
    world = await _bound_world(client)
    await _lawful_put(client, world)
    await _coordinated_binding_tamper(
        client, world,
        lambda doc: ({**doc, "sample_rate_hz": 44100},
                     {**doc, "sample_rate_hz": 44100}))
    await _read_and_backup_refuse(
        client, tmp_path, world,
        "binding sample rate != VP native sample rate",
        "binding sample rate != VP native sample rate", "sr2-rate")


@pytest.mark.asyncio
async def test_sr2_05_coordinated_alternate_vp(client, tmp_path):
    """Coordinated move to a REAL alternate same-line VP on a world
    whose payload cites alignments: every local law holds; only the
    exact-VP alignment law can refuse."""
    world = await _bound_world_with_alignments(client)
    alternate = await _same_line_alternate_vp(client, world)
    await _coordinated_binding_tamper(
        client, world,
        lambda doc: ({**doc, "vocal_performance_revision_id":
                      alternate["id"]},
                     {**doc, "vocal_performance_revision_id":
                      alternate["id"]}))
    await _read_and_backup_refuse(
        client, tmp_path, world,
        "alignment derived from a different",
        "alignment derived from a different", "sr2-altvp")


@pytest.mark.asyncio
async def test_sr2_05_coordinated_out_of_trim(client, tmp_path):
    world = await _bound_world(client)
    await _lawful_put(client, world)
    await _coordinated_binding_tamper(
        client, world,
        lambda doc: ({**doc, "source_end_sample_exclusive": 10 ** 9},
                     {**doc, "source_end_sample_exclusive": 10 ** 9}))
    await _read_and_backup_refuse(
        client, tmp_path, world,
        "binding source interval lies outside the VP trim",
        "binding source interval lies outside the VP trim", "sr2-trim")


@pytest.mark.asyncio
async def test_sr2_05_coordinated_origin_outside_domain(client, tmp_path):
    world = await _bound_world(client)
    await _lawful_put(client, world)
    await _coordinated_binding_tamper(
        client, world,
        lambda doc: ({**doc, "performance_origin_ms":
                      {"num": 20000, "den": 1}},
                     {**doc, "performance_origin_ms":
                      {"num": 20000, "den": 1}}))
    await _read_and_backup_refuse(
        client, tmp_path, world,
        "outside the revision's own temporal domain",
        "outside the temporal domain", "sr2-domain")


@pytest.mark.asyncio
async def test_sr2_05_wrong_vp_cited_alignment(client, tmp_path):
    """Binding intact; the CITED alignment row of the bound VP is
    repointed to the real alternate — only the exact-VP cited-alignment
    law can refuse."""
    world = await _bound_world_with_alignments(client)
    alternate = await _same_line_alternate_vp(client, world)
    await _sql(
        client,
        "UPDATE dialogue_alignments SET "
        "vocal_performance_revision_id = :a "
        "WHERE vocal_performance_revision_id = :v",
        {"a": alternate["id"], "v": world["vp"]["id"]})
    # recovery layering (recorded): the M17A verifier refuses this
    # tamper FIRST — the alignment's derivation-run digest embeds the
    # VP identity, so the repoint trips the M17A structural law
    # ("run digest != VP identity") before the M17C cited-alignment
    # law is reached; the state is refused either way
    await _read_and_backup_refuse(
        client, tmp_path, world,
        "alignment derived from a different",
        "run digest != VP identity", "sr2-alignvp")


# ---------------------------------------------------------------------------
# SR2-06 — current-duration drift survives restore
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sr2_06_duration_drift_survives_restore(client, tmp_path):
    from soloring.recovery import restore as rb_restore
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _generic_world(client)
    # d05's lawful L-cut: [0, 4500) anchored at 2000 in a 3000ms Shot
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 4500, 2000))
    assert r.status_code == 200, r.text
    assert (await client.get(
        f"/shots/{world['shot']}/performance-readiness")).json()[
        "ready"] is True

    async def drift_case(duration, tag):
        p = await client.patch(
            f"/shots/{world['shot']}", json={"duration_ms": duration})
        assert p.status_code == 200, p.text
        readiness = (await client.get(
            f"/shots/{world['shot']}/performance-readiness")).json()
        assert readiness["ready"] is False
        assert readiness["segments"][0]["readiness"] == \
            "BLOCKED_TIMING_MISMATCH"
        root = await _backup_m17c(client, tmp_path, tag)
        before = sqlite3.connect(root / "soloring.db")
        before.row_factory = sqlite3.Row
        row_before = dict(before.execute(
            f"SELECT * FROM {_TABLE} WHERE shot_id = ? AND position = 0",
            (world["shot"],)).fetchone())
        before.close()
        dest = tmp_path / f"restored-{tag}"
        await rb_restore(root, dest)
        con = sqlite3.connect(dest / "soloring.db")
        con.row_factory = sqlite3.Row
        row_after = dict(con.execute(
            f"SELECT * FROM {_TABLE} WHERE shot_id = ? AND position = 0",
            (world["shot"],)).fetchone())
        con.close()
        assert row_after == row_before
        restored = await _restored_readiness(dest, world["shot"])
        assert restored["segments"][0]["readiness"] == \
            "BLOCKED_TIMING_MISMATCH"

    await drift_case(1000, "sr2-shrunk")   # no longer intersects
    await drift_case(0, "sr2-zero")        # unlawful current duration


# ---------------------------------------------------------------------------
# SR2-07 — M17A vocal PUT selection semantics
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sr2_07_vocal_put_selection_semantics(client):
    world = await _bound_world(client)
    body = {
        "vocal_performance_revision_id": world["vp"]["id"],
        "source_start_sample": 48000,
        "source_end_sample_exclusive": 96000,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 0, "den": 1},
        "shot_anchor_ms": {"num": 0, "den": 1},
    }
    url = f"/shots/{world['shot']}/vocal-segments/5"
    # lawful baseline on a fresh position
    r = await client.put(url, json=body)
    assert r.status_code == 200, r.text
    # MISSING selection row is corruption (500), never a stale 409
    await _sql(
        client,
        "DELETE FROM vocal_performance_selections "
        "WHERE dialogue_line_revision_id = :d",
        {"d": world["dialogue_line_revision_id"]})
    r = await client.put(url, json=body)
    _corrupt(r, "no selection row")
    # lawful UNSET selection keeps the admission-shaped 409
    await _sql(
        client,
        "INSERT INTO vocal_performance_selections ("
        "dialogue_line_revision_id, selected_vocal_performance_revision_id,"
        " selected_by, selected_at, updated_at) VALUES "
        "(:d, NULL, NULL, NULL, :u)",
        {"d": world["dialogue_line_revision_id"],
         "u": "2026-01-01T00:00:00.000Z"})
    r = await client.put(url, json=body)
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "VOCAL_MAPPING_SELECTION_STALE"
    # selecting the requested VP lets ordinary validation proceed
    r = await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": world["vp"]["id"],
              "selected_by": "sr2"})
    assert r.status_code == 200, r.text
    r = await client.put(url, json=body)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# SR2-08 — concurrent first PUTs commit atomically
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sr2_08_concurrent_first_puts_both_commit(settings):
    from soloring.api.main import create_app
    from soloring.db import models  # noqa: F401 (register tables)
    from soloring.db.base import Base
    from soloring.db.engine import (
        create_session_factory, create_soloring_engine)

    engine = create_soloring_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    app = create_app(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    transport = httpx.ASGITransport(app=app,
                                    raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(
                transport=transport, base_url="http://t") as c:
            world = await _generic_world(c)
            r1, r2 = await asyncio.gather(
                c.put(
                    f"/shots/{world['shot']}/performance-segments/0",
                    json=_seg_body(world["pr"]["id"], 0, 2000, 0)),
                c.put(
                    f"/shots/{world['shot']}/performance-segments/0",
                    json=_seg_body(world["pr"]["id"], 500, 2500, 0)),
            )
            # both requests are ordinary stable API outcomes — the
            # atomic upsert closes the uniqueness/lock race
            assert r1.status_code == 200, r1.text
            assert r2.status_code == 200, r2.text
            rows = (await c.get(
                f"/shots/{world['shot']}/performance-segments")).json()
            assert len(rows) == 1
            assert (rows[0]["performance_start_ms"]["num"],
                    rows[0]["performance_end_ms"]["num"]) in (
                (0, 2000), (500, 2500))
            readiness = await c.get(
                f"/shots/{world['shot']}/performance-readiness")
            assert readiness.status_code == 200, readiness.text
            assert readiness.json()["ready"] is True
    finally:
        from tests.conftest import close_registered_sessions
        await close_registered_sessions(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_sr2_08_upsert_preserves_created_at(client):
    world = await _generic_world(client)
    r1 = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 2000, 0))
    assert r1.status_code == 200, r1.text
    created = (await _one(
        client,
        f"SELECT created_at, updated_at FROM {_TABLE} "
        "WHERE shot_id = :s AND position = 0",
        {"s": world["shot"]}))
    r2 = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 500, 2500, 0))
    assert r2.status_code == 200, r2.text
    after = (await _one(
        client,
        f"SELECT created_at, updated_at FROM {_TABLE} "
        "WHERE shot_id = :s AND position = 0",
        {"s": world["shot"]}))
    assert after["created_at"] == created["created_at"]


# ---------------------------------------------------------------------------
# SR2-09 — DELETE/PUT position domain
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sr2_09_delete_position_domain(client):
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
    # 2^63-1 is DB-safe and idempotent
    for _ in range(2):
        d = await client.delete(
            f"/shots/{world['shot']}/performance-segments/{_LIMIT}")
        assert d.status_code == 204, d.text
    assert await _count(client) == 1  # position 0 untouched


# ---------------------------------------------------------------------------
# SR2-10 — migration history proofs
# ---------------------------------------------------------------------------

def test_sr2_10_migration_history_proofs():
    repo = Path(__file__).resolve().parents[1]
    from soloring.recovery.backup import M17C_A_ALEMBIC_HEAD

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=str(repo), capture_output=True,
            text=True, check=True).stdout

    path = "server/alembic/versions"
    f0020 = f"{path}/0020_m17c_perf_capture_r2.py"
    f0021 = f"{path}/0021_m17c_shot_performance_mappings.py"
    baseline = "c502b81"  # the frozen M17C-A implementation head
    # frozen 0020 blob identity equals the c502b81 file
    assert git("cat-file", "blob", f"{baseline}:{f0020}") == \
        git("cat-file", "blob", f"HEAD:{f0020}")
    # 0021 did NOT exist at the c502b81 baseline
    probe = subprocess.run(
        ["git", "cat-file", "-e", f"{baseline}:{f0021}"],
        cwd=str(repo), capture_output=True, text=True)
    assert probe.returncode != 0
    # 0021's down_revision is exactly the frozen 0020 identity
    src = (repo / f0021).read_text(encoding="utf-8")
    needle = 'down_revision = "'
    line = next(l for l in src.splitlines()
                if l.strip().startswith(needle))
    assert line.strip()[len(needle):].rstrip('"') == M17C_A_ALEMBIC_HEAD
