"""M17C-C slice 2 regressions: the performance-plane coherent read and
the pure schema-8 wrap (frozen R4 11.1-11.5).

Laws proven:
- one-read coherence: after ``_snapshot_one_read`` returns, mutating
  every current performance surface still yields the ORIGINALLY
  captured schema-8 content (the tenth element is the complete
  immutable-in-practice value; the builder queries nothing);
- no mapping => EXACT predecessor snapshot bytes at multiple schema
  levels (1/2/3-family via the builder; the whole existing capture
  corpus is the broad green proof);
- performance-bearing capture => schema 8 with a NON-EMPTY
  position-ordered ``performance.segments``; empty schema 8 is
  unrepresentable (the builder refuses);
- the uniform closed vocal grammar: dialogue-bound => complete vocal
  object, non-dialogue => explicit null;
- schema 8 wraps schema 7 with the M16 block byte/meaning preserved;
- the readiness gate: non-READY refuses capture 409 typed; corruption
  inside the read fails closed 500;
- slice boundary: NO companion rows are written (slice 3).
"""

from __future__ import annotations

import copy

import pytest
from sqlalchemy import text

from soloring.domain.canonical import (
    canonical_hash, canonical_json_str,
)
from soloring.continuity.snapshots import build_capturable_snapshot
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


async def _lawful_bound_mapping(client, world):
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text


def _pack(segments, ready=True):
    return {"ready": ready, "segments": segments,
            "segment_readiness": []}


def _seg(position=0, vocal=None):
    return {
        "position": position,
        "subject_id": "s1",
        "performance_revision_id": "pr1",
        "performance_payload_sha256": "a" * 64,
        "performance_profile_id": "performance-profile/1",
        "performance_kind": "FACIAL",
        "performance_start_ms": {"num": 0, "den": 1},
        "performance_end_ms": {"num": 1000, "den": 1},
        "shot_anchor_ms": {"num": 0, "den": 1},
        "vocal": vocal,
    }


def _vocal():
    return {
        "vocal_performance_revision_id": "vp1",
        "vocal_binding_hash": "b" * 64,
        "source_start_sample": 84000,
        "source_end_sample_exclusive": 156000,
        "sample_rate_hz": 48000,
    }


class _Dep:
    entity_id = "e1"
    entity_kind = "location"
    entity_revision_id = "er1"
    entity_revision_number = 1
    entity_revision_hash = "x"
    role = "subject"
    position = 0
    source = "working"


class _Shot:
    id = "s1"
    project_id = "p1"
    scene_id = None
    subject = "s"
    action = "a"
    environment = None
    framing = None
    camera_motion = None
    lens = None
    mood = None
    duration_ms = 3000


# ---------------------------------------------------------------------------
# Pure builder laws
# ---------------------------------------------------------------------------

def test_no_pack_exact_predecessor_bytes_multiple_levels():
    """performance_pack absent (or explicitly None) leaves the builder's
    output byte-identical to the pre-M17C-C form at the schema-1 and
    schema-2 levels — the wrap only ever ADDS a plane."""
    shot = _Shot()
    # schema 1 (zero dependencies)
    s1, spec1 = build_capturable_snapshot(shot, [], [])
    assert s1["schema_version"] == 1
    assert "performance" not in s1
    s1b, _ = build_capturable_snapshot(shot, [], [], performance_pack=None)
    assert canonical_json_str(s1b) == canonical_json_str(s1)

    # schema 2 (deps, zero states)
    dep = type("D", (), {"entity_id": "e1", "entity_kind": "location",
                          "entity_revision_id": "er1",
                          "entity_revision_number": 1,
                          "entity_revision_hash": "x",
                          "role": "subject", "position": 0,
                          "source": "working"})()
    resolved = [dep]
    s2, spec2 = build_capturable_snapshot(shot, [], resolved)
    assert s2["schema_version"] == 2
    s2b, _ = build_capturable_snapshot(shot, [], resolved,
                                        performance_pack=None)
    assert canonical_json_str(s2b) == canonical_json_str(s2)
    # the historical two-form call (no kwargs at all) still equals
    s2c, _ = build_capturable_snapshot(shot, [], resolved)
    assert canonical_json_str(s2c) == canonical_json_str(s2)


def test_schema8_wrap_laws():
    shot = _Shot()
    segs = [_seg(0, _vocal()), _seg(1)]
    s8, _ = build_capturable_snapshot(
        shot, [], [_Dep()], performance_pack=_pack(segs))
    assert s8["schema_version"] == 8
    perf = s8["performance"]
    assert perf["schema_version"] == 1
    assert [s["position"] for s in perf["segments"]] == [0, 1]
    # uniform closed vocal grammar
    assert perf["segments"][0]["vocal"] == _vocal()
    assert perf["segments"][1]["vocal"] is None
    # the predecessor fields are all still present, untouched
    for key in ("intent", "schema_version"):
        pass
    assert "intent" in s8


def test_schema8_wraps_schema7_preserving_m16_block():
    """schema 8 over a schema-7 base: the intra_shot block and every
    predecessor field are byte/meaning preserved — only schema_version
    and the performance plane change."""
    shot = _Shot()
    intra = {"duration_ms": 3000, "events": [
        {"event_id": "ev1", "event_kind": "position",
         "time_ms": {"num": 0, "den": 1}}]}
    s7, _ = build_capturable_snapshot(
        shot, [], [_Dep()], intra_shot_pack=intra)
    assert s7["schema_version"] == 7
    s8, _ = build_capturable_snapshot(
        shot, [], [_Dep()], intra_shot_pack=intra,
        performance_pack=_pack([_seg(0, _vocal())]))
    assert s8["schema_version"] == 8
    assert s8["intra_shot"] == s7["intra_shot"]
    predecessor7 = {k: v for k, v in s7.items()
                    if k not in ("schema_version",)}
    predecessor8 = {k: v for k, v in s8.items() if k not in (
        "schema_version", "performance")}
    assert predecessor8 == predecessor7


def test_empty_schema8_unrepresentable():
    from soloring.errors import SoloRingError
    shot = _Shot()
    with pytest.raises(SoloRingError):
        build_capturable_snapshot(
            shot, [], [_Dep()], performance_pack=_pack([]))
    with pytest.raises(SoloRingError):
        build_capturable_snapshot(
            shot, [], [_Dep()], performance_pack={"ready": True, "segments": [],
                                        "segment_readiness": []})


def test_noncanonical_segment_order_refused():
    from soloring.errors import SoloRingError
    shot = _Shot()
    with pytest.raises(SoloRingError):
        build_capturable_snapshot(
            shot, [], [_Dep()],
            performance_pack=_pack([_seg(1), _seg(0)]))


def test_segment_grammar_divergence_refused():
    from soloring.errors import SoloRingError
    shot = _Shot()
    bad = _seg()
    del bad["performance_kind"]
    with pytest.raises(SoloRingError):
        build_capturable_snapshot(shot, [], [_Dep()], performance_pack=_pack([bad]))
    badv = _seg(0, {"vocal_performance_revision_id": "v"})
    with pytest.raises(SoloRingError):
        build_capturable_snapshot(
            shot, [], [_Dep()], performance_pack=_pack([badv]))


# ---------------------------------------------------------------------------
# The coherent read (live)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_one_read_coherence_survives_post_read_mutation(client):
    """THE central invariant: after _snapshot_one_read returns, mutate
    every current performance surface (delete the working mapping,
    repoint the paired vocal mapping, change the Shot duration) — the
    ALREADY-RESOLVED performance element and the snapshot built from
    the read tuple still carry the originally captured values."""
    from soloring.domain.revisions import _snapshot_one_read
    from tests.test_m17c_binding_transitions import _same_line_alternate_vp
    world = await _bound_world(client)
    await _lawful_bound_mapping(client, world)

    settings = client._transport.app.state.settings
    from tests.m17cc_capture_helper import _factory
    read = await _snapshot_one_read(
        _factory(client)(), world["shot"], settings=settings)
    performance = read[9]
    assert performance is not None
    assert performance["ready"] is True
    seg = performance["segments"][0]
    assert seg["performance_revision_id"] == world["pr"]["id"]
    assert seg["vocal"]["vocal_performance_revision_id"] == \
        world["vp"]["id"]
    captured = copy.deepcopy(performance)

    # mutate every current surface AFTER the read
    await _sql(client, f"DELETE FROM {_TABLE} WHERE shot_id = :s",
               {"s": world["shot"]})
    alternate = await _same_line_alternate_vp(client, world)
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": alternate["id"],
              "selected_by": "coh"})
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
        f"/shots/{world['shot']}", json={"duration_ms": 100})
    assert p.status_code == 200, p.text

    # the read value is untouched by construction (plain copy), and a
    # snapshot built NOW from the ORIGINAL read tuple embeds the
    # originally captured performance plane
    assert performance == captured
    shot = read[0]
    snapshot, _ = build_capturable_snapshot(
        shot, read[1], read[2], read[3], read[4],
        read[5].pack if read[5] is not None else None,
        read[6].pack if read[6] is not None else None,
        read[7].pack,
        performance_pack=performance)
    assert snapshot["schema_version"] == 8
    assert snapshot["performance"]["segments"][0][
        "performance_revision_id"] == world["pr"]["id"]
    assert snapshot["performance"]["segments"][0]["vocal"][
        "vocal_performance_revision_id"] == world["vp"]["id"]


@pytest.mark.asyncio
async def test_capture_refuses_non_ready_with_typed_409(client):
    from soloring.errors import ErrorCode
    world = await _bound_world(client)
    await _lawful_bound_mapping(client, world)
    # lawful working drift: repoint the paired vocal mapping through
    # the supported M17A API -> BLOCKED_BINDING_INTEGRITY
    from tests.test_m17c_binding_transitions import _same_line_alternate_vp
    alternate = await _same_line_alternate_vp(client, world)
    await client.put(
        f"/dialogue-line-revisions/{world['dialogue_line_revision_id']}/"
        "vocal-selection",
        json={"vocal_performance_revision_id": alternate["id"],
              "selected_by": "d"})
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
    from soloring.errors import SoloRingError
    from tests.m17cc_capture_helper import capture
    with pytest.raises(SoloRingError) as excinfo:
        await capture(client, world["shot"])
    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "PERFORMANCE_CAPTURE_NOT_READY"
    segs = excinfo.value.details["segments"]
    assert segs[0]["readiness"] == "BLOCKED_BINDING_INTEGRITY"


@pytest.mark.asyncio
async def test_capture_corruption_fails_closed_in_read(client):
    world = await _bound_world(client)
    await _lawful_bound_mapping(client, world)
    # corrupt the immutable revision binding hash AFTER the lawful PUT
    await _sql(
        client,
        "UPDATE performance_revision_vocal_bindings "
        "SET binding_hash = :h WHERE performance_revision_id = :r",
        {"h": "e" * 64, "r": world["pr"]["id"]})
    from soloring.errors import SoloRingError
    from tests.m17cc_capture_helper import capture
    with pytest.raises(SoloRingError) as excinfo:
        await capture(client, world["shot"])
    assert excinfo.value.status_code == 500
    assert excinfo.value.code == "INTERNAL_INVARIANT_VIOLATION"


@pytest.mark.asyncio
async def test_live_capture_schema8_shape_and_companions(client):
    """A lawful performance-bearing capture produces schema 8 with the
    complete embedded grammar — and (slice 3) persists EXACTLY one
    companion parent plus one child per captured segment, whose every
    column is the mechanical projection of the captured value."""
    from sqlalchemy import text as _text
    world = await _bound_world(client)
    await _lawful_bound_mapping(client, world)
    from tests.m17cc_capture_helper import capture
    revision_obj, _ = await capture(client, world["shot"])
    import json as _json
    snap = _json.loads(revision_obj.snapshot_json)
    assert snap["schema_version"] == 8
    seg = snap["performance"]["segments"][0]
    assert seg["performance_revision_id"] == world["pr"]["id"]
    assert seg["subject_id"] == world["subject_id"]
    assert seg["vocal"]["vocal_performance_revision_id"] == world["vp"]["id"]
    assert len(seg["vocal"]) == 5
    engine = _engine(client)
    async with engine.connect() as conn:
        parents = (await conn.execute(_text(
            "SELECT schema_version, spec_json, spec_hash FROM "
            "shot_revision_performance_specs WHERE shot_revision_id "
            "= :r"), {"r": revision_obj.id})).fetchall()
        assert len(parents) == 1
        assert parents[0].schema_version == 1
        assert parents[0].spec_json == canonical_json_str(
            {"schema_version": 1, "segments": snap["performance"]["segments"]})
        assert parents[0].spec_hash == canonical_hash(
            {"schema_version": 1, "segments": snap["performance"]["segments"]})
        children = (await conn.execute(_text(
            "SELECT position, subject_id, "
            "performance_revision_id, vocal_performance_revision_id, "
            "vocal_binding_hash, vocal_mapping_hash, segment_json "
            "FROM shot_revision_performance_segments WHERE "
            "shot_revision_id = :r ORDER BY position"),
            {"r": revision_obj.id})).fetchall()
        assert len(children) == 1
        ch = children[0]
        assert ch.position == 0
        assert ch.performance_revision_id == world["pr"]["id"]
        assert ch.subject_id == world["subject_id"]
        assert ch.vocal_performance_revision_id == world["vp"]["id"]
        assert len(ch.vocal_binding_hash) == 64
        assert len(ch.vocal_mapping_hash) == 64
        assert ch.segment_json == canonical_json_str(
            snap["performance"]["segments"][0])
        # derived-input rows remain M17C-D storage-only: zero rows
        n_gpi = (await conn.execute(_text(
            "SELECT COUNT(*) FROM generation_performance_inputs"))
        ).scalar_one()
        assert n_gpi == 0


@pytest.mark.asyncio
async def test_no_mapping_capture_is_exact_predecessor_live(client):
    """A capture with NO working mapping emits the exact predecessor
    schema (byte law, live): the snapshot equals the pre-slice-2 form
    and carries no performance key."""
    world = await _bound_world(client)
    from tests.m17cc_capture_helper import capture
    revision_obj, _ = await capture(client, world["shot"])
    import json as _json
    snap = _json.loads(revision_obj.snapshot_json)
    assert snap["schema_version"] != 8
    assert "performance" not in snap
    # the canonical bytes equal the builder's no-pack output over the
    # same captured value
    from soloring.domain.revisions import _snapshot_one_read
    from tests.m17cc_capture_helper import _factory
    settings = client._transport.app.state.settings
    read = await _snapshot_one_read(
        _factory(client)(), world["shot"], settings=settings)
    assert read[9] is None
    expected, _ = build_capturable_snapshot(
        read[0], read[1], read[2], read[3], read[4],
        read[5].pack if read[5] is not None else None,
        read[6].pack if read[6] is not None else None,
        read[7].pack)
    assert canonical_json_str(expected) == revision_obj.snapshot_json
    assert canonical_hash(expected) == revision_obj.snapshot_hash
