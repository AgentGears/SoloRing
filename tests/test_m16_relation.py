"""M16:RELATION — relation fold identity/endpoints (frozen §22).

B-eligible cells only: cells 04/05 (adopted downstream persistence,
historical soft-delete isolation) are owned by M16-C/M16-D.
"""

from __future__ import annotations

from tests.m16_seed_b import (
    event,
    get_intra,
    seed_relation_world,
)


def _rel(active: bool):
    return {"active": active}


async def test_relation_01(client, factory):
    """Relation events use the exact relation identity and endpoints."""
    base = await seed_relation_world(client, factory)
    sid, rid = base["shot_id"], base["relation_id"]
    r = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(rid, 1000, _rel(False), _rel(True),
                   kind="entity_relation"))
    assert r.status_code == 201, r.text
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    assert proj["events"][0]["target"] == {
        "kind": "entity_relation", "id": rid}
    assert proj["terminal_targets"][0]["terminal_state"] == _rel(True)


async def test_relation_02(client, factory):
    """Both directional endpoints must be Shot dependencies."""
    base = await seed_relation_world(client, factory)
    sid = base["shot_id"]
    # re-wire dependencies to the subject only, dropping the object
    d = await client.put(
        f"/shots/{sid}/semantic-dependencies",
        json={"dependencies": [
            {"entity_id": base["subject_id"], "role": "subject"}]})
    assert d.status_code == 200, d.text
    rejected = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(base["relation_id"], 1000, _rel(False), _rel(True),
                   kind="entity_relation"))
    assert rejected.status_code == 409, rejected.text
    assert "INTRA_SHOT_TARGET_INVALID" in rejected.text


async def test_relation_03(client, factory):
    """Activation/deactivation folds deterministically."""
    base = await seed_relation_world(client, factory)
    sid, rid = base["shot_id"], base["relation_id"]
    first = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(rid, 1000, _rel(False), _rel(True),
                   kind="entity_relation"))
    assert first.status_code == 201, first.text
    second = await client.post(
        f"/shots/{sid}/intra-shot/events",
        json=event(rid, 2000, _rel(True), _rel(False),
                   kind="entity_relation"))
    assert second.status_code == 201, second.text
    proj = await get_intra(client, sid)
    assert proj["intra_shot_ready"] is True, proj["intra_shot_issues"]
    assert proj["terminal_targets"][0]["terminal_state"] == _rel(False)
    assert [(e["time_ms"], e["ordinal"]) for e in proj["events"]] == [
        (1000, 0), (2000, 0)]


async def test_relation_05_soft_delete_does_not_alter_history(client, factory):
    """RELATION:05 — later soft-delete/edit of the current relation
    never changes the captured historical meaning."""
    import json as _json

    from sqlalchemy import text as _text

    from tests.test_m16_capture import _capture, _snap_json

    base = await seed_relation_world(client, factory)
    sid, rid = base["shot_id"], base["relation_id"]
    from tests.m16_seed_b import post_event

    await post_event(
        client, sid,
        event(rid, 1000, _rel(False), _rel(True), kind="entity_relation"))
    revision, _ = await _capture(client, sid)
    engine = client._transport.app.state.engine
    before = _json.loads(await _snap_json(engine, revision.id))

    async with engine.begin() as conn:
        await conn.execute(_text(
            "UPDATE continuity_relations SET deleted_at = "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :r"),
            {"r": rid})
    after = _json.loads(await _snap_json(engine, revision.id))
    assert before == after
    identity = after["intra_shot"]["events"][0]["target_identity"]
    assert identity["relation_id"] == rid
    assert identity["predicate_key"] == "carries"
    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
