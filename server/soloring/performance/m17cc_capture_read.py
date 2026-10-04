"""M17C-C slice 2+3: the performance-plane coherent READ and the
frozen-companion persistence/reuse projection.

Slice 2 (frozen R4 11.1): resolve the complete performance plane on the
pinned SQLite snapshot as one immutable-in-practice value — mappings,
PR closure fields, immutable revision vocal bindings, paired vocal
mappings, and the readiness projection fixed in memory before the
fenced persistence unit. The M17C-B session-based verifiers run through
an ``AsyncSession`` bound to the pinned connection in savepoint-join
mode, so their reads see exactly the pinned snapshot.

Slice 3 (frozen R4 10.4/10.5): persist and validate THE SAME
already-captured value — never resolve Performance again. The companion
parent's canonical bytes are the embedded ``performance`` value; the
children are a mechanical projection of the captured segments; reuse of
an existing ``(shot_id, snapshot_hash)`` winner validates the winner's
complete companion closure and never repairs it (a schema-8 winner
missing or contradicting its closure is durable-closure corruption, an
internal integrity failure — not another readiness decision).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.performance.m17c_models import (
    PerformanceRevisionVocalBinding,
)
from soloring.performance.models import ShotVocalSegmentMapping

# the frozen R4 11.2 embedded segment key set, EXTENDED by the
# RR-M17CC-03 correction (capture-grammar v2): the two captured
# mapping hashes AND their preimage are now part of the schema-8
# snapshot/segment identity, so the chain is
#   captured preimage -> recomputed mapping hash -> SNAPSHOT-ANCHORED
#       hash (segment_hash -> parent spec_hash -> snapshot identity)
# and a coherent child-side preimage+hash rewrite disagrees with the
# independent snapshot. Grammar v1 (0023-era, preimage companion-only)
# is REFUSED, never silently reinterpreted.
EMBEDDED_SEGMENT_KEYS = (
    "position", "subject_id", "performance_revision_id",
    "performance_payload_sha256", "performance_profile_id",
    "performance_kind", "performance_start_ms", "performance_end_ms",
    "shot_anchor_ms", "performance_mapping_hash",
    "vocal_mapping_hash", "vocal_mapping_position",
    "vocal_performance_origin_ms", "vocal",
)


# the frozen 11.2 five-key vocal grammar (the pack's vocal dict may
# additionally carry mapping-preimage projection keys)
_VOCAL_KEYS = (
    "vocal_performance_revision_id", "vocal_binding_hash",
    "source_start_sample", "source_end_sample_exclusive",
    "sample_rate_hz",
)


def _embedded_segment(seg: dict) -> dict:
    """The grammar-v2 projection of ONE captured pack segment: the
    fourteen frozen keys — including the two mapping hashes and their
    preimage (RR-M17CC-03: the mapping identity is snapshot-anchored).
    The vocal dict projects to its exact five keys (the pack may carry
    the origin preimage at the top level, which stays top-level)."""
    out = {}
    for k in EMBEDDED_SEGMENT_KEYS:
        if k == "vocal_performance_origin_ms" and k not in seg:
            # generic segments carry no origin (None); the pack may
            # place the preimage at top level or inside the vocal dict
            out[k] = vocal_origin_of(seg)
        else:
            out[k] = seg[k]
    vocal = out["vocal"]
    if vocal is not None:
        out["vocal"] = {k: vocal[k] for k in _VOCAL_KEYS}
    return out


def vocal_origin_of(seg: dict):
    origin = seg.get("vocal_performance_origin_ms")
    if isinstance(origin, dict):
        return origin
    vocal = seg.get("vocal")
    if isinstance(vocal, dict):
        origin = vocal.get("vocal_performance_origin_ms")
        if isinstance(origin, dict):
            return origin
    return None


def exact_projection_equal(relational_value, embedded_value) -> bool:
    """SR-M17CC-03: the captured companion graph is a MECHANICAL
    projection of the immutable canonical document — agreement must be
    exact in BOTH value and lawful type. Python's cross-type equality
    aliases (``False == 0``, ``True == 1``, ``1.0 == 1``) must not
    satisfy field identity: a JSON ``false``/``true``/float in the
    embedded document is never the integer (or string) the relational
    companion stores, even when every canonical hash was coherently
    recomputed over the forged document."""
    if type(relational_value) is not type(embedded_value):
        return False
    return relational_value == embedded_value


def is_actual_int_schema(value, frozen: int) -> bool:
    """RR12-M17CC-02: a captured grammar discriminator must be an
    ACTUAL non-bool Python integer exactly equal to the frozen
    version — ordinary numeric equality admits JSON floats
    (``2.0 == 2``) the canonical writer can never emit. The ONE
    shared discriminator law, consumed by BOTH the §12 grammar and
    the recovery capture-state grammar."""
    return (not isinstance(value, bool) and isinstance(value, int)
            and value == frozen)


def captured_vocal_preimage_error(row) -> str | None:
    """RR12-M17CC-01: the captured vocal preimage's persisted scalar
    law — certified BEFORE the preimage is hashed, anchored into
    snapshot identity, or used in any exact arithmetic. The §12/
    recovery projection equality proves same-type-and-value against
    the embedded JSON, NOT that the shared type is lawful authority:
    a coherent REAL coordinate (child float + embedded JSON float,
    every hash recomputed) would reach Fraction arithmetic and raise
    a raw TypeError. This ONE transport-neutral law (both sqlite3.Row
    and mapping rows subscript) requires actual non-bool persisted
    integers for the sample coordinates and rate with
    ``0 <= start < end`` and ``rate > 0``, an actual mapping-position-
    domain integer for ``vocal_mapping_position`` (the ONE shared
    position primitive), and an actual canonical-reduced integer
    rational for the captured origin (the ONE shared temporal
    primitive — positive denominator, canonical zero, signed-64-bit
    persistence range). Returns the precise violation, or ``None``
    for generic children. §12 maps failure to its internal-invariant
    contract; recovery to RECOVERY_CORRUPTION."""
    if row["vocal_performance_revision_id"] is None:
        return None
    for what, value in (
            ("source_start_sample", row["source_start_sample"]),
            ("source_end_sample_exclusive",
             row["source_end_sample_exclusive"]),
            ("sample_rate_hz", row["sample_rate_hz"]),
            ("vocal_mapping_position", row["vocal_mapping_position"]),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            return (f"{what} {value!r} is not a persisted integer "
                    "(non-integral SQLite storage class)")
    start = row["source_start_sample"]
    end = row["source_end_sample_exclusive"]
    rate = row["sample_rate_hz"]
    if not (0 <= start < end):
        return (f"captured sample interval [{start!r}, {end!r}) does "
                "not satisfy 0 <= start < end")
    if rate <= 0:
        return f"captured sample_rate_hz {rate!r} is not positive"
    from soloring.performance.temporal import (
        PositionError, RationalError, canonical_rational,
        validate_mapping_position,
    )
    try:
        validate_mapping_position(row["vocal_mapping_position"])
    except PositionError as exc:
        return (f"captured vocal_mapping_position "
                f"{row['vocal_mapping_position']!r} is outside the "
                f"persisted mapping-position domain: {exc}")
    num = row["vocal_performance_origin_num"]
    den = row["vocal_performance_origin_den"]
    if isinstance(num, bool) or not isinstance(num, int) \
            or isinstance(den, bool) or not isinstance(den, int):
        return (f"captured vocal_performance_origin {num!r}/{den!r} "
                "is not a persisted integer pair (non-integral SQLite "
                "storage class)")
    try:
        reduced = canonical_rational(num, den)
    except RationalError as exc:
        return (f"captured vocal_performance_origin {num!r}/{den!r} "
                f"fails the canonical rational law: {exc}")
    if reduced != (num, den):
        return (f"captured vocal_performance_origin {num}/{den} is "
                "not in canonical reduced form")
    return None


def embedded_rational_shape_error(seg: dict) -> str | None:
    """SR-M17CC-03 (residual): the nested rational objects of the
    frozen schema-8 segment grammar — ``performance_start_ms`` /
    ``performance_end_ms`` / ``shot_anchor_ms``, and a non-null
    ``vocal_performance_origin_ms`` — must each be an actual
    ``{num, den}`` object BEFORE any ``["num"]``/``["den"]`` access.
    Returns the precise violation, or ``None`` when the shapes are
    lawful. Malformed embedded JSON terminates through each
    consumer's typed contract (§12's internal invariant / recovery's
    RECOVERY_CORRUPTION), never a raw TypeError/KeyError."""
    for key in ("performance_start_ms", "performance_end_ms",
                "shot_anchor_ms"):
        value = seg.get(key)
        if not isinstance(value, dict) or set(value) != {"num", "den"}:
            return f"{key} {value!r} is not the frozen rational object"
    origin = seg.get("vocal_performance_origin_ms")
    if origin is not None and (not isinstance(origin, dict)
                               or set(origin) != {"num", "den"}):
        return (f"vocal_performance_origin_ms {origin!r} is not the "
                "frozen rational object")
    return None


def embedded_performance_value(performance_pack) -> dict:
    """The canonical embedded ``performance`` block: grammar v2 +
    the position-ordered projection of the frozen keys from each
    captured segment. This is THE value the snapshot carries and the
    companion parent's ``spec_json`` must serialize."""
    return {"schema_version": 2, "segments": [
        _embedded_segment(seg) for seg in performance_pack["segments"]]}


def performance_spec_bytes(performance_pack) -> tuple[str, str]:
    value = embedded_performance_value(performance_pack)
    return canonical_json_str(value), canonical_hash(value)


def _segment_bytes(seg) -> tuple[str, str]:
    value = _embedded_segment(seg)
    return canonical_json_str(value), canonical_hash(value)


async def resolve_performance_plane(conn, settings, shot_id: str):
    """Resolve the complete performance plane on the PINNED snapshot.

    Returns ``None`` when the Shot carries no working performance
    mappings (the capture emits the exact predecessor snapshot). When
    mappings exist, returns the complete capture value:

    ``{"ready": bool, "segments": [<captured segment dicts, position
    order — the frozen 11.2 keys PLUS the projection keys>],
    "segment_readiness": [<projection states/diagnostics>]}``

    Impossible persisted history fails closed exactly as every other
    M17C-B authority read (500 INTERNAL_INVARIANT_VIOLATION through
    the shared seam); non-READY working states do NOT raise here —
    readiness is data the CAPTURE path gates on (frozen 11.2/11.4).
    """
    n = (await conn.execute(text(
        "SELECT COUNT(*) FROM shot_performance_segment_mappings "
        "WHERE shot_id = :s"), {"s": shot_id})).scalar_one()
    if not n:
        return None

    from soloring.performance.m17c_shot_mapping import (
        project_shot_performance_readiness,
    )
    # the M17C-B verifiers are session-based; bind a short-lived
    # session to THIS pinned connection (savepoint join) so every read
    # sees the exact snapshot the outer BEGIN pinned — never a second
    # pooled connection
    async with AsyncSession(
            bind=conn, expire_on_commit=False,
            join_transaction_mode="create_savepoint") as pinned:
        projection = await project_shot_performance_readiness(
            pinned, settings, shot_id=shot_id)
        # RR-M17CC-02 (re-review): readiness CLASSIFICATION is separate
        # from capturable-closure EXTRACTION. A lawfully non-READY
        # working state (e.g. the supported DELETE of a paired vocal
        # mapping = BLOCKED_BINDING_INTEGRITY) is DATA — the capture
        # path issues its typed 409 from this projection, and
        # non-capture readers stay usable. No closure material is
        # extracted (and nothing is classified as corruption) unless
        # EVERY segment projects READY.
        ready = all(s["readiness"] == "READY"
                    for s in projection["segments"])
        if not ready:
            return {
                "ready": False,
                "segments": None,
                "segment_readiness": [
                    {"position": s["position"],
                     "readiness": s["readiness"],
                     "readiness_diagnostics":
                         s.get("readiness_diagnostics")}
                    for s in projection["segments"]],
            }
        segments = []
        for seg in projection["segments"]:
            pr_id = seg["performance_revision_id"]
            pr = await _pr_row(pinned, pr_id)
            vocal = None
            vocal_mapping_hash = None
            if seg["vocal_mapping_position"] is not None:
                binding = await pinned.get(
                    PerformanceRevisionVocalBinding, pr_id)
                if binding is None:
                    # under an all-READY projection the seam has
                    # verified classification/cardinality; a missing
                    # binding here is impossible persisted history
                    from soloring.performance.m17c_shot_mapping import (
                        _corrupt,
                    )
                    raise _corrupt(
                        f"dialogue-bound revision {pr_id!r} lost its "
                        "PF-03 binding inside the capture read")
                paired = await pinned.get(ShotVocalSegmentMapping,
                                          (shot_id,
                                           seg["vocal_mapping_position"]))
                if paired is None:
                    # under an all-READY projection the paired vocal
                    # mapping exists (its absence is the lawful
                    # BLOCKED_BINDING_INTEGRITY state returned above as
                    # data); losing it here mid-read never legitimately
                    # happens inside one pinned snapshot
                    from soloring.performance.m17c_shot_mapping import (
                        _corrupt,
                    )
                    raise _corrupt(
                        f"paired vocal mapping {shot_id!r}@"
                        f"{seg['vocal_mapping_position']} disappeared "
                        "inside the capture read")
                vocal = {
                    "vocal_performance_revision_id":
                        binding.vocal_performance_revision_id,
                    "vocal_binding_hash": binding.binding_hash,
                    "source_start_sample": paired.source_start_sample,
                    "source_end_sample_exclusive":
                        paired.source_end_sample_exclusive,
                    "sample_rate_hz": paired.sample_rate_hz,
                    # FPR-M17CC-04: the vocal mapping document's OWN
                    # origin preimage (caller-supplied at its PUT and
                    # pinned by no law to the binding's origin) — a
                    # projection key the companion consumes; the frozen
                    # 5-key embedded vocal grammar is untouched
                    "vocal_performance_origin_ms": {
                        "num": paired.performance_origin_num,
                        "den": paired.performance_origin_den},
                }
                vocal_mapping_hash = paired.mapping_hash
            segments.append({
                "position": seg["position"],
                "subject_id": pr["subject_id"],
                "performance_revision_id": pr_id,
                "performance_payload_sha256":
                    pr["canonical_channel_payload_sha256"],
                "performance_payload_blob_hash":
                    pr["canonical_channel_payload_blob_hash"],
                "performance_profile_id": pr["performance_profile_id"],
                "performance_kind": pr["performance_kind"],
                "performance_start_ms": seg["performance_start_ms"],
                "performance_end_ms": seg["performance_end_ms"],
                "shot_anchor_ms": seg["shot_anchor_ms"],
                "mapping_hash": seg["mapping_hash"],
                "performance_mapping_hash": seg["mapping_hash"],
                "vocal": vocal,
                "vocal_mapping_hash": vocal_mapping_hash,
                # FPR-M17CC-04: the performance mapping document's
                # paired-position preimage
                "vocal_mapping_position":
                    seg["vocal_mapping_position"],
            })
    return {
        "ready": True,
        "segments": segments,
        "segment_readiness": [
            {"position": s["position"], "readiness": s["readiness"],
             "readiness_diagnostics": s.get("readiness_diagnostics")}
            for s in projection["segments"]],
    }


async def _pr_row(pinned: AsyncSession, pr_id: str) -> dict:
    from soloring.performance.models import PerformanceRevision
    pr = await pinned.get(PerformanceRevision, pr_id)
    if pr is None:
        from soloring.performance.m17c_shot_mapping import _corrupt
        raise _corrupt(
            f"performance mapping references a missing "
            f"PerformanceRevision {pr_id!r} inside the capture read")
    return {
        "subject_id": pr.subject_id,
        "performance_kind": pr.performance_kind,
        "performance_profile_id": pr.performance_profile_id,
        "canonical_channel_payload_sha256":
            pr.canonical_channel_payload_sha256,
        "canonical_channel_payload_blob_hash":
            pr.canonical_channel_payload_blob_hash,
    }


# ---------------------------------------------------------------------------
# Slice 3: companion persistence + reuse validation (the SAME value)
# ---------------------------------------------------------------------------

_CHILD_COLUMNS = (
    "shot_revision_id, position, subject_id, performance_revision_id, "
    "performance_payload_blob_hash, performance_payload_sha256, "
    "performance_profile_id, performance_kind, "
    "performance_start_num, performance_start_den, "
    "performance_end_num, performance_end_den, "
    "shot_anchor_num, shot_anchor_den, performance_mapping_hash, "
    "vocal_performance_revision_id, vocal_binding_hash, "
    "vocal_mapping_hash, source_start_sample, "
    "source_end_sample_exclusive, sample_rate_hz, "
    "vocal_performance_origin_num, vocal_performance_origin_den, "
    "vocal_mapping_position, segment_json, segment_hash")


def _child_params(revision_id: str, seg: dict) -> dict:
    """The mechanical child projection of ONE captured segment — every
    column derives from the captured value; nothing is reread."""
    seg_json, seg_hash = _segment_bytes(seg)
    vocal = seg["vocal"]
    return {
        "rid": revision_id,
        "position": seg["position"],
        "subject_id": seg["subject_id"],
        "prid": seg["performance_revision_id"],
        "pbh": seg["performance_payload_blob_hash"],
        "psh": seg["performance_payload_sha256"],
        "profile": seg["performance_profile_id"],
        "kind": seg["performance_kind"],
        "sn": seg["performance_start_ms"]["num"],
        "sd": seg["performance_start_ms"]["den"],
        "en": seg["performance_end_ms"]["num"],
        "ed": seg["performance_end_ms"]["den"],
        "an": seg["shot_anchor_ms"]["num"],
        "ad": seg["shot_anchor_ms"]["den"],
        "pmh": seg["mapping_hash"],
        "vid": vocal["vocal_performance_revision_id"] if vocal else None,
        "vbh": vocal["vocal_binding_hash"] if vocal else None,
        "vmh": seg["vocal_mapping_hash"],
        "vss": vocal["source_start_sample"] if vocal else None,
        "vse": vocal["source_end_sample_exclusive"] if vocal else None,
        "vsr": vocal["sample_rate_hz"] if vocal else None,
        "von": vocal["vocal_performance_origin_ms"]["num"]
        if vocal else None,
        "vod": vocal["vocal_performance_origin_ms"]["den"]
        if vocal else None,
        "vmp": seg["vocal_mapping_position"],
        "sj": seg_json,
        "sh": seg_hash,
    }


async def persist_performance_companions(
        conn, revision_id: str, performance_pack) -> None:
    """Insert the companion PARENT first (immediate SQLite FKs), then
    exactly ``len(performance_pack['segments'])`` children — all from
    the SAME captured value, inside the caller's BEGIN IMMEDIATE unit.
    The parent's ``spec_json``/``spec_hash`` are the canonical embedded
    performance value (never an independent reconstruction)."""
    spec_json, spec_hash = performance_spec_bytes(performance_pack)
    await conn.execute(text(
        "INSERT INTO shot_revision_performance_specs "
        "(shot_revision_id, schema_version, spec_json, spec_hash) "
        "VALUES (:rid, 1, :sj, :sh)"),
        {"rid": revision_id, "sj": spec_json, "sh": spec_hash})
    await conn.execute(text(
        "INSERT INTO shot_revision_performance_segments ("
        + _CHILD_COLUMNS + ") VALUES ("
        ":rid, :position, :subject_id, :prid, :pbh, :psh, :profile, "
        ":kind, :sn, :sd, :en, :ed, :an, :ad, :pmh, :vid, :vbh, :vmh, "
        ":vss, :vse, :vsr, :von, :vod, :vmp, :sj, :sh)"),
        [_child_params(revision_id, seg)
         for seg in performance_pack["segments"]])


async def _performance_parent_exists(conn, revision_id: str) -> bool:
    return (await conn.execute(text(
        "SELECT 1 FROM shot_revision_performance_specs "
        "WHERE shot_revision_id = :r"), {"r": revision_id})).first() \
        is not None


async def verify_performance_companions(
        conn, revision_id: str, performance_pack) -> None:
    """Reuse-winner validation (frozen 10.4/10.5 closure): the stored
    parent must be exactly one with the canonical embedded bytes/hash,
    and the stored children must be the EXACT projection of the
    captured segments — same count, same positions in order, every
    field equal. Missing parent, missing/extra/reordered children,
    altered fields, altered spec bytes or hash are durable-closure
    corruption: internal-invariant failure. NEVER repaired, and the
    current database is never consulted to fill a gap."""
    from soloring.errors import internal_invariant

    stored_parent = (await conn.execute(text(
        "SELECT schema_version, spec_json, spec_hash FROM "
        "shot_revision_performance_specs WHERE shot_revision_id = :r"),
        {"r": revision_id})).mappings().fetchall()
    if len(stored_parent) != 1:
        raise internal_invariant(
            f"ShotRevision {revision_id} convergence requires exactly "
            "one performance companion parent")
    spec_json, spec_hash = performance_spec_bytes(performance_pack)
    sp = stored_parent[0]
    if sp.schema_version != 1 or sp.spec_json != spec_json \
            or sp.spec_hash != spec_hash:
        raise internal_invariant(
            f"ShotRevision {revision_id} performance companion parent "
            "disagrees with the converged capture")

    stored = (await conn.execute(text(
        "SELECT " + _CHILD_COLUMNS +
        " FROM shot_revision_performance_segments "
        "WHERE shot_revision_id = :r ORDER BY position"),
        {"r": revision_id})).mappings().fetchall()
    expected = sorted(performance_pack["segments"],
                      key=lambda s: s["position"])
    if len(stored) != len(expected):
        raise internal_invariant(
            f"ShotRevision {revision_id} performance companion row "
            f"count disagrees: stored {len(stored)}, expected "
            f"{len(expected)}")
    for row, seg in zip(stored, expected):
        want = _child_params(revision_id, seg)
        for col in _CHILD_COLUMNS.split(", "):
            if col == "shot_revision_id":
                continue
            if row[col] != want[_bind_for(col)]:
                raise internal_invariant(
                    f"ShotRevision {revision_id} performance companion "
                    f"child at position {row['position']} disagrees "
                    "with the converged capture")


def _bind_for(col: str) -> str:
    return {
        "position": "position", "subject_id": "subject_id",
        "performance_revision_id": "prid",
        "performance_payload_blob_hash": "pbh",
        "performance_payload_sha256": "psh",
        "performance_profile_id": "profile",
        "performance_kind": "kind",
        "performance_start_num": "sn", "performance_start_den": "sd",
        "performance_end_num": "en", "performance_end_den": "ed",
        "shot_anchor_num": "an", "shot_anchor_den": "ad",
        "performance_mapping_hash": "pmh",
        "vocal_performance_revision_id": "vid",
        "vocal_binding_hash": "vbh", "vocal_mapping_hash": "vmh",
        "source_start_sample": "vss",
        "source_end_sample_exclusive": "vse",
        "sample_rate_hz": "vsr",
        "vocal_performance_origin_num": "von",
        "vocal_performance_origin_den": "vod",
        "vocal_mapping_position": "vmp",
        "segment_json": "sj", "segment_hash": "sh",
    }[col]


# ---------------------------------------------------------------------------
# FPR-M17CC-04: the mapping-document preimage recompute — the ONE pure
# law shared by §12 reconstruction, §13.4 recovery, and reuse
# validation. Both captured mapping hashes are PURE functions of the
# stored child row (plus nothing else — never a current working
# mapping read, which §12 forbids).
# ---------------------------------------------------------------------------

def expected_mapping_hashes(
        performance_revision_id: str,
        performance_start_ms: dict, performance_end_ms: dict,
        shot_anchor_ms: dict, vocal_mapping_position,
        vocal: dict | None) -> tuple[str, str | None]:
    """Recompute (performance_mapping_hash, vocal_mapping_hash) from
    the captured child's own fields, using the exact frozen working-
    mapping document grammars (mapping.py / m17c_shot_mapping.py)."""
    performance_doc = {
        "mapping_schema_version": 1,
        "performance_revision_id": performance_revision_id,
        "performance_start_ms": performance_start_ms,
        "performance_end_ms": performance_end_ms,
        "shot_anchor_ms": shot_anchor_ms,
        "vocal_mapping_position": vocal_mapping_position,
    }
    vocal_hash = None
    if vocal is not None:
        vocal_doc = {
            "mapping_schema_version": 1,
            "vocal_performance_revision_id":
                vocal["vocal_performance_revision_id"],
            "source_start_sample": vocal["source_start_sample"],
            "source_end_sample_exclusive":
                vocal["source_end_sample_exclusive"],
            "sample_rate_hz": vocal["sample_rate_hz"],
            "performance_origin_ms":
                vocal["vocal_performance_origin_ms"],
            "shot_anchor_ms": shot_anchor_ms,
        }
        vocal_hash = canonical_hash(vocal_doc)
    return canonical_hash(performance_doc), vocal_hash


def _child_preimage_vocal(row) -> dict | None:
    """The vocal preimage dict from a stored child row (sqlite3.Row or
    mapping): None for generic children."""
    if row["vocal_performance_revision_id"] is None:
        if (row["vocal_binding_hash"] is not None
                or row["vocal_mapping_hash"] is not None
                or row["source_start_sample"] is not None
                or row["vocal_performance_origin_num"] is not None
                or row["vocal_performance_origin_den"] is not None
                or row["vocal_mapping_position"] is not None):
            raise ValueError("partial vocal group on the child row")
        return None
    return {
        "vocal_performance_revision_id":
            row["vocal_performance_revision_id"],
        "source_start_sample": row["source_start_sample"],
        "source_end_sample_exclusive":
            row["source_end_sample_exclusive"],
        "sample_rate_hz": row["sample_rate_hz"],
        "vocal_performance_origin_ms": {
            "num": row["vocal_performance_origin_num"],
            "den": row["vocal_performance_origin_den"]},
    }


def verify_mapping_hash_closure(row, where: str, seg=None) -> None:
    """Fail closed (typed internal invariant) when a stored child's
    captured mapping-hash columns disagree with the preimage the row
    itself carries (FPR-M17CC-04), AND — RR-M17CC-03 — when either the
    preimage or the hashes disagree with the SNAPSHOT-ANCHORED
    embedded segment (segment_hash -> parent spec_hash -> snapshot
    identity): a coherent child-side preimage+hash rewrite is refused
    by the independent snapshot, not merely by row-local recomputation."""
    from soloring.errors import internal_invariant

    # RR12-M17CC-01: the persisted scalar law of the captured vocal
    # preimage — certified BEFORE the preimage is hashed (below) or
    # used in any exact arithmetic downstream
    preimage_error = captured_vocal_preimage_error(row)
    if preimage_error is not None:
        raise internal_invariant(
            f"{where} captured vocal preimage violates its persisted "
            f"scalar law: {preimage_error}")

    try:
        vocal = _child_preimage_vocal(row)
        perf_hash, vocal_hash = expected_mapping_hashes(
            row["performance_revision_id"],
            {"num": row["performance_start_num"],
             "den": row["performance_start_den"]},
            {"num": row["performance_end_num"],
             "den": row["performance_end_den"]},
            {"num": row["shot_anchor_num"],
             "den": row["shot_anchor_den"]},
            row["vocal_mapping_position"], vocal)
    except ValueError as exc:
        raise internal_invariant(
            f"{where} carries an incoherent vocal-group preimage: "
            f"{exc}") from exc
    if row["performance_mapping_hash"] != perf_hash:
        raise internal_invariant(
            f"{where} performance_mapping_hash disagrees with its "
            "captured mapping-document preimage")
    if row["vocal_mapping_hash"] != vocal_hash:
        raise internal_invariant(
            f"{where} vocal_mapping_hash disagrees with its captured "
            "mapping-document preimage")
    if seg is not None:
        if (row["performance_mapping_hash"]
                != seg["performance_mapping_hash"]):
            raise internal_invariant(
                f"{where} performance_mapping_hash disagrees with the "
                "snapshot-anchored embedded segment")
        if (row["vocal_mapping_hash"]
                != seg["vocal_mapping_hash"]):
            raise internal_invariant(
                f"{where} vocal_mapping_hash disagrees with the "
                "snapshot-anchored embedded segment")
        if (row["vocal_mapping_position"]
                != seg["vocal_mapping_position"]):
            raise internal_invariant(
                f"{where} vocal_mapping_position preimage disagrees "
                "with the snapshot-anchored embedded segment")
        embedded_origin = seg["vocal_performance_origin_ms"]
        if embedded_origin is None:
            if (row["vocal_performance_origin_num"] is not None
                    or row["vocal_performance_origin_den"] is not None):
                raise internal_invariant(
                    f"{where} vocal performance-origin preimage "
                    "disagrees with the snapshot-anchored embedded "
                    "segment")
        # SR-M17CC-03 (residual): TYPE-EXACT origin projection — an
        # embedded JSON false/float that Python-compares equal to the
        # relational integer (0 == False, 1 == 1.0) is not the
        # mechanical projection the captured identity requires
        elif (not exact_projection_equal(
                    row["vocal_performance_origin_num"],
                    embedded_origin["num"])
                or not exact_projection_equal(
                    row["vocal_performance_origin_den"],
                    embedded_origin["den"])):
            raise internal_invariant(
                f"{where} vocal performance-origin preimage disagrees "
                "with the snapshot-anchored embedded segment")
