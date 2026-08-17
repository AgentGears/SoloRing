# SoloRing M2 — Creative UI Implementation Plan

## 1. Objective

M2 turns the closed M1 foundation into the usable creative surface and delivers
the final creative-layer backend primitives that depend on no execution
infrastructure:

```text
Project / Shot browsing + editing          (UI over M1B APIs)
reference upload / attach / reorder        (UI over M1C/M1D APIs)
prompt compiler + version                  (pure backend primitive, v0.1 §35)
working-state vs approved-canon comparison (backend computation, v0.1 §94)
```

Exit criterion (v0.1 §108):

> Creative working state has deterministic immutable snapshot semantics.

M2 demonstrates this through the UI: every creative edit flows through server
normalization → canonical snapshot construction → `working_snapshot_hash`, and
the visible hash changes exactly when canonical creative state changes.
Requests that normalize to the same canonical state leave the hash unchanged.

M2 does **not** make anything executable. There is no Generate button, queue,
worker lifecycle, progress stream, output import, Take review, or approval
mutation. Until M3A creates real candidate Takes, the Approved Take surface is
an honest no-canon state rather than a placeholder that implies execution is
available.

---

# 2. Milestone Boundary

## 2.1 Included

### Backend

* pure prompt compiler (`compile_prompt`) with pinned version;
* byte-stable prompt escaping/serialization rules;
* prompt-compiler determinism and raw UTF-8 byte fixtures;
* working-state-vs-approved comparison computation;
* `working_state_differs_from_approved` on Shot detail;
* no-approved-Take comparison semantics;
* strict approved-provenance integrity validation;
* synthetic Take/Generation/Revision comparison tests before M3A exercises the
  path live;
* lightweight Project Asset listing for persistent reference-asset discovery;
* backend-canonical content-addressed Blob URLs plus one browser proxy mapper;
* optional Asset-kind filtering with `reference` as the M2 default.

### Frontend

* typed browser/server API clients with a shared error abstraction;
* server-only absolute API origin for Server Components;
* browser-relative `/api/*` calls through the Next.js rewrite;
* global stable-error rendering (`error_code` + `message`);
* normalized network-failure rendering rather than raw `fetch` exceptions;
* Projects page: list / create / open / delete;
* Project page: shot list / create / delete, with historical shot numbering
  visible;
* persistent Project Asset list;
* Shot editor for `title` plus every `ShotIntent` field;
* PATCH-on-save with normalized values and `updated_at` feedback;
* reference upload into the Project;
* reference attachment from persistent Project Asset discovery;
* visually role-grouped references;
* deterministic role-scoped move-up/move-down ordering;
* role change and removal through the same atomic full-set PUT;
* image thumbnails through content-addressed Blob URLs;
* generic fallback for non-image/octet-stream Assets;
* Current Working State panel with `working_snapshot_hash` and canon-diff state;
* Approved Take panel with an honest no-canon state;
* revision summary list and deliberate empty/loading states;
* loading feedback around Server Component refreshes;
* production `next build` gates with FastAPI stopped.

## 2.2 Explicitly excluded

* public Generation creation endpoint or UI;
* queue claiming, worker Generation ownership, Generation heartbeat, or progress;
* SSE;
* FakeExecutor or ComfyExecutor;
* output staging/import;
* review grid or Take display;
* approve/reject mutations;
* Exact Rerun or provenance viewer UI;
* frontend pagination;
* Asset deletion UI;
* auth or multi-user behavior;
* theming/UI kits;
* drag-and-drop dependencies;
* new frontend state-management libraries;
* new component-test framework;
* frontend canonical JSON, hashing, or approved-comparison logic;
* optimistic-concurrency tokens for Shot PATCH or reference replacement.

---

# 3. Backend Additions

## 3.1 Prompt compiler

Location:

```text
server/soloring/domain/prompt.py
```

The module belongs to the creative domain. Executor and workflow packages may
consume its persisted result later, but they never own compiler behavior.

```python
PROMPT_COMPILER_VERSION = "1"


def compile_prompt(intent: ShotIntent) -> str:
    ...
```

The version constant is a literal module-level constant. It is not read from an
environment variable, configuration file, database row, or mutable registry.

### 3.1.1 Purity contract

`compile_prompt` is:

* synchronous;
* deterministic;
* database-independent;
* filesystem-independent;
* network-independent;
* LLM-independent;
* free of hidden mutable configuration.

It receives normalized persisted `ShotIntent`. The compiler does not redefine
Shot normalization. In particular, optional creative fields are expected to be
`None` rather than empty strings after persistence normalization.

Defensive skipping of a whitespace-only optional value is permitted only as a
compiler guard; it does not become a second canonical normalization policy.

### 3.1.2 Exact v1 textual format

Labels are fixed **English protocol strings** and are neither localizable nor
configurable in compiler version 1.

Fixed label/order:

```text
Subject
Action
Environment
Framing
Camera Motion
Lens
Mood
```

Each present field emits:

```text
Label: encoded-value
```

Logical records are joined with the literal LF code point:

```text
\n
```

Compiler output contains:

* LF line separators only;
* no CRLF conversion;
* no trailing newline;
* no Unicode normalization;
* no locale-sensitive formatting.

`duration_ms` is accepted as part of `ShotIntent` but has **no effect** on v1
compiled-prompt identity. It is temporal metadata consumed later by workflow
construction.

v1 defines no negative prompt:

```text
negative_prompt = None
```

The existing Generation field remains the future carrier.

### 3.1.3 Value escaping and control characters

The prompt is line-oriented, so literal record separators and C0 controls cannot
be inserted raw without violating the one-record-per-field contract. Compiler
v1 therefore applies **serialization escaping**, not domain normalization, to
each emitted value. Persisted Shot text is not rewritten.

Escaping is applied in this exact order:

1. escape every literal backslash (`U+005C`);
2. escape carriage return (`U+000D`), line feed (`U+000A`), and tab (`U+0009`);
3. escape every remaining C0 control (`U+0000`–`U+001F`) and DEL (`U+007F`).

The mapping below is expressed in terms of literal input code points and literal
ASCII characters emitted into the compiled value:

| Input | Emitted characters |
|---|---|
| `U+005C` BACKSLASH | two backslashes: `\\` |
| `U+000D` CR | backslash + `r`: `\r` |
| `U+000A` LF | backslash + `n`: `\n` |
| `U+0009` TAB | backslash + `t`: `\t` |
| remaining `U+0000`–`U+001F`, plus `U+007F` | six ASCII characters `\u00xx`, with lowercase hex |

Examples:

```text
input code points:    C : \ r e f s \ e v a
emitted value text:  C : \\ r e f s \\ e v a
```

```text
input value contains: enters the <LF> lobby
emitted value text:  enters the\nlobby
```

C1 controls (`U+0080`–`U+009F`) are **not** escaped in compiler v1. Unicode
line/paragraph separators `U+2028` and `U+2029` are also preserved verbatim.
Only ASCII LF (`U+000A`) separates compiler records. This distinction is
deliberate and byte-pinned.

All other Unicode code points, including combining characters, are preserved
exactly. No NFC/NFD normalization is performed.

The compiler output is later encoded as UTF-8 for byte fixtures and persisted as
the exact Python string returned by `compile_prompt`.

### 3.1.4 Golden fixture

Input:

```python
ShotIntent(
    subject="Eva",
    action="enters the lobby",
    environment="hotel lobby",
    framing="medium wide",
    camera_motion="slow push-in",
    lens="50mm",
    mood="restrained unease",
    duration_ms=5000,
)
```

Exact UTF-8 byte fixture:

```python
EXPECTED = (
    b"Subject: Eva\n"
    b"Action: enters the lobby\n"
    b"Environment: hotel lobby\n"
    b"Framing: medium wide\n"
    b"Camera Motion: slow push-in\n"
    b"Lens: 50mm\n"
    b"Mood: restrained unease"
)

assert compile_prompt(intent).encode("utf-8") == EXPECTED
```

`duration_ms=5000` is deliberately present in the fixture input and absent from
the expected output.

Golden expectations are stored/asserted as explicit UTF-8 bytes, not through
platform text-file newline translation.

### 3.1.5 Version policy

Any change to output bytes for an existing input requires a new:

```text
PROMPT_COMPILER_VERSION
```

This includes changes to:

* labels;
* label order;
* field inclusion;
* escaping;
* line endings;
* whitespace;
* Unicode treatment;
* negative-prompt behavior.

A changed fixture with an unchanged version is a failing test, not an accepted
compiler update. M3A must persist the exact compiled string together with the
exact `PROMPT_COMPILER_VERSION` that produced it; recompiling historical intent
is never a substitute for stored Generation provenance.

### 3.1.6 Structural purity test

Use an AST-based test for `domain/prompt.py`, not a loose text grep.

At minimum reject direct imports of:

```text
sqlalchemy
asyncio
os
pathlib
subprocess
socket
http
urllib
requests
httpx
aiohttp
soloring.db
soloring.assets
soloring.executors
soloring.worker
```

The compiler may depend on the creative `ShotIntent` type and standard-library
string logic only.

---

## 3.2 Working state vs approved canon

The server already computes `working_snapshot_hash` through the canonical
snapshot builder used for ShotRevision identity. M2 adds server-side comparison
against explicit canon.

```text
approved_take_id IS NULL
→ working_state_differs_from_approved = false
```

This means **no canon exists to differ from**. It does not mean that the current
working state matches an approved result. The client interprets this together
with:

```text
approved_take_id = null
```

and renders:

```text
No approved Take yet.
```

For a non-null approval pointer, comparison follows the complete provenance
chain:

```text
Shot.approved_take_id
        ↓
Take
        ↓
Generation
        ↓
ShotRevision.snapshot_hash
```

Required validation:

```text
approved Take exists
AND Take.shot_id == Shot.id
AND Generation exists
AND Generation.id == Take.generation_id
AND Generation.shot_id == Shot.id
AND ShotRevision exists
AND ShotRevision.id == Generation.shot_revision_id
AND ShotRevision.shot_id == Shot.id
```

Only after the full chain is validated:

```text
working_state_differs_from_approved
=
working_snapshot_hash != approved_revision.snapshot_hash
```

Common Shot ownership inferred indirectly is insufficient; every persisted
provenance link must be followed explicitly.

The Shot working snapshot and approved provenance chain are read inside one
bounded consistent database read unit: **one checked-out database connection
and one explicit SQLite read transaction, with no intermediate commit/rollback
or secondary connection/session.** (Amended during M2A: Python sqlite3's legacy
transaction handling does not open a driver transaction for SELECT-only
AsyncSession sequences, so an AsyncSession alone holds no WAL read snapshot on
this stack; the explicit-`BEGIN` one-connection unit delivers the actual
invariant.) A concurrent edit may land before or after that read snapshot, but
one response must never combine working state from one database snapshot with
approved provenance from another.

### 3.2.1 Integrity failure

A non-null `approved_take_id` with any dangling or cross-Shot provenance is a
ledger invariant violation.

Behavior:

```text
log integrity error
→ raise INTERNAL_INVARIANT_VIOLATION
→ never silently return false
```

The log must include safe diagnostic identifiers:

```text
shot_id
approved_take_id
broken/mismatched provenance link
relevant Take/Generation/ShotRevision ID when available
```

The API error `details` may include these identifiers and link classification,
but never filesystem paths or internal SQL.

### 3.2.2 API shape

`GET /shots/{id}` adds:

```text
working_state_differs_from_approved: bool
```

`GET /projects/{id}/shots` remains lightweight and does not add either working
hash or comparison logic.

The frontend never recomputes:

* canonical JSON;
* `working_snapshot_hash`;
* approved revision identity;
* differs state.

---

## 3.3 Project Asset discovery

Reference Assets must remain discoverable after refresh, navigation, or opening
the Shot editor in another tab. Upload response state is not authoritative
Asset discovery.

M2 deliberately amends the v0.1 API surface in §99 by adding:

```text
GET /projects/{id}/assets
```

The original v0.1 §99 surface listed only:

```text
POST /projects/{id}/assets
GET  /assets/{id}
```

The new list endpoint is an explicit API-contract extension required by the M2
creative workflow, not an accidental frontend convenience.

### 3.3.1 Query contract

Optional query:

```text
kind=reference|output
```

Default:

```text
kind=reference
```

The filter is parsed against the existing `AssetKind` domain. Invalid values are
normalized through the SoloRing error envelope:

```text
GET /projects/{id}/assets?kind=bogus
→ 422 VALIDATION_ERROR
```

M2 produces no output Assets, but accepting the existing `AssetKind` domain
allows later milestones to expose output Assets without changing Asset identity
or inventing a second project list endpoint.

Project must exist and be active. Ordering is deterministic:

```text
ORDER BY created_at, id
```

Pagination remains a future enhancement. The Asset endpoint does not return a
role catalog; reference roles remain explicit Shot-reference intent selected by
the editor.

### 3.3.2 Shared Asset DTO

M2 uses one shared Asset response model for upload, `GET /assets/{id}`, and the
Project Asset list. Extend `AssetRead` additively with:

```text
detected_media_type
```

The existing distinction remains intact:

```text
upload_mime_type      = client-declared upload provenance
detected_media_type    = Blob-derived serving/media metadata
```

Because `detected_media_type` belongs to the Blob row, Asset detail/list queries
join or otherwise load the referenced Blob explicitly. Do not infer it from
`upload_mime_type`.

`POST /projects/{id}/assets`, `GET /assets/{id}`, and
`GET /projects/{id}/assets` all serialize the same `AssetRead` contract. The
Project list does not invent a second reduced DTO; frontend code simply consumes
the selection-oriented subset it needs. Existing `AssetRead` fields remain
additive/stable, with `detected_media_type` added once to the shared model.

No Asset response exposes absolute filesystem paths or storage roots.

### 3.3.3 Canonical Blob URL boundary

The FastAPI/backend contract remains the closed M1D canonical form:

```text
/blobs/<hash[0:2]>/<hash[2:4]>/<hash>
```

Therefore `AssetRead.blob_url` is always backend-canonical:

```text
/blobs/<hash[0:2]>/<hash[2:4]>/<hash>
```

FastAPI never emits `/api/blobs/...` and never knows that Next.js uses an `/api`
proxy. This preserves the M1D storage/API contract and keeps frontend routing
concerns out of backend DTOs.

Browser code has exactly one mapping boundary in `api.client.ts`:

```text
backend blob_url:   /blobs/aa/bb/<hash>
browser blob_url:   /api/blobs/aa/bb/<hash>
```

The mapper accepts only canonical leading `/blobs/` URLs and prefixes `/api`.
It does not accept absolute backend origins or arbitrary paths. Client
components use the mapped value for `<img>`/download requests.

Server Components may fetch Asset metadata from FastAPI but pass the canonical
`blob_url` through as data; browser rendering performs the single client-side
proxy mapping.

Serving truth remains M1D's Blob endpoint:

```text
Content-Type = blob.detected_media_type or application/octet-stream
Cache-Control: public, max-age=31536000, immutable
ETag: "<sha256>"
```

### 3.3.4 Project scoping

Asset selection is Project-scoped. The existing atomic reference replacement
service remains the authoritative integrity boundary:

```text
asset.project_id must equal shot.project_id
```

The frontend filters choices for usability, but it never substitutes client-side
filtering for the server check.

---

## 3.4 M2 backend API delta

M2 deliberately amends the final v0.1 API contract with exactly these backend
changes:

```text
GET /shots/{id}
  + working_state_differs_from_approved

GET /shots/{id}/references        (M2C amendment: reading the persisted set)

GET /projects/{id}/assets
  ?kind=reference|output

GET /assets/{id}
POST /projects/{id}/assets
  AssetRead gains detected_media_type additively
```

The `GET /shots/{id}/references` endpoint is a deliberate second v0.1 §99
amendment (M2C): M1 exposed only the PUT, and reference editing plus
refresh-safe UI require reading the current canonical set. It returns
`ReferenceRead` rows in canonical (role, position) order, symmetric with the
PUT's response.

Invalid Asset-kind filters use:

```text
422 VALIDATION_ERROR
```

No Generation, queue, Take mutation, approval, cancellation, progress, SSE, or
execution endpoint is added.

---

# 4. Frontend Architecture

M2 uses the M0 frontend baseline:

```text
Next.js 14 App Router
React
TypeScript
plain CSS
```

No runtime UI/state dependency is added.

Server Components perform authoritative reads. Client Components own local
form/mutation state. `router.refresh()` is used after successful writes to
refresh server-derived hashes, timestamps, lists, and comparison fields.

---

## 4.1 Layout

Use explicit server/client API modules so server configuration cannot be
accidentally imported into Client Components.

```text
apps/web/src/
├── lib/
│   ├── api.shared.ts      ApiError + envelope parsing/common DTO helpers
│   ├── api.client.ts      browser-only /api calls + canonical Blob URL mapper
│   ├── api.server.ts      Server Component absolute-origin calls
│   └── types.ts           API DTOs
│
├── app/
│   ├── page.tsx
│   ├── loading.tsx
│   ├── projects/[id]/
│   │   ├── page.tsx
│   │   └── loading.tsx
│   └── shots/[id]/
│       ├── page.tsx
│       └── loading.tsx
│
└── components/
    ├── ErrorBanner.tsx
    ├── ProjectActions.tsx
    ├── ShotForm.tsx
    ├── ReferencePanel.tsx
    ├── ReferenceRoleGroup.tsx
    ├── ReferenceRow.tsx
    ├── WorkingStatePanel.tsx
    ├── ApprovedTakePanel.tsx
    └── RevisionList.tsx
```

If the scaffold already provides a supported server-only import guard, use it
in `api.server.ts`. Otherwise enforce the boundary through module separation,
Client Component import review, and emitted-bundle checks; do not add a new
runtime package only for this marker.

---

## 4.2 API origin and rendering policy

M2 standardizes the frontend/backend origin setting on one repository-wide name:

```text
SOLORING_API_ORIGIN
```

The M0 scaffold's older `SOLORING_API_URL` setting is removed/migrated. Do not
introduce `SOLO_RING_API_ORIGIN`; the repository uses the `SOLORING_*` prefix.

`SOLORING_API_ORIGIN` is the single origin consumed by:

* `next.config.mjs` for the browser `/api/*` rewrite target; and
* `api.server.ts` for Server Component requests.

There are no two competing backend-origin settings.

### Browser

Browser mutations and browser-side reads use:

```text
/api/*
```

through the existing Next.js rewrite. The rewrite must preserve normal request
headers and bodies, including multipart upload requests. The live smoke gate
uploads through the Next proxy, not directly to FastAPI, so forwarding is tested
in the actual M2 path.

Backend `AssetRead.blob_url` values remain `/blobs/...`; only the mapper in
`api.client.ts` converts those to `/api/blobs/...` for browser requests.

### Server Components

Server Components use the absolute server-only origin:

```text
SOLORING_API_ORIGIN=http://127.0.0.1:8000
```

`SOLORING_API_ORIGIN`:

* has no `NEXT_PUBLIC_` prefix;
* is read only from server-only code/configuration;
* never appears in Client Component props;
* never appears in emitted client JavaScript.

Pages that require live SoloRing data are dynamically rendered. `next build`
must not contact FastAPI.

Build proof:

```text
FastAPI stopped
+
SOLORING_API_ORIGIN points at an unreachable local address
→ npm run build still succeeds
```

The build gate also scans emitted client bundles for the configured origin
literal and fails if it appears. This prevents accidental build-time/backend
coupling and server-origin leakage.

---

## 4.3 Shared API error abstraction

Both server and browser clients parse the SoloRing envelope:

```json
{
  "error_code": "...",
  "message": "...",
  "details": {}
}
```

into one typed `ApiError` abstraction.

Network-level failures such as:

```text
connection refused
timeout
DNS/network failure
malformed non-envelope response
```

are also translated into a controlled `ApiError` form. Raw `TypeError: fetch
failed`, stack traces, or HTML proxy errors never render directly in UI
components.

`ErrorBanner` remains intentionally minimal:

```text
error_code
message
```

Diagnostic details stay available to developer logging and do not need a
request-id/timestamp UI in M2.

---

## 4.4 Mutation and refresh discipline

After every successful mutation that may affect Shot creative state, the UI
must refresh server truth and immediately show the resulting
`working_snapshot_hash`.

Required operations:

```text
Shot intent/title save
reference attachment
reference reorder
reference role change
reference removal
```

The result may be:

```text
canonical state changed
→ hash changes

request normalized to existing canonical state
→ hash remains identical
```

Both outcomes are meaningful and visible.

Client forms retain local state while a Server Component refresh is in flight.
A refresh must not overwrite unrelated unsaved local edits merely because
server props changed. After a successful save, controlled state may reconcile
to the normalized server response.

`loading.tsx`/pending affordances distinguish:

```text
refreshing/loading
```

from deliberate empty states.

---

## 4.5 Reference interaction semantics

### Visual grouping

References are displayed in distinct role groups. A flat list that implies a
global cross-role order is prohibited.

Example:

```text
reference
  Asset A   ↑ ↓
  Asset B   ↑ ↓

character
  Asset C   ↑ ↓

style
  Asset D   ↑ ↓
```

Move controls operate only inside one role group.

### Full-set replacement

Every attach, detach, role change, or reorder emits the complete desired set to:

```text
PUT /shots/{id}/references
```

The server owns persisted positions and re-normalizes positions contiguously per
role.

Role change therefore re-normalizes both:

```text
source role group
destination role group
```

The frontend never supplies persisted `position` as an authoritative user
field; it supplies ordered reference intent and consumes the normalized server
response.

### Concurrency policy

M2 intentionally retains M1's full-set replacement semantics without an
optimistic-concurrency token.

Policy:

```text
single-user / multi-tab
last successful PUT wins
```

Known failure mode:

```text
Tab A and Tab B load different historical reference sets
→ both mutate
→ later full-set PUT may overwrite an intermediate edit from the other tab
```

This is a **lost intermediate edit**, not partial database corruption: each PUT
is transactionally validated and atomic, and invalid payloads leave the prior
set unchanged.

M2 accepts this v0.1 risk explicitly. No claim of multi-tab lost-update safety
is made.

Deferred real fix:

```text
optimistic concurrency precondition
(e.g. working_snapshot_hash / reference-set version)
→ 409 on stale replace
```

A pre-mutation re-fetch may be used as a UX improvement, but it does not replace
an actual concurrency token and is not treated as correctness protection.

---

## 4.6 Reference Asset presentation

Image media:

```text
image/png
image/jpeg
```

render as browser `<img>` thumbnails through the client-mapped `/api` Blob URL derived from canonical `blob_url`.

Unknown/octet-stream media renders a small generic local icon or inline SVG; it
must not render a deliberately broken `<img>`.

No remote image host or image-optimization dependency is needed for v0.1.

Asset rows show enough provenance to distinguish repeated filenames, for
example:

```text
original_filename
created_at
short Blob-hash suffix/prefix
```

The full Blob hash remains available in the API and diagnostic UI where useful.

---

## 4.7 Shot editor semantics

Editable fields:

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

Optional text inputs:

```text
empty UI value
→ server normalization
→ NULL
```

Duration:

```text
empty UI value → null
0             → 0
negative      → validation envelope
```

The UI labels duration as temporal metadata, visually separate from textual
prompt fields, because compiler v1 deliberately excludes `duration_ms`.

Shot list pages do not display `working_snapshot_hash`; hash identity remains a
Shot-detail concern in M2.

---

## 4.8 Route error and deleted-hierarchy UX

Projects and Shots are soft-deleted server-side. Normal list behavior:

```text
deleted Project → omitted
deleted Shot    → omitted
```

M2 has no trash/recovery UI and no deleted badge. Direct navigation to a
missing/deleted entity renders the controlled entity-specific error state rather
than crashing the route. Repeat DELETE is silent/idempotent from the user's
perspective.

A broken non-null approved provenance chain is intentionally more severe. If
Shot detail returns `INTERNAL_INVARIANT_VIOLATION`, the Shot route renders a
controlled integrity-error state instead of the editor/canon panels. The page
does not reinterpret that failure as `No approved Take yet` or `Matches canon`.
This makes the consequence of ledger corruption explicit: the affected Shot
detail is unavailable until the invariant is repaired.

---

# 5. Slice Order

## M2A — Prompt compiler + working-state comparison

Build:

* `domain/prompt.py`;
* literal `PROMPT_COMPILER_VERSION = "1"`;
* v1 control-character escaping;
* UTF-8/LF golden byte fixtures;
* AST purity test;
* approved comparison service;
* strict Take → Generation → ShotRevision validation;
* `ShotRead.working_state_differs_from_approved`;
* synthetic provenance tests;
* structural single-session/no-intermediate-commit comparison assertion;
* deterministic interleave test proving one SQLite read snapshot.

Gate:

```text
all pre-M2 backend tests green
+
all M2A tests green
```

No predecessor test count is hard-coded.

---

## M2B — Project Asset API + frontend foundation

Build backend:

* `GET /projects/{id}/assets`;
* optional `kind` filter, default `reference`;
* deterministic `(created_at, id)` ordering;
* shared `AssetRead` including Blob-derived `detected_media_type`;
* backend-canonical content-addressed `/blobs/...` URLs;
* invalid `kind` → `422 VALIDATION_ERROR`;
* Project scoping/error tests.

Build frontend:

* `api.shared.ts`;
* `api.client.ts` with the only `/blobs/...` → `/api/blobs/...` mapper;
* `api.server.ts`;
* DTO types;
* ErrorBanner;
* global CSS/loading states;
* Projects list/create/delete;
* Project page shell;
* Shot list/create/delete;
* Project Asset list;
* migration from `SOLORING_API_URL` to the single `SOLORING_API_ORIGIN`.

Gate:

```text
all backend tests green
+
Project Asset list reachable, correctly Project-scoped, and deterministic
+
invalid Asset kind returns 422 VALIDATION_ERROR
+
npm run build green with FastAPI stopped and unreachable SOLORING_API_ORIGIN
+
client bundle contains no SOLORING_API_ORIGIN value/backend-origin literal
+
live smoke: project CRUD + Shot CRUD + Project Asset list
```

---

## M2C — Shot editor + upload + references

Build:

* ShotForm;
* controlled local edit state;
* normalization round-trip;
* `updated_at` feedback;
* reference upload through Next `/api` rewrite;
* persistent Asset selection;
* role-grouped ReferencePanel;
* attach/detach;
* role edit;
* role-scoped move-up/down;
* image thumbnails + generic fallback;
* hash refresh after every successful creative mutation.

Gate:

```text
npm run build green
+
edit subject → hash changes
+
attach reference → hash changes
+
same-role reorder → hash changes
+
role change → both role groups normalized + hash changes
+
remove reference → hash changes
+
identical full-set PUT → 200 + hash unchanged
+
no cross-role move control rendered
+
browser refresh → Assets rediscovered from server
+
cross-Project Asset attach → stable envelope + reference state unchanged
+
zero-byte upload → EMPTY_UPLOAD + local/reference state unchanged
+
PNG/JPEG thumbnail loads through /api Blob URL with immutable cache headers
+
octet-stream Asset uses generic icon
```

---

## M2D — Working/canon panel + revisions + full-stack gate

Build:

* WorkingStatePanel;
* full working hash display with line wrapping/copy-friendly presentation;
* explicit `No approved Take yet` state;
* differs badge only when canon exists;
* RevisionList;
* deliberate revision-empty state;
* loading vs empty-state polish;
* route-level error presentation.

Gate:

```text
npm run build green
+
full backend suite green
+
full-stack browser walkthrough:
    project
    → shot
    → edit creative fields
    → upload PNG
    → attach
    → role-group reorder
    → role change
    → remove
    → observe deterministic hash transitions
    → browser refresh and rediscovery
    → force envelope errors
```

Use existing environment/project browser automation when available. Adding a
new browser-test runtime dependency is not an M2 requirement.

If automation is unavailable, M2 closure requires both:

```text
scripted live-stack HTTP E2E
+
recorded manual browser walkthrough for client rendering/interactions
```

HTTP-only evidence is not treated as proof of browser interaction correctness.

---

# 6. Acceptance Matrix

## 6.1 Prompt compiler

* version constant exactly `"1"`;
* labels fixed English and non-configurable;
* golden fixture asserted as exact UTF-8 bytes;
* LF only; no CRLF; no trailing LF;
* same normalized intent → identical output over repeated calls;
* fixed field order;
* `None` fields skipped;
* defensive whitespace-only optional values skipped;
* subject-only input → exactly `b"Subject: <value>"`;
* `duration_ms` changes alone do not change compiled bytes;
* backslash escaping exact;
* CR escaping exact;
* LF escaping exact;
* TAB escaping exact;
* other C0/DEL escaping exact with lowercase `\u00xx`;
* C1 controls U+0080–U+009F remain unescaped;
* U+2028/U+2029 remain unescaped;
* Unicode and combining characters preserved without normalization;
* composed `é` and decomposed `e + U+0301` remain byte-distinct;
* long values near the Shot subject limit remain stable;
* module import has no side effects;
* AST purity check rejects DB/FS/network/executor dependencies.

## 6.2 Working-state comparison

* no approved Take → `false` + `approved_take_id=null`;
* approved revision hash equals working hash → false;
* approved revision hash differs → true;
* dangling approved Take → invariant + log;
* Take belongs to another Shot → invariant + log;
* Take's Generation belongs to another Shot → invariant + log;
* Generation references a revision belonging to another Shot → invariant + log;
* missing Generation → invariant + log;
* missing ShotRevision → invariant + log;
* comparison uses the same canonical working-snapshot builder as revision capture;
* structural test proves snapshot + provenance traversal uses one checked-out connection and one explicit SQLite read transaction, with no intermediate commit/rollback or secondary connection/session;
* deterministic interleave pauses after the first comparison read, commits a concurrent edit, then proves the response is derived from the original SQLite read snapshot rather than mixed snapshots;
* field present on Shot detail only;
* list remains lightweight;
* frontend contains no crypto/hash/canonicalization implementation.

## 6.3 Project Asset discovery

* active Project list succeeds;
* malformed/missing/deleted Project → `PROJECT_NOT_FOUND` envelope;
* default filter returns reference Assets;
* explicit `kind=reference` works;
* explicit `kind=output` follows existing enum semantics even if M2 has none;
* invalid `kind` → `422 VALIDATION_ERROR`;
* deterministic `(created_at, id)` ordering;
* Asset from Project A never appears in Project B list;
* upload/detail/list reuse one `AssetRead` shape;
* `detected_media_type` comes from the referenced Blob, not `upload_mime_type`;
* backend `blob_url` is canonical relative `/blobs/...`;
* backend `blob_url` contains no `/api` prefix and no backend origin;
* `api.client.ts` maps canonical `/blobs/...` to browser `/api/blobs/...`;
* the Blob URL mapper rejects noncanonical/absolute input;
* response contains no absolute/local storage path;
* repeated filename Assets remain distinct by Asset ID/provenance.

## 6.4 Projects / Shots UI

* create/list/open/delete Project;
* deleted Project disappears from list;
* direct deleted Project route renders controlled `PROJECT_NOT_FOUND` state;
* repeat DELETE is silent to user;
* Project deletion removes active child Shots from normal UI;
* create Shot number 1;
* sequential Shot numbers visible;
* delete Shot then create another → historical number not reused;
* deleted Shot disappears;
* blank/overlong inputs surface stable validation envelope;
* browser refresh returns authoritative server state.

## 6.5 Shot editor

* every editable intent field round-trips;
* optional empty text → persisted `NULL` and returns as empty UI control;
* subject/title trimming visible after normalized response;
* clearing duration → `NULL`, not `0`;
* explicit duration `0` round-trips as `0`;
* negative duration surfaces envelope;
* successful save updates `updated_at`;
* successful save refreshes visible working hash;
* unrelated unsaved local fields are not overwritten during refresh;
* compiler is not reimplemented or previewed in the frontend.

## 6.6 References

* references visually grouped by role;
* upload PNG/JPEG renders Blob thumbnail;
* immutable Blob cache headers verified on the proxied request;
* unknown/octet-stream Asset renders generic icon;
* upload through Next rewrite preserves multipart body;
* attach changes working hash;
* same Asset under two different roles allowed;
* duplicate `(asset, role)` → stable envelope + unchanged server/local state;
* cross-Project Asset → stable envelope + unchanged set;
* move controls exist only within same role;
* same-role reorder produces contiguous server positions and changes hash;
* role change re-normalizes source and destination roles and changes hash;
* removal changes hash;
* identical full-set PUT → 200 + unchanged hash;
* zero-byte upload → `EMPTY_UPLOAD` + no new Asset/reference state;
* invalid full-set PUT is transactionally atomic and leaves previous set intact;
* multi-tab behavior is documented as last-write-wins, not optimistic-safe.

## 6.7 Error surface

* SoloRing envelope renders code + message;
* server-component envelope failures use same abstraction;
* browser mutation envelope failures use same abstraction;
* network connection failure renders controlled error;
* malformed proxy/non-envelope response renders controlled error;
* no raw fetch/stack error appears in user-facing UI;
* clearing/dismissing an error does not mutate server state.

## 6.8 Build and bundle boundary

* `npm run build` green at every frontend slice;
* FastAPI need not be running during build;
* build succeeds with unreachable `SOLORING_API_ORIGIN`;
* no live backend fetch is performed at build time;
* server API origin absent from emitted browser JS;
* Client Components do not import `api.server.ts`;
* browser API calls use `/api` rewrite;
* backend Blob DTOs remain `/blobs/...`; only `api.client.ts` prefixes `/api` for browser Blob requests;
* no new runtime npm dependencies;
* no hashing/crypto implementation under `apps/web/src`;
* no absolute storage path rendered or serialized.

## 6.9 Full-stack UX

* after every successful creative mutation, refreshed hash is immediately visible;
* semantic no-op mutation visibly preserves the same hash;
* loading state is visually distinct from empty state;
* Approved Take panel says no canon rather than "matches canon" when pointer is null;
* Revisions empty state is deliberate, not a spinner/error;
* browser refresh repopulates forms and Assets from server truth;
* back/forward navigation does not manufacture client-only Asset/reference state.

---

# 7. Definition of Done

M2 closes only when:

* [ ] compiler v1 is byte-pinned as explicit UTF-8;
* [ ] compiler labels are fixed English protocol strings;
* [ ] compiler control-character escaping is specified and tested;
* [ ] compiler emits LF-only line framing with no trailing newline;
* [ ] `duration_ms` is proven not to affect compiler v1 bytes;
* [ ] compiler version is literal `"1"`;
* [ ] compiler structural purity test is green;
* [ ] `working_state_differs_from_approved` is server-computed;
* [ ] no-canon/match/differ paths are tested;
* [ ] broken or cross-Shot approval provenance produces invariant failure + diagnostics;
* [ ] comparison uses one checked-out connection and one explicit SQLite read transaction with no intermediate commit/rollback and passes the deterministic read-snapshot interleave test;
* [ ] Shot detail carries the comparison field and Shot list remains light;
* [ ] Project Assets are persistently discoverable through `GET /projects/{id}/assets`;
* [ ] Asset list is Project-scoped, deterministic, and future-kind compatible;
* [ ] backend Asset `blob_url` remains canonical `/blobs/...`;
* [ ] `api.client.ts` is the only `/api` Blob-prefix mapping boundary;
* [ ] shared `AssetRead` exposes Blob-derived `detected_media_type`;
* [ ] Project Asset listing is recorded as an explicit v0.1 §99 API amendment;
* [ ] Projects/Shots CRUD is usable end-to-end;
* [ ] Shot editor round-trips every creative field with M1 normalization semantics;
* [ ] duration UI distinguishes null from zero and is labeled as temporal metadata;
* [ ] references are visually grouped and reorder only within roles;
* [ ] attach/reorder/role-change/remove each visibly refresh working hash;
* [ ] semantic no-op reference PUT visibly preserves hash;
* [ ] invalid reference PUT leaves previous state intact;
* [ ] last-write-wins multi-tab reference behavior is documented as an accepted v0.1 risk;
* [ ] image thumbnails load through proxied content-addressed Blob URLs;
* [ ] unknown media uses a generic icon;
* [ ] stable envelopes and network failures render through one ErrorBanner abstraction;
* [ ] deleted entities disappear from normal lists and direct routes fail cleanly;
* [ ] loading states are distinct from honest empty states;
* [ ] Approved Take surface never implies canon exists when `approved_take_id` is null;
* [ ] `next build` is green with FastAPI stopped and an unreachable `SOLORING_API_ORIGIN`;
* [ ] legacy `SOLORING_API_URL` is removed/migrated and no `SOLO_RING_API_ORIGIN` spelling is introduced;
* [ ] server-only origin does not appear in browser bundles;
* [ ] no frontend canonicalization/hash/comparison implementation exists;
* [ ] no Generation/execution UI or endpoint leaks from M3;
* [ ] full backend suite is green;
* [ ] full-stack browser evidence is recorded.

---

# 8. Accepted M2 Decisions and Risks

## 8.1 Prompt format v1

Use fixed labeled English lines with explicit v1 escaping and LF framing.

Rejected for v1:

```text
free-form prose join
JSON prompt text
localized labels
configurable labels
platform-native line endings
raw multiline/control-character insertion
```

`duration_ms` remains outside prompt text. Negative prompt remains undefined.

## 8.2 Comparison on Shot detail

`working_state_differs_from_approved` remains additive on `GET /shots/{id}`.
No separate comparison endpoint is added in M2.

A later lightweight endpoint is permitted if a future polling surface genuinely
needs it.

## 8.3 `differs=false` with no canon

When:

```text
approved_take_id = null
```

return:

```text
working_state_differs_from_approved = false
```

The UI renders `No approved Take yet`, not `Matches canon`.

## 8.4 Persistent Project Asset discovery

`GET /projects/{id}/assets` is required. Upload-response-only discovery is not
sufficient for refresh-safe creative work. This is an explicit amendment to the
v0.1 §99 API surface.

The endpoint is compatible with future `output` Assets through the existing
Asset-kind identity. Invalid kind filters use the standard 422
`VALIDATION_ERROR` envelope.

## 8.5 Role-scoped buttons instead of drag-and-drop

Use explicit accessible move controls inside visually grouped roles.

This is deterministic, dependency-free, and aligned with persisted positions
being role-scoped.

## 8.6 Server/client API separation

Browser API calls use relative `/api`. Server Components and the Next rewrite
share one server-only `SOLORING_API_ORIGIN`. The legacy `SOLORING_API_URL` name
is removed. The production build never depends on a live backend.

FastAPI continues to emit canonical `/blobs/...` Blob URLs. Only
`api.client.ts` maps them to `/api/blobs/...` for browser requests.

## 8.7 No component unit-test framework in M2

M2 uses:

```text
TypeScript/build gates
backend tests
live-stack smoke
browser walkthrough evidence
structural bundle/import checks
```

Vitest/React Testing Library may be introduced later if client-side state logic
becomes materially more complex.

## 8.8 Compiler has no M2 UI

The compiler is a backend primitive first consumed by Generation orchestration
in M3A. No preview endpoint or compiler editor is added in M2.

## 8.9 Reference replacement is last-write-wins

`PUT /shots/{id}/references` remains a complete atomic replacement without an
optimistic concurrency precondition.

Accepted v0.1 behavior:

```text
single-user multi-tab edits may lose an intermediate edit
later successful full-set PUT wins
no partial set is committed
```

This is explicitly accepted for the local-first v0.1 milestone.

Future hardening:

```text
working_snapshot_hash / reference-version precondition
→ reject stale replacement with 409
```

## 8.10 No Asset deletion UI

Reference Assets remain durable provenance objects. M2 does not add Asset
delete semantics merely to keep the Project Asset picker small.

Storage growth and later GC/deletion UX remain separate milestones.

---


## 8.11 Broken approved provenance blocks Shot detail

A non-null approval pointer with a dangling or cross-Shot
Take→Generation→ShotRevision chain is a ledger invariant failure. M2 intentionally
returns/renders `INTERNAL_INVARIANT_VIOLATION` rather than degrading to an
editable Shot page with an ambiguous canon badge.

This behavior may make one corrupted Shot detail temporarily unusable; that is
accepted because silently misreporting canon state is worse.

# 9. Non-Gating Future Enhancements

The following do not block M2:

* Project/Shot/Asset pagination;
* move-to-top / move-to-bottom reference controls;
* optimistic locking for Shot PATCH;
* optimistic locking for reference replacement;
* frontend component-test framework;
* prompt preview endpoint;
* Asset deletion UI;
* richer provenance badges in Asset picker;
* denormalized approved revision hash if future high-frequency reads justify it.

No TODO may weaken an M2 invariant silently; deferred behavior must remain
explicit in this document or later milestone plans.

---

# 10. Run Book

## 10.1 Backend

From repository root on Windows/Git Bash with the repository virtualenv:

```bash
.venv/Scripts/python.exe -m alembic -c server/alembic.ini upgrade head
.venv/Scripts/python.exe -m uvicorn soloring.api.main:app --reload --port 8000
```

## 10.2 Frontend development

The only backend-origin variable is:

```text
SOLORING_API_ORIGIN
```

Windows `cmd`:

```bat
cd apps\web
set SOLORING_API_ORIGIN=http://127.0.0.1:8000
npm install
npm run dev
```

Git Bash / POSIX-style shell:

```bash
cd apps/web
export SOLORING_API_ORIGIN=http://127.0.0.1:8000
npm install
npm run dev
```

Browser API requests:

```text
http://localhost:3000/api/*
→ Next.js rewrite using SOLORING_API_ORIGIN
→ FastAPI :8000
```

Backend Asset DTOs still contain canonical Blob paths:

```text
/blobs/...
```

`api.client.ts` maps those to `/api/blobs/...` only when the browser requests
Blob bytes.

## 10.3 Production-build gate

Stop FastAPI first. Point the server-only origin at a deliberately unreachable
local address.

Windows `cmd`:

```bat
cd apps\web
set SOLORING_API_ORIGIN=http://127.0.0.1:65534
npm run build
```

Git Bash / POSIX-style shell:

```bash
cd apps/web
export SOLORING_API_ORIGIN=http://127.0.0.1:65534
npm run build
```

Expected:

```text
build succeeds
no FastAPI connection required
configured server-origin literal absent from emitted browser JS
```

The build/structural gate also verifies that `SOLORING_API_URL` is no longer in
active frontend configuration and that `SOLO_RING_API_ORIGIN` is not introduced.

## 10.4 M2 full-stack close

Run the migrated backend and Next development server, then execute the browser
walkthrough from §5 M2D.

The close evidence must distinguish:

```text
backend unit/integration proof
frontend build/type proof
live HTTP integration proof
browser interaction/rendering proof
```

M2 is not considered complete solely because individual API requests succeed.
