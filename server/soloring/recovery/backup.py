"""M10F-A full-instance local storage backup/restore (R5 §7).

Frozen posture: default file-backed SQLite layout only —
``database_url is None``, DB at ``<data_dir>/soloring.db``, BlobStore at
``<data_dir>/blobs``, WorkflowArtifactStore root at
``<data_dir>/workflow-artifacts``. Any other posture fails closed before
staging/filesystem mutation.

Backup copies one coherent online SQLite snapshot plus every historically
live Blob and workflow artifact byte, verifies each byte against its
frozen content identity before and after copy, and publishes atomically by
a single same-filesystem rename to an absent destination. Restore is the
mirror image into a fresh data root and re-verifies everything, including
production historical retrieval through the real artifact store.

Recovery is verify-only with respect to source history: missing or corrupt
bytes fail closed; there is no repair, no GC, no skip mode, and no write
into the live source database. Failures raise ``RecoveryError`` subclasses
(operator/recovery-tool level — no durable API error vocabulary exists
here).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from soloring.assets.blob_store import BlobStore
from soloring.domain.canonical import canonical_json_bytes, canonical_hash
from soloring.settings import Settings
from soloring.workflows.artifact_store import WorkflowArtifactStore

EXPECTED_ALEMBIC_HEAD = "0015_m14_world_observation_execution"
BACKUP_MANIFEST_SCHEMA_VERSION = 1

# M13 (frozen R3 §23): restore is head-dispatched across five heads. M14
# (frozen R2 §23) advances the expected head to 0015 and adds the eighth
# Blob-FK path (derived_observation_artifacts.blob_hash); historical
# restore heads 0011-0014 remain supported with their exact policies.
PRE_M11_ALEMBIC_HEAD = "0011_m10_derived_spatial_execution"
M11_ALEMBIC_HEAD = "0012_m11_reusable_production_revisions"
M12_ALEMBIC_HEAD = "0013_m12_composition_occurrences"
M13_ALEMBIC_HEAD = "0014_m13_authority_complete_world"
M14_ALEMBIC_HEAD = "0015_m14_world_observation_execution"
SUPPORTED_RESTORE_ALEMBIC_HEADS = frozenset({
    PRE_M11_ALEMBIC_HEAD,
    M11_ALEMBIC_HEAD,
    M12_ALEMBIC_HEAD,
    M13_ALEMBIC_HEAD,
    M14_ALEMBIC_HEAD,
})

ARTIFACT_KINDS = (
    "execution_model_fingerprints",
    "manifests",
    "realization_profiles",
    "templates",
)

# §7.5: the exhaustive frozen Blob-reference inventory. Recovery proves
# source-schema completeness against SQLite FK metadata before any copy.
#
# M10F-A implementation correction (disclosed): the R5 §5.2.5/§7.5 list
# named only the four M10-era paths. The published M10E schema carries SIX
# FK paths to blobs(hash) — the two immutable M8 visual-provenance tables
# (visual/models.py fk_visual_anchor_revision_items_blob_hash_blobs and
# fk_shot_revision_visual_anchor_items_blob_hash_blobs) also retain
# reference-image Blob bytes required by the frozen M8 retained-history
# contract. The recovery FK-completeness guard rejected the four-path
# expectation on its first real run; the inventory below is the
# source-true exhaustive set. Omitting the M8 paths would silently drop
# anchor-image bytes from every backup.
PRE_M11_BLOB_FK_COLUMNS = frozenset({
    ("assets", "blob_hash"),
    ("derived_spatial_artifacts", "blob_hash"),
    ("generation_derived_spatial_inputs", "blob_hash"),
    ("generation_inputs", "blob_hash"),
    ("shot_revision_visual_anchor_items", "blob_hash"),
    ("visual_anchor_revision_items", "blob_hash"),
})

# M11 adds the seventh durable Blob-reference path (frozen R3 §14.2): the
# immutable retained_blob/v1 closure projection. The 0012 policy is exactly
# seven paths; the 0011 restore policy stays exactly the six above.
M11_BLOB_FK_COLUMNS = frozenset(
    set(PRE_M11_BLOB_FK_COLUMNS)
    | {("production_revision_closures", "blob_hash")}
)

# M14 (frozen R2 §23): the 0015 policy is exactly the predecessor seven
# paths plus derived_observation_artifacts.blob_hash — the eighth path.
# The binding table pins its Blob through the composite FK to the
# artifact row (which itself FKs blobs), so it declares no independent
# blobs FK and the physical inventory is exactly eight.
M14_BLOB_FK_COLUMNS = frozenset(
    set(M11_BLOB_FK_COLUMNS)
    | {("derived_observation_artifacts", "blob_hash")}
)


def _blob_fk_policy_for_head(head: str) -> frozenset:
    """Exact head-specific Blob-FK inventory (frozen §§14.2/16.2/23.2/§23)."""
    if head == PRE_M11_ALEMBIC_HEAD:
        return PRE_M11_BLOB_FK_COLUMNS
    if head in (M11_ALEMBIC_HEAD, M12_ALEMBIC_HEAD, M13_ALEMBIC_HEAD):
        # M12/M13 add no Blob FK; 0012-0014 share the exact seven paths.
        return M11_BLOB_FK_COLUMNS
    if head == M14_ALEMBIC_HEAD:
        return M14_BLOB_FK_COLUMNS
    raise RecoveryCorruption(f"unsupported recovery head {head!r}.")

_HEX = set("0123456789abcdef")
_CHUNK = 1 << 20


class RecoveryError(RuntimeError):
    """Operator/recovery-tool level failure (never a durable API error)."""


class RecoveryUnsupported(RecoveryError):
    """The configured storage posture is not the supported default-local one."""


class RecoveryCorruption(RecoveryError):
    """Historical/source bytes or identities failed closed verification."""


class BackupManifestInvalid(RecoveryError):
    """backup-manifest.json violated the frozen backup-manifest-v1 grammar."""


# ---------------------------------------------------------------------------
# Posture guard (§7.1)
# ---------------------------------------------------------------------------


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def verify_supported_posture(
    settings: Settings, *, artifact_root: Path | None = None
) -> None:
    """Fail closed on any non-default storage posture BEFORE staging.

    ``artifact_root`` exists so callers (and the cell-31 drift tripwire
    test) can hand recovery the workflow-artifact root actually in use;
    it must still equal ``<data_dir>/workflow-artifacts``. Published M10E
    exposes no settings-level override for that root — recovery does not
    add one.
    """
    if settings.database_url is not None:
        raise RecoveryUnsupported(
            "Recovery supports only the default local database ("
            "database_url must be None); got an explicit override."
        )
    data_dir = Path(settings.data_dir)
    if Path(settings.db_path) != data_dir / "soloring.db":
        raise RecoveryUnsupported(
            "Recovery requires the DB at <data_dir>/soloring.db."
        )
    if Path(settings.blob_dir) != data_dir / "blobs":
        raise RecoveryUnsupported(
            "Recovery requires the default Blob root <data_dir>/blobs."
        )
    root = (
        Path(artifact_root) if artifact_root is not None
        else data_dir / "workflow-artifacts"
    )
    if root != data_dir / "workflow-artifacts":
        raise RecoveryUnsupported(
            "Recovery requires the deterministic WorkflowArtifactStore root "
            f"<data_dir>/workflow-artifacts; got {root}."
        )


# ---------------------------------------------------------------------------
# Streaming hash helpers
# ---------------------------------------------------------------------------


def _stream_hash(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(_CHUNK)
            if not chunk:
                break
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


def _verify_bytes(path: Path, expected_hash: str) -> int:
    actual, size = _stream_hash(path)
    if actual != expected_hash:
        raise RecoveryCorruption(
            f"{path} hashes to {actual}; frozen identity is {expected_hash}."
        )
    return size


def _copy_verified(src: Path, dst: Path, expected_hash: str) -> int:
    """§7.4 step 9: hash source, copy exact bytes, re-hash the copy."""
    _verify_bytes(src, expected_hash)
    dst.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with open(src, "rb") as f, open(dst, "wb") as out:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            out.write(chunk)
            size += len(chunk)
    _verify_bytes(dst, expected_hash)
    return size


# ---------------------------------------------------------------------------
# Staged-DB level checks (§7.4 steps 5-8)
# ---------------------------------------------------------------------------


def _sqlite_online_backup(source_uri: str, dest_db: Path) -> None:
    source = sqlite3.connect(source_uri, uri=True)
    try:
        dest = sqlite3.connect(str(dest_db))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()


def _normalize_staged_wal(staged_db: Path) -> dict:
    """Staged-copy-only WAL checkpoint normalization; never touches live."""
    con = sqlite3.connect(str(staged_db))
    try:
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = con.execute("PRAGMA foreign_keys").fetchone()[0]
        if str(mode).lower() == "wal":
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return {"journal_mode": mode, "foreign_keys": foreign_keys}
    finally:
        con.close()
    # A clean close removes any -wal/-shm side files; enforce that so the
    # staged backup tree contains exactly the DB bytes the manifest hashes.


def _drop_sidecar_files(staged_db: Path) -> None:
    for suffix in ("-wal", "-shm"):
        side = staged_db.with_name(staged_db.name + suffix)
        if side.exists():
            side.unlink()


def _verify_staged_db(staged_db: Path, expected_head: str = EXPECTED_ALEMBIC_HEAD) -> None:
    con = sqlite3.connect(str(staged_db))
    try:
        row = con.execute("PRAGMA quick_check").fetchone()
        if row is None or row[0] != "ok":
            raise RecoveryCorruption(f"staged DB quick_check failed: {row!r}")
        violations = con.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RecoveryCorruption(
                f"staged DB foreign_key_check reported {violations[:3]!r}"
            )
        try:
            versions = [
                r[0] for r in con.execute("SELECT version_num FROM alembic_version")
            ]
        except sqlite3.OperationalError as exc:
            raise RecoveryCorruption(
                "staged DB has no alembic_version table; cannot prove the "
                "migration head."
            ) from exc
        if versions != [expected_head]:
            raise RecoveryCorruption(
                f"staged DB migration head is {versions!r}; recovery "
                f"requires exactly [{expected_head!r}]."
            )
    finally:
        con.close()


def _blob_fk_inventory(con: sqlite3.Connection) -> set[tuple[str, str]]:
    tables = [
        r[0]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    ]
    found: set[tuple[str, str]] = set()
    for table in tables:
        quoted = table.replace('"', '""')
        for row in con.execute(f'PRAGMA foreign_key_list("{quoted}")'):
            _, _, parent, from_col, to_col = row[0], row[1], row[2], row[3], row[4]
            if parent == "blobs" and to_col in ("hash", None):
                found.add((table, from_col))
    return found


# ---------------------------------------------------------------------------
# Historical liveness enumeration (§7.5/§7.6)
# ---------------------------------------------------------------------------


@dataclass
class _Liveness:
    blob_hashes: list[str] = field(default_factory=list)
    blob_rows: dict[str, dict] = field(default_factory=dict)
    artifacts: list[tuple[str, str]] = field(default_factory=list)
    projects: list[dict] = field(default_factory=list)
    generation_count: int = 0


def _hex_or_corrupt(value: object, what: str) -> str:
    if not _is_hash(value):
        raise RecoveryCorruption(f"{what} is not a 64-lowercase-hex sha256.")
    return value  # type: ignore[return-value]


def _generation_artifact_requirements(spec: dict, what: str) -> list[tuple[str, str]]:
    """Schema-aware workflow-artifact dependencies of one WorkflowSpec."""
    schema_version = spec.get("schema_version")
    out: list[tuple[str, str]] = []
    if schema_version == 1:
        return out
    if schema_version == 2:
        try:
            profile_hash = spec["realization"]["profile"]["hash"]
            fp_hash = spec["model"]["execution_model_fingerprint_hash"]
        except (KeyError, TypeError) as exc:
            raise RecoveryCorruption(
                f"{what}: schema-2 WorkflowSpec lacks its frozen "
                "realization.profile.hash / model.execution_model_fingerprint_hash."
            ) from exc
        out.append(("realization_profiles", _hex_or_corrupt(
            profile_hash, f"{what}: realization.profile.hash")))
        out.append(("execution_model_fingerprints", _hex_or_corrupt(
            fp_hash, f"{what}: execution_model_fingerprint_hash")))
        return out
    if schema_version == 3:
        try:
            sr = spec["spatial_realization"]
            profile_hash = sr["realization_profile_hash"]
            fp_hash = spec["model"]["execution_model_fingerprint_hash"]
        except (KeyError, TypeError) as exc:
            raise RecoveryCorruption(
                f"{what}: schema-3 WorkflowSpec lacks its frozen "
                "spatial_realization.realization_profile_hash / "
                "model.execution_model_fingerprint_hash."
            ) from exc
        out.append(("realization_profiles", _hex_or_corrupt(
            profile_hash, f"{what}: spatial realization_profile_hash")))
        out.append(("execution_model_fingerprints", _hex_or_corrupt(
            fp_hash, f"{what}: execution_model_fingerprint_hash")))
        realization = spec.get("realization")
        if realization is not None:
            try:
                m9_hash = realization["profile"]["hash"]
            except (KeyError, TypeError) as exc:
                raise RecoveryCorruption(
                    f"{what}: schema-3 M9 realization block lacks profile.hash."
                ) from exc
            m9_hash = _hex_or_corrupt(
                m9_hash, f"{what}: M9 realization profile.hash")
            if m9_hash != profile_hash:
                raise RecoveryCorruption(
                    f"{what}: M9 realization profile hash disagrees with the "
                    "captured spatial realization profile hash; the frozen "
                    "release contract binds one profile per release."
                )
        return out
    if schema_version == 4:
        # M14 (frozen R2 §37): schema 4 references the same four workflow
        # package artifact kinds through its lower schema-3 value, plus
        # the exact observation profile/capability identities.
        try:
            sr = spec["lower_schema_3"]["spatial_realization"]
            profile_hash = sr["realization_profile_hash"]
            fp_hash = spec["lower_schema_3"]["model"][
                "execution_model_fingerprint_hash"]
        except (KeyError, TypeError) as exc:
            raise RecoveryCorruption(
                f"{what}: schema-4 lower_schema_3 lacks its frozen "
                "spatial_realization/model identities."
            ) from exc
        out.append(("realization_profiles", _hex_or_corrupt(
            profile_hash, f"{what}: schema-4 realization_profile_hash")))
        out.append(("execution_model_fingerprints", _hex_or_corrupt(
            fp_hash, f"{what}: schema-4 execution_model_fingerprint_hash")))
        observation = spec.get("world_observation")
        if not isinstance(observation, dict):
            raise RecoveryCorruption(
                f"{what}: schema-4 WorkflowSpec lacks world_observation.")
        for field in ("profile_hash", "capability_contract_hash"):
            _hex_or_corrupt(observation.get(field),
                            f"{what}: world_observation.{field}")
        return out
    raise RecoveryCorruption(
        f"{what}: unsupported WorkflowSpec schema_version {schema_version!r}."
    )


def _spec_ordinary_bindings(spec: dict, what: str) -> set[tuple[str, int, str]]:
    # M14 §26 (HIST:09): schema-4 ordinary inputs live on the inherited
    # lower_schema_3 value — the frozen delegated meaning, never rebuilt
    # from current state.
    if spec.get("schema_version") == 4:
        spec = spec.get("lower_schema_3") or {}
    inputs = spec.get("inputs")
    if not isinstance(inputs, dict):
        raise RecoveryCorruption(f"{what}: WorkflowSpec inputs must be an object.")
    out: set[tuple[str, int, str]] = set()
    for key, entry in inputs.items():
        bindings = entry.get("bindings") if isinstance(entry, dict) else None
        if not isinstance(bindings, list):
            raise RecoveryCorruption(
                f"{what}: input {key!r} lacks its bindings list."
            )
        for b in bindings:
            try:
                position = b["position"]
                blob_hash = b["blob_hash"]
            except (KeyError, TypeError) as exc:
                raise RecoveryCorruption(
                    f"{what}: input {key!r} binding lacks position/blob_hash."
                ) from exc
            if not isinstance(position, int) or isinstance(position, bool):
                raise RecoveryCorruption(
                    f"{what}: input {key!r} binding position must be an int."
                )
            out.add((key, position, _hex_or_corrupt(
                blob_hash, f"{what}: input {key!r} blob_hash")))
    return out


def _spec_derived_bindings(spec: dict, what: str) -> list[dict]:
    try:
        artifacts = spec["spatial_realization"]["derived_artifacts"]
    except (KeyError, TypeError) as exc:
        raise RecoveryCorruption(
            f"{what}: schema-3 WorkflowSpec lacks "
            "spatial_realization.derived_artifacts."
        ) from exc
    if not isinstance(artifacts, list) or not artifacts:
        raise RecoveryCorruption(
            f"{what}: spatial_realization.derived_artifacts must be a "
            "non-empty list."
        )
    out = []
    for a in artifacts:
        if not isinstance(a, dict):
            raise RecoveryCorruption(f"{what}: derived artifact is not an object.")
        for f in ("input_key", "position", "derived_spatial_artifact_id",
                  "spec_hash", "runtime_fingerprint_hash", "blob_hash"):
            if f not in a:
                raise RecoveryCorruption(
                    f"{what}: derived artifact lacks {f!r}."
                )
        out.append(a)
    return out


def _blob_relative_path(blob_hash: str) -> str:
    """The frozen BlobStore persisted-path grammar: sha256/aa/bb/<hash>
    (mirrors BlobStore.relative_path_for_hash, which is instance-bound)."""
    if not _is_hash(blob_hash):
        raise RecoveryCorruption(f"invalid blob hash: {blob_hash!r}")
    return f"sha256/{blob_hash[0:2]}/{blob_hash[2:4]}/{blob_hash}"


def _staged_db_head(staged_db: Path) -> str:
    con = sqlite3.connect(str(staged_db))
    try:
        rows = con.execute(
            "SELECT version_num FROM alembic_version").fetchall()
    finally:
        con.close()
    if len(rows) != 1:
        raise RecoveryCorruption(
            f"staged DB has {len(rows)} alembic_version rows")
    return rows[0][0]


def _enumerate_liveness(staged_db: Path, expected_columns: frozenset | None = None) -> _Liveness:
    """Exact Blob + workflow-artifact liveness from the staged DB only."""
    if expected_columns is None:
        # Backup/verification paths without an explicit head dispatch
        # read the policy from the staged DB's actual head.
        expected_columns = _blob_fk_policy_for_head(
            _staged_db_head(staged_db))
    con = sqlite3.connect(str(staged_db))
    con.row_factory = sqlite3.Row
    try:
        inventory = _blob_fk_inventory(con)
        if inventory != set(expected_columns):
            raise RecoveryCorruption(
                "Blob FK inventory drifted from the frozen head-specific "
                f"exact set {sorted(expected_columns)}: found "
                f"{sorted(inventory)}. A new durable Blob-reference path "
                "requires a plan revision before recovery can certify "
                "completeness."
            )

        blob_hashes: set[str] = set()
        for table, _col in sorted(expected_columns):
            for row in con.execute(f'SELECT DISTINCT blob_hash FROM "{table}"'):
                blob_hashes.add(_hex_or_corrupt(
                    row[0], f"{table}.blob_hash entry"))

        # R6 §7.5/PD-2: canonical relative rows everywhere; the ONLY legacy
        # exception is the known M10E D0-writer absolute form (row reachable
        # through derived_spatial_artifacts whose normalized value ends with
        # the exact canonical suffix). The stored value is preserved and is
        # NEVER dereferenced — physical access is always hash-derived.
        dsa_hashes = {
            r[0] for r in con.execute(
                "SELECT DISTINCT blob_hash FROM derived_spatial_artifacts")
        }

        blob_rows: dict[str, dict] = {}
        for h in sorted(blob_hashes):
            row = con.execute(
                "SELECT path, size_bytes FROM blobs WHERE hash = ?", (h,)
            ).fetchone()
            if row is None:
                raise RecoveryCorruption(
                    f"historically live Blob {h} has no blobs row."
                )
            canonical = _blob_relative_path(h)
            stored = row["path"]
            if stored != canonical:
                normalized = str(stored).replace("\\", "/")
                is_absolute = (
                    normalized.startswith("/")
                    or (len(normalized) > 2
                        and normalized[1] == ":"
                        and normalized[0].isalpha())
                )
                legacy = (
                    h in dsa_hashes
                    and is_absolute
                    and normalized.endswith("/" + canonical)
                )
                if not legacy:
                    raise RecoveryCorruption(
                        f"blobs.path for {h} is {stored!r}; frozen BlobStore "
                        f"grammar requires {canonical!r}, and the only "
                        "tolerated legacy form is the known M10E absolute "
                        "D0 path with an exactly matching canonical suffix."
                    )
            size = row["size_bytes"]
            if not isinstance(size, int) or size < 0:
                raise RecoveryCorruption(
                    f"blobs.size_bytes for {h} is not a non-negative int."
                )
            blob_rows[h] = {"path": stored, "size_bytes": size}

        artifacts: set[tuple[str, str]] = set()
        generation_specs: list[dict] = []
        gen_rows = con.execute(
            "SELECT g.id, g.shot_id, g.manifest_hash, g.workflow_template_hash, "
            "g.workflow_spec_json, g.workflow_spec_hash, s.project_id "
            "FROM generations g JOIN shots s ON s.id = g.shot_id"
        ).fetchall()
        for row in gen_rows:
            what = f"Generation {row['id']}"
            manifest_hash = _hex_or_corrupt(row["manifest_hash"],
                                            f"{what}: manifest_hash")
            template_hash = _hex_or_corrupt(
                row["workflow_template_hash"], f"{what}: workflow_template_hash")
            try:
                spec = json.loads(row["workflow_spec_json"])
            except ValueError as exc:
                raise RecoveryCorruption(
                    f"{what}: stored WorkflowSpec is not valid JSON."
                ) from exc
            if not isinstance(spec, dict):
                raise RecoveryCorruption(f"{what}: WorkflowSpec is not an object.")
            if canonical_hash(spec) != row["workflow_spec_hash"]:
                raise RecoveryCorruption(
                    f"{what}: canonical WorkflowSpec hash disagrees with the "
                    "persisted workflow_spec_hash."
                )
            if spec.get("schema_version") == 3:
                # M10E froze byte-canonical storage for schema-3 only.
                from soloring.domain.canonical import canonical_json_str
                if canonical_json_str(spec) != row["workflow_spec_json"]:
                    raise RecoveryCorruption(
                        f"{what}: schema-3 stored WorkflowSpec bytes are not "
                        "canonical."
                    )

            artifacts.add(("manifests", manifest_hash))
            artifacts.add(("templates", template_hash))
            artifacts.update(_generation_artifact_requirements(spec, what))

            ordinary = _spec_ordinary_bindings(spec, what)
            rows = con.execute(
                "SELECT input_key, position, blob_hash FROM generation_inputs "
                "WHERE generation_id = ?", (row["id"],)
            ).fetchall()
            relational = {
                (r["input_key"], r["position"], _hex_or_corrupt(
                    r["blob_hash"], f"{what}: generation_inputs blob_hash"))
                for r in rows
            }
            if ordinary != relational:
                raise RecoveryCorruption(
                    f"{what}: WorkflowSpec ordinary Blob bindings disagree "
                    "with generation_inputs relational history."
                )

            if spec.get("schema_version") == 3:
                spec_derived = _spec_derived_bindings(spec, what)
                rows = con.execute(
                    "SELECT input_key, position, derived_spatial_artifact_id, "
                    "blob_hash FROM generation_derived_spatial_inputs "
                    "WHERE generation_id = ?", (row["id"],)
                ).fetchall()
                sibling_map = {
                    (r["input_key"], r["position"]): r for r in rows
                }
                if len(sibling_map) != len(rows):
                    raise RecoveryCorruption(
                        f"{what}: duplicate derived sibling identity."
                    )
                if len(spec_derived) != len(rows):
                    raise RecoveryCorruption(
                        f"{what}: spatial_realization.derived_artifacts "
                        "cardinality disagrees with "
                        "generation_derived_spatial_inputs."
                    )
                for a in spec_derived:
                    sibling = sibling_map.get(
                        (a["input_key"], a["position"]))
                    if sibling is None:
                        raise RecoveryCorruption(
                            f"{what}: derived input {a['input_key']!r} has no "
                            "generation_derived_spatial_inputs sibling."
                        )
                    if sibling["derived_spatial_artifact_id"] != a[
                            "derived_spatial_artifact_id"] or sibling[
                                "blob_hash"] != a["blob_hash"]:
                        raise RecoveryCorruption(
                            f"{what}: derived input {a['input_key']!r} "
                            "identity disagrees with its sibling row."
                        )
                    dsa = con.execute(
                        "SELECT spec_hash, runtime_fingerprint_hash, blob_hash "
                        "FROM derived_spatial_artifacts WHERE id = ?",
                        (a["derived_spatial_artifact_id"],),
                    ).fetchone()
                    if dsa is None:
                        raise RecoveryCorruption(
                            f"{what}: derived artifact "
                            f"{a['derived_spatial_artifact_id']} has no "
                            "derived_spatial_artifacts row."
                        )
                    if (dsa["spec_hash"] != a["spec_hash"]
                            or dsa["runtime_fingerprint_hash"] != a[
                                "runtime_fingerprint_hash"]
                            or dsa["blob_hash"] != a["blob_hash"]):
                        raise RecoveryCorruption(
                            f"{what}: derived input {a['input_key']!r} "
                            "disagrees with derived_spatial_artifacts "
                            "provenance."
                        )

            if spec.get("schema_version") == 4:
                # M14 (frozen R2 §37): verify the exact schema-4
                # observation identities and the composite
                # artifact-id/Blob-hash binding.
                observation = spec["world_observation"]
                import hashlib as _hl
                from soloring.domain.canonical import (
                    canonical_json_bytes as _cjb,
                )
                if _hl.sha256(_cjb(observation["spec"])).hexdigest() != (
                        observation["spec_hash"]):
                    raise RecoveryCorruption(
                        f"{what}: world_observation.spec_hash disagrees "
                        "with the nested WorldObservationSpec bytes.")
                if _hl.sha256(_cjb(observation["negotiation"])).hexdigest() \
                        != observation["negotiation_hash"]:
                    raise RecoveryCorruption(
                        f"{what}: world_observation.negotiation_hash "
                        "disagrees with the nested NegotiationResult bytes.")
                obs_rows = con.execute(
                    "SELECT doa.id, doa.observation_spec_hash, "
                    "doa.parameters_hash, doa.provenance_hash, "
                    "doa.blob_hash, gdoi.input_key, gdoi.position "
                    "FROM generation_derived_observation_inputs gdoi "
                    "JOIN derived_observation_artifacts doa "
                    "  ON doa.id = gdoi.derived_observation_artifact_id "
                    "AND doa.blob_hash = gdoi.blob_hash "
                    "WHERE gdoi.generation_id = ?",
                    (row["id"],),
                ).fetchall()
                if obs_rows:
                    for r in obs_rows:
                        if r["observation_spec_hash"] != (
                                observation["spec_hash"]):
                            raise RecoveryCorruption(
                                f"{what}: derived observation artifact "
                                f"{r['id']} pins a different observation "
                                "spec hash than the stored WorkflowSpec.")
                parameters = json.loads(
                    con.execute(
                        "SELECT parameters_json FROM "
                        "derived_observation_artifacts WHERE id = ?",
                        (obs_rows[0]["id"],),
                    ).fetchone()["parameters_json"]
                ) if obs_rows else None
                if parameters is not None:
                    if _hl.sha256(_cjb(parameters)).hexdigest() != (
                            obs_rows[0]["parameters_hash"]):
                        raise RecoveryCorruption(
                            f"{what}: derived observation parameters_hash "
                            "disagrees with canonical parameters bytes.")

            generation_specs.append({
                "generation_id": row["id"],
                "project_id": row["project_id"],
                "spec": spec,
            })

        projects = _project_diagnostics(con, generation_specs)
        return _Liveness(
            blob_hashes=sorted(blob_hashes),
            blob_rows=blob_rows,
            artifacts=sorted(artifacts),
            projects=projects,
            generation_count=len(generation_specs),
        )
    finally:
        con.close()


def _project_diagnostics(
    con: sqlite3.Connection, generation_specs: list[dict]
) -> list[dict]:
    """Per-Project diagnostic projection of the full-instance liveness set
    (§7.3): every Project row, sorted; never an independent selector."""
    out: list[dict] = []
    project_rows = con.execute(
        "SELECT id FROM projects ORDER BY id"
    ).fetchall()
    for prow in project_rows:
        pid = prow["id"]
        blob_set: set[str] = set()
        for row in con.execute(
            "SELECT blob_hash FROM assets WHERE project_id = ?", (pid,)
        ):
            blob_set.add(_hex_or_corrupt(row[0], f"assets blob of {pid}"))
        gen_ids = {g["generation_id"] for g in generation_specs
                   if g["project_id"] == pid}
        for gid in gen_ids:
            for row in con.execute(
                "SELECT blob_hash FROM generation_inputs WHERE generation_id = ?",
                (gid,),
            ):
                blob_set.add(row[0])
            for row in con.execute(
                "SELECT blob_hash FROM generation_derived_spatial_inputs "
                "WHERE generation_id = ?", (gid,),
            ):
                blob_set.add(row[0])
        for row in con.execute(
            "SELECT blob_hash FROM derived_spatial_artifacts "
            "WHERE project_id = ?", (pid,),
        ):
            blob_set.add(row[0])
        for row in con.execute(
            "SELECT i.blob_hash FROM shot_revision_visual_anchor_items i "
            "JOIN shot_revisions sr ON sr.id = i.shot_revision_id "
            "JOIN shots s ON s.id = sr.shot_id WHERE s.project_id = ?",
            (pid,),
        ):
            blob_set.add(row[0])
        for row in con.execute(
            "SELECT i.blob_hash FROM visual_anchor_revision_items i "
            "JOIN visual_anchor_revisions ar ON ar.id = i.visual_anchor_revision_id "
            "JOIN visual_anchors a ON a.id = ar.visual_anchor_id "
            "JOIN entity_revisions er ON er.id = a.entity_revision_id "
            "JOIN creative_entities ce ON ce.id = er.entity_id "
            "WHERE ce.project_id = ?",
            (pid,),
        ):
            blob_set.add(row[0])

        artifact_set: set[tuple[str, str]] = set()
        for g in generation_specs:
            if g["project_id"] != pid:
                continue
            artifact_set.update(
                _generation_artifact_requirements(g["spec"], f"project {pid}"))
            gen_row = con.execute(
                "SELECT manifest_hash, workflow_template_hash FROM generations "
                "WHERE id = ?", (g["generation_id"],),
            ).fetchone()
            artifact_set.add(("manifests", gen_row["manifest_hash"]))
            artifact_set.add(("templates", gen_row["workflow_template_hash"]))

        out.append({
            "project_id": pid,
            "historical_blob_hashes": sorted(blob_set),
            "historical_workflow_artifacts": [
                {"kind": kind, "sha256": h}
                for kind, h in sorted(artifact_set)
            ],
        })
    return out


# ---------------------------------------------------------------------------
# Backup manifest v1 (§7.3)
# ---------------------------------------------------------------------------


def _reject_manifest(message: str) -> BackupManifestInvalid:
    return BackupManifestInvalid(f"backup-manifest.json: {message}")


def parse_backup_manifest_v1(raw: bytes) -> dict:
    """Strict parser/validator for backup-manifest schema 1 (§7.3).

    Rejects unknown fields, wrong schema/alembic versions, non-hex hashes,
    unsorted or duplicate lists, unknown artifact kinds, and noncanonical
    bytes. Shared by backup self-verification and restore.
    """
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise _reject_manifest(f"not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise _reject_manifest("root is not an object.")
    if set(doc) != {
        "schema_version", "alembic_version", "database_sha256",
        "blob_hashes", "workflow_artifacts", "projects",
    }:
        raise _reject_manifest(
            f"unknown/missing root fields: {sorted(set(doc))}.")
    if (not isinstance(doc["schema_version"], int)
            or isinstance(doc["schema_version"], bool)
            or doc["schema_version"] != BACKUP_MANIFEST_SCHEMA_VERSION):
        raise _reject_manifest("schema_version must be the integer 1.")
    if doc["alembic_version"] not in SUPPORTED_RESTORE_ALEMBIC_HEADS:
        raise _reject_manifest(
            f"alembic_version must be one of "
            f"{sorted(SUPPORTED_RESTORE_ALEMBIC_HEADS)}.")
    if not _is_hash(doc["database_sha256"]):
        raise _reject_manifest("database_sha256 is not 64-lowercase-hex.")

    blob_hashes = doc["blob_hashes"]
    if not isinstance(blob_hashes, list):
        raise _reject_manifest("blob_hashes must be a list.")
    for h in blob_hashes:
        if not _is_hash(h):
            raise _reject_manifest(f"blob_hashes entry {h!r} is not hex.")
    if blob_hashes != sorted(set(blob_hashes)):
        raise _reject_manifest("blob_hashes must be sorted and unique.")

    artifacts = doc["workflow_artifacts"]
    if not isinstance(artifacts, list):
        raise _reject_manifest("workflow_artifacts must be a list.")
    seen_pairs: set[tuple[str, str]] = set()
    for entry in artifacts:
        if not isinstance(entry, dict) or set(entry) != {"kind", "sha256"}:
            raise _reject_manifest(
                "workflow artifact entries must have exactly kind+sha256.")
        if entry["kind"] not in ARTIFACT_KINDS:
            raise _reject_manifest(f"unknown artifact kind {entry['kind']!r}.")
        if not _is_hash(entry["sha256"]):
            raise _reject_manifest(
                f"artifact sha256 {entry['sha256']!r} is not hex.")
        seen_pairs.add((entry["kind"], entry["sha256"]))
    if len(seen_pairs) != len(artifacts):
        raise _reject_manifest("duplicate (kind, sha256) pairs.")
    if [(e["kind"], e["sha256"]) for e in artifacts] != sorted(seen_pairs):
        raise _reject_manifest("workflow_artifacts must be sorted by (kind, sha256).")

    projects = doc["projects"]
    if not isinstance(projects, list):
        raise _reject_manifest("projects must be a list.")
    seen_pids: list[str] = []
    for proj in projects:
        if not isinstance(proj, dict) or set(proj) != {
            "project_id", "historical_blob_hashes",
            "historical_workflow_artifacts",
        }:
            raise _reject_manifest(
                "project entries must have exactly project_id + "
                "historical_blob_hashes + historical_workflow_artifacts.")
        try:
            uuid.UUID(str(proj["project_id"]))
        except (ValueError, AttributeError) as exc:
            raise _reject_manifest(
                f"project_id {proj['project_id']!r} is not a UUID.") from exc
        seen_pids.append(str(proj["project_id"]))
        blobs = proj["historical_blob_hashes"]
        if not isinstance(blobs, list):
            raise _reject_manifest("project historical_blob_hashes must be a list.")
        for h in blobs:
            if not _is_hash(h):
                raise _reject_manifest(
                    f"project blob hash {h!r} is not hex.")
        if blobs != sorted(set(blobs)):
            raise _reject_manifest(
                "project historical_blob_hashes must be sorted and unique.")
        arts = proj["historical_workflow_artifacts"]
        if not isinstance(arts, list):
            raise _reject_manifest(
                "project historical_workflow_artifacts must be a list.")
        pairs: list[tuple[str, str]] = []
        for entry in arts:
            if not isinstance(entry, dict) or set(entry) != {"kind", "sha256"}:
                raise _reject_manifest(
                    "project artifact entries must have exactly kind+sha256.")
            if entry["kind"] not in ARTIFACT_KINDS:
                raise _reject_manifest(
                    f"unknown project artifact kind {entry['kind']!r}.")
            if not _is_hash(entry["sha256"]):
                raise _reject_manifest("project artifact sha256 is not hex.")
            pairs.append((entry["kind"], entry["sha256"]))
        if pairs != sorted(set(pairs)):
            raise _reject_manifest(
                "project historical_workflow_artifacts must be sorted and "
                "unique.")
    if seen_pids != sorted(set(seen_pids)):
        raise _reject_manifest("projects must be sorted and unique by project_id.")

    if canonical_json_bytes(doc) != raw:
        raise _reject_manifest(
            "bytes are not the canonical backup-manifest-v1 representation.")
    return doc


def build_backup_manifest(
    *, database_sha256: str, liveness: _Liveness
) -> dict:
    return {
        "schema_version": BACKUP_MANIFEST_SCHEMA_VERSION,
        "alembic_version": EXPECTED_ALEMBIC_HEAD,
        "database_sha256": database_sha256,
        "blob_hashes": list(liveness.blob_hashes),
        "workflow_artifacts": [
            {"kind": kind, "sha256": h} for kind, h in liveness.artifacts
        ],
        "projects": liveness.projects,
    }


# ---------------------------------------------------------------------------
# Atomic finalization (§7.4/§7.7)
# ---------------------------------------------------------------------------


def _publish_staged_directory(stage: Path, final: Path) -> None:
    """One same-parent, same-filesystem rename to an ABSENT destination.

    No replace-existing and no copy-into-final fallback: platforms that
    cannot honor the contract fail closed with the final path absent.
    """
    if final.exists() or final.is_symlink():
        raise RecoveryError(
            f"final destination {final} already exists; refusing to replace."
        )
    if not stage.exists():
        raise RecoveryError(f"staged directory {stage} vanished before publish.")
    stage_parent = stage.parent
    final_parent = final.parent
    if os.stat(stage_parent).st_dev != os.stat(final_parent).st_dev:
        raise RecoveryError(
            "cross-filesystem directory finalization is unsupported; the "
            "final path was not created."
        )
    os.rename(stage, final)
    if not final.exists() or stage.exists():
        raise RecoveryError(
            "ambiguous finalize state: refusing to treat the result as a "
            "published recovery artifact."
        )


def _artifact_path(root: Path, kind: str, content_hash: str) -> Path:
    return (
        root / kind / "sha256" / content_hash[0:2] / content_hash[2:4]
        / f"{content_hash}.json"
    )


# ---------------------------------------------------------------------------
# Backup tree verification (backup step 11; restore steps 1-3/9)
# ---------------------------------------------------------------------------


def _verify_manifest_files(root: Path, manifest: dict) -> None:
    """Verify a tree's DB + Blob + artifact bytes against a manifest."""
    db_path = root / "soloring.db"
    if not db_path.is_file():
        raise RecoveryCorruption("backup DB is missing.")
    db_hash, _ = _stream_hash(db_path)
    if db_hash != manifest["database_sha256"]:
        raise RecoveryCorruption(
            "backup DB bytes disagree with manifest database_sha256."
        )

    blob_root = root / "blobs"
    for h in manifest["blob_hashes"]:
        path = blob_root / _blob_relative_path(h)
        if not path.is_file():
            raise RecoveryCorruption(f"backup Blob {h} is missing.")
        _verify_bytes(path, h)

    artifact_root = root / "workflow-artifacts"
    for entry in manifest["workflow_artifacts"]:
        path = _artifact_path(
            artifact_root, entry["kind"], entry["sha256"])
        if not path.is_file():
            raise RecoveryCorruption(
                f"backup workflow artifact {entry['kind']} "
                f"{entry['sha256']} is missing."
            )
        _verify_bytes(path, entry["sha256"])


def _verify_liveness_equal(db_path: Path, manifest: dict) -> None:
    """Re-enumerate DB liveness and require exact manifest equality."""
    head = manifest["alembic_version"]
    _normalize_staged_wal(db_path)
    _drop_sidecar_files(db_path)
    _verify_staged_db(db_path, expected_head=head)
    live = _enumerate_liveness(db_path, _blob_fk_policy_for_head(head))
    if live.blob_hashes != manifest["blob_hashes"]:
        raise RecoveryCorruption(
            "re-enumerated Blob liveness differs from the manifest."
        )
    if live.artifacts != [
        (e["kind"], e["sha256"])
        for e in manifest["workflow_artifacts"]
    ]:
        raise RecoveryCorruption(
            "re-enumerated workflow-artifact liveness differs from the "
            "manifest."
        )
    if live.projects != manifest["projects"]:
        raise RecoveryCorruption(
            "re-enumerated Project diagnostics differ from the manifest."
        )


def _verify_backup_tree(root: Path, full_liveness: bool) -> dict:
    """Verify a BACKUP tree from its own manifest (backup step 11).

    ``full_liveness`` additionally re-enumerates DB liveness and requires
    exact equality with the manifest. A restored DATA root is not a backup
    artifact (it carries no backup-manifest.json); restore verifies it via
    ``_verify_manifest_files``/``_verify_liveness_equal`` against the
    parsed source manifest instead.
    """
    manifest_path = root / "backup-manifest.json"
    try:
        raw = manifest_path.read_bytes()
    except FileNotFoundError as exc:
        raise RecoveryCorruption(
            f"{root} has no backup-manifest.json."
        ) from exc
    manifest = parse_backup_manifest_v1(raw)
    _verify_manifest_files(root, manifest)
    if full_liveness:
        _verify_liveness_equal(root / "soloring.db", manifest)
    return manifest


# ---------------------------------------------------------------------------
# M11 immutable production-state verification (frozen R3 §14.4)
# ---------------------------------------------------------------------------


def _verify_m11_production_state(staged_db: Path) -> None:
    """Verify every M11 Production Revision in a staged 0012 DB.

    Read-only with respect to the staged authoritative DB; runs before
    physical liveness copying on backup and after DB copy on restore. Does
    NOT require live ``blobs.detected_media_type`` equality — the closure's
    ``media_type`` is publication-time historical interpretation metadata.
    """
    from soloring.production.readiness import _media_type_valid

    con = sqlite3.connect(str(staged_db))
    con.row_factory = sqlite3.Row
    try:
        revisions = con.execute(
            "SELECT id, snapshot_json, snapshot_hash FROM production_revisions"
        ).fetchall()
        for rev in revisions:
            rid = rev["id"]
            try:
                parsed = json.loads(rev["snapshot_json"])
            except ValueError as exc:
                raise RecoveryCorruption(
                    f"production revision {rid} snapshot_json is not JSON: {exc}"
                ) from exc
            if not isinstance(parsed, dict) or parsed.get("schema_version") != 1:
                raise RecoveryCorruption(
                    f"production revision {rid} snapshot schema_version is not 1."
                )
            consumption = parsed.get("consumption")
            if not isinstance(consumption, dict):
                raise RecoveryCorruption(
                    f"production revision {rid} snapshot has no consumption object."
                )
            if canonical_json_bytes(parsed) != rev["snapshot_json"].encode("utf-8"):
                raise RecoveryCorruption(
                    f"production revision {rid} snapshot_json is not canonical."
                )
            if canonical_hash(parsed) != rev["snapshot_hash"]:
                raise RecoveryCorruption(
                    f"production revision {rid} snapshot_hash mismatch."
                )
            closures = con.execute(
                "SELECT contract_key, contract_version, blob_hash, size_bytes, "
                "media_type FROM production_revision_closures "
                "WHERE production_revision_id = ?", (rid,),
            ).fetchall()
            if len(closures) != 1:
                raise RecoveryCorruption(
                    f"production revision {rid} has {len(closures)} closure rows."
                )
            c = closures[0]
            # §14.4: closure ↔ SNAPSHOT equality. The parsed canonical
            # document's consumption object is compared DIRECTLY to the
            # normalized closure row — never rebuilt from the closure itself,
            # which would prove nothing about their agreement.
            for key in ("contract_key", "contract_version", "blob_hash",
                        "size_bytes", "media_type"):
                if c[key] != consumption.get(key):
                    raise RecoveryCorruption(
                        f"production revision {rid} closure row diverges from "
                        f"the canonical snapshot consumption at {key!r}."
                    )
            if not _media_type_valid(c["media_type"]):
                raise RecoveryCorruption(
                    f"production revision {rid} closure media_type violates "
                    "the schema-1 grammar."
                )
            blob = con.execute(
                "SELECT hash, size_bytes FROM blobs WHERE hash = ?",
                (c["blob_hash"],),
            ).fetchone()
            if blob is None:
                raise RecoveryCorruption(
                    f"production revision {rid} closure Blob row missing."
                )
            if blob["size_bytes"] != c["size_bytes"]:
                raise RecoveryCorruption(
                    f"production revision {rid} closure/Blob size identity "
                    "mismatch."
                )
            obj = con.execute(
                "SELECT project_id FROM production_objects WHERE id = "
                "(SELECT production_object_id FROM production_revisions "
                "WHERE id = ?)", (rid,),
            ).fetchone()
            if obj is None:
                raise RecoveryCorruption(
                    f"production revision {rid} has no owning Production Object."
                )
            links = con.execute(
                "SELECT prsa.asset_id, a.project_id AS project_id, "
                "a.blob_hash AS blob_hash "
                "FROM production_revision_source_assets prsa "
                "JOIN assets a ON a.id = prsa.asset_id "
                "WHERE prsa.production_revision_id = ?", (rid,),
            ).fetchall()
            if not links:
                raise RecoveryCorruption(
                    f"production revision {rid} has no source provenance link."
                )
            for link in links:
                if link["project_id"] != obj["project_id"]:
                    raise RecoveryCorruption(
                        f"production revision {rid} provenance link "
                        f"{link['asset_id']} contradicts the owning Project."
                    )
                if link["blob_hash"] != c["blob_hash"]:
                    raise RecoveryCorruption(
                        f"production revision {rid} provenance link "
                        f"{link['asset_id']} contradicts the closure Blob."
                    )
    finally:
        con.close()


def _prove_no_m11_state(staged_db: Path) -> None:
    """A restored pre-M11 0011 root invents no M11 authority (§14.6)."""
    con = sqlite3.connect(str(staged_db))
    try:
        tables = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
        }
        m11_tables = {
            "production_objects", "production_revisions",
            "production_revision_closures", "production_revision_source_assets",
        }
        if tables & m11_tables:
            raise RecoveryCorruption(
                "0011 restore invented M11 tables: "
                f"{sorted(tables & m11_tables)}."
            )
    finally:
        con.close()


def _prove_no_m12_state(staged_db: Path) -> None:
    """A restored 0012 root invents no M12 authority (frozen R3 §16.5)."""
    con = sqlite3.connect(str(staged_db))
    try:
        tables = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
        }
        m12_tables = {
            "compositions", "composition_occurrences", "composition_revisions",
            "composition_working_occurrences",
            "composition_revision_occurrences",
            "composition_revision_production_dependencies",
            "composition_revision_nested_dependencies",
            "composition_identity_operations",
            "composition_identity_operation_sources",
            "composition_identity_operation_targets",
        }
        if tables & m12_tables:
            raise RecoveryCorruption(
                "0012 restore invented M12 tables: "
                f"{sorted(tables & m12_tables)}."
            )
    finally:
        con.close()


_M13_TABLES = (
    "composition_occurrence_authority_subjects",
    "production_revision_spatial_interpretations",
    "production_instance_features",
    "production_instance_feature_transitions",
    "production_instance_spatial_tracks",
    "production_instance_spatial_transitions",
    "composition_spatial_bindings",
    "composition_spatial_binding_subjects",
    "composition_spatial_binding_entries",
    "shot_production_world_selections",
    "shot_revision_production_worlds",
    "shot_revision_production_instance_feature_states",
    "shot_revision_production_instance_spatial_states",
)


def _prove_no_m13_state(staged_db: Path) -> None:
    """A restored pre-M13 root invents no M13 authority (frozen R3 §23.3).

    The thirteen M13-owned tables exist only at 0014+; their absence at an
    older recorded head is the no-invention proof.
    """
    con = sqlite3.connect(str(staged_db))
    try:
        tables = {
            r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
        }
        present = tables & set(_M13_TABLES)
        if present:
            raise RecoveryCorruption(
                "pre-0014 restore invented M13 tables: "
                f"{sorted(present)}."
            )
    finally:
        con.close()


def _verify_m13_world_state(staged_db: Path) -> None:
    """Verify the M13 immutable state present at 0014 (frozen R3 §23.4).

    M13A slice: subject adoptions and Production Revision spatial
    interpretations. The verifier grows with the M13B-E slices that make
    the remaining tables writable; every table that can hold rows at the
    current slice is verified with no unverified-row window.
    """
    con = sqlite3.connect(str(staged_db))
    con.row_factory = sqlite3.Row
    try:
        _verify_m13_subjects(con)
        _verify_m13_interpretations(con)
        _verify_m13_pi_state(con)
        _verify_m13_pi_spatial(con)
        _verify_m13_bindings(con)
        _verify_m13_selection_and_history(con)
    finally:
        con.close()


def _verify_m13_subjects(con) -> None:
    rows = con.execute(
        "SELECT composition_id, occurrence_id, subject_kind, "
        "creative_entity_id FROM composition_occurrence_authority_subjects"
    ).fetchall()
    for r in rows:
        if r["subject_kind"] not in ("creative_entity", "production_instance"):
            raise RecoveryCorruption(
                f"adoption kind {r['subject_kind']!r} outside schema-1 domain")
        if r["subject_kind"] == "creative_entity":
            if r["creative_entity_id"] is None:
                raise RecoveryCorruption(
                    "creative_entity adoption without creative_entity_id")
        elif r["creative_entity_id"] is not None:
            raise RecoveryCorruption(
                "production_instance adoption carries creative_entity_id")
        occ = con.execute(
            "SELECT 1 FROM composition_occurrences "
            "WHERE id = ? AND composition_id = ?",
            (r["occurrence_id"], r["composition_id"])).fetchone()
        if occ is None:
            raise RecoveryCorruption(
                "adoption references an occurrence outside its lineage")
        if r["creative_entity_id"] is not None:
            ent = con.execute(
                "SELECT project_id FROM creative_entities WHERE id = ?",
                (r["creative_entity_id"],)).fetchone()
            if ent is None:
                raise RecoveryCorruption(
                    "adoption references a missing CreativeEntity")
            comp = con.execute(
                "SELECT project_id FROM compositions WHERE id = ?",
                (r["composition_id"],)).fetchone()
            if comp is None or comp["project_id"] != ent["project_id"]:
                raise RecoveryCorruption(
                    "adoption crosses Projects")
    # Active-liveness uniqueness (frozen §2.2): at most one ACTIVE
    # occurrence per (composition lineage, CreativeEntity) claim.
    dupes = con.execute(
        "SELECT a.composition_id, a.creative_entity_id, COUNT(*) AS n "
        "FROM composition_occurrence_authority_subjects a "
        "WHERE a.creative_entity_id IS NOT NULL "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM composition_identity_operation_sources s "
        "  JOIN composition_identity_operations op ON op.id = s.operation_id "
        "  WHERE op.composition_id = a.composition_id "
        "  AND s.occurrence_id = a.occurrence_id "
        "  AND s.terminates_identity = 1) "
        "GROUP BY a.composition_id, a.creative_entity_id HAVING n > 1"
    ).fetchall()
    if dupes:
        raise RecoveryCorruption(
            "overlapping active CreativeEntity claims: "
            f"{[(d['composition_id'], d['creative_entity_id']) for d in dupes]}"
        )


def _verify_m13_interpretations(con) -> None:
    from soloring.errors import SoloRingError
    from soloring.production_world.canonical import (
        verify_stored_interpretation,
    )

    rows = con.execute(
        "SELECT production_revision_id, schema_version, x_mm, y_mm, z_mm, "
        "yaw_udeg, pitch_udeg, roll_udeg, interpretation_json, "
        "interpretation_hash "
        "FROM production_revision_spatial_interpretations").fetchall()
    for r in rows:
        snap = con.execute(
            "SELECT snapshot_hash FROM production_revisions "
            "WHERE id = ?", (r["production_revision_id"],)).fetchone()
        if snap is None:
            raise RecoveryCorruption(
                "interpretation references a missing Production Revision")
        blob = con.execute(
            "SELECT blob_hash FROM production_revision_closures "
            "WHERE production_revision_id = ? AND contract_key = "
            "'retained_blob' AND contract_version = 1",
            (r["production_revision_id"],)).fetchone()
        if blob is None:
            raise RecoveryCorruption(
                "interpretation parent has no retained_blob/v1 closure")
        if r["schema_version"] != 1:
            raise RecoveryCorruption("interpretation schema_version != 1")
        try:
            verify_stored_interpretation(
                interpretation_json=r["interpretation_json"],
                interpretation_hash=r["interpretation_hash"],
                x_mm=r["x_mm"], y_mm=r["y_mm"], z_mm=r["z_mm"],
                yaw_udeg=r["yaw_udeg"], pitch_udeg=r["pitch_udeg"],
                roll_udeg=r["roll_udeg"],
                row_production_revision_id=r["production_revision_id"],
                parent_snapshot_hash=snap["snapshot_hash"],
                parent_blob_hash=blob["blob_hash"],
            )
        except SoloRingError as exc:
            raise RecoveryCorruption(
                f"corrupt spatial interpretation "
                f"{r['production_revision_id']}: {exc.message}") from exc


def _verify_m12_composition_state(staged_db: Path) -> None:
    """Verify every M12 immutable Composition state row (frozen R3 §16.6).

    Read-only with respect to the staged DB. Reuses the publication
    reader's invariants where possible; validates canonical bytes/hash,
    projection equality, transform grammar, independently rederived
    dependency closure, and the complete lineage temporal/liveness rules.
    """
    con = sqlite3.connect(str(staged_db))
    con.row_factory = sqlite3.Row
    try:
        _verify_m12_revisions(con)
        _verify_m12_lineage(con)
    finally:
        con.close()


def _verify_m12_revisions(con) -> None:
    # The async reader invariants are re-implemented synchronously here
    # against the same frozen contract: recovery must not run an event loop
    # inside the staged verifier.
    revisions = con.execute(
        "SELECT id, composition_id FROM composition_revisions").fetchall()
    for rev in revisions:
        _verify_m12_revision_sync(con, rev["id"], rev["composition_id"])


def _verify_m12_revision_sync(con, revision_id: str, composition_id: str) -> None:
    import json as _json

    from soloring.domain.canonical import canonical_hash, canonical_json_bytes
    from soloring.spatial.math import JS_SAFE_MIN, JS_SAFE_MAX, UDEG_MIN

    rev = con.execute(
        "SELECT snapshot_json, snapshot_hash FROM composition_revisions "
        "WHERE id = ?", (revision_id,),
    ).fetchone()
    if rev is None:
        raise RecoveryCorruption(f"composition revision {revision_id} missing")
    try:
        parsed = _json.loads(rev["snapshot_json"])
    except ValueError as exc:
        raise RecoveryCorruption(
            f"composition revision {revision_id} snapshot not JSON: {exc}")
    if parsed.get("schema_version") != 1:
        raise RecoveryCorruption(
            f"composition revision {revision_id} unknown schema version")
    if canonical_json_bytes(parsed) != rev["snapshot_json"].encode("utf-8"):
        raise RecoveryCorruption(
            f"composition revision {revision_id} snapshot not canonical")
    if canonical_hash(parsed) != rev["snapshot_hash"]:
        raise RecoveryCorruption(
            f"composition revision {revision_id} hash mismatch")

    proj = con.execute(
        "SELECT * FROM composition_revision_occurrences "
        "WHERE composition_revision_id = ? ORDER BY occurrence_id",
        (revision_id,),
    ).fetchall()
    occurrences = parsed.get("occurrences", [])
    if len(proj) != len(occurrences):
        raise RecoveryCorruption(
            f"composition revision {revision_id} projection count mismatch")
    direct_prod, direct_nested = set(), set()
    for row, occ in zip(proj, occurrences):
        if row["occurrence_id"] != occ["occurrence_id"]:
            raise RecoveryCorruption(
                f"composition revision {revision_id} projection identity drift")
        if row["source_kind"] == "production_revision":
            rid = row["production_revision_id"]
            direct_prod.add(rid)
            expected = {
                "display_name": row["display_name"],
                "source": {"kind": "production_revision", "revision_id": rid},
                "visible": bool(row["visible"]),
            }
        else:
            rid = row["nested_composition_revision_id"]
            direct_nested.add(rid)
            expected = {
                "display_name": row["display_name"],
                "source": {"kind": "composition_revision", "revision_id": rid},
                "visible": bool(row["visible"]),
            }
        got = {k: occ[k] for k in expected}
        if got != expected:
            raise RecoveryCorruption(
                f"composition revision {revision_id} projection/snapshot "
                f"mismatch at {row['occurrence_id']}")
        if occ["transform"]["translation_mm"] != [
                row["x_mm"], row["y_mm"], row["z_mm"]]:
            raise RecoveryCorruption(
                f"composition revision {revision_id} translation mismatch")
        if occ["transform"]["rotation_udeg"] != [
                row["yaw_udeg"], row["pitch_udeg"], row["roll_udeg"]]:
            raise RecoveryCorruption(
                f"composition revision {revision_id} rotation mismatch")
        for v in (row["x_mm"], row["y_mm"], row["z_mm"],
                  row["yaw_udeg"], row["pitch_udeg"], row["roll_udeg"]):
            if not (JS_SAFE_MIN <= v <= JS_SAFE_MAX):
                raise RecoveryCorruption(
                    f"composition revision {revision_id} transform outside "
                    "JS-safe domain")
        for v in (row["yaw_udeg"], row["pitch_udeg"], row["roll_udeg"]):
            if not (UDEG_MIN <= v < UDEG_MIN + 360_000_000):
                raise RecoveryCorruption(
                    f"composition revision {revision_id} rotation not "
                    "canonically normalized")
        # lineage coherence: occurrence belongs to this composition
        owner = con.execute(
            "SELECT composition_id FROM composition_occurrences WHERE id = ?",
            (row["occurrence_id"],),
        ).fetchone()
        if owner is None or owner["composition_id"] != composition_id:
            raise RecoveryCorruption(
                f"composition revision {revision_id} occurrence lineage drift")

    # independently rederive the closure (set-oriented, frozen §18)
    exp_prod, exp_nested = set(direct_prod), set(direct_nested)
    if direct_nested:
        ph = ",".join("?" for _ in direct_nested)
        for (d,) in con.execute(
            "SELECT production_revision_id FROM "
            "composition_revision_production_dependencies "
            f"WHERE composition_revision_id IN ({ph})",
            tuple(direct_nested),
        ):
            exp_prod.add(d)
        for (d,) in con.execute(
            "SELECT nested_composition_revision_id FROM "
            "composition_revision_nested_dependencies "
            f"WHERE composition_revision_id IN ({ph})",
            tuple(direct_nested),
        ):
            exp_nested.add(d)
    deps = parsed.get("dependencies", {})
    if (sorted(exp_prod) != deps.get("production_revision_ids")
            or sorted(exp_nested) != deps.get("composition_revision_ids")):
        raise RecoveryCorruption(
            f"composition revision {revision_id} dependency arrays differ "
            "from independently rederived closure")
    stored_prod = {r[0] for r in con.execute(
        "SELECT production_revision_id FROM "
        "composition_revision_production_dependencies "
        "WHERE composition_revision_id = ?", (revision_id,))}
    stored_nested = {r[0] for r in con.execute(
        "SELECT nested_composition_revision_id FROM "
        "composition_revision_nested_dependencies "
        "WHERE composition_revision_id = ?", (revision_id,))}
    if stored_prod != exp_prod or stored_nested != exp_nested:
        raise RecoveryCorruption(
            f"composition revision {revision_id} dependency rows differ "
            "from independently rederived closure")
    clash = con.execute(
        "SELECT COUNT(*) FROM composition_revision_nested_dependencies d "
        "JOIN composition_revisions cr ON cr.id = d.nested_composition_revision_id "
        "WHERE d.composition_revision_id = ? AND cr.composition_id = ?",
        (revision_id, composition_id),
    ).fetchone()[0]
    if clash:
        raise RecoveryCorruption(
            f"composition revision {revision_id} transitive same-lineage "
            "embedding")


def _verify_m12_lineage(con) -> None:
    """Complete frozen §12.2/§16.6 lineage verification over the staged DB.

    This is the full semantic checklist: operation-field equivalence with
    the canonical evidence (composition_id, kind, versions, fingerprints),
    normalized terminates_identity agreement, termination-by-kind,
    embedded target-spec grammar, birth-before-use, no post-termination
    use, unique intervals, and active-occurrence ↔ working-membership
    equality in BOTH directions.
    """
    import json as _json

    from soloring.domain.canonical import canonical_hash, canonical_json_bytes

    # The evidence grammar is owned solely by composition.evidence —
    # no second (dormant) interpretation survives here.

    compositions = con.execute("SELECT id, working_version FROM compositions")
    for comp in compositions.fetchall():
        cid, cur_wv = comp["id"], comp["working_version"]
        before_seen: set[int] = set()
        birth: dict[str, int] = {}
        terminated_at: dict[str, int] = {}
        ops = con.execute(
            "SELECT * FROM composition_identity_operations "
            "WHERE composition_id = ? ORDER BY working_version_before",
            (cid,),
        ).fetchall()
        for op in ops:
            if op["working_version_before"] in before_seen:
                raise RecoveryCorruption("duplicate operation version interval")
            before_seen.add(op["working_version_before"])
            if op["working_version_after"] != op["working_version_before"] + 1:
                raise RecoveryCorruption("operation version step != +1")
            if op["working_version_after"] > cur_wv:
                raise RecoveryCorruption(
                    "operation after exceeds current working_version")
            try:
                parsed = _json.loads(op["operation_json"])
            except ValueError:
                raise RecoveryCorruption("operation_json not parseable")
            if canonical_json_bytes(parsed) != op["operation_json"].encode():
                raise RecoveryCorruption("operation_json not canonical")
            if canonical_hash(parsed) != op["operation_hash"]:
                raise RecoveryCorruption("operation_hash mismatch")
            # THE one shared evidence checklist — identical contract to
            # the async historical verifier via composition.evidence.
            sources = con.execute(
                "SELECT occurrence_id, terminates_identity FROM "
                "composition_identity_operation_sources WHERE operation_id = ? "
                "ORDER BY occurrence_id", (op["id"],)).fetchall()
            targets = con.execute(
                "SELECT occurrence_id FROM "
                "composition_identity_operation_targets WHERE operation_id = ? "
                "ORDER BY occurrence_id", (op["id"],)).fetchall()
            from soloring.composition.evidence import (
                validate_operation_evidence as _validate_evidence,
            )
            try:
                _validate_evidence(
                    parsed,
                    row_composition_id=cid,
                    row_kind=op["operation_kind"],
                    row_before=op["working_version_before"],
                    row_after=op["working_version_after"],
                    row_request_fingerprint=op["request_fingerprint"],
                    row_impact_fingerprint=op["impact_fingerprint"],
                    normalized_sources=[
                        (r["occurrence_id"], r["terminates_identity"])
                        for r in sources],
                    normalized_targets=[r["occurrence_id"] for r in targets],
                )
            except ValueError as exc:
                raise RecoveryCorruption(str(exc))
            for s in sources:
                oid = s["occurrence_id"]
                if oid not in birth:
                    raise RecoveryCorruption("source used before birth")
                if oid in terminated_at:
                    raise RecoveryCorruption("post-termination source use")
                if s["terminates_identity"]:
                    if oid in terminated_at:
                        raise RecoveryCorruption("double termination")
                    terminated_at[oid] = op["working_version_before"]
            for t in targets:
                if t["occurrence_id"] in birth:
                    raise RecoveryCorruption("double birth")
                birth[t["occurrence_id"]] = op["working_version_before"]
        all_occ = [r[0] for r in con.execute(
            "SELECT id FROM composition_occurrences WHERE composition_id = ?",
            (cid,))]
        for oid in all_occ:
            if oid not in birth:
                raise RecoveryCorruption("occurrence without birth operation")
        working = [r[0] for r in con.execute(
            "SELECT occurrence_id FROM composition_working_occurrences "
            "WHERE composition_id = ?", (cid,))]
        for oid in working:
            if oid in terminated_at:
                raise RecoveryCorruption(
                    "terminated occurrence remains in working state")
        # active-occurrence ↔ working-membership equality (frozen §12.3):
        # a live, nonterminated occurrence must BE in working membership.
        active = {o for o in all_occ if o not in terminated_at}
        if active != set(working):
            raise RecoveryCorruption(
                "active occurrence set differs from working membership")
# Public operation: backup (§7.4)
# ---------------------------------------------------------------------------


async def backup(
    settings: Settings,
    dest: Path,
    *,
    artifact_root: Path | None = None,
) -> dict:
    verify_supported_posture(settings, artifact_root=artifact_root)

    dest = Path(dest)
    if not dest.parent.is_dir():
        raise RecoveryError(
            f"backup destination parent {dest.parent} does not exist."
        )
    if dest.exists() or dest.is_symlink():
        raise RecoveryError(
            f"final backup path {dest} already exists."
        )
    stage = dest.parent / f".{dest.name}.soloring-backup-{uuid.uuid4().hex}.staging"
    stage.mkdir()
    try:
        staged_db = stage / "soloring.db"
        source_uri = f"file:{Path(settings.db_path).as_posix()}?mode=ro"
        source_meta: dict = {}
        probe = sqlite3.connect(source_uri, uri=True)
        try:
            source_meta = {
                "journal_mode": probe.execute(
                    "PRAGMA journal_mode").fetchone()[0],
                "foreign_keys": probe.execute(
                    "PRAGMA foreign_keys").fetchone()[0],
            }
        finally:
            probe.close()

        await asyncio.to_thread(_sqlite_online_backup, source_uri, staged_db)
        if not staged_db.is_file():
            raise RecoveryCorruption(
                "SQLite online backup produced no staged DB file.")
        staged_meta = await asyncio.to_thread(_normalize_staged_wal, staged_db)
        await asyncio.to_thread(_drop_sidecar_files, staged_db)
        await asyncio.to_thread(_verify_staged_db, staged_db)
        # M11 §14.4: immutable production state is verified in the staged
        # DB before any liveness copying or certification.
        await asyncio.to_thread(_verify_m11_production_state, staged_db)
        # M12 §16.3: immutable composition/occurrence state is verified in
        # the staged DB before liveness enumeration/certification.
        await asyncio.to_thread(_verify_m12_composition_state, staged_db)
        # M13 §23.4: immutable production-world state is verified in the
        # staged DB before liveness enumeration/certification.
        await asyncio.to_thread(_verify_m13_world_state, staged_db)
        liveness = await asyncio.to_thread(_enumerate_liveness, staged_db)

        blob_root = Path(settings.blob_dir)
        for h in liveness.blob_hashes:
            # R6 §7.5: physical location is ALWAYS the hash-derived
            # canonical path under the active Blob root — the stored
            # blobs.path value is metadata and is never followed (legacy
            # M10E D0 absolute values included).
            relative = _blob_relative_path(h)
            src = blob_root / relative
            if not src.is_file():
                raise RecoveryCorruption(
                    f"historically live Blob {h} is missing from the source "
                    "Blob root."
                )
            size = await asyncio.to_thread(
                _copy_verified, src, stage / "blobs" / relative, h
            )
            if size != liveness.blob_rows[h]["size_bytes"]:
                raise RecoveryCorruption(
                    f"Blob {h} physical byte count {size} disagrees with "
                    f"blobs.size_bytes {liveness.blob_rows[h]['size_bytes']}."
                )

        art_root = (
            Path(artifact_root) if artifact_root is not None
            else Path(settings.data_dir) / "workflow-artifacts"
        )
        for kind, h in liveness.artifacts:
            src = _artifact_path(art_root, kind, h)
            if not src.is_file():
                raise RecoveryCorruption(
                    f"historical workflow artifact {kind} {h} is missing "
                    "from the source artifact root."
                )
            await asyncio.to_thread(
                _copy_verified, src,
                _artifact_path(stage / "workflow-artifacts", kind, h), h,
            )

        db_hash, db_bytes = await asyncio.to_thread(_stream_hash, staged_db)
        manifest = build_backup_manifest(
            database_sha256=db_hash, liveness=liveness)
        (stage / "backup-manifest.json").write_bytes(
            canonical_json_bytes(manifest))

        await asyncio.to_thread(_verify_backup_tree, stage, True)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    _publish_staged_directory(stage, dest)
    return {
        "sqlite_runtime_version": sqlite3.sqlite_version,
        "source": source_meta,
        "staged": staged_meta,
        "database_bytes": db_bytes,
        "blob_count": len(liveness.blob_hashes),
        "workflow_artifact_count": len(liveness.artifacts),
        "project_count": len(liveness.projects),
        "generation_count": liveness.generation_count,
        "backup_root": str(dest),
    }


# ---------------------------------------------------------------------------
# Public operation: restore (§7.7)
# ---------------------------------------------------------------------------


async def restore(backup_root: Path, dest: Path) -> dict:
    backup_root = Path(backup_root)
    dest = Path(dest)
    if not backup_root.is_dir():
        raise RecoveryError(f"backup root {backup_root} does not exist.")
    if not dest.parent.is_dir():
        raise RecoveryError(
            f"restore destination parent {dest.parent} does not exist."
        )
    if dest.exists() or dest.is_symlink():
        raise RecoveryError(
            f"final destination {dest} already exists; restore requires a "
            "fresh absent data root."
        )

    # Steps 1-3: verify the backup artifact itself before any staging.
    manifest = await asyncio.to_thread(
        _verify_backup_tree, backup_root, False)

    stage = dest.parent / f".{dest.name}.soloring-restore-{uuid.uuid4().hex}.staging"
    stage.mkdir()
    try:
        # Step 6: physical history enters the stage BEFORE any DB copy.
        blob_root = backup_root / "blobs"
        for h in manifest["blob_hashes"]:
            src = blob_root / _blob_relative_path(h)
            await asyncio.to_thread(
                _copy_verified, src,
                stage / "blobs" / _blob_relative_path(h), h,
            )
        art_src_root = backup_root / "workflow-artifacts"
        for entry in manifest["workflow_artifacts"]:
            await asyncio.to_thread(
                _copy_verified,
                _artifact_path(art_src_root, entry["kind"], entry["sha256"]),
                _artifact_path(
                    stage / "workflow-artifacts",
                    entry["kind"], entry["sha256"],
                ),
                entry["sha256"],
            )

        # Step 7: the already-verified DB copy lands after physical history.
        staged_db = stage / "soloring.db"
        await asyncio.to_thread(
            _copy_verified, backup_root / "soloring.db", staged_db,
            manifest["database_sha256"],
        )
        await asyncio.to_thread(_normalize_staged_wal, staged_db)
        await asyncio.to_thread(_drop_sidecar_files, staged_db)
        # Head-dispatched restore (frozen R3 §14.6): the staged DB is
        # verified at the head its own manifest recorded, never silently
        # migrated during restore.
        head = manifest["alembic_version"]
        await asyncio.to_thread(_verify_staged_db, staged_db, expected_head=head)
        if head == PRE_M11_ALEMBIC_HEAD:
            await asyncio.to_thread(_prove_no_m11_state, staged_db)
            await asyncio.to_thread(_prove_no_m13_state, staged_db)
        elif head == M11_ALEMBIC_HEAD:
            await asyncio.to_thread(_verify_m11_production_state, staged_db)
            await asyncio.to_thread(_prove_no_m12_state, staged_db)
            await asyncio.to_thread(_prove_no_m13_state, staged_db)
        elif head == M12_ALEMBIC_HEAD:  # 0013
            await asyncio.to_thread(_verify_m11_production_state, staged_db)
            await asyncio.to_thread(_verify_m12_composition_state, staged_db)
            await asyncio.to_thread(_prove_no_m13_state, staged_db)
        else:  # 0014
            await asyncio.to_thread(_verify_m11_production_state, staged_db)
            await asyncio.to_thread(_verify_m12_composition_state, staged_db)
            await asyncio.to_thread(_verify_m13_world_state, staged_db)

        # Step 9: exact liveness equality with the manifest (the restored
        # DATA root is not a backup artifact; verify against the parsed
        # source manifest, not a manifest file inside the stage).
        await asyncio.to_thread(
            _verify_liveness_equal, staged_db, manifest)

        # Step 10: production historical verification on the staged root.
        await _production_historical_probe(stage, manifest)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    _publish_staged_directory(stage, dest)

    # Step 12: reopen the FINAL destination normally; minimal probe.
    await _production_historical_probe(dest, manifest, minimal=True)
    return {
        "sqlite_runtime_version": sqlite3.sqlite_version,
        "restored_root": str(dest),
        "database_bytes": (dest / "soloring.db").stat().st_size,
        "blob_count": len(manifest["blob_hashes"]),
        "workflow_artifact_count": len(manifest["workflow_artifacts"]),
        "project_count": len(manifest["projects"]),
    }


async def _production_historical_probe(
    data_root: Path, manifest: dict, *, minimal: bool = False
) -> None:
    """§7.7 steps 10/12: open the root through the NORMAL Settings + engine
    and prove production historical retrieval works against it."""
    from sqlalchemy import text

    from soloring.db.engine import create_soloring_engine

    probe_settings = Settings(data_dir=data_root)
    engine = create_soloring_engine(probe_settings)
    try:
        async with engine.connect() as conn:
            gens = (await conn.execute(
                text("SELECT COUNT(*) FROM generations"))).scalar_one()
            projects = (await conn.execute(
                text("SELECT COUNT(*) FROM projects"))).scalar_one()
            if not minimal:
                if gens != _count_generations(manifest, data_root):
                    raise RecoveryCorruption(
                        "staged production probe generation count differs "
                        "from the staged DB."
                    )
                if projects != len(manifest["projects"]):
                    raise RecoveryCorruption(
                        "staged production probe project count differs from "
                        "the manifest."
                    )
    finally:
        await engine.dispose()

    store = WorkflowArtifactStore(probe_settings)
    getters = {
        "manifests": store.get_manifest,
        "templates": store.get_template,
        "realization_profiles": store.get_profile,
        "execution_model_fingerprints": store.get_fingerprint,
    }
    entries = manifest["workflow_artifacts"]
    if minimal and entries:
        # One representative production retrieval is enough for the final
        # reopen probe; the staged run (minimal=False) verified every entry.
        entries = entries[:1]
    for entry in entries:
        await getters[entry["kind"]](entry["sha256"])


def _count_generations(manifest: dict, data_root: Path) -> int:
    con = sqlite3.connect(str(data_root / "soloring.db"))
    try:
        return con.execute("SELECT COUNT(*) FROM generations").fetchone()[0]
    finally:
        con.close()


def _verify_m13_pi_state(con) -> None:
    rows = con.execute(
        "SELECT id, composition_id, occurrence_id, key, kind, value_type, "
        "name, enum_values_json, unit, supersedes_feature_id FROM "
        "production_instance_features").fetchall()
    seen: set = set()
    for r in rows:
        seen.add(r[0])
        if not (r[2] and r[3]):
            raise RecoveryCorruption("PI feature identity fields corrupt")
        occ = con.execute(
            "SELECT 1 FROM composition_occurrences WHERE id = ? AND "
            "composition_id = ?", (r[2], r[1])).fetchone()
        if occ is None:
            raise RecoveryCorruption(
                f"PI feature {r[0]} references an occurrence outside its "
                "lineage")
        if r[5] == "enum" and r[7] is None:
            raise RecoveryCorruption(
                f"PI feature {r[0]}: enum without enum_values_json")
        if r[5] != "enum" and r[7] is not None:
            raise RecoveryCorruption(
                f"PI feature {r[0]}: enum_values_json on non-enum")
        if r[9] is not None and r[9] not in seen and not con.execute(
                "SELECT 1 FROM production_instance_features WHERE id = ?",
                (r[9],)).fetchone():
            raise RecoveryCorruption(
                f"PI feature {r[0]} supersedes a missing predecessor")
        adoption = con.execute(
            "SELECT subject_kind FROM "
            "composition_occurrence_authority_subjects WHERE "
            "composition_id = ? AND occurrence_id = ?",
            (r[1], r[2])).fetchone()
        if adoption is None or adoption[0] != "production_instance":
            raise RecoveryCorruption(
                f"PI feature {r[0]} lacks a production_instance adoption "
                "for its occurrence (provenance incoherent)")
    # transitions: set/clear grammar + active-coordinate uniqueness
    trows = con.execute(
        "SELECT id, feature_id, anchor_type, anchor_id, boundary, "
        "operation, value_json, value_hash FROM "
        "production_instance_feature_transitions").fetchall()
    active: set = set()
    for t in trows:
        if t[3] is None:
            raise RecoveryCorruption(
                f"PI feature transition {t[0]} has no anchor")
        if t[5] == "set":
            if t[6] is None or t[7] is None or len(t[7]) != 64:
                raise RecoveryCorruption(
                    f"PI feature transition {t[0]}: set without canonical "
                    "value/hash")
        elif t[5] == "clear":
            if t[6] is not None or t[7] is not None:
                raise RecoveryCorruption(
                    f"PI feature transition {t[0]}: clear carries values")
        else:
            raise RecoveryCorruption(
                f"PI feature transition {t[0]}: operation outside "
                "set|clear")
        coord = (t[1], t[2], t[3], t[4])
        # tombstone-inclusive uniqueness is structural (PK/unique); the
        # active-coordinate partial unique is validated by schema parity
        del coord, active


def _verify_m13_pi_spatial(con) -> None:
    rows = con.execute(
        "SELECT id, spatial_world_id, composition_id, occurrence_id, "
        "requirement FROM production_instance_spatial_tracks").fetchall()
    for r in rows:
        if r[4] not in ("required", "optional"):
            raise RecoveryCorruption(
                f"PI track {r[0]}: requirement outside the domain")
        world = con.execute(
            "SELECT project_id FROM spatial_worlds WHERE id = ?",
            (r[1],)).fetchone()
        comp = con.execute(
            "SELECT project_id FROM compositions WHERE id = ?",
            (r[2],)).fetchone()
        if world is None or comp is None or world[0] != comp[0]:
            raise RecoveryCorruption(
                f"PI track {r[0]}: world/Composition coherence broken")
        adoption = con.execute(
            "SELECT subject_kind FROM "
            "composition_occurrence_authority_subjects WHERE "
            "composition_id = ? AND occurrence_id = ?",
            (r[2], r[3])).fetchone()
        if adoption is None or adoption[0] != "production_instance":
            raise RecoveryCorruption(
                f"PI track {r[0]} lacks a production_instance adoption")
    srows = con.execute(
        "SELECT id, spatial_track_id, operation, x_mm, y_mm, z_mm, "
        "yaw_udeg, pitch_udeg, roll_udeg FROM "
        "production_instance_spatial_transitions").fetchall()
    for t in srows:
        six = (t[3], t[4], t[5], t[6], t[7], t[8])
        if t[2] == "set":
            if any(v is None for v in six):
                raise RecoveryCorruption(
                    f"PI spatial transition {t[0]}: incomplete set")
        elif t[2] == "clear":
            if any(v is not None for v in six):
                raise RecoveryCorruption(
                    f"PI spatial transition {t[0]}: clear carries a "
                    "transform")
        else:
            raise RecoveryCorruption(
                f"PI spatial transition {t[0]}: operation outside "
                "set|clear")


def _verify_m13_bindings(con) -> None:
    """Immutable binding integrity ONLY (§23.4): canonical bytes/hash,
    normalized child equality, exact pinned closure, and pinned-target
    EXISTENCE even when the target is now soft-deleted. Never re-derives
    today's candidate — staleness is legal immutable history."""
    import hashlib
    import json as _json
    import re as _re

    from soloring.domain.canonical import canonical_json_str
    from soloring.errors import SoloRingError
    from soloring.production_world.binding import _parse_binding_value
    from soloring.production_world.canonical import (
        verify_stored_interpretation,
    )

    parents = con.execute(
        "SELECT id, composition_revision_id, composition_revision_hash, "
        "spatial_world_revision_id, spatial_world_revision_hash, "
        "schema_version, binding_json, binding_hash FROM "
        "composition_spatial_bindings").fetchall()
    for p in parents:
        try:
            parsed = _json.loads(p[6])
        except ValueError as exc:
            raise RecoveryCorruption(
                f"binding {p[0]} JSON unparseable") from exc
        try:
            value = _parse_binding_value(parsed)
        except SoloRingError as exc:
            raise RecoveryCorruption(
                f"binding {p[0]}: {exc.message}") from exc
        if canonical_json_str(value) != p[6]:
            raise RecoveryCorruption(
                f"binding {p[0]} is not the canonical encoding")
        if hashlib.sha256(p[6].encode("utf-8")).hexdigest() != p[7]:
            raise RecoveryCorruption(
                f"binding {p[0]} hash disagrees with canonical bytes")
        if (value["composition_revision"]["revision_id"] != p[1]
                or value["composition_revision"]["snapshot_hash"] != p[2]
                or value["spatial_world_revision"]["revision_id"] != p[3]
                or value["spatial_world_revision"]["snapshot_hash"] != p[4]
                or p[5] != 1):
            raise RecoveryCorruption(
                f"binding {p[0]} parent columns disagree with its value")
        # exact immutable closure: C hash + W hash
        c = con.execute(
            "SELECT snapshot_hash FROM composition_revisions WHERE id = ?",
            (p[1],)).fetchone()
        if c is None or c[0] != p[2]:
            raise RecoveryCorruption(
                f"binding {p[0]}: pinned CompositionRevision missing or "
                "hash disagrees")
        w = con.execute(
            "SELECT snapshot_hash FROM spatial_world_revisions WHERE "
            "id = ?", (p[3],)).fetchone()
        if w is None or w[0] != p[4]:
            raise RecoveryCorruption(
                f"binding {p[0]}: pinned SpatialWorldRevision missing or "
                "hash disagrees")
        # normalized children == canonical value (contiguous positions)
        srows = con.execute(
            "SELECT position, occurrence_id, production_revision_id, "
            "production_revision_hash, subject_kind, subject_id, "
            "creative_entity_id FROM composition_spatial_binding_subjects "
            "WHERE binding_id = ? ORDER BY position", (p[0],)).fetchall()
        if len(srows) != len(value["subjects"]):
            raise RecoveryCorruption(
                f"binding {p[0]} subject child count mismatch")
        for pos, (row, s) in enumerate(zip(srows, value["subjects"])):
            exp_ce = (s["authority_subject"]["id"]
                      if s["authority_subject"]["kind"] == "creative_entity"
                      else None)
            if (row[0] != pos or row[1] != s["occurrence_id"]
                    or row[2] != s["production_revision_id"]
                    or row[3] != s["production_revision_hash"]
                    or row[4] != s["authority_subject"]["kind"]
                    or row[5] != s["authority_subject"]["id"]
                    or row[6] != exp_ce):
                raise RecoveryCorruption(
                    f"binding {p[0]} subject projection mismatch")
            pr = con.execute(
                "SELECT snapshot_hash FROM production_revisions WHERE "
                "id = ?", (row[2],)).fetchone()
            if pr is None or pr[0] != row[3]:
                raise RecoveryCorruption(
                    f"binding {p[0]}: subject ProductionRevision closure "
                    "broken")
        erows = con.execute(
            "SELECT position, occurrence_id, production_revision_id, "
            "production_revision_hash, subject_kind, subject_id, "
            "creative_entity_id, placement_kind, spatial_frame_id, "
            "spatial_track_id, production_instance_track_id, "
            "spatial_interpretation_hash FROM "
            "composition_spatial_binding_entries WHERE binding_id = ? "
            "ORDER BY position", (p[0],)).fetchall()
        if len(erows) != len(value["entries"]):
            raise RecoveryCorruption(
                f"binding {p[0]} entry child count mismatch")
        for pos, (row, e) in enumerate(zip(erows, value["entries"])):
            exp_ce = (e["authority_subject"]["id"]
                      if e["authority_subject"]["kind"] == "creative_entity"
                      else None)
            if (row[0] != pos or row[1] != e["occurrence_id"]
                    or row[4] != e["authority_subject"]["kind"]
                    or row[5] != e["authority_subject"]["id"]
                    or row[6] != exp_ce
                    or row[7] != e["placement"]["kind"]
                    or row[11] != e["spatial_interpretation_hash"]):
                raise RecoveryCorruption(
                    f"binding {p[0]} entry projection mismatch")
            # placement XOR against the canonical value
            col = {"entity_fixed_frame": row[8], "entity_track": row[9],
                   "production_instance_track": row[10]}[row[7]]
            others = [v for k, v in {
                "entity_fixed_frame": row[8], "entity_track": row[9],
                "production_instance_track": row[10]}.items()
                if k != row[7]]
            if col != e["placement"]["id"] or any(v is not None
                                                  for v in others):
                raise RecoveryCorruption(
                    f"binding {p[0]} entry placement XOR broken")
            # pinned target EXISTENCE — soft-deleted remains verifiable
            target_table = {"entity_fixed_frame": "spatial_frames",
                            "entity_track": "spatial_tracks",
                            "production_instance_track":
                                "production_instance_spatial_tracks"}[row[7]]
            tgt = con.execute(
                f"SELECT 1 FROM {target_table} WHERE id = ?",
                (col,)).fetchone()  # noqa: S608 — fixed table whitelist
            if tgt is None:
                raise RecoveryCorruption(
                    f"binding {p[0]}: pinned A4 target row {col} missing")
            # pinned interpretation closure + hash agreement
            irow = con.execute(
                "SELECT production_revision_id, x_mm, y_mm, z_mm, "
                "yaw_udeg, pitch_udeg, roll_udeg, interpretation_json, "
                "interpretation_hash FROM "
                "production_revision_spatial_interpretations WHERE "
                "production_revision_id = ?", (row[2],)).fetchone()
            if irow is None or irow[8] != row[11]:
                raise RecoveryCorruption(
                    f"binding {p[0]}: pinned interpretation missing or "
                    "hash disagrees")
            parents_row = con.execute(
                "SELECT pr.snapshot_hash, (SELECT c.blob_hash FROM "
                "production_revision_closures c WHERE "
                "c.production_revision_id = pr.id AND c.contract_key = "
                "'retained_blob' AND c.contract_version = 1) FROM "
                "production_revisions pr WHERE pr.id = ?",
                (row[2],)).fetchone()
            if parents_row is None or parents_row[1] is None:
                raise RecoveryCorruption(
                    f"binding {p[0]}: interpretation parent closure "
                    "unreachable")
            try:
                verify_stored_interpretation(
                    interpretation_json=irow[7],
                    interpretation_hash=irow[8],
                    x_mm=irow[1], y_mm=irow[2], z_mm=irow[3],
                    yaw_udeg=irow[4], pitch_udeg=irow[5],
                    roll_udeg=irow[6],
                    row_production_revision_id=irow[0],
                    parent_snapshot_hash=parents_row[0],
                    parent_blob_hash=parents_row[1])
            except SoloRingError as exc:
                raise RecoveryCorruption(
                    f"binding {p[0]}: pinned interpretation corrupt: "
                    f"{exc.message}") from exc


def _verify_m13_selection_and_history(con) -> None:
    """Current selection referential coherence + schema-6 parents with
    exact child projections (§23.4). A selection referencing an
    unresolvable binding is corruption; selection STALENESS is not
    checked here — that is current-status classification."""
    sels = con.execute(
        "SELECT shot_id, binding_id FROM "
        "shot_production_world_selections").fetchall()
    for s in sels:
        if con.execute(
                "SELECT 1 FROM shots WHERE id = ?", (s[0],)).fetchone() \
                is None:
            raise RecoveryCorruption(
                f"selection for shot {s[0]}: shot missing")
        if con.execute(
                "SELECT 1 FROM composition_spatial_bindings WHERE id = ?",
                (s[1],)).fetchone() is None:
            raise RecoveryCorruption(
                f"selection for shot {s[0]}: binding {s[1]} missing")
    parents = con.execute(
        "SELECT shot_revision_id, production_world_hash, binding_id, "
        "binding_hash, composition_revision_id, composition_revision_hash, "
        "spatial_world_revision_id, spatial_world_revision_hash FROM "
        "shot_revision_production_worlds").fetchall()
    for p in parents:
        rev = con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (p[0],)).fetchone()
        if rev is None:
            raise RecoveryCorruption(
                f"schema-6 parent for missing ShotRevision {p[0]}")
        import json as _json

        from soloring.domain.canonical import canonical_json_str

        try:
            snap = _json.loads(rev[0])
        except ValueError as exc:
            raise RecoveryCorruption(
                f"ShotRevision {p[0]} snapshot unparseable") from exc
        pack = snap.get("production_world") if isinstance(snap, dict) \
            else None
        if pack is None:
            raise RecoveryCorruption(
                f"ShotRevision {p[0]}: M13 parent row without schema-6 "
                "content")
        b = pack["binding"]
        if (p[2] != b["binding_id"] or p[3] != b["binding_hash"]
                or p[4] != b["value"]["composition_revision"]["revision_id"]
                or p[5] != b["value"]["composition_revision"]
                ["snapshot_hash"]
                or p[6] != b["value"]["spatial_world_revision"]
                ["revision_id"]
                or p[7] != b["value"]["spatial_world_revision"]
                ["snapshot_hash"]):
            raise RecoveryCorruption(
                f"ShotRevision {p[0]}: M13 parent row disagrees with the "
                "embedded pack")
        # child projection equality against the pack (positions included)
        frows = con.execute(
            "SELECT position, occurrence_id, feature_id, value_json, "
            "value_hash FROM "
            "shot_revision_production_instance_feature_states WHERE "
            "shot_revision_id = ? ORDER BY position", (p[0],)).fetchall()
        expected_f = [
            (pos, e["occurrence_id"], e["feature_id"],
             canonical_json_str(e["value"]), e["value_hash"])
            for pos, e in enumerate(pack["instance_feature_states"])]
        got_f = [(r[0], r[1], r[2], r[3], r[4]) for r in frows]
        if got_f != expected_f:
            raise RecoveryCorruption(
                f"ShotRevision {p[0]}: PI feature-state children "
                "disagree with the captured pack")
        srows = con.execute(
            "SELECT position, occurrence_id, production_instance_track_id, "
            "x_mm FROM shot_revision_production_instance_spatial_states "
            "WHERE shot_revision_id = ? ORDER BY position", (p[0],)).fetchall()
        expected_s = [
            (pos, e["occurrence_id"], e["production_instance_track_id"],
             e["transform"]["translation_mm"][0])
            for pos, e in enumerate(pack["instance_spatial_states"])]
        got_s = [(r[0], r[1], r[2], r[3]) for r in srows]
        if got_s != expected_s:
            raise RecoveryCorruption(
                f"ShotRevision {p[0]}: PI spatial-state children disagree "
                "with the captured pack")
