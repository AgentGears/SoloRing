"""M17C-C RR13 correction (frozen register RR13-M17CC-01) — the
versioned Performance block enforces its own TOP-LEVEL key grammar.

The canonical writer emits exactly ``{"schema_version": 2,
"segments": [...]}`` (``embedded_performance_value``), and every
NESTED grammar is closed — but neither §12's
``_verify_embedded_grammar`` nor recovery's
``_m17cc_embedded_grammar`` checked the Performance object's key
set. A coherent adversary adding one unknown top-level member to
BOTH the companion ``spec_json`` and the snapshot ``performance``
block (canonical parent/snapshot hashes recomputed, every child and
segment untouched) passed byte-equality, the actual-integer
discriminator, and every nested law on BOTH surfaces — the versioned
grammar certified canonical history the writer cannot produce, and
an unrecognized member entered immutable snapshot identity while
disappearing semantically during reconstruction.

The correction: ONE shared structural law —
``performance_block_key_error`` over the frozen
``PERFORMANCE_BLOCK_KEYS`` — consumed by both grammar verifiers
AFTER the schema discriminator and the explicit grammar-v1 refusal,
so every existing diagnostic stays distinguishable. This validates
the already-frozen grammar; no writer format, migration, storage,
capture, readiness, PF-02/PF-03, or Generation change.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world

_HEAD = "0023_m17cc_capture_closure_preimage"
_PARENTS = "shot_revision_performance_specs"


def _engine(client):
    return client._transport.app.state.engine


async def _stage_lawful(client):
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    return world, revision


def _live_root(client):
    return client._transport.app.state.settings.data_dir


def _add_unknown_top_level_member(db_root, revision_id):
    """The decisive RR13 adversary: add one unknown member directly
    to the Performance block in BOTH the companion spec_json and the
    snapshot performance, recompute the canonical parent hash and
    outer snapshot bytes/hash — every child and every segment
    untouched (byte-equality and every nested law still hold; only
    the top-level key grammar can refuse)."""
    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )
    con = sqlite3.connect(db_root / "soloring.db")
    try:
        spec = json.loads(con.execute(
            f"SELECT spec_json FROM {_PARENTS} WHERE "
            "shot_revision_id = ?", (revision_id,)).fetchone()[0])
        snap = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (revision_id,)).fetchone()[0])
        extra = {"meaning": "not emitted by the writer"}
        spec["unexpected"] = extra
        snap["performance"]["unexpected"] = extra
        con.execute(
            f"UPDATE {_PARENTS} SET spec_json = ?, spec_hash = ? "
            "WHERE shot_revision_id = ?",
            (cj(spec), ch(spec), revision_id))
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ?, "
            "snapshot_hash = ? WHERE id = ?",
            (cj(snap), ch(snap), revision_id))
        con.commit()
    finally:
        con.close()


def _verify_staged_raises(root, fragment):
    from soloring.errors import SoloRingError
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )
    with pytest.raises(SoloRingError) as rec:
        verify_m17c_binding_state(
            root / "soloring.db", root / "blobs", head=_HEAD)
    assert rec.value.code == "RECOVERY_CORRUPTION"
    assert fragment in rec.value.message, rec.value.message


# ---------------------------------------------------------------------------
# The decisive top-level adversary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr13_unknown_top_level_member_refused_by_both(
        client, tmp_path):
    """One unknown top-level member on the Performance block in both
    the companion spec and the snapshot, canonical parent/snapshot
    hashes refreshed, every child and segment untouched: §12 returns
    its typed internal-corruption contract and staged recovery
    returns typed RECOVERY_CORRUPTION — the ordinary nested grammars
    were already closed and cannot catch this shape."""
    from tests.test_m17c_sr26_regressions import _backup_m17c

    world, revision = await _stage_lawful(client)
    root = await _backup_m17c(client, tmp_path, "rr13-unknown-key")

    # the lawful writer-produced schema-2 control: green before the
    # tamper
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text

    _add_unknown_top_level_member(_live_root(client), revision.id)
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    message = r.json()["message"]
    assert "carries unknown top-level member(s) ['unexpected'] " \
        "outside the frozen schema-2 grammar" in message, message

    _add_unknown_top_level_member(root, revision.id)
    _verify_staged_raises(
        root, "carries unknown top-level member(s) ['unexpected'] "
        "outside the frozen schema-2 grammar")


# ---------------------------------------------------------------------------
# The ordinary writer-produced schema-2 control stays green
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr13_writer_schema2_control_green(client):
    """The ordinary writer-produced schema-2 block — exactly
    {"schema_version": 2, "segments": [...]} — remains green at both
    surfaces under the new top-level law."""
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    from tests.test_m17c_sr26_regressions import _backup_m17c
    import tempfile
    from pathlib import Path

    world, revision = await _stage_lawful(client)

    con = sqlite3.connect(_live_root(client) / "soloring.db")
    try:
        spec = json.loads(con.execute(
            f"SELECT spec_json FROM {_PARENTS} WHERE "
            "shot_revision_id = ?", (revision.id,)).fetchone()[0])
    finally:
        con.close()
    assert set(spec) == {"schema_version", "segments"}
    assert spec["schema_version"] == 2

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text

    tmp = Path(tempfile.mkdtemp())
    root = await _backup_m17c(client, tmp, "rr13-clean")
    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD)
