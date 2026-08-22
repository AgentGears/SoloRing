"""M9 r3 — §60 designated target-dimension fixture (B6 closure).

The designated target Shot exercises, through the PRODUCTION compiler
and a purpose-built schema-2 package: recurring characters AND
locations (multi-entity dependencies), feature-value facet resolution,
requirement changes, state-specific realization changes, optional
approved anchors, a not-applicable feature value, multi-view multi-item
packs, multi-channel + shared-channel selectors, the capacity matrix
(required overflow + all four optional omission reasons).
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest
from sqlalchemy import text

from soloring.realization.authority import build_captured_authority
from soloring.realization.compiler import compile_realization
from soloring.realization.profile import parse_profile
from soloring.workflows.manifest import parse_manifest_v2
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


def _target_package(tmp_path):
    """Schema-2 package with THREE channels: hero (1 primary), detail
    (2, primary+supporting), shared (3, primary) fed by BOTH an entity
    and a feature_value selector."""
    pkg = tmp_path / "pkg_target"
    shutil.copytree(V4_DIR, pkg)

    manifest = json.loads((pkg / "manifest.json").read_text())
    manifest["inputs"]["reference_image"]["source"] = {
        "kind": "realization_channel", "channel": "hero",
    }
    manifest["inputs"]["detail_image"] = {
        "node": "4", "field": "image", "kind": "image",
        "required": False, "cardinality": None,
        "source": {"kind": "realization_channel", "channel": "detail"},
    }
    manifest["inputs"]["shared_image"] = {
        "node": "4", "field": "image", "kind": "image",
        "required": False, "cardinality": None,
        "source": {"kind": "realization_channel", "channel": "shared"},
    }
    (pkg / "manifest.json").write_text(json.dumps(manifest))

    profile = {
        "schema_version": 1,
        "profile_id": "m9r3-target-dimension",
        "profile_version": 1,
        "workflow_id": "hunyuan_i2v",
        "workflow_version": 4,
        "model": {
            "id": "hunyuan-video-i2v",
            "version": "q4_k_m-720p-llava",
        },
        "channels": {
            "hero": {
                "input_key": "reference_image", "min_items": 1,
                "max_items": 1, "allowed_roles": ["primary"],
            },
            "detail": {
                "input_key": "detail_image", "min_items": 0,
                "max_items": 2,
                "allowed_roles": ["primary", "supporting"],
            },
            "shared": {
                "input_key": "shared_image", "min_items": 0,
                "max_items": 3, "allowed_roles": ["primary"],
            },
        },
        "rules": [
            {"target_kind": "entity", "facet_key": "identity",
             "channel": "hero"},
            {"target_kind": "entity", "facet_key": "hair",
             "channel": "detail"},
            {"target_kind": "entity", "facet_key": "wardrobe",
             "channel": "detail"},
            # SHARED channel: one entity + one feature_value selector.
            {"target_kind": "entity", "facet_key": "signage",
             "channel": "shared"},
            {"target_kind": "feature_value", "facet_key": "cut",
             "channel": "shared"},
        ],
        "parameter_overrides": {},
    }
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


async def _target_state(client, factory, engine, settings, pid):
    """Recurring characters AND locations; identity required; hair
    optional multi-view; wardrobe optional; signage optional; cut
    feature required; scar feature under a not_applicable override."""
    eva, eva_rev = await _entity_with_revision(
        client, factory, pid, name="Eva"
    )
    lobby, lobby_rev = await _entity_with_revision(
        client, factory, pid, name="Lobby", kind="location"
    )
    assets = await _assets(engine, pid, 3)

    feat_cut = await _feature(client, eva["id"])
    feat_scar = await _feature(
        client, eva["id"], key="cheek_scars",
        enum_values=["none", "light", "heavy"],
    )

    # Facets: identity + hair (multi-view 2 items) on Eva; signage on
    # Lobby; cut (feature_value) required; scar not_applicable.
    f_identity = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="identity",
    )
    f_hair = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="hair",
        requirement="optional",
    )
    f_signage = await _facet(
        client, pid, "entity", entity_id=lobby["id"],
        facet_key="signage", requirement="optional",
    )
    f_cut = await _facet(
        client, pid, "feature", feature_id=feat_cut["id"],
        facet_key="cut",
    )
    f_scar = await _facet(
        client, pid, "feature", feature_id=feat_scar["id"],
        facet_key="scar", requirement="required",
    )
    await client.put(
        f"/visual-facets/{f_scar['id']}/value-policies",
        json={"policies": [{"value": "light",
                            "policy": "not_applicable"}]},
    )

    # Realizations: identity (1 primary), hair (primary + supporting
    # multi-view), signage (primary), cut at "fresh".
    a = await client.post(
        f"/visual-facets/{f_identity['id']}/anchors",
        json={"entity_revision_id": eva_rev},
    )
    await _approve_anchor(client, a.json()["id"], assets[:1], ["front"])
    a = await client.post(
        f"/visual-facets/{f_hair['id']}/anchors",
        json={"entity_revision_id": eva_rev},
    )
    await client.put(
        f"/visual-anchors/{a.json()['id']}/items",
        json={"items": [
            {"asset_id": assets[1], "role": "primary", "view_key": "side"},
            {"asset_id": assets[2], "role": "supporting",
             "view_key": "back"},
        ]},
    )
    r = await client.post(f"/visual-anchors/{a.json()['id']}/revisions")
    await client.post(
        f"/visual-anchor-revisions/{r.json()['id']}/approve",
        json={"expected_approved_revision_id": None},
    )
    a = await client.post(
        f"/visual-facets/{f_signage['id']}/anchors",
        json={"entity_revision_id": lobby_rev},
    )
    await _approve_anchor(client, a.json()["id"], assets[:1], ["front"])
    a = await client.post(
        f"/visual-facets/{f_cut['id']}/anchors",
        json={"value": "fresh",
              "visual_context_entity_revision_id": eva_rev},
    )
    await _approve_anchor(client, a.json()["id"], assets[:1], ["macro"])

    seq, scene, shots = await _topology(client, factory, pid)
    await _depend(client, shots[0], [eva["id"], lobby["id"]])
    await client.post(
        f"/continuity-features/{feat_cut['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )
    await client.post(
        f"/continuity-features/{feat_scar['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "light"},
    )
    return shots[0], eva, lobby


async def test_designated_target_dimension_matrix(
    client, factory, engine, settings, tmp_path,
):
    pkg = _target_package(tmp_path)
    settings.workflow_package_dir = pkg
    pid = await _seed_project(factory)
    shot, eva, lobby = await _target_state(
        client, factory, engine, settings, pid
    )

    visual = await _resolver_result(engine, shot)
    assert visual.visual_continuity_ready
    requirement_map = {
        s.visual_facet_id: s.requirement for s in visual.facet_statuses
    }
    authority = build_captured_authority(visual.pack, requirement_map)

    # Target dimension assertions (§60 list).
    kinds = {f.target_kind for f in authority.facets}
    assert kinds == {"entity", "feature_value"}
    entity_ids = {
        f.entity_id for f in authority.facets
        if f.target_kind == "entity"
    }
    assert entity_ids == {eva["id"], lobby["id"]}  # character + location
    hair = next(f for f in authority.facets if f.facet_key == "hair")
    assert len(hair.items) == 2  # multi-view multi-item pack

    profile = parse_profile(
        (pkg / "realization-profile.json").read_text()
    )
    manifest = parse_manifest_v2((pkg / "manifest.json").read_text())
    result = compile_realization(
        captured_visual_authority=authority,
        profile=profile, manifest=manifest,
        profile_hash="p" * 64, execution_model_fingerprint_hash="f" * 64,
    )
    assert result.ready, result.issues

    by_channel = {
        c["channel"]: c["bindings"] for c in result.spec["channels"]
    }
    # Multi-channel: three channels exercised.
    assert set(by_channel) == {"hero", "detail", "shared"}
    # Entity facet resolution: identity on hero.
    assert [b["facet_key"] for b in by_channel["hero"]] == ["identity"]
    # Feature-value resolution: cut on shared.
    assert "cut" in [b["facet_key"] for b in by_channel["shared"]]
    # Shared channel fed by BOTH selector kinds.
    shared_kinds = {b["target"]["kind"] for b in by_channel["shared"]}
    assert shared_kinds == {"entity", "feature_value"}
    # Multi-item atomic: hair binds BOTH views on detail.
    hair_bindings = [
        b for b in by_channel["detail"] if b["facet_key"] == "hair"
    ]
    assert len(hair_bindings) == 2
    # not_applicable: scar never appears anywhere.
    all_keys = {
        b["facet_key"] for c in result.spec["channels"]
        for b in c["bindings"]
    }
    assert "scar" not in all_keys
    # Determinism.
    again = compile_realization(
        captured_visual_authority=authority,
        profile=profile, manifest=manifest,
        profile_hash="p" * 64, execution_model_fingerprint_hash="f" * 64,
    )
    from soloring.domain.canonical import canonical_json_str

    assert canonical_json_str(result.spec) == canonical_json_str(again.spec)

    # Requirement-change dimension: flip hair optional→required and
    # re-resolve current state — hair remains bound (it has an approved
    # realization) and the matrix still resolves.
    facets = (await client.get(
        f"/projects/{pid}/visual-facets"
    )).json()
    hair_facet = next(f for f in facets if f["facet_key"] == "hair")
    await client.patch(
        f"/visual-facets/{hair_facet['id']}",
        json={"requirement": "required"},
    )
    visual2 = await _resolver_result(engine, shot)
    assert visual2.visual_continuity_ready
    authority2 = build_captured_authority(
        visual2.pack,
        {s.visual_facet_id: s.requirement
         for s in visual2.facet_statuses},
    )
    result2 = compile_realization(
        captured_visual_authority=authority2,
        profile=profile, manifest=manifest,
        profile_hash="p" * 64, execution_model_fingerprint_hash="f" * 64,
    )
    assert result2.ready
    hair2 = [
        b for c in result2.spec["channels"] for b in c["bindings"]
        if b["facet_key"] == "hair"
    ]
    assert len(hair2) == 2
    assert hair2[0]["required"] is True


async def test_designated_target_omission_reason_matrix(tmp_path):
    """All four closed omission reasons + required capacity overflow in
    one compiler fixture over the target package shape."""
    from soloring.realization.authority import (
        CapturedFacet,
        CapturedItem,
        CapturedVisualAuthority,
    )

    pkg = _target_package(tmp_path)

    def facet(fid, key, requirement="optional", kind="entity", items=None):
        return CapturedFacet(
            visual_facet_id=fid, facet_key=key, requirement=requirement,
            target_kind=kind,
            entity_id="eva" if kind == "entity" else None,
            entity_revision_id="rev" if kind == "entity" else None,
            feature_id="feat" if kind != "entity" else None,
            feature_value_hash="vh" if kind != "entity" else None,
            feature_value_json='"fresh"' if kind != "entity" else None,
            visual_context_entity_revision_id=(
                "rev" if kind != "entity" else None
            ),
            visual_anchor_id=f"anchor-{fid}",
            visual_anchor_revision_id=f"var-{fid}",
            visual_anchor_snapshot_hash="h" * 64,
            items=tuple(items or []),
        )

    def item(n, role="primary", position=0):
        return CapturedItem(
            asset_id=f"a{n}", blob_hash=f"{n}" * 64, role=role,
            view_key=None, position=position,
        )

    # wardrobe2 rule on detail (added below) lets its WHOLE eligible set
    # compete with hair for detail's max_items=2; a context-only channel
    # gives wardrobe's rule a role filter that excludes every item of a
    # legal one-primary facet (no_allowed_items).
    profile_doc = json.loads(
        (pkg / "realization-profile.json").read_text()
    )
    profile_doc["rules"].append(
        {"target_kind": "entity", "facet_key": "wardrobe2",
         "channel": "detail"}
    )
    for rule in profile_doc["rules"]:
        if rule["facet_key"] == "wardrobe":
            rule["channel"] = "context_only"
    profile_doc["channels"]["context_only"] = {
        "input_key": "context_image", "min_items": 0, "max_items": 2,
        "allowed_roles": ["context"],
    }
    (pkg / "realization-profile.json").write_text(json.dumps(profile_doc))
    manifest_doc = json.loads((pkg / "manifest.json").read_text())
    manifest_doc["inputs"]["context_image"] = {
        "node": "4", "field": "image", "kind": "image",
        "required": False, "cardinality": None,
        "source": {"kind": "realization_channel",
                   "channel": "context_only"},
    }
    (pkg / "manifest.json").write_text(json.dumps(manifest_doc))
    profile = parse_profile(
        (pkg / "realization-profile.json").read_text()
    )
    manifest = parse_manifest_v2((pkg / "manifest.json").read_text())

    # --- Overflow fixture: wardrobe2 REQUIRED with 3 eligible items
    # against detail max_items=2 (hair also targets detail; canonical
    # order: identity < hair < scar-less set; wardrobe2 last).
    authority = CapturedVisualAuthority(
        "a" * 64,
        (
            facet("f1", "identity", requirement="required", items=[item(1)]),
            facet("f2", "unknown_facet", items=[item(3)]),
            facet("f3", "wardrobe", items=[item(4), item(10, role="supporting", position=1)]),
            facet(
                "f5", "wardrobe2", requirement="required",
                items=[
                    item(7), item(8, role="supporting", position=1),
                    item(9, role="supporting", position=2),
                ],
            ),
        ),
    )
    result = compile_realization(
        captured_visual_authority=authority,
        profile=profile, manifest=manifest,
        profile_hash="p" * 64, execution_model_fingerprint_hash="f" * 64,
    )
    assert result.ready is False
    codes = {i["error_code"] for i in result.issues}
    assert codes == {"REALIZATION_CAPACITY_EXCEEDED"}
    statuses = {o.facet_key: o.status for o in result.facet_outcomes}
    assert statuses["wardrobe2"] == "required_blocked"
    assert statuses["identity"] == "selected"

    # --- Omission-reason fixture: wardrobe2 optional with 2 items.
    authority2 = CapturedVisualAuthority(
        "a" * 64,
        (
            facet("f1", "identity", requirement="required", items=[item(1)]),
            facet("f2", "unknown_facet", items=[item(3)]),
            facet("f3", "wardrobe", items=[item(4), item(10, role="supporting", position=1)]),
            facet("f4", "hair", items=[item(5), item(6, role="supporting", position=1)]),
            facet("f5", "wardrobe2", items=[item(7), item(8, role="supporting", position=1)]),
        ),
    )
    result2 = compile_realization(
        captured_visual_authority=authority2,
        profile=profile, manifest=manifest,
        profile_hash="p" * 64, execution_model_fingerprint_hash="f" * 64,
    )
    assert result2.ready
    reasons = {o.facet_key: o.reason for o in result2.omitted_optional}
    assert reasons["unknown_facet"] == "no_matching_rule"
    assert reasons["wardrobe"] == "no_allowed_items"
    assert reasons["wardrobe2"] == "capacity_exceeded"

    # --- channel_minimum_unmet: detail (optional-only feed) min_items=3.
    profile_doc["channels"]["detail"]["min_items"] = 3
    profile_doc["channels"]["detail"]["max_items"] = 3
    (pkg / "realization-profile.json").write_text(json.dumps(profile_doc))
    profile3 = parse_profile(
        (pkg / "realization-profile.json").read_text()
    )
    result3 = compile_realization(
        captured_visual_authority=authority2,
        profile=profile3, manifest=manifest,
        profile_hash="p" * 64, execution_model_fingerprint_hash="f" * 64,
    )
    assert result3.ready  # optional-only below min → omit, not block
    reasons3 = {o.facet_key: o.reason for o in result3.omitted_optional}
    assert reasons3["hair"] == "channel_minimum_unmet"
    # wardrobe2 overflowed capacity first (hair 2 + wardrobe2 2 > 3).
    assert reasons3["wardrobe2"] == "capacity_exceeded"
