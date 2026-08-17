# SoloRing

Local-first creative generation loop. v0.1 implements one complete loop:
create a project → define a shot → attach references → generate candidate
takes → inspect → approve one → reproduce any historical generation later.

Status: **SoloRing v0.1 COMPLETE — M0 through M5 closed (686/686 ×2).** M0–M4 and
M5A were reopened by a source-level audit (fifteen findings: unfenced
publication, snapshot-incoherent revision capture, blob-path integrity,
frontend occurrence identity, cancellation TOCTOU, containment prefix,
unbounded hashing, parse/hash races, captured-bytes coherence, binding
validation, subfolder loss, recovery prework, readiness model, history
tolerance, queue starvation). The fifteen first-pass findings, the eight second-pass composition
findings (R1–R8), and the four third-gate blockers are fixed with dedicated regression tests — see
`docs/AUDIT_REMEDIATION.md`. All re-gates passed; see the executor profile
for the live deployment contract.

## Layout (plan §4)

```
apps/web/              Next.js frontend (scaffold; UI lands in M2)
server/soloring/       Python package (api, db, worker, assets, ...)
server/alembic/        migrations
workflows/             ComfyUI workflow contracts (M4/M5)
data/                  runtime SQLite db, blobs, staging, tmp (gitignored)
tests/                 test suite
scripts/               diagnostics
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
