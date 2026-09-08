# SoloRing

Local-first **feature-film-level continuity architecture**: a persistent
production-authority and historical-world model in which every creative,
spatial, and assembly decision is captured as immutable, mechanically
verified state that can be reproduced exactly later — on this machine,
without any cloud dependency.

What exists through M13:

- **Story World & continuity (M6–M8)** — CreativeEntities with immutable
  kind-specific design revisions, explicit approvals, narrative structure
  (Sequences → Scenes → Shots), semantic dependencies, capture-time
  approved-revision resolution, immutable ShotRevisions, and a
  feature-film-grade authority model for continuity state and visual
  identity.
- **Reusable production identity (M11)** — Production Objects with
  immutable, closed Production Revisions (retained-byte provenance).
- **Stable occurrence identity (M12)** — Compositions with durable
  occurrence identity and lineage-bearing identity operations
  (mint/replace/split/merge/fork).
- **REMEMBER THE WORLD (M13)** — authority subjects for direct
  occurrences, Production Instance persistent state and spatial staging,
  the immutable Composition↔Spatial binding, schema-6 Shot capture on one
  coherent read, captured-graph-only historical reads, and Exact Rerun
  isolation from current production state.

Generation/executor support (ComfyUI binding, durable provenance, Exact
Rerun) exists and is exercised live, but a generalized renderer-neutral
feature-film execution layer is **downstream**: M14 (SHOOT THE WORLD) is
the future execution-enforcement milestone, not an implemented capability.

Status: **M13 — Authority-Complete Reusable World — CLOSED + PUBLISHED**
at `M13 @ 384a46d3a5c68d7d81784befc338aa8621b93fbd` (annotated tag `M13`,
migration head `0014_m13_authority_complete_world`). Earlier milestones
M0–M12 are closed; the M1-era audit record lives in
`docs/AUDIT_REMEDIATION.md` and the live deployment contract in
`docs/EXECUTOR_PROFILE.md`.

## Layout

```
apps/web/              Next.js frontend (project/shot editors, Story World,
                       World/Set workspace, Production Library, spatial
                       worlds & staging, Shot production-world surfaces)
server/soloring/       Python package (api, db, domain, continuity,
                       narrative, generation, executors, worker, assets,
                       production, composition, production_world)
server/alembic/        migrations (head: 0014_m13_authority_complete_world)
workflows/             ComfyUI workflow contracts (M4/M5)
data/                  runtime SQLite db, blobs, staging, tmp (gitignored)
tests/                 test suite (milestone proof maps + hygiene gates)
scripts/               proof-map/boundary/audit validators + live gates
docs/                  plans, proof maps, hygiene baseline, evidence
```

### Package versioning note

The `soloring` package version in `pyproject.toml` is independent of the
milestone numbering: milestones are immutable tagged baselines
(`M7`…`M13`), and the package semver is **deliberately left at 0.1.0**
until an explicit package-release policy exists. No package release is
implied by any milestone publication.

## Dev setup

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"   # Windows / Git Bash
# (on POSIX: source .venv/bin/activate && pip install -e ".[dev]")
```

## Run

```bash
# web (plan §4)
uvicorn soloring.api.main:app --reload
# worker (plan §4) — never runs inside FastAPI
python -m soloring.worker
```

Both expect the `soloring` package importable (editable install handles this).

## Test

```bash
.venv/Scripts/python.exe -m pytest
```

## Migrations

```bash
cd server && alembic upgrade head     # apply
cd server && alembic downgrade base    # remove
```

## Worker identity (plan §8)

Every worker process generates a fresh `uuid4()` id at startup. It is never
configurable, never loaded from the environment, and never persisted. The
durable authority is the stable lease role `generation-worker`; the worker id
is an ephemeral process incarnation.

## Architecture rule (plan §1)

> Creative state points downward into execution infrastructure.
> Execution infrastructure never defines creative state.
