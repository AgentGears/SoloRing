"""M9 r5 — the FULL §60 matrix inside the representative film-scale
fixture (r4-gate closure).

One designated target family inside the ~2,500-Shot representative
database exercises the entire frozen list through the production paths:

* single-reference finite-capacity profile (the baseline v4 package's
  hero channel, max_items=1, primary-only — evaluated against the same
  film-scale target);
* multi-channel profile (hero/detail/shared/context_only/pair);
* two selectors sharing one channel (signage + cut on `shared`);
* required whole-facet capacity overflow (designated blocked target);
* optional no_matching_rule / no_allowed_items / capacity_exceeded /
  channel_minimum_unmet — all on the designated ready target;
* multi-view multi-item packs; feature-value authority; not-applicable;
* package v2 + empty-M8 -> exact workflow-spec schema 1 (generation
  inside the same film-scale database);

plus the bounded statement-count proof on BOTH designated targets
(ready and blocked) through the exact production readiness path.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest
from sqlalchemy import text

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
    _topology,
)
from tests.test_m9a_package import V4_DIR

SCALE_TOTAL_SHOTS = 2_500
SCALE_BULK_OPTIONAL_FACETS = 60


def _matrix_package(tmp_path):
    """The multi-channel §60 package: hero (finite capacity 1, primary),
    detail (2, primary+supporting), shared (3, primary; fed by BOTH an
    entity and a feature_value selector), context_only (2, context-only
    roles), pair (min 2 = the channel-minimum dimension)."""
    pkg = tmp_path / "pkg_matrix"
    shutil.copytree(V4_DIR, pkg)

    manifest = json.loads((pkg / "manifest.json").read_text())
    manifest["inputs"]["reference_image"]["source"] = {
        "kind": "realization_channel", "channel": "hero",
    }
    for channel, key in (
        ("detail", "detail_image"),
        ("shared", "shared_image"),
        ("context_only", "context_image"),
        ("pair", "pair_image"),
    ):
        manifest["inputs"][key] = {
            "node": "4", "field": "image", "kind": "image",
            "required": False, "cardinality": None,
            "source": {"kind": "realization_channel", "channel": channel},
        }
    (pkg / "manifest.json").write_text(json.dumps(manifest))

    profile = {
        "schema_version": 1,
        "profile_id": "m9r5-representative-matrix",
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
            "context_only": {
                "input_key": "context_image", "min_items": 0,
                "max_items": 2, "allowed_roles": ["context"],
            },
            "pair": {
                "input_key": "pair_image", "min_items": 2,
                "max_items": 2, "allowed_roles": ["primary"],
            },
        },
        "rules": [
            {"target_kind": "entity", "facet_key": "identity",
             "channel": "hero"},
            {"target_kind": "entity", "facet_key": "hair",
             "channel": "detail"},
            {"target_kind": "entity", "facet_key": "wardrobe",
             "channel": "context_only"},
            {"target_kind": "entity", "facet_key": "wardrobe2",
             "channel": "detail"},
            {"target_kind": "entity", "facet_key": "earrings",
             "channel": "pair"},
            {"target_kind": "entity", "facet_key": "signage",
             "channel": "shared"},
            {"target_kind": "feature_value", "facet_key": "cut",
             "channel": "shared"},
            {"target_kind": "entity", "facet_key": "braid",
             "channel": "detail"},
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


def _v2_legacy_package(tmp_path):
    """Schema-2 package whose reference input is a LEGACY
    shot_reference (optional) — the v2+empty-authority → exact v1
    lattice path."""
    pkg = tmp_path / "pkg_legacy"
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


async def _anchor_with_items(client, facet_id, binding, assets, items):
    r = await client.post(
        f"/visual-facets/{facet_id}/anchors", json=binding
    )
    anchor_id = r.json()["id"]
    await client.put(
        f"/visual-anchors/{anchor_id}/items",
        json={"items": [
            {"asset_id": a, "role": role, "view_key": view}
            for a, role, view in items
        ]},
    )
    rr = await client.post(f"/visual-anchors/{anchor_id}/revisions")
    assert rr.status_code == 201, rr.text
    await client.post(
        f"/visual-anchor-revisions/{rr.json()['id']}/approve",
        json={"expected_approved_revision_id": None},
    )
    return anchor_id


async def _matrix_targets(client, factory, engine, pid):
    """The designated target family: A (ready, full optional matrix),
    B (required overflow), C (empty authority)."""
    eva, eva_rev = await _entity_with_revision(
        client, factory, pid, name="Eva"
    )
    lobby, lobby_rev = await _entity_with_revision(
        client, factory, pid, name="Lobby", kind="location"
    )
    braun, braun_rev = await _entity_with_revision(
        client, factory, pid, name="Braun"
    )
    assets = await _assets(engine, pid, 3)

    feat_cut = await _feature(client, eva["id"])
    feat_scar = await _feature(
        client, eva["id"], key="cheek_scars",
        enum_values=["none", "light", "heavy"],
    )

    # Target A facets on Eva/Lobby.
    f_identity = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="identity",
    )
    await _anchor_with_items(
        client, f_identity["id"], {"entity_revision_id": eva_rev},
        assets, [(assets[0], "primary", "front")],
    )
    f_hair = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="hair",
        requirement="optional",
    )
    await _anchor_with_items(
        client, f_hair["id"], {"entity_revision_id": eva_rev},
        assets,
        [(assets[1], "primary", "side"),
         (assets[2], "supporting", "back")],  # multi-view multi-item
    )
    f_wardrobe = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="wardrobe",
        requirement="optional",
    )
    await _anchor_with_items(
        client, f_wardrobe["id"], {"entity_revision_id": eva_rev},
        assets, [(assets[0], "primary", None),
                 (assets[1], "supporting", None)],  # roles not in context
    )
    f_wardrobe2 = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="wardrobe2",
        requirement="optional",
    )
    await _anchor_with_items(
        client, f_wardrobe2["id"], {"entity_revision_id": eva_rev},
        assets, [(assets[0], "primary", None),
                 (assets[2], "supporting", None)],  # detail is full → cap
    )
    f_boots = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="boots",
        requirement="optional",  # NO rule → no_matching_rule
    )
    await _anchor_with_items(
        client, f_boots["id"], {"entity_revision_id": eva_rev},
        assets, [(assets[0], "primary", None)],
    )
    f_earrings = await _facet(
        client, pid, "entity", entity_id=eva["id"], facet_key="earrings",
        requirement="optional",  # pair min 2 → channel_minimum_unmet
    )
    await _anchor_with_items(
        client, f_earrings["id"], {"entity_revision_id": eva_rev},
        assets, [(assets[0], "primary", None)],
    )
    f_signage = await _facet(
        client, pid, "entity", entity_id=lobby["id"],
        facet_key="signage", requirement="optional",
    )
    await _anchor_with_items(
        client, f_signage["id"], {"entity_revision_id": lobby_rev},
        assets, [(assets[0], "primary", "facade")],
    )
    f_cut = await _facet(
        client, pid, "feature", feature_id=feat_cut["id"],
        facet_key="cut",
    )
    await _anchor_with_items(
        client, f_cut["id"],
        {"value": "fresh",
         "visual_context_entity_revision_id": eva_rev},
        assets, [(assets[0], "primary", "macro")],
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

    # Target B: Braun with a REQUIRED braid facet whose 3-item eligible
    # set overflows detail (max 2).
    f_braid = await _facet(
        client, pid, "entity", entity_id=braun["id"], facet_key="braid",
    )
    await _anchor_with_items(
        client, f_braid["id"], {"entity_revision_id": braun_rev},
        assets,
        [(assets[0], "primary", None),
         (assets[1], "supporting", None),
         (assets[2], "supporting", None)],
    )

    seq, scene, shots = await _topology(client, factory, pid)
    # Target A: Eva + Lobby.
    await _depend(client, shots[0], [eva["id"], lobby["id"]])
    # Target B: Braun only.
    await _depend(client, shots[1], [braun["id"]])
    # Target C: empty authority (no dependencies, no references).
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc

    async with factory() as s:
        shot_c = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="empty authority"))).id

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
    return shots[0], shots[1], shot_c, eva




async def _count_readiness_statements(client, shot_id, expect_ready):
    from sqlalchemy import event
    from sqlalchemy.engine import Engine as SyncEngine

    n = {"count": 0}

    def before(conn, cursor, statement, params, ctx, many):
        n["count"] += 1

    event.listen(SyncEngine, "before_cursor_execute", before)
    try:
        r = await client.get(f"/shots/{shot_id}/realization-readiness")
        assert r.status_code == 200, r.text
        assert r.json()["ready"] is expect_ready
    finally:
        event.remove(SyncEngine, "before_cursor_execute", before)
    return n["count"], r.json()


async def test_full_matrix_inside_representative_film_scale(
    client, factory, engine, settings, tmp_path,
):
    """The ENTIRE frozen §60 matrix inside one ~2,500-Shot
    representative database, with bounded production-path statement
    counts on both designated targets (ready AND blocked)."""
    matrix_pkg = _matrix_package(tmp_path)
    legacy_pkg = _v2_legacy_package(tmp_path)
    settings.workflow_package_dir = matrix_pkg

    pid = await _seed_project(factory)
    target_a, target_b, target_c, eva = await _matrix_targets(
        client, factory, engine, pid
    )

    # --- Small-fixture statement counts (pre-bulk). ----------------------
    small_a, body_a = await _count_readiness_statements(
        client, target_a, expect_ready=True
    )
    small_b, body_b = await _count_readiness_statements(
        client, target_b, expect_ready=False
    )

    # --- The full matrix on the READY target (production projection). ----
    statuses = {s["facet_key"]: s for s in body_a["facet_statuses"]}
    omitted = {
        o["facet_key"]: o["reason"] for o in body_a["omitted_optional"]
    }
    assert statuses["identity"]["status"] == "selected"
    assert statuses["identity"]["channel"] == "hero"  # finite capacity 1
    assert len(statuses["identity"]["selected_items"]) == 1
    # Multi-view multi-item pack on detail.
    assert len(statuses["hair"]["selected_items"]) == 2
    views = {it["view_key"] for it in statuses["hair"]["selected_items"]}
    assert views == {"side", "back"}
    # Shared channel: both selector kinds bound.
    shared = next(
        c for c in body_a["channels"] if c["channel"] == "shared"
    )
    assert shared["used_items"] == 2  # signage + cut
    assert statuses["signage"]["channel"] == "shared"
    assert statuses["cut"]["channel"] == "shared"
    assert statuses["cut"]["target_kind"] == "feature_value"
    # The four optional omission reasons — ALL on this target.
    assert omitted["boots"] == "no_matching_rule"
    assert omitted["wardrobe"] == "no_allowed_items"
    assert omitted["wardrobe2"] == "capacity_exceeded"
    assert omitted["earrings"] == "channel_minimum_unmet"
    # not_applicable: scar never binds anywhere.
    assert "scar" not in {
        s["facet_key"] for s in body_a["facet_statuses"]
        if s["status"] == "selected"
    }

    # --- The BLOCKED target: required whole-facet overflow. --------------
    assert body_b["ready"] is False
    codes = {i["error_code"] for i in body_b["issues"]}
    assert codes == {"REALIZATION_CAPACITY_EXCEEDED"}
    b_status = {s["facet_key"]: s for s in body_b["facet_statuses"]}
    assert b_status["braid"]["status"] == "required_blocked"
    assert b_status["braid"]["issue_code"] == (
        "REALIZATION_CAPACITY_EXCEEDED"
    )

    # --- Single-reference finite-capacity profile against the SAME
    # film-scale target: the baseline v4 package (hero max 1). ----------
    settings.workflow_package_dir = V4_DIR
    r = await client.get(f"/shots/{target_a}/realization-readiness")
    assert r.status_code == 200, r.text
    v4_body = r.json()
    assert v4_body["ready"] is False  # matrix facets have no v4 rules
    v4_codes = {i["error_code"] for i in v4_body["issues"]}
    assert v4_codes == {"REALIZATION_REQUIRED_FACET_UNSUPPORTED"}
    v4_hero = next(
        c for c in v4_body["channels"]
        if c["channel"] == "hero_reference"
    )
    assert v4_hero["max_items"] == 1  # the finite-capacity profile shape
    settings.workflow_package_dir = matrix_pkg

    # --- Bulk-wire the representative volume. ----------------------------
    import uuid as _uuid

    now = "2026-01-01T00:00:00.000Z"
    async with engine.begin() as conn:
        existing = (await conn.execute(
            text("SELECT COUNT(*) FROM shots WHERE project_id = :p"),
            {"p": pid},
        )).scalar()
        rows = [
            {
                "id": str(_uuid.uuid4()), "project_id": pid,
                "shot_number": 30_000 + k, "title": None,
                "subject": f"bulk {k}", "action": None, "environment": None,
                "framing": None, "camera_motion": None, "lens": None,
                "mood": None, "duration_ms": None, "created_at": now,
                "updated_at": now,
            }
            for k in range(SCALE_TOTAL_SHOTS - existing)
        ]
        await conn.execute(
            text(
                "INSERT INTO shots (id, project_id, shot_number, title, "
                "subject, action, environment, framing, camera_motion, "
                "lens, mood, duration_ms, created_at, updated_at) "
                "VALUES (:id, :project_id, :shot_number, :title, "
                ":subject, :action, :environment, :framing, "
                ":camera_motion, :lens, :mood, :duration_ms, "
                ":created_at, :updated_at)"
            ),
            rows,
        )
        for k in range(SCALE_BULK_OPTIONAL_FACETS):
            await conn.execute(
                text(
                    "INSERT INTO visual_facets (id, project_id, "
                    "target_kind, entity_id, feature_id, facet_key, "
                    "label, description, requirement, created_at, "
                    "updated_at) VALUES (:id, :pid, 'entity', :eid, "
                    "NULL, :key, NULL, NULL, 'optional', :now, :now)"
                ),
                {
                    "id": f"e9000000-0000-4000-8000-{k:012d}",
                    "pid": pid, "eid": eva["id"],
                    "key": f"film{k:03d}", "now": now,
                },
            )
        bad = (await conn.execute(
            text(
                "SELECT COUNT(*) FROM visual_facets vf LEFT JOIN "
                "creative_entities ce ON ce.id = vf.entity_id "
                "WHERE vf.entity_id IS NOT NULL AND ce.project_id != :p"
            ),
            {"p": pid},
        )).scalar()
        total = (await conn.execute(
            text("SELECT COUNT(*) FROM shots WHERE project_id = :p"),
            {"p": pid},
        )).scalar()
    assert bad == 0
    assert total == SCALE_TOTAL_SHOTS

    # --- Statement counts at scale: identical on BOTH targets. -----------
    big_a, body_a2 = await _count_readiness_statements(
        client, target_a, expect_ready=True
    )
    big_b, body_b2 = await _count_readiness_statements(
        client, target_b, expect_ready=False
    )
    assert big_a == small_a, (small_a, big_a)
    assert big_b == small_b, (small_b, big_b)
    # And the matrix outcomes are unchanged at scale.
    omitted2 = {
        o["facet_key"]: o["reason"]
        for o in body_a2["omitted_optional"] if o["facet_key"] in (
            "boots", "wardrobe", "wardrobe2", "earrings",
        )
    }
    assert omitted2 == {
        "boots": "no_matching_rule",
        "wardrobe": "no_allowed_items",
        "wardrobe2": "capacity_exceeded",
        "earrings": "channel_minimum_unmet",
    }

    # --- v2 + empty authority -> exact workflow-spec v1, in the SAME
    # film-scale database (generation through the legacy-compatible
    # schema-2 package). --------------------------------------------------
    settings.executor = "comfy"
    settings.workflow_package_dir = legacy_pkg
    r = await client.post(f"/shots/{target_c}/generations")
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
