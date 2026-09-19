"""M17A dialogue/vocal semantic recovery verifier (frozen R5 §12.2).

Runs against the staged DB (and, for physical byte checks, the active
Blob root) during backup and restore. Fail-closed on any incoherence;
duplicate DialogueAlignment rows with identical provenance and/or
bytes are NOT corruption (the no-dedupe identity rule) — each row is
verified independently.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from pathlib import Path

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import SoloRingError

_M17A_TABLES = (
    "dialogue_lines",
    "dialogue_line_revisions",
    "vocal_candidates",
    "vocal_performance_revisions",
    "vocal_performance_selections",
    "shot_vocal_segment_mappings",
    "dialogue_alignments",
)

_TS_LEN_OK = lambda ts: isinstance(ts, str) and len(ts) == 27 and \
    ts.endswith("Z")


def _corrupt(msg: str) -> Exception:
    return SoloRingError("RECOVERY_CORRUPTION", msg, status_code=500)


def _blob_path(blob_root: Path, h: str) -> Path:
    return blob_root / "sha256" / h[:2] / h[2:4] / h


def _read_blob(blob_root: Path, h: str) -> bytes:
    p = _blob_path(blob_root, h)
    if not p.is_file():
        raise _corrupt(f"M17A blob {h} missing from the Blob root")
    data = p.read_bytes()
    if hashlib.sha256(data).hexdigest() != h:
        raise _corrupt(f"M17A blob {h} bytes do not rehash")
    return data


def _inspect_wave_min(data: bytes) -> tuple[int, int]:
    """(sample_rate_hz, sample_frame_count) via the same rules as
    audio_inspection (RIFF/WAVE PCM only)."""
    import struct

    if len(data) < 12 or data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise _corrupt("retained audio blob is not RIFF/WAVE")
    pos, fmt, data_bytes, channels, rate, bits = 12, False, None, \
        None, None, None
    while pos + 8 <= len(data):
        cid = data[pos:pos + 4]
        (size,) = struct.unpack_from("<I", data, pos + 4)
        body = data[pos + 8: pos + 8 + size]
        if len(body) < size:
            raise _corrupt("truncated WAVE chunk")
        if cid == b"fmt ":
            (aformat, ch, rt, _, _, bp) = struct.unpack_from(
                "<HHIIHH", body, 0)
            if aformat != 1:
                raise _corrupt("retained audio blob is not PCM")
            channels, rate, bits = ch, rt, bp
            fmt = True
        elif cid == b"data":
            data_bytes = size
        pos += 8 + size + (size & 1)
    if not fmt or data_bytes is None:
        raise _corrupt("WAVE missing fmt/data chunk")
    fb = (channels * bits) // 8
    if fb == 0 or data_bytes % fb != 0:
        raise _corrupt("WAVE data chunk not whole frames")
    return rate, data_bytes // fb


def verify_m17a_dialogue_vocal_state(staged_db: Path,
                                     blob_root: Path | None = None
                                     ) -> None:
    if blob_root is None:
        from soloring.settings import get_settings
        blob_root = get_settings().blob_dir
    con = sqlite3.connect(staged_db)
    con.row_factory = sqlite3.Row
    try:
        present = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(_M17A_TABLES) <= present:
            # head 0018 always carries the tables; absence is corruption
            raise _corrupt("M17A tables missing from staged schema")
        _verify_dialogue(con)
        _verify_candidates(con, blob_root)
        _verify_vps(con)
        _verify_selections(con)
        _verify_mappings(con)
        _verify_alignments(con, blob_root)
    finally:
        con.close()


def _verify_dialogue(con: sqlite3.Connection) -> None:
    lines = {r["id"]: r for r in con.execute(
        "SELECT * FROM dialogue_lines")}
    for r in con.execute("SELECT * FROM dialogue_line_revisions"):
        line = lines.get(r["dialogue_line_id"])
        if line is None:
            raise _corrupt(f"DLR {r['id']} has no DialogueLine")
        spec = json.loads(r["spec_json"])
        canonical = {"schema_version": 1,
                     "speaker_subject_id": r["speaker_subject_id"],
                     "wording": r["wording"],
                     "language": r["language"]}
        if spec != canonical:
            raise _corrupt(f"DLR {r['id']} stored spec != row triple")
        if canonical_hash(canonical) != r["spec_hash"]:
            raise _corrupt(f"DLR {r['id']} spec_hash mismatch")
        speaker = con.execute(
            "SELECT project_id FROM creative_entities WHERE id = ?",
            (r["speaker_subject_id"],)).fetchone()
        if speaker is None or speaker["project_id"] != line["project_id"]:
            raise _corrupt(f"DLR {r['id']} speaker not in line project")
    # numbering legality
    for r in con.execute(
            "SELECT dialogue_line_id, COUNT(*) n, "
            "COUNT(DISTINCT revision_number) d, "
            "MIN(revision_number) lo FROM dialogue_line_revisions "
            "GROUP BY dialogue_line_id"):
        if r["n"] != r["d"] or r["lo"] < 1:
            raise _corrupt("DLR numbering illegal")


def _verify_candidates(con: sqlite3.Connection,
                       blob_root: Path) -> None:
    for r in con.execute("SELECT * FROM vocal_candidates"):
        prov = json.loads(r["provenance_json"])
        if canonical_hash(prov) != r["provenance_hash"]:
            raise _corrupt(f"candidate {r['id']} provenance rehash fail")
        if prov.get("source_kind") != r["source_kind"]:
            raise _corrupt(
                f"candidate {r['id']} provenance/column source_kind "
                "mismatch")
        if con.execute("SELECT 1 FROM blobs WHERE hash = ?",
                       (r["retained_audio_blob_hash"],)).fetchone() \
                is None:
            raise _corrupt(f"candidate {r['id']} blob row missing")
        data = _read_blob(blob_root, r["retained_audio_blob_hash"])
        rate, frames = _inspect_wave_min(data)
        if rate != r["native_sample_rate_hz"] or \
                frames != r["retained_sample_count"]:
            raise _corrupt(
                f"candidate {r['id']} WAVE inspection disagrees with "
                "stored rate/count")
        if not (0 <= r["trim_start_sample"]
                and r["trim_start_sample"] < r["trim_end_sample_exclusive"]
                and r["trim_end_sample_exclusive"]
                <= r["retained_sample_count"]):
            raise _corrupt(f"candidate {r['id']} trim illegal")


def _verify_vps(con: sqlite3.Connection) -> None:
    for r in con.execute("SELECT * FROM vocal_performance_revisions"):
        c = con.execute("SELECT * FROM vocal_candidates WHERE id = ?",
                        (r["adopted_candidate_id"],)).fetchone()
        if c is None:
            raise _corrupt(f"VP {r['id']} adopted candidate missing")
        dup = con.execute(
            "SELECT COUNT(*) FROM vocal_performance_revisions WHERE "
            "adopted_candidate_id = ?", (r["adopted_candidate_id"],)
        ).fetchone()[0]
        if dup != 1:
            raise _corrupt("candidate adopted more than once")
        if (r["dialogue_line_revision_id"]
                != c["dialogue_line_revision_id"]
                or r["retained_audio_blob_hash"]
                != c["retained_audio_blob_hash"]
                or r["native_sample_rate_hz"] != c["native_sample_rate_hz"]
                or r["retained_sample_count"] != c["retained_sample_count"]
                or r["trim_start_sample"] != c["trim_start_sample"]
                or r["trim_end_sample_exclusive"]
                != c["trim_end_sample_exclusive"]
                or r["source_kind"] != c["source_kind"]
                or r["provenance_json"] != c["provenance_json"]
                or r["provenance_hash"] != c["provenance_hash"]):
            raise _corrupt(
                f"VP {r['id']} closure != adopted candidate closure")
        dlr = con.execute(
            "SELECT speaker_subject_id FROM dialogue_line_revisions "
            "WHERE id = ?", (r["dialogue_line_revision_id"],)).fetchone()
        if dlr is None or \
                r["speaker_subject_id"] != dlr["speaker_subject_id"]:
            raise _corrupt(
                f"VP {r['id']} speaker != DLR speaker (corruption)")


def _verify_selections(con: sqlite3.Connection) -> None:
    total = con.execute(
        "SELECT COUNT(*) FROM dialogue_line_revisions").fetchone()[0]
    rows = {r["dialogue_line_revision_id"]: r for r in con.execute(
        "SELECT * FROM vocal_performance_selections")}
    if len(rows) != total:
        raise _corrupt("selection rows != DLR count")
    for dlr_id, r in rows.items():
        unset = r["selected_vocal_performance_revision_id"] is None
        if unset and not (r["selected_by"] is None
                          and r["selected_at"] is None):
            raise _corrupt(f"selection {dlr_id} UNSET shape invalid")
        if not unset and (r["selected_by"] is None
                          or r["selected_at"] is None):
            raise _corrupt(f"selection {dlr_id} SELECTED shape invalid")
        if not unset:
            vp = con.execute(
                "SELECT dialogue_line_revision_id FROM "
                "vocal_performance_revisions WHERE id = ?",
                (r["selected_vocal_performance_revision_id"],)).fetchone()
            if vp is None or vp["dialogue_line_revision_id"] != dlr_id:
                raise _corrupt(
                    f"selection {dlr_id} binds a foreign-line VP")


def _verify_mappings(con: sqlite3.Connection) -> None:
    for r in con.execute("SELECT * FROM shot_vocal_segment_mappings"):
        doc = json.loads(r["mapping_json"])
        canonical = {"mapping_schema_version": 1,
                     "vocal_performance_revision_id":
                     r["vocal_performance_revision_id"],
                     "source_start_sample": r["source_start_sample"],
                     "source_end_sample_exclusive":
                     r["source_end_sample_exclusive"],
                     "sample_rate_hz": r["sample_rate_hz"],
                     "performance_origin_ms": {
                         "num": r["performance_origin_num"],
                         "den": r["performance_origin_den"]},
                     "shot_anchor_ms": {"num": r["shot_anchor_num"],
                                        "den": r["shot_anchor_den"]}}
        if doc != canonical or \
                canonical_hash(canonical) != r["mapping_hash"]:
            raise _corrupt(f"mapping {r['shot_id']}@{r['position']} "
                           "canonical rehash fail")
        for n, d in ((r["performance_origin_num"],
                      r["performance_origin_den"]),
                     (r["shot_anchor_num"], r["shot_anchor_den"])):
            if d <= 0 or math.gcd(abs(n), d) != 1 or (n == 0 and d != 1):
                raise _corrupt("noncanonical rational in mapping")
        vp = con.execute(
            "SELECT * FROM vocal_performance_revisions WHERE id = ?",
            (r["vocal_performance_revision_id"],)).fetchone()
        if vp is None:
            raise _corrupt("mapping references missing VP")
        if r["sample_rate_hz"] != vp["native_sample_rate_hz"]:
            raise _corrupt("mapping rate != VP native rate")
        if not (r["source_start_sample"] >= vp["trim_start_sample"]
                and r["source_end_sample_exclusive"]
                <= vp["trim_end_sample_exclusive"]):
            raise _corrupt("mapping segment outside VP authoritative "
                           "trim")
        shot = con.execute(
            "SELECT project_id, duration_ms FROM shots WHERE id = ?",
            (r["shot_id"],)).fetchone()
        line = con.execute(
            "SELECT project_id FROM dialogue_lines WHERE id = "
            "(SELECT dialogue_line_id FROM dialogue_line_revisions "
            "WHERE id = ?)",
            (vp["dialogue_line_revision_id"],)).fetchone()
        if shot is None or line is None or \
                shot["project_id"] != line["project_id"]:
            raise _corrupt("mapping Shot/VP project mismatch")
        if shot["duration_ms"] is None or shot["duration_ms"] <= 0:
            raise _corrupt("mapping Shot lacks positive duration")
        # picture intersection (readiness invariant restored historically)
        delta_num = (r["source_end_sample_exclusive"]
                     - r["source_start_sample"]) * 1000
        rate = r["sample_rate_hz"]
        end_ms_num = r["shot_anchor_num"] * rate + delta_num
        start_ms_num = r["shot_anchor_num"] * rate
        if not (end_ms_num > 0
                and start_ms_num < shot["duration_ms"] * rate
                * r["shot_anchor_den"]):
            raise _corrupt("mapping does not intersect Shot picture")


def _verify_alignments(con: sqlite3.Connection,
                       blob_root: Path) -> None:
    for r in con.execute("SELECT * FROM dialogue_alignments"):
        vp = con.execute(
            "SELECT * FROM vocal_performance_revisions WHERE id = ?",
            (r["vocal_performance_revision_id"],)).fetchone()
        if vp is None:
            raise _corrupt(f"alignment {r['id']} VP missing")
        if r["retained_sha256"] != r["retained_blob_hash"]:
            raise _corrupt(f"alignment {r['id']} hash columns disagree")
        if con.execute("SELECT 1 FROM blobs WHERE hash = ?",
                       (r["retained_blob_hash"],)).fetchone() is None:
            raise _corrupt(f"alignment {r['id']} blob row missing")
        data = _read_blob(blob_root, r["retained_blob_hash"])
        doc = json.loads(data.decode("utf-8"))
        if doc.get("schema_version") != 1:
            raise _corrupt(f"alignment {r['id']} schema != 1")
        for arr in ("words", "phonemes", "viseme_classes"):
            for e in doc.get(arr, []):
                if not (vp["trim_start_sample"] <= e["start_sample"]
                        < e["end_sample_exclusive"]
                        <= vp["trim_end_sample_exclusive"]):
                    raise _corrupt(
                        f"alignment {r['id']} entry outside VP trim")
        run = json.loads(r["derivation_run_json"])
        if canonical_hash(run) != r["derivation_run_hash"]:
            raise _corrupt(f"alignment {r['id']} run rehash fail")
        if run.get("input_digest", {}).get(
                "vocal_performance_revision_id") != vp["id"] or \
                run.get("input_digest", {}).get(
                    "retained_audio_blob_sha256") != \
                vp["retained_audio_blob_hash"]:
            raise _corrupt(
                f"alignment {r['id']} run digest != VP identity")
        for f in ("analyzer_id", "analyzer_version", "model_identity",
                  "runtime_identity"):
            if not isinstance(r[f], str) or not r[f].strip():
                raise _corrupt(
                    f"alignment {r['id']} provenance incomplete")
