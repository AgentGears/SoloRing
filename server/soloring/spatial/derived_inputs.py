"""Immutable sibling Generation bindings for M10 derived spatial inputs."""
from __future__ import annotations
import contextlib
from dataclasses import dataclass
from typing import Literal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from soloring.assets.blob_store import BlobStore
from soloring.domain.ids import is_uuid
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial.blob_integrity import blob_integrity_status
from soloring.spatial.derived import DerivedSpatialArtifactSpec, validate_derived_provenance_row
from soloring.spatial.error_codes import DERIVED_SPATIAL_BINDING_INVALID,DERIVED_SPATIAL_BLOB_CORRUPT,DERIVED_SPATIAL_BLOB_MISSING,DERIVED_SPATIAL_PROVENANCE_MISMATCH

INITIAL_MAX_CONTROL_STREAMS=3
ROLES=frozenset({"spatial.world_depth","spatial.entity_depth"})
@dataclass(frozen=True)
class DerivedInputBinding:
    input_key:str; position:int; artifact_role:Literal["spatial.world_depth","spatial.entity_depth"]; derived_spatial_artifact_id:str; blob_hash:str

def _bad(msg:str)->SoloRingError: return SoloRingError(DERIVED_SPATIAL_BINDING_INVALID,msg,status_code=503)
def validate_bindings(bindings:tuple[DerivedInputBinding,...])->None:
    if not bindings or len(bindings)>INITIAL_MAX_CONTROL_STREAMS: raise _bad("Initial M10 supports 1..3 derived control streams.")
    if any(b.artifact_role not in ROLES for b in bindings): raise _bad("Unknown initial M10 derived role.")
    if sum(b.artifact_role=="spatial.world_depth" for b in bindings)!=1 or sum(b.artifact_role=="spatial.entity_depth" for b in bindings)>2: raise _bad("Initial M10 requires one world stream and at most two Entity streams.")
    if sorted(b.position for b in bindings)!=list(range(len(bindings))): raise _bad("Derived input positions must be contiguous from zero.")
    if next(b for b in bindings if b.artifact_role=="spatial.world_depth").position!=0: raise _bad("World depth must occupy position zero.")
    if len({(b.input_key,b.position) for b in bindings})!=len(bindings) or len({(b.artifact_role,b.position) for b in bindings})!=len(bindings): raise _bad("Duplicate derived input coordinate.")
    if any(not b.input_key.strip() or not is_uuid(b.derived_spatial_artifact_id) or not BlobStore.validate_hash(b.blob_hash) for b in bindings): raise _bad("Invalid derived input binding.")

async def bind_generation_derived_inputs(session:AsyncSession,store:BlobStore,generation_id:str,bindings:tuple[DerivedInputBinding,...])->None:
    validate_bindings(bindings)
    for bh in sorted({b.blob_hash for b in bindings}):
        status=await blob_integrity_status(store,bh)
        if status!="valid": raise SoloRingError(DERIVED_SPATIAL_BLOB_MISSING if status=="missing" else DERIVED_SPATIAL_BLOB_CORRUPT,"Derived Generation Blob failed integrity verification.",status_code=500)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            gen=(await conn.execute(text("SELECT g.id,s.project_id,srsw.spatial_continuity_hash FROM generations g JOIN shots s ON s.id=g.shot_id LEFT JOIN shot_revision_spatial_worlds srsw ON srsw.shot_revision_id=g.shot_revision_id WHERE g.id=:g"),{"g":generation_id})).mappings().one_or_none()
            if gen is None: raise SoloRingError(ErrorCode.GENERATION_NOT_FOUND,f"Generation {generation_id} not found.",status_code=404)
            if gen["spatial_continuity_hash"] is None: raise SoloRingError(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Generation ShotRevision has no captured spatial authority.",status_code=500)
            old=(await conn.execute(text("SELECT input_key,position,artifact_role,derived_spatial_artifact_id,blob_hash FROM generation_derived_spatial_inputs WHERE generation_id=:g ORDER BY position"),{"g":generation_id})).mappings().all()
            want=sorted((b.input_key,b.position,b.artifact_role,b.derived_spatial_artifact_id,b.blob_hash) for b in bindings)
            if old:
                got=sorted((r["input_key"],r["position"],r["artifact_role"],r["derived_spatial_artifact_id"],r["blob_hash"]) for r in old)
                if got!=want: raise SoloRingError(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Historical derived inputs disagree with immutable binding.",status_code=500)
                await conn.exec_driver_sql("COMMIT"); return
            checked:list[tuple[DerivedInputBinding,DerivedSpatialArtifactSpec]]=[]
            for b in bindings:
                row=(await conn.execute(text("SELECT * FROM derived_spatial_artifacts WHERE id=:a"),{"a":b.derived_spatial_artifact_id})).mappings().one_or_none()
                if row is None or row["blob_hash"]!=b.blob_hash: raise SoloRingError(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Derived artifact/blob identity is invalid.",status_code=500)
                if row["project_id"]!=gen["project_id"] or row["spatial_continuity_hash"]!=gen["spatial_continuity_hash"]: raise SoloRingError(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Derived artifact Project/spatial authority mismatch.",status_code=500)
                spec,_=validate_derived_provenance_row(dict(row)); scope=spec.derivation.parameters.scope
                if (b.artifact_role=="spatial.world_depth")!=(scope=="world"): raise _bad("Derived role/scope mismatch.")
                checked.append((b,spec))
            order=[(s.derivation.parameters.entity_id,s.derivation.parameters.placement_source_kind,s.derivation.parameters.placement_source_id) for b,s in sorted(checked,key=lambda x:x[0].position) if b.artifact_role=="spatial.entity_depth"]
            if order!=sorted(order): raise _bad("Entity depth streams violate canonical Entity/placement ordering.")
            for b in bindings:
                await conn.execute(text("INSERT INTO generation_derived_spatial_inputs (generation_id,input_key,position,artifact_role,derived_spatial_artifact_id,blob_hash) VALUES (:g,:k,:p,:r,:a,:b)"),{"g":generation_id,"k":b.input_key,"p":b.position,"r":b.artifact_role,"a":b.derived_spatial_artifact_id,"b":b.blob_hash})
            await conn.exec_driver_sql("COMMIT")
        except Exception:
            with contextlib.suppress(Exception): await conn.exec_driver_sql("ROLLBACK")
            raise
