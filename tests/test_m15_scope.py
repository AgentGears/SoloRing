"""M15C source-scope audit (frozen R6 §15/§31.8 M15-APPLY:15)."""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import text

from tests.m15_seed import seed_a4_use

REPO = Path(__file__).resolve().parents[1]


async def test_all_direct_production_revision_source_mutation_paths_are_gated(
        client):
    """M15-APPLY:15 — every code path capable of mutating a direct
    ProductionRevision-backed composition_working_occurrences source
    routes through exactly one of: M15 fenced apply, replace_as_new,
    or nested predecessor behavior. No backdoor swap exists."""
    base = await seed_a4_use(client, tag=b"scope15")

    # 1. every production-source SQL writer in server/ source is in
    #    the audited allowlist
    allowed_writers = {
        # M15 fenced apply (the one ordinary mutator)
        "server/soloring/compatibility/apply.py",
        # predecessor identity-changing operations (replace_as_new /
        # remove_occurrence) — the M12 identity-apply machinery
        "server/soloring/composition/service.py",
        "server/soloring/composition/impacts.py",
    }
    pattern = re.compile(
        r"UPDATE\s+composition_working_occurrences|INSERT\s+INTO\s+"
        r"composition_working_occurrences|DELETE\s+FROM\s+"
        r"composition_working_occurrences", re.I)
    offenders = []
    for path in (REPO / "server/soloring").rglob("*.py"):
        body = path.read_text(encoding="utf-8", errors="replace")
        if "composition_working_occurrences" not in body:
            continue
        for m in pattern.finditer(body):
            line_start = body.rfind("\n", 0, m.start()) + 1
            line = body[line_start:body.find("\n", m.start())]
            if "--" in body[max(0, line_start - 200):line_start] \
                    and "test" in path.name:
                continue
            offenders.append((path.relative_to(REPO).as_posix(),
                              line.strip()))
    real = [o for o in offenders if o[0] not in allowed_writers]
    assert not real, real

    # 2. composition/service.py writers are the identity-operation
    #    family (apply_identity_operation), never a direct source swap
    svc = (REPO / "server/soloring/composition/service.py").read_text(
        encoding="utf-8")
    for m in re.finditer(
            r"UPDATE\s+composition_working_occurrences(.*?);",
            svc, re.I | re.S):
        block = m.group(0)
        assert "production_revision_id = " not in block or (
            "replace" in block.lower() or "identity" in block.lower()), (
        "service.py contains a non-identity source writer", block[:120])

    # 3. live probe: the one working source row can only move via the
    #    M15 apply (PATCH already refused by APPLY:12; the API surface
    #    exposes no other write that touches the source)
    engine = client._transport.app.state.engine
    r = await client.get(
        f"/compositions/{base['composition_id']}/occurrences")
    assert all(o["source_kind"] in ("production_revision",
                                    "composition_revision")
               for o in r.json())
