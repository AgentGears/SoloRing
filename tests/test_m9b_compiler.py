"""M9B — CapturedVisualAuthority + the ONE compiler + readiness
(frozen plan §§10–21, 34, 78).

Pure compiler fixtures are DB-free (§20). The preview/historical parity
proof (§10.2/§87) builds the same logical M8 state both ways through
production paths and demands byte-identical RealizationSpecs.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from soloring.domain.canonical import canonical_json_str
from soloring.errors import SoloRingError
from soloring.realization.authority import (
    CapturedFacet,
    CapturedItem,
    CapturedVisualAuthority,
    build_captured_authority,
    reconstruct_authority,
)
from soloring.realization.compiler import compile_realization
from soloring.realization.packages import capture_current_package
from soloring.realization.profile import parse_profile
from soloring.workflows.manifest import parse_manifest_v2
from tests.test_m8a_visual import (
    _entity_with_revision,
    _facet,
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


def _facet_value(
    fid, key, requirement="required", kind="entity", items=None,
    entity="eva-1", rev="rev-1", feature="feat-1",
):
    return CapturedFacet(
        visual_facet_id=fid,
        facet_key=key,
        requirement=requirement,
        target_kind=kind,
        entity_id=entity if kind == "entity" else None,
        entity_revision_id=rev if kind == "entity" else None,
        feature_id=feature if kind != "entity" else None,
        feature_value_hash="vh" if kind != "entity" else None,
        feature_value_json='"fresh"' if kind != "entity" else None,
        visual_context_entity_revision_id=rev if kind != "entity" else None,
        visual_anchor_id=f"anchor-{fid}",
        visual_anchor_revision_id=f"var-{fid}",
        visual_anchor_snapshot_hash="h" * 64,
        items=tuple(items or []),
    )


def _item(n, role="primary", position=0):
    return CapturedItem(
        asset_id=f"asset-{n}", blob_hash=f"{n}" * 64, role=role,
        view_key=None, position=position,
    )


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


def _identity_authority():
    return CapturedVisualAuthority(
        visual_reference_pack_hash="a" * 64,
        facets=(
            _facet_value("f1", "identity", items=[_item(1)]),
        ),
    )


# --- §13 item selection + §12 allocation ------------------------------------


def test_primary_only_channel_selects_by_role_filter_not_hardcoding():
    # Two items; allowed_roles=["primary"] retains exactly the primary.
    authority = CapturedVisualAuthority(
        "a" * 64,
        (
            _facet_value(
                "f1", "identity",
                items=[
                    _item(1, role="supporting", position=0),
                    _item(2, role="primary", position=1),
                ],
            ),
        ),
    )
    result = _compile(authority)
    assert result.ready
    b = result.spec["channels"][0]["bindings"][0]
    assert b["item"]["asset_id"] == "asset-2"
    assert b["item"]["source_position"] == 1  # captured order retained


def test_required_unsupported_no_rule_collects_issue_and_no_spec():
    authority = CapturedVisualAuthority(
        "a" * 64, (_facet_value("f1", "face", items=[_item(1)]),)
    )
    result = _compile(authority)
    assert result.ready is False
    assert result.spec is None and result.inputs == ()
    assert result.issues[0]["error_code"] == (
        "REALIZATION_REQUIRED_FACET_UNSUPPORTED"
    )
    assert result.issues[0]["facet_key"] == "face"


def test_required_no_allowed_items_blocks():
    def over(doc):
        doc["channels"]["hero_reference"]["allowed_roles"] = ["supporting"]
    result = _compile(
        CapturedVisualAuthority(
            "a" * 64, (_facet_value("f1", "identity", items=[_item(1)]),)
        ),
        profile=_profile(over),
    )
    assert result.ready is False
    assert result.issues[0]["error_code"] == (
        "REALIZATION_REQUIRED_FACET_UNSUPPORTED"
    )


def test_required_whole_facet_atomic_capacity():
    # max_items=1 with both roles allowed: the required facet's full
    # 2-item eligible set overflows ATOMICALLY (no partial binding).
    def over(doc):
        doc["channels"]["hero_reference"]["allowed_roles"] = [
            "primary", "supporting",
        ]
    authority = CapturedVisualAuthority(
        "a" * 64,
        (
            _facet_value(
                "f1", "identity",
                items=[
                    _item(1, position=0),
                    _item(2, role="supporting", position=1),
                ],
            ),
        ),
    )
    result = _compile(authority, profile=_profile(over))
    assert result.ready is False
    assert result.issues[0]["error_code"] == "REALIZATION_CAPACITY_EXCEEDED"
    assert result.spec is None  # never a partial/truncated binding


def test_optional_omission_reasons_closed_set():
    def over(doc):
        doc["channels"]["hero_reference"]["max_items"] = 3
        doc["channels"]["hero_reference"]["allowed_roles"] = [
            "primary", "supporting",
        ]
        doc["rules"] = [
            {"target_kind": "entity", "facet_key": "identity",
             "channel": "hero_reference"},
            {"target_kind": "entity", "facet_key": "wardrobe",
             "channel": "hero_reference"},
        ]
    authority = CapturedVisualAuthority(
        "a" * 64,
        (
            _facet_value("f1", "identity", items=[_item(1)]),
            # hair: no rule at all
            _facet_value(
                "f2", "hair", requirement="optional", items=[_item(3)]
            ),
            # wardrobe: fits (1+1 <= 3)
            _facet_value(
                "f3", "wardrobe", requirement="optional",
                items=[_item(4), _item(5, role="supporting", position=1)],
            ),
            # boots: rule + items but capacity 1+1+2 > 3
            _facet_value(
                "f4", "boots", requirement="optional",
                items=[_item(6), _item(7, role="supporting", position=1)],
            ),
        ),
    )
    # add a boots rule
    def over2(doc):
        over(doc)
        doc["rules"].append(
            {"target_kind": "entity", "facet_key": "boots",
             "channel": "hero_reference"}
        )
    profile = _profile(over2)
    result = _compile(authority, profile=profile)
    assert result.ready
    reasons = {o.facet_key: o.reason for o in result.omitted_optional}
    # Canonical §50 order processes boots BEFORE wardrobe: identity(1) +
    # boots(2) fit max 3; wardrobe then overflows wholly.
    assert reasons == {
        "hair": "no_matching_rule",
        "wardrobe": "capacity_exceeded",
    }
    # boots bound atomically with BOTH items.
    spec_boots = [
        b for c in result.spec["channels"] for b in c["bindings"]
        if b["facet_key"] == "boots"
    ]
    assert len(spec_boots) == 2


def test_no_allowed_items_omission_reason():
    def over(doc):
        doc["channels"]["hero_reference"]["max_items"] = 2
        doc["rules"].append(
            {"target_kind": "entity", "facet_key": "hair",
             "channel": "hero_reference"}
        )
    authority = CapturedVisualAuthority(
        "a" * 64,
        (
            _facet_value("f1", "identity", items=[_item(1)]),
            _facet_value(
                "f2", "hair", requirement="optional", items=[_item(3)]
            ),
        ),
    )
    profile = _profile(over)
    profile.channels["hero_reference"].allowed_roles = ["supporting"]
    # identity (required, primary-only) now has no allowed item → blocked.
    result = _compile(authority, profile=profile)
    assert result.ready is False
    # Separate fixture: hair optional with primary-only items + supporting
    # channel → no_allowed_items.
    def over2(doc):
        over(doc)
        doc["channels"]["hero_reference"]["allowed_roles"] = ["supporting"]
    profile2 = _profile(over2)
    authority2 = CapturedVisualAuthority(
        "a" * 64,
        (
            _facet_value(
                "f1", "identity",
                items=[_item(1, role="supporting"), _item(9)],
            ),
            _facet_value(
                "f2", "hair", requirement="optional", items=[_item(3)],
            ),
        ),
    )
    result2 = _compile(authority2, profile=profile2)
    reasons = {o.facet_key: o.reason for o in result2.omitted_optional}
    assert reasons.get("hair") == "no_allowed_items"


def test_channel_minimum_unmet_omits_optional_only_channel():
    def over(doc):
        doc["channels"]["hero_reference"]["min_items"] = 2
        doc["channels"]["hero_reference"]["max_items"] = 4
        doc["rules"] = [
            {"target_kind": "entity", "facet_key": "hair",
             "channel": "hero_reference"},
        ]
    authority = CapturedVisualAuthority(
        "a" * 64,
        (
            _facet_value(
                "f2", "hair", requirement="optional", items=[_item(3)],
            ),
        ),
    )
    result = _compile(authority, profile=_profile(over))
    assert result.ready  # optional-only channel below min → omit, not block
    assert [o.reason for o in result.omitted_optional] == [
        "channel_minimum_unmet"
    ]
    assert result.spec["channels"] == []


def test_channel_minimum_unmet_with_required_blocks():
    def over(doc):
        doc["channels"]["hero_reference"]["min_items"] = 2
        doc["channels"]["hero_reference"]["max_items"] = 4
    authority = CapturedVisualAuthority(
        "a" * 64, (_facet_value("f1", "identity", items=[_item(1)]),)
    )
    result = _compile(authority, profile=_profile(over))
    assert result.ready is False
    assert result.issues[0]["error_code"] == (
        "REALIZATION_CHANNEL_MINIMUM_UNMET"
    )


def test_shared_channel_two_selectors_deterministic():
    def over(doc):
        doc["channels"]["hero_reference"]["max_items"] = 3
        doc["rules"].append(
            {"target_kind": "feature_value", "facet_key": "cut",
             "channel": "hero_reference"}
        )
    authority = CapturedVisualAuthority(
        "a" * 64,
        (
            _facet_value(
                "ff", "cut", kind="feature_value", items=[_item(5)]
            ),
            _facet_value("f1", "identity", items=[_item(1)]),
        ),
    )
    result = _compile(authority, profile=_profile(over))
    assert result.ready
    # Entity facet precedes feature facet in §50 order regardless of the
    # profile's rule authoring order.
    keys = [
        b["facet_key"]
        for c in result.spec["channels"] for b in c["bindings"]
    ]
    assert keys == ["identity", "cut"]
    positions = [
        b["binding_position"]
        for c in result.spec["channels"] for b in c["bindings"]
    ]
    assert positions == [0, 1]


def test_double_run_byte_identical_and_overrides_recorded():
    def over(doc):
        doc["parameter_overrides"] = {"cfg": 2.5}
    authority = _identity_authority()
    r1 = _compile(authority, profile=_profile(over))
    r2 = _compile(authority, profile=_profile(over))
    assert canonical_json_str(r1.spec) == canonical_json_str(r2.spec)
    assert r1.parameter_overrides == {"cfg": 2.5}
    assert r1.spec["parameter_overrides"] == {"cfg": 2.5}
    assert r1.spec["profile"]["hash"] == "p" * 64
    assert r1.spec["model"]["execution_model_fingerprint_hash"] == "f" * 64


def test_unknown_override_name_is_binding_invalid():
    def over(doc):
        doc["parameter_overrides"] = {"no_such_param": 1}
    with pytest.raises(SoloRingError) as ei:
        _compile(_identity_authority(), profile=_profile(over))
    assert ei.value.code == "REALIZATION_INPUT_BINDING_INVALID"


def test_compiler_performs_zero_sql_by_design():
    import inspect

    from soloring.realization import compiler

    src = inspect.getsource(compiler)
    for forbidden in ("sqlalchemy", "execute(", "SELECT", "Path(", "open("):
        assert forbidden not in src, forbidden


# --- §10 authority builder + preview/historical parity ------------------------


async def _m8_state(client, factory, engine, pid):
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
    return shots[0], eva, rev1


async def test_preview_historical_parity_byte_identical(
    client, factory, engine,
):
    """§10.2/§87: same logical M8 state (+ same requirement value) →
    current-preview authority == reconstructed historical authority →
    byte-identical RealizationSpec under the same package."""
    from soloring.domain import revisions as revision_svc
    from soloring.realization.authority import reconstruct_pack

    pid = await _seed_project(factory)
    shot, _eva, _rev1 = await _m8_state(client, factory, engine, pid)

    # Capture the schema-4 revision through the production path.
    async with factory() as s:
        revision = await revision_svc.capture_revision(s, shot)

    # Current-preview side: ONE coherent read → resolver result.
    visual = await _resolver_result(engine, shot)
    assert visual.visual_continuity_ready
    requirement_map = {
        st.visual_facet_id: st.requirement for st in visual.facet_statuses
    }
    preview_authority = build_captured_authority(
        visual.pack, requirement_map
    )

    # Historical side: reconstruct + hash-validate from the revision.
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            historical_authority = await reconstruct_authority(
                conn, revision.id, requirement_map
            )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise

    assert preview_authority == historical_authority
    assert (
        historical_authority.visual_reference_pack_hash
        == preview_authority.visual_reference_pack_hash
    )

    package = await capture_current_package(_settings())
    spec_preview = compile_realization(
        captured_visual_authority=preview_authority,
        profile=package.profile,
        manifest=package.manifest_v2,
        profile_hash=package.release.realization_profile_hash,
        execution_model_fingerprint_hash=(
            package.release.execution_model_fingerprint_hash
        ),
    )
    spec_historical = compile_realization(
        captured_visual_authority=historical_authority,
        profile=package.profile,
        manifest=package.manifest_v2,
        profile_hash=package.release.realization_profile_hash,
        execution_model_fingerprint_hash=(
            package.release.execution_model_fingerprint_hash
        ),
    )
    assert spec_preview.ready and spec_historical.ready
    assert canonical_json_str(spec_preview.spec) == canonical_json_str(
        spec_historical.spec
    )


async def test_reconstruction_fails_closed_on_provenance_tamper(
    client, factory, engine,
):
    from soloring.domain import revisions as revision_svc
    from soloring.errors import SoloRingError as SE

    pid = await _seed_project(factory)
    shot, _eva, _rev1 = await _m8_state(client, factory, engine, pid)
    async with factory() as s:
        revision = await revision_svc.capture_revision(s, shot)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE shot_revision_visual_anchor_items SET role = "
                "'detail' WHERE shot_revision_id = :r"
            ),
            {"r": revision.id},
        )
    with pytest.raises(SE) as ei:
        async with engine.connect() as conn:
            await conn.exec_driver_sql("BEGIN")
            try:
                await reconstruct_authority(conn, revision.id, {})
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
    assert ei.value.code == "INTERNAL_INVARIANT_VIOLATIVE" or (
        ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    )


def _settings():
    from soloring.settings import Settings

    import soloring.settings as settings_mod

    if settings_mod._settings is not None:
        return settings_mod._settings
    return Settings()


# --- §34 readiness endpoint ----------------------------------------------------


async def test_readiness_endpoint_ready_and_blocked(client, factory, engine):
    pid = await _seed_project(factory)
    shot, eva, rev1 = await _m8_state(client, factory, engine, pid)

    r = await client.get(f"/shots/{shot}/realization-readiness")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ready"] is True
    assert body["package"]["schema_version"] == 2
    assert body["package"]["realization_profile_hash"]
    assert body["profile"]["id"] == "hunyuan-i2v-single-reference"
    assert body["visual_reference_pack_hash"]
    assert body["channels"][0]["used_items"] == 1
    assert body["channels"][0]["active"] is True
    row = body["facet_statuses"][0]
    assert row["facet_key"] == "identity"
    assert row["status"] == "selected"
    assert row["selected_items"][0]["role"] == "primary"

    # Blocked: a SECOND required facet the profile has no rule for.
    assets = await _assets(engine, pid, 1)
    f2 = await _facet(
        client, pid, "entity", entity_id=eva["id"],
        facet_key="wardrobe", requirement="required",
    )
    anchor = await client.post(
        f"/visual-facets/{f2['id']}/anchors",
        json={"entity_revision_id": rev1},
    )
    await _approve_anchor(client, anchor.json()["id"], assets, ["front"])

    r = await client.get(f"/shots/{shot}/realization-readiness")
    body = r.json()
    assert body["ready"] is False
    codes = {i["error_code"] for i in body["issues"]}
    assert codes == {"REALIZATION_REQUIRED_FACET_UNSUPPORTED"}
    blocked = [
        s for s in body["facet_statuses"]
        if s["status"] == "required_blocked"
    ]
    assert any(s["facet_key"] == "wardrobe" for s in blocked)


async def test_readiness_endpoint_reports_m7_blocker_honestly(
    client, factory,
):
    pid = await _seed_project(factory)
    eva, rev1 = await _entity_with_revision(client, factory, pid)
    from soloring.api.schemas.shots import ShotCreate
    from soloring.domain import shots as shot_svc
    from tests.test_m8a_visual import _feature

    feat = await _feature(client, eva["id"])
    seq, scene, shots = await _topology(client, factory, pid)
    await client.post(
        f"/continuity-features/{feat['id']}/transitions",
        json={"anchor_type": "scene", "anchor_id": scene,
              "boundary": "start", "operation": "set", "value": "fresh"},
    )

    async with factory() as s:
        loose = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="loose"))).id
    await _depend(client, loose, [eva["id"]])
    # Unassigned shot with dependency → M7 NARRATIVE_CONTEXT_REQUIRED.
    r = await client.get(f"/shots/{loose}/realization-readiness")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ready"] is False
    codes = {i["error_code"] for i in body["issues"]}
    assert "NARRATIVE_CONTEXT_REQUIRED" in codes
    assert body["facet_statuses"] == []

