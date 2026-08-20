"""M8B — curation, canonical revision, approval (frozen plan §§19–36;
M8B gate incl. §31.4 reuse-integrity regression).

Working items are seeded through the real upload path (asset factory via
seed_reference_asset) so Blob rows + physical bytes genuinely exist.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import text

from soloring.api.schemas.projects import ProjectCreate
from soloring.domain import projects as project_svc
from tests.conftest import seed_reference_asset
from tests.test_m8a_visual import (
    _entity_with_revision,
    _facet,
    _seed_project,
)


async def _anchor(client, factory, pid, name="Eva"):
    e, rev = await _entity_with_revision(client, factory, pid, name=name)
    f = await _facet(client, pid, "entity", entity_id=e["id"])
    r = await client.post(
        f"/visual-facets/{f['id']}/anchors", json={"entity_revision_id": rev}
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _assets(engine, pid, n=2):
    """Seed reference Assets AND their physical Blob bytes (capture's
    provenance check requires registered identity AND existing files)."""
    from soloring.assets.blob_store import BlobStore
    from soloring.settings import get_settings

    store = BlobStore(get_settings())
    out = []
    for _ in range(n):
        aid, bh = await seed_reference_asset(engine, pid)
        path = store.path_for_hash(bh)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"m8b-fixture-" + bh.encode())
        out.append(aid)
    return out


def _put_payload(asset_ids, roles=None, view_keys=None):
    roles = roles or ["primary"] + ["supporting"] * (len(asset_ids) - 1)
    view_keys = view_keys or [None] * len(asset_ids)
    items = []
    for aid, role, vk in zip(asset_ids, roles, view_keys):
        item = {"asset_id": aid, "role": role}
        if vk is not None:
            item["view_key"] = vk
        items.append(item)
    return {"items": items}


async def test_working_set_put_full_contract(client, factory, engine):
    pid = await _seed_project(factory)
    anchor = await _anchor(client, factory, pid)
    assets = await _assets(engine, pid, 3)

    r = await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json=_put_payload(
            assets,
            roles=["primary", "supporting", "detail"],
            view_keys=["  front  ", "left", None],
        ),
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    # Positions contiguous 0..N-1 in submitted order; view_key trimmed;
    # blank would be NULL (here "left" kept, None omitted entirely).
    positions = [it["position"] for it in detail["items"]]
    assert positions == [0, 1, 2]
    assert detail["items"][0]["view_key"] == "front"
    # One primary + items => capturable => working hash present.
    assert detail["working_snapshot_hash"]
    assert detail["approved_snapshot_hash"] is None
    assert detail["working_state_differs_from_approved"] is None

    # Duplicate asset → 422 ITEM_INVALID, atomic (set unchanged).
    r = await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json={"items": [
            {"asset_id": assets[0], "role": "primary"},
            {"asset_id": assets[0], "role": "supporting"},
        ]},
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "VISUAL_ANCHOR_ITEM_INVALID"
    r = await client.get(f"/visual-anchors/{anchor['id']}")
    assert len(r.json()["items"]) == 3

    # Two primaries → 422 MULTIPLE_PRIMARY.
    r = await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json={"items": [
            {"asset_id": assets[0], "role": "primary"},
            {"asset_id": assets[1], "role": "primary"},
        ]},
    )
    assert r.status_code == 422
    assert r.json()["error_code"] == "VISUAL_ANCHOR_MULTIPLE_PRIMARY"

    # Zero primary is a legal draft state: hash NULL.
    r = await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json={"items": [{"asset_id": assets[0], "role": "supporting"}]},
    )
    assert r.status_code == 200
    assert r.json()["working_snapshot_hash"] is None

    # Cross-Project Asset → 409.
    pid_b = await _seed_project(factory, "B")
    foreign = await _assets(engine, pid_b, 1)
    r = await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json={"items": [
            {"asset_id": foreign[0], "role": "primary"},
        ]},
    )
    assert r.status_code == 409
    assert (
        r.json()["error_code"] == "VISUAL_ANCHOR_ASSET_PROJECT_MISMATCH"
    )

    # Missing Asset → 404 ASSET_NOT_FOUND.
    r = await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json={"items": [
            {"asset_id": "00000000-0000-4000-8000-0000000000ff",
             "role": "primary"},
        ]},
    )
    assert r.status_code == 404
    assert r.json()["error_code"] == "ASSET_NOT_FOUND"


async def test_revision_capture_canonical_bytes_and_convergence(
    client, factory, engine,
):
    pid = await _seed_project(factory)
    anchor = await _anchor(client, factory, pid)
    assets = await _assets(engine, pid, 2)
    await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json=_put_payload(assets, view_keys=["front", "three-quarter"]),
    )

    r = await client.post(f"/visual-anchors/{anchor['id']}/revisions")
    assert r.status_code == 201, r.text
    rev = r.json()
    assert rev["revision_number"] == 1

    detail = (
        await client.get(f"/visual-anchor-revisions/{rev['id']}")
    ).json()
    snapshot = json.loads(detail["snapshot_json"])
    # Canonical shape (§28): binding + items only, sorted-key bytes.
    assert snapshot["schema_version"] == 1
    assert snapshot["state_binding"]["kind"] == "entity_revision"
    assert [it["position"] for it in snapshot["items"]] == [0, 1]
    assert snapshot["items"][0]["role"] == "primary"
    assert "approved_revision_id" not in snapshot
    assert "requirement" not in snapshot
    assert "created_at" not in snapshot

    from soloring.domain.canonical import canonical_json_bytes

    assert detail["snapshot_hash"] == hashlib.sha256(
        canonical_json_bytes(snapshot)
    ).hexdigest()

    # Identical recapture converges onto revision 1.
    r = await client.post(f"/visual-anchors/{anchor['id']}/revisions")
    assert r.status_code == 201
    assert r.json()["id"] == rev["id"]
    r = await client.get(f"/visual-anchors/{anchor['id']}/revisions")
    assert len(r.json()) == 1

    # A working change captures a NEW revision with the next number.
    await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json=_put_payload(assets, view_keys=["front", "rear"]),
    )
    r = await client.post(f"/visual-anchors/{anchor['id']}/revisions")
    assert r.status_code == 201
    rev2 = r.json()
    assert rev2["id"] != rev["id"]
    assert rev2["revision_number"] == 2


async def test_capture_requires_exactly_one_primary(client, factory, engine):
    pid = await _seed_project(factory)
    anchor = await _anchor(client, factory, pid)

    # Empty working set → ITEM_INVALID.
    r = await client.post(f"/visual-anchors/{anchor['id']}/revisions")
    assert r.status_code == 422
    assert r.json()["error_code"] == "VISUAL_ANCHOR_ITEM_INVALID"

    assets = await _assets(engine, pid, 1)
    await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json={"items": [{"asset_id": assets[0], "role": "supporting"}]},
    )
    r = await client.post(f"/visual-anchors/{anchor['id']}/revisions")
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_ANCHOR_PRIMARY_REQUIRED"


async def test_approval_lifecycle_and_conflicts(client, factory, engine):
    pid = await _seed_project(factory)
    anchor = await _anchor(client, factory, pid)
    assets = await _assets(engine, pid, 2)
    await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json=_put_payload(assets, view_keys=["front", "rear"]),
    )

    async def capture():
        r = await client.post(
            f"/visual-anchors/{anchor['id']}/revisions"
        )
        assert r.status_code == 201, r.text
        return r.json()

    r1 = await capture()

    # Approve with the correct expected pointer (None).
    r = await client.post(
        f"/visual-anchor-revisions/{r1['id']}/approve",
        json={"expected_approved_revision_id": None},
    )
    assert r.status_code == 200

    # Detail now carries approved hash + differs verdict.
    detail = (await client.get(f"/visual-anchors/{anchor['id']}")).json()
    assert detail["approved_revision_id"] == r1["id"]
    assert detail["approved_snapshot_hash"] == r1["snapshot_hash"]
    assert detail["working_state_differs_from_approved"] is False

    # Idempotent re-approval of the same revision (§34 fires before the
    # pointer check — both expected forms are 200 here).
    r = await client.post(
        f"/visual-anchor-revisions/{r1['id']}/approve",
        json={"expected_approved_revision_id": r1["id"]},
    )
    assert r.status_code == 200
    r = await client.post(
        f"/visual-anchor-revisions/{r1['id']}/approve",
        json={"expected_approved_revision_id": None},
    )
    assert r.status_code == 200

    # §36: edit after approval, capture rev2, authority stays rev1.
    await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json=_put_payload(assets, view_keys=["front", "left-profile"]),
    )
    detail = (await client.get(f"/visual-anchors/{anchor['id']}")).json()
    assert detail["working_state_differs_from_approved"] is True
    assert detail["approved_revision_id"] == r1["id"]
    r2 = await capture()
    assert detail["approved_revision_id"] == r1["id"]

    # Stale pointer for a DIFFERENT revision → 409 (§34).
    r = await client.post(
        f"/visual-anchor-revisions/{r2['id']}/approve",
        json={"expected_approved_revision_id": None},
    )
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_ANCHOR_APPROVAL_CONFLICT"

    # Approve rev2 with the correct expected pointer.
    r = await client.post(
        f"/visual-anchor-revisions/{r2['id']}/approve",
        json={"expected_approved_revision_id": r1["id"]},
    )
    assert r.status_code == 200
    detail = (await client.get(f"/visual-anchors/{anchor['id']}")).json()
    assert detail["approved_revision_id"] == r2["id"]

    # Unapprove with stale pointer → 409.
    r = await client.post(
        f"/visual-anchors/{anchor['id']}/unapprove",
        json={"expected_approved_revision_id": r1["id"]},
    )
    assert r.status_code == 409
    # Correct pointer.
    r = await client.post(
        f"/visual-anchors/{anchor['id']}/unapprove",
        json={"expected_approved_revision_id": r2["id"]},
    )
    assert r.status_code == 200
    detail = (await client.get(f"/visual-anchors/{anchor['id']}")).json()
    assert detail["approved_revision_id"] is None
    assert detail["approved_snapshot_hash"] is None
    # Idempotent unapproval.
    r = await client.post(
        f"/visual-anchors/{anchor['id']}/unapprove",
        json={"expected_approved_revision_id": None},
    )
    assert r.status_code == 200

    # Approved anchor delete is blocked; unapproved deletes fine (§39).
    r = await client.post(
        f"/visual-anchor-revisions/{r2['id']}/approve",
        json={"expected_approved_revision_id": None},
    )
    assert r.status_code == 200
    r = await client.delete(f"/visual-anchors/{anchor['id']}")
    assert r.status_code == 409
    assert r.json()["error_code"] == "VISUAL_ANCHOR_DELETE_BLOCKED"
    await client.post(
        f"/visual-anchors/{anchor['id']}/unapprove",
        json={"expected_approved_revision_id": r2["id"]},
    )
    r = await client.delete(f"/visual-anchors/{anchor['id']}")
    assert r.status_code == 204
    # History survives deletion.
    r = await client.get(f"/visual-anchor-revisions/{r1['id']}")
    assert r.status_code == 200


async def test_revision_reuse_integrity_corruption_loop(
    client, factory, engine,
):
    """§31.4: corrupt snapshot_json or one normalized item field by direct
    SQL UPDATE → identical recapture must fail closed as invariant (no new
    revision, no repair); restoring the exact original value restores
    convergence."""
    from soloring.errors import SoloRingError
    from soloring.visual import anchors as anchor_svc

    pid = await _seed_project(factory)
    anchor = await _anchor(client, factory, pid)
    assets = await _assets(engine, pid, 2)
    await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json=_put_payload(assets, view_keys=["front", "rear"]),
    )
    r = await client.post(f"/visual-anchors/{anchor['id']}/revisions")
    rev_id = r.json()["id"]

    async def factory_session():
        return factory()

    async def run(field: str, bad_value, restore_value):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"UPDATE visual_anchor_revisions SET {field} = :v "
                    "WHERE id = :rid"
                ),
                {"v": bad_value, "rid": rev_id},
            )
        async with factory() as s:
            with pytest.raises(SoloRingError) as ei:
                await anchor_svc.capture_revision(s, anchor["id"])
            assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
            assert ei.value.status_code == 500
        # No new revision was created.
        async with engine.connect() as conn:
            n = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM visual_anchor_revisions "
                        "WHERE visual_anchor_id = :aid"
                    ),
                    {"aid": anchor["id"]},
                )
            ).scalar()
        assert n == 1
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    f"UPDATE visual_anchor_revisions SET {field} = :v "
                    "WHERE id = :rid"
                ),
                {"v": restore_value, "rid": rev_id},
            )

    async with engine.connect() as conn:
        orig_json = (
            await conn.execute(
                text(
                    "SELECT snapshot_json FROM visual_anchor_revisions "
                    "WHERE id = :rid"
                ),
                {"rid": rev_id},
            )
        ).scalar()
        orig_item = (
            await conn.execute(
                text(
                    "SELECT view_key FROM "
                    "visual_anchor_revision_items "
                    "WHERE visual_anchor_revision_id = :rid "
                    "AND position = 1"
                ),
                {"rid": rev_id},
            )
        ).scalar()

    # Corrupt snapshot_json (still valid JSON, different content).
    bad_json = json.loads(orig_json)
    bad_json["items"][0]["view_key"] = "tampered"
    await run("snapshot_json", json.dumps(bad_json), orig_json)

    # Corrupt one normalized item row.
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE visual_anchor_revision_items SET view_key = 'bad' "
                "WHERE visual_anchor_revision_id = :rid AND position = 1"
            ),
            {"rid": rev_id},
        )
    async with factory() as s:
        with pytest.raises(SoloRingError) as ei:
            await anchor_svc.capture_revision(s, anchor["id"])
        assert ei.value.code == "INTERNAL_INVARIANT_VIOLATION"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE visual_anchor_revision_items SET view_key = :vk "
                "WHERE visual_anchor_revision_id = :rid AND position = 1"
            ),
            {"vk": orig_item, "rid": rev_id},
        )

    # Positive control: identical recapture converges again.
    async with factory() as s:
        rid = await anchor_svc.capture_revision(s, anchor["id"])
    assert rid == rev_id


async def test_approval_verifies_revision_integrity_fail_closed(
    client, factory, engine,
):
    """§34: approval of a corrupted revision (snapshot_json/hash mismatch
    or item-projection mismatch) fails closed."""
    pid = await _seed_project(factory)
    anchor = await _anchor(client, factory, pid)
    assets = await _assets(engine, pid, 1)
    await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json={"items": [{"asset_id": assets[0], "role": "primary"}]},
    )
    r = await client.post(f"/visual-anchors/{anchor['id']}/revisions")
    rev_id = r.json()["id"]

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE visual_anchor_revisions SET snapshot_hash = :h "
                "WHERE id = :rid"
            ),
            {"h": "0" * 64, "rid": rev_id},
        )
    r = await client.post(
        f"/visual-anchor-revisions/{rev_id}/approve",
        json={"expected_approved_revision_id": None},
    )
    assert r.status_code == 500
    assert r.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def test_generated_output_promotion_never_automatic(
    client, factory, engine,
):
    """§5/§86: an output Asset enters only via an explicit working-set
    PUT; no earlier step changes authority. (Take generation itself is
    exercised elsewhere; here the Asset-kind invariance + authority chain
    are proven.)"""
    from soloring.db.models import Asset as AssetModel  # noqa: F401
    from sqlalchemy import select

    pid = await _seed_project(factory)
    anchor = await _anchor(client, factory, pid)
    assets = await _assets(engine, pid, 1)

    # Simulate an output-kind asset by direct insert through the model
    # layer (kind stays 'output' — provenance never rewritten, §24).
    from soloring.domain.ids import new_uuid

    aid = new_uuid()
    async with engine.begin() as conn:
        shot_id = (
            await conn.execute(
                text("SELECT id FROM shots WHERE project_id = :p LIMIT 1"),
                {"p": pid},
            )
        ).scalar()
        if shot_id is None:
            from soloring.api.schemas.shots import ShotCreate as SC

            from soloring.domain import shots as shot_svc

            async with factory() as s:
                shot = await shot_svc.create_shot(s, pid, SC(subject="x"))
            shot_id = shot.id
        # Minimal real Generation + Take so the output Asset satisfies
        # the kind/take consistency CHECK. A schema-1 ShotRevision is
        # captured through the real service so the FK target exists.
        from soloring.domain import revisions as revision_svc

        async with factory() as s:
            rev = await revision_svc.capture_revision(s, shot_id)
        gen_id = new_uuid()
        take_id = new_uuid()
        await conn.execute(
            text(
                "INSERT INTO generations (id, shot_id, shot_revision_id, "
                "generation_number, status, operation, executor, "
                "workflow_id, workflow_version, workflow_template_hash, "
                "manifest_hash, compiled_prompt, prompt_compiler_version, "
                "parameters_json, workflow_spec_json, workflow_spec_hash, "
                "executor_submission_state) "
                "VALUES (:gid, :sid, :srid, 1, 'succeeded', 'generate', "
                "'fake', 'test', 'test', '" + "t" * 64 + "', '"
                + "m" * 64 + "', 'p', 'test', '{}', '{}', '"
                + "w" * 64 + "', 'not_started')"
            ),
            {"gid": gen_id, "sid": shot_id, "srid": rev.id},
        )
        await conn.execute(
            text(
                "INSERT INTO takes (id, shot_id, generation_id, output_key) "
                "VALUES (:tid, :sid, :gid, 'o1')"
            ),
            {"tid": take_id, "sid": shot_id, "gid": gen_id},
        )
        await conn.execute(
            text(
                "INSERT INTO assets (id, project_id, take_id, kind, "
                "blob_hash) SELECT :id, :pid, :tid, 'output', blob_hash "
                "FROM assets WHERE id = :src"
            ),
            {"id": aid, "pid": pid, "tid": take_id, "src": assets[0]},
        )

    detail = (await client.get(f"/visual-anchors/{anchor['id']}")).json()
    assert detail["approved_revision_id"] is None

    await client.put(
        f"/visual-anchors/{anchor['id']}/items",
        json={"items": [{"asset_id": aid, "role": "primary"}]},
    )
    detail = (await client.get(f"/visual-anchors/{anchor['id']}")).json()
    assert detail["approved_revision_id"] is None  # working ≠ authority

    r = await client.post(f"/visual-anchors/{anchor['id']}/revisions")
    rev_id = r.json()["id"]
    detail = (await client.get(f"/visual-anchors/{anchor['id']}")).json()
    assert detail["approved_revision_id"] is None  # captured ≠ authority

    r = await client.post(
        f"/visual-anchor-revisions/{rev_id}/approve",
        json={"expected_approved_revision_id": None},
    )
    assert r.status_code == 200
    detail = (await client.get(f"/visual-anchors/{anchor['id']}")).json()
    assert detail["approved_revision_id"] == rev_id  # NOW authority

    async with engine.connect() as conn:
        kind = (
            await conn.execute(
                text("SELECT kind FROM assets WHERE id = :a"), {"a": aid}
            )
        ).scalar()
    assert kind == "output"
