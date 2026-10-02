"""M17C-C RR8 correction (frozen register RR8-M17CC-01..02).

RR8-01 — the shared binding structural law communicates TYPED
  failure categories (BindingStructuralError.category — the routing
  contract, never human-readable text), and PF-03's adapter maps the
  categories back to the EXACT predecessor messages verified against
  132d2b3 — no prefixes, suffixes, parentheticals, or merged
  categories. §12 keeps the richer structural reason inside its own
  internal_invariant. The structural law stays singular (no duplicate
  grammar; no weakening).

RR8-02 — the retained CAPTURED-HASH law is proven AFTER
  self-authentication succeeds: a coherent post-capture binding
  rewrite (the scalar mutated AND canonical binding_json/binding_hash
  recomputed — authentication passes; the captured child/snapshot's
  vocal_binding_hash untouched) must reach and fail specifically at
  the captured-binding-hash disagreement, distinguishing that branch
  from self-authentication failure. The RR7 positive battery's
  vacuous hash assertion is repaired to a real expected-hash
  equality against the lawful immutable binding document.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from soloring.domain.canonical import (
    canonical_hash as _ch, canonical_json_str as _cj,
)
from tests.m17cc_capture_helper import capture as _capture
from tests.test_m17cc_persist import _lawful
from tests.test_m17c_shot_mapping import _bound_world, _seg_body

_CHILDREN = "shot_revision_performance_segments"


def _engine(client):
    return client._transport.app.state.engine


async def _sql(client, stmt, params=None):
    from sqlalchemy import text
    async with _engine(client).begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _row(client, stmt, params=None):
    from sqlalchemy import text
    async with _engine(client).connect() as conn:
        return dict((await conn.execute(
            text(stmt), params or {})).mappings().one())


async def _stage_lawful(client):
    world = await _bound_world(client)
    await _lawful(client, world, extra=True)
    revision, _visual = await _capture(client, world["shot"])
    return world, revision


class _BindingRow:
    """A duck-typed persisted binding row for the PF-03 seam."""

    def __init__(self, **kw):
        self.binding_schema_version = kw.get(
            "binding_schema_version", 1)
        self.synchronization_basis_version = kw.get(
            "synchronization_basis_version", 1)
        self.vocal_performance_revision_id = kw[
            "vocal_performance_revision_id"]
        self.source_start_sample = kw.get("source_start_sample", 48000)
        self.source_end_sample_exclusive = kw.get(
            "source_end_sample_exclusive", 96000)
        self.sample_rate_hz = kw.get("sample_rate_hz", 48000)
        self.performance_origin_num = kw.get(
            "performance_origin_num", 0)
        self.performance_origin_den = kw.get(
            "performance_origin_den", 1)
        self.binding_json = kw["binding_json"]
        self.binding_hash = kw["binding_hash"]


def _lawful_binding_doc(**overrides):
    doc = {
        "binding_schema_version": 1,
        "synchronization_basis_version": 1,
        "vocal_performance_revision_id":
            "00000000-0000-4000-8000-0000000000aa",
        "source_start_sample": 48000,
        "source_end_sample_exclusive": 96000,
        "sample_rate_hz": 48000,
        "performance_origin_ms": {"num": 0, "den": 1},
    }
    doc.update(overrides)
    return doc


# ---------------------------------------------------------------------------
# RR8-01: the exact predecessor vocabulary, pinned branch by branch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("branch,expected_message", [
    ("schema_basis",
     "M17C vocal binding schema/basis version is not 1"),
    ("rational_malformed",
     "M17C vocal binding stores an invalid persisted rational: "
     "INVALID_RATIONAL: denominator must be positive"),
    ("rational_noncanonical",
     "M17C vocal binding stores a noncanonical rational"),
    ("binding_json_divergence",
     "M17C vocal binding canonical bytes/hash diverge"),
    ("binding_hash_divergence",
     "M17C vocal binding canonical bytes/hash diverge"),
])
def test_rr8_pf03_predecessor_messages_pinned(branch, expected_message):
    """Each structural branch surfaces PF-03's EXACT predecessor
    message (verified verbatim against 132d2b3) — no prefix, suffix,
    or parenthetical — with the typed category as the only routing
    input."""
    from soloring.errors import SoloRingError
    from soloring.performance.m17c_binding import _verify_binding_bytes

    vid = "00000000-0000-4000-8000-0000000000aa"
    if branch == "schema_basis":
        doc = _lawful_binding_doc(binding_schema_version=2)
    elif branch == "rational_malformed":
        doc = _lawful_binding_doc()
    elif branch == "rational_noncanonical":
        doc = _lawful_binding_doc()
    else:
        doc = _lawful_binding_doc()
    row = _BindingRow(
        vocal_performance_revision_id=vid,
        binding_schema_version=doc["binding_schema_version"],
        source_start_sample=doc["source_start_sample"],
        source_end_sample_exclusive=(
            doc["source_end_sample_exclusive"]),
        sample_rate_hz=doc["sample_rate_hz"],
        performance_origin_num=doc["performance_origin_ms"]["num"],
        performance_origin_den=doc["performance_origin_ms"]["den"],
        binding_json=_cj(doc),
        binding_hash=_ch(doc))

    if branch == "schema_basis":
        pass  # already divergent
    elif branch == "rational_malformed":
        row.performance_origin_den = 0
    elif branch == "rational_noncanonical":
        row.performance_origin_num = 2
        row.performance_origin_den = 2
        doc["performance_origin_ms"] = {"num": 2, "den": 2}
        row.binding_json = _cj(doc)
        row.binding_hash = _ch(doc)
    elif branch == "binding_json_divergence":
        row.binding_json = '{"forged": true}'
    elif branch == "binding_hash_divergence":
        row.binding_hash = "e" * 64

    with pytest.raises(SoloRingError) as excinfo:
        _verify_binding_bytes(row)
    assert excinfo.value.status_code == 500
    # the EXACT predecessor message — equality, not fragment
    assert excinfo.value.message == expected_message, \
        excinfo.value.message


def test_rr8_typed_reason_reaches_section12():
    """§12 keeps the RICHER structural reason (the typed error's
    reason), distinct from PF-03's legacy surface."""
    from soloring.performance.m17c_binding import (
        BindingStructuralError, verify_stored_vocal_binding,
    )

    doc = _lawful_binding_doc()
    with pytest.raises(BindingStructuralError) as excinfo:
        verify_stored_vocal_binding(
            binding_schema_version=1, synchronization_basis_version=1,
            vocal_performance_revision_id=doc[
                "vocal_performance_revision_id"],
            source_start_sample=48000,
            source_end_sample_exclusive=96000,
            sample_rate_hz=48000,
            performance_origin_num=2, performance_origin_den=2,
            binding_json=_cj(doc), binding_hash=_ch(doc))
    assert excinfo.value.category == \
        BindingStructuralError.CATEGORY_RATIONAL_NONCANONICAL
    assert "not in canonical reduced form" in excinfo.value.reason


# ---------------------------------------------------------------------------
# RR8-02: the retained captured-hash law, reached after
# self-authentication succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rr8_coherently_resigned_binding_fails_captured_hash(
        client):
    """The decisive layer-separation proof: after a lawful capture,
    coherently mutate the immutable binding scalar (source_end) AND
    recompute its canonical binding_json/binding_hash — the row
    SELF-AUTHENTICATES (both layers of the shared law pass) — while
    the captured child/snapshot vocal_binding_hash stays untouched.
    §12 must then reach and fail specifically at the CAPTURED-BINDING-
    HASH disagreement law (a different message from the
    self-authentication failure)."""
    world, revision = await _stage_lawful(client)

    # the coherent re-sign: scalar + canonical bytes + canonical hash
    con = sqlite3.connect(
        client._transport.app.state.settings.data_dir / "soloring.db")
    row = con.execute(
        "SELECT * FROM performance_revision_vocal_bindings WHERE "
        "performance_revision_id = ?", (world["pr"]["id"],)).fetchone()
    cols = [d[0] for d in con.execute(
        "SELECT * FROM performance_revision_vocal_bindings "
        "LIMIT 0").description]
    r = dict(zip(cols, row))
    doc = {
        "binding_schema_version": r["binding_schema_version"],
        "synchronization_basis_version":
            r["synchronization_basis_version"],
        "vocal_performance_revision_id":
            r["vocal_performance_revision_id"],
        "source_start_sample": r["source_start_sample"],
        "source_end_sample_exclusive": 120000,   # the mutation
        "sample_rate_hz": r["sample_rate_hz"],
        "performance_origin_ms": {
            "num": r["performance_origin_num"],
            "den": r["performance_origin_den"]},
    }
    con.execute(
        "UPDATE performance_revision_vocal_bindings SET "
        "source_end_sample_exclusive = 120000, binding_json = ?, "
        "binding_hash = ? WHERE performance_revision_id = ?",
        (_cj(doc), _ch(doc), world["pr"]["id"]))
    con.commit()
    con.close()

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 500, r.text
    message = r.json()["message"]
    # the CAPTURED-HASH branch — NOT the self-authentication branch
    assert "captured vocal closure disagrees with the immutable " \
        "synchronization binding" in message, message
    assert "fails its own canonical structural law" not in message, \
        message


@pytest.mark.asyncio
async def test_rr8_positive_assertion_repaired(client):
    """The repaired positive proof: the §12 answer's
    synchronization_binding.binding_hash EQUALS the actual canonical
    hash of the lawful immutable binding document (a real identity,
    never a precedence tautology), and the RR6 subsegment path stays
    green end-to-end."""
    world, first_revision = await _stage_lawful(client)

    r = await client.put(
        f"/shots/{world['shot']}/vocal-segments/0",
        json={
            "vocal_performance_revision_id": world["vp"]["id"],
            "source_start_sample": 60000,
            "source_end_sample_exclusive": 84000,
            "sample_rate_hz": 48000,
            "performance_origin_ms": {"num": 0, "den": 1},
            "shot_anchor_ms": {"num": 250, "den": 1},
        })
    assert r.status_code == 200, r.text
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 250, 750, 250, vp=0))
    assert r.status_code == 200, r.text

    revision, _visual = await _capture(client, world["shot"])

    # the lawful immutable binding document's actual canonical hash
    binding = await _row(client, (
        "SELECT binding_json FROM performance_revision_vocal_bindings "
        "WHERE performance_revision_id = :p"), {"p": world["pr"]["id"]})
    expected_hash = _ch(json.loads(binding["binding_json"]))
    assert _cj(json.loads(binding["binding_json"])) == \
        binding["binding_json"]

    r = await client.get(f"/shot-revisions/{revision.id}/continuity")
    assert r.status_code == 200, r.text
    seg = r.json()["performance"]["segments"][0]
    exposed = seg["vocal"]["synchronization_binding"]["binding_hash"]
    assert exposed == expected_hash
    assert exposed == _ch(json.loads(binding["binding_json"]))
    # and the captured child carries the SAME hash
    child = await _row(client, (
        f"SELECT vocal_binding_hash FROM {_CHILDREN} WHERE "
        "shot_revision_id = :r AND position = 0"), {"r": revision.id})
    assert child["vocal_binding_hash"] == expected_hash
