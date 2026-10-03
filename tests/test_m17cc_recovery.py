"""M17C-C §13.4/§13.6 recovery-verifier regressions (frozen R4 §13).

The frozen rule: recovery independently proves that the durable
database can reconstruct and validate every M17C-C historical claim
without relying on current working state or the §12 API
implementation — it reuses the LAWS, never the reader. Laws proven:

- head behavior stays explicit: at 0022 the three capture tables are
  required and the §13.4/§13.6 passes run AFTER the unchanged
  predecessor laws; at 0020/0021 any companion/derived-input row
  refuses (rows those heads cannot represent);
- total schema classification: schema <8 ⇒ zero companions, schema 8
  ⇒ exactly one parent + non-empty canonical children, no in-between;
- snapshot↔parent↔children equivalence at canonical-BYTE strength;
- immutable authority closure revalidated independently (PR/VP/
  binding identity + hash agreement, retained payload Blob rehash);
- exact arithmetic recomputed (canonical rationals, non-empty
  interval, PR-domain containment, the §8.3 binding-induced interval
  reproduced with no tolerance, sample/trim containment);
- historical project/subject coherence (PR/shot project, VP speaker,
  VP lineage — never current dependency selection);
- the captured D14 channel-conflict law evaluated from captured
  history + retained payloads (disjoint-channel same-subject overlap
  is the LAWFUL shape and does not refuse);
- §13.6 structural derived-input laws (parent + creation-unit, role
  vocabulary, retained-byte rehash, exact segment tieback, vocal
  identity group, translation identity materialized in the execution
  spec) with the §14.6 sampler laws explicitly deferred to M17C-D;
- independence: with the §12 historical reader monkeypatched to
  explode, recovery still passes clean state and still refuses
  tampered state — the two surfaces agree because they implement the
  same frozen laws, not because one delegates;
- the full restore chain accepts a lawful schema-8 history (incl. a
  schema-8 wrap of a schema-7 predecessor — the M16 recovery verifier
  admits the wrap and reconstructs it through the unchanged history
  law).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world, _seg_body

_HEAD = "0023_m17cc_capture_closure_preimage"
_PARENTS = "shot_revision_performance_specs"
_CHILDREN = "shot_revision_performance_segments"
_GPI = "generation_performance_inputs"

_TRANSLATION_ID = "soloring-executor-translation-facial-liveportrait/1"


def _con(root):
    c = sqlite3.connect(root / "soloring.db")
    c.row_factory = sqlite3.Row
    return c


async def _live_snapshot(client, revision_id: str) -> dict:
    from sqlalchemy import text

    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        raw = (await conn.execute(text(
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision_id})).scalar_one()
    return json.loads(raw)


def _verify(root, head=_HEAD):
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    verify_m17c_binding_state(root / "soloring.db", root / "blobs",
                              head=head)


def _verify_refuses(root, fragment, head=_HEAD):
    from soloring.errors import SoloRingError
    with pytest.raises(SoloRingError) as excinfo:
        _verify(root, head=head)
    assert excinfo.value.code == "RECOVERY_CORRUPTION"
    assert fragment in excinfo.value.message, excinfo.value.message
    return excinfo.value


def _sql(root, stmt, params=()):
    con = _con(root)
    try:
        con.execute(stmt, params)
        con.commit()
    finally:
        con.close()


def _one(root, stmt, params=()):
    con = _con(root)
    try:
        return dict(con.execute(stmt, params).fetchone())
    finally:
        con.close()


def _stage_blob(root, blob_hash: str, data: bytes) -> None:
    """Fixture-construction: place derived-input bytes at the canonical
    path on the staged copy (the row referencing them is also a
    fixture — liveness at backup time knows nothing of it)."""
    p = root / "blobs" / "sha256" / blob_hash[:2] / blob_hash[2:4] / \
        blob_hash
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


async def _stage_schema8(client, tmp_path, tag, *, extra=True):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    await _lawful(client, world, extra=extra)
    revision, _visual = await _capture(client, world["shot"])
    root = await _backup_m17c(client, tmp_path, f"m17cc-r-{tag}")
    return root, world, revision.id


async def _stage_schema2(client, tmp_path, tag):
    """A predecessor-snapshot world: no performance mappings, so the
    capture emits the exact schema-2 predecessor bytes."""
    from tests.test_m17c_sr26_regressions import _backup_m17c
    world = await _bound_world(client)
    revision, _visual = await _capture(client, world["shot"])
    root = await _backup_m17c(client, tmp_path, f"m17cc-r2-{tag}")
    snap = json.loads(_one(root, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = ?"),
        (revision.id,))["snapshot_json"])
    assert snap["schema_version"] < 8
    return root, world, revision.id


_COLUMN_OF_EMBEDDED = {
    "performance_start_ms": "performance_start_num",
    "performance_end_ms": "performance_end_num",
    "shot_anchor_ms": "shot_anchor_num",
    "subject_id": "subject_id",
    "performance_revision_id": "performance_revision_id",
    "performance_payload_sha256": "performance_payload_sha256",
    "performance_profile_id": "performance_profile_id",
    "performance_kind": "performance_kind",
}


def _preimage_vocal_of(forged, seg):
    if seg["vocal"] is None:
        return None
    return {
        "vocal_performance_revision_id":
            forged["vocal_performance_revision_id"],
        "source_start_sample": forged["source_start_sample"],
        "source_end_sample_exclusive":
            forged["source_end_sample_exclusive"],
        "sample_rate_hz": forged["sample_rate_hz"],
        "vocal_performance_origin_ms": {
            "num": forged["vocal_performance_origin_num"],
            "den": forged["vocal_performance_origin_den"]},
    }


def _coherent_child_rewrite(root, revision_id, position, seg_updates,
                             pr_updates=()):
    """THE strong tamper shape: rewrite one captured segment
    EVERYWHERE coherently — embedded snapshot block, companion parent
    spec bytes/hash, and the child row's mirrored columns — so every
    internal-consistency law passes and only the laws that recompute
    against IMMUTABLE external authority can refuse."""
    from soloring.domain.canonical import (
        canonical_hash as _ch, canonical_json_str as _cj,
    )
    row = _one(root, (
        f"SELECT * FROM {_CHILDREN} WHERE shot_revision_id = ? "
        "AND position = ?"), (revision_id, position))
    rev = _one(root, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = ?"),
        (revision_id,))
    snap = json.loads(rev["snapshot_json"])
    spec = json.loads(_one(root, (
        f"SELECT spec_json FROM {_PARENTS} WHERE shot_revision_id = ?"),
        (revision_id,))["spec_json"])
    seg = spec["segments"][position]
    seg.update(seg_updates)
    snap["performance"]["segments"][position].update(seg_updates)

    # RR-M17CC-03: the mapping hashes are snapshot-anchored — a fully
    # coherent rewrite must ALSO rewrite the embedded segment's
    # mapping-hash/preimage fields (and every derived byte) so ONLY
    # the independent immutable-authority laws can refuse
    from soloring.performance.m17cc_capture_read import (
        expected_mapping_hashes,
    )
    forged = dict(row)
    for k, v in seg_updates.items():
        forged[_COLUMN_OF_EMBEDDED.get(k, k)] = v
    perf_hash, vocal_hash = expected_mapping_hashes(
        forged["performance_revision_id"],
        seg["performance_start_ms"], seg["performance_end_ms"],
        seg["shot_anchor_ms"], seg["vocal_mapping_position"],
        _preimage_vocal_of(forged, seg))
    seg["performance_mapping_hash"] = perf_hash
    seg["vocal_mapping_hash"] = vocal_hash
    snap_seg = snap["performance"]["segments"][position]
    snap_seg["performance_mapping_hash"] = perf_hash
    snap_seg["vocal_mapping_hash"] = vocal_hash

    parent_json, parent_hash = _cj(spec), _ch(spec)
    snap_json, snap_hash = _cj(snap), _ch(snap)
    seg_json, seg_hash = _cj(seg), _ch(seg)
    _sql(root, (
        f"UPDATE {_PARENTS} SET spec_json = ?, spec_hash = ? "
        "WHERE shot_revision_id = ?"),
        (parent_json, parent_hash, revision_id))
    _sql(root, (
        "UPDATE shot_revisions SET snapshot_json = ?, snapshot_hash = ? "
        "WHERE id = ?"), (snap_json, snap_hash, revision_id))
    columns = {
        "subject_id": seg["subject_id"],
        "performance_revision_id": seg["performance_revision_id"],
        "performance_payload_sha256":
            seg["performance_payload_sha256"],
        "performance_profile_id": seg["performance_profile_id"],
        "performance_kind": seg["performance_kind"],
        "performance_start_num":
            seg["performance_start_ms"]["num"],
        "performance_start_den":
            seg["performance_start_ms"]["den"],
        "performance_end_num": seg["performance_end_ms"]["num"],
        "performance_end_den": seg["performance_end_ms"]["den"],
        "shot_anchor_num": seg["shot_anchor_ms"]["num"],
        "shot_anchor_den": seg["shot_anchor_ms"]["den"],
        "segment_json": seg_json,
        "segment_hash": seg_hash,
    }
    # FPR-M17CC-08: fully NAMED parameters — the former named+positional
    # mix is a deprecation today and ProgrammingError under Python 3.14.
    # FPR-M17CC-04: the stored mapping hashes RECOMPUTE over the forged
    # preimage so the tamper is fully self-consistent and only the
    # immutable-authority laws can refuse.
    columns["performance_mapping_hash"] = perf_hash
    columns["vocal_mapping_hash"] = vocal_hash
    sets = ", ".join(f"{c} = :{c}" for c in columns)
    params = dict(columns)
    params["__rid"] = revision_id
    params["__pos"] = position
    _sql(root, (
        f"UPDATE {_CHILDREN} SET {sets} WHERE shot_revision_id = "
        ":__rid AND position = :__pos"), params)
    for column, value in pr_updates:
        _sql(root, (
            f"UPDATE performance_revisions SET {column} = ? "
            "WHERE id = ?"), (value, row["performance_revision_id"]))


@pytest.mark.asyncio
async def test_clean_schema8_history_passes_and_restores(
        client, tmp_path):
    """Lawful captured history passes the direct verifier AND the full
    restore chain (every predecessor verifier first — gate: recovery
    extends the chain)."""
    from soloring.recovery.backup import restore as rb_restore
    root, world, revision_id = await _stage_schema8(
        client, tmp_path, "clean")
    _verify(root)

    dest = tmp_path / "m17cc-r-clean-restored"
    await rb_restore(root, dest)
    assert (dest / "soloring.db").is_file()
    _verify(dest)


@pytest.mark.asyncio
async def test_recovery_is_independent_of_the_section12_reader(
        client, tmp_path, monkeypatch):
    """With the public §12 historical reader disabled, recovery still
    passes clean state and still refuses tampered state — recovery
    reuses the frozen laws, never the reader."""
    import soloring.performance.m17cc_history as history

    def _explode(*args, **kwargs):
        raise AssertionError("the §12 reader must not be called")

    monkeypatch.setattr(history, "verify_performance_history", _explode)

    root, world, revision_id = await _stage_schema8(
        client, tmp_path, "indep")
    _verify(root)
    _sql(root, f"DELETE FROM {_PARENTS} WHERE shot_revision_id = ?",
         (revision_id,))
    _verify_refuses(root, "schema 8 without its performance "
                          "companion parent")


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper,fragment", [
    ("no_parent", "schema 8 without its performance companion parent"),
    ("empty_children", "empty companion child set"),
    ("child_count", "row count disagrees"),
    ("moved_position", "disagrees with the embedded captured ordering"),
    ("altered_field", "column subject_id disagrees"),
    ("altered_segment_json",
     "segment_json/segment_hash disagree"),
    ("altered_spec_json",
     "spec_json/spec_hash disagree with canonical bytes"),
    ("snapshot_block", "snapshot performance block bytes disagree"),
    ("pr_mismatch",
     "disagrees with the immutable PerformanceRevision"),
    ("missing_binding", "binding companion is missing"),
    ("vocal_group_nulled",
     "vocal_mapping_hash disagrees with the embedded"),
    ("payload_blob_missing", "payload blob"),
    ("payload_blob_corrupt", "does not rehash"),
    ("timing_mismatch", "exact binding-induced interval"),
    ("subject_mismatch", "subject != bound VP speaker"),
    ("cross_project", "crosses projects"),
    ("overlap_conflict", "channel-conflict law is checked against"),
])
async def test_captured_schema8_tamper_matrix(
        client, tmp_path, tamper, fragment):
    root, world, revision_id = await _stage_schema8(
        client, tmp_path, f"m-{tamper}")

    if tamper == "no_parent":
        _sql(root, f"DELETE FROM {_PARENTS} WHERE shot_revision_id = ?",
             (revision_id,))
    elif tamper == "empty_children":
        _sql(root, f"DELETE FROM {_CHILDREN} WHERE shot_revision_id = ?",
             (revision_id,))
    elif tamper == "child_count":
        _sql(root, f"DELETE FROM {_CHILDREN} WHERE shot_revision_id = ? "
             "AND position = 1", (revision_id,))
    elif tamper == "moved_position":
        _sql(root, f"UPDATE {_CHILDREN} SET position = 5 "
             "WHERE shot_revision_id = ? AND position = 0",
             (revision_id,))
    elif tamper == "altered_field":
        _sql(root, f"UPDATE {_CHILDREN} SET subject_id = "
             "'00000000-0000-4000-8000-0000000000ff' "
             "WHERE shot_revision_id = ? AND position = 0",
             (revision_id,))
    elif tamper == "altered_segment_json":
        _sql(root, f"UPDATE {_CHILDREN} SET segment_json = "
             "'{}' WHERE shot_revision_id = ? AND position = 0",
             (revision_id,))
    elif tamper == "altered_spec_json":
        _sql(root, f"UPDATE {_PARENTS} SET spec_json = "
             "'{\"schema_version\": 1, \"segments\": []}' "
             "WHERE shot_revision_id = ?", (revision_id,))
    elif tamper == "snapshot_block":
        # coherent OUTER rewrite (snapshot_hash kept consistent) so the
        # ONLY disagreement is the snapshot block vs the parent bytes
        from soloring.domain.canonical import (
            canonical_hash as _ch, canonical_json_str as _cj,
        )
        snap = json.loads(_one(root, (
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?"),
            (revision_id,))["snapshot_json"])
        snap["performance"]["segments"][0]["shot_anchor_ms"] = \
            {"num": 7, "den": 1}
        _sql(root, (
            "UPDATE shot_revisions SET snapshot_json = ?, "
            "snapshot_hash = ? WHERE id = ?"),
            (_cj(snap), _ch(snap), revision_id))
    elif tamper == "pr_mismatch":
        _sql(root, "UPDATE performance_revisions SET "
             "performance_kind = 'BODY' WHERE id = ?",
             (world["pr"]["id"],))
    elif tamper == "missing_binding":
        _sql(root, "DELETE FROM "
             "performance_revision_vocal_bindings "
             "WHERE performance_revision_id = ?", (world["pr"]["id"],))
    elif tamper == "vocal_group_nulled":
        _sql(root, f"UPDATE {_CHILDREN} SET "
             "vocal_performance_revision_id = NULL, "
             "vocal_binding_hash = NULL, vocal_mapping_hash = NULL, "
             "source_start_sample = NULL, "
             "source_end_sample_exclusive = NULL, "
             "sample_rate_hz = NULL, "
             "vocal_performance_origin_num = NULL, "
             "vocal_performance_origin_den = NULL, "
             "vocal_mapping_position = NULL "
             "WHERE shot_revision_id = ? "
             "AND position = 0", (revision_id,))
    elif tamper == "payload_blob_missing":
        h = _one(root, (
            "SELECT canonical_channel_payload_blob_hash AS h FROM "
            "performance_revisions WHERE id = ?"),
            (world["pr"]["id"],))["h"]
        (root / "blobs" / "sha256" / h[:2] / h[2:4] / h).unlink()
    elif tamper == "payload_blob_corrupt":
        h = _one(root, (
            "SELECT canonical_channel_payload_blob_hash AS h FROM "
            "performance_revisions WHERE id = ?"),
            (world["pr"]["id"],))["h"]
        p = root / "blobs" / "sha256" / h[:2] / h[2:4] / h
        p.write_bytes(p.read_bytes()[:-1])
    elif tamper == "timing_mismatch":
        # coherent EVERYWHERE (embedded + parent + child columns) —
        # only the recomputed §8.3 binding induction can refuse
        _coherent_child_rewrite(
            root, revision_id, 0,
            {"performance_start_ms": {"num": 100, "den": 1}})
    elif tamper == "subject_mismatch":
        # child, embedded, and the PR row agree on the forged subject;
        # the immutable VP speaker disagrees — subject/speaker
        # agreement is historical
        forged = "00000000-0000-4000-8000-0000000000ee"
        _coherent_child_rewrite(
            root, revision_id, 0, {"subject_id": forged},
            pr_updates=[("subject_id", forged)])
    elif tamper == "cross_project":
        _sql(root, "UPDATE performance_revisions SET project_id = "
             "'00000000-0000-4000-8000-0000000000dd' WHERE id = ?",
             (world["pr"]["id"],))
    elif tamper == "overlap_conflict":
        # coherent: the generic child now names the SAME dialogue PR —
        # same subject, overlapping intervals, SHARED channels; only
        # the captured conflict law can refuse
        pr = _one(root, (
            "SELECT id, canonical_channel_payload_sha256 AS sha, "
            "performance_profile_id AS profile, performance_kind "
            "AS kind FROM performance_revisions WHERE id = ?"),
            (world["pr"]["id"],))
        _coherent_child_rewrite(
            root, revision_id, 1,
            {"performance_revision_id": pr["id"],
             "performance_payload_sha256": pr["sha"],
             "performance_profile_id": pr["profile"],
             "performance_kind": pr["kind"]})
        # the child's blob-hash column must follow the renamed PR
        _sql(root, f"UPDATE {_CHILDREN} SET "
             "performance_payload_blob_hash = "
             "(SELECT canonical_channel_payload_blob_hash FROM "
             "performance_revisions WHERE id = ?) "
             f"WHERE shot_revision_id = ? AND position = 1",
             (pr["id"], revision_id))

    _verify_refuses(root, fragment)


@pytest.mark.asyncio
async def test_schema_below8_companions_refuse_at_every_head(
        client, tmp_path):
    """Total classification: a predecessor-snapshot revision carrying
    companion rows refuses — at 0022 through the classification law,
    and at 0021 through the head law (rows the head cannot
    represent)."""
    root, world, revision_id = await _stage_schema2(client, tmp_path,
                                                    "below8")
    _sql(root, f"INSERT INTO {_PARENTS} (shot_revision_id, "
         "schema_version, spec_json, spec_hash) VALUES (?, 1, "
         "'{\"schema_version\": 1, \"segments\": []}', ?)",
         (revision_id, "0" * 64))
    _verify_refuses(root, "with M17C-C companion rows")

    _sql(root, "UPDATE alembic_version SET version_num = "
         "'0021_m17c_shot_performance_mappings'")
    _verify_refuses(root, "carries shot_revision_performance_specs "
                         "rows", head="0021_m17c_shot_performance_mappings")


@pytest.mark.asyncio
async def test_8_over_7_restore_roundtrip(client, tmp_path):
    """The M16 recovery verifier admits the §11.5 schema-8 wrap: a
    schema-8 capture over a schema-7 predecessor restores through the
    FULL chain with both planes verified."""
    from soloring.recovery.backup import restore as rb_restore
    from tests.m16_seed_b import (
        event, post_event, seed_feature_world, state,
    )
    from tests.m17c_seed import ARTICULATION, dialogue_bound_body, make_vp
    from tests.m17cc_capture_helper import _factory
    from tests.test_m17c_shot_mapping import _add_dependency

    base = await seed_feature_world(client, _factory(client))
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(),
                                        state("fresh")))
    vp_world = await make_vp(client, pid=base["project_id"],
                             eid=base["entity_id"])
    r = await client.put(
        f"/dialogue-line-revisions/"
        f"{vp_world['dialogue_line_revision_id']}/vocal-selection",
        json={"vocal_performance_revision_id": vp_world["vp"]["id"],
              "selected_by": "d"})
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{sid}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": vp_world["vp"]["id"],
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 0, "den": 1},
        })
    assert r.status_code == 200, r.text
    candidate = (await client.post(
        f"/creative-entities/{base['entity_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            vp_world["vp"]["id"],
            articulation_time={key: (600, 1) for key in ARTICULATION}),
    )).json()
    pr = (await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "d"})).json()
    r = await client.put(
        f"/shots/{sid}/performance-segments/0",
        json=_seg_body(pr["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text

    revision, _visual = await _capture(client, sid)
    from tests.test_m17c_sr26_regressions import _backup_m17c
    root = await _backup_m17c(client, tmp_path, "m17cc-87")
    snap = json.loads(_one(root, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = ?"),
        (revision.id,))["snapshot_json"])
    assert snap["schema_version"] == 8 and "intra_shot" in snap
    _verify(root)
    dest = tmp_path / "m17cc-87-restored"
    await rb_restore(root, dest)
    assert (dest / "soloring.db").is_file()


# ---------------------------------------------------------------------------
# §13.6: structural Generation-owned derived-input laws
# ---------------------------------------------------------------------------

async def _add_reference(client, shot_id: str, project_id: str) -> None:
    """One reference_image input so generation creation resolves (the
    m5a9 seeding pattern over a REAL placed Blob)."""
    from soloring.db.models import Asset
    from soloring.domain.ids import new_uuid
    from soloring.db.models import Blob
    from tests.conftest import make_tracked_maker
    from tests.m17a_seed import place_blob

    engine = client._transport.app.state.engine
    aid = new_uuid()
    bh = await place_blob(client, b"m17cc-gpi-reference-image")
    factory = make_tracked_maker(engine)
    async with factory() as s:
        blob = await s.get(Blob, bh)
        if blob is None:
            s.add(Blob(hash=bh,
                       path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                       size_bytes=1))
        s.add(Asset(id=aid, project_id=project_id,
                    blob_hash=bh, kind="reference"))
        await s.commit()
    r = await client.put(
        f"/shots/{shot_id}/references",
        json={"references": [{"asset_id": aid, "role": "reference"}]})
    assert r.status_code == 200, r.text


async def _make_generation(client, world):
    await _add_reference(client, world["shot"], world["project_id"])
    r = await client.post(f"/shots/{world['shot']}/generations")
    assert r.status_code == 202, r.text
    return r.json()


async def _stage_with_generation(client, tmp_path, tag):
    """A schema-8 world staged with a FIXTURE generation row inserted
    on the staged copy (the m13-history pattern: recovery verifies
    rows fixtures construct — it never writes them, and the fixture
    avoids dragging workflow-artifact liveness into the backup)."""
    from tests.test_m17c_sr26_regressions import _backup_m17c

    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    blob = hashlib.sha256(b"m17cc-gpi-derived-bytes").hexdigest()
    root = await _backup_m17c(client, tmp_path, f"m17cc-gpi-{tag}")
    _stage_blob(root, blob, b"m17cc-gpi-derived-bytes")
    gen_id = _insert_fixture_generation(root, world["shot"],
                                        revision.id)
    _materialize_translation(root, gen_id, _TRANSLATION_ID)
    return root, world, revision.id, gen_id, blob


def _insert_fixture_generation(root, shot_id: str,
                               revision_id: str) -> str:
    from soloring.domain.canonical import (
        canonical_hash as _ch, canonical_json_str as _cj,
    )
    from soloring.domain.ids import new_uuid

    gen_id = new_uuid()
    spec = {"schema_version": 1,
            "performance_translation": _TRANSLATION_ID}
    _sql(root, (
        "INSERT INTO generations (id, shot_id, shot_revision_id, "
        "generation_number, status, operation, executor, workflow_id, "
        "workflow_version, workflow_template_hash, manifest_hash, "
        "compiled_prompt, prompt_compiler_version, parameters_json, "
        "workflow_spec_json, workflow_spec_hash, created_at, "
        "updated_at, queued_at, executor_submission_state) VALUES "
        "(?, ?, ?, 1, 'queued', 'generate', 'fake', 'w', 1, ?, ?, "
        "'p', '1', '{}', ?, ?, ?, ?, ?, 'not_started')"),
        (gen_id, shot_id, revision_id, "1" * 64, "2" * 64,
         _cj(spec), _ch(spec),
         "2026-09-30T00:00:00.000Z", "2026-09-30T00:00:00.000Z",
         "2026-09-30T00:00:00.000Z"))
    return gen_id


def _insert_gpi(root, gen_id, revision_id, blob, *, role="performance.controls",
                key="performance:0", position=0, seg_pos=0,
                translation=_TRANSLATION_ID, created_at=None,
                vid=None, binding=None, segment_hash=None,
                pr_id=None, derived=None, no_child=False):
    if no_child:
        child = {"performance_revision_id":
                 "00000000-0000-4000-8000-0000000000aa",
                 "vocal_performance_revision_id": None,
                 "vocal_binding_hash": None, "segment_hash": "c" * 64}
    else:
        child = _one(root, (
            f"SELECT performance_revision_id, "
            f"vocal_performance_revision_id, vocal_binding_hash, "
            f"segment_hash FROM {_CHILDREN} "
            "WHERE shot_revision_id = ? AND position = ?"),
            (revision_id, seg_pos))
    if created_at is None:
        created_at = _one(root, (
            "SELECT created_at FROM generations WHERE id = ?"),
            (gen_id,))["created_at"]
    _sql(root, (
        f"INSERT INTO {_GPI} (generation_id, input_key, position, "
        "artifact_role, shot_revision_segment_position, "
        "performance_revision_id, vocal_performance_revision_id, "
        "blob_hash, binding_hash, segment_hash, translation_identity, "
        "derived_input_hash, created_at) VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"),
        (gen_id, key, position, role, seg_pos,
         pr_id or child["performance_revision_id"],
         vid if vid is not None else child["vocal_performance_revision_id"],
         blob, binding if binding is not None
         else child["vocal_binding_hash"],
         segment_hash or child["segment_hash"],
         translation, derived or "a" * 64, created_at))


def _materialize_translation(root, gen_id, translation):
    """Fixture-construction: extend the staged Generation's execution
    spec with the translation identity (canonical rewrite, hash kept
    consistent)."""
    from soloring.domain.canonical import (
        canonical_hash as _ch, canonical_json_str as _cj,
    )
    spec = json.loads(_one(root, (
        "SELECT workflow_spec_json FROM generations WHERE id = ?"),
        (gen_id,))["workflow_spec_json"])
    spec["performance_translation"] = translation
    _sql(root, (
        "UPDATE generations SET workflow_spec_json = ?, "
        "workflow_spec_hash = ? WHERE id = ?"),
        (_cj(spec), _ch(spec), gen_id))


@pytest.mark.asyncio
async def test_gpi_structural_laws_pass_and_refuse(client, tmp_path):
    root, world, revision_id, gen_id, blob = (
        await _stage_with_generation(client, tmp_path, "main"))
    _materialize_translation(root, gen_id, _TRANSLATION_ID)

    # lawful controls + vocal_audio siblings over both captured
    # segments pass
    _insert_gpi(root, gen_id, revision_id, blob, role="performance.controls",
                key="performance:0", seg_pos=0)
    _insert_gpi(root, gen_id, revision_id, blob,
                role="performance.vocal_audio", key="performance:0:vocal",
                seg_pos=0)
    _insert_gpi(root, gen_id, revision_id, blob, role="performance.controls",
                key="performance:1", seg_pos=1)
    _verify(root)

    # each structural law refuses independently
    cases = [
        ("creation_unit", ("performance:0", 0), "creation unit",
         {"created_at": "1999-01-01T00:00:00.000Z"}),
        ("tieback_segment", ("performance:0", 0),
         "segment_hash does not tie back", {"segment_hash": "b" * 64}),
        ("tieback_pr", ("performance:0", 0),
         "performance_revision_id disagrees",
         {"pr_id": "00000000-0000-4000-8000-0000000000cc"}),
        ("vocal_identity", ("performance:0:vocal", 0),
         "vocal identity disagrees", {"vid": world["vp"]["id"]}),
        ("vocal_audio_bare", ("performance:1:vocal", 1),
         "without its vocal identity group", {"vid": None,
                                              "binding": None}),
        ("translation_identity", ("performance:0", 0),
         "disagrees with the WorkflowSpec performance_translation",
         {"translation": "soloring-executor-translation-alp/9"}),
        ("derived_hash_hex", ("performance:0", 0),
         "lowercase hex digest", {"derived": "A" * 64}),
        ("blob_missing", ("performance:0", 0),
         "retained derived-input blob", None),
    ]
    for name, (key, position), fragment, overrides in cases:
        bad_root, _, bad_rev, bad_gen, bad_blob = (
            await _stage_with_generation(client, tmp_path, name))
        _materialize_translation(bad_root, bad_gen, _TRANSLATION_ID)
        kw = dict(role="performance.controls", key=key, position=position,
                  seg_pos=0 if name != "vocal_audio_bare" else 1)
        if name == "vocal_audio_bare":
            kw["role"] = "performance.vocal_audio"
        if name == "vocal_identity":
            child = _one(bad_root, (
                f"SELECT vocal_binding_hash FROM {_CHILDREN} WHERE "
                "shot_revision_id = ? AND position = 0"), (bad_rev,))
            kw["vid"] = "00000000-0000-4000-8000-0000000000bb"
            kw["binding"] = child["vocal_binding_hash"]
        if overrides:
            kw.update(overrides)
        _insert_gpi(bad_root, bad_gen, bad_rev, bad_blob, **kw)
        if name == "blob_missing":
            (bad_root / "blobs" / "sha256" / bad_blob[:2]
             / bad_blob[2:4] / bad_blob).unlink()
        _verify_refuses(bad_root, fragment)

    # the role vocabulary is DB-CHECK pinned — unreachable by column
    # tamper (IntegrityError), with the verifier law as the mirror
    root2, _, rev2, gen2, blob2 = await _stage_with_generation(
        client, tmp_path, "role-pin")
    _materialize_translation(root2, gen2, _TRANSLATION_ID)
    with pytest.raises(sqlite3.IntegrityError):
        _insert_gpi(root2, gen2, rev2, blob2, role="performance.other",
                    key="performance:0")


@pytest.mark.asyncio
async def test_gpi_tieback_requires_schema8(client, tmp_path):
    """A derived input tying back to a predecessor-snapshot revision
    resolves to no captured schema-8 segment — the §13.6 tieback keeps
    the total classification."""
    from tests.test_m17c_sr26_regressions import _backup_m17c

    world = await _bound_world(client)
    revision, _visual = await _capture(client, world["shot"])
    snap_live = await _live_snapshot(client, revision.id)
    assert snap_live["schema_version"] < 8
    blob = hashlib.sha256(b"m17cc-gpi-predecessor").hexdigest()
    root = await _backup_m17c(client, tmp_path, "m17cc-r2-gpi2")
    _stage_blob(root, blob, b"m17cc-gpi-predecessor")
    gen_id = _insert_fixture_generation(root, world["shot"],
                                        revision.id)
    _insert_gpi(root, gen_id, revision.id, blob, no_child=True)
    _verify_refuses(root, "resolves to no captured schema-8 segment")
