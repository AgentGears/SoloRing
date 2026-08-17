# SoloRing v0.1 Implementation Plan

## 1. Product Objective

SoloRing v0.1 implements one complete local creative loop:

> **Create a project → define a shot → attach references → generate candidate takes → inspect them → approve one → reproduce any historical generation later.**

The release is deliberately:

* single-user
* local-first
* one authoritative generation-worker role
* one dedicated ComfyUI instance
* one video-generation workflow
* durable across browser, API, and worker restarts
* independent of model/executor details at the creative-state layer

The governing architecture is:

```text
Mutable Shot Working State
          ↓
Immutable ShotRevision
          ↓
Immutable Generation Request
          ↓
Durable SQLite Queue
          ↓
Authoritative Worker
          ↓
GenerationExecutor
          ↓
Logical Workflow Specification
          ↓
Executor Materialization
          ↓
Model Execution
          ↓
Durable Blob + Asset Provenance
          ↓
Candidate Take
          ↓
Explicit Canon
```

The architectural rule is:

> **Creative state points downward into execution infrastructure. Execution infrastructure never defines creative state.**

---

# 2. Hard Development Gate

The first complete implementation uses `FakeExecutor`.

`ComfyExecutor` must not be implemented until three FakeExecutor gates pass:

### Gate A — Happy path

```text
Project
→ Shot + References
→ Generate
→ ShotRevision
→ Generation
→ Queue
→ Worker
→ FakeExecutor
→ Staging
→ Blob + Asset
→ Take
→ SSE
→ Review
→ Approve
```

### Gate B — Ownership and recovery

The system must prove:

* singleton lease acquisition
* lease refresh
* lease loss
* zombie-worker rejection
* stale Generation adoption
* active-job recovery
* cancellation persistence
* shutdown without destroying recoverable external work

### Gate C — Import idempotency and crash safety

The system must prove:

* import retry
* crash during import
* duplicate output prevention
* Blob deduplication
* Take deduplication
* Asset deduplication for repeated import of the same output event
* staging recovery

These are **hard gates**.

No Comfy integration begins until all three pass.

---

# 3. Technology Baseline

## Frontend

```text
Next.js
React
TypeScript
```

## Backend

```text
Python
FastAPI
Pydantic
Pydantic Settings
SQLAlchemy 2.x
Alembic
aiosqlite
SQLite
```

Normal application sessions:

```python
async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)
```

Use explicit eager loading where required.

Do not rely on implicit lazy-loading in async request handlers.

## Execution

```text
GenerationExecutor
├── FakeExecutor
└── ComfyExecutor
```

---

# 4. Repository Layout

```text
soloring/
├── apps/
│   └── web/
│
├── server/
│   ├── soloring/
│   │   ├── api/
│   │   ├── db/
│   │   ├── domain/
│   │   ├── assets/
│   │   ├── generation/
│   │   ├── executors/
│   │   ├── workflows/
│   │   ├── worker/
│   │   │   ├── ownership.py
│   │   │   ├── recovery.py
│   │   │   ├── runtime.py
│   │   │   └── process.py
│   │   └── settings.py
│   │
│   ├── alembic/
│   └── alembic.ini
│
├── workflows/
│   └── hunyuan_i2v_v1/
│       ├── workflow.json
│       ├── manifest.json
│       └── README.md
│
├── COMFYUI_VERSION
│
├── data/
│   ├── blobs/
│   ├── staging/
│   ├── tmp/
│   └── soloring.db
│
├── Procfile
└── tests/
```

Development processes:

```text
web:    uvicorn soloring.api.main:app --reload
worker: python -m soloring.worker
```

The generation worker never runs inside FastAPI.

---

# 5. v0.1 Scope

## Included

* Projects
* Shots
* centralized Shot numbering
* mutable Shot working state
* managed reference uploads
* ordered mutable ShotReferences
* immutable ShotRevisions
* immutable Generation requests
* immutable Blobs
* provenance-specific Assets
* Blob byte deduplication
* durable SQLite generation queue
* centralized Generation numbering
* ephemeral per-process worker IDs
* singleton worker lease
* per-Generation worker ownership
* ownership-fenced mutations
* worker lease heartbeat
* subordinate Generation heartbeat
* unconditional stale-work reconciliation after successful lease authority
* persisted cancellation requests
* state-specific takeover recovery
* idempotent output import
* deterministic output identities
* FakeExecutor
* one ComfyUI workflow
* one active SoloRing Generation per Comfy instance
* candidate Takes
* Review grid
* Solo View
* explicit approval/rejection
* provenance inspection
* exact logical rerun
* SSE progress
* recovery manifests
* manual Blob garbage collection

## Excluded

* Director
* Scenes
* screenplay model
* Characters
* Locations
* LoRA
* cloud execution
* multiple execution providers
* multiple authoritative generation workers
* parallel Comfy execution
* model routing
* authentication
* multi-user support
* Redis
* Postgres
* Celery/RQ
* timeline editing
* audio production
* vector search
* Asset deletion UI
* automatic GC
* mandatory thumbnails
* advanced generation parameter UI
* prompt-profile framework

---

# 6. Temporal Domain Model

```text
Project
│
├── Asset[]
│    │
│    └── Blob
│
└── Shot
     ├── Mutable Working Intent
     ├── ShotReference[]
     ├── approved_take_id
     │
     └── ShotRevision[]
           │
           └── Generation[]
                 ├── GenerationInput[]
                 │
                 └── Take[]
                       │
                       └── Asset[]
                             │
                             └── Blob
```

Historical state is predominantly append-only.

Mutable state is primarily limited to:

* Shot working fields
* ShotReference set/order
* `shots.approved_take_id`
* Take rejection timestamp
* Generation lifecycle metadata
* cancellation-request metadata
* worker ownership metadata

---

# 7. Core Semantic Distinctions

## Shot

Current editable creative working state.

## ShotRevision

Immutable snapshot of the complete creative state actually rendered.

## Generation

Immutable durable execution request plus mutable lifecycle state.

## GenerationInput

Immutable historical execution-input binding.

## Take

A candidate creative result.

## Asset

One explicit provenance event.

## Blob

Immutable physical bytes identified by SHA-256.

## Worker lease

Authority to act as SoloRing's generation worker.

## Worker ID

Ephemeral identity of one specific worker process incarnation.

## Canon

```text
shots.approved_take_id
```

Generation never changes canon automatically.

---

# 8. Worker Identity Policy

Every worker process generates a fresh ID exactly once at process startup:

```python
worker_id = str(uuid.uuid4())
```

`worker_id` is:

* not configurable
* not loaded from environment
* not persisted across restarts
* not derived from hostname
* not derived from PID
* not derived from machine identity

A restarted process always gets a different worker ID.

This is deliberate.

```text
worker lease name
= stable singleton role

worker_id
= ephemeral process incarnation
```

Example:

```text
generation-worker
    ↓
worker_id = 4722c...
```

After restart:

```text
generation-worker
    ↓
worker_id = a19e1...
```

Even if the same executable restarts on the same machine.

Readable diagnostic metadata such as hostname or PID may be logged separately but must never substitute for `worker_id`.

---

# 9. Worker Process Exit Semantics

Worker termination distinguishes clean deauthorization from unexpected failure.

## Clean shutdown

Examples:

* lease ownership lost
* explicit normal process termination
* another authoritative worker has taken over

Exit:

```text
0
```

or another explicitly documented clean-shutdown code.

## Fatal unexpected failure

Examples:

* unrecoverable runtime exception
* corrupted worker initialization
* internal invariant violation

Exit:

```text
non-zero
```

This allows process supervisors to distinguish:

```text
clean lease-loss exit
```

from:

```text
unexpected worker crash
```

A worker that loses authority does not report itself as crashed.

---

# 10. ShotIntent

Use:

```python
class ShotIntent(BaseModel):
    subject: str
    action: str | None = None
    environment: str | None = None
    framing: str | None = None
    camera_motion: str | None = None
    lens: str | None = None
    mood: str | None = None
    duration_ms: int | None = None
```

Persistent creative duration uses integer milliseconds.

```text
5000 ms = 5.0 seconds
```

`ShotIntent` never contains:

```text
steps
CFG
sampler
scheduler
denoise
model-specific strengths
workflow node IDs
executor filenames
filesystem paths
```

---

# 11. ShotRevision Semantics

A ShotRevision captures the **complete creative state actually used for rendering**.

It includes:

1. structured ShotIntent
2. ordered reference identities

Changing any of these creates a new ShotRevision:

* subject
* action
* environment
* framing
* camera motion
* lens
* mood
* duration
* reference Asset identity
* reference Blob identity
* reference role
* reference ordering

Therefore:

```text
same text + different reference
→ different ShotRevision
```

and:

```text
same text + same references + same order
→ same ShotRevision
```

---

# 12. ShotRevision Snapshot

Canonical shape:

```json
{
  "schema_version": 1,
  "intent": {
    "subject": "Eva",
    "action": "enters the lobby",
    "environment": "hotel lobby",
    "framing": "medium wide",
    "camera_motion": "slow push-in",
    "lens": "50mm",
    "mood": "restrained unease",
    "duration_ms": 5000
  },
  "references": [
    {
      "asset_id": "123e4567-e89b-12d3-a456-426614174000",
      "blob_hash": "abc123...",
      "role": "reference",
      "position": 0
    }
  ]
}
```

UUIDs use lowercase canonical UUID form.

Optional fields remain present as:

```json
null
```

References are sorted deterministically by:

```text
role
position
asset_id
```

before serialization.

---

# 13. Canonical Serialization

Use exactly one serializer:

```python
def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
```

Revision:

```python
snapshot_bytes = canonical_json_bytes(snapshot)

snapshot_json = snapshot_bytes.decode("utf-8")
snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
```

The exact stored bytes are the exact hashed bytes.

---

# 14. Domain Enums

```python
class AssetKind(str, Enum):
    REFERENCE = "reference"
    OUTPUT = "output"


class GenerationOperation(str, Enum):
    GENERATE = "generate"
    RERUN = "rerun"


class GenerationStatus(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    SUBMITTED = "submitted"
    RUNNING = "running"
    IMPORTING = "importing"

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
```

Persisted enum values are mirrored by database constraints.

---

# 15. SQLite Configuration

Required:

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
PRAGMA synchronous=NORMAL;
```

Relevant connection-local PRAGMAs are applied on every new connection.

Log:

```python
sqlite3.sqlite_version
```

at startup.

Favor predictable connection semantics over pool optimization.

A small pool or `NullPool` is acceptable.

---

# 16. Timestamp Policy

All timestamps are UTC.

Ownership-critical timestamps are generated by SQLite.

Use a single subsecond expression:

```sql
strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
```

Use the same representation for:

* lease acquisition
* lease heartbeat
* Generation claim
* Generation heartbeat
* adoption
* cancellation requests
* lifecycle timestamps
* stale comparisons

Do not mix:

```text
Python local timestamps
Python UTC timestamps
SQLite CURRENT_TIMESTAMP
subsecond SQLite timestamps
```

inside ownership-critical paths.

---

# 17. Timing Defaults

Initial configurable values:

```text
worker_lease_ttl_seconds = 30
worker_lease_refresh_interval_seconds = 5

generation_heartbeat_interval_seconds = 5
generation_heartbeat_stale_seconds = 30

worker_poll_interval_seconds = 1
sse_poll_interval_seconds = 2
```

Thresholds must remain comfortably larger than normal refresh cadence.

---

# 18. Blocking File Work vs Heartbeats

Long-running:

* Blob hashing
* media probing
* large staging copy
* executor output copy
* filesystem validation

must not block the event loop long enough to cause false worker staleness.

Use:

```python
await asyncio.to_thread(...)
```

or an explicitly controlled thread executor for blocking CPU/filesystem work.

Ownership heartbeat loops remain:

* pure async
* short
* DB-focused
* independent of long file operations

The worker must be able to continue lease renewal while large media files are being hashed or copied.

---

# 19. Projects Schema

```text
projects

id              UUID PK
name            TEXT NOT NULL
description     TEXT NULL

created_at      TEXT NOT NULL
updated_at      TEXT NOT NULL
deleted_at      TEXT NULL
```

Projects use soft deletion.

---

# 20. Shots Schema

```text
shots

id                   UUID PK
project_id           UUID NOT NULL
shot_number          INTEGER NOT NULL

title                TEXT NULL
subject              TEXT NOT NULL
action               TEXT NULL
environment          TEXT NULL
framing              TEXT NULL
camera_motion        TEXT NULL
lens                 TEXT NULL
mood                 TEXT NULL
duration_ms          INTEGER NULL

approved_take_id     UUID NULL

created_at           TEXT NOT NULL
updated_at           TEXT NOT NULL
deleted_at           TEXT NULL

UNIQUE(project_id, shot_number)
CHECK(duration_ms IS NULL OR duration_ms >= 0)
```

---

# 21. Shot Number Allocation

All Shot creation goes through:

```python
ShotService.create_shot(...)
```

Within one write transaction:

```text
MAX(shot_number including soft-deleted Shots)
+ 1
```

Shot numbers are never reused.

A soft-deleted Shot therefore still reserves its historical number.

The unique constraint remains the final concurrency guard.

---

# 22. ShotReferences Schema

```text
shot_references

shot_id              UUID NOT NULL
asset_id             UUID NOT NULL

role                  TEXT NOT NULL
position              INTEGER NOT NULL

created_at            TEXT NOT NULL

PRIMARY KEY(shot_id, asset_id, role)

UNIQUE(shot_id, role, position)

CHECK(position >= 0)
```

Positions are:

* zero-based
* contiguous
* server assigned

The same Asset may not appear twice under the same role.

Reference replacement/reordering occurs atomically.

Preferred API:

```text
PUT /shots/{shot_id}/references
```

---

# 23. ShotRevisions Schema

```text
shot_revisions

id                   UUID PK
shot_id              UUID NOT NULL
revision_number      INTEGER NOT NULL

snapshot_json        TEXT NOT NULL
snapshot_hash        TEXT NOT NULL

created_at           TEXT NOT NULL

UNIQUE(shot_id, revision_number)
UNIQUE(shot_id, snapshot_hash)
```

The second constraint is required for concurrent identical Generate requests.

Creation:

```text
build snapshot
↓
hash
↓
SELECT by shot_id + snapshot_hash
↓
existing?
├─ yes → reuse
└─ no  → allocate revision_number + INSERT
                ↓
          unique race conflict?
                ↓
          fetch winning revision
```

Concurrent identical creative state must converge on one ShotRevision.

---

# 24. Blobs Schema

```text
blobs

hash                   TEXT PK
path                   TEXT NOT NULL UNIQUE
size_bytes             INTEGER NOT NULL
detected_media_type    TEXT NULL
created_at             TEXT NOT NULL
```

Blob identity derives only from physical bytes.

---

# 25. Assets Schema

```text
assets

id                    UUID PK
project_id            UUID NOT NULL
take_id               UUID NULL

blob_hash             TEXT NOT NULL
kind                  TEXT NOT NULL

upload_mime_type      TEXT NULL
original_filename     TEXT NULL

width                 INTEGER NULL
height                INTEGER NULL
duration_ms           INTEGER NULL
fps                   REAL NULL

created_at            TEXT NOT NULL

FOREIGN KEY(blob_hash)
    REFERENCES blobs(hash)
    ON DELETE RESTRICT

CHECK(kind IN ('reference', 'output'))
```

One Take may own multiple Assets.

---

# 26. Blob vs Asset Invariant

> **Blob identity derives from bytes. Asset identity derives from provenance.**

Example:

```text
Asset 17 ─┐
          ├── Blob abc123
Asset 41 ─┘
```

Every explicit import creates a new Asset.

Every newly imported Generation output creates a new Asset for that output event.

Only physical bytes deduplicate.

---

# 27. GenerationInputs Schema

```text
generation_inputs

generation_id         UUID NOT NULL
asset_id              UUID NOT NULL

input_key             TEXT NOT NULL
reference_role        TEXT NULL
position              INTEGER NOT NULL
blob_hash             TEXT NOT NULL

PRIMARY KEY(generation_id, input_key, position)

CHECK(position >= 0)
```

`input_key` is workflow-semantic:

```text
reference_image
first_frame
last_frame
source_video
mask
```

`reference_role` is creative-semantic:

```text
reference
character
environment
style
```

These concepts remain distinct.

---

# 28. Deterministic GenerationInput Mapping

Given:

```text
ShotRevision
+
Workflow Manifest
```

Generation creation must always derive the same ordered GenerationInput set.

For identical inputs:

```text
(input_key,
 reference_role,
 position,
 asset_id,
 blob_hash)
```

must be identical.

The mapping logic belongs to one deterministic function.

Conceptually:

```python
def resolve_generation_inputs(
    revision: ShotRevisionSnapshot,
    manifest: WorkflowManifest,
) -> list[ResolvedGenerationInput]:
    ...
```

It must not depend on:

* database row iteration order
* filesystem order
* arbitrary dictionary order
* current ShotReferences after Generation creation

---

# 29. Takes Schema

```text
takes

id                   UUID PK
shot_id              UUID NOT NULL
generation_id        UUID NOT NULL

output_key           TEXT NOT NULL
label                TEXT NULL

rejected_at          TEXT NULL
created_at           TEXT NOT NULL

UNIQUE(generation_id, output_key)
```

`output_key` deterministically identifies one logical candidate output.

Examples:

```text
video:0
video:1
preview:0
```

This enables import idempotency.

---

# 30. Worker Leases Schema

```text
worker_leases

name             TEXT PK
worker_id        TEXT NOT NULL

acquired_at      TEXT NOT NULL
heartbeat_at     TEXT NOT NULL
```

v0.1 uses:

```text
name = "generation-worker"
```

The stable identity is the lease name.

The worker ID is ephemeral.

---

# 31. Generations Schema

```text
generations

id                       UUID PK
shot_id                  UUID NOT NULL
shot_revision_id         UUID NOT NULL

generation_number        INTEGER NOT NULL

status                   TEXT NOT NULL
operation                TEXT NOT NULL
executor                 TEXT NOT NULL

workflow_id              TEXT NOT NULL
workflow_version         INTEGER NOT NULL
workflow_template_hash   TEXT NOT NULL
manifest_hash            TEXT NOT NULL

model                    TEXT NULL
model_version            TEXT NULL

compiled_prompt          TEXT NOT NULL
negative_prompt          TEXT NULL
prompt_compiler_version  TEXT NOT NULL

seed                     INTEGER NULL
parameters_json          TEXT NOT NULL

workflow_spec_json       TEXT NOT NULL
workflow_spec_hash       TEXT NOT NULL

executor_submission_json TEXT NULL
executor_submission_hash TEXT NULL

executor_job_id          TEXT NULL
executor_handle_json     TEXT NULL

rerun_of_generation_id   UUID NULL

claimed_at               TEXT NULL
heartbeat_at             TEXT NULL
worker_id                TEXT NULL

progress_current         INTEGER NULL
progress_total           INTEGER NULL
current_node             TEXT NULL

cancel_requested_at      TEXT NULL
cancel_reason            TEXT NULL

error_code               TEXT NULL
error_message            TEXT NULL
error_details_json       TEXT NULL

created_at               TEXT NOT NULL
queued_at                TEXT NOT NULL
started_at               TEXT NULL
completed_at             TEXT NULL

UNIQUE(shot_id, generation_number)
```

`prompt_compiler_version` is mandatory and non-nullable from the first migration.

---

# 32. Generation Constraints and Indexes

```text
CHECK(operation IN (
    'generate',
    'rerun'
))
```

```text
CHECK(status IN (
    'queued',
    'preparing',
    'submitted',
    'running',
    'importing',
    'succeeded',
    'failed',
    'interrupted',
    'cancelled'
))
```

Indexes:

```sql
CREATE INDEX ix_generations_queue
ON generations(status, queued_at);
```

```sql
CREATE INDEX ix_generations_active_recovery
ON generations(status, heartbeat_at);
```

```sql
CREATE INDEX ix_generations_worker_active
ON generations(worker_id, status, heartbeat_at);
```

---

# 33. Generation Number Allocation

All Generation creation passes through:

```python
GenerationService.create_generation(...)
```

Inside one transaction:

```text
MAX(generation_number for Shot)
+ 1
```

Generation numbers are never reused.

If Generations later become soft-deletable, deleted rows still reserve their historical number.

Example:

```text
Generation 1 → generate
Generation 2 → generate
Generation 3 → rerun of 1
Generation 4 → generate
```

Numbering does not encode lineage.

---

# 34. Large Generation Fields

Defer:

```text
workflow_spec_json
executor_submission_json
error_details_json
```

when appropriate.

For example:

```python
workflow_spec_json: Mapped[str] = mapped_column(
    Text,
    deferred=True,
)
```

Queue/status/list endpoints must not load large graph payloads.

---

# 35. Prompt Compiler

Pure function:

```python
def compile_prompt(intent: ShotIntent) -> str:
    ...
```

Requirements:

* deterministic
* synchronous
* no DB
* no filesystem
* no network
* no LLM
* no hidden mutable global configuration

Persist:

```text
compiled_prompt
negative_prompt
prompt_compiler_version
```

Changing compiler behavior requires a new version.

---

# 36. Workflow Manifest

The manifest defines:

* logical inputs
* cardinality
* parameter mappings
* parameter types
* validation
* defaults
* expected outputs
* expected media kind
* deterministic output identities

Example:

```json
{
  "id": "hunyuan_i2v",
  "version": 1,

  "inputs": {
    "reference_image": {
      "node": "4",
      "field": "image",
      "kind": "image",
      "required": true,
      "source_role": "reference",
      "cardinality": 1
    },

    "prompt": {
      "node": "12",
      "field": "text",
      "kind": "string",
      "required": true
    }
  },

  "parameters": {
    "steps": {
      "node": "31",
      "field": "steps",
      "type": "int",
      "default": 30,
      "min": 1,
      "max": 100
    },

    "cfg": {
      "node": "31",
      "field": "cfg",
      "type": "float",
      "default": 7.0,
      "min": 0.0,
      "max": 30.0
    }
  },

  "outputs": {
    "video": {
      "node": "15",
      "field": "gifs",
      "kind": "video",
      "expected_count": 1,
      "output_key_prefix": "video"
    }
  }
}
```

No reference is silently ignored.

If cardinality is wrong, Generation creation fails.

---

# 37. Parameter Resolution

Supported:

```text
int
float
string
bool
```

Resolution:

```text
manifest defaults
      ↓
optional internal overrides
      ↓
type validation
      ↓
range validation
      ↓
parameters_json
```

Normal v0.1 UI supplies no overrides.

---

# 38. Logical Workflow Specification

The durable logical execution artifact includes its own schema version.

Example:

```json
{
  "schema_version": 1,
  "workflow_id": "hunyuan_i2v",
  "workflow_version": 1,
  "inputs": {
    "reference_image": {
      "asset_id": "...",
      "blob_hash": "..."
    }
  },
  "prompt": "...",
  "seed": 12345,
  "parameters": {
    "steps": 30,
    "cfg": 7.0
  }
}
```

Persist:

```text
workflow_spec_json
workflow_spec_hash
```

Canonicalization uses the same deterministic JSON serializer.

The logical specification must not contain:

* absolute local paths
* staging paths
* temporary Comfy filenames
* transient executor filesystem state

---

# 39. Executor Submission Artifact

Executor-specific materialization is stored separately:

```text
executor_submission_json
executor_submission_hash
```

For ComfyUI this may contain uploaded temporary filenames.

It is useful for debugging and executor provenance, but it is not the durable logical execution identity.

---

# 40. Exact Rerun

Exact Rerun recreates the historical logical execution request:

* ShotRevision
* GenerationInputs
* Blob hashes
* compiled prompt
* compiler version
* parameter values
* seed
* workflow ID/version
* template hash
* manifest hash
* logical workflow specification
* model/version

It does not promise bit-identical output if:

* model bytes changed
* runtime changed
* hardware changed
* kernel implementation changed
* executor changed
* scheduler implementation changed

Exact means:

> **same durable execution specification, not guaranteed same output bytes.**

---

# 41. Generation Creation

```text
POST /shots/{shot_id}/generations
```

Flow:

```text
validate Shot
      ↓
resolve ordered ShotReferences
      ↓
validate workflow cardinality
      ↓
build canonical ShotRevision snapshot
      ↓
hash
      ↓
reuse/create ShotRevision
      ↓
resolve deterministic GenerationInputs
      ↓
verify Asset + Blob rows/files
      ↓
compile prompt
      ↓
resolve parameters
      ↓
build versioned logical workflow spec
      ↓
canonicalize + hash
      ↓
allocate generation_number
      ↓
create Generation(status=queued)
      ↓
create GenerationInput rows
      ↓
commit
```

Return:

```text
202 Accepted
```

No model execution occurs in the API request.

---

# 42. Asset Upload

```text
POST /projects/{project_id}/assets
```

Uploads are streamed.

Forbidden:

```python
await file.read()
```

Required:

```python
while True:
    chunk = await file.read(settings.upload_chunk_bytes)
    if not chunk:
        break

    total += len(chunk)

    if total > settings.max_upload_bytes:
        raise UploadTooLarge()

    hasher.update(chunk)
    staging_file.write(chunk)
```

Default:

```text
1 MiB chunks
```

---

# 43. Upload Storage Sequence

```text
temp file in data/tmp/
      ↓
stream
      ↓
SHA-256
      ↓
size enforcement
      ↓
media detection
      ↓
derive final Blob path
      ↓
target exists?
├─ yes → discard temp
└─ no  → atomic rename
      ↓
insert/reuse Blob row
      ↓
always create new Asset
```

No database transaction remains open while bytes are being uploaded.

---

# 44. Concurrent Duplicate Upload

Expected result:

```text
two concurrent identical uploads
       ↓
same SHA-256
       ↓
one final Blob
       ↓
two distinct Assets
```

Unique Blob identity plus atomic final placement prevents corruption.

---

# 45. Blob Storage

```text
data/blobs/sha256/
  aa/
    bb/
      <full-hash>
```

All derivation:

```python
blob_store.path_for_hash(blob_hash)
```

No API handler accepts arbitrary paths.

---

# 46. Blob Serving

```text
GET /blobs/{prefix1}/{prefix2}/{hash}
```

Requirements:

```text
hash = exactly 64 lowercase hex chars
prefix1 == hash[0:2]
prefix2 == hash[2:4]
```

Malformed:

```text
400
```

Unknown Blob:

```text
404
```

Registered row with missing file:

```text
404
+
integrity error log
```

Content type:

```python
blob.detected_media_type or "application/octet-stream"
```

---

# 47. HTTP Range

Video playback requires Range support.

Test:

```http
Range: bytes=0-1023
```

Expected:

```text
206 Partial Content
Content-Range
Accept-Ranges: bytes
```

Also test:

* no range
* invalid range
* range past EOF
* HEAD
* real browser scrubbing

---

# 48. Ownership Architecture

```text
Stable Lease Role
"generation-worker"
       ↓
Ephemeral worker_id
"this process incarnation"
       ↓
Generation.worker_id
"this process owns this active job"
       ↓
Worker-Originated Mutations
```

The Generation ownership layer is subordinate to lease ownership.

---

# 49. Ownership Module

All fencing logic lives in:

```text
soloring/worker/ownership.py
```

It exposes full atomic operations:

```python
acquire_worker_lease(...)
refresh_worker_lease(...)
claim_next_generation(...)
heartbeat_owned_generation(...)
update_owned_generation_progress(...)
transition_owned_generation(...)
persist_owned_executor_handle(...)
adopt_stale_generation(...)
requeue_stale_preparing_generation(...)
```

Ownership-critical helpers own their own transactions.

They do **not** accept an externally managed `AsyncSession` for the critical transaction.

Higher layers never manually compose:

```text
lease SELECT
+
Generation UPDATE
```

---

# 50. Ownership Transaction Pattern

Preferred low-level implementation:

```python
async with engine.connect() as conn:
    await conn.exec_driver_sql("BEGIN IMMEDIATE")

    try:
        ...
        await conn.execute(...)
        ...
        await conn.exec_driver_sql("COMMIT")

    except Exception:
        await conn.exec_driver_sql("ROLLBACK")
        raise
```

The exact SQLAlchemy configuration must be proven in tests early.

Invariant:

```text
one checked-out connection
one BEGIN IMMEDIATE
authority check
protected mutation
COMMIT
```

No critical ownership operation may span multiple pooled connections.

---

# 51. Negative Connection-Safety Test

The test suite must demonstrate why the helper boundary exists.

Add a test that deliberately attempts:

```text
connection A
→ verify lease

connection B
→ protected Generation update
```

and verifies that this composition is either:

* impossible through the ownership API, or
* demonstrably fails the intended atomic safety property

The production code must make this misuse structurally difficult.

---

# 52. Lease Acquisition

Inside one `BEGIN IMMEDIATE`:

```text
lease missing
→ insert current worker_id

same worker_id already owner
→ refresh

another worker owns lease + stale
→ replace worker_id

another worker owns lease + fresh
→ acquisition denied
```

All stale calculations use database time.

---

# 53. Lease Acquisition Result

Result taxonomy should distinguish:

```text
ACQUIRED_NEW
REFRESHED_SELF
TAKEN_OVER
HELD_BY_OTHER
```

The distinction may be useful diagnostically.

However, reconciliation behavior does not depend on which successful branch occurred.

---

# 54. Unconditional Reconciliation Rule

After **every successful lease-authority cycle**, run stale-active-Generation reconciliation.

This applies when lease authority resulted from:

```text
fresh insertion
refresh-as-self
stale takeover
```

Sequence:

```text
acquire or refresh singleton lease
        ↓
authority confirmed?
   ├─ no → standby/backoff
   └─ yes
        ↓
scan stale active Generations
        ↓
reconcile them
        ↓
continue owned work / claim queue
```

Reconciliation is defensive and unconditional.

It is not limited to explicit takeover.

The indexed recovery query makes this cheap in steady state.

---

# 55. Standby Worker Behavior

If another fresh process owns the lease:

```text
do not process jobs
do not crash-loop
sleep/backoff
attempt acquisition again
```

A standby process may automatically become authoritative after lease expiry.

---

# 56. Lease Refresh

Conditional update:

```sql
UPDATE worker_leases
SET heartbeat_at = :db_now
WHERE name = 'generation-worker'
  AND worker_id = :worker_id;
```

Result:

```text
1 row → retained
0 rows → lost
```

---

# 57. Lease Loss Behavior

A worker that loses authority must:

1. stop claiming
2. stop Generation heartbeat
3. stop progress writes
4. stop lifecycle writes
5. stop external-handle persistence
6. detach observation
7. exit cleanly

It must **not** cancel running external execution.

Recoverable work belongs to the next authoritative worker.

---

# 58. Ownership-Fenced Mutations

All worker-originated active Generation mutations verify:

```text
current singleton lease owned by worker_id
AND
generation.worker_id == worker_id
```

inside the same transaction.

This includes:

* heartbeat
* progress
* current node
* external job handle
* status transition
* error details
* cancellation completion
* import lifecycle
* terminal transition

---

# 59. Coupled Generation Heartbeat

Generation heartbeat is not an independent peer mechanism.

It is one fenced mutation.

Conceptually:

```text
BEGIN IMMEDIATE
↓
verify lease still belongs to worker
↓
verify Generation belongs to worker
↓
verify Generation active
↓
refresh Generation heartbeat
↓
COMMIT
```

Result taxonomy:

```python
class OwnershipMutationResult(str, Enum):
    OK = "ok"
    LEASE_LOST = "lease_lost"
    GENERATION_OWNERSHIP_LOST = "generation_ownership_lost"
    GENERATION_NOT_ACTIVE = "generation_not_active"
    NOT_FOUND = "not_found"
```

A process that loses the lease cannot artificially keep a Generation fresh.

---

# 60. Queue Claim

Queue ordering:

```text
status = queued
ORDER BY queued_at
```

Claim transaction:

```text
BEGIN IMMEDIATE
↓
verify singleton lease
↓
select oldest queued
↓
conditional update:
    status = preparing
    worker_id = current worker
    claimed_at = now
    heartbeat_at = now
↓
COMMIT
```

SQLite ≥3.35 may use `RETURNING`.

Fallback uses explicit select/update/select inside the same transaction.

---

# 61. Queue Claim Capability

Startup detects:

```python
sqlite3.sqlite_version
```

Policy:

```text
SQLite >= 3.35
→ RETURNING

older
→ fallback
```

Packaged environments should pin the Python/runtime version.

---

# 62. Recovery Candidate Query

Recovery candidates:

```text
status IN (
    preparing,
    submitted,
    running,
    importing
)

AND heartbeat_at stale
AND worker_id != current worker_id
```

Because every process gets a fresh worker ID, Generations owned by a previous process incarnation remain clearly distinguishable.

---

# 63. Recovery Ordering

After every successful lease-authority cycle:

```text
confirm lease authority
      ↓
scan stale active Generations
      ↓
reconcile/adopt/requeue/finalize
      ↓
claim new queued work
```

Fresh queue work never takes precedence over unresolved stale active work.

---

# 64. Recovery — `preparing`

`preparing` means claimed but no durable confirmed external submission.

For FakeExecutor:

```text
stale preparing
+ no external handle
→ queued
```

Preserve:

```text
queued_at
```

Reset:

```text
status = queued
worker_id = NULL
claimed_at = NULL
heartbeat_at = NULL
```

A worker crash never moves the request behind newer queue entries.

---

# 65. Comfy `preparing` Ambiguity Rule

There is an unavoidable crash window:

```text
submit request sent
      ↓
Comfy accepts job
      ↓
worker crashes
      ↓
external handle never persisted
```

Therefore:

> **When SoloRing cannot determine whether external work was submitted, prefer `interrupted` over possible duplicate submission.**

Safe cases:

```text
stale preparing
+ no handle
+ dedicated Comfy clearly idle
→ requeue
```

Ambiguous:

```text
stale preparing
+ no handle
+ unknown active/queued Comfy work
→ reconcile if possible
→ otherwise interrupted
```

Never blindly resubmit an ambiguous expensive job.

---

# 66. Recovery — `submitted` / `running`

Use durable executor handle.

Possible states:

### Active externally

Atomically adopt:

```text
old worker_id
→ current worker_id
heartbeat refreshed
```

while verifying singleton lease.

### Succeeded externally

```text
adopt
→ importing
```

### Failed externally

```text
failed
```

### External job missing

```text
interrupted
```

---

# 67. Recovery — `importing`

Atomically adopt stale importing work.

Then:

```text
staging contains expected output?
├─ yes → resume
└─ no
    ↓
executor history recoverable?
├─ yes → restage → resume
└─ no  → interrupted
```

Import remains idempotent.

---

# 68. Generation State Machine

```text
queued
  ↓
preparing
  ↓
submitted
  ↓
running
  ↓
importing
  ↓
succeeded
```

Terminal alternatives:

```text
failed
interrupted
cancelled
```

All terminal transitions set:

```text
completed_at
```

---

# 69. Cancellation Persistence

Generations include:

```text
cancel_requested_at
cancel_reason
```

Cancellation intent survives:

* browser close
* API restart
* worker restart
* lease takeover

---

# 70. Queued Cancellation

Attempt conditional:

```text
queued → cancelled
```

If worker already claimed it, persist cancellation request for active handling.

---

# 71. Preparing Cancellation

If definitely not externally submitted:

```text
preparing → cancelled
```

If submission may have occurred, use executor-aware cancellation/reconciliation.

---

# 72. Submitted Cancellation

Attempt targeted queue removal.

If successful:

```text
submitted → cancelled
```

If execution has started, treat as running cancellation.

---

# 73. Running Cancellation

Prefer targeted cancellation.

Global Comfy interruption only when:

```text
Comfy instance explicitly exclusive to SoloRing
AND
target job confirmed active
AND
no unrelated work can be affected
```

Otherwise:

```text
409 GENERATION_NOT_CANCELLABLE
```

---

# 74. Importing Cancellation

v0.1 does not cancel after durable import begins.

```text
importing
→ 409 GENERATION_NOT_CANCELLABLE
```

---

# 75. Terminal Cancellation

For:

```text
succeeded
failed
interrupted
cancelled
```

return:

```text
409
```

---

# 76. GenerationExecutor

```python
class GenerationExecutor(ABC):

    async def submit(
        self,
        generation: GenerationExecutionSpec,
    ) -> ExecutionHandle:
        ...

    async def inspect(
        self,
        handle: ExecutionHandle,
    ) -> ExecutionState:
        ...

    async def cancel(
        self,
        handle: ExecutionHandle,
    ) -> CancelResult:
        ...

    async def fetch_outputs(
        self,
        handle: ExecutionHandle,
        manifest: WorkflowManifest,
        staging_directory: Path,
    ) -> list[StagedOutput]:
        ...
```

---

# 77. FakeExecutor

FakeExecutor is deterministic and script-driven.

Example:

```python
FakeExecutor(
    states=[
        Submitted(),
        Running(current=1, total=3),
        Running(current=2, total=3),
        Running(current=3, total=3),
        Succeeded(
            outputs=[
                FakeOutput(output_key="video:0")
            ]
        ),
    ]
)
```

Tests do not depend on real sleeps.

Use explicit state advancement or a fake clock.

---

# 78. FakeExecutor Required Scenarios

FakeExecutor must support:

* success
* failure
* cancellation accepted
* cancellation rejected
* lost external job
* multiple outputs
* missing output
* invalid output
* worker crash after submit
* worker crash before handle persistence
* lease loss while job continues
* takeover
* zombie heartbeat
* zombie progress write
* zombie lifecycle write
* import failure
* import retry

---

# 79. Output Identity

Manifest output definitions generate deterministic keys:

```text
video:0
video:1
preview:0
```

Before creating a Take:

```text
SELECT by generation_id + output_key
```

The unique constraint prevents duplicates.

---

# 80. Generation Staging

```text
data/staging/<generation-id>/
```

Example:

```text
video-0.tmp
video-1.tmp
```

Staging is:

* deterministic
* temporary
* resumable
* not referenced by Asset rows
* retained after recoverable failure
* disposable after durable success

---

# 81. Output Import

For each output:

```text
staged output
      ↓
validate expected kind
      ↓
detect media type
      ↓
extract metadata
      ↓
SHA-256
      ↓
place/reuse Blob
      ↓
BEGIN
      ↓
lookup generation_id + output_key
      ↓
already imported?
├─ yes → skip duplicate creation
└─ no
    ↓
    create Take
    create output Asset(s)
      ↓
all expected outputs durable?
      ↓
Generation → succeeded
      ↓
COMMIT
```

Asset never references staging.

---

# 82. Import Idempotency

Required invariant:

> **Repeated import of the same Generation output does not create duplicate Takes or duplicate output Assets.**

Blob byte deduplication is separate.

Example:

```text
first import video:0
→ Take A + Asset A + Blob X

retry video:0
→ recognizes existing Take/output identity
→ creates nothing new
```

---

# 83. Import Failure

If final Blob placement succeeds but DB commit fails:

```text
orphan Blob may remain
```

This is acceptable.

Prefer:

```text
unreferenced bytes
```

over:

```text
DB row pointing to missing bytes
```

---

# 84. Successful Import Cleanup

Once all expected outputs are durable and Generation becomes succeeded:

```text
staging may be deleted
```

Failure to delete staging does not roll back Generation success.

---

# 85. Comfy Deployment Model

Preferred v0.1 mode:

> **Dedicated ComfyUI instance controlled by SoloRing.**

One active SoloRing Generation at a time.

SQLite may contain many queued Generations.

---

# 86. Comfy Input Materialization

GenerationInputs remain durable Blob references.

Comfy execution may require temporary input filenames.

Flow:

```text
Blob
 ↓
upload/materialize into Comfy input storage
 ↓
receive temporary filename
 ↓
patch executor submission graph
 ↓
submit
```

Temporary names never enter the canonical logical workflow identity.

---

# 87. Executor Handles

Persist executor-agnostic identity:

```text
executor_job_id
executor_handle_json
```

Comfy:

```json
{
  "kind": "comfy",
  "prompt_id": "..."
}
```

Fake:

```json
{
  "kind": "fake",
  "job_id": "..."
}
```

Persist as soon as possible after executor submission succeeds.

---

# 88. Comfy Reconciliation

For active persisted handle:

```text
history contains job?
├─ yes → inspect result
└─ no
    ↓
queue contains job?
├─ yes → pending/running
└─ no  → interrupted
```

Comfy WebSocket state is observational.

A disconnected WebSocket never determines lifecycle truth.

---

# 89. Comfy Output Discovery

Ownership is:

```text
Generation
→ executor job ID
→ manifest output node/field
→ executor history
```

Never:

```text
latest file
filename prefix
directory mtime
global output scan
```

---

# 90. Comfy Version Pinning

Record:

```text
COMFYUI_VERSION
```

and workflow-specific tested version documentation.

Runtime health:

```text
matched
different
unknown
```

Mismatch produces warning.

---

# 91. Exact Rerun Endpoint

```text
POST /generations/{generation_id}/rerun
```

Allowed source states:

```text
succeeded
failed
interrupted
cancelled
```

Active source:

```text
409 GENERATION_ACTIVE
```

Rerun copies historical GenerationInputs exactly.

It never uses current ShotReferences.

---

# 92. Approval

Canonical source:

```text
shots.approved_take_id
```

Transaction:

```text
verify Take belongs to Shot
clear rejected_at
set approved_take_id
```

Approving an already-approved Take is idempotent.

---

# 93. Rejection

Reject unapproved:

```text
set rejected_at
```

Reject currently approved:

```text
BEGIN
clear approved_take_id
set rejected_at
COMMIT
```

No auto-promotion.

Rejecting an already rejected Take is idempotent.

---

# 94. Working State vs Canon

The API computes:

```text
current working snapshot hash
```

using the same canonical builder used during Generation creation.

Compare with:

```text
approved Take
→ Generation
→ ShotRevision.snapshot_hash
```

Return:

```json
{
  "working_snapshot_hash": "...",
  "working_state_differs_from_approved": true
}
```

Frontend does not independently reproduce comparison logic.

---

# 95. SSE Endpoint

```text
GET /generations/{generation_id}/events
```

SSE remains observational.

SQLite remains authoritative.

---

# 96. SSE Session Discipline

Required:

```text
open short session
read
close
emit
sleep
repeat
```

Never:

```text
open session
hold for entire SSE lifetime
```

Emit current state immediately on connection.

---

# 97. SSE Event Shape

Example:

```json
{
  "id": "generation-id",
  "status": "running",

  "progress_current": 12,
  "progress_total": 30,
  "current_node": "sampler",

  "cancel_requested": true,
  "cancel_requested_at": "2026-08-14T01:23:45.123Z",

  "error_code": null,
  "error_message": null,

  "updated_at": "2026-08-14T01:23:45.456Z"
}
```

`cancel_requested` is derived from:

```text
cancel_requested_at != NULL
```

This allows the UI to display:

```text
Cancellation requested…
```

while a Generation remains active.

For terminal status:

```text
emit final event
close stream
```

---

# 98. SSE Busy Handling

Default workload:

```text
~1 read / 2 sec / active viewer
≤1 progress write / sec / active Generation
```

Transient `SQLITE_BUSY` during SSE:

```text
skip current poll
retry next interval
```

Do not terminate the connection.

---

# 99. API Surface

## Projects

```text
GET    /projects
POST   /projects
GET    /projects/{id}
PATCH  /projects/{id}
DELETE /projects/{id}
```

## Shots

```text
GET    /projects/{id}/shots
POST   /projects/{id}/shots

GET    /shots/{id}
PATCH  /shots/{id}
DELETE /shots/{id}

GET    /shots/{id}/revisions
```

## References

```text
PUT /shots/{id}/references
```

## Assets

```text
POST /projects/{id}/assets
GET  /assets/{id}
```

## Generations

```text
POST /shots/{id}/generations
GET  /shots/{id}/generations

GET  /generations/{id}
GET  /generations/{id}/events

POST /generations/{id}/cancel
POST /generations/{id}/rerun
```

## Takes

```text
GET  /shots/{id}/takes

POST /takes/{id}/approve
POST /takes/{id}/reject
```

## Blobs

```text
GET /blobs/{prefix1}/{prefix2}/{hash}
```

## Recovery

```text
GET /projects/{id}/export-manifest
```

---

# 100. Stable Error Codes

Examples:

```text
PROJECT_NOT_FOUND
SHOT_NOT_FOUND
ASSET_NOT_FOUND
BLOB_NOT_FOUND

UPLOAD_TOO_LARGE
UNSUPPORTED_MEDIA_TYPE

WORKFLOW_VALIDATION_FAILED
WORKFLOW_INPUT_CARDINALITY_INVALID

GENERATION_NOT_FOUND
GENERATION_ACTIVE
GENERATION_NOT_CANCELLABLE

LEASE_LOST
GENERATION_OWNERSHIP_LOST

EXECUTOR_UNAVAILABLE
EXECUTOR_JOB_LOST

OUTPUT_MISSING
OUTPUT_INVALID

SQLITE_BUSY
```

Response:

```json
{
  "error_code": "GENERATION_NOT_CANCELLABLE",
  "message": "Generation import has already started.",
  "details": {}
}
```

---

# 101. Blob Garbage Collection

CLI:

```text
soloring gc
soloring gc --delete
```

Dry-run by default.

Eligible only when:

```text
not referenced by any Asset
AND
older than safety cutoff
AND
not part of active staging
AND
not part of active upload work
```

Initial cutoff:

```text
24 hours
```

Never delete a referenced Blob.

---

# 102. Recovery Manifest

SQLite is authoritative.

Derived manifest may contain:

* Projects
* Shots
* ShotReferences
* ShotRevisions
* GenerationInputs
* Generations
* Takes
* approval pointer
* Assets
* Blob hashes
* compiled prompts
* compiler version
* parameter values
* logical workflow spec
* workflow hashes
* executor submission hashes
* executor handles
* lineage
* errors

Manifest generation never participates in normal Generation transactions.

---

# 103. Alembic + SQLite

Use batch-mode conventions for SQLite structural changes:

```python
context.configure(
    ...,
    render_as_batch=True,
)
```

Use predictable naming conventions for constraints.

Migration tests must include populated databases.

---

# 104. Session Discipline

API:

```text
short AsyncSession per request/unit-of-work
```

SSE:

```text
short AsyncSession per poll
```

Ownership module:

```text
explicit connection
explicit BEGIN IMMEDIATE
helper owns transaction
```

Worker file/executor waits:

```text
no DB session held
```

---

# 105. Foundational Invariants

### F1. Creative state is model-independent.

### F2. ShotRevision captures complete creative state, including references.

### F3. Historical ShotRevisions are immutable.

### F4. Generation requests are immutable.

### F5. Blob identity derives from immutable bytes.

### F6. Asset identity derives from provenance.

### F7. ShotReferences are mutable; GenerationInputs are immutable.

### F8. Database state is authoritative.

### F9. SSE and executor WebSockets are observational only.

### F10. Executor success is not SoloRing success.

### F11. Canon changes only through explicit approval/rejection.

### F12. Persisted categorical domains are enum-constrained.

### F13. Canonical artifacts are versioned and deterministically serialized.

### F14. `worker_id` identifies one process incarnation and is freshly generated at startup.

### F15. Worker lease authority is stable by role; worker process identity is ephemeral.

### F16. Active Generation ownership is subordinate to singleton lease ownership.

### F17. Generation heartbeat is an ownership-fenced mutation.

### F18. A lease loser cannot keep a Generation fresh.

### F19. Every worker-originated active mutation verifies both ownership layers.

### F20. Ownership fences execute atomically on one SQLite connection and transaction.

### F21. Stale-active reconciliation runs after every successful lease-authority cycle.

### F22. Reconciliation happens before new queue claims.

### F23. Lease loss never cancels potentially recoverable external execution.

### F24. Ambiguous external submission is interrupted rather than blindly duplicated.

### F25. Blocking file work must not starve ownership heartbeats.

### F26. Import is idempotent by deterministic output identity.

### F27. Logical workflow identity contains no transient executor path.

### F28. Exact Rerun reproduces the logical execution specification, not guaranteed bytes.

### F29. Shot and Generation numbers are never reused.

### F30. Infrastructure depends on creative state, never the reverse.

---

# 106. M0 — Runtime Foundation

Build:

* repository
* Next.js
* FastAPI
* SQLAlchemy
* Alembic
* SQLite WAL
* PRAGMA configuration
* SQLite version logging
* timestamp policy
* settings
* CORS
* storage directories
* BlobStore skeleton
* upload limits
* worker entrypoint
* fresh `uuid4()` worker ID generation
* worker lease table
* ownership module skeleton
* explicit ownership transaction implementation
* lease acquire/refresh/loss
* standby behavior
* clean/fatal worker exit semantics

Required M0 tests:

* every process restart gets new worker ID
* configured hostname cannot replace worker ID
* lease acquisition succeeds in empty DB
* second worker sees fresh owner
* stale takeover works
* lease loser exits cleanly
* unexpected fatal worker error exits non-zero
* ownership helper keeps one connection for full transaction

Exit:

> Runtime, process identity, SQLite behavior, and worker authority are deterministic.

---

# 107. M1 — Temporal Domain and Storage

Build:

* Projects
* Shots
* Shot numbering
* non-reused numbering
* ShotReferences
* canonical snapshots
* ShotRevision schema version
* unique snapshot hash
* Blob storage
* Asset provenance
* streamed upload
* duplicate-byte race handling
* Generation schema
* Generation numbering
* cancellation fields
* GenerationInputs
* deterministic input mapping
* Takes with `output_key`
* recovery indexes
* enum constraints

Exit:

> Creative history, execution identities, and storage semantics are structurally complete.

---

# 108. M2 — Creative UI

Build:

* Project view
* Shot editor
* reference upload
* deterministic reference reorder
* Approved Take
* Current Working State
* snapshot hash comparison
* prompt compiler
* prompt compiler version

Exit:

> Creative working state has deterministic immutable snapshot semantics.

---

# 109. M3A — FakeExecutor Happy Path

Build:

* lazy ShotRevision reuse
* parameter resolution
* logical workflow specification
* logical workflow schema version
* Generation creation
* GenerationInput creation
* queue claim
* worker authority
* FakeExecutor success
* staging
* Blob import
* deterministic output keys
* Take creation
* SSE
* review
* approval

Hard Gate A:

> Complete FakeExecutor product path passes before proceeding.

---

# 110. M3B — Ownership, Cancellation, and Recovery

Build:

* fresh worker process IDs
* lease refresh
* unconditional reconciliation after every successful lease cycle
* fenced Generation heartbeat
* fenced progress
* fenced lifecycle
* fenced executor-handle write
* lease loss
* zombie rejection
* stale `preparing`
* active-job adoption
* importing recovery
* persisted cancellation
* Fake cancellation
* clean lease-loss shutdown without cancelling external work

Hard Gate B:

> Ownership and takeover suite passes completely.

---

# 111. M3C — Crash, Race, and Import Matrix

Exercise:

* concurrent identical Generate calls
* one ShotRevision under race
* deterministic GenerationInputs
* worker crash during preparing
* crash after Fake submit
* crash before handle persistence
* crash during running
* crash during importing
* duplicate upload race
* import failure
* import retry
* missing output
* invalid output
* stale worker after takeover
* event-loop-safe large file operation
* SQLite busy
* SSE reconnect

Hard Gate C:

> Import idempotency, race handling, and crash safety pass completely.

Only after Gates A, B, and C pass may Comfy code begin.

---

# 112. M4 — Workflow Contract

Build/harden:

* manifest schema
* manifest hash
* logical workflow schema version
* logical input identity
* deterministic GenerationInput mapping
* cardinality
* parameter validation
* output kind/count
* output keys
* Blob reference semantics
* executor materialization boundary
* prompt compiler identity
* tested Comfy version

Exit:

> Every queued Generation is a complete executor-independent execution specification.

---

# 113. M5 — ComfyExecutor

Build:

* Comfy health/version
* Blob input materialization
* executor submission graph
* prompt submission
* handle persistence
* progress observation
* queue/history reconciliation
* ambiguous stale-preparing handling
* conservative `interrupted` policy
* output lookup
* serialized execution
* targeted cancellation
* guarded global interruption

Exit:

> Comfy follows the lifecycle already proven with FakeExecutor.

---

# 114. M6 — Durable Import

Harden:

* staging
* expected-kind validation
* media probing
* hashing
* Blob reuse
* deterministic Take output identity
* retry after physical placement
* retry after DB failure
* staging recovery
* cleanup

Proof:

```text
repeat same Generation import
→ zero duplicate Takes
→ zero duplicate output Assets
→ zero duplicate Blob bytes
```

---

# 115. M7 — Provenance and Exact Rerun

Build:

* ShotRevision viewer
* reference provenance
* GenerationInput viewer
* Blob hashes
* compiled prompt
* compiler version
* parameters
* manifest hash
* logical workflow viewer
* executor submission viewer
* executor job ID
* model/version
* lineage
* errors
* Exact Rerun

Exit:

> Historical execution is fully inspectable and reconstructible.

---

# 116. M8 — Full Failure Matrix

Test:

* browser close
* API restart
* worker restart
* worker fatal crash
* fresh worker ID after restart
* stale lease takeover
* unconditional reconciliation
* zombie heartbeat
* zombie progress
* zombie lifecycle mutation
* executor active during takeover
* Comfy crash
* Comfy restart
* Comfy mismatch
* WebSocket loss
* executor lost job
* ambiguous preparing
* cancel race
* unsafe shared-instance cancellation
* DB busy
* filesystem failure
* event-loop blocking protection
* upload race
* Blob inconsistency
* import retry
* malformed output

Exit:

> All supported failure cases produce deterministic behavior.

---

# 117. M9 — Dogfood

Produce a real multi-shot project and evaluate:

* Shot editing
* reference ordering
* generation friction
* queue fairness
* cancellation
* takeover behavior
* progress display
* video scrubbing
* candidate comparison
* canon flow
* reruns
* provenance
* storage growth
* GC
* SQLite contention
* repeated operations

Only then define v0.2.

---

# 118. Critical Worker Identity Tests

Explicit tests:

```text
worker process starts
→ worker_id A

same machine restarts process
→ worker_id B

A != B
```

Also verify:

* worker ID is not configurable
* hostname changes nothing
* PID reuse changes nothing
* persisted DB state does not restore old worker ID

---

# 119. Critical Reconciliation Tests

Run reconciliation after:

* fresh lease insertion
* self-refresh
* stale takeover

Verify steady state:

```text
no stale candidates
→ cheap no-op
```

Verify corrupted/unusual state:

```text
self-refresh succeeds
+
stale Generation from another old worker exists
→ reconciliation still catches it
```

---

# 120. Critical Ownership Tests

Test:

* same-connection ownership operation
* deliberately split connection check/write
* lease loser heartbeat rejected
* lease loser progress rejected
* lease loser transition rejected
* lease loser cannot persist external handle
* lease loser does not cancel external work
* replacement worker adopts
* old process later resumes
* all old-worker writes remain rejected

---

# 121. Critical Revision/Input Tests

Test:

* concurrent identical Generate → one ShotRevision
* reference replacement → new revision
* reference reorder → new revision
* reference removal → new revision
* same ShotRevision + same manifest → same ordered GenerationInputs
* input ordering does not depend on DB retrieval order

---

# 122. Critical Heartbeat/File Tests

Simulate:

```text
large Blob hash/copy
+
active Generation heartbeat
+
worker lease heartbeat
```

Verify:

* event loop remains responsive
* lease heartbeat remains within cadence
* Generation heartbeat remains within cadence
* no false stale takeover occurs

---

# 123. Critical SSE Tests

Verify event contains:

```text
status
progress
current_node
cancel_requested
cancel_requested_at
errors
updated_at
```

Verify:

* immediate initial event
* cancellation request reflected before terminal cancellation
* transient busy skips tick
* terminal event closes stream
* no DB session held across sleep

---

# 124. Definition of Done

SoloRing v0.1 is complete when:

* [ ] Every worker process gets a new `uuid4()` ID.
* [ ] Worker IDs cannot be configured or reused.
* [ ] Worker lease name remains the stable authority role.
* [ ] Successful lease authority always triggers stale-work reconciliation.
* [ ] Reconciliation runs after insertion, self-refresh, and takeover.
* [ ] Reconciliation occurs before new queue claims.
* [ ] Ownership SQL is centralized in `ownership.py`.
* [ ] Ownership helpers own their full transaction.
* [ ] Ownership-critical paths use one checked-out SQLite connection.
* [ ] `BEGIN IMMEDIATE` semantics are verified by tests.
* [ ] Split-connection authority check/write is prevented or proven unsafe by tests.
* [ ] Lease loser cannot heartbeat a Generation.
* [ ] Lease loser cannot update progress.
* [ ] Lease loser cannot change lifecycle state.
* [ ] Lease loser does not cancel external work.
* [ ] Worker clean lease-loss shutdown is distinguishable from fatal crash.
* [ ] Large file work cannot starve ownership heartbeats.
* [ ] Ambiguous Comfy submission prefers `interrupted` over duplicate submission.
* [ ] ShotRevision has unique `(shot_id, snapshot_hash)`.
* [ ] Concurrent identical Generate calls converge on one ShotRevision.
* [ ] ShotRevision snapshot is schema-versioned.
* [ ] Logical workflow specification is schema-versioned.
* [ ] `prompt_compiler_version` is required from the first migration.
* [ ] GenerationInput mapping is deterministic.
* [ ] Shot numbers are never reused.
* [ ] Generation numbers are never reused.
* [ ] Cancellation intent is persisted.
* [ ] SSE exposes cancellation-request state.
* [ ] Output import uses deterministic output keys.
* [ ] Repeated import creates no duplicate Takes.
* [ ] Repeated import creates no duplicate output Assets.
* [ ] Blob upload remains streaming and atomic.
* [ ] Concurrent duplicate uploads produce one Blob and multiple provenance Assets.
* [ ] Blob serving supports HTTP Range.
* [ ] Logical workflow provenance contains no transient executor paths.
* [ ] Exact Rerun copies historical GenerationInputs.
* [ ] Exact Rerun does not promise byte-identical output.
* [ ] Rejecting an approved Take clears canon atomically.
* [ ] FakeExecutor Gate A passes before Comfy.
* [ ] FakeExecutor Gate B passes before Comfy.
* [ ] FakeExecutor Gate C passes before Comfy.
* [ ] ComfyUI remains an execution adapter rather than part of the creative domain model.

---

# 125. Immediate Engineering Sequence

```text
M0
Runtime + SQLite + Process Identity + Worker Lease
        ↓
M1
Temporal Domain + Storage + Structural Constraints
        ↓
M2
Creative UI
        ↓
M3A
Fake Happy Path
        ↓
M3B
Ownership + Cancellation + Recovery
        ↓
M3C
Crash + Race + Import Idempotency
        ↓
HARD GATE
        ↓
M4
Workflow Contract
        ↓
M5
ComfyExecutor
```

The foundational path is:

```text
Project
  ↓
Shot
  ↓
ShotIntent + Ordered References
  ↓
Versioned Canonical ShotRevision
  ↓
Immutable Generation
  ↓
Deterministic GenerationInputs
  ↓
Versioned Logical Workflow
  ↓
Indexed SQLite Queue
  ↓
Ephemeral Worker Process Identity
  ↓
Stable Singleton Lease Authority
  ↓
Transactionally Fenced Generation Ownership
  ↓
Unconditional Reconciliation
  ↓
FakeExecutor
  ↓
Recoverable Execution
  ↓
Idempotent Import
  ↓
Blob + Asset
  ↓
Take
  ↓
Review
  ↓
Explicit Canon
```

Only after this entire foundation is proven should ComfyUI enter the system.

At that point, ComfyUI is a replaceable executor behind a durable creative, temporal, ownership, cancellation, provenance, and recovery architecture.
