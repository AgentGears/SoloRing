"""RevisionService (plan §14).

Lazy capture: build the canonical snapshot from current working state, then
insert-or-reuse with bounded retry. A failed insert means one of two things and
they are NOT conflated (plan §14.3):

  * (shot_id, snapshot_hash) already present -> concurrent identical snapshot;
    return the existing revision (convergence).
  * (shot_id, revision_number) taken by a different snapshot -> revision-number
    collision; re-allocate and retry.

Exhausting the retry budget becomes a stable INTERNAL_INVARIANT_VIOLATION; a raw
IntegrityError never escapes.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.db.models import Shot, ShotRevision
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.domain.shots import (
    _load_active,
    _reference_refs,
    _visual_blob_store,
)
from soloring.errors import ErrorCode, internal_invariant, not_found

MAX_REVISION_ATTEMPTS = 5


async def _snapshot_one_read(
    session: AsyncSession, shot_id: str, *, settings=None
):
    """Shot + references + resolved semantic dependencies + effective M7
    Feature state from ONE SQLite read snapshot (audit F2; M6 §55; M7B §9).

    An AsyncSession alone does not hold a read snapshot across sequential
    SELECT-only statements under Python sqlite3's legacy transaction
    handling, so a concurrent writer could combine two different database
    states (subject from before, references from after) into one captured
    revision — a creative state that never existed. The explicit BEGIN on
    one checked-out connection is the same pattern read_shot_detail uses
    for working-vs-approved comparison. M6C extends the same unit to load
    the working dependency rows and resolve them against current approvals,
    so a capture can never mix dependency states from two moments (§58/§59).

    M7B extended the SAME unit (never a second connection — that would
    race) with the effective Feature-state resolution. M7C completes it:
    the resolved states are RETURNED as part of the captured value instead
    of tripping the temporary capture gate. The NARRATIVE_CONTEXT_REQUIRED
    failure (unassigned + relevant temporal data) remains — that is a
    genuine semantic incompleteness, not an implementation limitation.
    """
    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.continuity.state import (
        narrative_context_required,
        readiness_projection,
        relation_endpoint_required,
        resolve_effective_feature_state,
        resolve_effective_relation_state,
    )

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            row = (
                await conn.execute(
                    select(
                        Shot.subject, Shot.action, Shot.environment,
                        Shot.framing, Shot.camera_motion, Shot.lens,
                        Shot.mood, Shot.duration_ms,
                    ).where(Shot.id == shot_id, Shot.deleted_at.is_(None))
                )
            ).mappings().one_or_none()
            if row is None:
                raise not_found(
                    ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found."
                )
            shot = SimpleNamespace(**dict(row))
            refs = await _reference_refs(conn, shot_id)
            resolved = await resolve_working_dependencies(conn, shot_id)
            outcome = await resolve_effective_feature_state(conn, shot_id)
            relation_outcome = await resolve_effective_relation_state(
                conn, shot_id
            )
            # M7D §9: the two not-ready conditions raise BEFORE any builder
            # invocation — an incomplete current state is never captured.
            # Precedence mirrors the strict endpoint: unassigned first (no
            # authoritative position exists to classify endpoints against).
            if not outcome.assigned and (
                outcome.relevant_temporal_data
                or relation_outcome.relevant_relation_data
            ):
                raise narrative_context_required(shot_id)
            if relation_outcome.endpoint_requirements:
                raise relation_endpoint_required(
                    shot_id, list(relation_outcome.endpoint_requirements)
                )
            # M8 §53: visual resolution runs only after M7 readiness, on
            # the same pinned snapshot; the combined gate (§52.3) raises
            # the first canonical M8 blocker before any builder runs.
            from soloring.visual.readiness import (
                resolve_visual_readiness,
                visual_first_blocker,
            )

            m7_projection = readiness_projection(
                outcome, relation_outcome
            )
            visual_result = await resolve_visual_readiness(
                conn, shot_id,
                m7_projection["continuity_state_ready"],
                m7_projection["readiness_issues"],
                resolved, outcome.states,
                blob_store=_visual_blob_store(settings),
            )
            blocker = visual_first_blocker(visual_result)
            if blocker is not None:
                raise blocker
            # M10D §52: the complete spatial resolution runs on this SAME
            # pinned snapshot, after M7/M8 (frozen global precedence),
            # before any builder invocation. The strict gate raises the
            # first spatial blocker with the full reachable issue set;
            # shots without applicable M10 authority resolve ready/empty.
            from soloring.spatial.resolver import (
                require_spatial_ready, resolve_spatial_continuity,
            )

            spatial_result = await resolve_spatial_continuity(
                conn, shot_id=shot_id, resolved_dependencies=resolved
            )
            require_spatial_ready(spatial_result)
            await conn.commit()
            return (
                shot, refs, resolved, outcome.states,
                relation_outcome.relation_states,
                visual_result, spatial_result,
            )
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


async def _allocate_number(conn, shot_id: str) -> int:
    """MAX(revision_number)+1 inside the caller's held write lock (seam for
    the bounded defense-in-depth collision tests)."""
    return (
        await conn.execute(
            text(
                "SELECT COALESCE(MAX(revision_number), 0) + 1 "
                "FROM shot_revisions WHERE shot_id = :sid"
            ),
            {"sid": shot_id},
        )
    ).scalar()


def _expected_dep_rows(resolved):
    return {
        (dep.entity_id, dep.entity_revision_id, dep.role, dep.position)
        for dep in resolved
    }


def _expected_feature_rows(feature_states):
    """The M7 semantic child set (M7C §9.4): NEVER source_transition_id —
    audit provenance is not semantic identity (APR-022)."""
    return {
        (
            st.entity_id, st.feature_id, st.feature_key, st.feature_kind,
            st.value_type, st.unit, st.value_json, st.value_hash,
            st.source_anchor_type, st.source_anchor_id, st.source_boundary,
        )
        for st in feature_states
    }


def _expected_relation_rows(relation_states):
    """The M7D §10.4 relation semantic set: NEVER source_transition_id
    (APR-022, same rule as features)."""
    return {
        (
            rs.relation_id, rs.subject_entity_id, rs.predicate_id,
            rs.predicate_key, rs.object_entity_id,
            rs.source_anchor_type, rs.source_anchor_id, rs.source_boundary,
        )
        for rs in relation_states
    }


async def _validate_reuse_integrity(
    conn, revision_id, snapshot_json, spec_json, spec_hash,
    resolved, feature_states, relation_states=(), visual_result=None,
    spatial_result=None,
) -> None:
    """Fail-closed validation of an EXISTING winner (M7C §9.4 + M7D §10.4,
    APR-023).

    Full frozen chain, in order: exact parent snapshot bytes, then
    continuity_spec bytes AND hash, then the stored M6 dependency set,
    then the stored M7 feature-state semantic set, then the stored M7D
    relation-state semantic set. Any disagreement — missing, extra, wrong,
    bad hash, wrong anchor/schema, wrong spec bytes — is
    INTERNAL_INVARIANT_VIOLATION. Prohibited outcomes: never
    reuse-decline-and-recapture, never repair/refill, never omit."""
    parent = (
        await conn.execute(
            text(
                "SELECT snapshot_json, continuity_spec_json, "
                "continuity_spec_hash FROM shot_revisions WHERE id = :rid"
            ),
            {"rid": revision_id},
        )
    ).mappings().one_or_none()
    if parent is None:  # pragma: no cover - lookup key came from this row
        raise internal_invariant(
            f"ShotRevision {revision_id} vanished inside its reuse unit."
        )
    if parent["snapshot_json"] != snapshot_json:
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: stored snapshot_json "
            "disagrees with the captured expectation."
        )
    if parent["continuity_spec_json"] != spec_json or             parent["continuity_spec_hash"] != spec_hash:
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: stored continuity spec "
            "bytes/hash disagree with the captured expectation."
        )

    dep_rows = (
        await conn.execute(
            text(
                "SELECT entity_id, entity_revision_id, role, position "
                "FROM shot_revision_entity_dependencies "
                "WHERE shot_revision_id = :rid"
            ),
            {"rid": revision_id},
        )
    ).mappings().all()
    stored_deps = {
        (r["entity_id"], r["entity_revision_id"], r["role"], r["position"])
        for r in dep_rows
    }
    if stored_deps != _expected_dep_rows(resolved):
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: stored M6 dependency "
            "children disagree with the captured expectation."
        )

    feature_rows = (
        await conn.execute(
            text(
                "SELECT entity_id, feature_id, feature_key, feature_kind, "
                "value_type, unit, value_json, value_hash, "
                "source_anchor_type, source_anchor_id, source_boundary "
                "FROM shot_revision_feature_states "
                "WHERE shot_revision_id = :rid"
            ),
            {"rid": revision_id},
        )
    ).mappings().all()
    stored_features = {
        (
            r["entity_id"], r["feature_id"], r["feature_key"],
            r["feature_kind"], r["value_type"], r["unit"], r["value_json"],
            r["value_hash"], r["source_anchor_type"], r["source_anchor_id"],
            r["source_boundary"],
        )
        for r in feature_rows
    }
    if stored_features != _expected_feature_rows(feature_states):
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: stored feature-state "
            "children disagree with the captured expectation."
        )

    relation_rows = (
        await conn.execute(
            text(
                "SELECT relation_id, subject_entity_id, predicate_id, "
                "predicate_key, object_entity_id, source_anchor_type, "
                "source_anchor_id, source_boundary "
                "FROM shot_revision_relation_states "
                "WHERE shot_revision_id = :rid"
            ),
            {"rid": revision_id},
        )
    ).mappings().all()
    stored_relations = {
        (
            r["relation_id"], r["subject_entity_id"], r["predicate_id"],
            r["predicate_key"], r["object_entity_id"],
            r["source_anchor_type"], r["source_anchor_id"],
            r["source_boundary"],
        )
        for r in relation_rows
    }
    if stored_relations != _expected_relation_rows(relation_states):
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: stored relation-state "
            "children disagree with the captured expectation."
        )

    await _validate_spatial_reuse(conn, revision_id, spatial_result)
    if visual_result is not None:
        from soloring.visual.capture import validate_visual_reuse

        await validate_visual_reuse(conn, revision_id, visual_result.pack)


async def _persist_revision_fenced(
    engine,
    shot_id: str,
    snapshot_json: str,
    snapshot_hash: str,
    spec_json: str | None,
    spec_hash: str | None,
    resolved,
    feature_states=(),
    relation_states=(),
    visual_result=None,
    spatial_result=None,
) -> str:
    """The ShotRevision write phase as ONE BEGIN IMMEDIATE unit (M6 §9/§57,
    M6C re-gate blocker 2; M7D §10.3 adds the relation children):

        BEGIN IMMEDIATE
        ↓ reuse lookup by (shot_id, snapshot_hash)
        ↓ existing? → VALIDATE the winner semantically (§10.4) → return it
        ↓ MAX(revision_number)+1
        ↓ INSERT ShotRevision (parent first — the UOW has no mapper
          relationship to order these tables and SQLite FKs are immediate)
        ↓ INSERT all dependency rows from the SAME captured value
        ↓ INSERT all feature-state rows from the SAME captured value
        ↓ INSERT all relation-state rows from the SAME captured value
        ↓ INSERT all visual anchor/item rows from the SAME captured pack
        ↓ COMMIT

    Under the held write lock a revision-number collision is structurally
    impossible, so the bounded retry exists purely as defense in depth for
    the uniqueness constraints; exhaustion is an invariant violation.
    """
    from soloring.generation.repository import busy_error, is_busy_error

    for _ in range(MAX_REVISION_ATTEMPTS):
        revision_id = new_uuid()
        async with engine.connect() as conn:
            try:
                await conn.exec_driver_sql("BEGIN IMMEDIATE")
                existing = (
                    await conn.execute(
                        text(
                            "SELECT id FROM shot_revisions "
                            "WHERE shot_id = :sid AND snapshot_hash = :h"
                        ),
                        {"sid": shot_id, "h": snapshot_hash},
                    )
                ).first()
                if existing is not None:
                    await _validate_reuse_integrity(
                        conn, existing[0], snapshot_json, spec_json,
                        spec_hash, resolved, feature_states, relation_states,
                        visual_result, spatial_result,
                    )
                    await conn.exec_driver_sql("COMMIT")
                    return existing[0]

                number = await _allocate_number(conn, shot_id)
                await conn.execute(
                    text(
                        "INSERT INTO shot_revisions "
                        "(id, shot_id, revision_number, snapshot_json, "
                        " snapshot_hash, continuity_spec_json, "
                        " continuity_spec_hash, created_at) "
                        "VALUES (:id, :sid, :num, :sj, :sh, :cj, :ch, "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                    ),
                    {
                        "id": revision_id,
                        "sid": shot_id,
                        "num": number,
                        "sj": snapshot_json,
                        "sh": snapshot_hash,
                        "cj": spec_json,
                        "ch": spec_hash,
                    },
                )
                if resolved:
                    await conn.execute(
                        text(
                            "INSERT INTO shot_revision_entity_dependencies "
                            "(shot_revision_id, entity_id, entity_revision_id, "
                            " role, position, source) "
                            "VALUES (:rid, :eid, :erv, :role, :pos, :src)"
                        ),
                        [
                            {
                                "rid": revision_id,
                                "eid": dep.entity_id,
                                "erv": dep.entity_revision_id,
                                "role": dep.role,
                                "pos": dep.position,
                                "src": dep.source,
                            }
                            for dep in resolved
                        ],
                    )
                if feature_states:
                    await conn.execute(
                        text(
                            "INSERT INTO shot_revision_feature_states "
                            "(shot_revision_id, entity_id, feature_id, "
                            " feature_key, feature_kind, value_type, unit, "
                            " value_json, value_hash, source_transition_id, "
                            " source_anchor_type, source_anchor_id, "
                            " source_boundary) "
                            "VALUES (:rid, :eid, :fid, :fkey, :fkind, :vt, "
                            ":unit, :vj, :vh, :tid, :sat, :said, :sb)"
                        ),
                        [
                            {
                                "rid": revision_id,
                                "eid": st.entity_id,
                                "fid": st.feature_id,
                                "fkey": st.feature_key,
                                "fkind": st.feature_kind,
                                "vt": st.value_type,
                                "unit": st.unit,
                                "vj": st.value_json,
                                "vh": st.value_hash,
                                "tid": st.source_transition_id,
                                "sat": st.source_anchor_type,
                                "said": st.source_anchor_id,
                                "sb": st.source_boundary,
                            }
                            for st in feature_states
                        ],
                    )
                if relation_states:
                    await conn.execute(
                        text(
                            "INSERT INTO shot_revision_relation_states "
                            "(shot_revision_id, relation_id, "
                            " subject_entity_id, predicate_id, "
                            " predicate_key, object_entity_id, "
                            " source_transition_id, source_anchor_type, "
                            " source_anchor_id, source_boundary) "
                            "VALUES (:rid, :rlid, :sid, :pid, :pkey, :oid, "
                            ":tid, :sat, :said, :sb)"
                        ),
                        [
                            {
                                "rid": revision_id,
                                "rlid": rs.relation_id,
                                "sid": rs.subject_entity_id,
                                "pid": rs.predicate_id,
                                "pkey": rs.predicate_key,
                                "oid": rs.object_entity_id,
                                "tid": rs.source_transition_id,
                                "sat": rs.source_anchor_type,
                                "said": rs.source_anchor_id,
                                "sb": rs.source_boundary,
                            }
                            for rs in relation_states
                        ],
                    )
                if visual_result is not None and visual_result.pack:
                    from soloring.visual.capture import (
                        persist_visual_children,
                    )

                    await persist_visual_children(
                        conn, revision_id, visual_result.pack
                    )
                if spatial_result is not None and \
                        spatial_result.pack is not None:
                    await _persist_spatial_children(
                        conn, revision_id, spatial_result
                    )
                await conn.exec_driver_sql("COMMIT")
                return revision_id
            except IntegrityError:
                with contextlib.suppress(Exception):
                    await conn.exec_driver_sql("ROLLBACK")
                continue
            except OperationalError as exc:
                with contextlib.suppress(Exception):
                    await conn.exec_driver_sql("ROLLBACK")
                if is_busy_error(exc):
                    raise busy_error() from exc
                raise internal_invariant(
                    "Unexpected database error during revision persistence."
                ) from exc

    raise internal_invariant("Revision capture exhausted retries.")





async def capture_revision_with_visual(
    session: AsyncSession, shot_id: str, *, settings=None
):
    """Capture/reuse the immutable ShotRevision (schema 1 | 2 | 3) AND
    return the visual resolution of the SAME coherent read (M9 §10: the
    per-facet requirement map rides with the capture read; historical
    reconstruction never re-reads current requirement policy). No
    module-global patching (r1-gate B2): the state flows through the
    return value only.

    Zero dependencies → the EXACT v1 form with NULL continuity columns.
    Dependencies + zero effective Feature states AND zero effective
    relation states → the EXACT schema-2 form.
    One or more effective states of either kind → schema 3 + continuity-spec 2
    (M7C §4 + M7D §8.3). In every case the snapshot bytes, the spec bytes,
    and ALL immutable child rows derive from the SAME in-memory value
    captured by the one consistent read (M7C §9.1 + M7D §9). Persistence
    is the fenced unit above. ``settings`` is the RUNNING APP's Settings
    when supplied by the HTTP path (r2-gate B2).
    """
    from soloring.continuity.snapshots import (
        build_capturable_snapshot,
        continuity_spec_bytes,
    )

    read = await _snapshot_one_read(session, shot_id, settings=settings)
    shot, refs, resolved = read[0], read[1], read[2]
    feature_states, relation_states, visual_result = read[3], read[4], read[5]
    spatial_result = read[6]
    visual_pack = (
        visual_result.pack if visual_result is not None else None
    )
    spatial_pack = (
        spatial_result.pack if spatial_result is not None else None
    )
    snapshot, continuity_spec = build_capturable_snapshot(
        shot, refs, resolved, feature_states, relation_states, visual_pack,
        spatial_pack,
    )
    snapshot_hash = canonical_hash(snapshot)
    snapshot_json = canonical_json_str(snapshot)
    if continuity_spec is not None:
        spec_json, spec_hash = continuity_spec_bytes(continuity_spec)
    else:
        spec_json, spec_hash = None, None

    revision_id = await _persist_revision_fenced(
        session.bind, shot_id, snapshot_json, snapshot_hash,
        spec_json, spec_hash, resolved, feature_states, relation_states,
        visual_result, spatial_result,
    )
    revision = await session.get(ShotRevision, revision_id)
    assert revision is not None
    return revision, visual_result


async def capture_revision(
    session: AsyncSession, shot_id: str, *, settings=None
) -> ShotRevision:
    """Backward-compatible wrapper discarding the visual state."""
    revision, _visual = await capture_revision_with_visual(
        session, shot_id, settings=settings
    )
    return revision


async def list_revisions(session: AsyncSession, shot_id: str) -> list[dict]:
    """Summary-only revision list; snapshot_json is never selected (plan §16).

    M6C: the summary includes continuity_spec_hash (NULL for v1 revisions)
    so the UI can expose historical continuity provenance per revision."""
    await _load_active(session, shot_id)
    res = await session.execute(
        select(
            ShotRevision.id,
            ShotRevision.shot_id,
            ShotRevision.revision_number,
            ShotRevision.snapshot_hash,
            ShotRevision.continuity_spec_hash,
            ShotRevision.created_at,
        )
        .where(ShotRevision.shot_id == shot_id)
        .order_by(ShotRevision.revision_number)
    )
    return [
        {
            "id": r.id,
            "shot_id": r.shot_id,
            "revision_number": r.revision_number,
            "snapshot_hash": r.snapshot_hash,
            "continuity_spec_hash": r.continuity_spec_hash,
            "created_at": r.created_at,
        }
        for r in res
    ]


async def _persist_spatial_children(conn, revision_id: str,
                                    spatial_result) -> None:
    """Immutable M10 ShotRevision children (M10D §54-58): exactly one
    world row, canonical-order track rows as ONE batch, exactly one plan
    row — every field projecting exactly from the embedded pack."""
    from soloring.domain.canonical import canonical_json_str
    from soloring.spatial.schemas import plan_hash as _plan_hash

    pack = spatial_result.pack
    w = pack["spatial_world"]
    await conn.execute(text(
        "INSERT INTO shot_revision_spatial_worlds (shot_revision_id, "
        "spatial_continuity_hash, spatial_world_id, "
        "spatial_world_state_id, spatial_world_revision_id, "
        "spatial_world_revision_hash, location_entity_id, "
        "location_entity_revision_id, requirement) VALUES (:r, :ch, :w, "
        ":st, :wr, :wrh, :l, :lr, :req)"),
        {"r": revision_id, "ch": spatial_result.spatial_continuity_hash,
         "w": w["spatial_world_id"], "st": w["spatial_world_state_id"],
         "wr": w["spatial_world_revision_id"],
         "wrh": w["spatial_world_revision_hash"],
         "l": w["location_entity_id"],
         "lr": w["location_entity_revision_id"],
         "req": w["requirement"]})
    if pack["staging"]:
        await conn.execute(text(
            "INSERT INTO shot_revision_spatial_track_states ("
            "shot_revision_id, position, spatial_track_id, entity_id, "
            "entity_revision_id, requirement, x_mm, y_mm, z_mm, yaw_udeg, "
            "pitch_udeg, roll_udeg, source_transition_id, "
            "source_anchor_type, source_anchor_id, source_boundary) "
            "VALUES (:r, :pos, :t, :e, :er, :req, :x, :y, :z, :yaw, "
            ":pitch, :roll, :tid, :sat, :said, :sb)"),
            [{"r": revision_id, "pos": i,
              "t": st["spatial_track_id"], "e": st["entity_id"],
              "er": st["entity_revision_id"], "req": st["requirement"],
              "x": st["transform"]["translation_mm"][0],
              "y": st["transform"]["translation_mm"][1],
              "z": st["transform"]["translation_mm"][2],
              "yaw": st["transform"]["rotation_udeg"][0],
              "pitch": st["transform"]["rotation_udeg"][1],
              "roll": st["transform"]["rotation_udeg"][2],
              "tid": st["source_transition"]["spatial_transition_id"],
              "sat": st["source_transition"]["anchor_type"],
              "said": st["source_transition"]["anchor_id"],
              "sb": st["source_transition"]["boundary"]}
             for i, st in enumerate(pack["staging"])])
    plan_json = canonical_json_str(pack["shot_plan"])
    await conn.execute(text(
        "INSERT INTO shot_revision_spatial_plans (shot_revision_id, "
        "plan_hash, plan_json) VALUES (:r, :h, :j)"),
        {"r": revision_id, "h": _plan_hash(pack["shot_plan"]),
         "j": plan_json})


async def _validate_spatial_reuse(conn, revision_id: str,
                                  spatial_result) -> None:
    """M10D §59 reuse integrity: every schema-5 projection must equal the
    embedded pack exactly; schemas 1-4 must carry ZERO spatial children.
    Any disagreement is INTERNAL_INVARIANT_VIOLATION — never
    reuse-decline-and-recapture, never repair."""
    from soloring.domain.canonical import canonical_json_str
    from soloring.spatial.schemas import plan_hash as _plan_hash

    pack = spatial_result.pack if spatial_result is not None else None
    world_row = (await conn.execute(text(
        "SELECT spatial_continuity_hash, spatial_world_id, "
        "spatial_world_state_id, spatial_world_revision_id, "
        "spatial_world_revision_hash, location_entity_id, "
        "location_entity_revision_id, requirement FROM "
        "shot_revision_spatial_worlds WHERE shot_revision_id = :r"),
        {"r": revision_id})).mappings().first()
    track_rows = [dict(r) for r in (await conn.execute(text(
        "SELECT position, spatial_track_id, entity_id, "
        "entity_revision_id, requirement, x_mm, y_mm, z_mm, yaw_udeg, "
        "pitch_udeg, roll_udeg, source_transition_id, source_anchor_type, "
        "source_anchor_id, source_boundary FROM "
        "shot_revision_spatial_track_states WHERE shot_revision_id = :r "
        "ORDER BY position"), {"r": revision_id})).mappings().all()]
    plan_row = (await conn.execute(text(
        "SELECT plan_hash, plan_json FROM shot_revision_spatial_plans "
        "WHERE shot_revision_id = :r"), {"r": revision_id})).mappings() \
        .first()

    if pack is None:
        if world_row is not None or track_rows or plan_row is not None:
            raise internal_invariant(
                f"ShotRevision {revision_id} reuse: spatial children "
                "exist for a schema 1-4 snapshot.")
        return
    if world_row is None or plan_row is None:
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: schema-5 snapshot is "
            "missing its world or plan child.")
    w = pack["spatial_world"]
    expected_world = {
        "spatial_continuity_hash": spatial_result.spatial_continuity_hash,
        "spatial_world_id": w["spatial_world_id"],
        "spatial_world_state_id": w["spatial_world_state_id"],
        "spatial_world_revision_id": w["spatial_world_revision_id"],
        "spatial_world_revision_hash": w["spatial_world_revision_hash"],
        "location_entity_id": w["location_entity_id"],
        "location_entity_revision_id": w["location_entity_revision_id"],
        "requirement": w["requirement"]}
    if dict(world_row) != expected_world:
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: stored spatial world "
            "child disagrees with the embedded pack.")
    expected_tracks = [{
        "position": i,
        "spatial_track_id": st["spatial_track_id"],
        "entity_id": st["entity_id"],
        "entity_revision_id": st["entity_revision_id"],
        "requirement": st["requirement"],
        "x_mm": st["transform"]["translation_mm"][0],
        "y_mm": st["transform"]["translation_mm"][1],
        "z_mm": st["transform"]["translation_mm"][2],
        "yaw_udeg": st["transform"]["rotation_udeg"][0],
        "pitch_udeg": st["transform"]["rotation_udeg"][1],
        "roll_udeg": st["transform"]["rotation_udeg"][2],
        "source_transition_id": st["source_transition"][
            "spatial_transition_id"],
        "source_anchor_type": st["source_transition"]["anchor_type"],
        "source_anchor_id": st["source_transition"]["anchor_id"],
        "source_boundary": st["source_transition"]["boundary"]}
        for i, st in enumerate(pack["staging"])]
    if track_rows != expected_tracks:
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: stored spatial track "
            "children disagree with the embedded pack.")
    expected_plan_json = canonical_json_str(pack["shot_plan"])
    if plan_row["plan_json"] != expected_plan_json or \
            plan_row["plan_hash"] != _plan_hash(pack["shot_plan"]):
        raise internal_invariant(
            f"ShotRevision {revision_id} reuse: stored spatial plan "
            "child bytes/hash disagree with the embedded pack.")
