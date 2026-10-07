"""M17C-D W2 — the create-path performance translation (frozen
plan R2-FINAL §2.2–§2.4).

Captured-history-only input: the translation consumes the schema-8
ShotRevision's immutable companion children, the immutable PR
payload bytes, and the immutable VP retained audio bytes — never
current VP selection, current working mappings, or latest authority
(the §12-proven read pattern).

ALL-OR-NOTHING (§2.2): every captured segment is validated and
derived IN MEMORY first — kind/body-lane gates, anchor
representability, channel readiness, schedule rasterization, audio
materialization — and ONLY after the complete set passes may any
controls/audio blob be placed. A later-segment refusal leaves zero
released derived blobs.

The derived bytes are placed content-addressed in ONE fenced
BEGIN IMMEDIATE unit (the §12.3 spatial-publication precedent:
the service session stays read-only until the final Generation
write), and the returned rows follow the D-frozen grouped-key
convention (``expected_gpi_rows``) with the frozen v1
``derived_input_hash`` record (parent/lifecycle coordinates
excluded — duplicate Generations over identical captured inputs
keep identical derived identities).
"""

from __future__ import annotations

import hashlib
import json
from fractions import Fraction

from soloring.domain.canonical import canonical_json_str
from soloring.errors import ErrorCode, SoloRingError
from soloring.performance import execution_sampler as es


class PerformanceTranslation:
    """The complete in-memory result of a lawful translation."""

    def __init__(self, *, gpi_rows: list, performance_execution: dict,
                 placed_bytes: list | None = None):
        self.gpi_rows = gpi_rows
        self.performance_execution = performance_execution
        # the exact placed derived bytes (digest, data) — available
        # to staging/verification consumers without re-derivation
        self.placed_bytes = placed_bytes or []


def _execution_refusal(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
                         message, status_code=422)


def _internal(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                         message, status_code=500)


def rasterization_facts(parameters: dict) -> tuple[Fraction, int]:
    """The D-frozen rasterization-facts source: the pinned workflow
    package's manifest declares ``fps_num`` / ``fps_den`` /
    ``frame_count`` as exact integer parameters (resolved through
    the ordinary strict parameter machinery and captured into the
    spec), so a package change can never silently reinterpret a
    queued Generation's picture grid."""
    missing = [name for name in
               ("fps_num", "fps_den", "frame_count")
               if name not in parameters]
    if missing:
        raise _execution_refusal(
            "the performance execution package must declare the "
            f"rasterization parameters {missing} — execution refuses "
            "rather than guessing the picture grid")
    values = {}
    for name in ("fps_num", "fps_den", "frame_count"):
        value = parameters[name]
        if type(value) is not int or value < 1:
            raise _execution_refusal(
                f"rasterization parameter {name!r} must be a positive "
                "exact integer")
        values[name] = value
    fps = Fraction(values["fps_num"], values["fps_den"])
    if fps <= 0:
        raise _execution_refusal("fps must be positive")
    return fps, values["frame_count"]


async def _verified_bytes(settings, blob_hash: str, what: str) -> bytes:
    from soloring.assets.blob_store import BlobStore

    path = BlobStore(settings).path_for_hash(blob_hash)
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise _internal(
            f"{what} blob {blob_hash} is physically missing from "
            "storage") from exc
    except OSError as exc:
        raise _internal(
            f"{what} blob {blob_hash} is unreadable: {exc}") from exc
    if hashlib.sha256(data).hexdigest() != blob_hash:
        raise _internal(
            f"{what} blob {blob_hash} does not rehash to its content "
            "address")
    return data


async def derive_all(session, settings, *, revision_id: str,
                     fps: Fraction, frame_count: int) -> list:
    """The PURE derivation phase (§2.2 all-or-nothing): every
    captured segment validated and derived IN MEMORY — no blob
    placement. Exactly the phase the worker's pre-submit proof
    re-runs against the retained bytes."""
    from sqlalchemy import text as _text

    children = (await session.execute(_text(
        "SELECT * FROM shot_revision_performance_segments "
        "WHERE shot_revision_id = :r ORDER BY position"),
        {"r": revision_id})).mappings().all()
    if not children:
        raise _internal(
            f"schema-8 revision {revision_id} has no captured "
            "performance companion children")

    payload_cache: dict[str, dict] = {}
    audio_cache: dict[str, bytes] = {}
    derived: list[dict] = []
    for child in children:
        es.assert_supported_kind(child["performance_kind"])
        pr_id = child["performance_revision_id"]
        if pr_id not in payload_cache:
            payload_bytes = await _verified_bytes(
                settings, child["performance_payload_blob_hash"],
                "performance payload")
            payload_cache[pr_id] = json.loads(
                payload_bytes.decode("utf-8"))
        payload = payload_cache[pr_id]
        es.assert_facial_lane(payload)

        performance_start = Fraction(
            child["performance_start_num"],
            child["performance_start_den"])
        performance_end = Fraction(
            child["performance_end_num"],
            child["performance_end_den"])
        shot_anchor = Fraction(
            child["shot_anchor_num"], child["shot_anchor_den"])

        schedule = es.control_schedule_document(
            segment={
                "shot_revision_segment_position": child["position"],
                "segment_hash": child["segment_hash"],
                "performance_revision_id": pr_id,
            },
            channels=payload["channels"],
            performance_start=performance_start,
            performance_end=performance_end,
            shot_anchor=shot_anchor,
            fps=fps,
            frame_count=frame_count,
        )
        schedule_bytes = canonical_json_str(schedule).encode("utf-8")

        vocal: dict | None = None
        audio_bytes: bytes | None = None
        if child["vocal_performance_revision_id"] is not None:
            vp_id = child["vocal_performance_revision_id"]
            if vp_id not in audio_cache:
                row = (await session.execute(_text(
                    "SELECT retained_audio_blob_hash FROM "
                    "vocal_performance_revisions WHERE id = :v"),
                    {"v": vp_id})).mappings().one_or_none()
                if row is None:
                    raise _internal(
                        f"captured vocal performance {vp_id} is "
                        "missing from immutable authority")
                audio_cache[vp_id] = await _verified_bytes(
                    settings, row["retained_audio_blob_hash"],
                    "retained vocal audio")
            audio_bytes = es.materialize_audio_track(
                wav_bytes=audio_cache[vp_id],
                source_start=child["source_start_sample"],
                source_end_exclusive=(
                    child["source_end_sample_exclusive"]),
                sample_rate_hz=child["sample_rate_hz"],
                anchor=shot_anchor,
                fps=fps,
                frame_count=frame_count,
            )
            vocal = {
                "vocal_performance_revision_id": vp_id,
                "vocal_audio_blob_hash":
                    hashlib.sha256(audio_cache[vp_id]).hexdigest(),
                "source_start_sample": child["source_start_sample"],
                "source_end_sample_exclusive":
                    child["source_end_sample_exclusive"],
                "sample_rate_hz": child["sample_rate_hz"],
                "vocal_binding_hash": child["vocal_binding_hash"],
                "synchronization_basis_version": 1,
                "materialized_audio_track_blob_hash":
                    hashlib.sha256(audio_bytes).hexdigest(),
            }
        derived.append({
            "child": child,
            "schedule": schedule,
            "schedule_bytes": schedule_bytes,
            "vocal": vocal,
            "audio_bytes": audio_bytes,
        })
    return derived


async def translate_captured_performance(
    session, settings, *, revision_id: str, parameters: dict,
) -> PerformanceTranslation:
    """§2.2–§2.4: the all-or-nothing translation + blob placement +
    GPI row construction for one captured schema-8 revision."""
    fps, frame_count = rasterization_facts(parameters)
    derived = await derive_all(
        session, settings, revision_id=revision_id,
        fps=fps, frame_count=frame_count)

    # ---- the complete set passed: place the derived blobs ----
    placements: list[tuple[str, bytes]] = []
    seen_hashes: set[str] = set()
    for item in derived:
        for blob in (
            (item["schedule_bytes"],),
            (item["audio_bytes"],) if item["audio_bytes"] else (),
        ):
            for data in blob:
                digest = hashlib.sha256(data).hexdigest()
                if digest not in seen_hashes:
                    seen_hashes.add(digest)
                    placements.append((digest, data))

    if placements:
        import contextlib as _cl

        from sqlalchemy import text as _text

        from soloring.assets.blob_store import BlobStore
        from soloring.db.timeutil import DB_NOW_SQL

        store = BlobStore(settings)
        async with session.bind.connect() as conn:
            try:
                await conn.exec_driver_sql("BEGIN IMMEDIATE")
                for digest, data in placements:
                    tmp = store.tmp_path()
                    tmp.write_bytes(data)
                    await store.place(digest, tmp)
                    await conn.execute(_text(
                        "INSERT OR IGNORE INTO blobs (hash, path, "
                        "size_bytes, created_at) VALUES (:h, :p, :s, "
                        f"{DB_NOW_SQL})"),
                        {"h": digest,
                         "p": store.relative_path_for_hash(digest),
                         "s": len(data)})
                await conn.exec_driver_sql("COMMIT")
            except Exception:
                with _cl.suppress(Exception):
                    await conn.exec_driver_sql("ROLLBACK")
                raise

    # ---- the performance_execution container + the GPI rows ----
    entries = []
    for item in derived:
        child = item["child"]
        entry = {
            "shot_revision_segment_position": child["position"],
            "segment_hash": child["segment_hash"],
            "subject_id": child["subject_id"],
            "performance_revision_id":
                child["performance_revision_id"],
            "payload_blob_hash":
                child["performance_payload_blob_hash"],
            "payload_sha256": child["performance_payload_sha256"],
            "performance_profile_id":
                child["performance_profile_id"],
            "performance_kind": child["performance_kind"],
            "performance_start": {"num": child["performance_start_num"],
                                  "den": child["performance_start_den"]},
            "performance_end": {"num": child["performance_end_num"],
                                "den": child["performance_end_den"]},
            "shot_anchor": {"num": child["shot_anchor_num"],
                            "den": child["shot_anchor_den"]},
            "control_schedule_blob_hash": hashlib.sha256(
                item["schedule_bytes"]).hexdigest(),
            "vocal": item["vocal"],
        }
        entries.append(entry)
    performance_execution = {
        "rasterization": {
            "fps": {"num": fps.numerator, "den": fps.denominator},
            "frame_count": frame_count,
        },
        "segments": entries,
    }

    child_dicts = [{
        "shot_revision_segment_position": item["child"]["position"],
        "performance_revision_id":
            item["child"]["performance_revision_id"],
        "segment_hash": item["child"]["segment_hash"],
        "vocal_performance_revision_id":
            item["child"]["vocal_performance_revision_id"],
        "vocal_binding_hash": item["child"]["vocal_binding_hash"],
    } for item in derived]
    gpi_rows = []
    by_role: dict[tuple[str, int], dict] = {}
    for item in derived:
        schedule_hash = hashlib.sha256(
            item["schedule_bytes"]).hexdigest()
        by_role[("performance.controls", item["child"]["position"])] = \
            {"blob_hash": schedule_hash}
        if item["audio_bytes"] is not None:
            by_role[
                ("performance.vocal_audio", item["child"]["position"])] \
                = {"blob_hash": hashlib.sha256(
                    item["audio_bytes"]).hexdigest()}
    for expected in es.expected_gpi_rows(
            child_dicts, es.TRANSLATION_IDENTITY):
        blob_hash = by_role[(
            expected["artifact_role"],
            expected["shot_revision_segment_position"])]["blob_hash"]
        record = es.derived_input_record(
            input_key=expected["input_key"],
            position=expected["position"],
            artifact_role=expected["artifact_role"],
            shot_revision_segment_position=(
                expected["shot_revision_segment_position"]),
            performance_revision_id=expected["performance_revision_id"],
            vocal_performance_revision_id=(
                expected["vocal_performance_revision_id"]),
            binding_hash=expected["binding_hash"],
            segment_hash=expected["segment_hash"],
            translation_identity=expected["translation_identity"],
            blob_hash=blob_hash,
        )
        gpi_rows.append({**expected, "blob_hash": blob_hash,
                         "derived_input_hash":
                             es.derived_input_hash(record)})
    return PerformanceTranslation(
        gpi_rows=gpi_rows,
        performance_execution=performance_execution,
        placed_bytes=placements)
