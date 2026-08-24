"""M10A derived spec/provenance/global-D0 gates (frozen r3 §§102–108)."""
from __future__ import annotations
import hashlib, uuid
import pytest
from sqlalchemy import text
from soloring.assets.blob_store import BlobStore
from soloring.errors import SoloRingError
from soloring.spatial.blob_integrity import blob_integrity_status
from soloring.spatial.derived import _projection,prepare_derived_artifact,register_derived_artifact,validate_derived_provenance_row
from soloring.spatial.derived_inputs import DerivedInputBinding,validate_bindings
from soloring.spatial.error_codes import DERIVED_SPATIAL_NONDETERMINISTIC,DERIVED_SPATIAL_PROVENANCE_MISMATCH,DERIVED_SPATIAL_SPEC_INVALID

KINDS=frozenset({"test.depth"}); MEDIA=frozenset({"image/png"}); ALGS=frozenset({("soloring.boxdepth.rasterizer","1.0.0")})
def _spec(spatial_hash="a"*64,scope="world"):
 p={"scope":scope,"entity_id":None,"placement_source_kind":None,"placement_source_id":None,"proxy_geometry":None,"sampling":{"frame_count":17,"time_base":[1,24]},"projection":{"width":832,"height":480}}
 if scope=="entity": p|={"entity_id":str(uuid.uuid4()),"placement_source_kind":"track","placement_source_id":str(uuid.uuid4()),"proxy_geometry":{"kind":"box","half_extents_mm":[300,850,200]}}
 return {"schema_version":1,"artifact_kind":"test.depth","artifact_schema_version":1,"source":{"spatial_continuity_schema_version":1,"spatial_continuity_hash":spatial_hash},"derivation":{"algorithm_id":"soloring.boxdepth.rasterizer","algorithm_version":"1.0.0","parameters":p},"output_contract":{"media_type":"image/png","encoding":"uint8-depth","width":832,"height":480,"frame_count":17,"time_base_num":1,"time_base_den":24}}
def _runtime(): return {"schema_version":1,"materializer":{"algorithm_id":"soloring.boxdepth.rasterizer","algorithm_version":"1.0.0","implementation_sha256":"b"*64},"runtime":{"python":"3.12.0","numpy":"2.0.0","pillow_png_encoder":"10.0.0", "encoder_identity":{"pillow_release":"10.0.0","pillow_native_module":"_imaging.cp312-win_amd64.pyd","pillow_native_module_sha256":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","python_implementation":"cpython","python_abi_tag":"","platform":"win-amd64","zlib_compile_version":"1.3.1","zlib_runtime_version":"1.3.1"},"platform_contract":"test-cpu"},"external_components":[]}
def _prepare(blob_hash,spec=None,runtime=None): return prepare_derived_artifact(spec or _spec(),runtime or _runtime(),blob_hash,allowed_artifact_kinds=KINDS,allowed_media_types=MEDIA,allowed_algorithms=ALGS)

def test_prepare_canonical_runtime_separate_and_provenance_cross_validated():
 p=_prepare("c"*64); assert p.spec_hash==hashlib.sha256(p.spec_json.encode()).hexdigest(); assert "runtime_fingerprint" not in p.spec_json; validate_derived_provenance_row(_projection(p))
 bad=_projection(p); bad["spec_hash"]="d"*64
 with pytest.raises(SoloRingError) as e: validate_derived_provenance_row(bad)
 assert e.value.code==DERIVED_SPATIAL_PROVENANCE_MISMATCH

def test_float_identity_and_runtime_algorithm_mismatch_fail():
 spec=_spec(); spec["derivation"]["parameters"]["projection"]["near"]=0.1
 with pytest.raises(SoloRingError) as e: _prepare("c"*64,spec=spec)
 assert e.value.code==DERIVED_SPATIAL_SPEC_INVALID
 runtime=_runtime(); runtime["materializer"]["algorithm_version"]="2.0.0"
 with pytest.raises(SoloRingError) as e: _prepare("c"*64,runtime=runtime)
 assert e.value.code==DERIVED_SPATIAL_PROVENANCE_MISMATCH

def test_initial_binding_capacity_positions_and_world_first():
 w=DerivedInputBinding("control",0,"spatial.world_depth",str(uuid.uuid4()),"a"*64); e1=DerivedInputBinding("control",1,"spatial.entity_depth",str(uuid.uuid4()),"b"*64); e2=DerivedInputBinding("control",2,"spatial.entity_depth",str(uuid.uuid4()),"c"*64); validate_bindings((w,e1,e2))
 with pytest.raises(SoloRingError): validate_bindings((DerivedInputBinding("control",1,"spatial.world_depth",str(uuid.uuid4()),"d"*64),))
 with pytest.raises(SoloRingError): validate_bindings((w,DerivedInputBinding("control",2,"spatial.entity_depth",str(uuid.uuid4()),"e"*64)))
 with pytest.raises(SoloRingError): validate_bindings((w,e1,e2,DerivedInputBinding("control",3,"spatial.entity_depth",str(uuid.uuid4()),"f"*64)))

@pytest.mark.asyncio
async def test_blob_integrity_status(settings):
 store=BlobStore(settings); data=b"derived-control"; bh=hashlib.sha256(data).hexdigest(); assert await blob_integrity_status(store,bh)=="missing"; path=store.path_for_hash(bh); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b"wrong"); assert await blob_integrity_status(store,bh)=="corrupt"; path.write_bytes(data); assert await blob_integrity_status(store,bh)=="valid"

async def _seed(engine,store,pid,data):
 bh=hashlib.sha256(data).hexdigest(); path=store.path_for_hash(bh); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
 async with engine.begin() as c:
  await c.execute(text("INSERT INTO projects (id,name) VALUES (:i,:n)"),{"i":pid,"n":pid}); await c.execute(text("INSERT INTO blobs (hash,path,size_bytes) VALUES (:h,:p,:n)"),{"h":bh,"p":store.relative_path_for_hash(bh),"n":len(data)})
 return bh

@pytest.mark.asyncio
async def test_global_d0_convergence_cross_project(engine,factory,settings):
 store=BlobStore(settings); p1,p2=str(uuid.uuid4()),str(uuid.uuid4()); bh=await _seed(engine,store,p1,b"same")
 async with engine.begin() as c: await c.execute(text("INSERT INTO projects (id,name) VALUES (:i,:n)"),{"i":p2,"n":p2})
 prep=_prepare(bh)
 async with factory() as s:
  a1=await register_derived_artifact(s,store,p1,prep); assert a1==await register_derived_artifact(s,store,p1,prep); a2=await register_derived_artifact(s,store,p2,prep)
 assert a1!=a2
 async with engine.connect() as c: rows=(await c.execute(text("SELECT blob_hash FROM derived_spatial_artifacts WHERE spec_hash=:s AND runtime_fingerprint_hash=:r"),{"s":prep.spec_hash,"r":prep.runtime_hash})).all()
 assert len(rows)==2 and {r.blob_hash for r in rows}=={bh}

@pytest.mark.asyncio
async def test_global_d0_different_blob_fails(engine,factory,settings):
 store=BlobStore(settings); p1,p2=str(uuid.uuid4()),str(uuid.uuid4()); b1=await _seed(engine,store,p1,b"first"); b2=hashlib.sha256(b"second").hexdigest(); path=store.path_for_hash(b2); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b"second")
 async with engine.begin() as c:
  await c.execute(text("INSERT INTO projects (id,name) VALUES (:i,:n)"),{"i":p2,"n":p2}); await c.execute(text("INSERT INTO blobs (hash,path,size_bytes) VALUES (:h,:p,:n)"),{"h":b2,"p":store.relative_path_for_hash(b2),"n":6})
 async with factory() as s:
  await register_derived_artifact(s,store,p1,_prepare(b1))
  with pytest.raises(SoloRingError) as e: await register_derived_artifact(s,store,p2,_prepare(b2))
 assert e.value.code==DERIVED_SPATIAL_NONDETERMINISTIC
