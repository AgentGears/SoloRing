# SoloRing M1 — Temporal Domain and Storage Implementation Plan

## 1. Objective

M1 establishes SoloRing's durable temporal-domain, persistence, and storage foundation.

At M1 completion, the system must be able to represent and preserve:

```text
Project
  ↓
Mutable Shot Working State
  ↓
Ordered ShotReferences
  ↓
Canonical Immutable ShotRevision
  ↓
Durable Generation Identity
  ↓
Immutable GenerationInputs
```

and:

```text
Physical Bytes
  ↓
SHA-256 Blob
  ↓
Provenance Asset
  ↓
ShotReference / Future Take
```

M1 makes creative history, execution identity, and storage semantics structurally complete.

M1 does **not** make Generations executable.

### Exit criterion

> Creative history, execution identities, and storage semantics are structurally complete and race-safe.

---

# 2. Milestone Boundary

## 2.1 Included

M1 implements:

* Projects
* Project soft deletion
* Shots
* Shot soft deletion
* `ShotIntent`
* mutable Shot working state
* centralized Shot numbering
* non-reused Shot numbering
* ShotReferences
* reference-role validation
* server-assigned reference positions
* atomic reference replacement
* canonical JSON serialization
* schema-versioned ShotRevision snapshots
* ShotRevision hashing
* ShotRevision reuse
* concurrent ShotRevision convergence
* working snapshot hashes
* Blobs
* relative content-addressed Blob paths
* Assets
* Asset provenance
* streamed reference upload
* upload limits
* zero-byte upload rejection
* atomic physical Blob placement
* duplicate-byte race handling
* Blob integrity checks
* Blob integrity repair during verified upload
* Blob serving
* structural Blob path validation
* HTTP Range support
* immutable Blob caching
* complete Generation schema
* Generation `updated_at`
* centralized Generation numbering
* non-reused Generation numbering
* cancellation metadata
* lifecycle/ownership fields
* recovery indexes
* deferred large Generation columns
* immutable `GenerationDraft`
* deterministic GenerationInput mapping
* atomic Generation + GenerationInput persistence
* Takes
* deterministic `output_key`
* stable domain enums and database CHECK constraints
* stable API error envelope
* FastAPI/Pydantic validation-error normalization
* migration `0002_temporal_domain_storage`
* populated migration tests
* all M0 regression tests

## 2.2 Explicitly excluded

M1 does **not** implement:

* frontend creative UI
* prompt compiler behavior
* workflow-manifest parsing
* workflow cardinality validation
* parameter resolution
* logical workflow construction
* public Generation creation
* queue claiming
* worker Generation ownership
* Generation heartbeat
* progress mutation
* FakeExecutor
* ComfyExecutor
* active cancellation execution
* stale Generation recovery
* output staging
* output import
* approval/rejection
* SSE
* Exact Rerun
* provenance UI

The boundary is:

```text
M1
complete durable execution identity

M3A
assemble and execute durable Generation requests
```

---

# 3. Backend Organization

Use explicit domain modules rather than expanding one monolithic model file.

```text
server/soloring/
├── api/
│   ├── errors.py
│   ├── projects.py
│   ├── shots.py
│   ├── assets.py
│   ├── blobs.py
│   └── schemas/
│
├── db/
│   ├── engine.py
│   ├── models.py
│   ├── sqlite.py
│   └── timeutil.py
│
├── domain/
│   ├── models.py
│   ├── shot_intent.py
│   ├── canonical.py
│   ├── snapshots.py
│   ├── projects.py
│   ├── shots.py
│   ├── references.py
│   └── revisions.py
│
├── assets/
│   ├── models.py
│   ├── blob_store.py
│   ├── media.py
│   ├── upload.py
│   └── service.py
│
├── generation/
│   ├── models.py
│   ├── enums.py
│   ├── drafts.py
│   ├── repository.py
│   └── input_mapping.py
│
└── worker/
    └── ...                     # M0 foundation remains intact
```

`db/models.py` remains the metadata-registration point.

Request handlers must not depend on implicit async ORM lazy loading.

---

# 4. Migration `0002_temporal_domain_storage`

Create:

```text
server/alembic/versions/0002_temporal_domain_storage.py
```

with:

```python
down_revision = "0001_worker_leases"
```

Migration `0002` creates the complete M1 schema.

## 4.1 Creation order

Create tables in dependency order:

```text
projects
blobs
shots
shot_revisions
generations
takes
assets
shot_references
generation_inputs
indexes
```

Downgrade in exact reverse dependency order.

## 4.2 Constraint naming

Every constraint must have a deterministic explicit name.

This applies to:

* primary keys
* foreign keys
* unique constraints
* check constraints
* indexes

Examples:

```text
pk_projects
ck_projects_name_nonempty
fk_shots_project_id_projects
uq_shots_project_id_shot_number
ix_shots_project_active_number
```

Do not rely on anonymous constraint names.

Stable naming is required for future SQLite batch migrations.

---

# 5. Foreign-Key Policy

Create these foreign keys:

```text
shots.project_id
    → projects.id

shot_revisions.shot_id
    → shots.id

generations.shot_id
    → shots.id

generations.shot_revision_id
    → shot_revisions.id

generations.rerun_of_generation_id
    → generations.id

takes.shot_id
    → shots.id

takes.generation_id
    → generations.id

assets.project_id
    → projects.id

assets.take_id
    → takes.id

assets.blob_hash
    → blobs.hash

shot_references.shot_id
    → shots.id

shot_references.asset_id
    → assets.id

generation_inputs.generation_id
    → generations.id

generation_inputs.asset_id
    → assets.id

generation_inputs.blob_hash
    → blobs.hash
```

Use restrictive deletion semantics for historical/provenance relationships.

## 5.1 Intentional `approved_take_id` exception

Do not create:

```text
shots.approved_take_id → takes.id
```

as a database FK in M1.

This intentionally avoids a cyclic SQLite schema dependency between `shots` and `takes`.

Later approval/rejection services verify Take ownership transactionally.

Add:

```sql
CREATE INDEX ix_shots_approved_take_id
ON shots(approved_take_id);
```

M1 APIs must never permit clients to mutate `approved_take_id`.

---

# 6. Central Timestamp Policy

Use one central SQL expression:

```python
DB_NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"
```

All persisted M1 timestamps use SQLite UTC time.

This includes:

* `created_at`
* `updated_at`
* `deleted_at`
* `queued_at`
* Generation timestamps
* later lifecycle mutations
* later cancellation mutations

Do not generate persistent domain timestamps from Python wall-clock time.

## 6.1 `updated_at`

Every mutable entity update must set `updated_at` using the SQLite expression.

Later Generation lifecycle code must also update:

```text
generations.updated_at
```

with SQLite time.

---

# 7. Text Normalization Policy

Canonical snapshot identity depends on stored strings, so text normalization is part of the persistence contract.

## 7.1 Project name

Before persistence:

```text
trim leading/trailing whitespace
reject if empty after trim
```

Maximum:

```text
500 characters
```

Database checks:

```sql
CHECK(length(trim(name)) > 0)
CHECK(length(name) <= 500)
```

## 7.2 Project description

Before persistence:

```text
trim
empty after trim → NULL
otherwise persist trimmed value
```

## 7.3 Shot subject

Before persistence:

```text
trim
reject if empty after trim
```

Maximum:

```text
20,000 characters
```

Database checks:

```sql
CHECK(length(trim(subject)) > 0)
CHECK(length(subject) <= 20000)
```

## 7.4 Optional creative Shot strings

For:

```text
title
action
environment
framing
camera_motion
lens
mood
```

normalize:

```text
NULL
→ NULL

""
→ NULL

whitespace-only
→ NULL

non-empty
→ trim and persist
```

This means:

```text
action = ""
```

and:

```text
action = NULL
```

have one canonical persistent representation.

## 7.5 Reference roles

Reference roles are different.

They are:

* persisted exactly as supplied
* case-sensitive
* not trimmed
* not lowercased
* not otherwise normalized

However, validation rejects:

* empty roles
* whitespace-only roles
* roles longer than 64 characters

A role change is therefore an explicit creative-state change.

---

# 8. Projects

Schema:

```text
projects

id              UUID PK
name            TEXT NOT NULL
description     TEXT NULL

created_at      TEXT NOT NULL
updated_at      TEXT NOT NULL
deleted_at      TEXT NULL
```

Checks:

```sql
CHECK(length(trim(name)) > 0)
CHECK(length(name) <= 500)
```

## 8.1 Project PATCH boundary

`PATCH /projects/{id}` may mutate only:

```text
name
description
```

It must not accept:

```text
id
created_at
updated_at
deleted_at
```

## 8.2 Project soft deletion

Deleting an active Project occurs in one transaction:

```text
Project.deleted_at = db_now
Project.updated_at = db_now

for each child Shot where deleted_at IS NULL:
    Shot.deleted_at = db_now
    Shot.updated_at = db_now
```

Already-soft-deleted Shots are left untouched.

Their original:

```text
deleted_at
updated_at
```

are not overwritten by later Project deletion.

Do not modify:

* ShotReferences
* ShotRevisions
* Generations
* GenerationInputs
* Takes
* Assets
* Blobs

Historical provenance remains intact.

## 8.3 DELETE idempotency

```text
first DELETE   → 204
repeat DELETE  → 204
```

No restore endpoint exists in v0.1.

## 8.4 Deleted hierarchy

Normal reads and mutations treat deleted Projects as absent.

Examples:

```text
GET deleted Project
→ 404 PROJECT_NOT_FOUND

create Shot in deleted Project
→ 404 PROJECT_NOT_FOUND
```

---

# 9. Shots

Schema:

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
```

Checks:

```sql
CHECK(length(trim(subject)) > 0)
CHECK(length(subject) <= 20000)

CHECK(
    duration_ms IS NULL
    OR duration_ms >= 0
)
```

M1 preserves the v0.1 architectural contract that `duration_ms = 0` is structurally legal.

Semantic/UI restrictions may become stricter later without changing canonical storage semantics.

## 9.1 `ShotIntent`

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

Model/executor parameters never enter this model.

## 9.2 Shot PATCH boundary

May mutate only:

```text
title
subject
action
environment
framing
camera_motion
lens
mood
duration_ms
```

Must not accept:

```text
id
project_id
shot_number
approved_take_id
created_at
updated_at
deleted_at
```

Successful PATCH updates:

```text
shots.updated_at
```

with database time.

## 9.3 Shot soft deletion

Deleting a Shot sets:

```text
deleted_at = db_now
updated_at = db_now
```

Do not delete or modify historical rows.

DELETE is idempotent:

```text
first DELETE   → 204
repeat DELETE  → 204
```

---

# 10. Atomic Shot Number Allocation

Shot numbers are Project-scoped and never reused.

Allocation must:

1. verify that the parent Project exists and is active;
2. calculate the next number including soft-deleted Shots;
3. insert the Shot;
4. perform those actions atomically.

Preferred SQLite statement:

```sql
INSERT INTO shots (
    id,
    project_id,
    shot_number,
    title,
    subject,
    action,
    environment,
    framing,
    camera_motion,
    lens,
    mood,
    duration_ms,
    created_at,
    updated_at
)
SELECT
    :id,
    :project_id,
    COALESCE(
        (
            SELECT MAX(shot_number)
            FROM shots
            WHERE project_id = :project_id
        ),
        0
    ) + 1,
    :title,
    :subject,
    :action,
    :environment,
    :framing,
    :camera_motion,
    :lens,
    :mood,
    :duration_ms,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE EXISTS (
    SELECT 1
    FROM projects
    WHERE id = :project_id
      AND deleted_at IS NULL
)
RETURNING id, shot_number;
```

No returned row means:

```text
PROJECT_NOT_FOUND
```

The MAX calculation includes soft-deleted Shots.

## 10.1 Collision handling

The unique constraint:

```text
UNIQUE(project_id, shot_number)
```

is the final concurrency guard.

A numbering collision must never leak raw `IntegrityError`.

Policy:

```text
collision
→ retry once in a new short transaction

second collision
→ stable internal invariant error
→ HTTP 500
→ log at error level
```

With correct SQLite serialization this path should be exceptional.

## 10.2 RETURNING fallback

Where SQLite `RETURNING` is unavailable, use one checked-out connection and a short `BEGIN IMMEDIATE` transaction:

```text
BEGIN IMMEDIATE
↓
verify active Project
↓
compute MAX + 1
↓
INSERT
↓
read inserted row
↓
COMMIT
```

Do not reintroduce an unfenced SELECT-then-INSERT race.

---

# 11. ShotReferences

Schema:

```text
shot_references

shot_id              UUID NOT NULL
asset_id             UUID NOT NULL

role                  TEXT NOT NULL
position              INTEGER NOT NULL

created_at            TEXT NOT NULL

PRIMARY KEY(shot_id, asset_id, role)

UNIQUE(shot_id, role, position)
```

Checks:

```sql
CHECK(position >= 0)

CHECK(
    length(role) BETWEEN 1 AND 64
    AND length(trim(role)) > 0
)
```

Add:

```sql
CREATE INDEX ix_shot_references_asset_id
ON shot_references(asset_id);
```

## 11.1 Reference roles

Roles are arbitrary creative labels.

Examples:

```text
reference
character
environment
style
```

They are not a database enum.

Persistence is exact:

```text
"Character" != "character"
"reference " != "reference"
```

although whitespace-only roles are invalid.

## 11.2 Positions

Positions are:

* zero-based
* contiguous
* assigned by the server
* scoped within each role

Clients do not control persisted position values.

## 11.3 Atomic replacement

Endpoint:

```text
PUT /shots/{id}/references
```

First validate the entire proposed set.

Then, inside one transaction:

```sql
DELETE FROM shot_references
WHERE shot_id = :shot_id;

INSERT INTO shot_references (...)
VALUES (...);
```

Also update:

```text
shots.updated_at = db_now
```

because reference changes modify Shot working state.

## 11.4 Validation

Reject:

* missing Shot
* deleted Shot
* missing Asset
* Asset belonging to another Project
* duplicate `(asset_id, role)`
* invalid role
* client-controlled persisted positions

The same Asset may appear under multiple different roles.

## 11.5 Identical PUT

Submitting the same normalized reference set is valid.

M1 deliberately permits delete-and-reinsert even when the semantic set is unchanged.

The endpoint always returns:

```text
200 OK
+
full normalized persisted reference set
```

This keeps PUT behavior predictable and idempotent from the client's perspective.

`created_at` changes on the mutable reference rows do not affect ShotRevision identity.

---

# 12. Canonical JSON Serialization

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

No alternative canonical serializer is permitted.

## 12.1 Exact byte fixture

This value:

```python
snapshot = {
    "schema_version": 1,
    "intent": {
        "subject": "test",
        "action": None,
    },
    "references": [],
}
```

must produce exactly:

```text
{"intent":{"action":null,"subject":"test"},"references":[],"schema_version":1}
```

as UTF-8 bytes.

## 12.2 Required canonicalization cases

Tests must cover:

* nested `null`
* empty string versus `null`
* Unicode
* Unicode combining characters
* embedded quotes
* newlines
* very long subject strings
* reordered input dictionaries
* empty reference lists
* multiple reference roles
* reordered reference input before canonical sort

No Unicode normalization such as NFC/NFD conversion is performed unless explicitly added to a future schema version.

Exact stored code points therefore remain part of snapshot identity.

---

# 13. ShotRevision Snapshot

Canonical shape:

```json
{
  "schema_version": 1,
  "intent": {
    "subject": "...",
    "action": null,
    "environment": null,
    "framing": null,
    "camera_motion": null,
    "lens": null,
    "mood": null,
    "duration_ms": null
  },
  "references": [
    {
      "asset_id": "...",
      "blob_hash": "...",
      "role": "reference",
      "position": 0
    }
  ]
}
```

All optional intent fields remain present as JSON `null`.

References are sorted deterministically by:

```text
role
position
asset_id
```

UUIDs use lowercase canonical UUID form.

Compute:

```python
snapshot_bytes = canonical_json_bytes(snapshot)
snapshot_json = snapshot_bytes.decode("utf-8")
snapshot_hash = hashlib.sha256(snapshot_bytes).hexdigest()
```

The exact stored bytes are the exact hashed bytes.

---

# 14. ShotRevisions

Schema:

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

Check:

```sql
CHECK(length(snapshot_hash) = 64)
```

## 14.1 Capture pattern

```text
short consistent read
↓
construct immutable snapshot value
↓
close read unit
↓
canonicalize + hash
↓
short write transaction
↓
insert/reuse revision
```

Editing mutable working state does not automatically create a revision.

Revision capture is lazy.

## 14.2 Revision-number allocation

New revisions calculate:

```sql
COALESCE(MAX(revision_number), 0) + 1
```

for the Shot.

Two independent uniqueness dimensions exist:

```text
(shot_id, revision_number)
(shot_id, snapshot_hash)
```

## 14.3 Convergence and collision handling

Insertion uses conflict-aware semantics:

```text
attempt INSERT
↓
row returned?
├─ yes
│   → new revision
└─ no
    ↓
    fetch by (shot_id, snapshot_hash)
    ↓
    found?
    ├─ yes
    │   → concurrent identical snapshot
    │   → return existing revision
    └─ no
        → revision_number collided with a different snapshot
        → retry allocation
```

Use a bounded retry:

```text
maximum 5 attempts
```

After exhaustion:

```text
stable internal invariant error
+
error-level log
```

Raw `IntegrityError` must not escape the service boundary.

## 14.4 Required race cases

Test:

```text
same state captured twice
→ same revision

two concurrent identical snapshots
→ exactly one row
→ both callers receive same revision

two concurrent different snapshots
→ distinct revisions
→ no failed request due solely to revision_number collision
```

---

# 15. Working Snapshot Hash

`GET /shots/{id}` includes:

```text
working_snapshot_hash
```

computed by the server using the exact canonical snapshot builder used for ShotRevision capture.

The frontend never reimplements canonicalization.

Do not include `working_snapshot_hash` on:

```text
GET /projects/{id}/shots
```

because Shot list endpoints should remain lightweight.

M1 does not compute:

```text
working_state_differs_from_approved
```

because approval is not yet implemented.

---

# 16. Revision List API

Endpoint:

```text
GET /shots/{id}/revisions
```

returns summaries only:

```json
{
  "id": "...",
  "shot_id": "...",
  "revision_number": 3,
  "snapshot_hash": "...",
  "created_at": "..."
}
```

Do not return `snapshot_json` for every row in the list.

Full provenance inspection remains later work.

---

# 17. Blobs

Schema:

```text
blobs

hash                   TEXT PK
path                   TEXT NOT NULL UNIQUE
size_bytes             INTEGER NOT NULL
detected_media_type    TEXT NULL
created_at             TEXT NOT NULL
```

Checks:

```sql
CHECK(length(hash) = 64)
CHECK(size_bytes >= 0)
```

Application code additionally validates lowercase hexadecimal SHA-256 form.

Add:

```sql
CREATE INDEX ix_blobs_created_at
ON blobs(created_at);
```

for future GC cutoff queries.

## 17.1 Blob identity

> Blob identity derives only from immutable physical bytes.

## 17.2 Stored paths

Persist relative paths:

```text
sha256/aa/bb/<full-hash>
```

Never persist absolute machine paths.

`BlobStore.path_for_hash()` remains synchronous because path derivation performs no I/O.

---

# 18. Assets

Schema:

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
```

Constraints:

```sql
CHECK(kind IN ('reference', 'output'))

CHECK(
    (kind = 'reference' AND take_id IS NULL)
    OR
    (kind = 'output' AND take_id IS NOT NULL)
)

CHECK(width IS NULL OR width > 0)
CHECK(height IS NULL OR height > 0)
CHECK(duration_ms IS NULL OR duration_ms >= 0)
CHECK(fps IS NULL OR fps > 0)
```

Indexes:

```sql
CREATE INDEX ix_assets_project_created
ON assets(project_id, created_at);

CREATE INDEX ix_assets_take
ON assets(take_id);

CREATE INDEX ix_assets_blob_hash
ON assets(blob_hash);
```

`ix_assets_blob_hash` is required for:

* provenance lookup
* Blob integrity analysis
* later Blob GC

## 18.1 Provenance

> Asset identity derives from one explicit provenance event.

Every successful reference upload creates a new Asset UUID.

Physical bytes alone deduplicate.

## 18.2 Output Asset MIME semantics

Generated output Assets later use:

```text
kind = 'output'
take_id != NULL
upload_mime_type = NULL
```

because no client upload declared their MIME type.

If an output Asset is later used as a Shot reference, its provenance remains:

```text
kind = 'output'
```

---

# 19. Original Filename Policy

`original_filename` is provenance metadata only.

It is never used as a filesystem path.

Before persistence:

1. take only the filename component/basename;
2. bound to at most 512 characters;
3. preserve the resulting text for provenance.

Never use `original_filename` to construct:

* temp paths
* Blob paths
* executor paths

---

# 20. Media Detection Scope

M1 implements only deterministic magic-byte detection.

### JPEG

Starts with:

```text
FF D8 FF
```

→

```text
image/jpeg
```

### PNG

Starts with:

```text
89 50 4E 47
```

→

```text
image/png
```

All other content:

```text
detected_media_type = NULL
```

Do not add:

* python-magic
* FFmpeg
* ffprobe
* image decoders
* video probing
* metadata extraction libraries

in M1.

Unknown bytes are served as:

```text
application/octet-stream
```

---

# 21. Blob Temp/Final Same-Filesystem Invariant

Atomic final placement depends on `os.replace()`.

Therefore:

> The upload temp directory and final Blob directory must reside on the same filesystem/volume.

Default layout satisfies this:

```text
data/
├── tmp/
└── blobs/
```

Explicit storage overrides must not silently break the invariant.

## 21.1 Startup validation

After storage directories exist, startup validates that:

```text
settings.tmp_dir
settings.blob_dir
```

reside on the same filesystem/volume.

On platforms exposing device identity through `os.stat`, compare the relevant filesystem/device identifiers.

If atomic same-filesystem placement cannot be guaranteed:

```text
startup fails
+
clear configuration error
```

Do not wait for an upload to discover a cross-device rename.

---

# 22. Streamed Asset Upload

Endpoint:

```text
POST /projects/{project_id}/assets
```

This creates reference-upload provenance only.

Clients cannot request `kind='output'`.

## 22.1 Sequence

```text
short DB read
verify active Project
↓
close DB session
↓
create UUID-only temp file in settings.tmp_dir
↓
stream bounded chunks
↓
SHA-256 + byte count
↓
enforce size
↓
reject empty file
↓
detect media signature
↓
derive final Blob path
↓
atomic physical placement/reuse
↓
short DB transaction
↓
re-check active Project
↓
insert/reuse Blob
↓
always insert new reference Asset
↓
commit
```

No DB session remains open during file streaming.

## 22.2 Bounded reads

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
```

## 22.3 Empty upload

A zero-byte reference upload is invalid.

Return:

```text
400 EMPTY_UPLOAD
```

Create:

* no Blob row
* no Asset row
* no final Blob file

Clean the temp file.

## 22.4 Oversized upload

If:

```text
total > max_upload_bytes
```

return:

```text
413 UPLOAD_TOO_LARGE
```

and clean all temporary state.

---

# 23. File I/O and Event-Loop Discipline

Blocking filesystem operations must not starve the event loop.

Use:

```python
await asyncio.to_thread(...)
```

or a controlled thread executor for blocking work such as:

* file writes where required by implementation
* hashing large on-disk files
* filesystem metadata
* directory creation
* rename/replace
* cleanup

Upload processing must remain compatible with M0's lease-heartbeat requirements once worker file operations are introduced later.

---

# 24. Atomic Blob Placement

Use:

```python
os.replace(temp_path, final_path)
```

for atomic same-filesystem placement.

Sequence:

```text
hash complete
↓
derive final path
↓
create parent directories
↓
final exists?
├─ yes
│   → discard temp
└─ no
    → os.replace(temp, final)
```

A race between existence check and replacement is safe because both contenders have already computed the same SHA-256 identity from complete bytes.

---

# 25. Blob Database Convergence

Inside the short persistence transaction:

```text
INSERT Blob ... ON CONFLICT DO NOTHING
↓
SELECT canonical Blob row by hash
↓
INSERT fresh Asset
```

Conceptually:

```python
await session.execute(
    sqlite_insert(Blob)
    .values(...)
    .on_conflict_do_nothing(index_elements=[Blob.hash])
)

await session.flush()

blob = await session.scalar(
    select(Blob).where(Blob.hash == blob_hash)
)
```

The existing Blob row is the canonical row.

Duplicate bytes never deduplicate Asset provenance.

---

# 26. Duplicate Upload Invariant

Two concurrent identical uploads must produce:

```text
one SHA-256
one final physical Blob
one blobs row
two distinct Assets
```

Required assertions:

```text
Blob count = 1
Asset count = 2
Asset IDs differ
both Assets reference same Blob hash
physical file contains expected bytes
```

---

# 27. Blob Integrity Anomalies

## 27.1 Registered Blob row, missing physical file

Serving returns:

```text
404 BLOB_NOT_FOUND
```

and logs an integrity error containing at least:

```text
Blob hash
expected physical path
fact that registered bytes are missing
```

Do not silently:

* recreate
* delete the DB row
* serve empty bytes

## 27.2 Verified upload repairs missing registered bytes

If an upload has:

* computed the exact Blob SHA-256;
* verified the complete correct bytes;
* found an existing matching Blob row;
* found that the registered physical file is missing;

it may repair the missing file using the verified upload bytes.

Repair must emit a high-severity log containing:

```text
Blob hash
repair action
physical destination
```

Repair is never silent.

## 27.3 File exists but Blob row is absent

A successful verified upload may reuse the hash-addressed file and insert the missing Blob row.

Database state remains authoritative for serving.

A file merely existing on disk does not make it API-visible.

---

# 28. Blob Serving

Endpoints:

```text
GET  /blobs/{prefix1}/{prefix2}/{hash}
HEAD /blobs/{prefix1}/{prefix2}/{hash}
```

## 28.1 Structural validation before lookup

Require:

```text
hash:
    exactly 64 lowercase hexadecimal characters

prefix1:
    exactly hash[0:2]

prefix2:
    exactly hash[2:4]
```

Malformed hash:

```text
400
```

Prefix mismatch:

```text
400
```

These conditions are rejected **before**:

* Blob DB lookup
* filesystem access

This is a storage/path-traversal boundary and requires dedicated tests independent of Range handling.

## 28.2 Unknown Blob

No registered row:

```text
404 BLOB_NOT_FOUND
```

## 28.3 Missing registered file

Registered Blob row but missing file:

```text
404 BLOB_NOT_FOUND
+
integrity-error log
```

## 28.4 Content type

Use:

```python
blob.detected_media_type or "application/octet-stream"
```

Do not treat `upload_mime_type` as authoritative serving metadata.

---

# 29. HTTP Range

M1 implements single-range byte serving.

Support:

```text
bytes=0-1023
bytes=1024-
bytes=-1024
```

Multipart ranges are out of scope.

## 29.1 Responses

No Range:

```text
200 OK
```

Valid Range:

```text
206 Partial Content
```

Malformed/unsatisfiable Range:

```text
416 Range Not Satisfiable
```

HEAD:

```text
same relevant metadata headers
no body
```

## 29.2 `206` headers

Include:

```text
Content-Range
Content-Length
Accept-Ranges: bytes
```

## 29.3 `416`

Include:

```text
Content-Range: bytes */<full-size>
```

Zero-byte reference uploads are rejected, so Blob serving does not need special M1 behavior for newly uploaded empty files.

---

# 30. Immutable Blob Caching

Because Blob identity is content-addressed:

```text
Cache-Control: public, max-age=31536000, immutable
ETag: "<sha256>"
Accept-Ranges: bytes
```

The ETag uses the quoted SHA-256 hash.

Never expose absolute filesystem paths.

---

# 31. Generation Schema

M1 creates the complete durable Generation table.

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
updated_at               TEXT NOT NULL
queued_at                TEXT NOT NULL
started_at               TEXT NULL
completed_at             TEXT NULL

UNIQUE(shot_id, generation_number)
```

`updated_at` exists from the first Generation migration.

---

# 32. Generation Constraints

Operation:

```sql
CHECK(operation IN (
    'generate',
    'rerun'
))
```

Status:

```sql
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

Executor:

```sql
CHECK(executor IN (
    'fake',
    'comfy'
))
```

The executor CHECK is explicitly a **v0.1 schema constraint**, not a permanent architectural limitation.

Adding another executor in a future release requires a migration.

Required non-empty identity-bearing fields include:

```text
executor
workflow_id
compiled_prompt
prompt_compiler_version
parameters_json
workflow_spec_json
```

Hash fields representing SHA-256 values must be 64 characters.

Nullable hashes are length-checked only when non-NULL.

---

# 33. Generation Indexes

Required recovery indexes:

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

The worker index ordering is deliberate:

```text
worker_id
status
heartbeat_at
```

while the broader stale-state scan is already covered by:

```text
status
heartbeat_at
```

---

# 34. Additional Query Indexes

Create:

```sql
CREATE INDEX ix_projects_active_created
ON projects(deleted_at, created_at);
```

```sql
CREATE INDEX ix_shots_project_active_number
ON shots(project_id, deleted_at, shot_number);
```

```sql
CREATE INDEX ix_shots_approved_take_id
ON shots(approved_take_id);
```

```sql
CREATE INDEX ix_assets_project_created
ON assets(project_id, created_at);
```

```sql
CREATE INDEX ix_assets_take
ON assets(take_id);
```

```sql
CREATE INDEX ix_assets_blob_hash
ON assets(blob_hash);
```

```sql
CREATE INDEX ix_takes_shot_created
ON takes(shot_id, created_at);
```

```sql
CREATE INDEX ix_shot_references_asset_id
ON shot_references(asset_id);
```

```sql
CREATE INDEX ix_generation_inputs_asset_id
ON generation_inputs(asset_id);
```

```sql
CREATE INDEX ix_blobs_created_at
ON blobs(created_at);
```

Before freezing `0002`, inspect SQLite's actual PK/UNIQUE-generated indexes and confirm none of these are redundant with an existing useful leftmost-prefix index.

---

# 35. Deferred Generation Columns

Mark from the first ORM definition:

```text
workflow_spec_json
executor_submission_json
error_details_json
```

as deferred.

Lightweight queue/list/status queries must not load them.

Full provenance/detail queries use explicit:

```python
undefer(...)
```

options.

Provide separate repository methods for:

```text
lightweight Generation reads
full Generation provenance reads
```

Do not rely on implicit async lazy loading.

---

# 36. Immutable `GenerationDraft`

Define a frozen persistence value:

```python
@dataclass(frozen=True)
class GenerationDraft:
    shot_id: str
    shot_revision_id: str

    operation: GenerationOperation
    executor: str

    workflow_id: str
    workflow_version: int
    workflow_template_hash: str
    manifest_hash: str

    model: str | None
    model_version: str | None

    compiled_prompt: str
    negative_prompt: str | None
    prompt_compiler_version: str

    seed: int | None

    parameters_json: str

    workflow_spec_json: str
    workflow_spec_hash: str

    rerun_of_generation_id: str | None = None
```

Required text/JSON fields cannot be empty.

At minimum:

```text
parameters_json
workflow_spec_json
```

must parse as syntactically valid JSON before persistence.

M1 does **not** validate workflow semantics or recompute logical workflow hashes.

Those responsibilities remain later workflow/orchestration concerns.

---

# 37. Generation Number Allocation

Generation numbers are Shot-scoped and never reused.

Persistence must atomically verify:

```text
Shot exists
Shot is not soft-deleted
ShotRevision exists
ShotRevision belongs to Shot
```

before committing the Generation.

Calculate:

```sql
COALESCE(MAX(generation_number), 0) + 1
```

inside the same write transaction.

## 37.1 Number collision

The unique constraint:

```text
UNIQUE(shot_id, generation_number)
```

is the final guard.

Collision policy:

```text
collision
→ retry once

second collision
→ stable internal invariant error
```

Raw database exceptions do not cross the repository/API boundary.

## 37.2 RETURNING fallback

Use the same SQLite capability handling as Shot numbering.

The fallback uses one connection and `BEGIN IMMEDIATE` for:

```text
validation
number allocation
insert
verification
```

---

# 38. GenerationInputs

Schema:

```text
generation_inputs

generation_id         UUID NOT NULL
asset_id              UUID NOT NULL

input_key             TEXT NOT NULL
reference_role        TEXT NULL
position              INTEGER NOT NULL
blob_hash             TEXT NOT NULL

PRIMARY KEY(generation_id, input_key, position)
```

Checks:

```sql
CHECK(position >= 0)

CHECK(length(input_key) > 0)

CHECK(
    reference_role IS NULL
    OR (
        length(reference_role) BETWEEN 1 AND 64
        AND length(trim(reference_role)) > 0
    )
)

CHECK(length(blob_hash) = 64)
```

GenerationInputs are immutable historical bindings.

They never follow later ShotReference edits.

---

# 39. Deterministic GenerationInput Mapping

M1 provides a manifest-independent deterministic mapping seam:

```python
@dataclass(frozen=True)
class GenerationInputRule:
    input_key: str
    source_role: str
```

and:

```python
def resolve_generation_inputs(
    revision_snapshot: ShotRevisionSnapshot,
    rules: Sequence[GenerationInputRule],
) -> list[ResolvedGenerationInput]:
    ...
```

The function is:

* synchronous
* pure
* deterministic
* database-independent
* filesystem-independent
* network-independent

It may inspect only:

```text
immutable ShotRevision snapshot
+
explicit rules
```

It must not inspect:

* current Shot rows
* current ShotReferences
* Asset rows
* Blob rows
* filesystem state

## 39.1 Rule validation

Each `input_key` identifies one workflow-semantic input.

Therefore:

```text
duplicate input_key
→ reject
```

The same `source_role` may feed multiple distinct input keys:

```text
reference_image ← reference
character_image ← reference
```

is valid.

Do not reject duplicate `source_role` values across different input keys.

Reject:

* empty input key
* empty/whitespace-only source role
* source role longer than 64 characters
* duplicate input key

## 39.2 No-match behavior

If a rule matches zero revision references:

```text
emit zero GenerationInputs for that rule
```

M1 does not enforce:

* required-input semantics
* minimum cardinality
* maximum cardinality

Those belong to the later Workflow Manifest layer.

## 39.3 Deterministic ordering

Normalize rules by:

```text
input_key
```

For each rule, matching references retain deterministic snapshot order:

```text
role
position
asset_id
```

Output is ordered by:

```text
input_key
position
```

Positions are zero-based per `input_key`.

---

# 40. Atomic Generation + GenerationInput Persistence

Expose one persistence primitive:

```python
async def create_generation(
    draft: GenerationDraft,
    inputs: Sequence[ResolvedGenerationInput],
) -> Generation:
    ...
```

Do not expose Generation and input persistence as independently committed operations.

Transaction:

```text
BEGIN
↓
verify active Shot
↓
verify ShotRevision belongs to Shot
↓
validate immutable input bindings
↓
allocate generation_number
↓
insert Generation(status='queued')
↓
insert all GenerationInputs
↓
COMMIT
```

Any failure rolls back the entire operation.

Never allow:

```text
Generation row committed
+
partial/missing GenerationInputs
```

M3A later reuses this persistence seam.

---

# 41. Takes

Schema:

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

Check:

```sql
CHECK(length(output_key) > 0)
```

M1 establishes deterministic structural output identity only.

No output import occurs in M1.

---

# 42. Stable API Error Envelope

All SoloRing domain errors use:

```json
{
  "error_code": "...",
  "message": "...",
  "details": {}
}
```

Content type:

```text
application/json
```

Examples:

```text
PROJECT_NOT_FOUND
SHOT_NOT_FOUND
ASSET_NOT_FOUND
BLOB_NOT_FOUND

UPLOAD_TOO_LARGE
EMPTY_UPLOAD

REFERENCE_SET_INVALID

VALIDATION_ERROR

INTERNAL_INVARIANT_VIOLATION
```

---

# 43. FastAPI Validation Error Normalization

Register an exception handler for:

```python
RequestValidationError
```

so malformed JSON and Pydantic request validation use the same response envelope.

Example:

```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Request validation failed.",
  "details": {
    "errors": []
  }
}
```

Do not expose FastAPI's unrelated default 422 response shape alongside SoloRing errors.

---

# 44. Malformed UUID Policy

Entity path IDs are accepted as strings and validated inside SoloRing domain handling.

For normal entity APIs:

```text
malformed UUID
or
well-formed missing UUID
```

produce the same entity-specific 404.

Example:

```text
GET /shots/not-a-uuid
→ 404 SHOT_NOT_FOUND
```

Blob hashes are different because their syntax is part of the storage boundary:

```text
malformed Blob hash
→ 400
```

---

# 45. M1 API Surface

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

## Blobs

```text
GET  /blobs/{prefix1}/{prefix2}/{hash}
HEAD /blobs/{prefix1}/{prefix2}/{hash}
```

M1 does not expose:

```text
POST /shots/{id}/generations
POST /generations/{id}/cancel
POST /generations/{id}/rerun
SSE
approval
rejection
```

---

# 46. Response Models

Never return ORM objects directly.

Use explicit response schemas for:

* Project
* Shot
* ShotReference
* ShotRevision summary
* Asset
* Blob-facing metadata
* stable errors

Never expose:

* absolute filesystem paths
* internal storage directories
* SQLAlchemy internals
* deferred provenance payloads unintentionally

Asset upload responses may include:

```text
asset ID
Blob hash
detected media type
original filename
Blob URL
```

but never local paths.

---

# 47. Session Discipline

## Normal operations

Use short `AsyncSession` units of work.

## Upload

Do not use a request-scoped DB dependency that remains open for the complete file upload.

Required:

```text
short session
→ verify Project
→ close

stream/hash/place file
→ no DB session

short transaction
→ persist Blob/Asset
→ close
```

## Revision capture

Use a bounded consistent read and close it before canonicalization/hash computation.

## Generation persistence

Use one short atomic write unit.

---

# 48. M1 Slice Order

## M1A — Schema and canonical primitives

Build:

* migration `0002`
* all M1 ORM models
* all FKs
* all checks
* all indexes
* explicit constraint names
* enums
* central timestamp helper
* `ShotIntent`
* canonical JSON
* text normalization primitives
* migration tests

Gate:

```text
M0 regression suite green
+
schema/migration suite green
```

---

## M1B — Projects, Shots, numbering

Build:

* Project API/service
* Shot API/service
* soft-delete semantics
* parent-active atomic Shot creation
* Shot numbering
* numbering collision policy
* working snapshot hash
* API response/error infrastructure

Gate:

```text
CRUD
+
soft-delete
+
concurrent numbering
+
validation-envelope tests
+
all prior tests
```

---

## M1C — References and revisions

Build:

* reference validation
* atomic replacement
* server position normalization
* snapshot builder
* revision capture
* revision reuse
* revision-number collision retry
* revision list summaries

### M1C fixture rule

The complete Blob/Asset schema already exists from M1A.

During M1C, Blob and Asset fixtures required by reference tests are created directly through repository/ORM test fixtures.

The HTTP upload pipeline itself is not required until M1D.

Once M1D closes, add a full integration test:

```text
upload Asset
→ attach as ShotReference
→ capture ShotRevision
→ verify Asset ID + Blob hash in canonical snapshot
```

Gate:

```text
reference atomicity
+
canonical byte tests
+
revision race tests
+
all prior tests
```

---

## M1D — Blobs, Assets, upload, serving

Build:

* Blob/Asset repositories
* same-filesystem startup validation
* media signature detector
* streamed uploads
* empty upload rejection
* upload limits
* filename bounds
* atomic placement
* duplicate Blob convergence
* integrity repair/logging
* Blob structural validation
* GET/HEAD
* Range
* immutable caching
* upload→reference→revision integration test

Gate:

```text
upload race matrix
+
integrity tests
+
Range tests
+
storage-boundary tests
+
all prior tests
```

---

## M1E — Generation identity and Takes

Build:

* full Generation ORM
* `updated_at`
* status/operation/executor checks
* deferred columns
* frozen `GenerationDraft`
* JSON syntax validation
* Generation numbering
* deterministic GenerationInput mapping
* atomic Generation+input persistence
* Take schema/output identity

Gate:

```text
Generation schema tests
+
numbering races
+
input determinism
+
atomic persistence
+
Take uniqueness
+
all prior tests
```

---

# 49. Migration Testing

## 49.1 Populated `0001 → 0002`

Start with:

```text
database at 0001
+
populated worker_leases row
```

Upgrade to `0002`.

Verify:

* worker lease unchanged
* every M1 table exists
* every required constraint exists
* required indexes exist
* SQLite PRAGMAs remain correct
* `PRAGMA foreign_key_check` returns no violations

Downgrade to `0001`.

Verify:

* worker lease still unchanged
* all M1 tables removed
* no `_alembic_tmp_*` tables remain

## 49.2 Structural migration preservation

Migration `0002` creates new tables.

It does not structurally alter an existing populated M1 table.

Therefore `0002` is **not** a populated `batch_alter_table` data-preservation test.

The first future migration that restructures an existing populated table must add a genuine preservation test.

Do not introduce a fake structural migration merely to satisfy this test category.

---

# 50. Required M1 Acceptance Matrix

## 50.1 M0 regression

* every closed-M0 test remains green

## 50.2 Migration/schema

* populated `0001 → 0002` preserves M0 state
* downgrade restores valid `0001`
* `foreign_key_check` clean
* all constraints explicitly named
* all enum CHECKs reject invalid values
* `ix_assets_blob_hash` exists
* `ix_shots_approved_take_id` exists
* no unexpected redundant custom indexes
* no Alembic temp tables remain

## 50.3 Projects

* create/read/update/list
* name trimmed
* blank name rejected
* overlong name rejected
* description blank → NULL
* Project DELETE updates Project timestamps
* only active child Shots receive deletion timestamp
* previously deleted child timestamp remains unchanged
* repeat DELETE → 204
* mutations against deleted Project fail

## 50.4 Shots

* subject normalization
* blank/whitespace-only subject rejected
* optional empty creative strings → NULL
* `approved_take_id` cannot be patched
* successful PATCH updates `updated_at`
* Shot DELETE preserves historical rows
* repeat DELETE → 204
* first number = 1
* deleted number not reused
* concurrent creation yields unique sequence
* Project deletion race cannot insert a new Shot
* raw numbering `IntegrityError` never leaks

## 50.5 References

* roles are exact/case-sensitive
* whitespace-only role rejected
* role >64 rejected
* server assigns position
* positions contiguous per role
* duplicate `(asset, role)` rejected
* same Asset under different roles allowed
* cross-Project Asset rejected
* invalid replacement rolls back entirely
* identical PUT → 200 with normalized set
* replacement updates Shot `updated_at`
* no client-controlled persisted position

## 50.6 Canonicalization

* exact canonical byte fixture
* nested nulls deterministic
* empty string/null distinction tested at serializer level
* normalized domain state eliminates optional creative empty strings
* Unicode deterministic
* combining characters preserved exactly
* dictionary insertion order irrelevant
* very long subject deterministic
* reference order canonical

## 50.7 ShotRevision

* same creative state → same hash
* same state captured twice → same row
* changed subject → new revision
* reference replacement → new revision
* role change → new revision
* reorder → new revision
* removal → new revision
* concurrent identical snapshots → one row
* concurrent different snapshots survive revision-number collision
* retry exhaustion produces stable internal error, not raw DB failure

## 50.8 Upload

* upload uses bounded chunk reads
* no request-long DB session
* zero-byte upload rejected
* oversized upload rejected
* temp file removed on every failure path
* `original_filename` basename-only and bounded
* event loop remains responsive
* temp/blob directories validated as same filesystem
* physical path derives only from SHA-256
* sequential duplicate bytes → one Blob/two Assets
* concurrent duplicate bytes → one Blob/two Assets
* Blob row conflict handled normally
* every successful explicit upload creates a fresh Asset

## 50.9 Blob integrity

* registered row + missing file → 404
* integrity log contains Blob hash
* verified upload may repair missing bytes
* repair logs at high severity
* unregistered physical file is not served
* successful upload may register an existing correct hash-addressed file

## 50.10 Blob validation/serving

* malformed hash → 400 before DB lookup
* prefix mismatch → 400 before DB lookup
* unknown Blob → 404
* normal GET → 200
* valid bounded Range → 206
* open-ended Range → 206
* suffix Range → 206
* malformed Range → 416
* past-EOF Range → 416
* HEAD valid Blob → no body
* HEAD malformed hash → 400
* HEAD unknown Blob → 404
* Content-Range correct
* Content-Length correct
* Accept-Ranges present
* immutable Cache-Control present
* ETag is quoted SHA-256
* filesystem path never exposed

## 50.11 Generation schema

* all durable fields exist
* `updated_at` exists
* `prompt_compiler_version` non-null
* invalid operation rejected
* invalid status rejected
* invalid executor rejected
* executor restriction documented as v0.1-specific
* hash constraints enforced
* required draft strings non-empty
* `parameters_json` valid JSON
* `workflow_spec_json` valid JSON
* large fields deferred

## 50.12 Generation numbering/persistence

* first Generation number = 1
* numbers never reused
* concurrent inserts allocate unique numbers
* missing Shot rejected
* deleted Shot rejected atomically
* mismatched ShotRevision rejected
* Generation+inputs commit atomically
* failed input persistence leaves no Generation
* raw numbering collision does not leak DB exception
* `updated_at` generated by SQLite

## 50.13 GenerationInput mapping

* empty input key rejected
* invalid source role rejected
* duplicate input key rejected
* duplicate source role across different input keys allowed
* reversed rule order yields identical output
* source snapshot order permutations do not affect mapping
* zero matches emits zero bindings
* mapping never reads current ShotReferences
* persisted GenerationInputs remain unchanged after working-reference edits

## 50.14 Takes

* duplicate `(generation_id, output_key)` rejected
* same output key on different Generations allowed
* empty output key rejected

## 50.15 API validation

* malformed JSON uses SoloRing envelope
* invalid Pydantic fields use SoloRing envelope
* malformed entity UUID uses entity-specific 404
* domain errors use JSON envelope consistently

---

# 51. Non-Goals Verification

Before declaring M1 complete, confirm there is still no implemented path for:

```text
Generate request
→ worker queue claim
→ executor
```

Specifically absent:

* public Generation creation endpoint
* FakeExecutor execution
* ComfyExecutor execution
* Generation ownership implementation beyond M0 stubs
* worker queue claim
* cancellation execution
* output staging/import
* approval/rejection
* SSE

Generation persistence infrastructure must not accidentally collapse the M3A milestone boundary.

---

# 52. Non-Gating Enhancements

The following are useful but are not required to close M1 unless implementation cost is negligible.

## 52.1 List pagination

Potential endpoints:

```text
GET /projects
GET /projects/{id}/shots
GET /shots/{id}/revisions
```

Suggested defaults:

```text
offset = 0
limit = 50
max_limit = 200
```

Do not allow unbounded list queries if pagination is introduced.

## 52.2 Stale temp cleanup

A later operational cleanup may remove:

```text
data/tmp/*
```

older than a safety threshold such as 24 hours.

Crash-left temp files do not affect correctness because they are never database-addressable Blobs.

This cleanup is not required for M1 correctness.

---

# 53. M1 Definition of Done

M1 closes only when:

* [ ] all M0 tests remain green;
* [ ] migration `0002` creates the complete M1 schema;
* [ ] all constraints have stable explicit names;
* [ ] populated M0 state survives migration correctly;
* [ ] `PRAGMA foreign_key_check` is clean;
* [ ] Project soft-delete semantics are deterministic;
* [ ] active child Shots are soft-deleted with Project deletion;
* [ ] already-deleted child timestamps are preserved;
* [ ] Shot text normalization is deterministic;
* [ ] Shot numbers are atomic and never reused;
* [ ] active Project verification is atomic with Shot creation;
* [ ] `approved_take_id` is not mutable through M1 APIs;
* [ ] ShotReferences replace atomically;
* [ ] reference roles are exact and bounded;
* [ ] reference positions are server-owned;
* [ ] canonical JSON is byte-tested;
* [ ] snapshot schema version is present;
* [ ] optional canonical intent fields are explicit `null`;
* [ ] ShotRevision identity includes ordered reference Asset and Blob identity;
* [ ] identical concurrent revisions converge;
* [ ] different concurrent revisions survive revision-number races;
* [ ] Blob paths are relative and content-addressed;
* [ ] upload temp/final storage is guaranteed same-filesystem;
* [ ] upload remains streamed and DB-transaction-free during file I/O;
* [ ] zero-byte uploads are rejected;
* [ ] duplicate uploads produce one Blob and multiple Assets;
* [ ] `assets.blob_hash` is indexed;
* [ ] Blob integrity anomalies are detected and logged;
* [ ] verified upload repair is explicit and logged;
* [ ] malformed Blob addresses fail before DB lookup;
* [ ] GET/HEAD/Range semantics are complete;
* [ ] immutable Blob caching is enabled;
* [ ] Generation schema is complete;
* [ ] `generations.updated_at` exists and uses SQLite time;
* [ ] Generation status/operation/executor values are constrained;
* [ ] required recovery indexes exist;
* [ ] large Generation payloads are deferred;
* [ ] `GenerationDraft` is immutable and validates basic syntax;
* [ ] Generation numbers are atomic and never reused;
* [ ] active Shot validation is atomic with Generation persistence;
* [ ] Generation and GenerationInputs persist atomically;
* [ ] GenerationInput mapping is pure and deterministic;
* [ ] duplicate source roles across different input keys remain legal;
* [ ] Takes enforce deterministic per-Generation output identity;
* [ ] validation errors use one API envelope;
* [ ] response models prevent internal path leakage;
* [ ] no public execution path has been implemented;
* [ ] full M1 test suite passes.

---

# 54. Handoff State

At M1 completion:

```text
Mutable Shot
  ↓
Normalized Creative State
  ↓
Ordered ShotReferences
  ↓
Canonical Versioned ShotRevision
  ↓
Durable Generation Record
  ↓
Immutable GenerationInputs
```

Storage is independently complete:

```text
Uploaded Bytes
  ↓
SHA-256
  ↓
Content-Addressed Blob
  ↓
Explicit Asset Provenance
```

M2 can build creative interaction and prompt compilation against stable working-state and snapshot primitives.

M3A can build Generation orchestration against:

* immutable ShotRevisions;
* deterministic GenerationInputs;
* complete durable Generation schema;
* atomic Generation persistence;
* race-safe numbering;
* durable Blob/Asset storage.

Until M3A:

> The execution specification can be persisted, but no model execution occurs.
