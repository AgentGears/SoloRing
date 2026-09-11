"""M14 derived-observation publication (frozen R2 §§22/25/33).

Blob publication + convergence of `derived_observation_artifacts`
inside one BEGIN IMMEDIATE unit (global convergence, the M10 register
pattern): same complete coordinate + same bytes → one immutable row;
same coordinate + different bytes → invariant failure; different
materializer-contract hash → a different coordinate.
"""

from __future__ import annotations

import contextlib
import hashlib

from sqlalchemy import text as _text

from soloring.db.timeutil import DB_NOW_SQL as _NOW
from soloring.errors import internal_invariant as _internal_invariant
from soloring.domain.canonical import canonical_json_str, canonical_hash


class ObservationBinding:
    """The immutable Generation binding value (frozen §22.2)."""

    __slots__ = ("input_key", "position", "artifact_id", "blob_hash")

    def __init__(self, *, input_key: str, position: int,
                 artifact_id: str, blob_hash: str):
        self.input_key = input_key
        self.position = position
        self.artifact_id = artifact_id
        self.blob_hash = blob_hash


def _convergence_error(message: str):
    return _internal_invariant(
        f"derived-observation convergence: {message}")


async def publish_observation_artifact(
    conn,
    store,
    *,
    project_id: str,
    observation_spec_hash: str,
    materializer_id: str,
    materializer_version: int,
    materializer_contract_hash: str,
    parameters: dict,
    parameters_hash: str,
    provenance: dict,
    provenance_hash_value: str,
    blob_bytes: bytes,
) -> str:
    """Publish the Blob + converge the artifact row. Returns the
    (existing or newly inserted) artifact id.

    ``conn`` is an async Engine connection WITHOUT an open transaction;
    the convergence runs in its own BEGIN IMMEDIATE unit so competing
    writers serialize on the write fence and converge on one row.
    """
    blob_hash = hashlib.sha256(blob_bytes).hexdigest()

    # Blob physical publication first (outside the convergence fence,
    # idempotent by content address — the M10 §12.3 pattern)
    tmp = store.tmp_path()
    tmp.write_bytes(blob_bytes)
    await store.place(blob_hash, tmp)
    async with _immediate(conn):
        await conn.execute(
            _text(f"INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
                  f"created_at) VALUES (:h, :p, :s, {_NOW})"),
            {"h": blob_hash, "p": store.relative_path_for_hash(blob_hash),
             "s": len(blob_bytes)})

    async with _immediate(conn):
        existing = (await conn.execute(
            _text(
                "SELECT id, blob_hash, parameters_hash, provenance_hash, "
                "materializer_contract_hash, artifact_role, materializer_id,"
                " materializer_version FROM derived_observation_artifacts "
                "WHERE project_id = :p AND observation_spec_hash = :s "
                "AND artifact_role = :r AND materializer_id = :mi "
                "AND materializer_version = :mv "
                "AND materializer_contract_hash = :mc "
                "AND parameters_hash = :ph"),
            {"p": project_id, "s": observation_spec_hash,
             "r": "observation.world_depth", "mi": materializer_id,
             "mv": materializer_version, "mc": materializer_contract_hash,
             "ph": parameters_hash})).mappings().one_or_none()

        if existing is not None:
            if existing["blob_hash"] != blob_hash:
                raise _convergence_error(
                    "Same complete derived-observation coordinate "
                    "produced different bytes — determinism invariant "
                    "failure.")
            if (existing["provenance_hash"] != provenance_hash_value
                    or existing["parameters_hash"] != parameters_hash):
                raise _convergence_error(
                    "Existing derived-observation provenance disagrees "
                    "with the requested publication.")
            return existing["id"]

        artifact_id = _new_uuid()
        await conn.execute(
            _text(
                "INSERT INTO derived_observation_artifacts "
                "(id, project_id, observation_spec_hash, artifact_role, "
                "materializer_id, materializer_version, "
                "materializer_contract_hash, parameters_json, "
                "parameters_hash, provenance_json, provenance_hash, "
                "blob_hash, created_at) VALUES "
                f"(:id, :p, :s, :r, :mi, :mv, :mc, :pj, :ph, :vj, :vh, "
                f":bh, {_NOW})"),
            {"id": artifact_id, "p": project_id,
             "s": observation_spec_hash, "r": "observation.world_depth",
             "mi": materializer_id, "mv": materializer_version,
             "mc": materializer_contract_hash,
             "pj": canonical_json_str(parameters),
             "ph": parameters_hash,
             "vj": canonical_json_str(provenance),
             "vh": provenance_hash_value, "bh": blob_hash})
        return artifact_id


class _Immediate:
    """BEGIN IMMEDIATE context on a raw async connection."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        await self._conn.exec_driver_sql("BEGIN IMMEDIATE")
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            await self._conn.exec_driver_sql("COMMIT")
        else:
            with contextlib.suppress(Exception):
                await self._conn.exec_driver_sql("ROLLBACK")
        return False


def _immediate(conn):
    return _Immediate(conn)


def _new_uuid() -> str:
    import uuid

    return str(uuid.uuid4())


async def insert_generation_binding(
    conn,
    *,
    generation_id: str,
    binding: ObservationBinding,
) -> None:
    """Insert the immutable Generation binding (runs INSIDE the
    Generation publication transaction — atomicity §25.1)."""
    await conn.execute(
        _text(
            "INSERT INTO generation_derived_observation_inputs "
            "(generation_id, input_key, position, artifact_role, "
            "derived_observation_artifact_id, blob_hash) VALUES "
            "(:g, :k, :pos, 'observation.world_depth', :a, :bh)"),
        {"g": generation_id, "k": binding.input_key,
         "pos": binding.position, "a": binding.artifact_id,
         "bh": binding.blob_hash})
