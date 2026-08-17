# SoloRing M2 — Creative UI Implementation Plan

## 1. Objective

M2 turns the closed M1 foundation into the usable creative surface, and delivers
the last two creative-layer backend primitives that depend on no execution
infrastructure:

```text
Project / Shot browsing + editing          (UI over M1B APIs)
reference upload / attach / reorder        (UI over M1C/M1D APIs)
prompt compiler + version                  (pure backend primitive, §35)
working-state vs approved-canon comparison (backend computation, §94)
```

Exit criterion (v0.1 §108):

> Creative working state has deterministic immutable snapshot semantics.

In M2 that is demonstrated **through the UI**: every creative edit visibly flows
through normalization → canonical snapshot → `working_snapshot_hash`, and the
hash changes exactly when the canonical state changes.

M2 does **not** make anything executable. No Generate button, no queue, no SSE,
no Takes, no approval mutation. Until M3A there is no approved Take and no
revision rows; the UI must represent those states honestly (empty states, not
placeholders implying functionality).

---

## 2. Milestone Boundary

### 2.1 Included

Backend:

* pure prompt compiler (`compile_prompt`) with pinned version
* prompt-compiler determinism + byte-fixture tests
* working-state-vs-approved comparison computation (§94)
* `working_state_differs_from_approved` on the Shot detail API
* comparison semantics for the no-approved-Take case (the only real case until M3A)
* synthetic-Take tests of the approved-vs-working comparison (logic proven before M3A exercises it live)

Frontend:

* typed API client over the existing `/api/*` rewrite proxy
* global error-envelope rendering (`error_code` / `message` from §42 envelope)
* Projects page: list / create / open / delete (soft-delete semantics visible)
* Project page: shot list / create / delete, shot numbering visible
* Shot editor: all `ShotIntent` fields + title, PATCH-on-save, `updated_at` feedback
* reference upload (multipart) into the Project, then attach to a Shot with roles
* deterministic reference reorder (explicit move-up/move-down; full-set PUT)
* reference removal and role change (same atomic PUT)
* reference thumbnails via content-addressed Blob URLs (`/api/blobs/...`)
* Current Working State panel: `working_snapshot_hash` + differs-from-approved badge
* Approved Take panel: honest "none yet" state (approval arrives in M3A)
* revision summary list (empty state until M3A captures revisions lazily)
* production build green (`next build`) as a slice gate

### 2.2 Explicitly excluded

* public Generation creation UI or endpoint
* queue / worker / progress / SSE
* review grid, Take display, approve/reject mutations (M3A)
* output import, provenance viewers, Exact Rerun (M6/M7)
* Comfy anything (hard gate §2)
* frontend pagination (non-gating; lists are small in v0.1 — noted, not built)
* auth, multi-user, theming, UI kits, drag-and-drop libraries, new npm runtime deps
* frontend reimplementation of canonicalization or comparison logic (§94: server-computed only)

---

## 3. Backend Additions

### 3.1 Prompt compiler (v0.1 §35)

Location: `server/soloring/domain/prompt.py` (creative layer; executor code must
never own it).

```python
PROMPT_COMPILER_VERSION = "1"

def compile_prompt(intent: ShotIntent) -> str: ...
```

Contract: deterministic, synchronous, pure — no DB, filesystem, network, LLM,
or hidden mutable global configuration. Input is a normalized `ShotIntent`
(optional fields already `None`, never `""`).

**Exact v1 format (byte-pinned by tests):**

* one line per present field, `"Label: value"`
* fixed label order: `Subject`, `Action`, `Environment`, `Framing`,
  `Camera Motion`, `Lens`, `Mood`
* lines joined with `\n`; no trailing newline; values inserted verbatim
  (post-normalization), Unicode code points preserved (no NFC/NFD)
* `None` fields are skipped; defensively, whitespace-only fields are skipped
* `duration_ms` is **not** compiled into text (temporal metadata, not prompt
  content) — consumed later by the workflow layer
* v1 produces no negative prompt (`negative_prompt = None`); the Generation
  draft field remains the carrier when a future version defines one

Golden fixture:

```python
ShotIntent(subject="Eva", action="enters the lobby", environment="hotel lobby",
           framing="medium wide", camera_motion="slow push-in",
           lens="50mm", mood="restrained unease")
```

```text
Subject: Eva
Action: enters the lobby
Environment: hotel lobby
Framing: medium wide
Camera Motion: slow push-in
Lens: 50mm
Mood: restrained unease
```

Version policy: any change to output bytes requires a new
`PROMPT_COMPILER_VERSION`. Enforced by golden byte tests — an output change
breaks the fixture, forcing the bump.

### 3.2 Working state vs approved canon (v0.1 §94)

The server already computes `working_snapshot_hash` via the exact canonical
builder (M1B). M2 adds the comparison, entirely server-side:

```text
approved_take_id IS NULL
→ differs = false                      (no canon yet — the only live case in M2)

approved_take_id set
→ Take → Generation → ShotRevision.snapshot_hash
→ differs = working_snapshot_hash != approved_revision_hash
```

API change (additive): `GET /shots/{id}` gains
`working_state_differs_from_approved: bool`. The frontend renders it; it never
recomputes hashes or comparisons (§94).

Tests insert synthetic Take/Generation/Revision rows through the ORM to prove
both branches (same-hash → false, different-hash → true) before M3A can produce
real ones.

---

## 4. Frontend Architecture

Stack is fixed by M0 scaffold: Next.js 14 App Router, React, TypeScript, no
additional runtime dependencies. Styling: plain CSS (single stylesheet /
module CSS). No state library — server components for reads, small client
components for mutations, `router.refresh()` after writes.

### 4.1 Layout

```text
apps/web/src/
├── lib/api.ts          typed client: envelope-aware, base "/api"
├── lib/types.ts        API DTOs (mirror server response schemas)
├── app/
│   ├── page.tsx                     projects list + create
│   ├── projects/[id]/page.tsx       shot list + create + delete
│   └── shots/[id]/page.tsx          editor (client-heavy)
└── components/          ShotForm, ReferencePanel, ReferenceRow,
                         WorkingStatePanel, ErrorBanner, ...
```

### 4.2 UX contracts worth pinning

* **Reference reorder is explicit** — move-up/move-down buttons emitting the
  full ordered set to `PUT /shots/{id}/references`. Deterministic, no drag
  library, positions remain server-owned.
* **Attach flow**: upload → asset appears in project assets → user attaches
  with a role (default `reference`); same asset may hold multiple roles.
* **Hash visibility**: the working hash is always visible on the shot page;
  after every save/reorder the page refreshes and the hash change (or
  non-change) is immediately observable — the core M2 dogfooding loop.
* **Deleted hierarchy**: deleted projects/shots are absent from lists; DELETE
  buttons confirm; repeat-DELETE idempotency is not surfaced as an error.
* **Error envelope**: every failed call renders `error_code` + message in an
  ErrorBanner; no raw fetch errors leak into the UI.

---

## 5. Slice Order

### M2A — Prompt compiler + working-state comparison (backend)

Build: `domain/prompt.py`, comparison service, `ShotRead` field, tests
(byte fixtures, determinism, field-skip, Unicode, version pin; comparison
true/false/null-path with synthetic Takes; API field test).

Gate:

```text
full backend suite green (244 + new M2A tests)
```

### M2B — Frontend foundation: API client + projects

Build: `lib/api.ts` (envelope-aware), types, projects page (list/create/delete),
project page shell with shot list/create/delete, ErrorBanner, global CSS.

Gate:

```text
npm run build green (types + lint + compile)
+ live smoke: uvicorn (migrated DB) + Next against it; project CRUD walkthrough
```

### M2C — Shot editor + reference upload/reorder

Build: ShotForm (intent fields, PATCH-on-save, updated_at feedback),
ReferencePanel (upload, attach/detach, role edit, move-up/down), Blob
thumbnails, hash display on every mutation.

Gate:

```text
npm run build green
+ live smoke: edit subject → hash changes; reorder → hash changes;
  identical PUT → hash unchanged; cross-project asset rejected with envelope shown
```

### M2D — Working/approved panel + revisions + full-stack gate

Build: WorkingStatePanel (hash + differs badge), ApprovedTakePanel ("none
yet" honest state), revision summary list (empty state), page polish.

Gate (M2 exit):

```text
npm run build green
+ full-stack browser walkthrough: project → shot → upload PNG → attach
  → reorder → hash transitions visible; envelopes on forced errors
+ full backend suite green
```

Browser walkthrough via the available browser automation tooling; if the
environment blocks it, fall back to scripted HTTP E2E against the live stack
and record the limitation honestly — the gate is evidence, not assertion.

---

## 6. Acceptance Matrix

### 6.1 Prompt compiler

* golden byte fixture exact
* determinism: same intent → identical bytes, repeated calls
* field order fixed regardless of input construction order
* None/whitespace-only fields skipped
* Unicode + combining characters preserved (no normalization)
* long values stable
* version constant present and non-empty
* no hidden config: module import has no side effects, no globals mutated

### 6.2 Working-state comparison

* no approved take → `working_state_differs_from_approved = false`
* approved revision hash == working hash → false (synthetic)
* approved revision hash != working hash → true (synthetic)
* comparison uses the same canonical builder as revision capture (single code path)
* field present on `GET /shots/{id}`; absent from shot list (list stays light)
* frontend never computes the hash or comparison (structural: no crypto in `src/`)

### 6.3 Projects / shots UI

* create/list/open/delete project; delete cascades visibly (shots disappear)
* deleted project 404s render as envelope, not crash
* shot create: first number 1, sequential numbers visible
* shot delete: gone from list; numbers never reused (create after delete)
* blank subject / overlong inputs surface server envelopes

### 6.4 Shot editor

* all intent fields editable; empty optional input → persisted `NULL` (round-trips as absent)
* successful save updates `updated_at`
* title/subject trimming visible after round-trip
* `duration_ms` >= 0 enforced by envelope

### 6.5 References

* upload PNG/JPEG renders thumbnail via Blob URL (immutable cache headers in dev tools)
* unknown media type uploads but shows generic icon (octet-stream)
* attach with role; same asset under two roles allowed
* duplicate (asset, role) rejected → envelope shown, state unchanged
* move-up/move-down produces contiguous server positions (verified via API response)
* reorder/role-change/removal each change the working hash
* identical resubmission → 200, hash unchanged
* zero-byte upload rejected with EMPTY_UPLOAD envelope

### 6.6 Full-stack

* `next build` green at every slice gate
* no absolute storage paths in any response or rendered attribute
* full backend suite green at M2 close

---

## 7. Definition of Done

* [ ] compiler byte-fixtures green; version pinned "1"
* [ ] compiler purity structurally verified (no DB/FS/net imports in module)
* [ ] `working_state_differs_from_approved` computed server-side, tested all three paths
* [ ] ShotRead carries the field; shot list does not
* [ ] projects/shots CRUD usable end-to-end in the browser
* [ ] shot editor round-trips every intent field with correct normalization
* [ ] reference upload → attach → reorder → hash-change loop observable live
* [ ] honest empty states for approved take and revisions
* [ ] all API failures render the stable envelope
* [ ] `next build` green; no new runtime npm dependencies
* [ ] no frontend reimplementation of canonicalization/comparison
* [ ] no execution-path UI or endpoints leaked from M3
* [ ] full backend suite green

---

## 8. Flagged Decisions (need reviewer sign-off or objection)

1. **Prompt format v1** — labeled-line format above; alternatives (prose join,
   JSON) rejected for readability + byte-stability. `duration_ms` excluded from
   text; negative prompt undefined in v1.
2. **Comparison lives on `ShotRead`** rather than a separate §94 endpoint —
   one round-trip, additive field. Separate endpoint if preferred.
3. **`differs=false` when no approved take** (rather than null/unknown) — with
   `approved_take_id: null` adjacent, the client renders "no canon yet".
4. **Move-buttons instead of drag-and-drop** — zero deps, deterministic.
5. **No component unit-test framework in M2** — gates are build + live/browser
   smoke; vitest can be added later without architectural impact.
6. **Compiler has no UI surface in M2** — first consumed by generation creation
   (M3A); a preview endpoint is a non-gating future enhancement.

## 9. Run Book (dev loop for slices M2B+)

```bash
# backend (repo root)
.venv/Scripts/python.exe -m alembic -c server/alembic.ini upgrade head   # once per data dir
.venv/Scripts/python.exe -m uvicorn soloring.api.main:app --reload --port 8000

# frontend
cd apps/web && npm install && npm run dev        # :3000, proxies /api/* → :8000
```
