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

# SR2-02/IR-01: the exact staged head drives the schema contract (mirrors
# recovery.backup's M17C_A/M17C_B constants without importing the
# backup module — the backup module installs this verifier).
_HEAD_0020 = "0020_m17c_perf_capture_r2"
_HEAD_0021 = "0021_m17c_shot_performance_mappings"
# M17C-C slice 1: schema-8 capture storage (the section 13.4 verifier
# laws land with the capture/history slices; at this head the new
# tables are storage-only)
_HEAD_0022 = "0022_m17c_schema8_capture"
# FPR-M17CC-04: the closure-preimage successor — schema-8 companion
# rows captured at 0022 lack the preimage columns and cannot certify
_HEAD_0023 = "0023_m17cc_capture_closure_preimage"

# ---------------------------------------------------------------------------
# IR-01/IR-02: frozen PHYSICAL schema contracts for every migration-0020/0021
# table, proven from PRAGMA evidence + the stored sqlite_master DDL.
#
# The stored DDL is deterministic across the ORM (create_all) and the
# alembic migrations: SQLAlchemy's metadata naming convention prefixes
# CHECK and PRIMARY-KEY constraint names with the table name while FK
# names pass through verbatim (probed against both engines; the stored
# forms below are the FROZEN contract). Column tuples are
# (declared type, notnull, pk ordinal) per PRAGMA table_info; FK maps
# are {(target table, source column, target column):
# (on_update, on_delete, match)} per PRAGMA foreign_key_list; CHECK
# maps are {stored constraint name: normalized expression} parsed from
# the DDL — name-preserving rewrites such as CHECK(1) diverge on the
# expression and are refused.
# ---------------------------------------------------------------------------

_FK_RESTRICT = ("NO ACTION", "RESTRICT", "NONE")


def _binding_contract(table: str, parent_col: str, parent_table: str,
                      ck: str) -> dict:
    n = f"ck_{table}_ck_{ck}"
    return {
        "columns": {
            parent_col: ("VARCHAR(36)", 1, 1),
            "vocal_performance_revision_id": ("VARCHAR(36)", 1, 0),
            "source_start_sample": ("INTEGER", 1, 0),
            "source_end_sample_exclusive": ("INTEGER", 1, 0),
            "sample_rate_hz": ("INTEGER", 1, 0),
            "performance_origin_num": ("INTEGER", 1, 0),
            "performance_origin_den": ("INTEGER", 1, 0),
            "synchronization_basis_version": ("INTEGER", 1, 0),
            "binding_schema_version": ("INTEGER", 1, 0),
            "binding_json": ("TEXT", 1, 0),
            "binding_hash": ("TEXT", 1, 0),
            "created_at": ("TEXT", 1, 0),
        },
        # IND-02: the exact PK column sequence whose SQLite autoindex
        # (origin 'pk') is the lawful consequence of the frozen PK
        "pk_columns": [parent_col],
        # IR-01: the COMPLETE ordered CHECK multiset — closed world
        "checks": [
            (f"{n}_start_nonneg", "source_start_sample >= 0"),
            (f"{n}_sample_order",
             "source_start_sample < source_end_sample_exclusive"),
            (f"{n}_rate_positive", "sample_rate_hz > 0"),
            (f"{n}_origin_den_positive", "performance_origin_den > 0"),
            (f"{n}_sync_basis", "synchronization_basis_version = 1"),
            (f"{n}_schema", "binding_schema_version = 1"),
            (f"{n}_hash_hex",
             "length(binding_hash) = 64 AND "
             "binding_hash NOT GLOB '*[^0-9a-f]*'"),
        ],
        # IR-01: the COMPLETE FK row multiset (seq, target table,
        # source col, target col, ON UPDATE, ON DELETE, MATCH) —
        # duplicates and conflicting actions cannot collapse
        "fks": sorted([
            (0, "vocal_performance_revisions",
             "vocal_performance_revision_id", "id") + _FK_RESTRICT,
            (0, parent_table, parent_col, "id") + _FK_RESTRICT,
        ]),
        # IR-01/IND-02: the closed explicit-index inventory (origin-'c'
        # indexes only) — the PF-03 tables carry none
        "explicit_indexes": {},
        # IND-02: the migrations declare NO additional UNIQUE
        # constraints, so any origin-'u' autoindex refuses
        "unique_indexes": {},
    }


def _classification_contract(table: str, parent_col: str,
                             parent_table: str, ck: str) -> dict:
    n = f"ck_{table}_ck_{ck}"
    return {
        "columns": {
            parent_col: ("VARCHAR(36)", 1, 1),
            "sync_mode": ("TEXT", 1, 0),
            "classification_schema_version": ("INTEGER", 1, 0),
            "created_at": ("TEXT", 1, 0),
        },
        "pk_columns": [parent_col],
        "checks": [
            (f"{n}_mode", "sync_mode IN ('NONE', 'VOCAL_V1')"),
            (f"{n}_schema", "classification_schema_version = 1"),
        ],
        "fks": sorted([
            (0, parent_table, parent_col, "id") + _FK_RESTRICT,
        ]),
        "explicit_indexes": {},
        "unique_indexes": {},
    }


_PF03_CONTRACTS = {
    "performance_candidate_vocal_bindings": _binding_contract(
        "performance_candidate_vocal_bindings",
        "performance_candidate_id", "performance_candidates", "pcvb"),
    "performance_revision_vocal_bindings": _binding_contract(
        "performance_revision_vocal_bindings",
        "performance_revision_id", "performance_revisions", "prvb"),
    "performance_candidate_sync_classifications":
        _classification_contract(
            "performance_candidate_sync_classifications",
            "performance_candidate_id", "performance_candidates", "pcsc"),
    "performance_revision_sync_classifications":
        _classification_contract(
            "performance_revision_sync_classifications",
            "performance_revision_id", "performance_revisions", "prsc"),
}

# ---------------------------------------------------------------------------
# ISR2-M17CC-02: the frozen PHYSICAL schema contracts for the three
# M17C-C successor tables, proven from PRAGMA evidence + the stored
# sqlite_master DDL of a genuinely migrated 0022/0023 database (the
# same _verify_table_schema machinery the predecessor tables use).
# The segment table's lawful shape DIFFERS by head: 0023 recreates it
# with the captured mapping-preimage columns and their constraints.
# ---------------------------------------------------------------------------


def _srpfs_contract() -> dict:
    n = "ck_shot_revision_performance_specs_ck_srpfs"
    return {
        "columns": {
            "shot_revision_id": ("VARCHAR(36)", 1, 1),
            "schema_version": ("INTEGER", 1, 0),
            "spec_json": ("TEXT", 1, 0),
            "spec_hash": ("TEXT", 1, 0),
        },
        "pk_columns": ["shot_revision_id"],
        "checks": [
            (f"{n}_schema", "schema_version = 1"),
            (f"{n}_hash_len", "length(spec_hash) = 64"),
            (f"{n}_hash_hex",
             "spec_hash NOT GLOB '*[^0-9a-f]*'"),
        ],
        "fks": sorted([
            (0, "shot_revisions", "shot_revision_id", "id")
            + _FK_RESTRICT,
        ]),
        "explicit_indexes": {},
        "unique_indexes": {},
    }


def _srpss_contract(*, successor: bool) -> dict:
    n = "ck_shot_revision_performance_segments_ck_srpss"
    columns = {
        "shot_revision_id": ("VARCHAR(36)", 1, 1),
        "position": ("INTEGER", 1, 2),
        "subject_id": ("VARCHAR(36)", 1, 0),
        "performance_revision_id": ("VARCHAR(36)", 1, 0),
        "performance_payload_blob_hash": ("TEXT", 1, 0),
        "performance_payload_sha256": ("TEXT", 1, 0),
        "performance_profile_id": ("TEXT", 1, 0),
        "performance_kind": ("TEXT", 1, 0),
        "performance_start_num": ("INTEGER", 1, 0),
        "performance_start_den": ("INTEGER", 1, 0),
        "performance_end_num": ("INTEGER", 1, 0),
        "performance_end_den": ("INTEGER", 1, 0),
        "shot_anchor_num": ("INTEGER", 1, 0),
        "shot_anchor_den": ("INTEGER", 1, 0),
        "performance_mapping_hash": ("TEXT", 1, 0),
        "vocal_performance_revision_id": ("VARCHAR(36)", 0, 0),
        "vocal_binding_hash": ("TEXT", 0, 0),
        "vocal_mapping_hash": ("TEXT", 0, 0),
        "source_start_sample": ("INTEGER", 0, 0),
        "source_end_sample_exclusive": ("INTEGER", 0, 0),
        "sample_rate_hz": ("INTEGER", 0, 0),
        "segment_json": ("TEXT", 1, 0),
        "segment_hash": ("TEXT", 1, 0),
    }
    checks = [
        (f"{n}_position", "position >= 0"),
    ]
    if successor:
        # FPR-M17CC-04 / 0023: the captured vocal-mapping preimage
        # columns join the all-or-none group and carry their own laws
        # (declaration order per the migration's stored DDL)
        columns.update({
            "vocal_performance_origin_num": ("INTEGER", 0, 0),
            "vocal_performance_origin_den": ("INTEGER", 0, 0),
            "vocal_mapping_position": ("INTEGER", 0, 0),
        })
        checks.append((
            f"{n}_vocal_group_all_or_none",
            "(vocal_performance_revision_id IS NULL AND "
            "vocal_binding_hash IS NULL AND vocal_mapping_hash IS "
            "NULL AND source_start_sample IS NULL AND "
            "source_end_sample_exclusive IS NULL AND sample_rate_hz "
            "IS NULL AND vocal_performance_origin_num IS NULL AND "
            "vocal_performance_origin_den IS NULL AND "
            "vocal_mapping_position IS NULL) OR "
            "(vocal_performance_revision_id IS NOT NULL AND "
            "vocal_binding_hash IS NOT NULL AND vocal_mapping_hash "
            "IS NOT NULL AND source_start_sample IS NOT NULL AND "
            "source_end_sample_exclusive IS NOT NULL AND "
            "sample_rate_hz IS NOT NULL AND "
            "vocal_performance_origin_num IS NOT NULL AND "
            "vocal_performance_origin_den IS NOT NULL AND "
            "vocal_mapping_position IS NOT NULL)"))
        checks.extend([
            (f"{n}_payload_hash_len",
             "length(performance_payload_blob_hash) = 64"),
            (f"{n}_binding_hash_len",
             "length(vocal_binding_hash) = 64 OR vocal_binding_hash "
             "IS NULL"),
            (f"{n}_segment_hash_len", "length(segment_hash) = 64"),
            (f"{n}_vocal_position",
             "vocal_mapping_position >= 0 OR vocal_mapping_position "
             "IS NULL"),
            (f"{n}_vocal_origin_den",
             "vocal_performance_origin_den > 0 OR "
             "vocal_performance_origin_den IS NULL"),
        ])
    else:
        checks.extend([
            (f"{n}_vocal_group_all_or_none",
             "(vocal_performance_revision_id IS NULL AND "
             "vocal_binding_hash IS NULL AND vocal_mapping_hash IS "
             "NULL AND source_start_sample IS NULL AND "
             "source_end_sample_exclusive IS NULL AND sample_rate_hz "
             "IS NULL) OR (vocal_performance_revision_id IS NOT NULL "
             "AND vocal_binding_hash IS NOT NULL AND "
             "vocal_mapping_hash IS NOT NULL AND "
             "source_start_sample IS NOT NULL AND "
             "source_end_sample_exclusive IS NOT NULL AND "
             "sample_rate_hz IS NOT NULL)"),
            (f"{n}_payload_hash_len",
             "length(performance_payload_blob_hash) = 64"),
            (f"{n}_binding_hash_len",
             "length(vocal_binding_hash) = 64 OR vocal_binding_hash "
             "IS NULL"),
            (f"{n}_segment_hash_len", "length(segment_hash) = 64"),
        ])
    return {
        "columns": columns,
        "pk_columns": ["shot_revision_id", "position"],
        "checks": checks,
        "fks": sorted([
            (0, "shot_revisions", "shot_revision_id", "id")
            + _FK_RESTRICT,
            (0, "performance_revisions", "performance_revision_id",
             "id") + _FK_RESTRICT,
        ]),
        "explicit_indexes": {
            "ix_srpss_pr": (0, "c", 0),
        },
        # RR15-M17CC-02: the exact ordered column sequence of the
        # migration's index (name + flags alone certify nothing about
        # WHICH column is indexed)
        "index_columns": {
            "ix_srpss_pr": ["performance_revision_id"],
        },
        "unique_indexes": {},
    }


def _gpi_contract() -> dict:
    n = "ck_generation_performance_inputs_ck_gpi"
    return {
        "columns": {
            "generation_id": ("VARCHAR(36)", 1, 1),
            "input_key": ("TEXT", 1, 2),
            "position": ("INTEGER", 1, 3),
            "artifact_role": ("TEXT", 1, 0),
            "shot_revision_segment_position": ("INTEGER", 1, 0),
            "performance_revision_id": ("VARCHAR(36)", 1, 0),
            "vocal_performance_revision_id": ("VARCHAR(36)", 0, 0),
            "blob_hash": ("TEXT", 1, 0),
            "binding_hash": ("TEXT", 0, 0),
            "segment_hash": ("TEXT", 1, 0),
            "translation_identity": ("TEXT", 1, 0),
            "derived_input_hash": ("TEXT", 1, 0),
            "created_at": ("TEXT", 1, 0),
        },
        "pk_columns": ["generation_id", "input_key", "position"],
        "checks": [
            (f"{n}_role",
             "artifact_role IN ('performance.controls', "
             "'performance.vocal_audio')"),
            (f"{n}_position", "position >= 0"),
            (f"{n}_blob_hash_len", "length(blob_hash) = 64"),
            (f"{n}_binding_hash_len",
             "length(binding_hash) = 64 OR binding_hash IS NULL"),
            (f"{n}_segment_hash_len", "length(segment_hash) = 64"),
            (f"{n}_derived_hash_len",
             "length(derived_input_hash) = 64"),
        ],
        "fks": sorted([
            (0, "generations", "generation_id", "id") + _FK_RESTRICT,
            (0, "blobs", "blob_hash", "hash") + _FK_RESTRICT,
        ]),
        "explicit_indexes": {},
        "unique_indexes": {},
    }


_M17CC_TABLE_CONTRACTS = {
    _HEAD_0022: {
        "shot_revision_performance_specs": _srpfs_contract(),
        "shot_revision_performance_segments":
            _srpss_contract(successor=False),
        "generation_performance_inputs": _gpi_contract(),
    },
    _HEAD_0023: {
        "shot_revision_performance_specs": _srpfs_contract(),
        "shot_revision_performance_segments":
            _srpss_contract(successor=True),
        "generation_performance_inputs": _gpi_contract(),
    },
}

# IR-01: the migration-0021 working-mapping table contract
_SPSM_CONTRACT = {
    "columns": {
        "shot_id": ("VARCHAR(36)", 1, 1),
        "position": ("INTEGER", 1, 2),
        "performance_revision_id": ("VARCHAR(36)", 1, 0),
        "performance_start_num": ("INTEGER", 1, 0),
        "performance_start_den": ("INTEGER", 1, 0),
        "performance_end_num": ("INTEGER", 1, 0),
        "performance_end_den": ("INTEGER", 1, 0),
        "shot_anchor_num": ("INTEGER", 1, 0),
        "shot_anchor_den": ("INTEGER", 1, 0),
        "vocal_mapping_position": ("INTEGER", 0, 0),
        "mapping_schema_version": ("INTEGER", 1, 0),
        "mapping_json": ("TEXT", 1, 0),
        "mapping_hash": ("TEXT", 1, 0),
        "created_at": ("TEXT", 1, 0),
        "updated_at": ("TEXT", 1, 0),
    },
    "checks": [
        ("ck_shot_performance_segment_mappings_ck_spsm_position",
         "position >= 0"),
        ("ck_shot_performance_segment_mappings_"
         "ck_spsm_start_den_positive",
         "performance_start_den > 0"),
        ("ck_shot_performance_segment_mappings_"
         "ck_spsm_end_den_positive",
         "performance_end_den > 0"),
        ("ck_shot_performance_segment_mappings_"
         "ck_spsm_anchor_den_positive",
         "shot_anchor_den > 0"),
        ("ck_shot_performance_segment_mappings_"
         "ck_spsm_mapping_schema",
         "mapping_schema_version = 1"),
        ("ck_shot_performance_segment_mappings_"
         "ck_spsm_mapping_hash_len",
         "length(mapping_hash) = 64"),
    ],
    "fks": sorted([
        (0, "shots", "shot_id", "id") + _FK_RESTRICT,
        (0, "performance_revisions", "performance_revision_id", "id")
        + _FK_RESTRICT,
    ]),
    "explicit_indexes": {"ix_spsm_pr": (0, "c", 0)},
    "pk_columns": ["shot_id", "position"],
    "unique_indexes": {},
}


def _find_word(sql: str, word: str, start: int):
    """Case-insensitive WHOLE-WORD find (identifier boundaries)."""
    low = sql.lower()
    w = word.lower()
    n = len(sql)
    i = start
    while True:
        i = low.find(w, i)
        if i == -1:
            return None
        before_ok = i == 0 or not (
            sql[i - 1].isalnum() or sql[i - 1] == "_")
        j = i + len(w)
        after_ok = j >= n or not (sql[j].isalnum() or sql[j] == "_")
        if before_ok and after_ok:
            return i
        i += 1


def parse_table_checks(sql: str) -> list:
    """IR-01: parse EVERY table-level CHECK occurrence into a complete
    ordered multiset ``[(name_or_none, normalized_expression), ...]``.

    CONSTRAINT/CHECK are matched case-insensitively; anonymous CHECKs
    are captured with name ``None``; duplicate constraint names are
    preserved; malformed/truncated CHECK syntax fails closed; nested
    parentheses and quoted strings inside repository-generated
    expressions are balanced correctly; a named CONSTRAINT clause of
    an unrecognized non-CHECK kind is rejected instead of silently
    skipped."""
    checks: list = []
    pending_name = None
    i = 0
    while True:
        c = _find_word(sql, "constraint", i)
        k = _find_word(sql, "check", i)
        if c is not None and (k is None or c < k):
            j = c + len("constraint")
            while j < len(sql) and sql[j].isspace():
                j += 1
            e = j
            while e < len(sql) and (sql[e].isalnum() or sql[e] == "_"):
                e += 1
            if e == j:
                raise _corrupt(
                    "malformed CONSTRAINT clause in stored DDL")
            name = sql[j:e]
            p = e
            while p < len(sql) and sql[p].isspace():
                p += 1
            if _find_word(sql, "check", p) == p:
                pending_name = name
                i = p
            else:
                firsts = [x for x in (
                    _find_word(sql, "foreign", p),
                    _find_word(sql, "primary", p),
                    _find_word(sql, "unique", p)) if x is not None]
                if not firsts or min(firsts) != p:
                    raise _corrupt(
                        "unsupported table-level CONSTRAINT syntax in "
                        "stored DDL")
                pending_name = None
                i = p
            continue
        if k is None:
            return checks
        p = k + len("check")
        while p < len(sql) and sql[p].isspace():
            p += 1
        if p >= len(sql) or sql[p] != "(":
            raise _corrupt("malformed CHECK syntax in stored DDL")
        depth = 0
        in_string = False
        j = p
        while j < len(sql):
            ch = sql[j]
            if in_string:
                if ch == "'":
                    in_string = False
            elif ch == "'":
                in_string = True
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(sql) or in_string:
            raise _corrupt(
                "unbalanced or unterminated CHECK expression in "
                "stored DDL")
        checks.append((pending_name,
                       " ".join(sql[p + 1:j].split())))
        pending_name = None
        i = j + 1


def _verify_table_schema(con: sqlite3.Connection, table: str,
                         contract: dict) -> None:
    """IR-01/IR-02: prove the EXACT stored physical schema of one
    migration-owned table — declared column names/types/nullability/PK
    ordinals; the COMPLETE FK row multiset (seq, target table, source
    column, target column, ON UPDATE, ON DELETE, MATCH — multiplicity
    preserved, duplicate/conflicting rows cannot collapse); the
    COMPLETE ordered CHECK multiset of stored-name + normalized
    expression pairs (anonymous/lowercase/duplicate/right-name-wrong-
    expression CHECKs all diverge); and the closed explicit-index
    inventory (SQLite autoindexes implied by PK/UNIQUE constraints are
    lawful and never rejected merely for existing)."""
    cols = {r[1]: (r[2], r[3], r[5]) for r in con.execute(
        f"PRAGMA table_info({table})")}
    if cols != contract["columns"]:
        raise _corrupt(
            f"{table} column contract diverges: expected "
            f"{sorted(contract['columns'].items())}, got "
            f"{sorted(cols.items())}")
    fks = sorted((r[1], r[2], r[3], r[4], r[5], r[6], r[7])
                 for r in con.execute(f"PRAGMA foreign_key_list({table})"))
    if fks != contract["fks"]:
        raise _corrupt(
            f"{table} foreign-key contract diverges: expected "
            f"{contract['fks']}, got {fks}")
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' "
        f"AND name = '{table}'").fetchone()
    if row is None:
        raise _corrupt(f"{table} missing from sqlite_master DDL")
    checks = parse_table_checks(row[0])
    if checks != contract["checks"]:
        raise _corrupt(
            f"{table} CHECK-contract diverges: expected "
            f"{contract['checks']}, got {checks}")
    explicit = {r[1]: (r[2], r[3], r[4]) for r in con.execute(
        f"PRAGMA index_list({table})") if r[3] == "c"}
    if explicit != contract["explicit_indexes"]:
        raise _corrupt(
            f"{table} explicit-index contract diverges: expected "
            f"{contract['explicit_indexes']}, got {explicit}")
    # RR15-M17CC-02: when the contract carries explicit-index column
    # sequences, each named index must index EXACTLY those columns in
    # order — the (unique, origin, partial) tuple above proves only
    # the index's name and flags, so a same-name same-flags index
    # rebuilt over a different column would otherwise certify. The
    # key is optional: contracts that omit it (the frozen predecessor
    # PF-03/PF-02 surfaces, whose own wrapper performs the equivalent
    # check where required) keep byte-identical behavior.
    for name, expected_cols in contract.get(
            "index_columns", {}).items():
        cols = [r[2] for r in con.execute(
            f"PRAGMA index_info({name})")]
        if cols != expected_cols:
            raise _corrupt(
                f"{table} explicit index {name!r} does not index "
                f"exactly {expected_cols!r} (got {cols!r})")
    # IND-02: classify EVERY remaining autoindex by origin. 'pk'
    # entries are lawful ONLY as the exact consequence of the frozen
    # PK — each must index exactly the frozen PK columns in order.
    # 'u' entries are UNIQUE-constraint consequences; the frozen
    # 0020/0021 migrations declare NO additional UNIQUE constraints,
    # so ANY origin-'u' index (anonymous UNIQUE(column) or a named
    # CONSTRAINT ... UNIQUE) refuses — arbitrary autoindexes are never
    # treated as benign.
    pk_autoindexes = []
    unique_autoindexes = []
    for r in con.execute(f"PRAGMA index_list({table})"):
        if r[3] == "pk":
            pk_autoindexes.append(r[1])
        elif r[3] == "u":
            unique_autoindexes.append(r[1])
    for name in pk_autoindexes:
        cols = [row[2] for row in con.execute(
            f"PRAGMA index_info({name})")]
        if cols != contract["pk_columns"]:
            raise _corrupt(
                f"{table} PK autoindex {name!r} does not index exactly "
                f"the frozen PK columns {contract['pk_columns']!r} "
                f"(got {cols!r})")
    if unique_autoindexes:
        raise _corrupt(
            f"{table} carries unexpected UNIQUE-constraint autoindexes "
            f"{unique_autoindexes!r} — the frozen migrations declare "
            "no UNIQUE constraints beyond the primary key")


def _verify_spsm_schema(con: sqlite3.Connection) -> None:
    """IR-01: the full working-mapping table contract — exact columns,
    exact FK multiset, exact ordered CHECK multiset, and the closed
    explicit-index inventory: exactly one migration-owned index,
    ix_spsm_pr, a non-unique, non-partial CREATE INDEX over exactly
    performance_revision_id."""
    _verify_table_schema(con, _SHOT_MAPPING_TABLE, _SPSM_CONTRACT)
    ix_cols = [r[2] for r in con.execute("PRAGMA index_info(ix_spsm_pr)")]
    if ix_cols != ["performance_revision_id"]:
        raise _corrupt(
            "ix_spsm_pr does not index exactly performance_revision_id")


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
    optional table presence.

    At head 0022 (M17C-C) the three schema-8 capture tables are
    REQUIRED, and the §13.4/§13.6 M17C-C recovery passes run on top
    of the unchanged PF-03/PF-02 laws: the captured-schema-8 laws
    (total snapshot classification, snapshot↔parent↔children
    equivalence, immutable authority closure, exact rational
    arithmetic, historical project/subject coherence, and the captured
    same-subject channel-conflict law) plus the structural
    Generation-owned derived-input laws. Recovery re-derives every law
    from the STAGED ROWS + immutable authority + retained Blob
    closure — it never delegates to the §12 historical reader and
    never consults current working state. At heads 0020/0021 the rows
    those heads cannot represent are REFUSED: any companion or
    derived-input row refuses.

    §13.6 deferral (frozen scope): the control-schedule recomputation
    and the sample-exact vocal-audio realization laws require the
    M17C-D §14.6 sampler; this pass proves the structural/tieback/
    rehash/identity laws constructible today."""
    if blob_root is None:
        from soloring.settings import get_settings
        blob_root = get_settings().blob_dir
    if head not in (_HEAD_0020, _HEAD_0021, _HEAD_0022, _HEAD_0023):
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
                    f"staged head {head!r} is missing the PF-02 "
                    "working-mapping table")
        if head in (_HEAD_0022, _HEAD_0023):
            # §13.4: head behavior stays explicit — the successor
            # migration physically creates the three capture tables, so
            # a 0022+ database without them is structurally corrupt
            missing = [t for t in _M17CC_TABLES if t not in present]
            if missing:
                raise _corrupt(
                    f"staged head 0022 is missing the M17C-C capture "
                    f"tables {missing}")
            if head == _HEAD_0022 and con.execute(
                    "SELECT 1 FROM "
                    "shot_revision_performance_segments LIMIT 1"
                    ).fetchone():
                # FPR-M17CC-04: preimage-less captured rows cannot
                # certify their mapping-hash closure — refuse rather
                # than silently skipping the anchor law
                raise _corrupt(
                    "staged head 0022 carries schema-8 companion "
                    "children captured without the closure preimage — "
                    "upgrade to 0023 to certify the captured closure")
        else:
            # §13.4 total classification at the predecessor heads: rows
            # those heads cannot represent are refused, not ignored
            # (the tables themselves may lawfully be present as
            # create_all staging artifacts)
            for table in _M17CC_TABLES:
                if table in present and con.execute(
                        f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                    raise _corrupt(
                        f"staged head {head!r} carries {table} rows — "
                        "schema-8 capture companions are created by "
                        "successor migration 0022 only")
        # IR-01/IR-02: the COMPLETE physical-schema phase runs BEFORE
        # any semantic row traversal — head 0021 inherits the frozen
        # 0020 PF-03 schemas physically and must not weaken their
        # certification. A structurally damaged table surfaces as the
        # recovery-corruption contract, never a raw sqlite3 error.
        try:
            for table, contract in _PF03_CONTRACTS.items():
                _verify_table_schema(con, table, contract)
            if head != _HEAD_0020:
                _verify_spsm_schema(con)
            if head in (_HEAD_0022, _HEAD_0023):
                # ISR2-M17CC-02: the successor tables' PHYSICAL
                # contracts — the same _verify_table_schema machinery
                # the predecessor tables already use, proven BEFORE
                # any semantic row traversal. A staged successor-head
                # database whose CHECKs/FKs/indexes/PK shape were
                # weakened (even with EMPTY tables, where quick_check,
                # foreign_key_check, presence, and row semantics all
                # stay green) refuses at the physical boundary.
                for table, contract in \
                        _M17CC_TABLE_CONTRACTS[head].items():
                    _verify_table_schema(con, table, contract)
        except sqlite3.Error as exc:
            raise _corrupt(
                f"physical schema verification failed structurally on "
                f"the staged M17C tables: {exc}") from exc
        _verify_classifications(con)
        _verify_candidate_bindings(con, blob_root)
        _verify_revision_bindings(con)
        _verify_retarget_lineage(con)
        if head != _HEAD_0020:
            _verify_shot_performance_mappings(con)
        if head in (_HEAD_0022, _HEAD_0023):
            # §13.4/§13.6 (M17C-C): AFTER every predecessor pass — the
            # captured-schema-8 laws extend the chain, they do not
            # replace it
            _verify_m17cc_capture_state(con, blob_root)
            _verify_generation_performance_inputs(con, blob_root)
    finally:
        con.close()


def _canonical(obj) -> str:
    from soloring.domain.canonical import canonical_json_str
    return canonical_json_str(obj)


def _hash(obj) -> str:
    from soloring.domain.canonical import canonical_hash
    return canonical_hash(obj)


def _check_rational(num, den, what: str) -> None:
    # RR9-M17CC-01: total over SQLite storage classes — a non-integral
    # REAL numerator or denominator (INTEGER affinity admits REALs)
    # fails HERE as typed corruption, never as a raw TypeError from
    # math.gcd. Binding rows reach this only after the shared
    # structural law already certified their origin; the captured-child
    # rationals are certified on their own before their arithmetic.
    if isinstance(num, bool) or not isinstance(num, int) \
            or isinstance(den, bool) or not isinstance(den, int):
        raise _corrupt(f"{what} rational {num!r}/{den!r} is not a "
                       "persisted integer pair (non-integral SQLite "
                       "storage class)")
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
    # RR9-M17CC-01: the structural binding law is the ONE shared
    # transport-neutral verifier — the same function the live PF-03
    # seam and §12 enforce (schema/basis versions, the TOTAL
    # storage-class certification of the sample scalars, the
    # canonical-reduced origin, the exact canonical bytes/hash). It
    # REPLACES this verifier's local grammar (its schema check, its
    # _check_rational/math.gcd origin pass, and its doc
    # reconstruction) so the two definitions cannot drift and no
    # unchecked arithmetic below can ever receive a malformed storage
    # class: a storage-valid non-integral REAL coordinate or REAL
    # origin fails HERE as typed corruption, never as a raw
    # TypeError from math.gcd/Fraction.
    from soloring.performance.m17c_binding import (
        BindingStructuralError, verify_stored_vocal_binding,
    )
    try:
        verify_stored_vocal_binding(
            binding_schema_version=row["binding_schema_version"],
            synchronization_basis_version=(
                row["synchronization_basis_version"]),
            vocal_performance_revision_id=(
                row["vocal_performance_revision_id"]),
            source_start_sample=row["source_start_sample"],
            source_end_sample_exclusive=(
                row["source_end_sample_exclusive"]),
            sample_rate_hz=row["sample_rate_hz"],
            performance_origin_num=row["performance_origin_num"],
            performance_origin_den=row["performance_origin_den"],
            binding_json=row["binding_json"],
            binding_hash=row["binding_hash"])
    except BindingStructuralError as exc:
        raise _corrupt(
            f"{what} {parent['id']!r} binding fails its own canonical "
            f"structural law: {exc.reason}") from exc

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
    """frozen R4 §13.3 + IR-02: the STORED structural laws of every
    working mapping row run through the ONE transport-neutral shared
    law (``verify_persisted_mapping_structural`` — the same law the
    live readiness/list path runs); recovery additionally and
    independently proves the referenced PerformanceRevision and Shot
    exist and agree on project. Current VP selection, paired vocal
    mapping existence/VP identity, and current Shot duration/picture
    are working-readiness concerns and deliberately NOT certified
    here."""
    from soloring.performance.m17c_shot_mapping import (
        verify_persisted_mapping_structural,
    )
    for row in con.execute(
            "SELECT * FROM shot_performance_segment_mappings"):
        pr = con.execute(
            "SELECT * FROM performance_revisions WHERE id = ?",
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
        cls = con.execute(
            "SELECT sync_mode FROM "
            "performance_revision_sync_classifications "
            "WHERE performance_revision_id = ?",
            (row["performance_revision_id"],)).fetchone()
        # IR-02: the shared persisted law — structural rows through the
        # SAME verifier the live path uses (transport-neutral). The
        # historical corruption contract of the shared law is the
        # recovery-corruption family by construction.
        try:
            verify_persisted_mapping_structural(
                shot_id=row["shot_id"],
                position=row["position"],
                performance_revision_id=row["performance_revision_id"],
                mapping_schema_version=row["mapping_schema_version"],
                performance_start_num=row["performance_start_num"],
                performance_start_den=row["performance_start_den"],
                performance_end_num=row["performance_end_num"],
                performance_end_den=row["performance_end_den"],
                shot_anchor_num=row["shot_anchor_num"],
                shot_anchor_den=row["shot_anchor_den"],
                vocal_mapping_position=row["vocal_mapping_position"],
                mapping_json=row["mapping_json"],
                mapping_hash=row["mapping_hash"],
                domain_start_num=pr["temporal_start_num"],
                domain_start_den=pr["temporal_start_den"],
                domain_end_num=pr["temporal_end_num"],
                domain_end_den=pr["temporal_end_den"],
                expected_mode=(cls["sync_mode"] if cls is not None
                               else "NONE"))
        except SoloRingError as exc:
            raise _corrupt(f"IR-02 shared persisted mapping law: "
                           f"{exc.message}") from exc
        # B-F3/SR2-03 pairing preservation: a MISSING paired vocal
        # mapping is an API-creatable lawful BLOCKED working state
        # (supported DELETE; readiness reports BLOCKED_BINDING_INTEGRITY);
        # so is a paired vocal mapping whose VP was REPOINTED through
        # the supported M17A PUT to the now-current selection — mutable
        # working drift against the immutable revision binding, never
        # rewritten by diagnosis and never refused here. Other
        # structural corruption of the vocal row stays the M17A
        # verifier's concern.


# ---------------------------------------------------------------------------
# M17C-C (frozen R4 §13.4/§13.6): captured schema-8 + derived-input laws.
# Recovery re-derives every law from the staged rows + immutable
# authority + retained Blob closure. It never calls the §12 historical
# reader (the two surfaces agree because they implement the same frozen
# laws, not because one delegates) and never consults current working
# state — no VP selection, no current vocal/performance mappings, no
# candidates as working intent, no current Shot dependency selection,
# no current Shot duration.
# ---------------------------------------------------------------------------

_M17CC_TABLES = (
    "shot_revision_performance_specs",
    "shot_revision_performance_segments",
    "generation_performance_inputs",
)

_M17CC_CHILD_COLUMNS = (
    "position, subject_id, performance_revision_id, "
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


def _verify_m17cc_capture_state(con: sqlite3.Connection,
                                blob_root: Path) -> None:
    """§13.4: total snapshot classification + the captured-schema-8
    equivalence/closure/arithmetic/coherence/conflict laws.

    Memory law: the traversal STREAMS — phase 1 retains only each
    revision's (shot_id, schema) after decoding (scale databases carry
    thousands of multi-MB snapshots; holding the decoded documents
    would exhaust memory), and phase 2 re-decodes ONLY the schema-8
    snapshots the closure laws need."""
    classified = {}
    schema8_ids = []
    for row in con.execute(
            "SELECT id, shot_id, snapshot_json, snapshot_hash "
            "FROM shot_revisions"):
        try:
            snap = json.loads(row["snapshot_json"])
        except (ValueError, TypeError) as exc:
            raise _corrupt(
                f"ShotRevision {row['id']} snapshot_json is not "
                f"decodable: {exc}") from exc
        if not isinstance(snap, dict):
            raise _corrupt(
                f"ShotRevision {row['id']} snapshot is not a JSON "
                "object")
        # RR15-M17CC-01: EVERY envelope is authenticated BEFORE its
        # schema discriminator is trusted for classification — the
        # persisted bytes must BE the canonical serialization of the
        # decoded snapshot and snapshot_hash its canonical digest
        # (ISR2-01 proved this pair for revisions already classified
        # schema 8; a discriminator corrupted DOWNWARD must not exempt
        # its own document from the same authentication). This is the
        # successor-head M17C-C verifier law; restoring an actual
        # pre-0022 alembic head is a different, unchanged concern.
        if _canonical(snap) != row["snapshot_json"]:
            raise _corrupt(
                f"ShotRevision {row['id']} snapshot_json is not the "
                "canonical serialization of its decoded snapshot")
        if _hash(snap) != row["snapshot_hash"]:
            raise _corrupt(
                f"ShotRevision {row['id']} snapshot_hash does not "
                "authenticate its snapshot bytes")
        schema = snap.get("schema_version")
        classified[row["id"]] = (row["shot_id"], schema)
        if schema == 8:
            schema8_ids.append((row["id"], row["shot_id"]))

    # total classification: every revision is either schema <8 with
    # ZERO M17C-C companions, or schema 8 with the full closure. No
    # "companions ignored because the snapshot is old" and no "schema
    # 8 accepted without companions".
    for rev_id, (shot_id, schema) in classified.items():
        if not isinstance(schema, int) or isinstance(schema, bool) \
                or not 1 <= schema <= 8:
            raise _corrupt(
                f"ShotRevision {rev_id} carries illegal snapshot "
                f"schema_version {schema!r}")
        companions = con.execute(
            "SELECT COUNT(*) FROM shot_revision_performance_specs "
            "WHERE shot_revision_id = ?", (rev_id,)).fetchone()[0]
        children = con.execute(
            "SELECT COUNT(*) FROM shot_revision_performance_segments "
            "WHERE shot_revision_id = ?", (rev_id,)).fetchone()[0]
        if schema < 8:
            if companions or children:
                raise _corrupt(
                    f"ShotRevision {rev_id} carries schema {schema} "
                    "with M17C-C companion rows — schema <8 captures "
                    "write zero companions")
        else:
            if not companions:
                raise _corrupt(
                    f"ShotRevision {rev_id} is schema 8 without its "
                    "performance companion parent")

    # orphan sweep: companions reference known revisions (FK-shielded
    # live; the law stands as the recovery parity mirror)
    for table in ("shot_revision_performance_specs",
                  "shot_revision_performance_segments"):
        for (rev_id,) in con.execute(
                f"SELECT DISTINCT shot_revision_id FROM {table}"):
            if rev_id not in classified:
                raise _corrupt(
                    f"{table} references missing ShotRevision "
                    f"{rev_id!r}")

    for rev_id, shot_id in schema8_ids:
        # RR15-M17CC-01: every envelope was already authenticated in
        # the classification pass above (canonical bytes + hash,
        # BEFORE the discriminator was trusted) — the schema-8 closure
        # walk only re-decodes
        snap = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (rev_id,)).fetchone()[0])
        _verify_one_schema8(con, blob_root, rev_id, shot_id, snap)


def _m17cc_embedded_grammar(perf, rev_id: str) -> list:
    from soloring.performance.m17cc_capture_read import (
        EMBEDDED_SEGMENT_KEYS, is_actual_int_schema,
        performance_block_key_error,
    )
    # RR-M17CC-03: grammar v2 — the mapping hashes + preimage are
    # snapshot-anchored. Grammar v1 (0023-era companion-only preimage)
    # is REFUSED, never silently certified.
    if isinstance(perf, dict) and perf.get("schema_version") == 1:
        raise _corrupt(
            f"ShotRevision {rev_id} carries a grammar-v1 performance "
            "block captured before the mapping-hash anchor existed — "
            "re-capture at the corrected head")
    # RR12-M17CC-02: the discriminator must be an ACTUAL non-bool
    # integer exactly 2 — ordinary numeric equality admits JSON 2.0,
    # a value the canonical writer cannot emit
    if not isinstance(perf, dict) or not is_actual_int_schema(
            perf.get("schema_version"), 2):
        raise _corrupt(
            f"ShotRevision {rev_id} performance history declares "
            f"unknown schema {perf!r}")
    # RR13-M17CC-01: the TOP-LEVEL key grammar — the ONE shared law,
    # after the discriminator/v1 refusal so every existing diagnostic
    # stays distinguishable
    key_error = performance_block_key_error(perf)
    if key_error is not None:
        raise _corrupt(
            f"ShotRevision {rev_id} performance history {key_error}.")
    segments = perf.get("segments")
    if not isinstance(segments, list) or not segments:
        raise _corrupt(
            f"ShotRevision {rev_id} performance history carries an "
            "empty segment list — no empty schema 8 exists")
    for index, seg in enumerate(segments):
        if not isinstance(seg, dict) or set(seg) != set(
                EMBEDDED_SEGMENT_KEYS):
            raise _corrupt(
                f"ShotRevision {rev_id} performance history segment "
                f"{index} is not the exact frozen key projection")
        if seg["position"] != index:
            raise _corrupt(
                f"ShotRevision {rev_id} performance history segment "
                f"{index} declares position {seg['position']!r}")
        vocal = seg["vocal"]
        if vocal is not None and (not isinstance(vocal, dict) or
                                  set(vocal) != {
                                      "vocal_performance_revision_id",
                                      "vocal_binding_hash",
                                      "source_start_sample",
                                      "source_end_sample_exclusive",
                                      "sample_rate_hz"}):
            raise _corrupt(
                f"ShotRevision {rev_id} performance history segment "
                f"{index} carries a vocal object outside the closed "
                "5-key grammar")
    return segments


def _verify_one_schema8(con: sqlite3.Connection, blob_root: Path,
                        rev_id: str, shot_id: str, snap: dict) -> None:
    where = f"ShotRevision {rev_id}"
    # §13.4 snapshot↔parent equivalence: the embedded block reproduces
    # the canonical parent bytes EXACTLY (no semantic-equivalence
    # shortcut) and the canonical bytes reproduce the hash
    parent = con.execute(
        "SELECT schema_version, spec_json, spec_hash FROM "
        "shot_revision_performance_specs WHERE shot_revision_id = ?",
        (rev_id,)).fetchall()
    if len(parent) != 1:
        raise _corrupt(
            f"{where} requires exactly one performance companion "
            f"parent, found {len(parent)}")
    parent = parent[0]
    if parent["schema_version"] != 1:
        raise _corrupt(
            f"{where} performance companion parent carries unknown "
            f"schema {parent['schema_version']!r}")
    try:
        spec = json.loads(parent["spec_json"])
    except (ValueError, TypeError) as exc:
        raise _corrupt(
            f"{where} performance companion spec_json is malformed "
            f"JSON: {exc}") from exc
    if _canonical(spec) != parent["spec_json"] \
            or _hash(spec) != parent["spec_hash"]:
        raise _corrupt(
            f"{where} performance companion spec_json/spec_hash "
            "disagree with canonical bytes")
    embedded = snap.get("performance")
    if not isinstance(embedded, dict):
        raise _corrupt(
            f"{where} schema-8 snapshot carries no performance block")
    if _canonical(embedded) != parent["spec_json"]:
        raise _corrupt(
            f"{where} snapshot performance block bytes disagree with "
            "its companion parent spec bytes")
    segments = _m17cc_embedded_grammar(spec, rev_id)

    # §13.4 parent↔children equivalence: count, position, canonical
    # segment bytes/hash, every projection column, rational fields,
    # and vocal-group nullability project exactly from the embedded
    # grammar (the recovery form of the slice-3 persistence invariant)
    children = con.execute(
        "SELECT " + _M17CC_CHILD_COLUMNS +
        " FROM shot_revision_performance_segments "
        "WHERE shot_revision_id = ? ORDER BY position",
        (rev_id,)).fetchall()
    if not children:
        raise _corrupt(
            f"{where} is schema 8 with an empty companion child set")
    if len(children) != len(segments):
        raise _corrupt(
            f"{where} performance companion row count disagrees: "
            f"stored {len(children)}, captured {len(segments)}")

    verified = []
    for row, seg in zip(children, segments):
        verified.append(_verify_m17cc_child(
            con, blob_root, rev_id, shot_id, row, seg))
    _verify_m17cc_captured_conflicts(rev_id, verified)


def _verify_m17cc_child(con, blob_root, rev_id, shot_id, row, seg):
    import hashlib
    from soloring.performance.m17cc_capture_read import (
        captured_vocal_preimage_error, embedded_rational_shape_error,
        exact_projection_equal,
    )
    where = (f"ShotRevision {rev_id} performance companion child at "
             f"position {row['position']}")
    # RR-M17CC-03 (residual): the nested rational objects are
    # SHAPE-VALIDATED before ANY ["num"]/["den"] access below —
    # malformed embedded JSON terminates as typed RECOVERY_CORRUPTION,
    # never a raw TypeError/KeyError
    shape_error = embedded_rational_shape_error(seg)
    if shape_error is not None:
        raise _corrupt(
            f"{where} carries a malformed nested captured value: "
            f"{shape_error}")
    # RR12-M17CC-01: the persisted scalar law of the captured vocal
    # preimage — certified BEFORE the preimage is hashed (the
    # mapping-hash closure below) or used in exact §8.3 arithmetic
    preimage_error = captured_vocal_preimage_error(row)
    if preimage_error is not None:
        raise _corrupt(
            f"{where} captured vocal preimage violates its persisted "
            f"scalar law: {preimage_error}")
    # SR-M17CC-03: TYPE-EXACT — a JSON false/true/float embedded
    # value that Python-compares equal to the relational integer is
    # not the mechanical projection the captured grammar requires
    if not exact_projection_equal(row["position"], seg["position"]):
        raise _corrupt(
            f"{where} disagrees with the embedded captured ordering")
    if row["segment_json"] != _canonical(seg) \
            or row["segment_hash"] != _hash(seg):
        raise _corrupt(
            f"{where} segment_json/segment_hash disagree with the "
            "canonical embedded segment")
    vocal = seg["vocal"]
    for column, want in (
        ("subject_id", seg["subject_id"]),
        ("performance_revision_id", seg["performance_revision_id"]),
        ("performance_payload_sha256",
         seg["performance_payload_sha256"]),
        ("performance_profile_id", seg["performance_profile_id"]),
        ("performance_kind", seg["performance_kind"]),
        ("performance_start_num", seg["performance_start_ms"]["num"]),
        ("performance_start_den", seg["performance_start_ms"]["den"]),
        ("performance_end_num", seg["performance_end_ms"]["num"]),
        ("performance_end_den", seg["performance_end_ms"]["den"]),
        ("shot_anchor_num", seg["shot_anchor_ms"]["num"]),
        ("shot_anchor_den", seg["shot_anchor_ms"]["den"]),
        ("performance_mapping_hash",
         seg["performance_mapping_hash"]),
        ("vocal_mapping_hash", seg["vocal_mapping_hash"]),
        ("vocal_mapping_position", seg["vocal_mapping_position"]),
    ):
        if not exact_projection_equal(row[column], want):
            raise _corrupt(
                f"{where} column {column} disagrees with the embedded "
                "captured segment")
    for column, key in (
        ("vocal_performance_revision_id",
         "vocal_performance_revision_id"),
        ("vocal_binding_hash", "vocal_binding_hash"),
        ("source_start_sample", "source_start_sample"),
        ("source_end_sample_exclusive",
         "source_end_sample_exclusive"),
        ("sample_rate_hz", "sample_rate_hz"),
    ):
        captured = vocal[key] if vocal is not None else None
        if not exact_projection_equal(row[column], captured):
            raise _corrupt(
                f"{where} vocal-group column {column} disagrees with "
                "the embedded captured vocal grammar (all-or-none)")

    # FPR-M17CC-04: the captured mapping-document preimage ANCHOR —
    # both stored mapping hashes recompute as pure functions of the
    # child row itself (never a current working-mapping read)
    from soloring.performance.m17cc_capture_read import (
        _child_preimage_vocal, expected_mapping_hashes,
    )
    try:
        preimage_vocal = _child_preimage_vocal(row)
    except ValueError as exc:
        raise _corrupt(
            f"{where} carries an incoherent vocal-group preimage: "
            f"{exc}") from exc
    if (row["vocal_mapping_position"] is None) != (preimage_vocal
                                                   is None):
        raise _corrupt(
            f"{where} vocal_mapping_position preimage disagrees with "
            "the all-or-none vocal group")
    expected_perf_hash, expected_vocal_hash = expected_mapping_hashes(
        row["performance_revision_id"],
        {"num": row["performance_start_num"],
         "den": row["performance_start_den"]},
        {"num": row["performance_end_num"],
         "den": row["performance_end_den"]},
        {"num": row["shot_anchor_num"],
         "den": row["shot_anchor_den"]},
        row["vocal_mapping_position"], preimage_vocal)
    if row["performance_mapping_hash"] != expected_perf_hash:
        raise _corrupt(
            f"{where} performance_mapping_hash disagrees with its "
            "captured mapping-document preimage")
    if row["vocal_mapping_hash"] != expected_vocal_hash:
        raise _corrupt(
            f"{where} vocal_mapping_hash disagrees with its captured "
            "mapping-document preimage")
    # RR-M17CC-03: the SNAPSHOT-ANCHORED comparison — the embedded
    # segment (covered by segment_hash -> parent spec_hash ->
    # snapshot identity) is the independent authority a coherent
    # child-side preimage+hash rewrite cannot satisfy
    if row["performance_mapping_hash"] != seg[
            "performance_mapping_hash"]:
        raise _corrupt(
            f"{where} performance_mapping_hash disagrees with the "
            "snapshot-anchored embedded segment")
    if row["vocal_mapping_hash"] != seg["vocal_mapping_hash"]:
        raise _corrupt(
            f"{where} vocal_mapping_hash disagrees with the "
            "snapshot-anchored embedded segment")
    if row["vocal_mapping_position"] != seg[
            "vocal_mapping_position"]:
        raise _corrupt(
            f"{where} vocal_mapping_position preimage disagrees with "
            "the snapshot-anchored embedded segment")
    embedded_origin = seg["vocal_performance_origin_ms"]
    if embedded_origin is None:
        if (row["vocal_performance_origin_num"] is not None
                or row["vocal_performance_origin_den"] is not None):
            raise _corrupt(
                f"{where} vocal performance-origin preimage disagrees "
                "with the snapshot-anchored embedded segment")
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
        raise _corrupt(
            f"{where} vocal performance-origin preimage disagrees with "
            "the snapshot-anchored embedded segment")

    # §13.4 exact arithmetic (recomputed, never trusted from text):
    # canonical rationals and a non-empty interval
    start = _m17cc_rational(row["performance_start_num"],
                            row["performance_start_den"],
                            f"{where} performance_start")
    end = _m17cc_rational(row["performance_end_num"],
                          row["performance_end_den"],
                          f"{where} performance_end")
    _m17cc_rational(row["shot_anchor_num"], row["shot_anchor_den"],
                    f"{where} shot_anchor")
    if start >= end:
        raise _corrupt(f"{where} captured interval is empty/inverted")

    pr = con.execute(
        "SELECT subject_id, project_id, performance_kind, "
        "performance_profile_id, temporal_start_num, "
        "temporal_start_den, temporal_end_num, temporal_end_den, "
        "canonical_channel_payload_sha256, "
        "canonical_channel_payload_blob_hash "
        "FROM performance_revisions WHERE id = ?",
        (row["performance_revision_id"],)).fetchone()
    if pr is None:
        raise _corrupt(
            f"{where} references a missing immutable "
            f"PerformanceRevision {row['performance_revision_id']!r}")
    if (pr["subject_id"] != row["subject_id"]
            or pr["performance_kind"] != row["performance_kind"]
            or pr["performance_profile_id"]
            != row["performance_profile_id"]
            or pr["canonical_channel_payload_sha256"]
            != row["performance_payload_sha256"]
            or pr["canonical_channel_payload_blob_hash"]
            != row["performance_payload_blob_hash"]):
        raise _corrupt(
            f"{where} disagrees with the immutable PerformanceRevision "
            f"{row['performance_revision_id']!r} it names")
    domain_start = _m17cc_rational(
        pr["temporal_start_num"], pr["temporal_start_den"],
        f"{where} PR temporal_start")
    domain_end = _m17cc_rational(
        pr["temporal_end_num"], pr["temporal_end_den"],
        f"{where} PR temporal_end")

    # §13.4 historical project/subject coherence (immutable + captured
    # identities only — never current dependency selection)
    shot = con.execute(
        "SELECT project_id FROM shots WHERE id = ?",
        (shot_id,)).fetchone()
    if shot is None:
        raise _corrupt(
            f"{where} belongs to a missing Shot {shot_id!r}")
    if pr["project_id"] != shot["project_id"]:
        raise _corrupt(
            f"{where} crosses projects: PR project "
            f"{pr['project_id']!r} != Shot project "
            f"{shot['project_id']!r}")

    info = {
        "subject_id": row["subject_id"],
        "start": start, "end": end,
        "channels": None,
    }

    # the retained payload Blob closure rehashes and parses as the
    # channel document the captured history is built from
    blob_hash = row["performance_payload_blob_hash"]
    blob_path = blob_root / "sha256" / blob_hash[:2] / \
        blob_hash[2:4] / blob_hash
    if not blob_path.is_file():
        raise _corrupt(
            f"{where} names a payload blob absent from the retained "
            "Blob closure")
    data = blob_path.read_bytes()
    if hashlib.sha256(data).hexdigest() != blob_hash:
        raise _corrupt(
            f"{where} retained payload blob does not rehash")
    info["channels"] = _m17cc_payload_channels(data, where)

    if vocal is None:
        # generic §8.2 law: the captured interval lies inside the
        # immutable PR temporal domain
        if not (domain_start <= start and end <= domain_end):
            raise _corrupt(
                f"{where} captured interval lies outside the immutable "
                f"PerformanceRevision domain [{domain_start}, "
                f"{domain_end})")
        return info

    # dialogue-bound §8.3 laws, recomputed exactly through the
    # immutable synchronization binding: identity/hash agreement, the
    # captured sample interval inside the binding interval and the VP
    # trim, and the EXACT induced performance interval (origin +
    # sample/rate arithmetic — no tolerance, no float conversion)
    binding = con.execute(
        "SELECT vocal_performance_revision_id, binding_hash, "
        "source_start_sample, source_end_sample_exclusive, "
        "sample_rate_hz, performance_origin_num, "
        "performance_origin_den FROM "
        "performance_revision_vocal_bindings "
        "WHERE performance_revision_id = ?",
        (row["performance_revision_id"],)).fetchone()
    if binding is None:
        raise _corrupt(
            f"{where} is dialogue-bound but its immutable "
            "synchronization binding is gone")
    if (binding["binding_hash"] != row["vocal_binding_hash"]
            or binding["vocal_performance_revision_id"]
            != row["vocal_performance_revision_id"]
            or binding["sample_rate_hz"] != row["sample_rate_hz"]):
        raise _corrupt(
            f"{where} captured vocal closure disagrees with the "
            "immutable synchronization binding")
    vp = con.execute(
        "SELECT speaker_subject_id, trim_start_sample, "
        "trim_end_sample_exclusive, dialogue_line_revision_id "
        "FROM vocal_performance_revisions WHERE id = ?",
        (row["vocal_performance_revision_id"],)).fetchone()
    if vp is None:
        raise _corrupt(
            f"{where} names a missing immutable "
            f"VocalPerformanceRevision "
            f"{row['vocal_performance_revision_id']!r}")
    if vp["speaker_subject_id"] != row["subject_id"]:
        raise _corrupt(
            f"{where} subject disagrees with the VP speaker "
            f"({vp['speaker_subject_id']!r}) — subject/speaker "
            "agreement is historical")
    line = con.execute(
        "SELECT project_id FROM dialogue_lines WHERE id = ("
        "SELECT dialogue_line_id FROM dialogue_line_revisions "
        "WHERE id = ?)",
        (vp["dialogue_line_revision_id"],)).fetchone()
    if line is None or line["project_id"] != shot["project_id"]:
        raise _corrupt(
            f"{where} VP lineage crosses projects")
    origin = _m17cc_rational(
        binding["performance_origin_num"],
        binding["performance_origin_den"],
        f"{where} binding performance_origin")
    rate = row["sample_rate_hz"]
    s0 = binding["source_start_sample"]
    p0 = origin + Fraction(
        (row["source_start_sample"] - s0) * 1000, rate)
    p1 = origin + Fraction(
        (row["source_end_sample_exclusive"] - s0) * 1000, rate)
    if start != p0 or end != p1:
        raise _corrupt(
            f"{where} captured interval [{start}, {end}) != the exact "
            f"binding-induced interval [{p0}, {p1})")
    if not (binding["source_start_sample"] <= row["source_start_sample"]
            and row["source_end_sample_exclusive"]
            <= binding["source_end_sample_exclusive"]):
        raise _corrupt(
            f"{where} captured sample interval lies outside the "
            "immutable binding source interval")
    if not (vp["trim_start_sample"] <= row["source_start_sample"]
            and row["source_end_sample_exclusive"]
            <= vp["trim_end_sample_exclusive"]):
        raise _corrupt(
            f"{where} captured sample interval lies outside the VP "
            "trim")
    return info


def _m17cc_rational(num, den, what: str) -> Fraction:
    _check_rational(num, den, what)
    return Fraction(num, den)


def _verify_m17cc_captured_conflicts(rev_id: str, verified) -> None:
    """§13.4 captured conflict law: no overlapping same-subject
    interval pair whose retained payload CHANNEL sets intersect
    inside ONE captured history — evaluated from the CAPTURED
    companion rows + the immutable payloads (the D14 channel-conflict
    law checked against captured history, never against present-day
    performance mappings; disjoint-channel same-subject overlap is
    the LAWFUL D14 shape and must not refuse)."""
    import itertools
    for a, b in itertools.combinations(verified, 2):
        if a["subject_id"] != b["subject_id"]:
            continue
        if not (a["start"] < b["end"] and b["start"] < a["end"]):
            continue
        shared = (a["channels"] or frozenset()) & \
            (b["channels"] or frozenset())
        if shared:
            raise _corrupt(
                f"ShotRevision {rev_id} captured history carries "
                f"overlapping same-subject segments "
                f"[{a['start']}, {a['end']}) and [{b['start']}, "
                f"{b['end']}) sharing channels {sorted(shared)} — "
                "the D14 channel-conflict law is checked against "
                "captured history")


def _m17cc_payload_channels(data: bytes, where: str) -> frozenset:
    """The retained payload's channel-key set (the captured conflict
    law's disjointness domain)."""
    try:
        return frozenset(
            ch["channel_key"] for ch in json.loads(data)["channels"])
    except (ValueError, TypeError, KeyError) as exc:
        raise _corrupt(
            f"{where} retained payload blob is not a channel "
            f"payload document: {exc}") from exc


def _verify_generation_performance_inputs(
        con: sqlite3.Connection, blob_root: Path) -> None:
    """§13.6 structural laws constructible before the M17C-D writer:
    parent + creation-unit coherence, role vocabulary, retained-byte
    rehash, exact segment tieback, and translation/derived-input
    identity validity. The control-schedule recomputation and the
    sample-exact vocal-audio realization laws require the §14.6
    sampler and remain M17C-D — no substitute sampler is invented
    here. Recovery never WRITES these rows."""
    import hashlib
    for row in con.execute(
            "SELECT generation_id, input_key, position, artifact_role, "
            "shot_revision_segment_position, performance_revision_id, "
            "vocal_performance_revision_id, blob_hash, binding_hash, "
            "segment_hash, translation_identity, derived_input_hash, "
            "created_at FROM generation_performance_inputs"):
        gwhere = (f"generation performance input "
                  f"{row['generation_id']!r}/{row['input_key']!r}"
                  f"@{row['position']}")
        # SR-M17CC-05: total over SQLite storage classes — certify the
        # persisted types BEFORE any string/integer operation. A
        # 64-byte BLOB passes the schema's length CHECK on a
        # TEXT-affinity hash column and returns as Python bytes, for
        # which .strip(str) raises a raw TypeError; a REAL/bool/None
        # coordinate is not the nonnegative integer the tie-back laws
        # assume. Malformed storage terminates HERE as typed
        # corruption, never an uncontrolled Python exception.
        for column in ("position",
                       "shot_revision_segment_position"):
            value = row[column]
            if isinstance(value, bool) or not isinstance(value, int) \
                    or value < 0:
                raise _corrupt(
                    f"{gwhere} {column} {value!r} is not a persisted "
                    "nonnegative integer (malformed SQLite storage "
                    "class)")
        for column in ("blob_hash", "segment_hash",
                       "derived_input_hash"):
            if not isinstance(row[column], str):
                raise _corrupt(
                    f"{gwhere} {column} is not persisted text "
                    f"(malformed SQLite storage class: "
                    f"{row[column]!r})")
        if row["binding_hash"] is not None and \
                not isinstance(row["binding_hash"], str):
            raise _corrupt(
                f"{gwhere} binding_hash is not persisted text "
                f"(malformed SQLite storage class: "
                f"{row['binding_hash']!r})")
        gen = con.execute(
            "SELECT shot_revision_id, created_at, workflow_spec_json, "
            "workflow_spec_hash FROM generations WHERE id = ?",
            (row["generation_id"],)).fetchone()
        if gen is None:
            raise _corrupt(f"{gwhere} has no parent Generation")
        # same creation unit: the sibling binding was written in the
        # Generation's creation transaction
        if row["created_at"] != gen["created_at"]:
            raise _corrupt(
                f"{gwhere} was not written in its Generation's "
                "creation unit")
        if row["artifact_role"] not in (
                "performance.controls", "performance.vocal_audio"):
            raise _corrupt(
                f"{gwhere} carries unknown artifact_role "
                f"{row['artifact_role']!r}")
        for column in ("blob_hash", "segment_hash", "derived_input_hash"):
            value = row[column]
            if len(value) != 64 or value.strip("0123456789abcdef"):
                raise _corrupt(
                    f"{gwhere} {column} is not a 64-char lowercase "
                    "hex digest")
        if row["binding_hash"] is not None and (
                len(row["binding_hash"]) != 64
                or row["binding_hash"].strip("0123456789abcdef")):
            raise _corrupt(
                f"{gwhere} binding_hash is not a 64-char lowercase "
                "hex digest")
        # retained derived bytes exist and rehash
        blob_path = blob_root / "sha256" / row["blob_hash"][:2] / \
            row["blob_hash"][2:4] / row["blob_hash"]
        if not blob_path.is_file():
            raise _corrupt(
                f"{gwhere} retained derived-input blob "
                f"{row['blob_hash']} is missing")
        if hashlib.sha256(
                blob_path.read_bytes()).hexdigest() != row["blob_hash"]:
            raise _corrupt(
                f"{gwhere} retained derived-input blob does not rehash")
        # the tie-back resolves to the EXACT captured schema-8 segment
        child = con.execute(
            "SELECT " + _M17CC_CHILD_COLUMNS +
            " FROM shot_revision_performance_segments "
            "WHERE shot_revision_id = ? AND position = ?",
            (gen["shot_revision_id"],
             row["shot_revision_segment_position"])).fetchone()
        if child is None:
            raise _corrupt(
                f"{gwhere} tie-back resolves to no captured schema-8 "
                f"segment ({gen['shot_revision_id']!r}@"
                f"{row['shot_revision_segment_position']})")
        if child["segment_hash"] != row["segment_hash"]:
            raise _corrupt(
                f"{gwhere} segment_hash does not tie back to the exact "
                "captured segment")
        if child["performance_revision_id"] != \
                row["performance_revision_id"]:
            raise _corrupt(
                f"{gwhere} performance_revision_id disagrees with the "
                "tied-back captured segment")
        if row["vocal_performance_revision_id"] is not None \
                or row["binding_hash"] is not None:
            if child["vocal_performance_revision_id"] is None:
                raise _corrupt(
                    f"{gwhere} carries vocal identity but the tied-back "
                    "segment is generic")
            if (row["vocal_performance_revision_id"]
                    != child["vocal_performance_revision_id"]
                    or row["binding_hash"]
                    != child["vocal_binding_hash"]):
                raise _corrupt(
                    f"{gwhere} vocal identity disagrees with the "
                    "tied-back captured segment")
        elif row["artifact_role"] == "performance.vocal_audio":
            raise _corrupt(
                f"{gwhere} is a vocal-audio input without its vocal "
                "identity group")
        # the translation identity is materialized in the Generation's
        # execution spec (grammar-agnostic presence: the exact spec
        # field grammar is frozen with the M17C-D writer)
        try:
            spec = json.loads(gen["workflow_spec_json"])
        except (ValueError, TypeError) as exc:
            raise _corrupt(
                f"Generation {row['generation_id']} workflow_spec_json "
                f"is malformed JSON: {exc}") from exc
        if _canonical(spec) != gen["workflow_spec_json"] \
                or _hash(spec) != gen["workflow_spec_hash"]:
            raise _corrupt(
                f"Generation {row['generation_id']} workflow spec "
                "bytes/hash disagree with canonical form")
        # FPR-M17CC-06: IDENTITY EQUALITY at the frozen coordinate —
        # the WorkflowSpec's dedicated performance-translation field
        # must EQUAL the row's translation identity (presence anywhere
        # else in the document is not identity). The coordinate is
        # frozen here ahead of the M17C-D writer.
        if spec.get("performance_translation") != \
                row["translation_identity"]:
            raise _corrupt(
                f"{gwhere} translation_identity disagrees with the "
                "WorkflowSpec performance_translation coordinate "
                f"({spec.get('performance_translation')!r} != "
                f"{row['translation_identity']!r})")
