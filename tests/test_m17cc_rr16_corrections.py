"""M17C-C RR16 correction (frozen register RR16-M17CC-01) — the
successor recovery chain is total over malformed outer ShotRevision
snapshot JSON BEFORE any M16 semantic use.

The M17C-C verifier's own decode was already guarded, but the M16
PREDECESSOR verifier parsed every ShotRevision with bare
``json.loads`` + ``.get(...)`` (the global history enumeration, the
intra-shot companion sweep, and the proposal source-revision lookup)
BEFORE the M17C-C chain ran — so malformed JSON or an invalid-UTF-8
SQLite BLOB escaped as raw ``JSONDecodeError``/``UnicodeDecodeError``
and a valid non-object top level (``[]``) as raw ``AttributeError``
on the full backup/restore path.

The correction: ONE shared recovery-side outer-ShotRevision parser
(``soloring.recovery.outer_snapshot.load_outer_snapshot``) — decode
failures convert to the typed recovery-corruption contract, and a
JSON OBJECT is required before any consumer calls ``.get()``; no
semantic interpretation lives there (M16 keeps predecessor-first
semantics; the M17C-C classification keeps its own guarded decode and
its authenticate-before-classification law unchanged). All three M16
ShotRevision reads consume the shared boundary.

The battery proves the commission's frozen shapes on a lawful
head-0023 mixed-successor database (a GENUINE schema<8 revision plus
lawful schema-8 state as the green control): malformed JSON, an
actual invalid-UTF-8 SQLite BLOB, and valid non-object ``[]`` (with
a coherent hash, isolating the object-shape law) — each refused by
the direct M17C-C verifier AND the full staged restore through the
typed corruption contract, never a raw Python exception (the backup
manifest is rehashed so the restore reaches semantic verification
rather than failing artifact authentication first; the malformed
shapes intentionally carry stale snapshot identity — no canonical
form exists to recompute).
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world

_HEAD_0023 = "0023_m17cc_capture_closure_preimage"


def _live_root(client):
    return client._transport.app.state.settings.data_dir


async def _stage_mixed_successor(client):
    """The lawful head-0023 mixed-successor world: a GENUINE
    historical schema<8 revision (captured before any performance
    mappings existed) alongside a lawful schema-8 revision."""
    world = await _bound_world(client)
    old_revision, _visual = await _capture(client, world["shot"])
    await _lawful(client, world, extra=True)
    new_revision, _visual = await _capture(client, world["shot"])
    return world, old_revision, new_revision


async def _backup(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, f"rr16-{tag}")


# ---------------------------------------------------------------------------
# The green control — the lawful mixed-successor database
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr16_lawful_mixed_successor_green_both_surfaces(
        client, tmp_path):
    """The green control: a genuine schema<8 revision plus lawful
    schema-8 state verifies green on the direct M17C-C verifier AND
    restores successfully through the full predecessor chain."""
    from soloring.recovery import restore as rb_restore
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )

    world, old_revision, new_revision = await _stage_mixed_successor(
        client)
    root = await _backup(client, tmp_path, "clean")

    verify_m17c_binding_state(
        root / "soloring.db", root / "blobs", head=_HEAD_0023)

    dest = tmp_path / "rr16-clean-restored"
    await rb_restore(root, dest)
    assert (dest / "soloring.db").is_file()


# ---------------------------------------------------------------------------
# The frozen malformed shapes — typed on BOTH surfaces
# ---------------------------------------------------------------------------

def _tamper(root, revision_id, mode):
    from soloring.domain.canonical import canonical_hash as _ch
    con = sqlite3.connect(root / "soloring.db")
    try:
        if mode == "malformed_json":
            # stale identity is INTENTIONAL here: no canonical form of
            # malformed bytes exists to recompute
            con.execute(
                "UPDATE shot_revisions SET snapshot_json = ? "
                "WHERE id = ?", ('{"broken":', revision_id))
        elif mode == "invalid_utf8_blob":
            con.execute(
                "UPDATE shot_revisions SET snapshot_json = ? "
                "WHERE id = ?", (b"\xff\xfe\x00garbage", revision_id))
        elif mode == "non_object":
            # a COHERENT hash isolates the object-shape law from any
            # hash-divergence law
            con.execute(
                "UPDATE shot_revisions SET snapshot_json = ?, "
                "snapshot_hash = ? WHERE id = ?",
                ("[]", _ch([]), revision_id))
        con.commit()
        if mode == "invalid_utf8_blob":
            stored = con.execute(
                "SELECT typeof(snapshot_json) FROM shot_revisions "
                "WHERE id = ?", (revision_id,)).fetchone()[0]
            assert stored == "blob", stored
        return con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (revision_id,)).fetchone()[0]
    finally:
        con.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,direct_fragment,restore_fragment", [
    ("malformed_json",
     "snapshot_json is not decodable",
     "snapshot_json is not decodable persisted JSON"),
    ("invalid_utf8_blob",
     "snapshot_json is not decodable",
     "snapshot_json is not decodable persisted JSON"),
    ("non_object",
     "snapshot is not a JSON object",
     "snapshot is not a JSON object"),
])
async def test_rr1601_malformed_outer_snapshots_typed_both_surfaces(
        client, tmp_path, mode, direct_fragment, restore_fragment):
    """Each frozen malformed shape on the OLD revision of a lawful
    mixed-successor database: the direct M17C-C verifier refuses
    through its typed contract, and the full staged restore (the
    M16-first predecessor chain) refuses through the shared total
    parser's typed contract — never JSONDecodeError,
    UnicodeDecodeError, AttributeError, or any other raw exception."""
    from soloring.recovery import restore as rb_restore
    from soloring.recovery.backup import RecoveryCorruption
    from soloring.recovery.m17c_verifier import (
        verify_m17c_binding_state,
    )
    from tests.test_m17c_sr26_regressions import _rehash_manifest

    world, old_revision, new_revision = await _stage_mixed_successor(
        client)
    root = await _backup(client, tmp_path, mode)

    stored = _tamper(root, old_revision.id, mode)
    assert not isinstance(stored, dict)

    # the direct M17C-C verifier: typed (SoloRingError carrying the
    # RECOVERY_CORRUPTION code — the M17C-C chain's own corruption
    # contract), with its guarded-decode wording
    from soloring.errors import SoloRingError
    with pytest.raises(SoloRingError) as direct:
        verify_m17c_binding_state(
            root / "soloring.db", root / "blobs", head=_HEAD_0023)
    assert direct.value.code == "RECOVERY_CORRUPTION"
    assert direct_fragment in direct.value.message, direct.value.message

    # the full staged restore reaches SEMANTIC verification (the
    # manifest is rehashed so artifact authentication passes) and the
    # M16-first predecessor chain refuses through the shared total
    # parser — the typed RecoveryCorruption class itself is the
    # never-raw proof (a raw JSONDecodeError/UnicodeDecodeError/
    # AttributeError is not this class)
    _rehash_manifest(root)
    dest = tmp_path / f"rr16-refused-{mode}"
    with pytest.raises(RecoveryCorruption) as restored:
        await rb_restore(root, dest)
    assert restore_fragment in str(restored.value), str(restored.value)
    assert not dest.exists()
