# SoloRing

Local-first **feature-film-level continuity architecture**: a persistent
production-authority and historical-world model in which every creative,
spatial, and assembly decision is captured as immutable, mechanically
verified state that can be reproduced exactly later — on this machine,
without any cloud dependency.

What exists through M16:

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
- **SHOOT THE WORLD (M14)** — world observation compilation and
  execution: structural mesh resource caps, the frozen
  MaterializerContract identity (materializer/rasterizer/runtime byte
  identities), observation artifacts imported from real certified
  ComfyUI execution with durable provenance, and the GPU source gates.
- **EVOLVE THE WORLD (M15)** — safe reusable revision evolution: update
  discovery and compatibility assessment over published revisions
  without silent rebasing of historical truth.
- **Intra-Shot persistent consequences (M16)** — intra-Shot events with
  exact before/after chains and folds, terminal state and Shot/end
  handoff equality, immutable proposals and explicit
  consequence review/adoption (single + atomic batch, R7 direct-review
  grammar), schema-7 Shot capture with immutable companions, historical
  re-fold, fail-closed generation fence for schema-7 authority, 0017
  recovery verification, and the Shot event-timeline / review UI.

Generation/executor support (ComfyUI binding, durable provenance, Exact
Rerun) exists and is exercised live through the M14 observation path;
M16 deliberately refuses to execute schema-7 (event-bearing) authority —
event-aware execution is downstream of a future contract.

Status: **M16 — Intra-Shot Persistent Consequences — CLOSED** at
certified head `9e703806304063110a07458c3d3e0b0124c6ab14`
(frozen plan R7, CI #149, migration head
`0017_m16_intra_shot_consequences`); merge/publication of the branch is
a separate pending gate. Earlier milestones M0–M15 are closed and
published — the M13 hygiene baseline remains
**M13 — Authority-Complete Reusable World — CLOSED + PUBLISHED**
at `M13 @ 384a46d3a5c68d7d81784befc338aa8621b93fbd`, then M14 @
`89298e7…` and M15 @ `30ea135f…`; the M1-era audit record lives in
`docs/AUDIT_REMEDIATION.md` and the live deployment contract in
`docs/EXECUTOR_PROFILE.md`.

## Layout

```
apps/web/              Next.js frontend (project/shot editors, Story World,
                       World/Set workspace, Production Library, spatial
                       worlds & staging, Shot production-world surfaces,
                       intra-Shot event timeline + consequence review)
server/soloring/       Python package (api, db, domain, continuity,
                       narrative, generation, executors, worker, assets,
                       production, composition, production_world)
server/alembic/        migrations (head: 0017_m16_intra_shot_consequences)
workflows/             ComfyUI workflow contracts (M4/M5)
data/                  runtime SQLite db, blobs, staging, tmp (gitignored)
tests/                 test suite (milestone proof maps + hygiene gates)
scripts/               proof-map/boundary/audit validators + live gates
docs/                  plans, proof maps, hygiene baseline, evidence
```

### Package versioning note

The `soloring` package version in `pyproject.toml` is independent of the
milestone numbering: milestones are immutable tagged baselines
(`M7`…`M15`), and the package semver is **deliberately left at 0.1.0**
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
