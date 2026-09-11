"""M14 retained structural-mesh consumer (frozen R2 §§9/12/13/27/28).

Set-oriented immutable-history loading for captured schema-6
production-world observations:

    captured binding value (composition revision pin)
        ↓ one batched immutable lookup per domain
    captured CompositionRevision  →  direct/nested occurrence partition
    ProductionRevision + closure  →  exact M11 hash agreement
    physical retained Blob        →  hash/size + Stage A byte cap
    structural_mesh.v1 recognition → typed unsupported representation
    interpretation (recognized only) → required, hash-pinned
    M13 binding placement          →  A4 or A6 chain
    renderer-neutral retained-mesh observation sources

Failure distinctions are exact: a non-mesh retained blob is a typed
unsupported representation; anything that disagrees with the captured
immutable history (composition/revision/closure/interpretation hashes,
physical blob bytes) is a fail-closed invariant error — never a
fallback to current state. SQL round trips are bounded by domain batch,
not occurrence count (APR-044).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

from sqlalchemy import text as _sa_text

from soloring.domain.canonical import canonical_hash
from soloring.errors import ErrorCode, SoloRingError, internal_invariant
from soloring.observation.mesh import (
    MAX_RETAINED_MESH_BYTES_PER_REVISION,
    MAX_TOTAL_TRIANGLES_PER_OBSERVATION,
    REPRESENTATION_CONTRACT,
    is_structural_mesh_grammar,
    parse_structural_mesh_v1,
)
from soloring.spatial.math import normalize_udeg, rotation_matrix

NESTED_COMPOSITION_CONTRACT = "nested_composition.v1"
UNRECOGNIZED_RETAINED_BLOB_CONTRACT = "unrecognized.retained_blob"
PLACEMENT_CONTRACT = "m14.placement.v1"

_DIRECT_SOURCE_KIND = "production_revision"
_NESTED_SOURCE_KIND = "composition_revision"

_ENTITY_PLACEMENT_KINDS = {"entity_fixed_frame", "entity_track"}
_PI_PLACEMENT_KIND = "production_instance_track"


@dataclass(frozen=True)
class UnsupportedOccurrence:
    occurrence_id: str
    source_contract: str
    production_revision_id: str | None = None
    production_revision_hash: str | None = None


@dataclass(frozen=True)
class RetainedMeshSource:
    """One renderer-neutral retained-mesh observation source."""

    occurrence_id: str
    composition_revision_id: str
    composition_revision_hash: str
    production_revision_id: str
    production_revision_hash: str
    retained_blob_hash: str
    mesh: dict
    interpretation_hash: str
    realization_local_to_subject_local: dict
    placement_owner: str
    placement_source_kind: str
    placement_source_id: str
    placement_source_hash: str
    subject_local_to_world: dict
    realization_local_to_world: dict
    authority_subject_kind: str = ""
    authority_subject_id: str = ""
    structure_requirement: dict = field(default=None)
    placement_requirement: dict = field(default=None)
    occurrence_object: dict = field(default=None)


@dataclass(frozen=True)
class RetainedLoadOutcome:
    sources: list[RetainedMeshSource]
    unsupported: list[UnsupportedOccurrence]
    unsupported_requirements: list[dict]
    total_triangles: int
    query_count: int


def _invariant(message: str):
    return internal_invariant(
        f"retained structural-mesh consumer: {message}")


def compose_transforms(first: dict, second: dict) -> dict:
    """Compose (realization→subject) then (subject→world) under the
    frozen M10/M13 convention R = Ry·Rx·Rz (active, local→world).

    R_total = R2·R1; t_total = t2 + R2·t1. The authoritative identity is
    the normalized integer microdegree tuple, so the composed rotation is
    re-quantized to the nearest microdegree and the translation to whole
    millimeters (exact for axis-aligned/identity chains).
    """
    t1 = first["translation_mm"]
    r1 = tuple(first["rotation_udeg"])
    t2 = second["translation_mm"]
    r2 = tuple(second["rotation_udeg"])

    m2 = rotation_matrix(r2)
    m1 = rotation_matrix(r1)
    total = [[sum(m2[i][k] * m1[k][j] for k in range(3))
              for j in range(3)] for i in range(3)]
    translation = [t2[i] + sum(m2[i][k] * t1[k] for k in range(3))
                   for i in range(3)]

    # Y-X-Z Tait-Bryan extraction for R = Ry(yaw)·Rx(pitch)·Rz(roll):
    # R[1][2] = -sp, R[0][2] = sy·cp, R[2][2] = cy·cp,
    # R[1][0] = cp·sr, R[1][1] = cp·cr  (principal range cp > 0)
    pitch = math.asin(max(-1.0, min(1.0, -total[1][2])))
    yaw = math.atan2(total[0][2], total[2][2])
    roll = math.atan2(total[1][0], total[1][1])

    return {
        "translation_mm": [int(round(v)) for v in translation],
        "rotation_udeg": [
            normalize_udeg(
                int(round(math.degrees(angle) * 1_000_000)))
            for angle in (yaw, pitch, roll)],
    }


def _structure_requirement(occurrence_id: str, pr_id: str, pr_hash: str,
                           contract: str, domain: str = "A5",
                           source_kind: str = "production_revision",
                           subject_kind: str = "production_occurrence"
                           ) -> dict:
    return {
        "property": "occurrence.structure",
        "preservation": "STRUCTURAL",
        "enforcement": "REQUIRED",
        "subject": {"kind": subject_kind, "id": occurrence_id},
        "occurrence_id": occurrence_id,
        "subkey": None,
        "authority": {
            "domain": domain,
            "source_kind": source_kind,
            "source_id": pr_id,
            "source_hash": pr_hash,
        },
        "source_contract": contract,
    }


def _placement_requirement(occurrence_id: str, owner: str,
                           source_kind: str, source_id: str,
                           source_hash: str) -> dict:
    return {
        "property": "occurrence.placement",
        "preservation": "STRUCTURAL",
        "enforcement": "REQUIRED",
        "subject": {"kind": "production_occurrence", "id": occurrence_id},
        "occurrence_id": occurrence_id,
        "subkey": None,
        "authority": {
            "domain": owner,
            "source_kind": source_kind,
            "source_id": source_id,
            "source_hash": source_hash,
        },
        "source_contract": PLACEMENT_CONTRACT,
    }


def _resolve_a4_subject_world(placement: dict, subject: dict,
                              captured_production_world: dict,
                              captured_spatial_pack: dict | None, *,
                              composition_id: str,
                              occurrence_id: str) -> dict:
    kind = placement["kind"]
    if kind == _PI_PLACEMENT_KIND:
        # Frozen §13.3 (source review P0-3): the exact matching key is
        # (composition_id, occurrence_id, production_instance_track_id).
        # Missing, duplicate, or malformed state fails closed — never
        # the first merely-plausible row.
        matches = [
            state for state in captured_production_world.get(
                "instance_spatial_states", [])
            if state.get("composition_id") == composition_id
            and state.get("occurrence_id") == occurrence_id
            and state.get("production_instance_track_id")
            == placement["id"]]
        if len(matches) != 1:
            raise _invariant(
                "captured production_world.instance_spatial_states must "
                f"hold exactly one state for the exact key "
                f"(composition {composition_id}, occurrence "
                f"{occurrence_id}, PI track {placement['id']!r}) — "
                f"found {len(matches)}")
        transform = matches[0].get("transform")
        if (not isinstance(transform, dict)
                or not isinstance(transform.get("translation_mm"), list)
                or not isinstance(transform.get("rotation_udeg"), list)):
            raise _invariant(
                f"captured PI state for occurrence {occurrence_id} has "
                "a malformed transform")
        return transform
    if kind in _ENTITY_PLACEMENT_KINDS:
        if kind == "entity_track" and captured_spatial_pack is not None:
            for staged in captured_spatial_pack.get("staging", []):
                if staged.get("entity_id") == subject["id"]:
                    return staged["transform"]
        if kind == "entity_fixed_frame" and captured_spatial_pack is not None:
            frames = (captured_spatial_pack.get("spatial_world", {})
                      .get("world_snapshot", {}).get("frames", []))
            for frame in frames:
                if frame.get("bound_entity_id") == subject["id"]:
                    return frame["transform"]
        raise _invariant(
            f"captured schema-5 spatial plane has no exact placement "
            f"source for {kind} subject {subject['id']!r}")
    raise _invariant(f"unknown captured placement kind {kind!r}")


async def load_retained_mesh_sources(
    conn,
    read_blob,
    *,
    captured_production_world: dict,
    captured_spatial_pack: dict | None,
) -> RetainedLoadOutcome:
    """Load every direct occurrence of the captured CompositionRevision.

    ``read_blob(blob_hash) -> bytes`` supplies physical retained bytes by
    exact hash. Lookups are batched by domain: composition revision,
    production revisions, closures, interpretations — four queries total
    regardless of occurrence count.
    """
    queries = 0

    binding = captured_production_world["binding"]
    binding_id = binding["binding_id"]
    binding_hash = binding["binding_hash"]
    value = binding["value"]
    comp_pin = value["composition_revision"]
    comp_id = comp_pin["revision_id"]
    comp_hash_pin = comp_pin["snapshot_hash"]
    # The placement entries carry the full per-occurrence pins: exact
    # ProductionRevision hash, authority subject, placement target, and
    # the pinned interpretation hash (frozen M13 §11.1 binding value).
    entries_by_occurrence = {
        e["occurrence_id"]: e for e in value.get("entries", [])}

    rows = (await conn.execute(_sa_text(
        "SELECT id, composition_id, snapshot_json, snapshot_hash FROM "
        "composition_revisions WHERE id = :c"),
        {"c": comp_id})).mappings().all()
    queries += 1
    if len(rows) != 1:
        raise _invariant(
            f"captured CompositionRevision {comp_id} missing from "
            "immutable history")
    comp_row = rows[0]
    comp_snapshot = json.loads(comp_row["snapshot_json"])
    if comp_row["snapshot_hash"] != canonical_hash(comp_snapshot):
        raise _invariant(
            "captured CompositionRevision stored bytes disagree with "
            "the stored hash")
    if comp_row["snapshot_hash"] != comp_hash_pin:
        raise _invariant(
            "captured CompositionRevision hash disagrees with the "
            "binding pin")

    direct: list[dict] = []
    unsupported: list[UnsupportedOccurrence] = []
    for occurrence in comp_snapshot["occurrences"]:
        source = occurrence["source"]
        if source["kind"] == _DIRECT_SOURCE_KIND:
            direct.append(occurrence)
        else:
            unsupported.append(UnsupportedOccurrence(
                occurrence_id=occurrence["occurrence_id"],
                source_contract=NESTED_COMPOSITION_CONTRACT))

    pr_ids = [o["source"]["revision_id"] for o in direct]
    pr_rows: dict[str, dict] = {}
    closure_rows: dict[str, dict] = {}
    interp_rows: dict[str, dict] = {}
    if pr_ids:
        placeholders = ",".join(f":p{i}" for i in range(len(pr_ids)))
        params = {f"p{i}": pid for i, pid in enumerate(pr_ids)}

        rows = (await conn.execute(_sa_text(
            "SELECT id, snapshot_json, snapshot_hash FROM "
            "production_revisions WHERE id IN "
            f"({placeholders})"), params)).mappings().all()
        queries += 1
        pr_rows = {row["id"]: dict(row) for row in rows}

        rows = (await conn.execute(_sa_text(
            "SELECT production_revision_id, contract_key, "
            "contract_version, blob_hash, size_bytes, media_type FROM "
            "production_revision_closures WHERE production_revision_id "
            f"IN ({placeholders})"), params)).mappings().all()
        queries += 1
        closure_rows = {row["production_revision_id"]: dict(row)
                        for row in rows}

        rows = (await conn.execute(_sa_text(
            "SELECT production_revision_id, interpretation_json, "
            "interpretation_hash FROM "
            "production_revision_spatial_interpretations WHERE "
            f"production_revision_id IN ({placeholders})"),
            params)).mappings().all()
        queries += 1
        interp_rows = {row["production_revision_id"]: dict(row)
                       for row in rows}

    from soloring.production.canonical import (
        RetainedBlobClosure,
        production_revision_snapshot_json as _pr_json,
        production_revision_snapshot_hash as _pr_hash,
    )

    sources: list[RetainedMeshSource] = []
    total_triangles = 0
    for occurrence in direct:
        occurrence_id = occurrence["occurrence_id"]
        pr_id = occurrence["source"]["revision_id"]
        pr_row = pr_rows.get(pr_id)
        if pr_row is None:
            raise _invariant(
                f"captured ProductionRevision {pr_id} (occurrence "
                f"{occurrence_id}) missing from immutable history")
        closure = closure_rows.get(pr_id)
        if closure is None:
            raise _invariant(
                f"retained_blob/v1 closure for ProductionRevision "
                f"{pr_id} missing from immutable history")
        if (closure["contract_key"] != "retained_blob"
                or closure["contract_version"] != 1):
            raise _invariant(
                f"closure for ProductionRevision {pr_id} is not the "
                "frozen retained_blob/v1 contract")
        pr_canonical = _pr_json(RetainedBlobClosure(
            blob_hash=closure["blob_hash"],
            size_bytes=closure["size_bytes"],
            media_type=closure["media_type"]))
        if (pr_row["snapshot_json"] != pr_canonical
                or pr_row["snapshot_hash"] != _pr_hash(RetainedBlobClosure(
                    blob_hash=closure["blob_hash"],
                    size_bytes=closure["size_bytes"],
                    media_type=closure["media_type"]))):
            raise _invariant(
                f"ProductionRevision {pr_id} snapshot/hash disagrees "
                "with its retained closure (M11 agreement)")
        pr_hash = pr_row["snapshot_hash"]

        subject = entries_by_occurrence.get(occurrence_id)
        if subject is not None and subject[
                "production_revision_hash"] != pr_hash:
            raise _invariant(
                f"binding subject for occurrence {occurrence_id} pins a "
                "different ProductionRevision hash than immutable "
                "history")

        raw = read_blob(closure["blob_hash"])
        physical_hash = hashlib.sha256(raw).hexdigest()
        if physical_hash != closure["blob_hash"]:
            raise _invariant(
                f"physical retained Blob for ProductionRevision {pr_id} "
                "does not hash to the closure pin")
        if len(raw) != closure["size_bytes"]:
            raise _invariant(
                f"physical retained Blob length for ProductionRevision "
                f"{pr_id} disagrees with closure size_bytes")
        if len(raw) > MAX_RETAINED_MESH_BYTES_PER_REVISION:
            raise SoloRingError(
                ErrorCode.STRUCTURAL_MESH_LIMIT_EXCEEDED,
                f"retained mesh for ProductionRevision {pr_id} is "
                f"{len(raw)} bytes; MAX_RETAINED_MESH_BYTES_PER_REVISION "
                f"is {MAX_RETAINED_MESH_BYTES_PER_REVISION}",
                status_code=409)

        if not is_structural_mesh_grammar(raw):
            unsupported.append(UnsupportedOccurrence(
                occurrence_id=occurrence_id,
                source_contract=UNRECOGNIZED_RETAINED_BLOB_CONTRACT,
                production_revision_id=pr_id,
                production_revision_hash=pr_hash))
            continue

        mesh = parse_structural_mesh_v1(raw)  # Stage B element caps
        total_triangles += len(mesh["triangles"])
        if total_triangles > MAX_TOTAL_TRIANGLES_PER_OBSERVATION:
            raise SoloRingError(
                ErrorCode.STRUCTURAL_MESH_LIMIT_EXCEEDED,
                f"observation total {total_triangles} triangles exceeds "
                f"MAX_TOTAL_TRIANGLES_PER_OBSERVATION "
                f"{MAX_TOTAL_TRIANGLES_PER_OBSERVATION}",
                status_code=409)

        interp = interp_rows.get(pr_id)
        if interp is None:
            raise SoloRingError(
                ErrorCode.STRUCTURAL_MESH_INTERPRETATION_REQUIRED,
                "a recognized executable retained mesh requires an "
                f"immutable ProductionRevisionSpatialInterpretation "
                f"(ProductionRevision {pr_id}, occurrence "
                f"{occurrence_id})",
                status_code=409,
                details={"production_revision_id": pr_id,
                         "occurrence_id": occurrence_id})
        interpretation = json.loads(interp["interpretation_json"])
        if canonical_hash(interpretation) != interp["interpretation_hash"]:
            raise _invariant(
                f"stored interpretation for ProductionRevision {pr_id} "
                "disagrees with its hash")
        if interpretation["production_revision_hash"] != pr_hash:
            raise _invariant(
                f"interpretation for ProductionRevision {pr_id} pins a "
                "different revision hash than immutable history")
        if interpretation["retained_blob_hash"] != closure["blob_hash"]:
            raise _invariant(
                f"interpretation for ProductionRevision {pr_id} pins a "
                "different retained Blob than immutable history")
        if subject is not None and subject[
                "spatial_interpretation_hash"] != (
                    interp["interpretation_hash"]):
            raise _invariant(
                f"binding subject for occurrence {occurrence_id} pins a "
                "different interpretation hash than immutable history")

        first = interpretation["realization_local_to_subject_local"]
        if subject is not None:
            owner = "A4"
            # Source review P1-5 (frozen §13.2 no-conflict rule): an
            # M13-bound occurrence's captured Composition transform
            # must be the identity — a conflicting composition
            # transform on a bound subject is historical corruption
            # (the binding publish already refuses it at write time).
            occurrence_transform = occurrence.get("transform") or {}
            if (occurrence_transform.get("translation_mm") != [0, 0, 0]
                    or occurrence_transform.get("rotation_udeg")
                    != [0, 0, 0]):
                raise _invariant(
                    f"bound occurrence {occurrence_id} carries a "
                    "non-identity Composition transform — conflicting "
                    "with its A4 spatial placement (frozen §13.2)")
            placement = subject["placement"]
            second = _resolve_a4_subject_world(
                placement, subject["authority_subject"],
                captured_production_world, captured_spatial_pack,
                composition_id=comp_row["composition_id"],
                occurrence_id=occurrence_id)
            placement_source_kind = "composition_spatial_binding"
            placement_source_id = binding_id
            placement_source_hash = binding_hash
        else:
            owner = "A6"
            second = occurrence["transform"]
            placement_source_kind = "composition_revision"
            placement_source_id = comp_id
            placement_source_hash = comp_row["snapshot_hash"]
        composed = compose_transforms(first, second)

        structure_requirement = _structure_requirement(
            occurrence_id, pr_id, pr_hash, REPRESENTATION_CONTRACT)
        placement_requirement = _placement_requirement(
            occurrence_id, owner, placement_source_kind,
            placement_source_id, placement_source_hash)
        occurrence_object = {
            "occurrence_id": occurrence_id,
            "composition_revision_id": comp_id,
            "composition_revision_hash": comp_row["snapshot_hash"],
            "production_revision_id": pr_id,
            "production_revision_hash": pr_hash,
            "retained_blob_hash": closure["blob_hash"],
            "representation_contract": REPRESENTATION_CONTRACT,
            "placement_owner": owner,
            "interpretation": {
                "hash": interp["interpretation_hash"],
                "realization_local_to_subject_local": first,
            },
            "placement": {
                "source_kind": placement_source_kind,
                "source_id": placement_source_id,
                "source_hash": placement_source_hash,
                "subject_local_to_world": second,
            },
            "realization_local_to_world": composed,
        }
        sources.append(RetainedMeshSource(
            occurrence_id=occurrence_id,
            composition_revision_id=comp_id,
            composition_revision_hash=comp_row["snapshot_hash"],
            production_revision_id=pr_id,
            production_revision_hash=pr_hash,
            retained_blob_hash=closure["blob_hash"],
            mesh=mesh,
            interpretation_hash=interp["interpretation_hash"],
            realization_local_to_subject_local=first,
            placement_owner=owner,
            placement_source_kind=placement_source_kind,
            placement_source_id=placement_source_id,
            placement_source_hash=placement_source_hash,
            subject_local_to_world=second,
            realization_local_to_world=composed,
            authority_subject_kind=(
                subject["authority_subject"]["kind"] if subject else ""),
            authority_subject_id=(
                subject["authority_subject"]["id"] if subject else ""),
            structure_requirement=structure_requirement,
            placement_requirement=placement_requirement,
            occurrence_object=occurrence_object))

    unsupported_entries = []
    for entry in unsupported:
        if entry.source_contract == NESTED_COMPOSITION_CONTRACT:
            unsupported_entries.append(_structure_requirement(
                entry.occurrence_id, comp_id, comp_row["snapshot_hash"],
                NESTED_COMPOSITION_CONTRACT, domain="A6",
                source_kind="composition_revision"))
        else:
            unsupported_entries.append(_structure_requirement(
                entry.occurrence_id, entry.production_revision_id,
                entry.production_revision_hash,
                UNRECOGNIZED_RETAINED_BLOB_CONTRACT))

    return RetainedLoadOutcome(
        sources=sources,
        unsupported=unsupported,
        unsupported_requirements=unsupported_entries,
        total_triangles=total_triangles,
        query_count=queries)


def merge_retained_into_spec(spec: dict, outcome: RetainedLoadOutcome) -> dict:
    """Fold the B1 consumer outcome into a compiled base spec (frozen
    §§8.5/10/28): occurrence structure/placement requirements for every
    direct occurrence (recognized meshes contribute both; nested and
    non-mesh contribute their typed unsupported structure requirement),
    the ProductionOccurrence objects in captured order, and the
    materialization source list. Rebuilds through the strict builder so
    canonical ordering and the full grammar hold."""
    from soloring.observation.spec import build_world_observation_spec

    requirements = list(spec["requirements"])
    for source in outcome.sources:
        requirements.append(source.structure_requirement)
        requirements.append(source.placement_requirement)
    requirements.extend(outcome.unsupported_requirements)

    materialization = dict(spec["materializations"][0])
    materialization["source_occurrence_ids"] = [
        source.occurrence_id for source in outcome.sources]

    return build_world_observation_spec(
        shot_revision_id=spec["shot_revision"]["id"],
        plan_hash=spec["shot_revision"]["plan_hash"],
        captured_domains=spec["captured_domains"],
        requirements=requirements,
        production_occurrences=[
            source.occurrence_object for source in outcome.sources],
        materializations=[materialization])
