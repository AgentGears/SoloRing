"""M17C-C §12 regressions: historical performance reconstruction
(frozen R4 §12; scope R0 1.5).

The frozen rule: historical inspection reconstructs WHAT WAS
CAPTURED, never what is true now. Laws proven:

- the captured-graph-only read: the schema-8 historical answer comes
  from snapshot bytes + companion rows + immutable referenced
  authority + retained Blob closure, and a query spy proves the
  forbidden current tables (VP selection, current vocal/performance
  mappings, candidate working intent, current Shot dependency
  selection) are NEVER touched — absence, not just equal output;
- the exact per-segment §12 answer (subject, exact PR + identity,
  exact payload bytes/hash + retained size, exact VP + identity,
  vocal sample interval, Performance interval, Shot-relative anchor,
  immutable synchronization binding) with dialogue and generic shapes
  kept distinct (vocal is the complete object or null);
- schema branching stays historical: schema < 8 keeps the exact
  predecessor behavior and never consults the performance companions;
  Performance is never inferred from current mappings (the temptation
  fixture: newer, internally valid current mappings/selections exist
  and are ignored);
- current-state mutation immunity of the ACTUAL public historical
  read: capture → record response → mutate every prohibited current
  surface → read again on a REOPENED session → exact equality;
- immutable-closure corruption fails closed (missing parent/child,
  moved/altered fields/bytes/hash, PR/binding disagreement, gone
  binding) with no present-day fallback — and the FK-shielded shapes
  (missing retained Blob, missing VP behind its binding/selection)
  are proven unconstructible rather than silently skipped;
- ordering is the CAPTURED position order (it survives deletion of
  every current mapping);
- a schema-8 capture wrapping a schema-7 predecessor keeps BOTH
  historical planes (§11.5), and a present embedded intra_shot block
  with gone companions refuses.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event, text

from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world, _seg_body

_PARENTS = "shot_revision_performance_specs"
_CHILDREN = "shot_revision_performance_segments"

# §12's forbidden current surfaces, as SQL substrings (the candidate
# token covers both candidate tables as mutable working intent)
_FORBIDDEN = (
    "vocal_performance_selections",
    "shot_vocal_segment_mappings",
    "shot_performance_segment_mappings",
    "performance_candidate",
    "shot_entity_dependencies",
)


def _engine(client):
    return client._transport.app.state.engine


def _factory(client):
    from tests.m17cc_capture_helper import _factory as _f
    return _f(client)


async def _sql(client, stmt, params=None):
    async with _engine(client).begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _row(client, stmt, params=None):
    async with _engine(client).connect() as conn:
        return dict((await conn.execute(
            text(stmt), params or {})).mappings().one())


async def _history(client, revision_id):
    r = await client.get(f"/shot-revisions/{revision_id}/continuity")
    assert r.status_code == 200, r.text
    return r.json()


async def _capture_schema8(client):
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    return world, revision


class _ForbiddenTableSpy:
    """Fails the statement stream if the historical path queries any
    §12-forbidden current table."""

    def __init__(self, engine):
        # async engines take synchronous listeners on the sync engine
        self.engine = engine.sync_engine
        self.hits: list[str] = []

    def _check(self, conn, cursor, statement, parameters, context,
               executemany):
        lowered = statement.lower()
        for table in _FORBIDDEN:
            if table in lowered:
                self.hits.append(f"{table}: {statement[:120]}")

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute",
                     self._check)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute",
                     self._check)


@pytest.mark.asyncio
async def test_history_answers_the_frozen_segment_contract(client):
    """The §12 per-segment answer: every question the frozen contract
    asks, answered from the captured graph with dialogue and generic
    segments kept in their distinct captured shapes."""
    world, revision = await _capture_schema8(client)

    hist = await _history(client, revision.id)
    perf = hist["performance"]
    assert perf is not None and perf["schema_version"] == 1
    assert [seg["position"] for seg in perf["segments"]] == [0, 1]
    assert perf["spec_hash"] == (await _row(client, (
        f"SELECT spec_hash FROM {_PARENTS} WHERE "
        "shot_revision_id = :r"), {"r": revision.id}))["spec_hash"]

    d0, d1 = perf["segments"]
    # segment 0: dialogue-bound — subject, exact PR identity, payload
    # bytes/hash + retained size, intervals, anchor, binding
    assert d0["subject_id"] == world["subject_id"]
    assert d0["performance_revision_id"] == world["pr"]["id"]
    pr = await _row(client, (
        "SELECT subject_id, performance_kind, performance_profile_id, "
        "payload_schema_version, source_kind, temporal_start_num, "
        "temporal_start_den, temporal_end_num, temporal_end_den, "
        "canonical_channel_payload_sha256, "
        "canonical_channel_payload_blob_hash, adopted_at "
        "FROM performance_revisions WHERE id = :p"),
        {"p": world["pr"]["id"]})
    assert d0["performance_revision"] == {
        "subject_id": pr["subject_id"],
        "performance_kind": pr["performance_kind"],
        "performance_profile_id": pr["performance_profile_id"],
        "payload_schema_version": pr["payload_schema_version"],
        "source_kind": pr["source_kind"],
        "temporal_start_ms": {"num": pr["temporal_start_num"],
                              "den": pr["temporal_start_den"]},
        "temporal_end_ms": {"num": pr["temporal_end_num"],
                            "den": pr["temporal_end_den"]},
        "adopted_at": pr["adopted_at"],
    }
    blob = await _row(client, (
        "SELECT size_bytes FROM blobs WHERE hash = :h"),
        {"h": pr["canonical_channel_payload_blob_hash"]})
    payload_path = (
        client._transport.app.state.settings.blob_dir / "sha256"
        / pr["canonical_channel_payload_blob_hash"][:2]
        / pr["canonical_channel_payload_blob_hash"][2:4]
        / pr["canonical_channel_payload_blob_hash"])
    import base64 as _b64
    assert d0["performance_payload"] == {
        "blob_hash": pr["canonical_channel_payload_blob_hash"],
        "sha256": pr["canonical_channel_payload_sha256"],
        "size_bytes": blob["size_bytes"],
        # FPR-M17CC-05: the EXACT retained bytes (verified + base64)
        "payload_bytes_base64": _b64.b64encode(
            payload_path.read_bytes()).decode("ascii"),
    }
    assert d0["performance_start_ms"] == {"num": 0, "den": 1}
    assert d0["performance_end_ms"] == {"num": 1000, "den": 1}
    assert d0["shot_anchor_ms"] == {"num": 0, "den": 1}
    binding = await _row(client, (
        "SELECT vocal_performance_revision_id, binding_hash, "
        "source_start_sample, source_end_sample_exclusive, "
        "sample_rate_hz, performance_origin_num, "
        "performance_origin_den, synchronization_basis_version "
        "FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = :p"), {"p": world["pr"]["id"]})
    vp = await _row(client, (
        "SELECT dialogue_line_revision_id, revision_number, "
        "speaker_subject_id, native_sample_rate_hz, "
        "retained_audio_blob_hash, adopted_at "
        "FROM vocal_performance_revisions WHERE id = :v"),
        {"v": world["vp"]["id"]})
    assert d0["vocal"] == {
        "vocal_performance_revision_id": world["vp"]["id"],
        "vocal_performance_revision": {
            "dialogue_line_revision_id":
                vp["dialogue_line_revision_id"],
            "revision_number": vp["revision_number"],
            "speaker_subject_id": vp["speaker_subject_id"],
            "native_sample_rate_hz": vp["native_sample_rate_hz"],
            "retained_audio_blob_hash": vp["retained_audio_blob_hash"],
            "adopted_at": vp["adopted_at"],
        },
        "synchronization_binding": {
            "binding_hash": binding["binding_hash"],
            "vocal_performance_revision_id":
                binding["vocal_performance_revision_id"],
            "source_start_sample": binding["source_start_sample"],
            "source_end_sample_exclusive":
                binding["source_end_sample_exclusive"],
            "sample_rate_hz": binding["sample_rate_hz"],
            "performance_origin_ms": {
                "num": binding["performance_origin_num"],
                "den": binding["performance_origin_den"]},
            "synchronization_basis_version":
                binding["synchronization_basis_version"],
        },
        "sample_interval": {
            "source_start_sample": 48000,
            "source_end_sample_exclusive": 96000,
            "sample_rate_hz": 48000,
        },
        "vocal_mapping_hash": d0["vocal"]["vocal_mapping_hash"],
    }
    assert d0["vocal"]["vocal_mapping_hash"] is not None
    # segment 1: generic — the exact same answer shape with the
    # complete null vocal group, never an ambiguous optional form
    assert d1["subject_id"] == world["subject_id"]
    assert d1["performance_revision_id"] != world["pr"]["id"]
    assert d1["vocal"] is None
    assert d1["performance_start_ms"] == {"num": 0, "den": 1}
    assert d1["performance_end_ms"] == {"num": 1000, "den": 1}
    assert d1["shot_anchor_ms"] == {"num": 0, "den": 1}


@pytest.mark.asyncio
async def test_schema_below_8_history_never_consults_companions(client):
    """Schema < 8 keeps the exact predecessor historical behavior: no
    performance plane in the answer, and the companion tables are not
    even queried (proven absence)."""
    world = await _bound_world(client)
    revision, _visual = await _capture(client, world["shot"])

    engine = _engine(client).sync_engine
    seen: list[str] = []

    def _spy(conn, cursor, statement, parameters, context, executemany):
        if "shot_revision_performance_spec" in statement.lower():
            seen.append(statement[:120])

    event.listen(engine, "before_cursor_execute", _spy)
    try:
        hist = await _history(client, revision.id)
    finally:
        event.remove(engine, "before_cursor_execute", _spy)
    assert hist["performance"] is None
    assert seen == []


@pytest.mark.asyncio
async def test_current_state_mutation_leaves_history_identical(client):
    """The §12 product proof: after the capture, EVERY prohibited
    current surface moves — including the temptation fixture (newer,
    internally valid mappings and a re-selected VP that would be the
    answer under latest-substitution) — and the historical read on a
    REOPENED session (each request binds a fresh session) is exactly
    equal, captured ordering included."""
    world, revision = await _capture_schema8(client)
    before = await _history(client, revision.id)
    captured_pr = before["performance"]["segments"][0][
        "performance_revision_id"]
    captured_vp = before["performance"]["segments"][0]["vocal"][
        "vocal_performance_revision_id"]

    # temptation 1: a NEWER, valid VP on the same dialogue line,
    # re-selected as current
    from tests.m17a_seed import place_blob, wave_bytes
    new_blob = await place_blob(client, wave_bytes(48000, 72000))
    new_vc = (await client.post(
        f"/dialogue-line-revisions/"
        f"{world['dialogue_line_revision_id']}/vocal-candidates",
        json={
            "retained_audio_blob_hash": new_blob,
            "source_provenance": {
                "schema_version": 1, "source_kind": "recorded"},
        })).json()
    new_vp = (await client.post(
        f"/vocal-candidates/{new_vc['id']}/adopt",
        json={"adopted_by": "director"})).json()
    r = await client.put(
        f"/dialogue-line-revisions/"
        f"{world['dialogue_line_revision_id']}/vocal-selection",
        json={"vocal_performance_revision_id": new_vp["id"],
              "selected_by": "d"})
    assert r.status_code == 200, r.text

    # temptation 2: a NEWER, valid performance mapping (fresh PR,
    # disjoint interval so the channel-conflict rule stays lawful)
    from tests.m17b_seed import (
        HEAD_YAW, candidate_body, channel as m17b_channel,
        kf as m17b_kf,
    )
    newer_candidate = (await client.post(
        f"/creative-entities/{world['subject_id']}/"
        "performance-candidates",
        json=candidate_body(
            [m17b_channel(HEAD_YAW, [m17b_kf(0, 2, 0)])]),
    )).json()
    newer_pr = (await client.post(
        f"/performance-candidates/{newer_candidate['id']}/adopt",
        json={"adopted_by": "s12"})).json()
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/7",
        json=_seg_body(newer_pr["id"], 1500, 2000, 0))
    assert r.status_code == 200, r.text

    # deletion/repointing of every current surface the answer must
    # never need
    await _sql(client, "DELETE FROM shot_vocal_segment_mappings "
                       "WHERE shot_id = :s", {"s": world["shot"]})
    await _sql(client, "DELETE FROM shot_performance_segment_mappings "
                       "WHERE shot_id = :s", {"s": world["shot"]})
    r = await client.put(
        f"/shots/{world['shot']}/semantic-dependencies",
        json={"dependencies": []})
    assert r.status_code == 200, r.text
    await _sql(client, "UPDATE shots SET duration_ms = 9999 "
                       "WHERE id = :s", {"s": world["shot"]})

    after = await _history(client, revision.id)
    assert after == before
    assert after["performance"]["segments"][0][
        "performance_revision_id"] == captured_pr
    assert after["performance"]["segments"][0]["vocal"][
        "vocal_performance_revision_id"] == captured_vp
    assert new_vp["id"] != captured_vp
    assert newer_pr["id"] != captured_pr
    # captured ordering survived the deletion of every current mapping
    assert [seg["position"] for seg in
            after["performance"]["segments"]] == [0, 1]


@pytest.mark.asyncio
async def test_forbidden_current_tables_never_queried(client):
    """Absence proof, not output equivalence: while the schema-8
    historical read runs, no statement may touch any §12-forbidden
    current table — an accidental current read whose value happens to
    agree would still fail here."""
    world, revision = await _capture_schema8(client)

    with _ForbiddenTableSpy(_engine(client)) as spy:
        hist = await _history(client, revision.id)
    assert spy.hits == []
    assert hist["performance"] is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper,fragment", [
    ("missing_parent", "exactly one performance companion parent"),
    ("missing_child", "row count disagrees"),
    ("moved_position", "segment_json/segment_hash disagree"),
    ("altered_field", "column subject_id disagrees"),
    ("altered_segment_json",
     "segment_json/segment_hash disagree"),
    ("altered_spec_json",
     "spec_json/spec_hash disagree with canonical bytes"),
    ("altered_spec_hash",
     "spec_json/spec_hash disagree with canonical bytes"),
    ("snapshot_block_disagreement",
     "snapshot performance block bytes disagree"),
    ("pr_disagreement",
     "disagrees with the immutable PerformanceRevision"),
    ("missing_binding", "synchronization binding is gone"),
    ("binding_disagreement",
     "captured vocal closure disagrees"),
    ("vocal_group_nulled", "vocal-group column"),
    ("vocal_group_grafted", "vocal-group column"),
])
async def test_immutable_closure_corruption_fails_closed(
        client, tamper, fragment):
    world, revision = await _capture_schema8(client)
    hist = await _history(client, revision.id)
    assert hist["performance"] is not None

    if tamper == "missing_parent":
        await _sql(client, f"DELETE FROM {_PARENTS} WHERE "
                           "shot_revision_id = :r", {"r": revision.id})
    elif tamper == "missing_child":
        await _sql(client, f"DELETE FROM {_CHILDREN} WHERE "
                           "shot_revision_id = :r AND position = 1",
                   {"r": revision.id})
    elif tamper == "moved_position":
        await _sql(client, f"UPDATE {_CHILDREN} SET position = 5 "
                           "WHERE shot_revision_id = :r "
                           "AND position = 0", {"r": revision.id})
    elif tamper == "altered_field":
        await _sql(client, f"UPDATE {_CHILDREN} SET subject_id = "
                           "'00000000-0000-4000-8000-0000000000ff' "
                           "WHERE shot_revision_id = :r "
                           "AND position = 0", {"r": revision.id})
    elif tamper == "altered_segment_json":
        await _sql(client, f"UPDATE {_CHILDREN} SET segment_json = "
                           "'{}' WHERE shot_revision_id = :r "
                           "AND position = 0", {"r": revision.id})
    elif tamper == "altered_spec_json":
        await _sql(client, f"UPDATE {_PARENTS} SET spec_json = "
                           "'{\"schema_version\": 1, \"segments\": []}' "
                           "WHERE shot_revision_id = :r",
                   {"r": revision.id})
    elif tamper == "altered_spec_hash":
        await _sql(client, f"UPDATE {_PARENTS} SET spec_hash = "
                           ":h WHERE shot_revision_id = :r",
                   {"h": "0" * 64, "r": revision.id})
    elif tamper == "snapshot_block_disagreement":
        # rewrite the embedded snapshot block WITH a consistent outer
        # snapshot hash, so the only remaining disagreement is the
        # snapshot block vs the companion parent spec bytes
        import json as _json
        from soloring.domain.canonical import (
            canonical_hash as _ch, canonical_json_str as _cj,
        )
        snap = _json.loads((await _row(client, (
            "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
            {"r": revision.id}))["snapshot_json"])
        snap["performance"]["segments"][0]["shot_anchor_ms"] = \
            {"num": 7, "den": 1}
        await _sql(client, "UPDATE shot_revisions SET snapshot_json = "
                           ":sj, snapshot_hash = :sh WHERE id = :r",
                   {"sj": _cj(snap), "sh": _ch(snap),
                    "r": revision.id})
    elif tamper == "pr_disagreement":
        await _sql(client, "UPDATE performance_revisions SET "
                           "performance_kind = 'BODY' WHERE id = :p",
                   {"p": world["pr"]["id"]})
    elif tamper == "missing_binding":
        await _sql(client, "DELETE FROM "
                           "performance_revision_vocal_bindings "
                           "WHERE performance_revision_id = :p",
                   {"p": world["pr"]["id"]})
    elif tamper == "binding_disagreement":
        await _sql(client, "UPDATE performance_revision_vocal_bindings "
                           "SET source_start_sample = "
                           "source_start_sample + 1 "
                           "WHERE performance_revision_id = :p",
                   {"p": world["pr"]["id"]})
    elif tamper == "vocal_group_nulled":
        await _sql(client, f"UPDATE {_CHILDREN} SET "
                           "vocal_performance_revision_id = NULL, "
                           "vocal_binding_hash = NULL, "
                           "vocal_mapping_hash = NULL, "
                           "source_start_sample = NULL, "
                           "source_end_sample_exclusive = NULL, "
                           "sample_rate_hz = NULL, "
                           "vocal_performance_origin_num = NULL, "
                           "vocal_performance_origin_den = NULL, "
                           "vocal_mapping_position = NULL "
                           "WHERE shot_revision_id = :r "
                           "AND position = 0", {"r": revision.id})
    elif tamper == "vocal_group_grafted":
        donor = await _row(client, (
            f"SELECT vocal_performance_revision_id, vocal_binding_hash,"
            f" vocal_mapping_hash, source_start_sample, "
            f"source_end_sample_exclusive, sample_rate_hz, "
            f"vocal_performance_origin_num, "
            f"vocal_performance_origin_den, vocal_mapping_position "
            f"FROM {_CHILDREN} WHERE shot_revision_id = :r "
            "AND position = 0"), {"r": revision.id})
        await _sql(client, f"UPDATE {_CHILDREN} SET "
                           "vocal_performance_revision_id = "
                           ":vocal_performance_revision_id, "
                           "vocal_binding_hash = :vocal_binding_hash, "
                           "vocal_mapping_hash = :vocal_mapping_hash, "
                           "source_start_sample = :source_start_sample, "
                           "source_end_sample_exclusive = "
                           ":source_end_sample_exclusive, "
                           "sample_rate_hz = :sample_rate_hz, "
                           "vocal_performance_origin_num = "
                           ":vocal_performance_origin_num, "
                           "vocal_performance_origin_den = "
                           ":vocal_performance_origin_den, "
                           "vocal_mapping_position = "
                           ":vocal_mapping_position "
                           "WHERE shot_revision_id = :r "
                           "AND position = 1",
                   {"r": revision.id, **donor})

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert fragment in r.json()["message"], r.text


@pytest.mark.asyncio
async def test_fk_shielded_missing_shapes_unconstructible(client):
    """The missing-retained-Blob and missing-VP shapes are shielded by
    FK RESTRICT from the immutable rows that name them — proven
    unconstructible here (IntegrityError), with the reader's
    existence laws standing as the recovery-parity mirror (§13.4)."""
    world, revision = await _capture_schema8(client)
    pr = await _row(client, (
        "SELECT canonical_channel_payload_blob_hash FROM "
        "performance_revisions WHERE id = :p"),
        {"p": world["pr"]["id"]})

    # the driver raises through SQLAlchemy's IntegrityError wrapper
    from sqlalchemy.exc import IntegrityError as SQLIntegrityError

    with pytest.raises(SQLIntegrityError):
        async with _engine(client).begin() as conn:
            await conn.execute(text(
                "DELETE FROM blobs WHERE hash = :h"),
                {"h": pr["canonical_channel_payload_blob_hash"]})
    # the VP is shielded while its immutable binding and the current
    # selection reference it
    with pytest.raises(SQLIntegrityError):
        async with _engine(client).begin() as conn:
            await conn.execute(text(
                "DELETE FROM vocal_performance_revisions "
                "WHERE id = :v"), {"v": world["vp"]["id"]})


@pytest.mark.asyncio
async def test_schema8_wrapping_schema7_keeps_both_planes(client):
    """§11.5: a schema-8 capture over a schema-7 predecessor keeps the
    intra_shot historical plane AND adds the performance plane; a
    present embedded intra_shot block with gone companions refuses."""
    from tests.m16_seed_b import (
        event, post_event, seed_feature_world, state,
    )
    from tests.m17c_seed import ARTICULATION, dialogue_bound_body, make_vp
    from tests.test_m17c_shot_mapping import _add_dependency

    base = await seed_feature_world(client, _factory(client))
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(client, sid, event(fid, 1000, state(),
                                        state("fresh")))

    # the dialogue-bound candidate subject must agree with the VP
    # speaker (M17A subject/speaker agreement) — seed the VP ON the
    # shot's existing dependent entity so both planes share it
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
    hist = await _history(client, revision.id)
    assert hist["snapshot_schema_version"] == 8
    assert hist["intra_shot"] is not None
    assert hist["intra_shot_provenance"] is not None
    assert hist["performance"] is not None
    assert hist["performance"]["segments"][0][
        "performance_revision_id"] == pr["id"]

    # gone companions under a present embedded block refuse (never
    # silent absence) — children first: the events FK-shield the spec
    # parent row
    await _sql(client, "DELETE FROM shot_revision_intra_shot_events "
                       "WHERE shot_revision_id = :r",
               {"r": revision.id})
    await _sql(client, "DELETE FROM shot_revision_intra_shot_specs "
                       "WHERE shot_revision_id = :r",
               {"r": revision.id})
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    assert "intra_shot block without its companion closure" \
        in r.json()["message"], r.text
