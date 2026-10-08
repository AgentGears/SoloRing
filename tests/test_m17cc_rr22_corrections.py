"""M17C-C RR22 correction (frozen register RR22-M17CC-01) — the
CLOSED public request grammar for Shot duration.

RR21's admission contract was not mechanically closed: the
validator's catch-all ``return value`` let raw JSON floats and
exponent numbers fall through Pydantic's NON-STRICT ``int``
coercion — ``1.0`` became 1, ``1e3`` became 1000, and
``9007199254740993.0`` (which the JSON decoder itself produces as
``…992.0``) could be PERSISTED as ``…992``: the precision-loss
authority mutation recreated at the public request boundary.

The correction: the admission primitive is now a CLOSED type gate —
it returns ONLY the accepted branches (None; ``type(value) is
exactly int``; a canonical decimal string converted to the exact
int) and raises on EVERY other representation (bool, float,
Decimal-like wrappers, containers, and every ambiguous string
form), enforcing the [0, SQLITE_INT_MAX] storage bound inside the
gate; NOTHING reaches Pydantic's ordinary coercion. The FIELD TYPE
is now ``int | str | None`` so the generated validation/OpenAPI
schema tells the truth about the accepted input union. The frontend
helper enforces the same canonical lexical rule WITHOUT trimming
(only the literal empty string is unset).

The decisive battery drives the REAL HTTP parser with explicit raw
JSON bytes (never ``json=`` float arguments, which could round
before the request body exists) and re-proves every preserved
fence.
"""

from __future__ import annotations

import json

import pytest

_SQLITE_MAX = 9_223_372_036_854_775_807  # 2^63 - 1
_STRONG = 9_007_199_254_740_993          # 2^53 + 1
_STRONG_ROUNDED = 9_007_199_254_740_992  # what IEEE-754 makes of it
_SAFE_MAX = 9_007_199_254_740_991        # 2^53 - 1


async def _duration_column(client, shot_id):
    from sqlalchemy import text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT duration_ms FROM shots WHERE id = :s"),
            {"s": shot_id})).scalar_one()


async def _shot_count(client, project_id):
    from sqlalchemy import text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT COUNT(*) FROM shots WHERE project_id = :p"),
            {"p": project_id})).scalar_one()


async def _raw(client, method, url, body: str):
    """Send an EXPLICIT raw JSON body through the real HTTP parser —
    never a ``json=`` kwarg (the client runtime could transform a
    float before the request body exists)."""
    return await client.request(
        method, url, content=body.encode("utf-8"),
        headers={"content-type": "application/json"})


async def _project(client, name="rr22"):
    r = await client.post("/projects", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Model-level pins (the Pydantic coercion boundary, independent of FastAPI)
# ---------------------------------------------------------------------------

def test_rr22_model_level_closed_gate():
    """The exact shapes the review named: model_validate accepts the
    exact int / canonical string / None and refuses every coercible
    representation — 1.0, the unsafe rounded float, bool, aliases,
    containers, and the above-storage forms."""
    import pydantic

    from soloring.api.schemas.shots import ShotCreate, ShotPatch

    for model, base in ((ShotCreate, {"subject": "s"}),
                         (ShotPatch, {})):
        assert model.model_validate(
            {**base, "duration_ms": None}).duration_ms is None
        assert model.model_validate(
            {**base, "duration_ms": 1}).duration_ms == 1
        assert model.model_validate(
            {**base, "duration_ms": _STRONG}).duration_ms == _STRONG
        assert model.model_validate(
            {**base, "duration_ms": str(_STRONG)}).duration_ms \
            == _STRONG
        assert model.model_validate(
            {**base, "duration_ms": str(_SQLITE_MAX)}).duration_ms \
            == _SQLITE_MAX
        for bad in (1.0, 1000.0, float(_STRONG_ROUNDED),
                    9.007199254740993e15, float(_SQLITE_MAX),
                    True, False, "+1", "-1", "1.0", " 1", "1 ",
                    "01", "1e3", "", [1], {"a": 1},
                    _SQLITE_MAX + 1, str(_SQLITE_MAX + 1), -1):
            with pytest.raises(pydantic.ValidationError):
                model.model_validate({**base, "duration_ms": bad})


def test_rr22_generated_schema_truth():
    """Both create and patch schemas visibly describe the
    integer + string + null input union (point 8a)."""
    from soloring.api.schemas.shots import ShotCreate, ShotPatch

    for schema in (ShotCreate.model_json_schema(),
                   ShotPatch.model_json_schema()):
        props = schema["properties"]["duration_ms"]
        types = sorted(
            branch.get("type") for branch in props.get("anyOf", [])
            if branch.get("type"))
        assert types == ["integer", "null", "string"], \
            (schema.get("title"), types)


# ---------------------------------------------------------------------------
# Points 1-6: the raw-body HTTP boundaries
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("raw_token", [
    "1.0", "1e3",
    "9007199254740993.0", "9.007199254740993e15",
])
@pytest.mark.parametrize("method", ["post", "patch"])
async def test_rr22_raw_float_tokens_refused(client, raw_token, method):
    """Points 1-4: raw JSON NUMERIC tokens (decimal and exponent
    forms, incl. the two unsafe shapes the JSON decoder itself
    rounds) refuse 422 on BOTH POST and PATCH — the POST creates
    ZERO Shot rows and the PATCH leaves the prior durable duration
    EXACTLY unchanged, so no hidden rounded write can pass
    unnoticed."""
    project_id = await _project(client)
    r = await client.post(
        f"/projects/{project_id}/shots", json={"subject": "s",
                                                "duration_ms": 5000})
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]
    before = await _shot_count(client, project_id)

    if method == "post":
        post_body = '{"subject": "s", "duration_ms": %s}' % raw_token
        r = await _raw(client, "POST",
                       f"/projects/{project_id}/shots", post_body)
        assert r.status_code == 422, (raw_token, r.text)
        assert await _shot_count(client, project_id) == before
    else:
        body = '{"duration_ms": %s}' % raw_token
        r = await _raw(client, "PATCH", f"/shots/{shot_id}", body)
        assert r.status_code == 422, (raw_token, r.text)
        assert await _duration_column(client, shot_id) == 5000


@pytest.mark.asyncio
async def test_rr22_canonical_and_integer_tokens_green(client):
    """Point 5: the canonical strings AND the genuine JSON integer
    token remain exact and green through the raw parser."""
    project_id = await _project(client, "rr22-green")
    for token, expected in (('"%d"' % _STRONG, _STRONG),
                            ('"%d"' % _SQLITE_MAX, _SQLITE_MAX),
                            ('%d' % _STRONG, _STRONG)):
        body = '{"subject": "s", "duration_ms": %s}' % token
        r = await _raw(client, "POST",
                       f"/projects/{project_id}/shots", body)
        assert r.status_code == 201, (token, r.text)
        shot_id = r.json()["id"]
        assert await _duration_column(client, shot_id) == expected
        assert r.json()["duration_ms_dec"] == str(expected)


@pytest.mark.asyncio
async def test_rr22_above_storage_refused_every_representation(client):
    """Point 6: 2^63 refused whether supplied as a genuine integer
    token or a canonical decimal string (raw bodies)."""
    project_id = await _project(client, "rr22-max")
    r = await client.post(
        f"/projects/{project_id}/shots", json={"subject": "s"})
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]
    for token in (str(_SQLITE_MAX + 1), '"%d"' % (_SQLITE_MAX + 1)):
        r = await _raw(client, "PATCH", f"/shots/{shot_id}",
                       '{"duration_ms": %s}' % token)
        assert r.status_code == 422, (token, r.text)
    assert await _duration_column(client, shot_id) is None


# ---------------------------------------------------------------------------
# Point 7: the frontend lexical contract (no normalization)
# ---------------------------------------------------------------------------

def test_rr22_frontend_no_normalization():
    """The helper source carries the exact contract: no trim inside
    durationToTransport (a whitespace alias can never become valid),
    and only the literal empty string is unset. The behavioral
    cases run in the frontend battery (vitest); this guards the
    shipped source shape."""
    src = open("apps/web/src/lib/exactDuration.ts",
               encoding="utf-8").read()
    body = src.split("export function durationToTransport")[1] \
        .split("\n}")[0]
    assert ".trim()" not in body
    assert 'if (raw === "") return null;' in src


# ---------------------------------------------------------------------------
# Point 8: the preserved fences
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr22_preserved_fences(client, factory, tmp_path):
    """RR21's browser unrelated-save round trip at 2^53+1, RR20's
    2^63 refusal, RR19's TEXT recovery adversary, RR18's lawful
    large duration, and the event-coordinate overflow fences all
    remain green."""
    from soloring.continuity.intra_shot_canonical import (
        SAFE_INT_MAX, require_plain_int,
    )
    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )
    from soloring.errors import SoloRingError
    from soloring.recovery.backup import RecoveryCorruption, backup \
        as rb_backup
    from soloring.recovery.m16_verifier import (
        verify_m16_intra_shot_state,
    )
    from tests.m16_seed_b import event, post_event, seed_feature_world, \
        state
    from tests.test_m16_recovery import _settings, _stamp_alembic
    from tests.test_m16_recovery_proposals import (
        _valid_proposal_review_world,
    )
    from tests.m17cc_capture_helper import capture as _capture
    import sqlite3

    # RR21: the browser round-trip shape — the wire string PATCH
    project_id = await _project(client, "rr22-rr21")
    r = await client.post(
        f"/projects/{project_id}/shots",
        json={"subject": "s", "duration_ms": str(_STRONG)})
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]
    wire = json.loads((await client.get(f"/shots/{shot_id}")).text)
    assert wire["duration_ms_dec"] == str(_STRONG)
    r = await client.patch(
        f"/shots/{shot_id}",
        json={"title": "renamed", "duration_ms": wire["duration_ms_dec"]})
    assert r.status_code == 200, r.text
    assert await _duration_column(client, shot_id) == _STRONG

    # RR20: the 2^63 authoring refusal (json= form — the raw form
    # proven above)
    r = await client.patch(
        f"/shots/{shot_id}", json={"duration_ms": _SQLITE_MAX + 1})
    assert r.status_code == 422, r.text

    # RR19: the TEXT recovery adversary
    world = await _valid_proposal_review_world(client, factory)
    source_rev_id = world["revision"].id
    await _stamp_alembic(client)
    root = tmp_path / "rr22-rr19"
    await rb_backup(await _settings(client), root)
    con = sqlite3.connect(root / "soloring.db")
    try:
        snap = json.loads(con.execute(
            "SELECT snapshot_json FROM shot_revisions WHERE id = ?",
            (source_rev_id,)).fetchone()[0])
        snap["intent"]["duration_ms"] = _SQLITE_MAX + 1
        new_hash = ch(snap)
        con.execute(
            "UPDATE shot_revisions SET snapshot_json = ?, "
            "snapshot_hash = ? WHERE id = ?",
            (cj(snap), new_hash, source_rev_id))
        con.execute(
            "UPDATE shot_intra_shot_event_proposals SET "
            "source_shot_revision_hash = ? WHERE "
            "source_shot_revision_id = ?",
            (new_hash, source_rev_id))
        con.commit()
    finally:
        con.close()
    with pytest.raises(RecoveryCorruption):
        verify_m16_intra_shot_state(root / "soloring.db")

    # RR18: the lawful 2^53+1-band capture + the event ceiling
    base = await seed_feature_world(client, factory, duration=_STRONG)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["intent"]["duration_ms"] == _STRONG
    with pytest.raises(SoloRingError):
        require_plain_int(SAFE_INT_MAX + 1, field="time_ms")
