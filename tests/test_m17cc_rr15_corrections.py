"""M17C-C RR15 corrections (frozen register RR15-M17CC-01..02).

RR15-01 — authenticate before classification. The ISR2-01 outer
  authentication applied only to revisions the first classification
  pass had already decided were schema 8 — but the verifier trusted
  the UNAUTHENTICATED `schema_version` to decide whether that law
  applied, so a lawful schema-8 capture with its discriminator
  rewritten DOWNWARD to an older legal schema, its M17C-C companion
  rows removed, and `snapshot_hash` left stale satisfied the
  schema<8-with-zero-companions branch and was never
  outer-authenticated. The classification pass now authenticates
  EVERY ShotRevision envelope (canonical persisted bytes +
  `snapshot_hash`) BEFORE the discriminator is trusted — a
  successor-head M17C-C verifier law (restoring an actual pre-0022
  alembic head is a different, unchanged concern).

RR15-02 — index column identity. The physical contract proved
  `ix_srpss_pr`'s name and (unique, origin, partial) flags but never
  `PRAGMA index_info`, so a same-name same-flags index rebuilt over
  `subject_id` certified. The shared `_verify_table_schema` contract
  now carries an OPTIONAL `index_columns` mapping (exact ordered
  sequences; contracts that omit it keep byte-identical behavior —
  the frozen predecessor PF-03/PF-02 surfaces are untouched), and
  both the 0022 and 0023 segment contracts require
  `ix_srpss_pr -> ["performance_revision_id"]`.

The battery proves the commission's decisive shapes: the
discriminator-downgrade adversary refused by the direct verifier AND
the full restore BEFORE classification can legitimize it; the
mixed-successor control (a genuine historical schema<8 revision
alongside a schema-8 revision inside ONE lawful 0023 database)
stays green; the wrong-column index adversary is refused at the
physical boundary at BOTH heads (the 0022 shape built by a real
alembic upgrade); and the already-closed ISR2-01 stale-hash and
noncanonical-byte adversaries keep refusing.
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
    world = await _bound_world(client)
    await _lawful(client, world)
    return world


async def _backup(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, f"rr15-{tag}")


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


# ---------------------------------------------------------------------------
# RR15-01 — the discriminator-downgrade bypass is closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr1501_discriminator_downgrade_refused_both_surfaces(
        client, tmp_path):
    """The commission's decisive adversary from a lawful schema-8
    capture: rewrite ONLY the embedded outer discriminator 8 -> 7 (a
    lawful older schema, canonical bytes persisted), remove precisely
    that revision's M17C-C companion closure so the old-schema branch
    would otherwise be satisfied, and leave snapshot_hash STALE — the
    direct verifier must refuse through outer authentication BEFORE
    classification can legitimize the downgraded shape, and the full
    staged restore must independently refuse."""
    from tests.test_m17c_sr26_regressions import _restore_refuses

    world, revision = await _stage_captured(client)
    root = await _backup(client, tmp_path, "downgrade")

    con = sqlite3.connect(root / "soloring.db")
    try:
        snapshot_json = con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (revision.id,)).fetchone()[0]
        snap = json.loads(snapshot_json)
        assert snap["schema_version"] == 8
        snap["schema_version"] = 7
        # canonical bytes over the downgraded document, hash untouched
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ? WHERE id = ?",
            (_cj(snap), revision.id))
        con.execute(
            f"DELETE FROM {_CHILDREN} WHERE shot_revision_id = ?",
            (revision.id,))
        con.execute(
            f"DELETE FROM {_PARENTS} WHERE shot_revision_id = ?",
            (revision.id,))
        con.commit()
    finally:
        con.close()

    _verify_raises(root, "snapshot_hash does not authenticate its "
                         "snapshot bytes")

    # the full staged restore independently refuses
    await _restore_refuses(root, tmp_path, "rr15-downgrade")


@pytest.mark.asyncio
async def test_rr1501_mixed_successor_database_green(client, tmp_path):
    """The commission's control: ONE lawful head-0023 database
    containing a GENUINE historical schema<8 revision (captured
    before any performance mappings existed) alongside a lawful
    schema-8 revision — authenticating every revision inside a
    successor database refuses nothing lawful (and is NOT a change to
    restoring an actual older alembic head)."""
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )

    world = await _bound_world(client)
    old_revision, _visual = await _capture(client, world["shot"])
    await _lawful(client, world, extra=True)
    new_revision, _visual = await _capture(client, world["shot"])

    con = sqlite3.connect(_live_root(client) / "soloring.db")
    try:
        old_schema = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (old_revision.id,)).fetchone()[0])["schema_version"]
        new_schema = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (new_revision.id,)).fetchone()[0])["schema_version"]
    finally:
        con.close()
    assert old_schema < 8, old_schema
    assert new_schema == 8, new_schema

    root = await _backup(client, tmp_path, "mixed")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD_0023)


# ---------------------------------------------------------------------------
# RR15-02 — the indexed-column identity of ix_srpss_pr
# ---------------------------------------------------------------------------

def _wrong_column_index(con):
    con.execute(f"DROP INDEX ix_srpss_pr")
    con.execute(
        f"CREATE INDEX ix_srpss_pr ON {_CHILDREN} (subject_id)")
    con.commit()


@pytest.mark.asyncio
async def test_rr1502_wrong_column_index_refused_0023(client, tmp_path):
    """The commission's decisive physical adversary at 0023: the
    same-name, same-flags index recreated over subject_id with every
    other detail lawful — recovery must refuse at the physical-schema
    boundary (absence is already ISR2-02's law; this distinguishes
    name+flags+wrong COLUMN)."""
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )

    world = await _stage_empty_successor(client)
    root = await _backup(client, tmp_path, "wrongcol-0023")

    # the undamaged state is green first
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD_0023)

    con = sqlite3.connect(root / "soloring.db")
    try:
        _wrong_column_index(con)
    finally:
        con.close()

    _verify_raises(
        root, "explicit index 'ix_srpss_pr' does not index exactly "
              "['performance_revision_id']")


@pytest.mark.asyncio
async def test_rr1502_wrong_column_index_refused_0022(client, tmp_path):
    """The same decisive adversary against the GENUINE 0022 segment
    shape (a real alembic 0021->0022 upgrade): the lawful shape
    proves the full tuple green first, then the wrong-column index
    refuses at the physical boundary."""
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )
    from tests.test_m17cc_migration import _run

    world = await _stage_empty_successor(client)
    root = await _backup(client, tmp_path, "wrongcol-0022")

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

    # the genuine 0022 shape (with the correct index) is green
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD_0022)

    con = sqlite3.connect(root / "soloring.db")
    try:
        _wrong_column_index(con)
    finally:
        con.close()
    _verify_raises(
        root, "explicit index 'ix_srpss_pr' does not index exactly "
              "['performance_revision_id']", head=_HEAD_0022)
