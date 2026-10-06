"""M17C-C RR23 completion (the residual Low finding of RR23-M17CC-01,
commissioned as a completion — not RR24) — the EMITTED OpenAPI
document carries the EXACT signed-SQLite integer boundary.

The twenty-eighth review found the RR23 correction's own battery
accepting ``int_branch maximum == float(SQLITE_INT_MAX)`` — and
float(9223372036854775807) is the binary value ...808, so the
published INCLUSIVE maximum rounded UP past the runtime boundary:
the endpoint rejects 9223372036854775808 while its published
integer schema described that value as within its maximum. The
mechanism is FastAPI's internal openapi Schema model declaring
``maximum: float | None`` (verified on the CI-installed 0.142.2;
the mechanism, not any version pin, is what the correction depends
on).

The completion: a narrow post-generation OpenAPI correction —
``_install_exact_duration_openapi_maximum`` wraps the app's
``openapi`` callable, lets FastAPI generate normally, verifies the
expected Shot create/PATCH ``duration_ms`` structure (failing
LOUDLY — and clearing the cache so every attempt keeps failing —
on any drift), then replaces ONLY that integer branch's rounded
maximum with the exact Python integer from the ONE storage-domain
owner, caching the corrected document in ``app.openapi_schema``
per the normal FastAPI pattern. No unrelated maximum, response
schema, or request model is touched; the model schemas, the
bounded canonical-decimal pattern, and the runtime admission law
are frozen unchanged.

The decisive assertion (frozen by the commission, never weakened):
for the integer branch used by BOTH POST /projects/{project_id}/shots
and PATCH /shots/{shot_id} in the REAL HTTP /openapi.json —
``type(maximum) is int`` AND ``maximum == 9223372036854775807``.
"""

from __future__ import annotations

import json
import re

import pytest

_SQLITE_MAX = 9_223_372_036_854_775_807  # 2^63 - 1
_STRONG = 9_007_199_254_740_993          # 2^53 + 1
_ROUNDED = float(_SQLITE_MAX)            # binary ...808 (== 2^63)


def _models():
    from soloring.api.schemas.shots import ShotCreate, ShotPatch
    return (ShotCreate, ShotPatch)


# ---------------------------------------------------------------------------
# Points 1-2: the model schemas remain unchanged and exact
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model", _models())
def test_rr23c_model_schemas_unchanged(model):
    """The Pydantic-side contract is untouched by the document-level
    correction: integer/string/null, EXACT int-typed minimum 0 and
    maximum SQLITE_INT_MAX, and the string branch still carrying
    the ONE bounded canonical-decimal pattern."""
    from soloring.api.schemas.shots import (
        CANONICAL_DURATION_INPUT_PATTERN,
    )

    props = model.model_json_schema()["properties"]["duration_ms"]
    branches = props.get("anyOf", [])
    types = sorted(b.get("type") for b in branches if b.get("type"))
    assert types == ["integer", "null", "string"], types
    int_branch = next(b for b in branches
                      if b.get("type") == "integer")
    assert type(int_branch["minimum"]) is int
    assert int_branch["minimum"] == 0
    assert type(int_branch["maximum"]) is int
    assert int_branch["maximum"] == _SQLITE_MAX
    str_branch = next(b for b in branches if b.get("type") == "string")
    assert str_branch["pattern"] == CANONICAL_DURATION_INPUT_PATTERN


# ---------------------------------------------------------------------------
# Points 3-7: the ACTUAL published /openapi.json
# ---------------------------------------------------------------------------

def _duration_branches(spec):
    """The $ref-resolved duration_ms schema nodes used by the POST
    and PATCH Shot routes (following inline or component refs)."""
    components = spec.get("components", {}).get("schemas", {})

    def resolve(node, depth=0):
        while isinstance(node, dict) and "$ref" in node and depth < 10:
            node = components.get(
                node["$ref"].rsplit("/", 1)[-1], {})
            depth += 1
        return node

    found = {}
    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            if method not in ("post", "patch") or "shots" not in path:
                continue
            body = (op.get("requestBody") or {}) \
                .get("content", {}).get("application/json", {})
            schema = resolve(body.get("schema", {}))
            if "duration_ms" not in json.dumps(schema):
                continue
            props = schema.get("properties", {})
            if not props and "allOf" in schema:
                for sub in schema["allOf"]:
                    props.update(resolve(sub).get("properties", {}))
            node = resolve(props.get("duration_ms", {}))
            if node:
                found[f"{method.upper()} {path}"] = node
    return found


@pytest.mark.asyncio
async def test_rr23c_published_openapi_exact_maximum(client):
    """Points 3-5: the REAL HTTP /openapi.json, $ref-resolved,
    exposes the same three branches on BOTH routes, with integer
    branches carrying ``type(maximum) is int`` AND the EXACT storage
    bound (never the rounded float, never scientific notation), and
    the boundary bracket proving the published maximum admits
    SQLITE_INT_MAX while refusing SQLITE_INT_MAX + 1 — this fails
    if the maximum ever becomes the rounded 2^63 float again."""
    from soloring.api.schemas.shots import (
        CANONICAL_DURATION_INPUT_PATTERN,
    )

    r = await client.get("/openapi.json")
    assert r.status_code == 200, r.text
    found = _duration_branches(r.json())

    assert any(k.startswith("POST ") for k in found), found.keys()
    assert any(k.startswith("PATCH ") for k in found), found.keys()
    assert len(found) == 2, found.keys()

    for name, node in found.items():
        branches = node.get("anyOf", [])
        types = sorted(b.get("type") for b in branches
                       if b.get("type"))
        assert types == ["integer", "null", "string"], (name, types)
        int_branch = next(b for b in branches
                          if b.get("type") == "integer")
        maximum = int_branch.get("maximum")
        assert type(maximum) is int, (name, repr(maximum))
        assert maximum == _SQLITE_MAX, (name, repr(maximum))
        # the commission freezes type-exactness for the MAXIMUM
        # only; the published minimum is the framework's lossless
        # 0.0 float (numerically exactly 0 — nothing to round)
        assert int_branch.get("minimum") == 0, (name, int_branch)
        # the boundary bracket on the PUBLISHED maximum itself
        assert _SQLITE_MAX <= maximum < _SQLITE_MAX + 1, name
        # point 6: the string branch is value-identical
        str_branch = next(b for b in branches
                          if b.get("type") == "string")
        assert str_branch.get("pattern") == \
            CANONICAL_DURATION_INPUT_PATTERN, (name, str_branch)


@pytest.mark.asyncio
async def test_rr23c_published_string_boundary_bracket(client):
    """Point 6 (behavioral): the PUBLISHED string pattern admits the
    exact storage maximum and refuses above it."""
    from soloring.api.schemas.shots import (
        CANONICAL_DURATION_INPUT_PATTERN,
    )

    r = await client.get("/openapi.json")
    assert r.status_code == 200, r.text
    found = _duration_branches(r.json())
    assert len(found) == 2
    for name, node in found.items():
        str_branch = next(b for b in node["anyOf"]
                          if b.get("type") == "string")
        compiled = re.compile(str_branch["pattern"])
        assert compiled.fullmatch(str(_SQLITE_MAX)), name
        assert not compiled.fullmatch(str(_SQLITE_MAX + 1)), name
        assert str_branch["pattern"] == CANONICAL_DURATION_INPUT_PATTERN


@pytest.mark.asyncio
async def test_rr23c_openapi_cached_and_stable(client):
    """Point 7: repeated /openapi.json requests return the exact
    cached document — the correction neither degrades nor
    double-transforms on subsequent generations."""
    app = client._transport.app
    for _ in range(3):
        r = await client.get("/openapi.json")
        assert r.status_code == 200, r.text
        found = _duration_branches(r.json())
        assert len(found) == 2
        for name, node in found.items():
            int_branch = next(b for b in node["anyOf"]
                              if b.get("type") == "integer")
            assert type(int_branch["maximum"]) is int, name
            assert int_branch["maximum"] == _SQLITE_MAX, name
    # the FastAPI-standard cache holds the corrected document
    assert app.openapi_schema is not None
    cached = _duration_branches(app.openapi_schema)
    assert len(cached) == 2
    for name, node in cached.items():
        int_branch = next(b for b in node["anyOf"]
                          if b.get("type") == "integer")
        assert type(int_branch["maximum"]) is int, name
        assert int_branch["maximum"] == _SQLITE_MAX, name


def _walk_maxima(node):
    if isinstance(node, dict):
        if isinstance(node.get("maximum"), (int, float)) \
                and not isinstance(node.get("maximum"), bool):
            yield node["maximum"]
        for value in node.values():
            yield from _walk_maxima(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_maxima(value)


@pytest.mark.asyncio
async def test_rr23c_correction_is_narrow(client):
    """The structural narrowness proof: an unrelated integer maximum
    elsewhere in the published document — the pre-existing
    m17c-performance/binding schemas carry FastAPI-float maxima from
    their own constrained-int declarations — is NOT rewritten by the
    Shot-duration hook (a general rewrite would have converted every
    such float to its exact int)."""
    r = await client.get("/openapi.json")
    assert r.status_code == 200, r.text
    components = r.json().get("components", {}).get("schemas", {})
    assert "ShotCreate" in components and "ShotPatch" in components

    untouched = [
        (name, maximum)
        for name, schema in components.items()
        if name not in ("ShotCreate", "ShotPatch")
        for maximum in _walk_maxima(schema)
        if maximum == _ROUNDED
    ]
    assert untouched, (
        "expected the pre-existing unrelated float maxima (the "
        "m17c-performance/binding constrained ints) to remain in "
        "their float form — a general maximum rewrite would have "
        "converted them")
    for name, maximum in untouched:
        assert type(maximum) is float, (name, repr(maximum))

    # and the two Shot components themselves ARE exact
    for name in ("ShotCreate", "ShotPatch"):
        node = components[name]["properties"]["duration_ms"]
        int_branch = next(b for b in node["anyOf"]
                          if b.get("type") == "integer")
        assert type(int_branch["maximum"]) is int, name
        assert int_branch["maximum"] == _SQLITE_MAX, name


# ---------------------------------------------------------------------------
# The fail-loudly drift contract
# ---------------------------------------------------------------------------

def _intercept_generation(monkeypatch, mutate_document):
    """Intercept FastAPI's schema generation and mutate the emitted
    document BEFORE the post-generation correction runs — proving
    the drift verification refuses to publish."""
    import fastapi.applications

    real = fastapi.applications.get_openapi

    def drifted(*args, **kwargs):
        document = real(*args, **kwargs)
        mutate_document(document)
        return document

    monkeypatch.setattr(fastapi.applications, "get_openapi", drifted)


def _shotcreate_duration(document):
    return document["components"]["schemas"]["ShotCreate"] \
        ["properties"]["duration_ms"]


@pytest.mark.asyncio
async def test_rr23c_drift_wrong_maximum_refused(client, monkeypatch):
    """A pre-correction maximum that is not the known rounded
    representation of the storage bound (and not already exact)
    fails schema generation clearly — on EVERY attempt, not just
    the first (the refused document is never left cached)."""

    def mutate(document):
        int_branch = next(b for b in _shotcreate_duration(document)
                          ["anyOf"] if b.get("type") == "integer")
        int_branch["maximum"] = 1234.5

    _intercept_generation(monkeypatch, mutate)
    app = client._transport.app
    for _ in range(2):
        with pytest.raises(RuntimeError, match="drift"):
            app.openapi()
    assert app.openapi_schema is None


@pytest.mark.asyncio
async def test_rr23c_drift_pattern_and_minimum_refused(
        client, monkeypatch):
    """The drift family also covers the string pattern and the
    integer minimum: any change to the verified structure refuses
    publication rather than quietly publishing an unverified
    contract."""
    app = client._transport.app

    def mutate_pattern(document):
        str_branch = next(b for b in _shotcreate_duration(document)
                          ["anyOf"] if b.get("type") == "string")
        str_branch["pattern"] = "WRONG"

    _intercept_generation(monkeypatch, mutate_pattern)
    with pytest.raises(RuntimeError, match="drift"):
        app.openapi()
    assert app.openapi_schema is None
    # undo before the second variant, or the second interception
    # would capture (and chain) the first drift wrapper as "real"
    monkeypatch.undo()

    def mutate_minimum(document):
        int_branch = next(b for b in _shotcreate_duration(document)
                          ["anyOf"] if b.get("type") == "integer")
        int_branch["minimum"] = 7

    _intercept_generation(monkeypatch, mutate_minimum)
    with pytest.raises(RuntimeError, match="drift"):
        app.openapi()
    assert app.openapi_schema is None


# ---------------------------------------------------------------------------
# Point 8: runtime remains untouched + the fences
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr23c_runtime_and_fences_unchanged(client, factory,
                                                  tmp_path):
    """Point 8: the runtime admission law is untouched — exact
    integer and canonical string through 2^63-1 green (raw bytes);
    2^63, raw floats/exponents, and ambiguous strings refused; the
    RR22/RR21/RR20/RR19/RR18 and event-coordinate fences
    unchanged."""
    from sqlalchemy import text

    r = await client.post("/projects", json={"name": "rr23c"})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]

    # the accepted forms (raw bytes)
    for token, expected in (('"%d"' % _STRONG, _STRONG),
                            ('"%d"' % _SQLITE_MAX, _SQLITE_MAX),
                            ('%d' % _STRONG, _STRONG),
                            ('%d' % _SQLITE_MAX, _SQLITE_MAX)):
        body = '{"subject": "s", "duration_ms": %s}' % token
        r = await client.request(
            "POST", f"/projects/{project_id}/shots",
            content=body.encode("utf-8"),
            headers={"content-type": "application/json"})
        assert r.status_code == 201, (token, r.text)
        assert r.json()["duration_ms_dec"] == str(expected)

    # the refused forms (raw bytes) — floats, exponents, 2^63,
    # ambiguous strings
    r = await client.post(
        f"/projects/{project_id}/shots", json={"subject": "s"})
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]
    for token in ("1.0", "1e3", "9007199254740993.0",
                  "9.007199254740993e15", "9223372036854775808",
                  '"9223372036854775808"', '"01"', '" 1"'):
        r = await client.request(
            "PATCH", f"/shots/{shot_id}",
            content=('{"duration_ms": %s}' % token).encode("utf-8"),
            headers={"content-type": "application/json"})
        assert r.status_code == 422, (token, r.text)
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        column = (await conn.execute(text(
            "SELECT duration_ms FROM shots WHERE id = :s"),
            {"s": shot_id})).scalar_one()
    assert column is None

    # RR20: the 2^63 refusal through the json= integer form too
    r = await client.patch(
        f"/shots/{shot_id}", json={"duration_ms": _SQLITE_MAX + 1})
    assert r.status_code == 422, r.text

    # RR21: the browser round-trip shape (the wire string PATCH)
    r = await client.patch(
        f"/shots/{shot_id}", json={"duration_ms": str(_STRONG)})
    assert r.status_code == 200, r.text
    wire = json.loads((await client.get(f"/shots/{shot_id}")).text)
    assert wire["duration_ms_dec"] == str(_STRONG)
    r = await client.patch(
        f"/shots/{shot_id}",
        json={"title": "renamed",
              "duration_ms": wire["duration_ms_dec"]})
    assert r.status_code == 200, r.text
    async with engine.connect() as conn:
        column = (await conn.execute(text(
            "SELECT duration_ms FROM shots WHERE id = :s"),
            {"s": shot_id})).scalar_one()
    assert column == _STRONG

    # RR19: the TEXT recovery adversary
    from soloring.domain.canonical import (
        canonical_hash as ch, canonical_json_str as cj,
    )
    from soloring.errors import SoloRingError
    from soloring.recovery.backup import RecoveryCorruption, backup \
        as rb_backup
    from soloring.recovery.m16_verifier import (
        verify_m16_intra_shot_state,
    )
    from tests.m16_seed_b import event, post_event, \
        seed_feature_world, state
    from tests.test_m16_recovery import _settings, _stamp_alembic
    from tests.test_m16_recovery_proposals import (
        _valid_proposal_review_world,
    )
    from tests.m17cc_capture_helper import capture as _capture
    import sqlite3

    world = await _valid_proposal_review_world(client, factory)
    source_rev_id = world["revision"].id
    await _stamp_alembic(client)
    root = tmp_path / "rr23c-rr19"
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
    from soloring.continuity.intra_shot_canonical import (
        SAFE_INT_MAX, require_plain_int,
    )
    base = await seed_feature_world(client, factory,
                                    duration=_STRONG)
    sid, fid = base["shot_id"], base["feature_id"]
    await post_event(
        client, sid, event(fid, 1, state(), state("fresh")))
    revision, _ = await _capture(client, sid)
    snap = json.loads(revision.snapshot_json)
    assert snap["intent"]["duration_ms"] == _STRONG
    with pytest.raises(SoloRingError):
        require_plain_int(SAFE_INT_MAX + 1, field="time_ms")
