"""Canonical M10 derived-artifact specs and global D0 provenance convergence."""
from __future__ import annotations
import contextlib, json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from soloring.assets.blob_store import BlobStore
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import is_uuid, new_uuid
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial.blob_integrity import blob_integrity_status
from soloring.spatial.error_codes import (
    DERIVED_SPATIAL_BLOB_CORRUPT, DERIVED_SPATIAL_BLOB_MISSING,
    DERIVED_SPATIAL_KIND_UNSUPPORTED, DERIVED_SPATIAL_NONDETERMINISTIC,
    DERIVED_SPATIAL_OUTPUT_INVALID, DERIVED_SPATIAL_PROVENANCE_MISMATCH,
    DERIVED_SPATIAL_RUNTIME_UNPINNABLE, DERIVED_SPATIAL_SPEC_INVALID,
)
from soloring.spatial.math import JS_SAFE_MAX

_SHA = r"^[0-9a-f]{64}$"
class _Strict(BaseModel): model_config = ConfigDict(extra="forbid")

def _nonempty(v: str, label: str) -> None:
    if not v.strip(): raise ValueError(f"{label} must be non-empty")

def _identity(v: Any, path: str) -> None:
    if v is None or isinstance(v, (str, bool)): return
    if isinstance(v, int) and not isinstance(v, bool):
        if abs(v) > JS_SAFE_MAX: raise ValueError(f"{path} outside JavaScript-safe integer domain")
        return
    if isinstance(v, float): raise ValueError(f"{path} must not contain floating-point values")
    if isinstance(v, dict):
        for k, x in v.items():
            if not isinstance(k, str): raise ValueError(f"{path} keys must be strings")
            _identity(x, f"{path}.{k}")
        return
    if isinstance(v, (list, tuple)):
        for i, x in enumerate(v): _identity(x, f"{path}[{i}]")
        return
    raise ValueError(f"{path} contains unsupported identity value {type(v).__name__}")

class SpatialArtifactSource(_Strict):
    spatial_continuity_schema_version: Literal[1]
    spatial_continuity_hash: str = Field(pattern=_SHA)
class SpatialDerivationParameters(_Strict):
    scope: Literal["world", "entity"]
    entity_id: str | None = None
    placement_source_kind: str | None = None
    placement_source_id: str | None = None
    proxy_geometry: dict[str, Any] | None = None
    sampling: dict[str, Any]
    projection: dict[str, Any]
    @model_validator(mode="after")
    def _valid(self):
        _identity(self.proxy_geometry, "proxy_geometry"); _identity(self.sampling, "sampling"); _identity(self.projection, "projection")
        if self.scope == "world":
            if any(x is not None for x in (self.entity_id,self.placement_source_kind,self.placement_source_id,self.proxy_geometry)):
                raise ValueError("world scope must not carry Entity placement identity")
        else:
            if not is_uuid(self.entity_id): raise ValueError("entity scope requires canonical entity_id UUID")
            if not self.placement_source_kind or not self.placement_source_kind.strip(): raise ValueError("entity scope requires placement_source_kind")
            if not self.placement_source_id or not self.placement_source_id.strip(): raise ValueError("entity scope requires placement_source_id")
            if self.proxy_geometry is None: raise ValueError("entity scope requires explicit proxy_geometry")
        return self
class SpatialDerivation(_Strict):
    algorithm_id: str; algorithm_version: str; parameters: SpatialDerivationParameters
    @model_validator(mode="after")
    def _valid(self): _nonempty(self.algorithm_id,"algorithm_id"); _nonempty(self.algorithm_version,"algorithm_version"); return self
class SpatialOutputContract(_Strict):
    media_type: str; encoding: str; width: int = Field(gt=0); height: int = Field(gt=0); frame_count: int = Field(gt=0); time_base_num: int = Field(gt=0); time_base_den: int = Field(gt=0)
    @model_validator(mode="after")
    def _valid(self): _nonempty(self.media_type,"media_type"); _nonempty(self.encoding,"encoding"); return self
class DerivedSpatialArtifactSpec(_Strict):
    schema_version: Literal[1]; artifact_kind: str; artifact_schema_version: int = Field(gt=0); source: SpatialArtifactSource; derivation: SpatialDerivation; output_contract: SpatialOutputContract
    @model_validator(mode="after")
    def _valid(self): _nonempty(self.artifact_kind,"artifact_kind"); return self
class MaterializerIdentity(_Strict):
    algorithm_id: str; algorithm_version: str; implementation_sha256: str = Field(pattern=_SHA)
class MaterializerRuntime(_Strict):
    python: str; numpy: str; platform_contract: str
class ExternalRuntimeComponent(_Strict):
    kind: str; name: str; version_or_commit: str; sha256: str | None = Field(default=None, pattern=_SHA)
class MaterializerRuntimeFingerprint(_Strict):
    schema_version: Literal[1]; materializer: MaterializerIdentity; runtime: MaterializerRuntime; external_components: list[ExternalRuntimeComponent]

@dataclass(frozen=True)
class PreparedDerivedArtifact:
    spec: DerivedSpatialArtifactSpec; spec_json: str; spec_hash: str
    runtime: MaterializerRuntimeFingerprint; runtime_json: str; runtime_hash: str; blob_hash: str

def _err(code: str, message: str, status: int) -> SoloRingError: return SoloRingError(code,message,status_code=status)
def parse_derived_spec(raw: dict | str) -> DerivedSpatialArtifactSpec:
    try: return DerivedSpatialArtifactSpec.model_validate(json.loads(raw) if isinstance(raw,str) else raw)
    except (ValueError,ValidationError,TypeError) as exc: raise _err(DERIVED_SPATIAL_SPEC_INVALID,f"Invalid DerivedSpatialArtifactSpec: {exc}",422) from exc
def parse_runtime_fingerprint(raw: dict | str) -> MaterializerRuntimeFingerprint:
    try: return MaterializerRuntimeFingerprint.model_validate(json.loads(raw) if isinstance(raw,str) else raw)
    except (ValueError,ValidationError,TypeError) as exc: raise _err(DERIVED_SPATIAL_RUNTIME_UNPINNABLE,f"Invalid materializer runtime fingerprint: {exc}",503) from exc

def _canonical(model: BaseModel) -> tuple[str,str]:
    value=model.model_dump(mode="json",exclude_none=False); return canonical_json_str(value), canonical_hash(value)
def validate_derived_provenance_row(row: Mapping[str,object]) -> tuple[DerivedSpatialArtifactSpec,MaterializerRuntimeFingerprint]:
    sj=row.get("spec_json"); rj=row.get("runtime_fingerprint_json")
    if not isinstance(sj,str) or not isinstance(rj,str): raise _err(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Derived provenance is missing canonical bytes.",500)
    spec=parse_derived_spec(sj); runtime=parse_runtime_fingerprint(rj); cs,ch=_canonical(spec); cr,rh=_canonical(runtime)
    if sj != cs or rj != cr: raise _err(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Stored derived provenance bytes are not canonical.",500)
    expected={"spec_schema_version":1,"spec_hash":ch,"spatial_continuity_schema_version":1,"spatial_continuity_hash":spec.source.spatial_continuity_hash,"artifact_kind":spec.artifact_kind,"artifact_schema_version":spec.artifact_schema_version,"algorithm_id":spec.derivation.algorithm_id,"algorithm_version":spec.derivation.algorithm_version,"runtime_fingerprint_hash":rh,"determinism_class":"D0","media_type":spec.output_contract.media_type}
    if any(row.get(k)!=v for k,v in expected.items()): raise _err(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Derived provenance projection disagrees with canonical bytes.",500)
    if (runtime.materializer.algorithm_id,runtime.materializer.algorithm_version)!=(spec.derivation.algorithm_id,spec.derivation.algorithm_version): raise _err(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Stored materializer identity disagrees with derivation spec.",500)
    bh=row.get("blob_hash")
    if not isinstance(bh,str) or not BlobStore.validate_hash(bh): raise _err(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Derived provenance Blob hash is invalid.",500)
    return spec,runtime

def prepare_derived_artifact(spec_raw: dict|str,runtime_raw: dict|str,blob_hash: str,*,allowed_artifact_kinds:frozenset[str],allowed_media_types:frozenset[str],allowed_algorithms:frozenset[tuple[str,str]]) -> PreparedDerivedArtifact:
    spec=parse_derived_spec(spec_raw); runtime=parse_runtime_fingerprint(runtime_raw); alg=(spec.derivation.algorithm_id,spec.derivation.algorithm_version)
    if spec.artifact_kind not in allowed_artifact_kinds: raise _err(DERIVED_SPATIAL_KIND_UNSUPPORTED,f"Unsupported derived artifact kind {spec.artifact_kind!r}.",409)
    if spec.output_contract.media_type not in allowed_media_types: raise _err(DERIVED_SPATIAL_OUTPUT_INVALID,f"Unsupported derived media type {spec.output_contract.media_type!r}.",503)
    if alg not in allowed_algorithms: raise _err(DERIVED_SPATIAL_KIND_UNSUPPORTED,f"Unsupported derived algorithm {alg!r}.",409)
    if (runtime.materializer.algorithm_id,runtime.materializer.algorithm_version)!=alg: raise _err(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Materializer runtime algorithm identity does not match spec.",500)
    if not BlobStore.validate_hash(blob_hash): raise _err(DERIVED_SPATIAL_OUTPUT_INVALID,"Derived Blob hash is not canonical lowercase SHA-256.",503)
    sj,sh=_canonical(spec); rj,rh=_canonical(runtime); return PreparedDerivedArtifact(spec,sj,sh,runtime,rj,rh,blob_hash)

def _projection(p: PreparedDerivedArtifact) -> dict[str,object]:
    s=p.spec; return {"spec_schema_version":1,"spec_json":p.spec_json,"spec_hash":p.spec_hash,"spatial_continuity_schema_version":1,"spatial_continuity_hash":s.source.spatial_continuity_hash,"artifact_kind":s.artifact_kind,"artifact_schema_version":s.artifact_schema_version,"algorithm_id":s.derivation.algorithm_id,"algorithm_version":s.derivation.algorithm_version,"runtime_fingerprint_json":p.runtime_json,"runtime_fingerprint_hash":p.runtime_hash,"determinism_class":"D0","blob_hash":p.blob_hash,"media_type":s.output_contract.media_type}

async def register_derived_artifact(session: AsyncSession,store: BlobStore,project_id: str,p: PreparedDerivedArtifact) -> str:
    if not is_uuid(project_id): raise SoloRingError(ErrorCode.PROJECT_NOT_FOUND,"Project not found.",status_code=404)
    status=await blob_integrity_status(store,p.blob_hash)
    if status!="valid": raise _err(DERIVED_SPATIAL_BLOB_MISSING if status=="missing" else DERIVED_SPATIAL_BLOB_CORRUPT,"Derived artifact physical Blob failed integrity verification.",500)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            if (await conn.execute(text("SELECT 1 FROM projects WHERE id=:p"),{"p":project_id})).first() is None: raise SoloRingError(ErrorCode.PROJECT_NOT_FOUND,f"Project {project_id} not found.",status_code=404)
            if (await conn.execute(text("SELECT 1 FROM blobs WHERE hash=:h"),{"h":p.blob_hash})).first() is None: raise _err(DERIVED_SPATIAL_BLOB_MISSING,"Derived Blob row is missing.",500)
            rows=(await conn.execute(text("SELECT * FROM derived_spatial_artifacts WHERE spec_hash=:s AND runtime_fingerprint_hash=:r"),{"s":p.spec_hash,"r":p.runtime_hash})).mappings().all()
            for row in rows: validate_derived_provenance_row(dict(row))
            seen={row["blob_hash"] for row in rows}
            if seen and seen!={p.blob_hash}: raise _err(DERIVED_SPATIAL_NONDETERMINISTIC,"Same derived spec/runtime produced a different Blob hash.",503)
            existing=(await conn.execute(text("SELECT * FROM derived_spatial_artifacts WHERE project_id=:p AND spec_hash=:s AND runtime_fingerprint_hash=:r"),{"p":project_id,"s":p.spec_hash,"r":p.runtime_hash})).mappings().one_or_none()
            if existing is not None:
                validate_derived_provenance_row(dict(existing))
                if any(existing[k]!=v for k,v in _projection(p).items()): raise _err(DERIVED_SPATIAL_PROVENANCE_MISMATCH,"Existing provenance disagrees with requested projection.",500)
                await conn.exec_driver_sql("COMMIT"); return existing["id"]
            aid=new_uuid(); vals=_projection(p)|{"id":aid,"project_id":project_id}
            await conn.execute(text("INSERT INTO derived_spatial_artifacts (id,project_id,spec_schema_version,spec_json,spec_hash,spatial_continuity_schema_version,spatial_continuity_hash,artifact_kind,artifact_schema_version,algorithm_id,algorithm_version,runtime_fingerprint_json,runtime_fingerprint_hash,determinism_class,blob_hash,media_type,created_at) VALUES (:id,:project_id,:spec_schema_version,:spec_json,:spec_hash,:spatial_continuity_schema_version,:spatial_continuity_hash,:artifact_kind,:artifact_schema_version,:algorithm_id,:algorithm_version,:runtime_fingerprint_json,:runtime_fingerprint_hash,:determinism_class,:blob_hash,:media_type,strftime('%Y-%m-%dT%H:%M:%fZ','now'))"),vals)
            await conn.exec_driver_sql("COMMIT"); return aid
        except Exception:
            with contextlib.suppress(Exception): await conn.exec_driver_sql("ROLLBACK")
            raise
