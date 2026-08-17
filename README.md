# SoloRing

Local-first creative generation loop: create a project → define a shot →
attach references → generate candidate takes → inspect → approve one →
reproduce any historical generation later.

Status: **v0.2 milestone M6 (Feature-Film Continuity Foundation) COMPLETE.**
M0 through M5 closed v0.1 (execution pipeline, durable provenance, ComfyUI
binding — suite 686/686 ×2 after the three audit passes documented in
`docs/AUDIT_REMEDIATION.md`). M6 adds the continuity layer on top: a
persistent Story World (CreativeEntities with immutable, kind-specific
design revisions and explicit approved revisions), narrative structure
(Sequences → Scenes → ordered Shots), Shot semantic dependencies on entity
identity, capture-time approved-revision resolution, immutable v1/v2
ShotRevisions with a deterministic `continuity_spec_hash`, historical
continuity provenance endpoints, and an Exact Rerun product path whose
execution never follows current Story World state. Suite 765/765 ×2;
see `docs/EXECUTOR_PROFILE.md` for the live deployment contract.

## Layout (plan §4)

```
apps/web/              Next.js frontend (project/shot editors, Story World,
                       narrative structure, semantic dependencies)
server/soloring/       Python package (api, db, domain, continuity,
                       narrative, generation, executors, worker, assets)
server/alembic/        migrations
workflows/             ComfyUI workflow contracts (M4/M5)
data/                  runtime SQLite db, blobs, staging, tmp (gitignored)
tests/                 test suite
scripts/               diagnostics + live gates
docs/                  plans, audit remediation, executor profile, evidence
```

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
