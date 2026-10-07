"""M17C-D W2 — the create path (frozen plan R2-FINAL §2.1–§2.6):
the admission gates, the all-or-nothing translation, the v5 wrap,
the GPI writer in the ONE unit, and the frozen identity laws live
against the real HTTP surface."""

from __future__ import annotations

import hashlib
import json

import pytest

from tests.m16_seed_b import seed_feature_world
from tests.m17c_seed import dialogue_bound_body, make_vp
from tests.m17cc_capture_helper import _factory
from tests.test_m17c_shot_mapping import _add_dependency
from tests.test_m17cc_fpr_corrections import _add_reference


async def _capture_closed(client, shot_id):
    """The capture helper's tracked session is registry-kept until
    fixture teardown; batteries that stage MANY worlds per test must
    close each session to stay inside the engine pool."""
    from soloring.domain.revisions import capture_revision_with_visual

    async with _factory(client)() as session:
        return await capture_revision_with_visual(
            session, shot_id,
            settings=client._transport.app.state.settings)

_FPS_NUM, _FPS_DEN, _FRAMES = 25, 1, 25  # a 1 s picture grid


async def _performance_manifest(tmp_path, monkeypatch):
    """FPR32-M17CD-01 correction: install the REAL pinned
    performance/LivePortrait executor package
    (workflows/performance_liveportrait_v1 — the tracked contract)
    as the workflow directory. No synthetic fields on the Hunyuan
    KSampler: the pinned package's own manifest declares the
    performance segment inputs and the rasterization parameters at
    ITS graph nodes."""
    import shutil

    from soloring.workflows import manifest as manifest_module

    pinned = (manifest_module.BASE_DIR / "workflows" /
              "performance_liveportrait_v1")
    wf = tmp_path / "wf"
    if not wf.exists():
        shutil.copytree(pinned, wf)
    monkeypatch.setattr(manifest_module, "WORKFLOW_DIR", wf)


async def _attach_facial_performance(client, sid, pid, eid, *,
                                     articulation_first=(0, 1),
                                     anchor=(0, 1),
                                     _skip_dependency=False):
    """Attach a lawful single dialogue-bound FACIAL performance
    segment to an existing shot (the FPR-M17CC-01 scaffolding with
    the FACIAL kind and readiness-lawful keyframes) and re-capture."""
    vp_world = await make_vp(client, pid=pid, eid=eid)
    if not _skip_dependency:
        await _add_dependency(client, sid, vp_world["subject_id"])
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
            "shot_anchor_ms": {"num": anchor[0], "den": anchor[1]},
        })
    assert r.status_code == 200, r.text
    from tests.m17c_seed import ARTICULATION

    candidate = (await client.post(
        f"/creative-entities/{vp_world['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            vp_world["vp"]["id"],
            articulation_time={key: articulation_first
                               for key in ARTICULATION}),
    )).json()
    pr = (await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "d"})).json()
    r = await client.put(
        f"/shots/{sid}/performance-segments/0",
        json={
            "performance_revision_id": pr["id"],
            "performance_start_ms": {"num": 0, "den": 1},
            "performance_end_ms": {"num": 1000, "den": 1},
            "shot_anchor_ms": {"num": anchor[0], "den": anchor[1]},
            "vocal_mapping_position": 0,
        })
    assert r.status_code == 200, r.text
    revision, _visual = await _capture_closed(client, sid)
    return {"revision": revision, "pr": pr, "vp": vp_world}


async def _facial_world(client, factory, *, articulation_first=(0, 1),
                        anchor=(0, 1)):
    """A lawful single-segment dialogue-bound FACIAL world captured
    at schema 8."""
    base = await seed_feature_world(client, _factory(client))
    attached = await _attach_facial_performance(
        client, base["shot_id"], base["project_id"],
        base["entity_id"], articulation_first=articulation_first,
        anchor=anchor)
    snap = json.loads((await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": attached["revision"].id}))["snapshot_json"])
    assert snap["schema_version"] == 8
    world = {"shot": base["shot_id"], "project_id": base["project_id"],
             "entity_id": base["entity_id"], **attached}
    await _add_reference(client, world)
    return world


async def _row(client, sql, params=None):
    engine = client._transport.app.state.engine
    from sqlalchemy import text

    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params or {})).mappings(
            ).one()


async def _rows(client, sql, params=None):
    engine = client._transport.app.state.engine
    from sqlalchemy import text

    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params or {})).mappings(
            ).all()


async def _blob_count(client):
    return (await _row(client, "SELECT COUNT(*) AS n FROM blobs"))["n"]


# ---------------------------------------------------------------------------
# The happy path: translation + v5 + the GPI writer in the ONE unit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_path_happy_multi_segment(client, factory,
                                               tmp_path, monkeypatch):
    """A two-segment world (one dialogue-bound + one generic) → 202
    with 3 GPI rows (2 controls + 1 vocal-audio) under the grouped
    keys, the v5 spec carrying the 2-entry segment collection with
    vocal: null on the generic entry, parent-equal created_at, and
    the coordinate equalities."""
    from soloring.performance.execution_sampler import (
        TRANSLATION_IDENTITY,
        derived_input_hash, derived_input_record,
    )

    await _performance_manifest(tmp_path, monkeypatch)
    world = await _facial_world(client, factory)
    sid = world["shot"]

    # a SECOND, GENERIC FACIAL segment (position 1, no vocal): a
    # non-dialogue-bound PR via the M17B candidate lane
    from tests.m17b_seed import (
        SMILE as _SMILE_META, adopt as _adopt_generic,
        candidate_body as _candidate_body,
        channel as _channel, create_candidate as _create_candidate,
        kf as _kf17b,
    )

    generic = await _create_candidate(
        client, world["vp"]["subject_id"],
        _candidate_body(
            [_channel(_SMILE_META, [_kf17b(0, 1, 100000)])],
            start=(0, 1), end=(500, 1)))
    pr2 = await _adopt_generic(client, generic["id"], adopted_by="d")
    r = await client.put(
        f"/shots/{sid}/performance-segments/1",
        json={
            "performance_revision_id": pr2["id"],
            "performance_start_ms": {"num": 0, "den": 1},
            "performance_end_ms": {"num": 500, "den": 1},
            "shot_anchor_ms": {"num": 1500, "den": 1},
        })
    assert r.status_code == 200, r.text
    revision, _visual = await _capture_closed(client, sid)

    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 202, r.text
    generation_id = r.json()["id"]

    gpi = await _rows(client, (
        "SELECT * FROM generation_performance_inputs "
        "WHERE generation_id = :g "
        "ORDER BY input_key, position"), {"g": generation_id})
    assert [(row["input_key"], row["position"],
             row["shot_revision_segment_position"],
             row["artifact_role"]) for row in gpi] == [
        ("performance.controls", 0, 0, "performance.controls"),
        ("performance.controls", 1, 1, "performance.controls"),
        ("performance.vocal_audio", 0, 0, "performance.vocal_audio")]
    assert all(row["translation_identity"] == TRANSLATION_IDENTITY
               for row in gpi)

    # created_at: the parent's EXACT value (the §13.6 creation-unit
    # law, by construction)
    parent = await _row(client, (
        "SELECT created_at FROM generations WHERE id = :g"),
        {"g": generation_id})
    assert all(row["created_at"] == parent["created_at"]
               for row in gpi)

    # the v5 spec + the coordinate equalities
    spec = json.loads((await _row(client, (
        "SELECT workflow_spec_json FROM generations WHERE id = :g"),
        {"g": generation_id}))["workflow_spec_json"])
    assert spec["schema_version"] == 5
    assert spec["performance_translation"] == TRANSLATION_IDENTITY
    container = spec["performance_execution"]
    assert container["rasterization"] == {
        "fps": {"num": _FPS_NUM, "den": _FPS_DEN},
        "frame_count": _FRAMES}
    entries = container["segments"]
    assert [e["shot_revision_segment_position"] for e in entries] == [
        0, 1]
    assert entries[0]["vocal"] is not None
    assert entries[1]["vocal"] is None       # generic → null vocal
    controls = {row["shot_revision_segment_position"]: row
                for row in gpi
                if row["artifact_role"] == "performance.controls"}
    vocal = next(row for row in gpi
                 if row["artifact_role"] == "performance.vocal_audio")
    assert entries[0]["control_schedule_blob_hash"] == \
        controls[0]["blob_hash"]
    assert entries[1]["control_schedule_blob_hash"] == \
        controls[1]["blob_hash"]
    assert entries[0]["vocal"][
        "materialized_audio_track_blob_hash"] == vocal["blob_hash"]

    # the derived blobs exist, rehash, and the v1 identity records
    # recompute exactly
    from soloring.assets.blob_store import BlobStore
    from soloring.settings import get_settings

    store = BlobStore(get_settings())
    for row in gpi:
        data = store.path_for_hash(row["blob_hash"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row["blob_hash"]
        record = derived_input_record(
            input_key=row["input_key"], position=row["position"],
            artifact_role=row["artifact_role"],
            shot_revision_segment_position=(
                row["shot_revision_segment_position"]),
            performance_revision_id=row["performance_revision_id"],
            vocal_performance_revision_id=(
                row["vocal_performance_revision_id"]),
            binding_hash=row["binding_hash"],
            segment_hash=row["segment_hash"],
            translation_identity=row["translation_identity"],
            blob_hash=row["blob_hash"])
        assert derived_input_hash(record) == row["derived_input_hash"]

    # the v1 lower projection is preserved (no model/realization on
    # the plain fake lane) and the grammar law passes
    from soloring.performance.execution_spec import (
        validate_workflow_spec_v5,
    )

    validate_workflow_spec_v5(spec)
    assert "model" not in spec and "realization" not in spec


@pytest.mark.asyncio
async def test_create_path_duplicate_keeps_identical_identities(
        client, factory, tmp_path, monkeypatch):
    """Decision B live: a duplicate Generation over the identical
    captured inputs produces identical derived bytes AND identical
    derived_input_hash values (parent/lifecycle coordinates
    excluded from the record)."""
    await _performance_manifest(tmp_path, monkeypatch)
    world = await _facial_world(client, factory)
    first = (await client.post(
        f"/shots/{world['shot']}/generations")).json()
    second = (await client.post(
        f"/shots/{world['shot']}/generations")).json()
    assert first["id"] != second["id"]
    rows = await _rows(client, (
        "SELECT generation_id, input_key, position, blob_hash, "
        "derived_input_hash FROM generation_performance_inputs "
        "WHERE generation_id IN (:a, :b) ORDER BY generation_id, "
        "input_key"), {"a": first["id"], "b": second["id"]})
    by_generation = {}
    for row in rows:
        by_generation.setdefault(row["generation_id"], []).append(
            (row["input_key"], row["position"], row["blob_hash"],
             row["derived_input_hash"]))
    assert by_generation[first["id"]] == by_generation[second["id"]]
    assert len(by_generation[first["id"]]) == 2


# ---------------------------------------------------------------------------
# The refusals — zero generations, zero GPI rows, zero derived blobs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_path_anchor_refusal_zero_side_effects(
        client, factory, tmp_path, monkeypatch):
    """FPR31-M17CD-07 correction — the REAL multi-segment
    later-failure adversary: segment 0 (dialogue-bound) is fully
    derivable; the strictly LATER dialogue-bound segment 1 pairs
    with a second vocal mapping whose anchor (1/7 ms @ 48 kHz) is
    lawfully capturable at authority (J/L intersection holds) but
    NOT representable on the sample grid — audio materialization
    fails AT THE LATER SEGMENT after segment 0's derivation,
    leaving ZERO Generation, ZERO GPI rows, and ZERO newly
    published blobs (all-or-nothing)."""
    await _performance_manifest(tmp_path, monkeypatch)
    world = await _facial_world(client, factory)  # seg 0 GOOD
    sid = world["shot"]

    # a second dialogue-bound performance on its own VP + line, with
    # a second vocal mapping carrying the unrepresentable anchor
    from tests.m17c_seed import ARTICULATION

    vp2 = await make_vp(client, pid=world["project_id"])
    # APPEND the second subject (the plain helper replaces the set)
    current = (await client.get(
        f"/shots/{sid}/semantic-dependencies")).json()
    existing = current.get("dependencies", current)         if isinstance(current, dict) else current
    r = await client.put(
        f"/shots/{sid}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": d["entity_id"], "role": d["role"]}
            for d in existing] + [
            {"entity_id": vp2["subject_id"], "role": "subject"}]})
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/dialogue-line-revisions/"
        f"{vp2['dialogue_line_revision_id']}/vocal-selection",
        json={"vocal_performance_revision_id": vp2["vp"]["id"],
              "selected_by": "d"})
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{sid}/vocal-segments/1",
        json={
            "vocal_performance_revision_id": vp2["vp"]["id"],
            "source_start_sample": 0,
            "source_end_sample_exclusive": 48000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 1, "den": 7},
        })
    assert r.status_code == 200, r.text
    candidate = (await client.post(
        f"/creative-entities/{vp2['subject_id']}/"
        "dialogue-bound-performance-candidates",
        json=dialogue_bound_body(
            vp2["vp"]["id"], source_start=0, source_end=48000,
            origin=(0, 1),
            articulation_time={key: (0, 1) for key in ARTICULATION}),
    )).json()
    pr2 = (await client.post(
        f"/performance-candidates/{candidate['id']}/adopt",
        json={"adopted_by": "d"})).json()
    r = await client.put(
        f"/shots/{sid}/performance-segments/1",
        json={
            "performance_revision_id": pr2["id"],
            "performance_start_ms": {"num": 0, "den": 1},
            "performance_end_ms": {"num": 1000, "den": 1},
            "shot_anchor_ms": {"num": 1, "den": 7},
            "vocal_mapping_position": 1,
        })
    assert r.status_code == 200, r.text
    readiness = (await client.get(
        f"/shots/{sid}/performance-readiness")).json()
    assert readiness["ready"], readiness
    revision, _visual = await _capture_closed(client, sid)
    snap = json.loads((await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": revision.id}))["snapshot_json"])
    assert len(snap["performance"]["segments"]) == 2  # multi-segment

    blobs_before = await _blob_count(client)
    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == \
        "PERFORMANCE_EXECUTION_ANCHOR_UNREPRESENTABLE"
    assert (await _row(client, (
        "SELECT COUNT(*) AS n FROM generations")))["n"] == 0
    assert (await _row(client, (
        "SELECT COUNT(*) AS n FROM "
        "generation_performance_inputs")))["n"] == 0
    assert await _blob_count(client) == blobs_before


@pytest.mark.asyncio
async def test_create_path_readiness_refusal(client, factory, tmp_path,
                                             monkeypatch):
    """Keyframes after the first sampled Performance time refuse
    with the typed binding error (never a zero default)."""
    await _performance_manifest(tmp_path, monkeypatch)
    world = await _facial_world(client, factory,
                                articulation_first=(600, 1))
    r = await client.post(f"/shots/{world['shot']}/generations")
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == \
        "PERFORMANCE_EXECUTION_BINDING_INVALID"
    assert (await _row(client, (
        "SELECT COUNT(*) AS n FROM generations")))["n"] == 0


@pytest.mark.asyncio
async def test_create_path_rasterization_facts_required(
        client, factory):
    """The DEFAULT (non-performance) package lacks the rasterization
    parameters — the typed facts refusal (execution refuses rather
    than guessing the picture grid)."""
    world = await _facial_world(client, factory)
    r = await client.post(f"/shots/{world['shot']}/generations")
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == \
        "PERFORMANCE_EXECUTION_BINDING_INVALID"
    assert "rasterization" in r.json()["message"]
    assert (await _row(client, (
        "SELECT COUNT(*) AS n FROM generations")))["n"] == 0


@pytest.mark.asyncio
async def test_create_path_kind_and_body_refusals(client, factory,
                                                  tmp_path,
                                                  monkeypatch):
    """§14.7: a BODY-kind PR refuses at the admission gate with the
    typed kind error; the FACIAL lane itself stays green."""
    await _performance_manifest(tmp_path, monkeypatch)
    base = await seed_feature_world(client, _factory(client))
    sid = base["shot_id"]
    vp_world = await make_vp(client, pid=base["project_id"],
                             eid=base["entity_id"])
    await _add_dependency(client, sid, vp_world["subject_id"])
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
    from tests.m17c_seed import ARTICULATION

    # pure-BODY cannot be dialogue-bound by construction (dialogue
    # binding inherently carries the facial articulation channels);
    # BODY_FACIAL is the lawful non-FACIAL dialogue shape — exactly
    # the §14.7 case the first lane refuses
    for kind in ("BODY_FACIAL",):
        candidate = (await client.post(
            f"/creative-entities/{vp_world['subject_id']}/"
            "dialogue-bound-performance-candidates",
            json=dialogue_bound_body(
                vp_world["vp"]["id"], kind=kind,
                articulation_time={key: (0, 1)
                                   for key in ARTICULATION}),
        )).json()
        pr = (await client.post(
            f"/performance-candidates/{candidate['id']}/adopt",
            json={"adopted_by": "d"})).json()
        r = await client.put(
            f"/shots/{sid}/performance-segments/0",
            json={
                "performance_revision_id": pr["id"],
                "performance_start_ms": {"num": 0, "den": 1},
                "performance_end_ms": {"num": 1000, "den": 1},
                "shot_anchor_ms": {"num": 0, "den": 1},
                "vocal_mapping_position": 0,
            })
        assert r.status_code == 200, r.text
        revision, _visual = await _capture_closed(client, sid)
        snap = json.loads((await _row(client, (
            "SELECT snapshot_json FROM shot_revisions "
            "WHERE id = :r"), {"r": revision.id}))["snapshot_json"])
        assert snap["schema_version"] == 8
        world = {"shot": sid, "project_id": base["project_id"]}
        await _add_reference(client, world)
        r = await client.post(f"/shots/{sid}/generations")
        assert r.status_code == 409, r.text
        assert r.json()["error_code"] == \
            "PERFORMANCE_EXECUTION_KIND_UNSUPPORTED"
        assert (await _row(client, (
            "SELECT COUNT(*) AS n FROM generations")))["n"] == 0
        r = await client.delete(
            f"/shots/{sid}/performance-segments/0")
        assert r.status_code in (200, 204), r.text


@pytest.mark.asyncio
async def test_create_path_eight_over_seven_events_refuses(client,
                                                           factory,
                                                           tmp_path,
                                                           monkeypatch):
    """The M16 law through the wrap: non-empty intra_shot events
    under the schema-8 capture refuse INTRA_SHOT_REALIZATION."""
    from tests.m16_seed_b import event, post_event, state

    await _performance_manifest(tmp_path, monkeypatch)
    base = await seed_feature_world(client, _factory(client))
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid,
                     event(fid, 1000, state(), state("fresh")))
    attached = await _attach_facial_performance(
        client, sid, base["project_id"], base["entity_id"])
    snap = json.loads((await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": attached["revision"].id}))["snapshot_json"])
    assert snap["schema_version"] == 8
    assert snap["intra_shot"]["events"]      # events under the wrap
    world = {"shot": sid, "project_id": base["project_id"]}
    await _add_reference(client, world)
    r = await client.post(f"/shots/{sid}/generations")
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == "INTRA_SHOT_REALIZATION_UNSUPPORTED"
    assert (await _row(client, (
        "SELECT COUNT(*) AS n FROM generations")))["n"] == 0


@pytest.mark.asyncio
async def test_create_path_spatial_composition_refuses(client, factory,
                                                       tmp_path,
                                                       monkeypatch):
    """Decision A live: a REAL schema-8 capture wrapping a schema-5
    spatial base (the M13 selected-binding world + the performance
    plane) refuses with PERFORMANCE_SPATIAL_COMPOSITION_UNSUPPORTED
    naming the embedded authority; nothing persists."""
    from tests.test_m13_shot_capture import (
        _capture as _m13_capture, _full_m13_world, _select_binding,
    )

    await _performance_manifest(tmp_path, monkeypatch)
    b = await _full_m13_world(client, tag=b"m17cd-a8over5")
    await _select_binding(client, b)
    revision, _visual = await _m13_capture(client, b["shot"])
    snap = json.loads((await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": revision.id}))["snapshot_json"])
    # the M13 selected-binding world captures at schema 6 (spatial +
    # production world + observation) — the wrap target
    assert snap["schema_version"] == 6
    # attach performance WITHOUT clobbering the spatial world's
    # location-entity dependency: read the current set, append the
    # performance subject, then PUT the union (the shared helper
    # replaces the set wholesale)
    current = (await client.get(
        f"/shots/{b['shot']}/semantic-dependencies")).json()
    existing = current.get("dependencies", current) \
        if isinstance(current, dict) else current
    vp_world = await make_vp(client, pid=b["pid"])
    r = await client.put(
        f"/shots/{b['shot']}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": d["entity_id"], "role": d["role"]}
            for d in existing] + [
            {"entity_id": vp_world["subject_id"], "role": "subject"}]})
    assert r.status_code == 200, r.text
    attached = await _attach_facial_performance(
        client, b["shot"], b["pid"], vp_world["subject_id"],
        _skip_dependency=True)
    wrapped = json.loads((await _row(client, (
        "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
        {"r": attached["revision"].id}))["snapshot_json"])
    assert wrapped["schema_version"] == 8
    assert "spatial_continuity" in wrapped
    world = {"shot": b["shot"], "project_id": b["pid"]}
    await _add_reference(client, world)
    r = await client.post(f"/shots/{b['shot']}/generations")
    assert r.status_code == 409, r.text
    assert r.json()["error_code"] == \
        "PERFORMANCE_SPATIAL_COMPOSITION_UNSUPPORTED"
    assert (await _row(client, (
        "SELECT COUNT(*) AS n FROM generations")))["n"] == 0
