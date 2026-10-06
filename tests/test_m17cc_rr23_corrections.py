"""M17C-C RR23 correction (frozen register RR23-M17CC-01) — the
machine-readable input contract exactly describes the closed runtime
gate.

RR22 closed the runtime authority boundary but left the generated
validation/OpenAPI schema an unconstrained
``anyOf: [integer, string, null]`` — no ``minimum: 0``, no
``maximum``, no canonical-decimal pattern — so the public contract
advertised ``-1``, ``9223372036854775808``, ``"-1"``, ``"+1"``,
``"01"``, ``"1.0"``, ``"1e3"``, and arbitrary text as schema-valid
while the endpoint deterministically rejected them.

The correction: Pydantic's ``WithJsonSchema(mode="validation")``
attaches the bounded input contract to the RR22 admission alias —
``anyOf: [integer minimum 0 / maximum SQLITE_INT_MAX; string with
the ONE bounded canonical-decimal pattern; null]`` — where the
pattern is GENERATED from ``SQLITE_INT_MAX`` (never a hand-typed
regex, never a duplicated literal; a bare regex + maxLength would
admit "9999999999999999999", which this construction excludes).
The runtime law ``_exact_duration`` is untouched; the model's
post-validation value remains the integer authority.

The decisive battery asserts BOTH layers — the model schemas and
the ACTUAL FastAPI ``/openapi.json`` request bodies — and re-proves
the runtime plus every preserved fence.
"""

from __future__ import annotations

import json
import re

import pytest

_SQLITE_MAX = 9_223_372_036_854_775_807  # 2^63 - 1
_STRONG = 9_007_199_254_740_993          # 2^53 + 1
_SAFE_MAX = 9_007_199_254_740_991        # 2^53 - 1

_ACCEPTED_STRINGS = ("0", "1", str(_STRONG), str(_SQLITE_MAX))
_REJECTED_STRINGS = (
    "-1", "+1", "01", "1.0", "1e3", " 1", "1 ", "  ",
    "", "0x1", "1_000",
    "9223372036854775808",       # max + 1
    "9223372036854775809",
    "9223372036854775810",
    "9300000000000000000",
    "9999999999999999999",       # the maxLength-implementation trap
    "99999999999999999999",
    "10000000000000000000",
)


def _models():
    from soloring.api.schemas.shots import ShotCreate, ShotPatch
    return (ShotCreate, ShotPatch)


# ---------------------------------------------------------------------------
# Points 1-5: the model schemas carry the exact bounded contract
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model", _models())
def test_rr23_model_schema_bounded_contract(model):
    """(1) integer/string/null exposed; (2) the integer branch has
    EXACT minimum 0 and maximum SQLITE_INT_MAX; (3) the string
    branch's machine-readable pattern admits the four lawful forms;
    (4) it rejects every alias/whitespace/above-max form; (5) it
    rejects several 19-digit above-max values — a mere maxLength
    implementation cannot pass."""
    from soloring.api.schemas.shots import (
        CANONICAL_DURATION_INPUT_PATTERN,
    )

    props = model.model_json_schema()["properties"]["duration_ms"]
    branches = props.get("anyOf", [])
    types = sorted(b.get("type") for b in branches if b.get("type"))
    assert types == ["integer", "null", "string"], types

    int_branch = next(b for b in branches
                      if b.get("type") == "integer")
    assert int_branch["minimum"] == 0
    assert int_branch["maximum"] == _SQLITE_MAX

    str_branch = next(b for b in branches if b.get("type") == "string")
    pattern = str_branch.get("pattern")
    assert pattern, str_branch
    assert pattern == CANONICAL_DURATION_INPUT_PATTERN
    compiled = re.compile(pattern)
    for accepted in _ACCEPTED_STRINGS:
        assert compiled.fullmatch(accepted), accepted
    for rejected in _REJECTED_STRINGS:
        assert not compiled.fullmatch(rejected), rejected


def test_rr23_pattern_generated_from_the_storage_bound():
    """The bounded pattern is GENERATED from SQLITE_INT_MAX — one
    named owner, no duplicated literal — and its numeric boundary is
    exhaustively neighborhood-checked both ways so a construction
    typo cannot silently broaden the contract."""
    from soloring.api.schemas.shots import (
        CANONICAL_DURATION_INPUT_PATTERN,
    )

    compiled = re.compile(CANONICAL_DURATION_INPUT_PATTERN)
    # the immediate neighborhood of the maximum, both directions
    for offset in range(0, 50):
        assert compiled.fullmatch(str(_SQLITE_MAX - offset))
        assert not compiled.fullmatch(str(_SQLITE_MAX + 1 + offset))
    # magnitudes across the digit-length ladder
    for magnitude in (0, 1, 2, 9, 10, 99, 10**17, 10**18 - 1):
        assert compiled.fullmatch(str(magnitude))
    # every canonical same-length form strictly above the maximum
    # (a maxLength implementation admits all of these)
    for above in ("9223372036854775808", "9300000000000000000",
                  "9900000000000000000", "9999999999999999999"):
        assert not compiled.fullmatch(above), above


# ---------------------------------------------------------------------------
# Point 6: the ACTUAL FastAPI /openapi.json request bodies
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr23_openapi_request_bodies_carry_the_contract(client):
    """The real OpenAPI document — not merely model_json_schema() —
    exposes the bounded contract on BOTH the POST
    /projects/{project_id}/shots and PATCH /shots/{shot_id}
    request bodies (inline or through component $refs).

    COMPLETION (the twenty-eighth review's residual): this test
    originally pinned the document's integer maximum to the
    framework's rounded double (accepting the loss) — the exact
    weakness the review condemned. FastAPI's internal openapi
    Schema model declares ``maximum: float | None`` (CI installs
    0.142.2; the mechanism, not any pin, is what matters), so the
    DEFAULT generator coerces the bound to the nearest IEEE double
    — float(SQLITE_INT_MAX) == 9.223372036854776e+18, rounding the
    INCLUSIVE maximum UP past the runtime boundary. The completion
    (``_install_exact_duration_openapi_maximum`` in
    soloring.api.main) corrects the published integer branch to the
    exact Python integer after generation, so this test now asserts
    the FROZEN decisive contract: ``type(maximum) is int`` AND
    ``maximum == SQLITE_INT_MAX``. The full completion battery
    (tests/test_m17cc_rr23_completion.py) carries the drift,
    cache-stability, narrowness, and repeated-generation proofs."""
    from soloring.api.schemas.shots import (
        CANONICAL_DURATION_INPUT_PATTERN,
    )

    r = await client.get("/openapi.json")
    assert r.status_code == 200, r.text
    spec = r.json()
    components = spec.get("components", {}).get("schemas", {})

    def resolve(node, depth=0):
        while isinstance(node, dict) and "$ref" in node and depth < 10:
            name = node["$ref"].rsplit("/", 1)[-1]
            node = components.get(name, {})
            depth += 1
        return node

    targets = {}
    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            if method not in ("post", "patch"):
                continue
            if "shots" not in path:
                continue
            body = (op.get("requestBody") or {}) \
                .get("content", {}).get("application/json", {})
            schema = resolve(body.get("schema", {}))
            if "duration_ms" in json.dumps(schema):
                targets[f"{method.upper()} {path}"] = schema

    assert any(k.startswith("POST ") for k in targets), targets.keys()
    assert any(k.startswith("PATCH ") for k in targets), targets.keys()

    for name, schema in targets.items():
        # follow allOf / property nesting to the duration_ms node
        props = schema.get("properties", {})
        if not props and "allOf" in schema:
            for sub in schema["allOf"]:
                props.update(resolve(sub).get("properties", {}))
        node = resolve(props.get("duration_ms", {}))
        branches = node.get("anyOf", [])
        types = sorted(b.get("type") for b in branches
                       if b.get("type"))
        assert types == ["integer", "null", "string"], (name, types)
        int_branch = next(b for b in branches
                          if b.get("type") == "integer")
        assert int_branch.get("minimum") == 0, (name, int_branch)
        maximum = int_branch.get("maximum")
        assert type(maximum) is int, (name, repr(maximum))
        assert maximum == _SQLITE_MAX, (name, repr(maximum))
        str_branch = next(b for b in branches
                          if b.get("type") == "string")
        assert str_branch.get("pattern") == \
            CANONICAL_DURATION_INPUT_PATTERN, (name, str_branch)


# ---------------------------------------------------------------------------
# Point 7: runtime behavior remains unchanged
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr23_runtime_unchanged(client):
    """Canonical decimal strings and genuine integer tokens through
    2^63-1 remain exact and green; raw floats/exponents and all
    ambiguous forms remain 422; 2^63 remains refused (raw bytes —
    never json= float arguments)."""
    from sqlalchemy import text

    r = await client.post("/projects", json={"name": "rr23"})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]

    # the accepted forms
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

    # the refused forms (raw bytes)
    r = await client.post(
        f"/projects/{project_id}/shots", json={"subject": "s"})
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]
    for token in ("1.0", "1e3", "9007199254740993.0",
                  "9.007199254740993e15", '"01"', '" 1"',
                  "9223372036854775808", '"9223372036854775808"'):
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


# ---------------------------------------------------------------------------
# Point 8: the preserved fences
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr23_preserved_fences(client, factory, tmp_path):
    """RR22's raw-body adversaries, RR21's unsafe-integer browser
    round-trip, RR20/RR19/RR18, and the M16 event-coordinate
    overflow fences all remain unchanged."""
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

    # RR22: the raw-body adversaries (POST + PATCH legs)
    r = await client.post("/projects", json={"name": "rr23-fences"})
    assert r.status_code == 201, r.text
    project_id = r.json()["id"]
    r = await client.post(
        f"/projects/{project_id}/shots",
        json={"subject": "s", "duration_ms": 5000})
    assert r.status_code == 201, r.text
    shot_id = r.json()["id"]
    for token in ("1.0", "1e3", "9007199254740993.0",
                  "9.007199254740993e15"):
        body = '{"duration_ms": %s}' % token
        r = await client.request(
            "PATCH", f"/shots/{shot_id}", content=body.encode(),
            headers={"content-type": "application/json"})
        assert r.status_code == 422, (token, r.text)

    # RR21: the browser round-trip shape (the wire string PATCH)
    from sqlalchemy import text
    r = await client.patch(
        f"/shots/{shot_id}",
        json={"duration_ms": str(_STRONG)})
    assert r.status_code == 200, r.text
    wire = json.loads((await client.get(f"/shots/{shot_id}")).text)
    assert wire["duration_ms_dec"] == str(_STRONG)
    r = await client.patch(
        f"/shots/{shot_id}",
        json={"title": "renamed",
              "duration_ms": wire["duration_ms_dec"]})
    assert r.status_code == 200, r.text
    engine = client._transport.app.state.engine
    async with engine.connect() as conn:
        column = (await conn.execute(text(
            "SELECT duration_ms FROM shots WHERE id = :s"),
            {"s": shot_id})).scalar_one()
    assert column == _STRONG

    # RR20: the 2^63 refusal
    r = await client.patch(
        f"/shots/{shot_id}", json={"duration_ms": _SQLITE_MAX + 1})
    assert r.status_code == 422, r.text

    # RR19: the TEXT recovery adversary
    world = await _valid_proposal_review_world(client, factory)
    source_rev_id = world["revision"].id
    await _stamp_alembic(client)
    root = tmp_path / "rr23-rr19"
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
