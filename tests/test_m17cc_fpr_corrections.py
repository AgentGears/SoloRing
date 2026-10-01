"""M17C-C first-pass-review corrections (frozen register
FPR-M17CC-01..08) — the reviewer's verification demands, one battery.

- FPR-01: schema-8 realization is a TERMINAL typed refusal at the
  Generation seam — an 8-over-7 capture can no longer bypass the M16
  capability refusal, and 8-over-5/6/plain-8 can no longer silently
  drop captured spatial/observation predecessor authority; nothing
  persists.
- FPR-02: the effective working hash is built by the SAME
  performance-aware canonical construction capture uses — unchanged
  Performance equals the captured hash; a Performance-only change
  moves it.
- FPR-03: observation readiness on an 8-over-6 capture is the
  successor-aware schema-6 posture (not "not-applicable"), and its
  is_current incorporates the Performance plane.
- FPR-04: tampering ONLY performance_mapping_hash or ONLY
  vocal_mapping_hash refuses at BOTH the §12 reader and §13.4
  recovery.
- FPR-05: deleting or corrupting the retained PR payload FILE (DB row
  intact) fails the §12 historical read closed.
- FPR-06: the §13.6 translation identity is IDENTITY EQUALITY at the
  frozen WorkflowSpec coordinate — the same string appearing in an
  unrelated field does not certify a wrong identity, and an unrelated
  duplicate does not refuse a correct one.
- FPR-07: the pure builder wraps ANY schema-1-7 base — including the
  zero-dependency schema-1 cell.
"""

from __future__ import annotations

import base64
import json
import sqlite3

import pytest

from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world, _seg_body

_PARENTS = "shot_revision_performance_specs"
_CHILDREN = "shot_revision_performance_segments"
_HEAD = "0023_m17cc_capture_closure_preimage"
_TRANSLATION_ID = "soloring-executor-translation-facial-liveportrait/1"


def _engine(client):
    return client._transport.app.state.engine


async def _sql(client, stmt, params=None):
    from sqlalchemy import text
    async with _engine(client).begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _row(client, stmt, params=None):
    from sqlalchemy import text
    async with _engine(client).connect() as conn:
        return dict((await conn.execute(
            text(stmt), params or {})).mappings().one())


async def _stage(client, *, extra=True):
    world = await _bound_world(client)
    await _lawful(client, world, extra=extra)
    revision, _visual = await _capture(client, world["shot"])
    return world, revision


async def _backup(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, f"m17cc-fpr-{tag}")


async def _add_reference(client, world):
    from soloring.db.models import Asset, Blob
    from soloring.domain.ids import new_uuid
    from tests.conftest import make_tracked_maker
    from tests.m17a_seed import place_blob

    engine = _engine(client)
    aid = new_uuid()
    bh = await place_blob(client, b"m17cc-fpr-reference-image")
    factory = make_tracked_maker(engine)
    async with factory() as s:
        blob = await s.get(Blob, bh)
        if blob is None:
            s.add(Blob(hash=bh,
                       path=f"sha256/{bh[:2]}/{bh[2:4]}/{bh}",
                       size_bytes=1))
        s.add(Asset(id=aid, project_id=world["project_id"],
                    blob_hash=bh, kind="reference"))
        await s.commit()
    r = await client.put(
        f"/shots/{world['shot']}/references",
        json={"references": [{"asset_id": aid, "role": "reference"}]})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# FPR-01 — the typed schema-8 realization refusal
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fpr01_schema8_generation_refuses_typed(client):
    """A plain schema-8 capture (no intra-shot/spatial/observation
    planes) refuses Generation with PERFORMANCE_REALIZATION_UNSUPPORTED
    and persists nothing."""
    world, revision = await _stage(client)
    await _add_reference(client, world)
    r = await client.post(f"/shots/{world['shot']}/generations")
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "PERFORMANCE_REALIZATION_UNSUPPORTED"
    assert "revision_id" in r.json()["details"] or \
        "shot_revision_id" in r.json()["details"]
    n = (await _row(client, "SELECT COUNT(*) AS n FROM generations",
                    ))["n"]
    assert n == 0


@pytest.mark.asyncio
async def test_fpr01_eight_over_seven_cannot_bypass_m16_refusal(client):
    """The motivating bypass: an 8-over-7 capture with non-empty M16
    events used to sail past INTRA_SHOT_REALIZATION_UNSUPPORTED; the
    successor refusal fires first and equally terminal."""
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
    snap = await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": revision.id})
    assert json.loads(snap["snapshot_json"])["schema_version"] == 8

    world = {"shot": sid, "project_id": base["project_id"]}
    await _add_reference(client, world)
    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "PERFORMANCE_REALIZATION_UNSUPPORTED"
    assert (await _row(client, (
        "SELECT COUNT(*) AS n FROM generations")))["n"] == 0


# ---------------------------------------------------------------------------
# FPR-02 — the performance-aware working-hash canon
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fpr02_working_hash_equals_captured_and_tracks_performance(
        client):
    world, revision = await _stage(client)

    detail = (await client.get(
        f"/shots/{world['shot']}")).json()
    working = detail.get("working_snapshot_hash")
    assert working == revision.snapshot_hash, (
        "the effective working hash must be built by the same "
        "performance-aware canonical construction capture uses")
    assert detail.get("working_state_differs_from_approved") is False

    # a Performance-ONLY change moves the hash
    from tests.m17b_seed import (
        HEAD_YAW, candidate_body, channel as m17b_channel,
        kf as m17b_kf,
    )
    newer = (await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "performance-candidates",
        json=candidate_body(
            [m17b_channel(HEAD_YAW, [m17b_kf(0, 2, 0)])]),
    )).json()
    newer_pr = (await client.post(
        f"/performance-candidates/{newer['id']}/adopt",
        json={"adopted_by": "fpr"})).json()
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/9",
        json=_seg_body(newer_pr["id"], 1500, 2000, 0))
    assert r.status_code == 200, r.text

    moved = (await client.get(f"/shots/{world['shot']}")).json()
    # RR-M17CC-02 (posture FROZEN): this mutation leaves the plane
    # lawfully non-READY (BLOCKED_CHANNEL_CONFLICT with the existing
    # BODY segment) — the authoritative working hash becomes
    # UNAVAILABLE, never a second uncapturable canon
    assert moved["working_snapshot_hash"] is None
    assert moved["working_state_differs_from_approved"] is None

    # removing the change returns the captured hash exactly
    await _sql(client, "DELETE FROM shot_performance_segment_mappings "
                       "WHERE shot_id = :s AND position = 9",
               {"s": world["shot"]})
    restored = (await client.get(f"/shots/{world['shot']}")).json()
    assert restored["working_snapshot_hash"] == revision.snapshot_hash
    assert restored["working_state_differs_from_approved"] is False


# ---------------------------------------------------------------------------
# FPR-03 — successor-aware observation readiness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fpr03_observation_readiness_on_eight_over_six(client):
    """A schema-8 wrap of a schema-6 predecessor keeps the observation
    plane applicable (the production_world block survives the wrap),
    and is_current incorporates the Performance plane."""
    from tests.m17c_seed import ARTICULATION, dialogue_bound_body, make_vp
    from tests.test_m13_history import _captured_world

    # a captured schema-6 world (M13 production-world selected)
    b, sel, rev6 = await _captured_world(client, tag=b"fpr-o36")
    sid = b["shot"]

    vp_world = await make_vp(client, pid=b["pid"], eid=b["eva"])
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
        f"/creative-entities/{b['eva']}/"
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

    before = (await client.get(
        f"/shots/{sid}/observation-readiness")).json()
    assert before["capture"]["schema_version"] == 6

    revision, _visual = await _capture(client, sid)
    after = (await client.get(
        f"/shots/{sid}/observation-readiness")).json()
    assert after["capture"]["schema_version"] == 8
    # successor-aware: the 8-over-6 wrap keeps the observation plane
    # ADDRESSABLE (not "not-applicable") — the readiness outcome is
    # the package policy's (refused/...) rather than a false claim
    # that the production world does not exist
    assert after["readiness"] != "not-applicable"
    assert "carries no production world" not in str(
        after.get("explanation", ""))
    # is_current incorporates the Performance plane: unchanged state
    # right after capture compares equal
    assert after["capture"]["is_current"] is True

    # a Performance-only mutation flips is_current
    from tests.m17b_seed import (
        HEAD_YAW, candidate_body, channel as m17b_channel,
        kf as m17b_kf,
    )
    newer = (await client.post(
        f"/creative-entities/{b['eva']}/"
        "performance-candidates",
        json=candidate_body(
            [m17b_channel(HEAD_YAW, [m17b_kf(0, 2, 0)])]),
    )).json()
    newer_pr = (await client.post(
        f"/performance-candidates/{newer['id']}/adopt",
        json={"adopted_by": "fpr"})).json()
    r = await client.put(
        f"/shots/{sid}/performance-segments/9",
        json=_seg_body(newer_pr["id"], 1500, 2000, 0))
    assert r.status_code == 200, r.text
    diverged = (await client.get(
        f"/shots/{sid}/observation-readiness")).json()
    assert diverged["capture"]["is_current"] is False


# ---------------------------------------------------------------------------
# FPR-04 — mapping-hash tamper refuses everywhere
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("column", [
    "performance_mapping_hash", "vocal_mapping_hash",
])
async def test_fpr04_mapping_hash_only_tamper_refuses(client, tmp_path,
                                                      column):
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    from soloring.errors import SoloRingError

    world, revision = await _stage(client)
    root = await _backup(client, tmp_path, f"mh-{column}")

    async def _tamper(db):
        con = sqlite3.connect(db)
        con.execute(
            f"UPDATE {_CHILDREN} SET {column} = ? "
            "WHERE shot_revision_id = ? AND position = 0",
            ("e" * 64, revision.id))
        con.commit()
        con.close()

    # the §12 public reader refuses
    await _tamper(client._transport.app.state.settings.data_dir
                  / "soloring.db")
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert "mapping_hash disagrees" in r.json()["message"], r.text

    # recovery refuses on the staged copy
    await _tamper(root / "soloring.db")
    with pytest.raises(SoloRingError) as excinfo:
        verify_m17c_binding_state(root / "soloring.db", root / "blobs",
                                  head=_HEAD)
    assert excinfo.value.code == "RECOVERY_CORRUPTION"
    assert "mapping_hash disagrees" in excinfo.value.message


# ---------------------------------------------------------------------------
# FPR-05 — physical payload bytes fail closed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["missing", "corrupt"])
async def test_fpr05_physical_payload_loss_fails_closed(client, mode):
    world, revision = await _stage(client)
    h = (await _row(client, (
        "SELECT canonical_channel_payload_blob_hash AS h FROM "
        "performance_revisions WHERE id = :p"),
        {"p": world["pr"]["id"]}))["h"]
    blob_dir = client._transport.app.state.settings.blob_dir
    path = blob_dir / "sha256" / h[:2] / h[2:4] / h

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    # the frozen answer carries the EXACT retained bytes
    payload = r.json()["performance"]["segments"][0][
        "performance_payload"]
    assert base64.b64decode(payload["payload_bytes_base64"]) == \
        path.read_bytes()

    if mode == "missing":
        path.unlink()
        fragment = "physically missing"
    else:
        path.write_bytes(path.read_bytes()[:-1])
        fragment = "does not rehash"

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert fragment in r.json()["message"], r.text


# ---------------------------------------------------------------------------
# FPR-06 — identity equality at the frozen coordinate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fpr06_translation_identity_is_the_coordinate(client,
                                                             tmp_path):
    from soloring.recovery.m17c_verifier import verify_m17c_binding_state
    from tests.m17a_seed import place_blob

    def _gpi(root, gen_id, revision_id, blob, translation, spec):
        from soloring.domain.canonical import (
            canonical_hash as _ch, canonical_json_str as _cj,
        )
        con = sqlite3.connect(root / "soloring.db")
        child = con.execute(
            f"SELECT performance_revision_id, "
            f"vocal_performance_revision_id, vocal_binding_hash, "
            f"segment_hash FROM {_CHILDREN} WHERE shot_revision_id = ? "
            "AND position = 0", (revision_id,)).fetchone()
        created = con.execute(
            "SELECT created_at FROM generations WHERE id = ?",
            (gen_id,)).fetchone()[0]
        con.execute(
            "UPDATE generations SET workflow_spec_json = ?, "
            "workflow_spec_hash = ? WHERE id = ?",
            (_cj(spec), _ch(spec), gen_id))
        con.execute(
            f"INSERT INTO generation_performance_inputs ("
            "generation_id, input_key, position, artifact_role, "
            "shot_revision_segment_position, performance_revision_id, "
            "vocal_performance_revision_id, blob_hash, binding_hash, "
            "segment_hash, translation_identity, derived_input_hash, "
            "created_at) VALUES (?, 'performance:0', 0, "
            "'performance.controls', 0, ?, ?, ?, ?, ?, ?, ?, ?)",
            (gen_id, child[0], child[1], blob, child[2], child[3],
             translation, "7" * 64, created))
        con.commit()
        con.close()

    def _gen(root, shot_id, revision_id, spec):
        from soloring.domain.canonical import (
            canonical_hash as _ch, canonical_json_str as _cj,
        )
        from soloring.domain.ids import new_uuid

        gen_id = new_uuid()
        template_hash, manifest_hash = _artifacts(root)
        now = "2026-10-01T00:00:00.000Z"
        con = sqlite3.connect(root / "soloring.db")
        con.execute(
            "INSERT INTO generations (id, shot_id, shot_revision_id, "
            "generation_number, status, operation, executor, "
            "workflow_id, workflow_version, workflow_template_hash, "
            "manifest_hash, compiled_prompt, prompt_compiler_version, "
            "parameters_json, workflow_spec_json, workflow_spec_hash, "
            "created_at, updated_at, queued_at, "
            "executor_submission_state) VALUES "
            "(?, ?, ?, 1, 'queued', 'generate', 'fake', 'w', 1, ?, ?, "
            "'p', '1', '{}', ?, ?, ?, ?, ?, 'not_started')",
            (gen_id, shot_id, revision_id, template_hash, manifest_hash,
             _cj(spec), _ch(spec), now, now, now))
        con.commit()
        con.close()
        return gen_id

    def _artifacts(root):
        import hashlib

        def _p(kind, content):
            h = hashlib.sha256(content).hexdigest()
            p = root / "workflow-artifacts" / kind / "sha256" / \
                h[:2] / h[2:4] / f"{h}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
            return h

        return (_p("templates", b"fpr-template"),
                _p("manifests", b'{"fixture": "fpr"}'))

    world, revision = await _stage(client)
    blob = await place_blob(client, b"fpr-derived-bytes")
    data_dir = client._transport.app.state.settings.data_dir

    # PASS: the dedicated coordinate equals the identity — an
    # UNRELATED duplicate field changes nothing
    root1 = await _backup(client, tmp_path, "id-pass")
    _stage_blob(root1, blob, b"fpr-derived-bytes")
    spec = {"schema_version": 1, "inputs": {},
            "performance_translation": _TRANSLATION_ID,
            "unrelated_note": _TRANSLATION_ID}
    gen1 = _gen(root1, world["shot"], revision.id, spec)
    _gpi(root1, gen1, revision.id, blob, _TRANSLATION_ID, spec)
    verify_m17c_binding_state(root1 / "soloring.db", root1 / "blobs",
                              head=_HEAD)

    # REFUSE: the identity appears ONLY in an unrelated field while
    # the dedicated coordinate names something else
    root2 = await _backup(client, tmp_path, "id-unrelated")
    _stage_blob(root2, blob, b"fpr-derived-bytes")
    wrong = "soloring-executor-translation-alp/9"
    spec2 = {"schema_version": 1, "inputs": {},
             "performance_translation": wrong,
             "unrelated_note": _TRANSLATION_ID}
    gen2 = _gen(root2, world["shot"], revision.id, spec2)
    _gpi(root2, gen2, revision.id, blob, _TRANSLATION_ID, spec2)
    from soloring.errors import SoloRingError
    with pytest.raises(SoloRingError) as excinfo:
        verify_m17c_binding_state(root2 / "soloring.db", root2 / "blobs",
                                  head=_HEAD)
    assert excinfo.value.code == "RECOVERY_CORRUPTION"
    assert "translation_identity disagrees with the WorkflowSpec" \
        in excinfo.value.message


def _stage_blob(root, blob_hash, data):
    p = root / "blobs" / "sha256" / blob_hash[:2] / blob_hash[2:4] / \
        blob_hash
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


# ---------------------------------------------------------------------------
# FPR-07 — the pure builder wraps the schema-1 base
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fpr07_builder_wraps_zero_dependency_schema1(client):
    from soloring.continuity.snapshots import build_capturable_snapshot

    class _Shot:
        id = "00000000-0000-4000-8000-000000000001"
        subject = "s"
        action = "a"
        environment = "e"
        framing = "f"
        camera_motion = "cm"
        lens = "l"
        mood = "m"
        duration_ms = 3000

    base, _spec = build_capturable_snapshot(_Shot(), [], [])
    assert base["schema_version"] == 1

    from tests.m17cc_capture_helper import _factory
    pack = {"schema_version": 2, "segments": [{
        "position": 0,
        "subject_id": "00000000-0000-4000-8000-000000000002",
        "performance_revision_id":
            "00000000-0000-4000-8000-000000000003",
        "performance_payload_sha256": "a" * 64,
        "performance_payload_blob_hash": "b" * 64,
        "performance_profile_id": "performance-profile/1",
        "performance_kind": "FACIAL",
        "performance_start_ms": {"num": 0, "den": 1},
        "performance_end_ms": {"num": 1000, "den": 1},
        "shot_anchor_ms": {"num": 0, "den": 1},
        "mapping_hash": "c" * 64,
        "performance_mapping_hash": "c" * 64,
        "vocal": None,
        "vocal_mapping_hash": None,
        "vocal_mapping_position": None,
        "vocal_performance_origin_ms": None,
    }]}
    wrapped, _ = build_capturable_snapshot(
        _Shot(), [], [], performance_pack=pack)
    assert wrapped["schema_version"] == 8
    inner = {k: v for k, v in wrapped.items()
             if k not in ("performance", "schema_version")}
    assert inner == {k: v for k, v in base.items()
                     if k != "schema_version"}
    assert wrapped["performance"]["segments"][0]["vocal"] is None
