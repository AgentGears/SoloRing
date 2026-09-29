"""M17C-B IND2 corrective regressions (IND2-01..03, frozen under the
PR #26 protocol cycle of 2026-09-29; product base a8c822b).

- IND2-01: persisted candidate provenance must be TEXT storage — a
  BLOB (X'FF' or even a valid-UTF8 BLOB containing valid JSON) refuses
  as recovery corruption with a provenance-specific diagnostic, never
  a raw UnicodeDecodeError, at BOTH supported recovery heads.
- IND2-02: the COMPLETE blob filesystem boundary is normalized — the
  existence probe and the content read are one narrow boundary;
  stat/read PermissionError, representative OSError, and the
  probe-to-read disappearance race all surface as branch-specific
  recovery corruption against the STAGED copy (matched by blob NAME).
- IND2-03: retarget eligibility precedence without trusting stored
  verdicts — Phase A recomputes the assessment and returns the
  RECOMPUTED verdict; the lawful no-op 4xx branches fire BEFORE any
  review resolution; only recomputed REQUIRES_REVIEW resolves the
  accepted review (Phase B); corrupt assessments fire historical
  corruption FIRST.
"""

from __future__ import annotations

import pathlib
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.errors import SoloRingError
from tests.test_m17c_shot_mapping import (
    _bound_world,
    _generic_world,
    _seg_body,
)

_TABLE = "shot_performance_segment_mappings"


def _engine(client):
    return client._transport.app.state.engine


async def _sql(client, stmt, params=None):
    async with _engine(client).begin() as conn:
        await conn.execute(text(stmt), params or {})


async def _one(client, stmt, params=None):
    async with _engine(client).connect() as conn:
        return dict((await conn.execute(
            text(stmt), params or {})).mappings().one())


def _corrupt(resp):
    assert resp.status_code == 500, resp.text
    assert resp.json()["error_code"] == "INTERNAL_INVARIANT_VIOLATION"


async def _backup_0021(client, tmp_path, tag):
    from tests.test_m17c_sr26_regressions import _backup_m17c
    return await _backup_m17c(client, tmp_path, tag)


async def _backup_0020(client, tmp_path, tag):
    from soloring.recovery.backup import M17C_A_ALEMBIC_HEAD
    from tests.test_m17c_sr2_regressions import _retarget_backup
    root = await _backup_0021(client, tmp_path, tag + "-src")
    _retarget_backup(root, M17C_A_ALEMBIC_HEAD, drop_pf02=True)
    return root


async def _restore_refuses(backup_root, tmp_path, tag):
    from tests.test_m17c_sr2_regressions import (
        _restore_refuses as sr2_refuses)
    return await sr2_refuses(backup_root, tmp_path, tag)


async def _lawful_mapping(client, world):
    r = await client.put(
        f"/shots/{world['shot']}/performance-segments/0",
        json=_seg_body(world["pr"]["id"], 0, 1000, 0, vp=0))
    assert r.status_code == 200, r.text


async def _retargeted_world(client):
    """A dialogue-bound world carrying one lawful RETARGETED
    candidate (for the retargeted-provenance storage regressions)."""
    from tests.m17b_seed import (seed_production_object,
                                 seed_production_revision)
    world = await _bound_world(client)
    await _lawful_mapping(client, world)
    obj = await seed_production_object(
        client, world["project_id"], "IND2 obj", b"ind2")
    p1 = await seed_production_revision(client, obj, b"ind2-1", 1)
    p2 = await seed_production_revision(client, obj, b"ind2-2", 2)
    a = (await client.post(
        f"/performance-revisions/{world['pr']['id']}/"
        "retarget-assessments",
        json={"from_production_revision_id":
              p1["production_revision_id"],
              "to_production_revision_id":
              p2["production_revision_id"]})).json()
    acc = (await client.post(
        f"/performance-retarget-assessments/{a['id']}/reviews",
        json={"decision": "ACCEPT_FOR_NEW_CANDIDATE",
              "reviewed_by": "ind2", "rationale": None})).json()
    rc = (await client.post(
        f"/performance-revisions/{world['pr']['id']}/"
        "retarget-candidates",
        json={"assessment_id": a["id"],
              "accepted_review_id": acc["id"],
              "producer_id": "ind2", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None}))
    assert rc.status_code == 201, rc.text
    world["retarget_candidate_id"] = rc.json()["id"]
    return world


def _set_provenance_blob(root: Path, candidate_id: str,
                         blob_literal: str) -> None:
    con = sqlite3.connect(root / "soloring.db")
    con.execute(
        "UPDATE performance_candidates SET provenance_json = " +
        blob_literal + " WHERE id = ?", (candidate_id,))
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# IND2-01 — provenance TEXT storage + stable parser corruption
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("head,make_backup", [
    ("0020", lambda c, t, tag: _backup_0020(c, t, tag)),
    ("0021", lambda c, t, tag: _backup_0021(c, t, tag)),
])
async def test_ind201_generic_provenance_blob_storage_refuses(
        client, tmp_path, head, make_backup):
    """A generic candidate's provenance_json stored as a BLOB (X'FF')
    refuses at both recovery heads with a provenance-specific TEXT
    storage diagnostic — never a UnicodeDecodeError."""
    world = await _bound_world(client)
    if head == "0021":
        await _lawful_mapping(client, world)
    root = await make_backup(client, tmp_path, f"ind201-{head}")
    _set_provenance_blob(root, world["candidate"]["id"], "X'FF'")
    exc = await _restore_refuses(root, tmp_path, f"ind201-{head}")
    assert isinstance(exc, SoloRingError), exc
    assert exc.code == "RECOVERY_CORRUPTION", exc
    assert "not persisted TEXT storage" in str(exc), exc
    assert "bytes" in str(exc), exc


@pytest.mark.asyncio
async def test_ind201_retargeted_provenance_blob_storage_refuses(
        client, tmp_path):
    """The retargeted candidate pass enforces the same TEXT-storage
    law: an X'FF' BLOB provenance refuses with the same family."""
    world = await _retargeted_world(client)
    root = await _backup_0021(client, tmp_path, "ind201-rt")
    _set_provenance_blob(root, world["retarget_candidate_id"], "X'FF'")
    exc = await _restore_refuses(root, tmp_path, "ind201-rt")
    assert isinstance(exc, SoloRingError), exc
    assert exc.code == "RECOVERY_CORRUPTION", exc
    assert "not persisted TEXT storage" in str(exc), exc


@pytest.mark.asyncio
async def test_ind201_valid_utf8_json_blob_still_refuses(client, tmp_path):
    """The frozen storage representation is TEXT, not 'anything that
    decodes': a BLOB containing otherwise-valid UTF-8 JSON refuses —
    the runtime storage class itself is the corruption."""
    world = await _bound_world(client)
    root = await _backup_0021(client, tmp_path, "ind201-vb")
    con = sqlite3.connect(root / "soloring.db")
    stored = con.execute(
        "SELECT provenance_json FROM performance_candidates WHERE "
        "id = ?", (world["candidate"]["id"],)).fetchone()[0]
    con.execute(
        "UPDATE performance_candidates SET provenance_json = CAST(? AS "
        "BLOB) WHERE id = ?", (stored, world["candidate"]["id"]))
    con.commit()
    # prove the persisted value really is BLOB storage now
    typeof = con.execute(
        "SELECT typeof(provenance_json) FROM performance_candidates "
        "WHERE id = ?", (world["candidate"]["id"],)).fetchone()[0]
    con.close()
    assert typeof == "blob"
    exc = await _restore_refuses(root, tmp_path, "ind201-vb")
    assert isinstance(exc, SoloRingError), exc
    assert exc.code == "RECOVERY_CORRUPTION", exc
    assert "not persisted TEXT storage" in str(exc), exc


# ---------------------------------------------------------------------------
# IND2-02 — the complete blob filesystem boundary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("probe_error,read_error,fragment", [
    # (1) the existence/type probe boundary -> PermissionError
    (PermissionError("denied"), None,
     "permission denied) during the storage probe"),
    # (2) the stat boundary -> representative OSError(EIO)
    (OSError(5, "Input/output error"), None,
     "storage error") ,
    # (3) the content read -> PermissionError
    (None, PermissionError("denied"),
     "unreadable (permission denied)"),
    # (4) the content read -> representative OSError
    (None, OSError(5, "Input/output error"),
     "unreadable through a storage error"),
    # (5) disappearance between a successful probe and the read
    (None, FileNotFoundError("gone"),
     "disappeared during restore verification"),
])
async def test_ind202_blob_filesystem_boundary_normalized(
        client, tmp_path, monkeypatch, probe_error, read_error,
        fragment):
    """All five filesystem-boundary failures refuse through the stable
    recovery-corruption contract with branch-specific diagnostics.
    Monkeypatched at the recovery seam against the STAGED copy,
    selected by blob NAME (never OS-ACL dependent)."""
    world = await _bound_world(client)
    await _lawful_mapping(client, world)
    root = await _backup_0021(client, tmp_path, "ind202")
    blob_hash = (await _one(
        client,
        "SELECT canonical_channel_payload_blob_hash AS h FROM "
        "performance_candidates WHERE id = :c",
        {"c": world["candidate"]["id"]}))["h"]
    assert (root / "blobs" / "sha256" / blob_hash[:2]
            / blob_hash[2:4] / blob_hash).is_file()
    real_is_file = pathlib.Path.is_file
    real_read_bytes = pathlib.Path.read_bytes

    def selective_is_file(self):
        if probe_error is not None and self.name == blob_hash:
            raise probe_error
        return real_is_file(self)

    def selective_read_bytes(self):
        if self.name == blob_hash:
            if probe_error is not None:
                # the probe path is patched to raise, so read is only
                # reached in its absence
                pass
            if read_error is not None:
                raise read_error
        return real_read_bytes(self)

    monkeypatch.setattr(pathlib.Path, "is_file", selective_is_file)
    monkeypatch.setattr(pathlib.Path, "read_bytes", selective_read_bytes)
    exc = await _restore_refuses(root, tmp_path, "ind202")
    monkeypatch.setattr(pathlib.Path, "is_file", real_is_file)
    monkeypatch.setattr(pathlib.Path, "read_bytes", real_read_bytes)
    # the stable recovery-corruption contract: either SoloRingError
    # with the code, or the RecoveryCorruption/RecoveryError family
    # (the probe boundary lives in the backup module's own hierarchy)
    assert isinstance(exc, (SoloRingError, Exception)) and (
        getattr(exc, "code", None) == "RECOVERY_CORRUPTION"
        or type(exc).__name__ in ("RecoveryCorruption",)), exc
    assert fragment in str(exc), (fragment, exc)


# ---------------------------------------------------------------------------
# IND2-03 — retarget eligibility precedence without stored-verdict trust
# ---------------------------------------------------------------------------

async def _verdict_world(client, verdict: str):
    """A generic NONE source with a LAWFUL assessment recomputing the
    requested verdict (REQUIRES_REVIEW / COMPATIBLE_AS_IS /
    INCOMPATIBLE) and, for REQUIRES_REVIEW, an ACCEPT review."""
    from tests.m17b_seed import (seed_production_object,
                                 seed_production_revision)
    world = await _generic_world(client)
    world["candidate"] = {"id": (await _one(
        client,
        "SELECT adopted_candidate_id AS id FROM performance_revisions "
        "WHERE id = :r", {"r": world["pr"]["id"]}))["id"]}
    obj = await seed_production_object(
        client, world["project_id"], "IND2v obj", b"ind2v")
    p1 = await seed_production_revision(client, obj, b"ind2v-1", 1)
    if verdict == "COMPATIBLE_AS_IS":
        to = p1
    elif verdict == "INCOMPATIBLE":
        obj2 = await seed_production_object(
            client, world["project_id"], "IND2v obj2", b"ind2w")
        to = await seed_production_revision(client, obj2, b"ind2w-1", 1)
    else:
        to = await seed_production_revision(client, obj, b"ind2v-2", 2)
    a = (await client.post(
        f"/performance-revisions/{world['pr']['id']}/"
        "retarget-assessments",
        json={"from_production_revision_id":
              p1["production_revision_id"],
              "to_production_revision_id":
                  to["production_revision_id"]})).json()
    assert a["overall_verdict"] == verdict, a
    world["assessment"] = a
    if verdict == "REQUIRES_REVIEW":
        acc = (await client.post(
            f"/performance-retarget-assessments/{a['id']}/reviews",
            json={"decision": "ACCEPT_FOR_NEW_CANDIDATE",
                  "reviewed_by": "ind2", "rationale": None})).json()
        world["accept"] = acc
    return world


async def _counts(client):
    cands = (await _one(
        client, "SELECT COUNT(*) AS n FROM performance_candidates"))["n"]
    cls = (await _one(
        client,
        "SELECT COUNT(*) AS n FROM "
        "performance_candidate_sync_classifications"))["n"]
    binds = (await _one(
        client,
        "SELECT COUNT(*) AS n FROM "
        "performance_candidate_vocal_bindings"))["n"]
    return cands, cls, binds


_DUMMY = "55555555-5555-4555-8555-555555555555"


async def _retarget(client, world, review_id):
    return await client.post(
        f"/performance-revisions/{world['pr']['id']}/"
        "retarget-candidates",
        json={"assessment_id": world["assessment"]["id"],
              "accepted_review_id": review_id,
              "producer_id": "ind2", "producer_version": "1",
              "source_identity": None, "parameters_sha256": None})


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict,code", [
    ("INCOMPATIBLE", "RETARGET_INCOMPATIBLE"),
    ("COMPATIBLE_AS_IS", "RETARGET_NOT_REQUIRED"),
])
async def test_ind203_lawful_verdict_precedes_review_lookup(
        client, verdict, code):
    """Lawful recomputed INCOMPATIBLE / COMPATIBLE_AS_IS + a
    syntactically valid NONEXISTENT accepted_review_id -> the 4xx
    eligibility branch fires (the review id is never resolved), with
    zero new rows."""
    world = await _verdict_world(client, verdict)
    before = await _counts(client)
    r = await _retarget(client, world, _DUMMY)
    assert r.status_code == 422, r.text
    assert r.json()["error_code"] == code, r.text
    assert await _counts(client) == before


@pytest.mark.asyncio
async def test_ind203_corrupt_assessment_fires_before_missing_review(
        client):
    """Corrupt assessment + missing review id -> the ASSESSMENT
    historical corruption fires FIRST (500), because assessment
    authority precedes eligibility and review lookup."""
    world = await _verdict_world(client, "REQUIRES_REVIEW")
    await _sql(
        client,
        "UPDATE performance_retarget_assessments SET scope_hash = :v "
        "WHERE id = :a",
        {"v": "6" * 64, "a": world["assessment"]["id"]})
    before = await _counts(client)
    r = await _retarget(client, world, _DUMMY)
    _corrupt(r)
    assert "scope does not recompute" in r.json()["message"], r.text
    assert await _counts(client) == before


@pytest.mark.asyncio
async def test_ind203_requires_review_missing_review_not_found(client):
    """REQUIRES_REVIEW + a genuinely nonexistent request-supplied
    review id keeps the established not-found 404 contract."""
    world = await _verdict_world(client, "REQUIRES_REVIEW")
    before = await _counts(client)
    r = await _retarget(client, world, _DUMMY)
    assert r.status_code == 404, r.text
    assert r.json()["error_code"] == "RETARGET_REVIEW_NOT_FOUND"
    assert await _counts(client) == before


@pytest.mark.asyncio
async def test_ind203_requires_review_corrupt_existing_review(client):
    """REQUIRES_REVIEW + a corrupt EXISTING accepted review (repointed
    at another assessment) -> Phase B historical corruption, zero new
    rows."""
    from tests.m17b_seed import (seed_production_object,
                                 seed_production_revision)
    world = await _verdict_world(client, "REQUIRES_REVIEW")
    obj2 = await seed_production_object(
        client, world["project_id"], "IND2p obj", b"ind2p")
    q1 = await seed_production_revision(client, obj2, b"ind2p-1", 1)
    q2 = await seed_production_revision(client, obj2, b"ind2p-2", 2)
    a2 = (await client.post(
        f"/performance-revisions/{world['pr']['id']}/"
        "retarget-assessments",
        json={"from_production_revision_id":
              q1["production_revision_id"],
              "to_production_revision_id":
                  q2["production_revision_id"]})).json()
    before = await _counts(client)
    await _sql(
        client,
        "UPDATE performance_retarget_reviews SET assessment_id = :v "
        "WHERE id = :r",
        {"v": a2["id"], "r": world["accept"]["id"]})
    r = await _retarget(client, world, world["accept"]["id"])
    _corrupt(r)
    assert "different assessment" in r.json()["message"], r.text
    assert await _counts(client) == before


@pytest.mark.asyncio
async def test_ind203_lawful_requires_review_still_creates(client):
    """Lawful REQUIRES_REVIEW + lawful ACCEPT review -> creation
    remains successful (the precedence split changed no lawful
    behavior)."""
    world = await _verdict_world(client, "REQUIRES_REVIEW")
    before = await _counts(client)
    r = await _retarget(client, world, world["accept"]["id"])
    assert r.status_code == 201, r.text
    after = await _counts(client)
    assert after[0] == before[0] + 1
    assert after[1] == before[1] + 1
    assert after[2] == before[2]
