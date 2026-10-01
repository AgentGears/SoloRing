"""M17C-C §12: historical performance reconstruction (frozen R4 §12).

Historical inspection reconstructs WHAT WAS CAPTURED, never what is
true now. The one entry — ``verify_performance_history`` — is consumed
by the ShotRevision historical inspector and rebuilds the complete
performance plane from:

  the ShotRevision snapshot bytes
+ the M17C companion parent/children rows
+ immutable referenced Performance/Vocal authority rows
+ the retained Blob closure

It NEVER reads current VocalPerformanceSelection, current
ShotVocalSegmentMapping, current ShotPerformanceSegmentMapping,
current candidate rows, or current Shot dependency selection — and it
never falls back to present-day state: every disagreement between the
captured graph and the immutable closure it names is typed internal
corruption. Segment order is the CAPTURED position order, never a
temporal or identity sort. The exhaustive repository-wide §13.4 sweep
is a later slice; the laws here are only the local defensive
validation a trustworthy historical answer needs (frozen R4 §12 +
scope R0 1.5).
"""

from __future__ import annotations

import base64
import hashlib
import json

from sqlalchemy import text

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import internal_invariant
from soloring.performance.m17cc_capture_read import EMBEDDED_SEGMENT_KEYS

# the slice-3 §10.5 column order (identity column first); history
# compares every column against the EMBEDDED segment projection and
# the immutable referenced rows. FPR-M17CC-04: the captured mapping-
# document preimage columns are included.
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

_VOCAL_KEYS = (
    "vocal_performance_revision_id", "vocal_binding_hash",
    "source_start_sample", "source_end_sample_exclusive",
    "sample_rate_hz",
)


def _rat(num, den, what: str, revision_id: str) -> dict:
    """A persisted rational pair answers as its canonical {num, den}."""
    if not isinstance(num, int) or not isinstance(den, int) or den <= 0:
        raise internal_invariant(
            f"ShotRevision {revision_id} performance companion "
            f"{what} is not a canonical rational pair "
            f"({num!r}, {den!r}).")
    return {"num": num, "den": den}


def _verify_embedded_grammar(perf: dict, revision_id: str) -> list[dict]:
    """The frozen §11.2 grammar of the embedded/snapshot block: schema
    1, a NON-EMPTY position-ordered segment list, the exact frozen key
    set per segment, and the uniform vocal grammar (the complete
    5-key object or explicit null — never omission, never partial)."""
    if perf.get("schema_version") != 1:
        raise internal_invariant(
            f"ShotRevision {revision_id} performance history declares "
            f"unknown schema {perf.get('schema_version')!r}.")
    segments = perf.get("segments")
    if not isinstance(segments, list) or not segments:
        raise internal_invariant(
            f"ShotRevision {revision_id} performance history carries "
            "an empty segment list — no empty schema 8 exists.")
    for index, seg in enumerate(segments):
        if not isinstance(seg, dict) or set(seg) != set(EMBEDDED_SEGMENT_KEYS):
            raise internal_invariant(
                f"ShotRevision {revision_id} performance history "
                f"segment {index} is not the exact frozen key "
                "projection.")
        if seg["position"] != index:
            raise internal_invariant(
                f"ShotRevision {revision_id} performance history "
                f"segment {index} declares position "
                f"{seg['position']!r} — captured order is canonical.")
        vocal = seg["vocal"]
        if vocal is not None and (not isinstance(vocal, dict)
                                  or set(vocal) != set(_VOCAL_KEYS)):
            raise internal_invariant(
                f"ShotRevision {revision_id} performance history "
                f"segment {index} carries a vocal object outside the "
                "closed 5-key grammar.")
    return segments


async def verify_performance_history(session, revision_id: str,
                                      snapshot: dict,
                                      settings=None) -> dict:
    """Reconstruct + verify the schema-8 performance history. Pure
    read of the captured graph; raises the typed internal invariant on
    ANY disagreement — never repairs, never substitutes current state.
    Returns the §12 per-segment historical answer in captured order."""
    parent = (await session.execute(text(
        "SELECT schema_version, spec_json, spec_hash FROM "
        "shot_revision_performance_specs WHERE shot_revision_id = :r"),
        {"r": revision_id})).mappings().all()
    if len(parent) != 1:
        raise internal_invariant(
            f"ShotRevision {revision_id} schema-8 history requires "
            "exactly one performance companion parent")
    parent = parent[0]
    if parent.schema_version != 1:
        raise internal_invariant(
            f"ShotRevision {revision_id} performance companion parent "
            f"carries unknown schema {parent.schema_version!r}.")
    try:
        spec = json.loads(parent.spec_json)
    except (ValueError, TypeError) as exc:
        raise internal_invariant(
            f"ShotRevision {revision_id} performance companion "
            f"spec_json is malformed JSON: {exc}") from exc
    if not isinstance(spec, dict):
        raise internal_invariant(
            f"ShotRevision {revision_id} performance companion "
            "spec_json is not a JSON object.")
    if canonical_json_str(spec) != parent.spec_json \
            or canonical_hash(spec) != parent.spec_hash:
        raise internal_invariant(
            f"ShotRevision {revision_id} performance companion "
            "spec_json/spec_hash disagree with canonical bytes.")
    embedded = snapshot.get("performance")
    if not isinstance(embedded, dict):
        raise internal_invariant(
            f"ShotRevision {revision_id} schema-8 snapshot carries no "
            "performance block — corrupted history.")
    if canonical_json_str(embedded) != parent.spec_json:
        raise internal_invariant(
            f"ShotRevision {revision_id} snapshot performance block "
            "bytes disagree with its companion parent spec bytes.")
    segments = _verify_embedded_grammar(spec, revision_id)

    children = (await session.execute(text(
        "SELECT " + _CHILD_COLUMNS +
        " FROM shot_revision_performance_segments "
        "WHERE shot_revision_id = :r ORDER BY position"),
        {"r": revision_id})).mappings().all()
    if len(children) != len(segments):
        raise internal_invariant(
            f"ShotRevision {revision_id} performance companion row "
            f"count disagrees with its captured segment list: stored "
            f"{len(children)}, captured {len(segments)}")

    answer_segments = []
    for row, seg in zip(children, segments):
        answer_segments.append(await _verify_one_child(
            session, settings, revision_id, row, seg))
    return {
        "schema_version": 1,
        "spec_hash": parent.spec_hash,
        "segments": answer_segments,
    }


async def _verify_one_child(session, settings, revision_id: str,
                            row, seg: dict) -> dict:
    """Verify ONE captured child against its embedded segment and the
    immutable closure it names, then answer the §12 questions for it."""
    position = row["position"]
    where = (f"ShotRevision {revision_id} performance companion child "
             f"at position {position}")

    seg_json, seg_hash = canonical_json_str(seg), canonical_hash(seg)
    if row.segment_json != seg_json or row.segment_hash != seg_hash:
        raise internal_invariant(
            f"{where} segment_json/segment_hash disagree with the "
            "canonical embedded segment.")

    vocal = seg["vocal"]
    for column, embedded_value in (
        ("subject_id", seg["subject_id"]),
        ("performance_revision_id", seg["performance_revision_id"]),
        ("performance_payload_sha256",
         seg["performance_payload_sha256"]),
        ("performance_profile_id", seg["performance_profile_id"]),
        ("performance_kind", seg["performance_kind"]),
        ("performance_start_num",
         seg["performance_start_ms"]["num"]),
        ("performance_start_den",
         seg["performance_start_ms"]["den"]),
        ("performance_end_num", seg["performance_end_ms"]["num"]),
        ("performance_end_den", seg["performance_end_ms"]["den"]),
        ("shot_anchor_num", seg["shot_anchor_ms"]["num"]),
        ("shot_anchor_den", seg["shot_anchor_ms"]["den"]),
    ):
        if row[column] != embedded_value:
            raise internal_invariant(
                f"{where} column {column} disagrees with the embedded "
                "captured segment.")
    for column, embedded_key in (
        ("vocal_performance_revision_id",
         "vocal_performance_revision_id"),
        ("vocal_binding_hash", "vocal_binding_hash"),
        ("source_start_sample", "source_start_sample"),
        ("source_end_sample_exclusive",
         "source_end_sample_exclusive"),
        ("sample_rate_hz", "sample_rate_hz"),
    ):
        captured = vocal[embedded_key] if vocal is not None else None
        if row[column] != captured:
            raise internal_invariant(
                f"{where} vocal-group column {column} disagrees with "
                "the embedded captured vocal grammar (all-or-none).")

    # FPR-M17CC-04: the captured mapping-document preimage columns —
    # all-or-none with the vocal group (the origin pair and position
    # live ONLY on the child row; the frozen embedded vocal grammar
    # excludes them by design) — and ANCHORING both stored mapping
    # hashes (they must recompute exactly from the child's own
    # preimage, never a current read)
    if vocal is None:
        for column in ("vocal_performance_origin_num",
                       "vocal_performance_origin_den",
                       "vocal_mapping_position"):
            if row[column] is not None:
                raise internal_invariant(
                    f"{where} preimage column {column} is set on a "
                    "generic child (all-or-none)")
    else:
        for column in ("vocal_performance_origin_num",
                       "vocal_performance_origin_den",
                       "vocal_mapping_position"):
            if row[column] is None:
                raise internal_invariant(
                    f"{where} dialogue-bound child lacks its "
                    f"{column} preimage (all-or-none)")
    from soloring.performance.m17cc_capture_read import (
        verify_mapping_hash_closure,
    )
    verify_mapping_hash_closure(row, where)

    pr = (await session.execute(text(
        "SELECT subject_id, performance_kind, performance_profile_id, "
        "payload_schema_version, source_kind, temporal_start_num, "
        "temporal_start_den, temporal_end_num, temporal_end_den, "
        "canonical_channel_payload_sha256, "
        "canonical_channel_payload_blob_hash, adopted_at "
        "FROM performance_revisions WHERE id = :pr"),
        {"pr": row["performance_revision_id"]})).mappings().one_or_none()
    if pr is None:
        raise internal_invariant(
            f"{where} references a missing immutable "
            f"PerformanceRevision {row['performance_revision_id']!r}.")
    if (pr.subject_id != row.subject_id
            or pr.performance_kind != row.performance_kind
            or pr.performance_profile_id != row.performance_profile_id
            or pr.canonical_channel_payload_sha256
            != row.performance_payload_sha256
            or pr.canonical_channel_payload_blob_hash
            != row.performance_payload_blob_hash):
        raise internal_invariant(
            f"{where} disagrees with the immutable PerformanceRevision "
            f"{row['performance_revision_id']!r} it names.")

    blob = (await session.execute(text(
        "SELECT size_bytes FROM blobs WHERE hash = :h"),
        {"h": row.performance_payload_blob_hash})).mappings().one_or_none()
    if blob is None:
        raise internal_invariant(
            f"{where} names a payload blob absent from the retained "
            "Blob closure.")
    # FPR-M17CC-05: the EXACT retained bytes are physically read,
    # rehash-verified, and carried in the frozen answer — a missing or
    # corrupt physical file (DB row intact) fails closed; size
    # metadata may never substitute for the bytes
    payload_bytes = _verified_payload_bytes(
        settings, where, row.performance_payload_blob_hash)

    answer = {
        "position": position,
        "subject_id": row.subject_id,
        "performance_revision_id": row.performance_revision_id,
        "performance_revision": {
            "subject_id": pr.subject_id,
            "performance_kind": pr.performance_kind,
            "performance_profile_id": pr.performance_profile_id,
            "payload_schema_version": pr.payload_schema_version,
            "source_kind": pr.source_kind,
            "temporal_start_ms": _rat(
                pr.temporal_start_num, pr.temporal_start_den,
                "performance_start", revision_id),
            "temporal_end_ms": _rat(
                pr.temporal_end_num, pr.temporal_end_den,
                "performance_end", revision_id),
            "adopted_at": pr.adopted_at,
        },
        "performance_payload": {
            "blob_hash": row.performance_payload_blob_hash,
            "sha256": row.performance_payload_sha256,
            "size_bytes": blob.size_bytes,
            "payload_bytes_base64": base64.b64encode(
                payload_bytes).decode("ascii"),
        },
        "performance_start_ms": _rat(
            row.performance_start_num, row.performance_start_den,
            "performance_start", revision_id),
        "performance_end_ms": _rat(
            row.performance_end_num, row.performance_end_den,
            "performance_end", revision_id),
        "shot_anchor_ms": _rat(
            row.shot_anchor_num, row.shot_anchor_den, "shot_anchor",
            revision_id),
        "performance_mapping_hash": row.performance_mapping_hash,
        "vocal": None,
        "segment_hash": row.segment_hash,
    }

    if vocal is not None:
        binding = (await session.execute(text(
            "SELECT vocal_performance_revision_id, binding_hash, "
            "source_start_sample, source_end_sample_exclusive, "
            "sample_rate_hz, performance_origin_num, "
            "performance_origin_den, synchronization_basis_version "
            "FROM performance_revision_vocal_bindings "
            "WHERE performance_revision_id = :pr"),
            {"pr": row["performance_revision_id"]}
        )).mappings().one_or_none()
        if binding is None:
            raise internal_invariant(
                f"{where} is dialogue-bound but its immutable "
                "synchronization binding is gone.")
        if (binding.binding_hash != row.vocal_binding_hash
                or binding.vocal_performance_revision_id
                != row.vocal_performance_revision_id
                or binding.source_start_sample != row.source_start_sample
                or binding.source_end_sample_exclusive
                != row.source_end_sample_exclusive
                or binding.sample_rate_hz != row.sample_rate_hz):
            raise internal_invariant(
                f"{where} captured vocal closure disagrees with the "
                "immutable synchronization binding that proved it.")
        vp = (await session.execute(text(
            "SELECT dialogue_line_revision_id, revision_number, "
            "speaker_subject_id, native_sample_rate_hz, "
            "retained_audio_blob_hash, adopted_at "
            "FROM vocal_performance_revisions WHERE id = :vp"),
            {"vp": row.vocal_performance_revision_id}
        )).mappings().one_or_none()
        if vp is None:
            raise internal_invariant(
                f"{where} names a missing immutable "
                f"VocalPerformanceRevision "
                f"{row.vocal_performance_revision_id!r}.")
        answer["vocal"] = {
            "vocal_performance_revision_id":
                row.vocal_performance_revision_id,
            "vocal_performance_revision": {
                "dialogue_line_revision_id":
                    vp.dialogue_line_revision_id,
                "revision_number": vp.revision_number,
                "speaker_subject_id": vp.speaker_subject_id,
                "native_sample_rate_hz": vp.native_sample_rate_hz,
                "retained_audio_blob_hash":
                    vp.retained_audio_blob_hash,
                "adopted_at": vp.adopted_at,
            },
            "synchronization_binding": {
                "binding_hash": binding.binding_hash,
                "vocal_performance_revision_id":
                    binding.vocal_performance_revision_id,
                "source_start_sample": binding.source_start_sample,
                "source_end_sample_exclusive":
                    binding.source_end_sample_exclusive,
                "sample_rate_hz": binding.sample_rate_hz,
                "performance_origin_ms": _rat(
                    binding.performance_origin_num,
                    binding.performance_origin_den,
                    "binding origin", revision_id),
                "synchronization_basis_version":
                    binding.synchronization_basis_version,
            },
            "sample_interval": {
                "source_start_sample": row.source_start_sample,
                "source_end_sample_exclusive":
                    row.source_end_sample_exclusive,
                "sample_rate_hz": row.sample_rate_hz,
            },
            "vocal_mapping_hash": row.vocal_mapping_hash,
        }
    return answer


def _verified_payload_bytes(settings, where: str, blob_hash: str) -> bytes:
    """FPR-M17CC-05: open the retained payload file, rehash it against
    its content address, and return the exact bytes. A missing or
    corrupt physical file (with the DB row intact) fails closed — the
    historical answer may never substitute metadata for the frozen
    bytes."""
    if settings is None:
        from soloring.settings import get_settings
        settings = get_settings()
    from soloring.assets.blob_store import BlobStore

    path = BlobStore(settings).path_for_hash(blob_hash)
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise internal_invariant(
            f"{where} retained payload blob {blob_hash} is physically "
            "missing from storage") from exc
    except OSError as exc:
        raise internal_invariant(
            f"{where} retained payload blob {blob_hash} is unreadable: "
            f"{exc}") from exc
    if hashlib.sha256(data).hexdigest() != blob_hash:
        raise internal_invariant(
            f"{where} retained payload blob {blob_hash} does not "
            "rehash to its content address")
    return data
