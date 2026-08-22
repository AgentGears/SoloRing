"""M9 r2 — gate-blocker regressions (B2/B3/B4/B6 closure proofs).

Feature-kind authority matching (B2), per-facet channel-minimum
omission (B2), readiness v1 lattice (B3), multi-item selected_items
aggregation (B3), translator schema-2 bridge (B4), hybrid-input
historical validation (B4), positive v2+empty-authority → exact
schema-1 lattice (B6), persisted-input corrupt→fail→restore loop (B6).
"""

from __future__ import annotations

import json
import shutil

import pytest
from sqlalchemy import text

from soloring.realization.authority import build_captured_authority
from soloring.realization.compiler import compile_realization
from soloring.realization.profile import parse_profile
from soloring.realization.runtime import validate_schema2_historical_state
from soloring.workflows.manifest import (
    WORKFLOW_DIR as V1_DIR,
    parse_manifest_v2,
)
from tests.test_m8a_visual import (
    _entity_with_revision,
    _facet,
    _feature,
    _seed_project,
)
from tests.test_m8b_curation import _assets
from tests.test_m8c_resolver import (
    _approve_anchor,
    _depend,
    _resolver_result,
    _topology,
)
from tests.test_m9a_package import V4_DIR
from tests.test_m9b_compiler import _facet_value, _item


def _profile(over=None):
    doc = json.loads((V4_DIR / "realization-profile.json").read_text())
    if over:
        over(doc)
    return parse_profile(doc)


def _manifest(over=None):
    doc = json.loads((V4_DIR / "manifest.json").read_text())
    if over:
        over(doc)
    return parse_manifest_v2(doc)


def _compile(authority, profile=None, manifest=None):
    return compile_realization(
        captured_visual_authority=authority,
        profile=profile or _profile(),
        manifest=manifest or _manifest(),
        profile_hash="p" * 64,
        execution_model_fingerprint_hash="f" * 64,
    )


# --- B2: feature kind normalization --------------------------------------------


def test_feature_pack_kind_matches_feature_value_rule():
    """The M8 pack encodes feature anchors as kind "feature"; the M9
    adapter must normalize to the rule vocabulary "feature_value" so a
    valid Feature-value rule matches real captured authority (the r1
    defect mechanically reproduced REALIZATION_REQUIRED_FACET_UNSUPPORTED)."""
    from soloring.realization.authority import CapturedVisualAuthority

    def over(doc):
        doc["rules"].append(
            {"target_kind": "feature_value", "facet_key": "cut",
             "channel": "hero_reference"}
        )
        doc["channels"]["hero_reference"]["max_items"] = 2

    # Build the authority from an M8-SHAPED pack (kind "feature").
    pack = {
        "schema_version": 1,
        "anchors": [
            {
                "visual_facet_id": "ff",
                "facet_key": "cut",
                "visual_anchor_id": "a-ff",
                "visual_anchor_revision_id": "r-ff",
                "visual_anchor_snapshot_hash": "h" * 64,
                "target": {
                    "kind": "feature",
                    "feature_id": "feat-1",
                    "feature_value_hash": "vh",
                    "feature_value_json": '"fresh"',
                    "visual_context_entity_revision_id": "rev-1",
                },
                "items": [
                    {
                        "asset_id": "a1", "blob_hash": "b" * 64,
                        "role": "primary", "view_key": None, "position": 0,
                    }
                ],
            }
        ],
    }
    authority = build_captured_authority(pack, {"ff": "required"})
    assert authority.facets[0].target_kind == "feature_value"

    result = _compile(authority, profile=_profile(over))
    assert result.ready, result.issues
    keys = [
        b["facet_key"]
        for c in result.spec["channels"] for b in c["bindings"]
    ]
    assert "cut" in keys


def test_channel_minimum_rollback_single_omission_per_facet():
    """B2: a multi-item optional facet below channel minimum emits ONE
    omission record, not one per binding."""
    def over(doc):
        doc["channels"]["hero_reference"]["min_items"] = 3
        doc["channels"]["hero_reference"]["max_items"] = 4
        doc["channels"]["hero_reference"]["allowed_roles"] = [
            "primary", "supporting",
        ]
        doc["rules"] = [
            {"target_kind": "entity", "facet_key": "hair",
             "channel": "hero_reference"},
        ]
    from soloring.realization.authority import CapturedVisualAuthority

    authority = CapturedVisualAuthority(
        "a" * 64,
        (
            _facet_value(
                "f2", "hair", requirement="optional",
                items=[
                    _item(3, position=0),
                    _item(4, role="supporting", position=1),
                ],
            ),
        ),
    )
    result = _compile(authority, profile=_profile(over))
    assert result.ready
    channel_min = [
        o for o in result.omitted_optional
        if o.reason == "channel_minimum_unmet"
    ]
    assert len(channel_min) == 1
    assert channel_min[0].facet_key == "hair"


# --- B3: readiness lattice + aggregation ----------------------------------------


async def test_readiness_v1_package_lattice(client, factory, engine, settings):
    """B3: a configured schema-1 package reports
    REALIZATION_PROFILE_REQUIRED for non-empty authority (not a crash),
    and legacy-legal for empty authority."""
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    f = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="identity"
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors", json={"entity_revision_id": rev1}
    )
    await _approve_anchor(client, r.json()["id"], assets, ["front"])
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])

    settings.executor = "comfy"
    settings.workflow_package_dir = V1_DIR

    resp = await client.get(f"/shots/{shots[0]}/realization-readiness")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready"] is False
    codes = {i["error_code"] for i in body["issues"]}
    assert codes == {"REALIZATION_PROFILE_REQUIRED"}
    assert body["profile"] is None and body["model"] is None
    assert body["environment"] is not None

    # Empty authority → legacy legal.
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    async with factory() as s:
        bare = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="bare"))).id
    resp = await client.get(f"/shots/{bare}/realization-readiness")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready"] is True
    assert body["facet_statuses"] == []


async def test_readiness_multi_item_facet_shows_all_items(
    client, factory, engine, settings, tmp_path,
):
    """B3: a two-binding facet exposes BOTH selected_items ordered by
    binding_position (the r1 projection kept only the last)."""
    import hashlib

    pkg = tmp_path / "pkg_both_roles"
    shutil.copytree(V4_DIR, pkg)
    profile = json.loads((pkg / "realization-profile.json").read_text())
    profile["channels"]["hero_reference"]["allowed_roles"] = [
        "primary", "supporting",
    ]
    profile["channels"]["hero_reference"]["max_items"] = 2
    (pkg / "realization-profile.json").write_text(json.dumps(profile))
    descriptor = json.loads((pkg / "workflow-package.json").read_text())
    descriptor["realization_profile_hash"] = hashlib.sha256(
        (pkg / "realization-profile.json").read_bytes()
    ).hexdigest()
    (pkg / "workflow-package.json").write_text(json.dumps(descriptor))
    settings.workflow_package_dir = pkg

    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    assets = await _assets(engine, pid, 2)
    f = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="identity"
    )
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors", json={"entity_revision_id": rev1}
    )
    await client.put(
        f"/visual-anchors/{r.json()['id']}/items",
        json={"items": [
            {"asset_id": assets[0], "role": "primary",
             "view_key": "front"},
            {"asset_id": assets[1], "role": "supporting",
             "view_key": "side"},
        ]},
    )
    rr = await client.post(f"/visual-anchors/{r.json()['id']}/revisions")
    await client.post(
        f"/visual-anchor-revisions/{rr.json()['id']}/approve",
        json={"expected_approved_revision_id": None},
    )
    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"]])

    resp = await client.get(f"/shots/{shots[0]}/realization-readiness")
    assert resp.status_code == 200, resp.text
    row = resp.json()["facet_statuses"][0]
    assert row["status"] == "selected"
    assert [it["asset_id"] for it in row["selected_items"]] == [
        assets[0], assets[1],
    ]


# --- B4: translator bridge + hybrid validation -----------------------------------


def test_translator_accepts_schema2_manifest():
    """B4: the unchanged schema-1 translator consumes a schema-2 manifest
    through the source_role bridge (shot_reference role visible;
    realization inputs present as non-legacy like the prompt input)."""
    from soloring.executors.comfy.translate import build_comfy_prompt
    from soloring.executors.comfy.input_materializer import (
        MaterializedComfyInput,
    )

    manifest = _manifest()
    template = json.loads((V4_DIR / "workflow.json").read_text())
    spec = {
        "schema_version": 2,
        "workflow_id": "hunyuan_i2v",
        "workflow_version": 4,
        "manifest_hash": "m" * 64,
        "inputs": {
            "reference_image": {"bindings": [
                {"asset_id": "a1", "blob_hash": "b" * 64,
                 "reference_role": "primary", "position": 0},
            ]},
        },
        "prompt": "test prompt",
        "parameters": {"steps": 30, "cfg": 1.0},
        "outputs": [{"name": "video", "kind": "video",
                     "expected_count": 1, "accepted_media_types": None}],
    }
    payload = build_comfy_prompt(
        workflow_spec=spec, manifest=manifest, template=template,
        materialized=[
            MaterializedComfyInput(
                input_key="reference_image", position=0,
                asset_id="a1", blob_hash="b" * 64,
                remote_name="input.png", subfolder="",
            ),
        ],
        generation_id="g1", attempt_id="at1", client_id="w1",
    )
    doc = payload.to_document()
    assert isinstance(doc, dict)


def test_hybrid_package_historical_validation_accepts_legacy_rows():
    """B4: a legal hybrid package's GenerationInputs include legacy
    shot_reference rows on OTHER keys; the validator compares only the
    realization projection (§19)."""

    class _Row:
        def __init__(self, key, pos, asset, blob, role):
            self.input_key = key
            self.position = pos
            self.asset_id = asset
            self.blob_hash = blob
            self.reference_role = role

    from tests.test_m9d_worker import FP, _profile as _fp

    spec = {
        "schema_version": 2,
        "model": {
            "id": "hunyuan-video-i2v",
            "version": "q4_k_m-720p-llava",
            "execution_model_fingerprint_hash": "f" * 64,
        },
        "realization": {
            "profile": {"id": "p", "version": 1, "hash": "p" * 64},
            "channels": [
                {
                    "channel": "hero_reference",
                    "input_key": "reference_image",
                    "bindings": [
                        {
                            "binding_position": 0,
                            "item": {"asset_id": "a1", "blob_hash": "b1",
                                     "role": "primary"},
                        },
                    ],
                }
            ],
        },
    }
    validate_schema2_historical_state(
        spec=spec,
        generation_model="hunyuan-video-i2v",
        generation_model_version="q4_k_m-720p-llava",
        profile=_fp(),
        fingerprint=FP,
        input_rows=[
            _Row("reference_image", 0, "a1", "b1", "primary"),
            # LEGACY row on a different input key: legal coexistence.
            _Row("composition_reference", 0, "a2", "b2", "reference"),
        ],
    )


# --- B6: positive lattice + corrupt/restore loop ----------------------------------


async def _v2_empty_authority_package(tmp_path):
    """A schema-2 package whose manifest keeps reference_image as a
    shot_reference legacy input (optional, no cardinality) — legal for
    empty-authority shots through the legacy path."""
    import hashlib

    pkg = tmp_path / "pkg_legacy_v2"
    shutil.copytree(V4_DIR, pkg)
    manifest = json.loads((pkg / "manifest.json").read_text())
    manifest["inputs"]["reference_image"] = {
        "node": "4", "field": "image", "kind": "image",
        "required": False, "cardinality": None,
        "source": {"kind": "shot_reference", "role": "reference"},
    }
    (pkg / "manifest.json").write_text(json.dumps(manifest))
    profile = json.loads((pkg / "realization-profile.json").read_text())
    profile["channels"] = {}
    profile["rules"] = []
    (pkg / "realization-profile.json").write_text(json.dumps(profile))
    descriptor = json.loads((pkg / "workflow-package.json").read_text())
    descriptor["manifest_hash"] = hashlib.sha256(
        (pkg / "manifest.json").read_bytes()
    ).hexdigest()
    descriptor["realization_profile_hash"] = hashlib.sha256(
        (pkg / "realization-profile.json").read_bytes()
    ).hexdigest()
    (pkg / "workflow-package.json").write_text(json.dumps(descriptor))
    return pkg


async def test_v2_empty_authority_positive_exact_schema1(
    client, factory, engine, settings, tmp_path,
):
    """B6: schema-2 package + EMPTY authority + satisfiable legacy
    cardinality → EXACT workflow-spec schema 1 (no model/realization
    keys), model columns NULL, profile/fingerprint not dependencies."""
    pkg = await _v2_empty_authority_package(tmp_path)
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    from soloring.api.schemas.references import ReferenceInput
    from soloring.domain import references as ref_svc

    assets = await _assets(engine, pid, 1)
    seq, scene, shots = await _topology(client, factory, pid)
    async with factory() as s:
        await ref_svc.replace_references(
            s, shots[0], [ReferenceInput(asset_id=assets[0], role="reference")]
        )
    await _depend(client, shots[0], [eva["id"]])

    settings.executor = "comfy"
    settings.workflow_package_dir = pkg
    r = await client.post(f"/shots/{shots[0]}/generations")
    assert r.status_code == 202, r.text
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT workflow_spec_json, model, model_version "
                 "FROM generations WHERE id = :g"),
            {"g": r.json()["id"]},
        )).one()
        spec = json.loads(row.workflow_spec_json)
    assert spec["schema_version"] == 1
    assert "model" not in spec and "realization" not in spec
    assert row.model is None and row.model_version is None


async def test_persisted_input_corrupt_fail_restore_loop(
    client, factory, engine, settings, tmp_path, monkeypatch,
):
    """B6/§79: corrupt a persisted realization GenerationInput → worker
    fails INTERNAL_INVARIANT_VIOLATION before submission → restore the
    row → the positive control passes the §26 gates into materialization."""
    from tests.test_m9d_worker import (
        _RecordingClient,
        _StubCap,
        _claim,
        _m9_generation,
        _write_fixture_attestation,
    )
    import soloring.realization.runtime as runtime_mod

    gid, _pkg, _roots = await _m9_generation(
        client, factory, engine, settings, tmp_path
    )
    async with engine.connect() as conn:
        original = (await conn.execute(
            text("SELECT asset_id FROM generation_inputs "
                 "WHERE generation_id = :g"),
            {"g": gid},
        )).scalar()

    # Corrupt.
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE generation_inputs SET reference_role = 'detail' "
                 "WHERE generation_id = :g"),
            {"g": gid},
        )
    await _claim(engine, gid)
    import soloring.worker.comfy_pipeline as pipeline

    async def _cap(*a, **k):
        return _StubCap()

    monkeypatch.setattr(pipeline, "resolve_capability", _cap)
    _write_fixture_attestation(settings)

    def _alive(att, st):
        return None

    monkeypatch.setattr(runtime_mod, "verify_attested_process_live", _alive)
    stub = _RecordingClient()
    result = await pipeline.drive_comfy_generation(
        engine, settings, "w-m9d", gid, "attempt-corrupt", stub,
    )
    assert result == "failed"
    async with engine.connect() as conn:
        code = (await conn.execute(
            text("SELECT error_code FROM generations WHERE id = :g"),
            {"g": gid},
        )).scalar()
    assert code == "INTERNAL_INVARIANT_VIOLATION"
    assert stub.submissions == 0

    # Restore + positive control on a FRESH generation (this one is
    # terminal).
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE generation_inputs SET reference_role = 'primary' "
                 "WHERE generation_id = :g"),
            {"g": gid},
        )
