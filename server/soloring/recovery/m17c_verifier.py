"""M17C-A/PF-03 recovery verifier (SR26-02 corrective).

Minimal semantic verification of the authority introduced at migration
head 0020: the immutable vocal-synchronization binding companions and
the SR26-01 applicability classifications. Runs at the 0020 restore
head after every predecessor verifier (M11..M17B), so a restored
database can no longer certify corrupted, missing, or downgraded PF-03
authority.
"""

from __future__ import annotations

import json
import math
import sqlite3
from fractions import Fraction
from pathlib import Path

from soloring.errors import SoloRingError

_BINDING_FIELDS = (
    "vocal_performance_revision_id",
    "source_start_sample",
    "source_end_sample_exclusive",
    "sample_rate_hz",
    "performance_origin_num",
    "performance_origin_den",
    "synchronization_basis_version",
    "binding_schema_version",
    "binding_json",
    "binding_hash",
)

_REQUIRED_ARTICULATION = (
    "profile-1/face.articulation.jaw_open",
    "profile-1/face.articulation.lip_round",
    "profile-1/face.articulation.lip_press",
    "profile-1/face.articulation.mouth_width",
)

_M17C_TABLES = (
    "performance_candidate_vocal_bindings",
    "performance_revision_vocal_bindings",
    "performance_candidate_sync_classifications",
    "performance_revision_sync_classifications",
)

# B-F1: created by successor migration 0021 only — a 0020 database
# lawfully lacks it, so its absence is not corruption and the
# working-mapping pass is conditional on its presence.
_SHOT_MAPPING_TABLE = "shot_performance_segment_mappings"

# SR2-02: the exact staged head drives the schema contract (mirrors
# recovery.backup's M17C_A/M17C_B constants without importing the
# backup module — the backup module installs this verifier).
_HEAD_0020 = "0020_m17c_perf_capture_r2"
_HEAD_0021 = "0021_m17c_shot_performance_mappings"

# SR2-02 deterministic schema proof for the PF-02 table at 0021:
# PRAGMA table_info (name -> (notnull, pk ordinal)), foreign_key_list
# ((table, from, to) -> on_delete), index contract, and the named
# CHECK constraints in the sqlite_master DDL.
_SPSM_COLUMNS = {
    "shot_id": (1, 1), "position": (1, 2),
    "performance_revision_id": (1, 0),
    "performance_start_num": (1, 0), "performance_start_den": (1, 0),
    "performance_end_num": (1, 0), "performance_end_den": (1, 0),
    "shot_anchor_num": (1, 0), "shot_anchor_den": (1, 0),
    "vocal_mapping_position": (0, 0),
    "mapping_schema_version": (1, 0),
    "mapping_json": (1, 0), "mapping_hash": (1, 0),
    "created_at": (1, 0), "updated_at": (1, 0),
}
_SPSM_FKS = {
    ("shots", "shot_id", "id"): "RESTRICT",
    ("performance_revisions", "performance_revision_id", "id"): "RESTRICT",
}
_SPSM_CHECKS = ("ck_spsm_position", "ck_spsm_start_den_positive",
                "ck_spsm_end_den_positive", "ck_spsm_anchor_den_positive",
                "ck_spsm_mapping_schema", "ck_spsm_mapping_hash_len")


def _corrupt(msg: str) -> Exception:
    return SoloRingError("RECOVERY_CORRUPTION", msg, status_code=500)


def verify_m17c_binding_state(staged_db: Path,
                              blob_root: Path | None = None,
                              *, head: str) -> None:
    """SR2-02: head-aware M17C recovery verification.

    At head 0020 the four PF-03 companion tables are REQUIRED and the
    PF-02 working-mapping table MUST be absent (it is created by
    successor migration 0021 only). At head 0021 the PF-02 table is
    REQUIRED, its physical schema is proven deterministically, and the
    working-mapping row laws run. Schema shape is NEVER inferred from
    optional table presence."""
    if blob_root is None:
        from soloring.settings import get_settings
        blob_root = get_settings().blob_dir
    if head not in (_HEAD_0020, _HEAD_0021):
        raise _corrupt(
            f"M17C verifier invoked at unsupported staged head {head!r}")
    con = sqlite3.connect(staged_db)
    con.row_factory = sqlite3.Row
    try:
        present = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not set(_M17C_TABLES) <= present:
            raise _corrupt("M17C tables missing from staged schema")
        if head == _HEAD_0020:
            if _SHOT_MAPPING_TABLE in present:
                raise _corrupt(
                    "staged head 0020 carries the PF-02 working-mapping "
                    "table — that table is created by successor "
                    "migration 0021 only; a 0020 database must not have "
                    "it")
        else:
            if _SHOT_MAPPING_TABLE not in present:
                raise _corrupt(
                    "staged head 0021 is missing the PF-02 "
                    "working-mapping table")
            _verify_spsm_schema(con)
        _verify_classifications(con)
        _verify_candidate_bindings(con, blob_root)
        _verify_revision_bindings(con)
        _verify_retarget_lineage(con)
        if head == _HEAD_0021:
            _verify_shot_performance_mappings(con)
    finally:
        con.close()


def _verify_spsm_schema(con: sqlite3.Connection) -> None:
    """SR2-02: deterministic physical-schema proof for the PF-02 table
    (columns/nullability/PK, FKs with RESTRICT, the PR index, and the
    named CHECK contract) — never trust row laws alone."""
    cols = {r[1]: (r[3], r[5]) for r in con.execute(
        f"PRAGMA table_info({_SHOT_MAPPING_TABLE})")}
    if cols != _SPSM_COLUMNS:
        raise _corrupt(
            f"{_SHOT_MAPPING_TABLE} column contract diverges: got "
            f"{sorted(cols.items())}")
    fks = {(r[2], r[3], r[4]): r[6] for r in con.execute(
        f"PRAGMA foreign_key_list({_SHOT_MAPPING_TABLE})")}
    if fks != _SPSM_FKS:
        raise _corrupt(
            f"{_SHOT_MAPPING_TABLE} foreign-key contract diverges: got "
            f"{sorted(fks.items())}")
    # PRAGMA index_list rows: (seq, name, unique, origin, partial) —
    # the contract is on ORIGIN 'c' (an explicit CREATE INDEX), not the
    # uniqueness flag (the PK's sqlite_autoindex is a separate index)
    indexes = {r[1]: r[3] for r in con.execute(
        f"PRAGMA index_list({_SHOT_MAPPING_TABLE})")}
    if indexes.get("ix_spsm_pr") != "c":
        raise _corrupt(
            f"{_SHOT_MAPPING_TABLE} index contract diverges: expected "
            f"ix_spsm_pr as a CREATE INDEX index, got {sorted(indexes.items())}")
    ix_cols = [r[2] for r in con.execute("PRAGMA index_info(ix_spsm_pr)")]
    if ix_cols != ["performance_revision_id"]:
        raise _corrupt(
            "ix_spsm_pr does not index exactly performance_revision_id")
    sql = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        f"AND name = '{_SHOT_MAPPING_TABLE}'").fetchone()[0]
    for name in _SPSM_CHECKS:
        if name not in sql:
            raise _corrupt(
                f"{_SHOT_MAPPING_TABLE} DDL lost CHECK constraint "
                f"{name!r}")


def _canonical(obj) -> str:
    from soloring.domain.canonical import canonical_json_str
    return canonical_json_str(obj)


def _hash(obj) -> str:
    from soloring.domain.canonical import canonical_hash
    return canonical_hash(obj)


def _check_rational(num, den, what: str) -> None:
    if den <= 0 or math.gcd(abs(num), den) != 1 or (num == 0
                                                    and den != 1):
        raise _corrupt(f"{what} rational {num}/{den} is not canonical")


def _verify_classifications(con: sqlite3.Connection) -> None:
    for table, parent, parent_col, what in (
        ("performance_candidate_sync_classifications",
         "performance_candidates", "performance_candidate_id",
         "performance candidate"),
        ("performance_revision_sync_classifications",
         "performance_revisions", "performance_revision_id",
         "performance revision"),
    ):
        classified = {r[0] for r in con.execute(
            f"SELECT {parent_col} FROM {table}")}
        for (row_id,) in con.execute(
                f"SELECT id FROM {parent}"):
            if row_id not in classified:
                raise _corrupt(
                    f"{what} {row_id!r} has no PF-03 sync "
                    "classification; applicability cannot be determined")
        for r in con.execute(f"SELECT * FROM {table}"):
            if r["classification_schema_version"] != 1:
                raise _corrupt(
                    f"{what} {r[parent_col]!r} classification schema "
                    "version is not 1")
            if r["sync_mode"] not in ("NONE", "VOCAL_V1"):
                raise _corrupt(
                    f"{what} {r[parent_col]!r} classification has unknown "
                    f"mode {r['sync_mode']!r}")


def _binding_cardinality(con, *, parent_col, parent_table, binding_table,
                         classification_table, what):
    """Yield (parent_row, classification, binding_row_or_None) enforcing
    NONE-prohibits / VOCAL_V1-requires cardinality."""
    for parent in con.execute(f"SELECT * FROM {parent_table}"):
        cls = con.execute(
            f"SELECT * FROM {classification_table} WHERE {parent_col} = ?",
            (parent["id"],)).fetchone()
        if cls is None:
            raise _corrupt(
                f"{what} {parent['id']!r} has no PF-03 sync "
                "classification; applicability cannot be determined")
        binding = con.execute(
            f"SELECT * FROM {binding_table} WHERE {parent_col} = ?",
            (parent["id"],)).fetchone()
        if cls["sync_mode"] == "VOCAL_V1" and binding is None:
            raise _corrupt(
                f"{what} {parent['id']!r} is classified VOCAL_V1 but its "
                "PF-03 binding companion is missing (total companion loss)")
        if cls["sync_mode"] == "NONE" and binding is not None:
            raise _corrupt(
                f"{what} {parent['id']!r} is classified NONE but carries a "
                "PF-03 binding companion")
        yield parent, cls, binding


def _verify_binding_row(con, row, parent, what: str) -> None:
    if row["binding_schema_version"] != 1 or \
            row["synchronization_basis_version"] != 1:
        raise _corrupt(
            f"{what} {parent['id']!r} binding schema/basis version is not 1")
    _check_rational(row["performance_origin_num"],
                    row["performance_origin_den"],
                    f"{what} {parent['id']!r} origin")
    doc = {
        "binding_schema_version": row["binding_schema_version"],
        "synchronization_basis_version":
            row["synchronization_basis_version"],
        "vocal_performance_revision_id":
            row["vocal_performance_revision_id"],
        "source_start_sample": row["source_start_sample"],
        "source_end_sample_exclusive":
            row["source_end_sample_exclusive"],
        "sample_rate_hz": row["sample_rate_hz"],
        "performance_origin_ms": {
            "num": row["performance_origin_num"],
            "den": row["performance_origin_den"],
        },
    }
    if row["binding_json"] != _canonical(doc) or \
            row["binding_hash"] != _hash(doc):
        raise _corrupt(
            f"{what} {parent['id']!r} binding canonical bytes/hash diverge")

    vp = con.execute(
        "SELECT * FROM vocal_performance_revisions WHERE id = ?",
        (row["vocal_performance_revision_id"],)).fetchone()
    if vp is None:
        raise _corrupt(
            f"{what} {parent['id']!r} binding names a missing "
            f"VocalPerformanceRevision "
            f"{row['vocal_performance_revision_id']!r}")
    if row["sample_rate_hz"] != vp["native_sample_rate_hz"]:
        raise _corrupt(
            f"{what} {parent['id']!r} binding sample rate != VP native "
            "sample rate")
    if not (vp["trim_start_sample"] <= row["source_start_sample"] <
            row["source_end_sample_exclusive"] <=
            vp["trim_end_sample_exclusive"]):
        raise _corrupt(
            f"{what} {parent['id']!r} binding source interval lies outside "
            "the VP trim")
    if parent["subject_id"] != vp["speaker_subject_id"]:
        raise _corrupt(
            f"{what} {parent['id']!r} subject != bound VP speaker")

    start = Fraction(row["performance_origin_num"],
                     row["performance_origin_den"])
    end = start + Fraction(
        (row["source_end_sample_exclusive"]
         - row["source_start_sample"]) * 1000, row["sample_rate_hz"])
    domain_lo = Fraction(parent["temporal_start_num"],
                         parent["temporal_start_den"])
    domain_hi = Fraction(parent["temporal_end_num"],
                         parent["temporal_end_den"])
    if not (domain_lo <= start < end <= domain_hi):
        raise _corrupt(
            f"{what} {parent['id']!r} binding interval lies outside the "
            "temporal domain")
    return start, end


def _verify_candidate_bindings(con, blob_root: Path) -> None:
    for parent, cls, binding in _binding_cardinality(
            con,
            parent_col="performance_candidate_id",
            parent_table="performance_candidates",
            binding_table="performance_candidate_vocal_bindings",
            classification_table=(
                "performance_candidate_sync_classifications"),
            what="performance candidate"):
        if binding is None:
            continue
        if parent["performance_kind"] not in ("FACIAL", "BODY_FACIAL"):
            raise _corrupt(
                f"performance candidate {parent['id']!r} carries a vocal "
                "binding but is not FACIAL/BODY_FACIAL")
        start, end = _verify_binding_row(
            con, binding, parent, "performance candidate")
        _verify_payload_pf03_laws(con, blob_root, parent, binding,
                                  start, end)


def _verify_revision_bindings(con) -> None:
    # DR26-01 closure invariant first: an adopted revision's sync
    # classification must equal its adopted candidate's classification
    # BEFORE either side's NONE/VOCAL_V1 interpretation — checked for
    # every revision, including revisions with no binding at all.
    for parent in con.execute(
            "SELECT * FROM performance_revisions"):
        cls = con.execute(
            "SELECT * FROM performance_revision_sync_classifications "
            "WHERE performance_revision_id = ?",
            (parent["id"],)).fetchone()
        if cls is None:
            raise _corrupt(
                f"performance revision {parent['id']!r} has no PF-03 sync "
                "classification; applicability cannot be determined")
        candidate = con.execute(
            "SELECT * FROM performance_candidates WHERE id = ?",
            (parent["adopted_candidate_id"],)).fetchone()
        if candidate is None:
            raise _corrupt(
                f"performance revision {parent['id']!r} adopted candidate "
                "is missing")
        candidate_cls = con.execute(
            "SELECT * FROM performance_candidate_sync_classifications "
            "WHERE performance_candidate_id = ?",
            (candidate["id"],)).fetchone()
        if candidate_cls is None:
            raise _corrupt(
                f"adopted candidate {candidate['id']!r} has no PF-03 sync "
                "classification; applicability cannot be determined")
        if candidate_cls["sync_mode"] != cls["sync_mode"]:
            raise _corrupt(
                # PAIR-CLASSIFICATION-DISAGREEMENT is the stable
                # diagnostic marker for the cross-pair branch (C3-02):
                # regressions assert it plus both conflicting modes so
                # the proof cannot be satisfied by a missing/malformed
                # classification or a local cardinality failure.
                "PAIR-CLASSIFICATION-DISAGREEMENT: "
                f"performance revision {parent['id']!r} classification "
                f"{cls['sync_mode']!r} != adopted candidate classification "
                f"{candidate_cls['sync_mode']!r}")

    for parent, cls, binding in _binding_cardinality(
            con,
            parent_col="performance_revision_id",
            parent_table="performance_revisions",
            binding_table="performance_revision_vocal_bindings",
            classification_table=(
                "performance_revision_sync_classifications"),
            what="performance revision"):
        if binding is None:
            continue
        _verify_binding_row(con, binding, parent, "performance revision")
        candidate = con.execute(
            "SELECT * FROM performance_candidates WHERE id = ?",
            (parent["adopted_candidate_id"],)).fetchone()
        if candidate is None:
            raise _corrupt(
                f"performance revision {parent['id']!r} adopted candidate "
                "is missing")
        candidate_cls = con.execute(
            "SELECT * FROM performance_candidate_sync_classifications "
            "WHERE performance_candidate_id = ?",
            (candidate["id"],)).fetchone()
        if candidate_cls is None or \
                candidate_cls["sync_mode"] != cls["sync_mode"]:
            raise _corrupt(
                f"performance revision {parent['id']!r} classification != "
                "adopted candidate classification")
        candidate_binding = con.execute(
            "SELECT * FROM performance_candidate_vocal_bindings "
            "WHERE performance_candidate_id = ?",
            (candidate["id"],)).fetchone()
        if candidate_binding is None:
            raise _corrupt(
                f"performance revision {parent['id']!r} source candidate "
                "binding is missing")
        for field in _BINDING_FIELDS:
            if candidate_binding[field] != binding[field]:
                raise _corrupt(
                    f"performance revision {parent['id']!r} binding != "
                    "adopted candidate binding closure")


def _verify_payload_pf03_laws(con, blob_root: Path, candidate, binding,
                              start: Fraction, end: Fraction) -> None:
    """Articulation + cited-alignment laws over the retained payload."""
    import hashlib
    h = candidate["canonical_channel_payload_blob_hash"]
    p = blob_root / "sha256" / h[:2] / h[2:4] / h
    if not p.is_file():
        raise _corrupt(f"PF-03 candidate payload blob {h} missing")
    data = p.read_bytes()
    if hashlib.sha256(data).hexdigest() != h:
        raise _corrupt(f"PF-03 candidate payload blob {h} does not rehash")
    doc = json.loads(data)
    by_key = {ch["channel_key"]: ch for ch in doc["channels"]}
    for key in _REQUIRED_ARTICULATION:
        channel = by_key.get(key)
        if channel is None:
            raise _corrupt(
                f"dialogue-bound candidate {candidate['id']!r} lacks "
                f"articulation channel {key!r}")
        if not any(start <= Fraction(kf["time_ms"]["num"],
                                     kf["time_ms"]["den"]) < end
                   for kf in channel["keyframes"]):
            raise _corrupt(
                f"dialogue-bound candidate {candidate['id']!r} articulation "
                f"channel {key!r} has no keyframe inside the bound interval")
    seen = set()
    for channel in doc["channels"]:
        for kf in channel["keyframes"]:
            aid = kf["provenance"]["source_alignment_id"]
            if aid is None or aid in seen:
                continue
            seen.add(aid)
            alignment = con.execute(
                "SELECT vocal_performance_revision_id FROM "
                "dialogue_alignments WHERE id = ?",
                (aid,)).fetchone()
            if alignment is None:
                raise _corrupt(
                    f"dialogue-bound candidate {candidate['id']!r} cites a "
                    f"missing dialogue alignment {aid!r}")
            if alignment["vocal_performance_revision_id"] != \
                    binding["vocal_performance_revision_id"]:
                raise _corrupt(
                    f"dialogue-bound candidate {candidate['id']!r} cites an "
                    "alignment derived from a different "
                    "VocalPerformanceRevision")


def _verify_retarget_lineage(con) -> None:
    """A retargeted candidate classified VOCAL_V1 must carry exactly the
    source revision's binding closure."""
    for candidate in con.execute(
            "SELECT * FROM performance_candidates "
            "WHERE source_kind = 'retargeted'"):
        cls = con.execute(
            "SELECT * FROM performance_candidate_sync_classifications "
            "WHERE performance_candidate_id = ?",
            (candidate["id"],)).fetchone()
        if cls is None:
            raise _corrupt(
                f"retarget candidate {candidate['id']!r} has no PF-03 sync "
                "classification")
        prov = json.loads(candidate["provenance_json"])
        source_id = prov.get("retarget", {}).get(
            "source_performance_revision_id")
        if source_id is None:
            raise _corrupt(
                f"retarget candidate {candidate['id']!r} provenance lacks "
                "the source revision id")
        source_cls = con.execute(
            "SELECT * FROM performance_revision_sync_classifications "
            "WHERE performance_revision_id = ?",
            (source_id,)).fetchone()
        if source_cls is None or \
                source_cls["sync_mode"] != cls["sync_mode"]:
            raise _corrupt(
                f"retarget candidate {candidate['id']!r} classification != "
                f"source revision {source_id!r} classification")
        if cls["sync_mode"] != "VOCAL_V1":
            continue
        binding = con.execute(
            "SELECT * FROM performance_candidate_vocal_bindings "
            "WHERE performance_candidate_id = ?",
            (candidate["id"],)).fetchone()
        source_binding = con.execute(
            "SELECT * FROM performance_revision_vocal_bindings "
            "WHERE performance_revision_id = ?",
            (source_id,)).fetchone()
        if binding is None or source_binding is None:
            raise _corrupt(
                f"retarget candidate {candidate['id']!r} VOCAL_V1 lineage "
                "is missing a binding companion")
        for field in _BINDING_FIELDS:
            if binding[field] != source_binding[field]:
                raise _corrupt(
                    f"retarget candidate {candidate['id']!r} binding "
                    f"diverges from source revision {source_id!r}")


def _verify_shot_performance_mappings(con) -> None:
    """frozen R4 §13.3: working mapping rows are verified for canonical
    storage/project/reference integrity (current VP selection is NOT
    historical truth during backup validation — a lawfully STALE
    working mapping remains a lawful stored working state)."""
    import math
    for row in con.execute(
            "SELECT * FROM shot_performance_segment_mappings"):
        pr = con.execute(
            "SELECT project_id FROM performance_revisions WHERE id = ?",
            (row["performance_revision_id"],)).fetchone()
        if pr is None:
            raise _corrupt(
                f"performance mapping {row['shot_id']!r}@"
                f"{row['position']} references a missing "
                "PerformanceRevision")
        shot = con.execute(
            "SELECT project_id FROM shots WHERE id = ?",
            (row["shot_id"],)).fetchone()
        if shot is None:
            raise _corrupt(
                f"performance mapping {row['shot_id']!r}@"
                f"{row['position']} references a missing Shot")
        if pr["project_id"] != shot["project_id"]:
            raise _corrupt(
                f"performance mapping {row['shot_id']!r}@"
                f"{row['position']} crosses projects")
        if row["mapping_schema_version"] != 1:
            raise _corrupt(
                f"performance mapping {row['shot_id']!r}@"
                f"{row['position']} schema version is not 1")
        if row["performance_start_den"] <= 0 or \
                row["performance_end_den"] <= 0 or \
                row["shot_anchor_den"] <= 0:
            raise _corrupt(
                f"performance mapping {row['shot_id']!r}@"
                f"{row['position']} stores a nonpositive rational "
                "denominator")
        if math.gcd(abs(row["performance_start_num"]),
                    row["performance_start_den"]) != 1 or \
                math.gcd(abs(row["performance_end_num"]),
                         row["performance_end_den"]) != 1 or \
                math.gcd(abs(row["shot_anchor_num"]),
                         row["shot_anchor_den"]) != 1:
            raise _corrupt(
                f"performance mapping {row['shot_id']!r}@"
                f"{row['position']} stores a noncanonical rational")
        doc = {
            "mapping_schema_version": row["mapping_schema_version"],
            "performance_revision_id": row["performance_revision_id"],
            "performance_start_ms": {
                "num": row["performance_start_num"],
                "den": row["performance_start_den"]},
            "performance_end_ms": {
                "num": row["performance_end_num"],
                "den": row["performance_end_den"]},
            "shot_anchor_ms": {
                "num": row["shot_anchor_num"],
                "den": row["shot_anchor_den"]},
            "vocal_mapping_position":
                row["vocal_mapping_position"],
        }
        if row["mapping_json"] != _canonical(doc) or \
                row["mapping_hash"] != _hash(doc):
            raise _corrupt(
                f"performance mapping {row['shot_id']!r}@"
                f"{row['position']} canonical bytes/hash diverge")
        # B-F3/SR2-03 pairing laws. Applicability comes from the
        # immutable discriminator, never from the nullable payload
        # shape: a shape that the supported API cannot create (VOCAL_V1
        # without a position; a position on a non-VOCAL_V1 revision)
        # is corruption. A MISSING paired vocal mapping is an
        # API-creatable lawful BLOCKED working state (supported DELETE;
        # readiness reports BLOCKED_BINDING_INTEGRITY). SR2-03: so is a
        # paired vocal mapping whose VP was REPOINTED through the
        # supported M17A PUT to the now-current selection — mutable
        # working drift against the immutable revision binding, never
        # rewritten by diagnosis and never refused here. Other
        # structural corruption of the vocal row stays the M17A
        # verifier's concern.
        cls = con.execute(
            "SELECT sync_mode FROM "
            "performance_revision_sync_classifications "
            "WHERE performance_revision_id = ?",
            (row["performance_revision_id"],)).fetchone()
        vocal_v1 = cls is not None and cls["sync_mode"] == "VOCAL_V1"
        if row["vocal_mapping_position"] is not None:
            if not vocal_v1:
                raise _corrupt(
                    f"performance mapping {row['shot_id']!r}@"
                    f"{row['position']} carries vocal_mapping_position "
                    "but the PerformanceRevision is not VOCAL_V1")
        else:
            if vocal_v1:
                raise _corrupt(
                    f"performance mapping {row['shot_id']!r}@"
                    f"{row['position']} maps a VOCAL_V1 "
                    "PerformanceRevision without vocal_mapping_position")
