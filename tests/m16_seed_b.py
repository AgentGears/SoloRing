"""M16-B shared seeding: entity-feature and entity-relation Shot worlds.

Each helper leaves one duration-bearing Shot with explicit semantic
dependencies and the M7 continuity facts the resolver folds over. All
creation goes through production HTTP paths.
"""

from __future__ import annotations

from soloring.api.schemas.projects import ProjectCreate
from soloring.api.schemas.shots import ShotCreate
from soloring.domain import projects as project_svc
from soloring.domain import shots as shot_svc
from soloring.domain.canonical import canonical_hash


async def _approved_entity(client, pid, *, kind="character", name="Eva"):
    e = await client.post(
        f"/projects/{pid}/entities", json={"kind": kind, "name": name})
    assert e.status_code == 201, e.text
    eid = e.json()["id"]
    r = await client.post(
        f"/entities/{eid}/revisions", json={"spec": {"description": "d"}})
    assert r.status_code == 201, r.text
    a = await client.put(
        f"/entities/{eid}/approved-revision",
        json={"revision_id": r.json()["id"],
              "expected_approved_revision_id": None})
    assert a.status_code == 200, a.text
    return eid


async def seed_ordered_pair(factory, pid, *, name="M16 pair"):
    """Two Shots in canonical narrative order (first, then second)."""
    from soloring.api.schemas.shots import ShotCreate as _SC
    from soloring.narrative import scenes as scene_svc
    from soloring.narrative import sequences as seq_svc

    async with factory() as s:
        seq = await seq_svc.create_sequence(s, pid, name)
        scene = await scene_svc.create_scene(s, seq, name, None)
        first = (await shot_svc.create_shot(
            s, pid, _SC(subject="a", duration_ms=4000))).id
        second = (await shot_svc.create_shot(
            s, pid, _SC(subject="b", duration_ms=4000))).id
        await scene_svc.assign_scene_shots(s, scene, [first, second])
    return first, second


async def assign_shot(factory, pid, sid, *, name="M16 scene"):
    """Put one Shot into canonical narrative order (scene boundary)."""
    from soloring.narrative import scenes as scene_svc
    from soloring.narrative import sequences as seq_svc

    async with factory() as s:
        seq = await seq_svc.create_sequence(s, pid, name)
        scene = await scene_svc.create_scene(s, seq, name, None)
        await scene_svc.assign_scene_shots(s, scene, [sid])
        return scene


async def seed_feature_world(client, factory, *, duration=5000,
                             extra_feature_keys=()):
    """One Shot + one dependent character + an enum injury feature."""
    async with factory() as s:
        pid = (await project_svc.create_project(
            s, ProjectCreate(name="M16-B feature"))).id
        sid = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="x", duration_ms=duration))).id
    await assign_shot(factory, pid, sid, name="M16-B feature scene")
    eid = await _approved_entity(client, pid, name="Eva")
    d = await client.put(
        f"/shots/{sid}/semantic-dependencies",
        json={"dependencies": [{"entity_id": eid, "role": "subject"}]})
    assert d.status_code == 200, d.text
    f = await client.post(
        f"/entities/{eid}/continuity-features",
        json={"key": "cut", "kind": "injury", "value_type": "enum",
              "name": "Cut", "enum_values": ["fresh", "healing", "scarred"]})
    assert f.status_code == 201, f.text
    out = {"project_id": pid, "shot_id": sid, "entity_id": eid,
           "feature_id": f.json()["id"]}
    for i, key in enumerate(extra_feature_keys):
        g = await client.post(
            f"/entities/{eid}/continuity-features",
            json={"key": key, "kind": "wardrobe_condition",
                  "value_type": "text", "name": key.title()})
        assert g.status_code == 201, g.text
        out[f"{key}_feature_id"] = g.json()["id"]
    return out


async def seed_relation_world(client, factory, *, duration=5000):
    """One Shot + two dependent characters + one directional relation."""
    async with factory() as s:
        pid = (await project_svc.create_project(
            s, ProjectCreate(name="M16-B relation"))).id
        sid = (await shot_svc.create_shot(
            s, pid, ShotCreate(subject="x", duration_ms=duration))).id
    await assign_shot(factory, pid, sid, name="M16-B relation scene")
    sub = await _approved_entity(client, pid, name="Eva")
    obj = await _approved_entity(client, pid, kind="prop", name="Rifle")
    d = await client.put(
        f"/shots/{sid}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": sub, "role": "subject"},
            {"entity_id": obj, "role": "object"}]})
    assert d.status_code == 200, d.text
    p = await client.post(
        f"/projects/{pid}/continuity-predicates",
        json={"key": "carries", "name": "Carries"})
    assert p.status_code == 201, p.text
    r = await client.post(
        f"/projects/{pid}/continuity-relations",
        json={"subject_entity_id": sub, "predicate_id": p.json()["id"],
              "object_entity_id": obj})
    assert r.status_code == 201, r.text
    return {"project_id": pid, "shot_id": sid, "subject_id": sub,
            "object_id": obj, "predicate_id": p.json()["id"],
            "relation_id": r.json()["id"]}


def state(value=None):
    if value is None:
        return {"present": False}
    return {"present": True, "value": value,
            "value_hash": canonical_hash(value)}


def event(target_id, t, before, after, *, kind="entity_feature",
          ordinal=0, persistence="transient"):
    return {
        "time_ms": t, "ordinal": ordinal,
        "target": {"kind": kind, "id": target_id},
        "before": before, "after": after,
        "persistence_mode": persistence,
    }


async def post_event(client, shot_id, body):
    r = await client.post(f"/shots/{shot_id}/intra-shot/events", json=body)
    assert r.status_code == 201, getattr(r, "text", "")
    return r.json()


async def get_intra(client, shot_id, **params):
    r = await client.get(f"/shots/{shot_id}/intra-shot", params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def put_transition(client, feature_id, shot_id, *, operation,
                         value=None):
    payload = {"anchor_type": "shot", "anchor_id": shot_id,
               "boundary": "end", "operation": operation}
    if value is not None:
        payload["value"] = value
    r = await client.post(
        f"/continuity-features/{feature_id}/transitions", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def put_relation_transition(client, relation_id, shot_id, *, st):
    r = await client.post(
        f"/continuity-relations/{relation_id}/transitions",
        json={"anchor_type": "shot", "anchor_id": shot_id,
              "boundary": "end", "state": st})
    assert r.status_code == 201, r.text
    return r.json()
