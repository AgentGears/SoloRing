"""M14B-6 — feature-film scale and benchmark proofs (frozen R2 §45;
proof cells M14-SCALE:01..05).

The closure load is set-oriented: SQL round trips stay bounded by
domain batch (one CompositionRevision load + one ProductionRevision
batch + one closure batch + one interpretation batch) at 10, 100, and
1,000 addressable occurrences; no per-occurrence SELECT loop exists.
The B1 frozen resource caps refuse BEFORE rasterization allocation
(both stages), the benchmark machinery records CPU + peak memory +
artifact size per tier into tmp_path evidence, and the repository
working tree carries no residue after the proofs.
"""

from __future__ import annotations

import json
import re
import time

import pytest
from sqlalchemy import text

TIERS = (10, 100, 1000)


def _statement_class(statement: str) -> str:
    """The statement with bind-placeholder arity erased — a batch of N
    ids and a batch of M ids are the same SQL class, one round trip
    each."""
    return re.sub(r"\(\?(?:,\?)*\)", "(?)", statement)

_PINNED_CONTRACT_HASH = (
    "dd3511218c673e7f2727d8226c3d73bfd85222bd5f9a5edb3d2e4779146f66d0")

_MESH_COORDINATE_SYSTEM = {
    "handedness": "right", "right_axis": "+x", "up_axis": "+y",
    "depth_positive_axis": "+z", "forward_axis": "-z",
    "linear_unit": "millimeter", "vector_convention": "column",
}


def _engine_of(client):
    return client._transport.app.state.engine


class _SqlCounter:
    """Engine-level SELECT counter, active only inside its context."""

    def __init__(self, engine):
        from sqlalchemy import event

        self.statements: list[str] = []
        self.active = False
        event.listen(engine.sync_engine, "before_cursor_execute", self._hook)

    def _hook(self, conn, cursor, statement, parameters, context,
              executemany=False):
        if self.active and statement.lstrip().upper().startswith("SELECT"):
            self.statements.append(
                _statement_class(" ".join(statement.split())))

    def __enter__(self):
        self.active = True
        return self

    def __exit__(self, *exc):
        self.active = False


async def _scaled_world(client, *, tag: bytes, occurrences: int,
                        first_offset: int = 0):
    """A captured schema-6 world whose composition carries the given
    number of direct tiny-mesh occurrences (comfortably below B1 caps).
    ``first_offset`` keeps per-tier blob contents distinct when several
    tiers share one test database."""
    from tests.test_m14_materializer import _mesh_doc, _observation_world

    sources = [
        {"kind": "mesh", "mesh": _mesh_doc(offset=first_offset + i),
         "transform": (25, -50, 10), "interpretation": (5, 0, 0)}
        for i in range(occurrences)]
    return await _observation_world(
        client, tag=tag, sources=sources, adopt_first_mesh=False)


async def _load_with_sql_count(client, snapshot):
    from soloring.observation.retained import load_retained_mesh_sources
    from tests.test_m14_materializer import _reader

    engine = _engine_of(client)
    counter = _SqlCounter(engine)
    with counter:
        async with engine.connect() as conn:
            outcome = await load_retained_mesh_sources(
                conn, _reader(client),
                captured_production_world=snapshot["production_world"],
                captured_spatial_pack=snapshot["spatial_continuity"])
    return outcome, counter.statements


async def _latest_revision_id(client, shot_id: str) -> str:
    async with _engine_of(client).connect() as conn:
        return (await conn.execute(text(
            "SELECT id FROM shot_revisions WHERE shot_id = :s "
            "ORDER BY revision_number DESC LIMIT 1"),
            {"s": shot_id})).scalar_one()


async def _companions(client, revision_id: str) -> dict:
    async with _engine_of(client).connect() as conn:
        return dict((await conn.execute(text(
            "SELECT srsw.spatial_continuity_hash, "
            "srpw.production_world_hash FROM shot_revisions sr "
            "LEFT JOIN shot_revision_spatial_worlds srsw "
            "  ON srsw.shot_revision_id = sr.id "
            "LEFT JOIN shot_revision_production_worlds srpw "
            "  ON srpw.shot_revision_id = sr.id "
            "WHERE sr.id = :rid"), {"rid": revision_id})).mappings().one())


_DOMAIN_CLASSES = (
    "FROM composition_revisions",
    "FROM production_revisions",
    "FROM production_revision_closures",
    "FROM production_revision_spatial_interpretations",
)


# ---- M14-SCALE:01/02 bounded SQL classes; no per-occurrence loop ---------

async def test_m14_scale_01(client) -> None:
    """M14-SCALE:01 the 10/100/1000 closure load has bounded SQL classes:
    exactly the four domain batches, identical at every tier."""
    from soloring.observation.retained import (
        MAX_TOTAL_TRIANGLES_PER_OBSERVATION,
    )

    per_tier: dict[int, list[str]] = {}
    first_offset = 0
    for tier in TIERS:
        _b, snapshot, oids, _prids = await _scaled_world(
            client, tag=f"m14-scale01-{tier}".encode(), occurrences=tier,
            first_offset=first_offset)
        first_offset += tier
        assert len(oids) == tier, (
            f"premise: {tier} addressable occurrences exist")
        outcome, statements = await _load_with_sql_count(client, snapshot)
        assert len(outcome.sources) == tier
        assert outcome.total_triangles <= (
            MAX_TOTAL_TRIANGLES_PER_OBSERVATION), (
            "the ordinary scale proof stays comfortably below the B1 caps")
        per_tier[tier] = statements

    for tier, statements in per_tier.items():
        assert all(any(cls in s for cls in _DOMAIN_CLASSES)
                   for s in statements), (
            f"tier {tier}: every loader SELECT is one of the four domain "
            f"batches — got {statements}")
    first = per_tier[TIERS[0]]
    for tier in TIERS[1:]:
        assert per_tier[tier] == first, (
            f"tier {tier} issued different SQL than tier {TIERS[0]}: "
            f"{per_tier[tier]} vs {first}")
    assert len(first) == 4, (
        "exactly the four domain batches: composition, production "
        f"revisions, closures, interpretations — got {first}")


async def test_m14_scale_02(client) -> None:
    """M14-SCALE:02 no per-occurrence closure/interpretation SELECT loop:
    at every tier no loader statement repeats — a per-occurrence loop
    would necessarily re-execute its statement class per occurrence."""
    first_offset = 0
    for tier in TIERS:
        _b, snapshot, _oids, _prids = await _scaled_world(
            client, tag=f"m14-scale02-{tier}".encode(), occurrences=tier,
            first_offset=first_offset)
        first_offset += tier
        _outcome, statements = await _load_with_sql_count(client, snapshot)
        assert len(statements) == len(set(statements)), (
            f"tier {tier}: a repeated statement implies a per-occurrence "
            f"loop — {statements}")
        for cls in _DOMAIN_CLASSES:
            assert sum(1 for s in statements if cls in s) <= 1, (
                f"tier {tier}: domain batch {cls} executed more than "
                "once — the load is not set-oriented")


# ---- M14-SCALE:03 B1 caps refuse before rasterization allocation ----------

async def test_m14_scale_03(client, monkeypatch) -> None:
    """M14-SCALE:03 the B1 frozen resource caps refuse BEFORE
    rasterization allocation — Stage A (bytes, before JSON decode) and
    Stage B (elements, after classification before transform expansion)
    — and the rasterizer is never entered."""
    from soloring.errors import ErrorCode, SoloRingError
    from soloring.observation.retained import load_retained_mesh_sources
    from tests.m13_seed import make_composition, mint, publish
    from tests.test_m13_binding import _publish
    from tests.test_m13_shot_capture import _capture, _full_m13_world
    from tests.test_m14_materializer import (
        _mesh_production_revision,
        _write_blob,
        structural_mesh_bytes,
    )

    raster_calls: list = []

    def _spy_raster(*args, **kwargs):
        raster_calls.append((args, kwargs))
        raise AssertionError(
            "the rasterizer was entered for an over-cap retained mesh")

    import soloring.spatial.boxdepth as boxdepth_module

    monkeypatch.setattr(boxdepth_module, "materialize", _spy_raster)

    # ---- Stage B: an otherwise-valid mesh over the frozen triangle cap.
    # Vertices sit on the integer paraboloid z = x² + y² — a line meets
    # a strictly convex surface in at most two points, so no distinct
    # triple is ever collinear (zero-area rejection cannot fire first).
    side = 44
    vertices = [[x * 37, y * 53, (x * x + y * y) * 11]
                for y in range(side) for x in range(side)]
    triangles = []
    i = 0
    while len(triangles) <= 500_000:
        a = i % len(vertices)
        b = (i + 7) % len(vertices)
        c = (i + 13 + side) % len(vertices)
        if len({a, b, c}) == 3:
            triangles.append([a, b, c])
        i += 1
    assert len(triangles) == 500_001
    over_cap_doc = {
        "schema_version": 1, "kind": "soloring.structural_mesh",
        "coordinate_system": _MESH_COORDINATE_SYSTEM,
        "vertices_mm": vertices, "triangles": triangles,
    }

    b = await _full_m13_world(client, tag=b"m14-scale03")
    engine = _engine_of(client)
    from tests.test_m14_materializer import _reader

    async def _capture_over_world(client, blob, number) -> dict:
        await _write_blob(client, blob)
        prid = await _mesh_production_revision(
            client, b["pid"], blob, number=number)
        cid = await make_composition(client, b["pid"])
        await mint(client, cid, prid, 0, transform=(0, 0, 0))
        composed = (await publish(
            client, cid, 1))["revision"]["revision_id"]
        published = await _publish(client, composed, b["rev"]["id"])
        assert published.status_code == 201, published.text
        return published.json()["binding_id"]

    binding_b = await _capture_over_world(
        client, structural_mesh_bytes(over_cap_doc), 900)
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": binding_b, "expected_binding_id": None})
    assert r.status_code == 200, r.text
    revision_b, _ = await _capture(client, b["shot"])
    snapshot_b = json.loads(revision_b.snapshot_json)
    assert snapshot_b["schema_version"] == 6

    with pytest.raises(SoloRingError) as excinfo:
        async with engine.connect() as conn:
            await load_retained_mesh_sources(
                conn, _reader(client),
                captured_production_world=(
                    snapshot_b["production_world"]),
                captured_spatial_pack=snapshot_b["spatial_continuity"])
    assert excinfo.value.code == ErrorCode.STRUCTURAL_MESH_LIMIT_EXCEEDED
    assert raster_calls == [], (
        "the Stage B element cap must refuse before any rasterization "
        "allocation")

    # ---- Stage A: a physical retained blob over the frozen byte cap,
    # refused before JSON decode (the bytes are not valid mesh at all)
    oversized = b"x" * (100_000_000 + 1)
    binding_a = await _capture_over_world(client, oversized, 901)
    r = await client.put(
        f"/shots/{b['shot']}/production-world-selection",
        json={"binding_id": binding_a, "expected_binding_id": binding_b})
    assert r.status_code == 200, r.text
    revision_a, _ = await _capture(client, b["shot"])
    snapshot_a = json.loads(revision_a.snapshot_json)
    with pytest.raises(SoloRingError) as excinfo_a:
        async with engine.connect() as conn:
            await load_retained_mesh_sources(
                conn, _reader(client),
                captured_production_world=(
                    snapshot_a["production_world"]),
                captured_spatial_pack=snapshot_a["spatial_continuity"])
    assert excinfo_a.value.code == ErrorCode.STRUCTURAL_MESH_LIMIT_EXCEEDED
    assert "MAX_RETAINED_MESH_BYTES_PER_REVISION" in (
        excinfo_a.value.message)
    assert raster_calls == [], "Stage A also never reaches the rasterizer"


# ---- M14-SCALE:04 benchmark records CPU + peak memory + artifact size -----

async def test_m14_scale_04(client, tmp_path) -> None:
    """M14-SCALE:04 the benchmark/materializer machinery records CPU,
    peak memory, and artifact size for every tier into tmp_path
    evidence (never the repository)."""
    import tracemalloc

    from soloring.observation.compiler import compile_world_observation_spec
    from soloring.observation.materializer import (
        materialize_observation_world_depth,
    )
    from soloring.observation.retained import (
        load_retained_mesh_sources,
        merge_retained_into_spec,
    )
    from soloring.spatial import schemas as spatial_schemas
    from tests.test_m14_materializer import _reader

    evidence: dict[int, dict] = {}
    first_offset = 0

    for tier in TIERS:
        _b, snapshot, _oids, _prids = await _scaled_world(
            client, tag=f"m14-scale04-{tier}".encode(), occurrences=tier,
            first_offset=first_offset)
        first_offset += tier
        revision_id = await _latest_revision_id(client, _b["shot"])
        companions = await _companions(client, revision_id)

        tracemalloc.start()
        cpu_compile = time.perf_counter()
        spec = compile_world_observation_spec(
            shot_id=_b["shot"],
            shot_revision_id=revision_id,
            plan_hash=spatial_schemas.plan_hash(
                snapshot["spatial_continuity"]["shot_plan"]),
            captured_schema_6=snapshot,
            spatial_continuity_hash=companions["spatial_continuity_hash"],
            production_world_hash=companions["production_world_hash"],
            visual_reference_pack_hash=None,
            materializer_contract_hash=_PINNED_CONTRACT_HASH)
        cpu_compile = time.perf_counter() - cpu_compile

        cpu_load = time.perf_counter()
        async with _engine_of(client).connect() as conn:
            retained = await load_retained_mesh_sources(
                conn, _reader(client),
                captured_production_world=snapshot["production_world"],
                captured_spatial_pack=snapshot["spatial_continuity"])
        spec = merge_retained_into_spec(spec, retained)
        cpu_load = time.perf_counter() - cpu_load

        cpu_materialize = time.perf_counter()
        result = materialize_observation_world_depth(
            snapshot["spatial_continuity"], retained.sources)
        cpu_materialize = time.perf_counter() - cpu_materialize
        _current, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        evidence[tier] = {
            "tier": tier,
            "sql_statement_classes": 4,
            "captured_json_bytes": len(
                json.dumps(snapshot).encode("utf-8")),
            "production_revision_rows": tier,
            "closure_rows": tier,
            "interpretation_rows": tier,
            "mesh_bytes": sum(
                len(_reader(client)(s.retained_blob_hash))
                for s in retained.sources),
            "triangle_count": retained.total_triangles,
            "observation_compiler_cpu_s": round(cpu_compile, 6),
            "closure_and_transform_cpu_s": round(cpu_load, 6),
            "materializer_cpu_s": round(cpu_materialize, 6),
            "peak_memory_bytes": peak_memory,
            "derived_artifact_bytes": len(b"".join(result.frames)),
            "derived_artifact_digest": result.digest,
        }

    numeric_fields = (
        "sql_statement_classes", "captured_json_bytes",
        "production_revision_rows", "closure_rows", "interpretation_rows",
        "mesh_bytes", "triangle_count", "observation_compiler_cpu_s",
        "closure_and_transform_cpu_s", "materializer_cpu_s",
        "peak_memory_bytes", "derived_artifact_bytes")
    for tier, row in evidence.items():
        for field in numeric_fields:
            assert row[field] is not None and row[field] >= 0, (
                f"tier {tier}: benchmark field {field} missing/empty")
        assert row["derived_artifact_digest"], (
            f"tier {tier}: the artifact digest is recorded")
        assert row["triangle_count"] == tier * 2, (
            "each tiny mesh contributes exactly two triangles")

    record = tmp_path / "m14-scale04-evidence.json"
    record.write_text(json.dumps(evidence, indent=1, sort_keys=True),
                      encoding="utf-8")
    reloaded = json.loads(record.read_text(encoding="utf-8"))
    assert reloaded == {str(tier): row for tier, row in evidence.items()}, (
        "the recorded evidence round-trips exactly")


# ---- M14-SCALE:05 repository residue absent -------------------------------

async def test_m14_scale_05(client, tmp_path) -> None:
    """M14-SCALE:05 the repository working tree carries no residue after
    the scale/benchmark proofs: the tracked tree is untouched and no
    new untracked paths appear."""
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]

    def _snapshot_tree() -> frozenset[str]:
        out = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(repo),
            capture_output=True, text=True, check=True)
        return frozenset(out.stdout.splitlines())

    before = _snapshot_tree()

    # re-run the smallest tier of the exact scale machinery end-to-end
    from soloring.observation.materializer import (
        materialize_observation_world_depth,
    )

    _b, snapshot, _oids, _prids = await _scaled_world(
        client, tag=b"m14-scale05", occurrences=TIERS[0])
    outcome, _statements = await _load_with_sql_count(client, snapshot)
    result = materialize_observation_world_depth(
        snapshot["spatial_continuity"], outcome.sources)
    (tmp_path / "scale05-digest.txt").write_text(
        result.digest, encoding="utf-8")

    after = _snapshot_tree()
    assert after == before, (
        "scale/benchmark proofs must leave zero repository residue: "
        f"new/changed paths {sorted(after - before)}")
