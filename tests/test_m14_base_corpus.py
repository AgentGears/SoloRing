"""M14A-3 — predecessor WorkflowSpec regression corpus (frozen R2 §38
E1; proof cell M14-BASE:04).

Schema 1/2/3 execution meaning is unchanged by the M14A-3 integration:
the schema-5 spatial path still composes exactly schema 3 through the
same frozen seam, byte-for-byte.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from tests.test_m10e_generation import _create, _spatial_seed, _spatial_settings
from tests.test_m10e_package3_production import _schema3_package


async def test_m14_base_04(factory, engine, settings, tmp_path):
    """M14-BASE:04 WorkflowSpec schema-1/2/3 regression corpus green.

    The M10E schema-5 spatial path through the integrated service still
    produces exactly schema 3 — the M14A-3 branch is unreachable for
    schema ≤ 5."""
    pkg = await _schema3_package(tmp_path)
    seed = await _spatial_seed(factory, staged=1, extents=[600, 400, 300])
    generation = await _create(
        factory, _spatial_settings(settings, pkg), seed)

    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"),
            {"g": generation.id})).mappings().one()
    spec = json.loads(row["workflow_spec_json"])

    assert spec["schema_version"] == 3, (
        "schema-5 captures compose exactly schema 3 — unchanged by M14A-3")
    assert "world_observation" not in spec
    assert "spatial_realization" in spec

    from soloring.domain.canonical import canonical_hash

    assert canonical_hash(spec) == row["workflow_spec_hash"]

    from soloring.spatial.spec3 import validate_spec_v3

    validate_spec_v3(spec)
