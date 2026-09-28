"""M17C-B PF-02: Shot-local Performance working mappings and readiness.

Frozen R4 §8–§9 laws plus the B-F corrective set:

- B-F2: PF-02 consumes one downstream PerformanceRevision integrity
  seam — generic revisions prove their adopted candidate's immutable
  closure and canonical payload; dialogue-bound revisions additionally
  prove the FULL M17C-A revision vocal-binding closure (binding
  bytes/hash, candidate↔revision binding equality, VP structural
  authority; PUT additionally pays the retained-media price). No PF-02
  code path reads raw binding scalars without the seam.
- B-F3: applicability comes from the immutable PF-03 discriminator,
  never from the nullable ``vocal_mapping_position`` payload shape.
- B-F6: one stored-mapping integrity verifier (schema version, rational
  canonicality, canonical JSON/hash, nonempty interval, immutable
  PR-domain containment, mode/position shape) gates live reads and
  readiness.
- B-F5: readiness revalidates the picture-intersection law against the
  CURRENT Shot duration without rewriting stored intent.
- B-F8: a MISSING VocalPerformanceSelection row is corruption (M17A
  law); only a lawful UNSET or different selection is STALE.

``ShotPerformanceSegmentMapping`` is mutable Shot intent (§20.2 last
committed PUT wins); readiness is a read-time PROJECTION never persisted
as authority (§9.1). Dialogue-bound mappings store the exact interval/
anchor mechanically induced from the paired ``ShotVocalSegmentMapping``
through the immutable revision vocal binding — no tolerance (§8.3).
"""

from __future__ import annotations

from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.now import db_now
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.performance import revision as revision_svc
from soloring.performance.m17c_binding import (
    verify_revision_sync_classification,
    verify_revision_vocal_binding,
    verify_revision_vocal_binding_read_grade,
)
from soloring.performance.m17c_models import (
    PerformanceRevisionVocalBinding,
    ShotPerformanceSegmentMapping,
)
from soloring.performance.models import (
    PerformanceCandidate,
    PerformanceRevision,
    ShotVocalSegmentMapping,
    VocalPerformanceRevision,
    VocalPerformanceSelection,
)
from soloring.performance.temporal import (RationalError,
                                           canonical_rational)

READY = "READY"
STALE_VOCAL_SELECTION = "STALE_VOCAL_SELECTION"
BLOCKED_BINDING_INTEGRITY = "BLOCKED_BINDING_INTEGRITY"
BLOCKED_TIMING_MISMATCH = "BLOCKED_TIMING_MISMATCH"
BLOCKED_SUBJECT_OR_PROJECT = "BLOCKED_SUBJECT_OR_PROJECT"
BLOCKED_CHANNEL_CONFLICT = "BLOCKED_CHANNEL_CONFLICT"
BLOCKED_SHOT_DEPENDENCY = "BLOCKED_SHOT_DEPENDENCY"

SQLITE_INT_MAX = 2 ** 63 - 1


def _invalid(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.PERFORMANCE_SHOT_MAPPING_INVALID,
                         message, status_code=422)


def _validate_position(position, *, what: str = "position") -> None:
    """SR2-09/IR-04: the shared path-position law for PUT and DELETE —
    the ONE neutral primitive from ``temporal`` (integer, bool
    excluded, SQLite-i64 domain), mapped into this service's stable
    error vocabulary."""
    from soloring.performance.temporal import (
        PositionError, validate_mapping_position)
    try:
        validate_mapping_position(position)
    except PositionError as exc:
        raise _invalid(f"{what}: {exc}") from exc


def _mismatch(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.PERFORMANCE_VOCAL_MAPPING_MISMATCH,
                         message, status_code=422)


def _corrupt(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                         message, status_code=500)


def _fraction(num: int, den: int) -> Fraction:
    return Fraction(num, den)


def _pr_domain(pr) -> tuple[Fraction, Fraction]:
    return (_fraction(pr.temporal_start_num, pr.temporal_start_den),
            _fraction(pr.temporal_end_num, pr.temporal_end_den))


def _stored_interval(row) -> tuple[Fraction, Fraction]:
    return (_fraction(row.performance_start_num,
                      row.performance_start_den),
            _fraction(row.performance_end_num,
                      row.performance_end_den))


def _shot_interval(row) -> tuple[Fraction, Fraction]:
    anchor = _fraction(row.shot_anchor_num, row.shot_anchor_den)
    start, end = _stored_interval(row)
    return anchor, anchor + (end - start)


def _induced_interval(binding, vocal_mapping) -> tuple[Fraction, Fraction]:
    """frozen §8.3 exact induction through the immutable binding."""
    origin = _fraction(binding.performance_origin_num,
                       binding.performance_origin_den)
    rate = binding.sample_rate_hz
    s0 = binding.source_start_sample
    p0 = origin + Fraction(
        (vocal_mapping.source_start_sample - s0) * 1000, rate)
    p1 = origin + Fraction(
        (vocal_mapping.source_end_sample_exclusive - s0) * 1000, rate)
    return p0, p1


# ---------------------------------------------------------------------------
# B-F2/SR2-04/SR2-05: the downstream PerformanceRevision integrity seam
# ---------------------------------------------------------------------------

async def verify_performance_revision_for_shot_use(
        session: AsyncSession, settings, pr: PerformanceRevision, *,
        media: bool) -> dict:
    """The ONE downstream seam PF-02 consumes (B-F2 + SR2-04/SR2-05).

    Both grades first prove the adopted candidate's immutable closure
    (canonical payload included) AND — SR2-04 — that the
    PerformanceRevision itself reproduces its adopted candidate's
    copied closure with lawful persisted adoption metadata
    (``revalidate_winner``; candidate integrity alone is never treated
    as revision integrity). ``media=True`` (PUT — fresh authority) then
    pays the FULL M17C-A binding verifier including retained VP media;
    ``media=False`` (readiness/list — the C3-01 read cost boundary)
    runs the SHARED authoritative read-grade binding verifier
    (SR2-05 — never a weaker parallel copy); neither grade rehashes
    VP audio on the read path.
    """
    candidate = await session.get(PerformanceCandidate,
                                  pr.adopted_candidate_id)
    if candidate is None:
        raise _corrupt("adopted revision's candidate is missing")
    # IR-03: persisted candidate authority goes through the shared
    # HISTORICAL seam — admission-shaped defects of an already-persisted
    # candidate are corruption (500), preserving the diagnostic
    integrity = await revision_svc.verify_candidate_integrity_historical(
        session, settings, candidate)
    # SR2-04: revision copied closure == adopted candidate + persisted
    # adoption-metadata grammar, with the 500 corruption contract — an
    # admission-shaped failure from the shared grammar validator is
    # TRANSLATED here (this is a persisted-history read, never a fresh
    # client request)
    try:
        revision_svc.revalidate_winner_historical(pr, candidate)
    except SoloRingError as exc:
        raise _corrupt(
            f"adopted revision closure/adoption metadata violates "
            f"persisted law: {exc.message}") from exc
    classification = await verify_revision_sync_classification(session, pr)
    if classification.sync_mode == "VOCAL_V1":
        binding = await session.get(PerformanceRevisionVocalBinding, pr.id)
        if media:
            await verify_revision_vocal_binding(
                session, settings, pr, binding)
            return {"classification": classification, "binding": binding,
                    "candidate": candidate,
                    "payload_document": integrity["payload_document"]}
        return await verify_revision_vocal_binding_read_grade(
            session, settings, pr, binding,
            classification=classification)
    return {"classification": classification, "binding": None,
            "candidate": candidate,
            "payload_document": integrity["payload_document"]}


def _mapping_doc(row) -> dict:
    return {
        "mapping_schema_version": 1,
        "performance_revision_id": row.performance_revision_id,
        "performance_start_ms": {"num": row.performance_start_num,
                                 "den": row.performance_start_den},
        "performance_end_ms": {"num": row.performance_end_num,
                               "den": row.performance_end_den},
        "shot_anchor_ms": {"num": row.shot_anchor_num,
                           "den": row.shot_anchor_den},
        "vocal_mapping_position": row.vocal_mapping_position,
    }


def verify_persisted_mapping_structural(
        *, shot_id, position, performance_revision_id,
        mapping_schema_version,
        performance_start_num, performance_start_den,
        performance_end_num, performance_end_den,
        shot_anchor_num, shot_anchor_den,
        vocal_mapping_position, mapping_json, mapping_hash,
        domain_start_num, domain_start_den,
        domain_end_num, domain_end_den,
        expected_mode: str) -> None:
    """IR-02: the ONE transport-neutral persisted PF-02 mapping law —
    every STORED structural/immutable property, shared verbatim by the
    live readiness/list path (ORM rows) and staged-sqlite recovery.
    Deliberately excludes ALL mutable current-readiness concerns
    (current Shot duration, picture intersection, current selection,
    paired vocal mapping existence or CURRENT VP identity). Raises the
    500 corruption contract on any violation."""
    def _fail(what: str):
        return _corrupt(
            f"stored mapping {shot_id!r}@{position!r} {what}")

    # the row's position and vocal_mapping_position are actual
    # SQLite-safe mapping positions wherever storage could represent a
    # non-position (SQLite affinity can persist TEXT/REAL there)
    if not isinstance(position, int) or isinstance(position, bool) \
            or position < 0 or position > SQLITE_INT_MAX:
        raise _fail(
            f"row position {position!r} is not a SQLite-safe mapping "
            "position")
    if isinstance(mapping_schema_version, bool) \
            or not isinstance(mapping_schema_version, int) \
            or mapping_schema_version != 1:
        raise _fail("schema version is not 1")
    for num, den, what in (
            (performance_start_num, performance_start_den,
             "performance_start"),
            (performance_end_num, performance_end_den,
             "performance_end"),
            (shot_anchor_num, shot_anchor_den, "shot_anchor")):
        if isinstance(num, bool) or isinstance(den, bool) \
                or not isinstance(num, int) or not isinstance(den, int):
            raise _fail(f"{what} rational is not an integer pair")
        try:
            cn, cd = canonical_rational(num, den)
        except RationalError as exc:
            raise _fail(
                f"{what} rational invalid: {exc.message}") from exc
        if (cn, cd) != (num, den):
            raise _fail(f"{what} rational is not canonical")
    if not performance_start_num < performance_end_num:
        raise _fail("interval is empty or inverted")
    domain_lo = Fraction(domain_start_num, domain_start_den)
    domain_hi = Fraction(domain_end_num, domain_end_den)
    start = Fraction(performance_start_num, performance_start_den)
    end = Fraction(performance_end_num, performance_end_den)
    if not (domain_lo <= start and end <= domain_hi):
        raise _fail(
            "interval lies outside the immutable PerformanceRevision "
            "domain")
    # IR-03/B-F3: immutable classification ↔ vocal_mapping_position
    # shape — applicability from the discriminator, never from the
    # nullable payload shape
    if expected_mode == "VOCAL_V1":
        if vocal_mapping_position is None:
            raise _fail(
                "maps a VOCAL_V1 PerformanceRevision without "
                "vocal_mapping_position")
    elif vocal_mapping_position is not None:
        raise _fail(
            "carries vocal_mapping_position on a non-VOCAL_V1 "
            "PerformanceRevision")
    if vocal_mapping_position is not None \
            and (not isinstance(vocal_mapping_position, int)
                 or isinstance(vocal_mapping_position, bool)
                 or vocal_mapping_position < 0
                 or vocal_mapping_position > SQLITE_INT_MAX):
        raise _fail(
            f"persists vocal_mapping_position "
            f"{vocal_mapping_position!r} that is not a SQLite-safe "
            "mapping position")
    doc = {
        "mapping_schema_version": 1,
        "performance_revision_id": performance_revision_id,
        "performance_start_ms": {"num": performance_start_num,
                                 "den": performance_start_den},
        "performance_end_ms": {"num": performance_end_num,
                               "den": performance_end_den},
        "shot_anchor_ms": {"num": shot_anchor_num,
                           "den": shot_anchor_den},
        "vocal_mapping_position": vocal_mapping_position,
    }
    if mapping_json != canonical_json_str(doc) or \
            mapping_hash != canonical_hash(doc):
        raise _fail("canonical bytes/hash diverge")


def _verify_stored_mapping(row, pr, *, expected_mode: str) -> None:
    """B-F6/IR-02: live-side adapter — the stored ORM row through the
    ONE shared transport-neutral persisted law."""
    verify_persisted_mapping_structural(
        shot_id=row.shot_id,
        position=row.position,
        performance_revision_id=row.performance_revision_id,
        mapping_schema_version=row.mapping_schema_version,
        performance_start_num=row.performance_start_num,
        performance_start_den=row.performance_start_den,
        performance_end_num=row.performance_end_num,
        performance_end_den=row.performance_end_den,
        shot_anchor_num=row.shot_anchor_num,
        shot_anchor_den=row.shot_anchor_den,
        vocal_mapping_position=row.vocal_mapping_position,
        mapping_json=row.mapping_json,
        mapping_hash=row.mapping_hash,
        domain_start_num=pr.temporal_start_num,
        domain_start_den=pr.temporal_start_den,
        domain_end_num=pr.temporal_end_num,
        domain_end_den=pr.temporal_end_den,
        expected_mode=expected_mode)


async def _dependency_ids(session, shot_id: str) -> set[str]:
    from soloring.continuity.models import ShotEntityDependency
    rows = (await session.execute(
        select(ShotEntityDependency.entity_id).where(
            ShotEntityDependency.shot_id == shot_id))).scalars().all()
    return set(rows)


async def _vp_dlr_id(session, binding) -> str:
    vp = await session.get(VocalPerformanceRevision,
                            binding.vocal_performance_revision_id)
    if vp is None:
        raise _corrupt(
            "revision vocal binding names a missing VP — corruption")
    return vp.dialogue_line_revision_id


async def _selection_posture(session, binding) -> tuple[str, str | None]:
    """(state, selected_vp_id) — B-F8: a MISSING selection row is
    corruption (every DLR is created with one; M17A law); lawful
    states are UNSET (selected None) and SELECTED."""
    dlr_id = await _vp_dlr_id(session, binding)
    sel = await session.get(VocalPerformanceSelection, dlr_id)
    if sel is None:
        raise _corrupt(
            f"DialogueLineRevision {dlr_id} has no selection row — "
            "every revision is created with one; this is corruption, "
            "not a readiness state")
    selected = sel.selected_vocal_performance_revision_id
    return ("UNSET" if selected is None else "SELECTED"), selected


async def put_shot_performance_segment_mapping(
        session: AsyncSession, settings, *, shot_id: str, position: int,
        performance_revision_id: str,
        performance_start_num: int, performance_start_den: int,
        performance_end_num: int, performance_end_den: int,
        shot_anchor_num: int, shot_anchor_den: int,
        vocal_mapping_position: int | None) -> ShotPerformanceSegmentMapping:
    from soloring.domain.models import Shot
    _validate_position(position)
    if vocal_mapping_position is not None:
        _validate_position(vocal_mapping_position,
                           what="vocal_mapping_position")
    shot = await session.get(Shot, shot_id)
    if shot is None:
        raise not_found(ErrorCode.SHOT_NOT_FOUND,
                        f"shot {shot_id!r} not found")
    if shot.duration_ms is None or shot.duration_ms <= 0:
        raise SoloRingError(ErrorCode.SHOT_DURATION_REQUIRED,
                            "Shot.duration_ms must be present and > 0 for "
                            "performance segment mapping", status_code=422)
    pr = await session.get(PerformanceRevision, performance_revision_id)
    if pr is None:
        raise not_found(ErrorCode.PERFORMANCE_REVISION_NOT_FOUND,
                        f"performance revision {performance_revision_id!r} "
                        "not found")

    # B-F2: the downstream seam at FULL strength (media=True — a PUT
    # is fresh authority creation and pays the retained-media price)
    seam = await verify_performance_revision_for_shot_use(
        session, settings, pr, media=True)
    classification = seam["classification"]
    binding = seam["binding"]
    dialogue_bound = classification.sync_mode == "VOCAL_V1"

    try:
        sn, sd = canonical_rational(performance_start_num,
                                    performance_start_den)
        en, ed = canonical_rational(performance_end_num,
                                    performance_end_den)
        an, ad = canonical_rational(shot_anchor_num, shot_anchor_den)
    except RationalError:
        raise

    if dialogue_bound:
        if vocal_mapping_position is None:
            raise SoloRingError(
                ErrorCode.PERFORMANCE_VOCAL_MAPPING_REQUIRED,
                "a dialogue-bound PerformanceRevision requires "
                "vocal_mapping_position", status_code=422)
        vocal = await session.get(ShotVocalSegmentMapping,
                                  (shot_id, vocal_mapping_position))
        if vocal is None:
            raise _mismatch(
                f"paired ShotVocalSegmentMapping {shot_id!r}@"
                f"{vocal_mapping_position} does not exist on this Shot")
        if vocal.vocal_performance_revision_id != \
                binding.vocal_performance_revision_id:
            raise _mismatch(
                "paired vocal mapping names VocalPerformanceRevision "
                f"{vocal.vocal_performance_revision_id!r} != the "
                "immutable revision binding VP "
                f"{binding.vocal_performance_revision_id!r}")
        if vocal.sample_rate_hz != binding.sample_rate_hz:
            raise _mismatch(
                "paired vocal mapping rate != the immutable revision "
                "binding rate")
        if not (binding.source_start_sample
                <= vocal.source_start_sample
                and vocal.source_end_sample_exclusive
                <= binding.source_end_sample_exclusive):
            raise _mismatch(
                "paired vocal mapping source interval "
                f"[{vocal.source_start_sample}, "
                f"{vocal.source_end_sample_exclusive}) lies outside the "
                "immutable revision binding source interval "
                f"[{binding.source_start_sample}, "
                f"{binding.source_end_sample_exclusive})")
        # current selection is working-readiness policy at PUT (§8.3);
        # B-F8: a missing selection row is corruption, never stale
        state, selected = await _selection_posture(session, binding)
        if selected != binding.vocal_performance_revision_id:
            raise SoloRingError(
                ErrorCode.PERFORMANCE_VOCAL_SELECTION_STALE,
                "the paired vocal mapping's VocalPerformanceRevision is "
                "not the current explicit selection for its "
                "DialogueLineRevision", status_code=409)
        # exact induction: supplied interval and anchor must equal the
        # mechanically induced values with NO tolerance (frozen §8.3)
        p0, p1 = _induced_interval(binding, vocal)
        if (Fraction(sn, sd) != p0 or Fraction(en, ed) != p1):
            raise _mismatch(
                f"supplied performance interval [{sn}/{sd}, {en}/{ed}) "
                f"!= the exact induced interval [{p0}, {p1}) — no "
                "tolerance is permitted")
        van = Fraction(vocal.shot_anchor_num, vocal.shot_anchor_den)
        if Fraction(an, ad) != van:
            raise _mismatch(
                f"supplied Shot anchor {an}/{ad} != the paired vocal "
                f"mapping anchor {van} — they must be exactly equal")
    else:
        if vocal_mapping_position is not None:
            raise _invalid(
                "a generic (non-dialogue-bound) PerformanceRevision "
                "must not carry vocal_mapping_position")

    # shared interval laws (frozen §8.2/§8.3)
    start = Fraction(sn, sd)
    end = Fraction(en, ed)
    if start >= end:
        raise _invalid("mapped performance interval is empty or inverted")
    domain = _pr_domain(pr)
    if not (domain[0] <= start and end <= domain[1]):
        raise _invalid(
            f"mapped interval [{sn}/{sd}, {en}/{ed}) lies outside the "
            f"immutable PerformanceRevision domain "
            f"[{domain[0]}, {domain[1]})")
    if pr.project_id != shot.project_id:
        raise _invalid(
            "Shot and PerformanceRevision resolve to different projects")
    # picture intersection (J/L-cut lawful when intersecting)
    shot_start, shot_end = (
        Fraction(an, ad), Fraction(an, ad) + (end - start))
    if not (shot_end > 0 and shot_start < Fraction(shot.duration_ms)):
        raise SoloRingError(
            ErrorCode.MAPPING_NO_SHOT_OVERLAP,
            "mapped interval does not intersect the Shot picture "
            "interval (entirely before/after)", status_code=422)

    doc = {"mapping_schema_version": 1,
           "performance_revision_id": pr.id,
           "performance_start_ms": {"num": sn, "den": sd},
           "performance_end_ms": {"num": en, "den": ed},
           "shot_anchor_ms": {"num": an, "den": ad},
           "vocal_mapping_position": vocal_mapping_position}
    mapping_json = canonical_json_str(doc)
    mapping_hash = canonical_hash(doc)
    # SR2-08: ONE atomic SQLite upsert on the (shot_id, position) key —
    # the canonical document/hash are constructed deterministically
    # BEFORE persistence, the conflict path replaces the complete
    # mutable mapping in a single statement, and created_at is NOT in
    # the update set (the original creation timestamp is preserved).
    # Concurrent first PUTs to the same position therefore serialize on
    # SQLite's single writer and BOTH commit as ordinary 200s — no raw
    # uniqueness/lock exception escapes the API, no duplicate or torn
    # row can exist, and the durable row always equals exactly one
    # complete submitted payload.
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    now = await db_now(session)
    stmt = sqlite_insert(ShotPerformanceSegmentMapping).values(
        shot_id=shot_id, position=position,
        performance_revision_id=pr.id,
        performance_start_num=sn, performance_start_den=sd,
        performance_end_num=en, performance_end_den=ed,
        shot_anchor_num=an, shot_anchor_den=ad,
        vocal_mapping_position=vocal_mapping_position,
        mapping_schema_version=1,
        mapping_json=mapping_json, mapping_hash=mapping_hash,
        created_at=now, updated_at=now)
    stmt = stmt.on_conflict_do_update(
        index_elements=["shot_id", "position"],
        set_={"performance_revision_id": pr.id,
              "performance_start_num": sn, "performance_start_den": sd,
              "performance_end_num": en, "performance_end_den": ed,
              "shot_anchor_num": an, "shot_anchor_den": ad,
              "vocal_mapping_position": vocal_mapping_position,
              "mapping_json": mapping_json,
              "mapping_hash": mapping_hash,
              "updated_at": now})
    await session.execute(stmt)
    row = await session.get(ShotPerformanceSegmentMapping,
                            (shot_id, position))
    await session.flush()
    return row


async def delete_shot_performance_segment_mapping(
        session: AsyncSession, *, shot_id: str, position: int) -> None:
    # SR2-09: the shared position law — DELETE must refuse an
    # out-of-domain integer with a stable 4xx BEFORE any storage access
    # (an unbounded Python int would otherwise reach SQLite and surface
    # as a raw OverflowError 500); 2^63-1 stays DB-safe and idempotent.
    _validate_position(position)
    row = await session.get(ShotPerformanceSegmentMapping,
                            (shot_id, position))
    if row is not None:
        await session.delete(row)
        await session.flush()


def _row_view(row) -> dict:
    return {
        "shot_id": row.shot_id, "position": row.position,
        "performance_revision_id": row.performance_revision_id,
        "performance_start_ms": {"num": row.performance_start_num,
                                 "den": row.performance_start_den},
        "performance_end_ms": {"num": row.performance_end_num,
                               "den": row.performance_end_den},
        "shot_anchor_ms": {"num": row.shot_anchor_num,
                           "den": row.shot_anchor_den},
        "vocal_mapping_position": row.vocal_mapping_position,
        "mapping_hash": row.mapping_hash,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


async def _pr_subject(session, row) -> str:
    pr = await session.get(PerformanceRevision,
                            row.performance_revision_id)
    if pr is None:
        raise _corrupt(
            f"mapping {row.shot_id}@{row.position} references a missing "
            "PerformanceRevision — corruption")
    return pr.subject_id


async def _pr_channel_keys(session, settings, seam_payload) -> set[str]:
    return {ch["channel_key"] for ch in seam_payload["channels"]}


async def _project_one(session, settings, shot, row, seam_by_pr,
                       dependency_ids) -> tuple[str, dict | None]:
    pr = await session.get(PerformanceRevision,
                            row.performance_revision_id)
    if pr is None:
        raise _corrupt(
            f"mapping {row.shot_id}@{row.position} references a missing "
            "PerformanceRevision — corruption")

    # B-F2: readiness consumes the same downstream seam (read-grade,
    # no retained-media rehash) — hard upstream corruption fails closed
    seam = await verify_performance_revision_for_shot_use(
        session, settings, pr, media=False)
    classification = seam["classification"]

    # B-F6/B-F3: stored-row structural integrity with the
    # discriminator-driven shape law, BEFORE any current-context law
    _verify_stored_mapping(row, pr,
                           expected_mode=classification.sync_mode)

    if pr.project_id != shot.project_id:
        return (BLOCKED_SUBJECT_OR_PROJECT,
                {"reason": "PerformanceRevision belongs to another "
                           "project than the Shot"})
    if pr.subject_id not in dependency_ids:
        return (BLOCKED_SHOT_DEPENDENCY,
                {"reason": "the Performance subject is not a current "
                           "semantic dependency of this Shot"})

    # B-F5: revalidate the picture-intersection law against the CURRENT
    # Shot duration (mutable) without rewriting stored intent
    if shot.duration_ms is None or shot.duration_ms <= 0:
        return (BLOCKED_TIMING_MISMATCH,
                {"reason": "the Shot no longer carries a lawful "
                           "duration"})
    shot_start, shot_end = _shot_interval(row)
    if not (shot_end > 0 and shot_start < Fraction(shot.duration_ms)):
        return (BLOCKED_TIMING_MISMATCH,
                {"reason": "the stored mapping no longer intersects "
                           "the current Shot picture interval"})

    if classification.sync_mode == "VOCAL_V1":
        binding = seam["binding"]
        vocal = await session.get(ShotVocalSegmentMapping,
                                  (row.shot_id,
                                   row.vocal_mapping_position))
        if vocal is None:
            # B-F4: API-creatable lawful blocked working state (the
            # paired vocal mapping was deleted through the supported
            # DELETE) — readiness reports blocked; recovery preserves.
            return (BLOCKED_BINDING_INTEGRITY,
                    {"reason": "the paired vocal mapping is missing"})
        if vocal.vocal_performance_revision_id != \
                binding.vocal_performance_revision_id:
            # SR2-03: the supported M17A vocal PUT can repoint the
            # paired working vocal mapping to the now-current
            # selection — lawful mutable working drift against the
            # immutable revision binding. Readiness reports blocked
            # (never 500), and neither the working mapping nor the
            # immutable binding is rewritten during diagnosis.
            return (BLOCKED_BINDING_INTEGRITY,
                    {"reason": "the paired vocal mapping is currently "
                               "bound to a different "
                               "VocalPerformanceRevision (lawful "
                               "working drift; the immutable revision "
                               "binding is unchanged)",
                     "paired_vocal_performance_revision_id":
                         vocal.vocal_performance_revision_id,
                     "bound_vocal_performance_revision_id":
                         binding.vocal_performance_revision_id})
        # B-F8: missing selection row is corruption inside
        # _selection_posture; lawful UNSET/different selection is STALE
        state, selected = await _selection_posture(session, binding)
        if selected != binding.vocal_performance_revision_id:
            return (STALE_VOCAL_SELECTION,
                    {"mapped_vocal_performance_revision_id":
                     binding.vocal_performance_revision_id,
                     "selected_vocal_performance_revision_id": selected,
                     "selection_state": state})
        # exact induced-interval equality against CURRENT state
        p0, p1 = _induced_interval(binding, vocal)
        s0, s1 = _stored_interval(row)
        if s0 != p0 or s1 != p1 or \
                Fraction(row.shot_anchor_num,
                         row.shot_anchor_den) != Fraction(
                    vocal.shot_anchor_num, vocal.shot_anchor_den):
            return (BLOCKED_TIMING_MISMATCH,
                    {"reason": "the stored interval/anchor no longer "
                               "equals the exact induced values "
                               "(paired vocal mapping changed)"})
    return READY, None


async def project_shot_performance_readiness(
        session: AsyncSession, settings, *, shot_id: str) -> dict:
    """frozen §9.1: readiness is a projection, never persisted."""
    from soloring.domain.models import Shot
    shot = await session.get(Shot, shot_id)
    if shot is None:
        raise not_found(ErrorCode.SHOT_NOT_FOUND,
                        f"shot {shot_id!r} not found")
    rows = (await session.execute(
        select(ShotPerformanceSegmentMapping).where(
            ShotPerformanceSegmentMapping.shot_id == shot_id)
        .order_by(ShotPerformanceSegmentMapping.position))
    ).scalars().all()

    dependency_ids = await _dependency_ids(session, shot_id)
    row_states = []
    states = []
    for row in rows:
        state, diagnostics = await _project_one(
            session, settings, shot, row, {}, dependency_ids)
        row_states.append([row, state, diagnostics])
        states.append(state)

    # channel conflict (frozen §8.5): same subject + overlapping shot
    # intervals + intersecting immutable channel_key sets. Channel keys
    # come from the seam's verified canonical payload.
    async def keys_for(row):
        pr = await session.get(PerformanceRevision,
                                row.performance_revision_id)
        seam = await verify_performance_revision_for_shot_use(
            session, settings, pr, media=False)
        return await _pr_channel_keys(session, settings,
                                      seam["payload_document"])

    subjects = [await _pr_subject(session, r[0]) for r in row_states]
    for i in range(len(row_states)):
        row_i, state_i, _ = row_states[i]
        if state_i != READY:
            continue
        for j in range(i + 1, len(row_states)):
            row_j, state_j, _ = row_states[j]
            if state_j != READY:
                continue
            si0, si1 = _shot_interval(row_i)
            sj0, sj1 = _shot_interval(row_j)
            if not (si0 < sj1 and sj0 < si1):
                continue
            if subjects[i] != subjects[j]:
                continue
            if not (await keys_for(row_i) & await keys_for(row_j)):
                continue
            for k in (i, j):
                row_states[k][1] = BLOCKED_CHANNEL_CONFLICT
                row_states[k][2] = {
                    "conflict_with_position":
                        row_states[j if k == i else i][0].position}
            states[i] = BLOCKED_CHANNEL_CONFLICT
            states[j] = BLOCKED_CHANNEL_CONFLICT

    segments = []
    for row, state, diagnostics in row_states:
        view = _row_view(row)
        view["readiness"] = state
        if diagnostics:
            view["readiness_diagnostics"] = diagnostics
        segments.append(view)
    return {"shot_id": shot_id,
            "ready": all(s == READY for s in states),
            "segments": segments}


async def list_shot_performance_segment_mappings(
        session: AsyncSession, settings, *, shot_id: str) -> list[dict]:
    projection = await project_shot_performance_readiness(
        session, settings, shot_id=shot_id)
    return projection["segments"]
