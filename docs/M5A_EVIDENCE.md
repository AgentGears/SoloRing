# SoloRing Executor Evidence Ledger — M5A doubles + M5B live

Historical scope note: the M5A sections below were proven against
**deterministic HTTP doubles** (`httpx.MockTransport`). The M5B sections
above subsequently validated every live claim against the real deployment;
the close-out table records the final state of each item.

## Proven (HTTP-double evidence)

### Aggregate lifecycle (M5A-10, `tests/test_m5a10_aggregate.py`)
- **Headline lifecycle**: real Project → Shot → reference Blob → API creation
  with `SOLORING_EXECUTOR=comfy` → persisted `executor='comfy'` → historical
  manifest/template captured (descriptor-coherent) → worker claim + attempt_id
  → streamed input upload (attempt namespace, hash-verified) → pure translation
  → ONE POST → observe to terminal → streamed /view → import → Take/Asset/Blob
  → `succeeded`. Full provenance chain asserted end-to-end:
  shot_revision_id, manifest_hash, workflow_template_hash, workflow_spec_hash,
  executor_submission_hash (persisted bytes ARE the hashed canonical bytes),
  attempt_id, executor_job_id, marker identity.
- **Takeover after response-lost**: A's POST is accepted but the response is
  dropped; A dies mid-rediscovery (durable state: `submission_possible`, no
  job id). B ages into authority, adopts, REDISCOVERS ONLY — exactly one POST,
  one remote prompt, one durable result, attempt identity preserved.
- **Soft Cancel**: cancel requested while running under the conservative
  SOFT_ONLY capability → durable soft-cancel selection → remote completion is
  discarded: zero Takes, zero Assets, zero /view calls, zero /interrupt calls,
  zero queue deletes, executor_job_id unchanged.
- **Installed-workflow mutation**: G1 captures M1/T1; the installed release
  then mutates to T2 (descriptor swapped); G2 captures M2/T2. G1 executes
  AFTER the mutation and still submits the T1 graph; G2 submits T2.
- **Creative-state freeze**: post-capture Shot mutation (subject, creative
  fields, entirely different reference set) never reaches the executor — the
  submitted prompt text and uploaded input are the captured revision's.
- **Executor-selection dispatch**: config switch affects only NEW creations;
  queued history executes per its persisted executor. Fake rows never acquire
  submission_possible/artifact/prompt_id/soft-cancel; unknown executor values
  are rejected at Settings load (closed Literal, mirrored by the DB CHECK).
- **Error envelope through the worker boundary**: contract-proven 400
  rejection → `failed`/EXECUTOR_UNAVAILABLE; missing historical artifact →
  `failed`/WORKFLOW_MANIFEST_MISSING with zero POSTs.
- **AST boundary audits**: Comfy package is DB/worker/generation-free (sole
  sanctioned import: the pure canonical-bytes serializer); wire dialect keys
  confined to wire.py; `.submit_prompt(` has exactly one call site (the
  durable-protocol module); lifecycle transitions never target
  queued/preparing/submission states; queued-status writes confined to the
  fenced requeue + creation INSERT; generation status mutations confined to
  the worker fence plus the sanctioned §69 API immediate-cancel.

### Slice proofs (M5A-1 … M5A-9)
- **M5A-1** one-shot submission authority (`test_m5a1_submission_state.py`):
  not_started → submission_possible → confirmed|uncertain one-way state
  machine; only the committing frame receives MAY_POST; DB CHECK enforcement.
- **M5A-2** wire normalization (`test_m5a2_wire.py`): two queue dialects,
  history/submit/upload/view normalization, bounded diagnostics.
- **M5A-3** historical artifacts (`test_m5a3_artifacts.py`):
  content-addressed manifest/template store, corrupt-target REPAIR, MISSING/
  INTEGRITY on retrieval (never installed fallback), workflow-package.json
  descriptor coherence — hybrid M1/T2 pairs rejected including
  structurally-compatible ones.
- **M5A-4** input materialization (`test_m5a4_materialize.py`): streamed
  bounded-memory verification → transport → re-verification; hostile
  validation of returned references; attempt namespace isolation.
- **M5A-5** pure translation (`test_m5a5_translate.py`): exact bindings,
  logical-identity input binding, no defaults at translation time, marker
  under extra_data.soloring, deterministic artifact bytes.
- **M5A-6** client + submit recovery (`test_m5a6_submit.py`): exactly-one
  POST attempt; ambiguity classification; bounded monotonic rediscovery
  (duplicate/conflict detection; read failures never reset the deadline);
  uncertain is permanently ineligible; contract-proven 400 rejection.
- **M5A-7** observation (`test_m5a7_observe.py`): terminal history > queue >
  disappearance grace precedence; monotonic grace; marker discipline.
- **M5A-8** cancellation (`test_m5a8_cancel.py`): pending delete targeted;
  hard cancel only TARGETED+retry-safe; Soft Cancel durable and
  zero-publication; global /interrupt unreachable (instrumented count 0).
- **M5A-9** outputs (`test_m5a9_outputs.py`): unrelated-node tolerance vs
  binding-level cardinality; strict /view reference validation; streamed
  bounded staging with retry-from-zero and convergent finalization.

### Infrastructure gates
- **Migrations** (`test_migration.py`, `test_migration_m1.py`,
  `test_m5a10_migration_gate.py`): fresh upgrade → 0005; populated 0004 DB →
  0005 with documented not_started/NULL defaults for existing rows;
  downgrade/re-upgrade round-trip; `foreign_key_check` clean; no temp debris.
- **Backend repeatability**: 627/627 × 2 consecutive full-suite passes.
- **Stress**: 5/5 clean repeated runs on artifact placement, blob import,
  materialization, submission permission, submit recovery, output staging,
  and the M5A-10 aggregate.
- **Frontend**: production build succeeds with the API unreachable;
  zero case-insensitive "comfy" occurrences in the entire `.next/` output;
  no `NEXT_PUBLIC_*` in source; no Comfy URL/credential/path in bundles.

## M5B-1 — live fingerprint COMPLETE (2026-08-16)

The dedicated instance is provisioned and probed (report + sanitized
fixtures: `data/comfy-fingerprint/`).

- **Deployment pin** (`COMFYUI_VERSION`): ComfyUI **0.33.0** @
  `b963f4a` (frontend 1.49.6), python 3.12, torch 2.13.0+cu126, RTX 3080 Ti
  12 GB, custom node city96/ComfyUI-GGUF. Serving `127.0.0.1:8188`.
- **Capability report: READY** — all six mandatory features SUPPORTED from
  recorded live evidence (marker canary: one CPU-only LoadImage→SaveImage
  prompt through /prompt → targeted /history → /view). WS endpoint observed
  (first-message `{"type":"status",...}`); observational only.
- **Live dialect finding (fixed loop exercised)**: terminal success is
  `status_str:"success"` on 0.33.0 (older dialect: `"completed"`). Fixture
  captured → wire.py map extended → M5A regression added
  (`test_history_success_dialect_from_live_0_33`) → full suite ×2 green
  (660/660).
- **Identity round-trip live**: /upload/image echoed
  `soloring_probe.png`/`soloring_probe` exactly (R6 exact-or-reject
  semantics validated against the real endpoint).
- **Cancellation contract finding**: /interrupt with an unknown prompt_id
  returns 200/empty (skip), not a targeted-acceptance body — upstream has
  no provable targeted running-cancel contract. Capability stays
  **SOFT_ONLY**; pending/running cancellation UNKNOWN until the M5B-5
  probes (with real long-running work).
- **Remaining M5B**: workflow+models (M5B-2), live happy path with the real
  graph and streaming bridge under load (M5B-3), worker-death adoption
  (M5B-4), cancellation behavior (M5B-5), restart/history-loss
  characterization (M5B-6), final live gate (M5B-7).

## M5B-2 — real workflow/template installation: COMPLETE (2026-08-16)

**Topology preflight (the mandatory question, resolved from live
/object_info + the installed official templates):** the official 0.33 I2V
template is HunyuanVideo **1.5** (dual-stage: two UNETLoaders + a
LatentUpscaleModelLoader — the "Load Image Model" class). Per the decision
list, the workflow is **validly re-authored on the officially documented
v1 I2V baseline** — every node/field verified live — with the single GGUF
substitution ComfyUI-GGUF documents (diffusion loader only). No unresolved
model role; the 1.5 dual-stage pipeline is additionally unsuitable for
12 GB VRAM.

**Release v2 committed** (`workflows/hunyuan_i2v_v1/`, manifest version 2):
12-node API graph — LoadImage → CLIPVisionEncode(llava_llama3_vision) +
TextEncodeHunyuanVideo_ImageToVideo(dual-clip llava+clip_l) →
HunyuanImageToVideo(guidance v1 concat, 848x480x53) → KSampler(seed/steps/
cfg; euler/simple; cfg 1.0) → VAEDecode(bf16 VAE) → SaveAnimatedWEBP(24fps,
history field "images" — verified from ComfyUI source `SavedImages.as_dict`).
Descriptor written LAST (MH b18a34d9…, TH 531758e0…); coherent
capture_package + binding validation + hash retrieval gated by
`tests/test_m5b2_package.py` (3 tests, incl. hybrid rejection).

**Seed resolution (explicit):** SoloRing v0.1 specs carry seed=None (the
strict M4 manifest schema deliberately has no seed declaration), so no seed
binding is captured; the graph's KSampler.seed stays the template constant
0. A non-null seed would fail translation until a future schema version
adds the binding.

**Model inventory — verified SHA-256 (authoritative HF tree API; the HEAD
ETags on Xet-backed storage are NOT sha256s):**

| file | dir | size | sha256 |
|---|---|---|---|
| hunyuan-video-i2v-720p-Q4_K_M.gguf (city96/HunyuanVideo-I2V-gguf) | models/unet | 7.88 GB | 1c1490ea… |
| clip_l.safetensors (Comfy-Org/HunyuanVideo_repackaged) | models/text_encoders | 0.25 GB | 660c6f5b… |
| llava_llama3_fp8_scaled.safetensors (same) | models/text_encoders | 9.09 GB | 2f0c3ad2… |
| llava_llama3_vision.safetensors (same) | models/clip_vision | 0.65 GB | 7d0f89bf… |
| hunyuan_video_vae_bf16.safetensors (same) | models/vae | 0.49 GB | e8f85532… |

Total 18.36 GB. **Live visibility proven** post-restart: all five filenames
appear in their loader enums via /object_info. Environment fully frozen in
`COMFYUI_VERSION` (ComfyUI b963f4a/0.33.0, frontend 1.49.6,
ComfyUI-GGUF 6ea2651, torch 2.13.0+cu126).

No generation executed (that is M5B-3). Stale placeholder-topology test
pins updated to the release-v2 bindings; full suite **663/663 ×2**,
frontend tsc clean.

## M5B-3 — live end-to-end generation: COMPLETE (2026-08-16)

The first real HunyuanVideo I2V render through the complete SoloRing
lifecycle. Durable evidence specimen: `data/m5b3-specimen/` (ledger.json,
DB, blobs — preserved). Full backend suite after the release change:
**663/663**.

- **Release v3 en route**: the live instance's contract-proven 400 rejected
  release v2's sampler wiring (`HunyuanImageToVideo` emits BOTH
  `[0] CONDITIONING` and `[1] LATENT`; v2 fed [0] to latent_image). The
  M5A-6 rejection classification worked live: no POST retry, clean
  EXECUTOR_UNAVAILABLE envelope, nothing queued. v3 fixes the slots;
  new MH `67e43719…` / TH `c7ee0fb9…`; package gate re-run green.
- **The render**: 30/30 steps, **549.3 s**, VRAM peak **12,011 MB**
  (Q4_K_M 7.16 GB on-GPU + 433 MB offloaded), ~11.5 s/it at 848×480×53.
- **One real /prompt** (t=0.047) carrying the 12-node v3 graph + marker;
  upload requested identity echoed EXACTLY (hash-name +
  `soloring_gen_{G}_att_{A}` namespace) and the returned authoritative
  reference entered the submitted graph verbatim. No auto-rename observed
  under SoloRing's overwrite=true mode (recorded, not manufactured).
- **Observation**: 1,102 targeted-history+queue calls over the render
  (1/s); lifecycle preparing→submitted at t=0.5; targeted history was
  terminal authority.
- **Streaming bridge (the mandatory proof)**: loop thread **37424** ≠
  chunk-consumer thread **37172** (runtime deadlock guard armed and
  satisfied); 2,345,034 bytes streamed in **4×1 MiB chunks** (no
  whole-object read), 0.031 s; concurrently **290/290 lease and 290/290
  generation heartbeats succeeded (zero failures)**; ticker max gap
  **0.047 s** (no event-loop starvation); no deadlock.
- **Output contract**: resolved from the exact captured binding
  (node 15 / field "images", type output, `soloring_00003_.webp`);
  bytes are RIFF/WEBP; detector reports None (M1 knows JPEG/PNG only) and
  the captured contract is explicitly unconstrained (null) — coherent by
  v0.1 design, no importer weakening. Logical kind video.
- **Publication**: exactly one Take/Asset/Blob; blob
  `07f724f422beab55…`; import replay created **zero duplicates**; the
  real Take **approved through the normal API** (`approved_take_id` set,
  canon re-evaluated). Generation `succeeded`.
- No `/interrupt` issued at any point.

Debugging notes (honest record): three instrumentation defects in the live
runner were found and fixed en route (a monitor blocking the event loop via
`threading.Event.wait()`, a transport wrapper needing `request.aread()`
for multipart capture, and a drift assertion that wrongly treated
translation-bound fields as static); none were product defects. The
release-v2 sampler-slot bug was a REAL workflow defect caught by the live
400 path exactly as designed.

## M5B-4 — live worker-death adoption: COMPLETE (2026-08-16)

A real GPU job survived the abrupt death of its owning SoloRing worker,
and a genuinely fresh worker identity completed the SAME attempt/prompt
with zero resubmission and zero collateral executor effects. Specimen:
`data/m5b4-specimen/` (ledger + DB + blobs preserved).

- **Worker A** = a separate OS process; claimed G4, submitted exactly one
  prompt (P=`4a4f4dd0…`), confirmed durable, KILLED via taskkill /F/T
  while P was demonstrably running (verified in /queue before and AFTER
  the kill — Comfy untouched, P still active).
- **Worker B** = fresh identity; followed the REAL ownership path:
  natural lease staleness → TAKEN_OVER (**30.2 s** after death — the first
  real failover-latency measurement, TTL-bound) → unconditional
  reconciliation → adoption → completion in 468.7 s.
- **Adoption preserved the frame exactly**: attempt `a18af1fa…` unchanged,
  state `confirmed`, submission hash/json unchanged, executor_job_id == P,
  handle unchanged, all provenance hashes unchanged, soft-cancel null;
  the live marker's attempt equals the durable attempt.
- **B's entire client boundary**: **0 /prompt, 0 uploads, 0 queue-deletes,
  0 /interrupt, 0 global history scans** — 7,403 targeted-history + 7,401
  queue reads (reconstruction from P alone via targeted HTTP; the F12
  no-prework remediation proven live), 1 /view stream.
- **Exactly-once**: live history holds exactly one prompt carrying the
  (G,A) marker — P; one Take/Asset/Blob (2,725,842-byte WebP,
  `64d893e4…`); replay reconciliation import created zero duplicates;
  final status `succeeded`.
- WS telemetry irrelevant by construction: B reconstructed running state
  purely from targeted HTTP (no WS dependency in the proof).

Run 1 note (honest): the first attempt aborted on a script-side assertion
that compared the post-adoption attempt against a PRE-claim snapshot
(attempt is legitimately NULL before claim) — instrumentation defect, not
product; the rerun baselines the frame at A's confirmation.

## M5B-5 — live cancellation characterization: COMPLETE (2026-08-16)

Specimen: `data/m5b5-specimen/` (ledger + DB + capability_m5b5.json, copied
to `data/comfy-fingerprint/`). Full backend suite after the product-path
change: **666/666**.

- **Discovery (source + live)**: the pinned 0.33.0 deployment ships an
  ATOMIC per-job endpoint, `POST /api/jobs/{prompt_id}/cancel` —
  server-side `interrupt_if_running` holds the queue mutex and the
  per-prompt interrupt-flag reset makes fall-through onto a successor
  impossible; finished/unknown ids are idempotent no-ops. The plain
  `/interrupt` route (even with prompt_id) is check-then-act and is NOT
  used by the product path.
- **Product change**: `client.cancel_job` (atomic endpoint, strict
  wire normalizer) is now the running-cancel transport; capability mode
  is explicit config — `SOLORING_COMFY_CANCELLATION_MODE`
  (`soft_only` default | `targeted`), `soft_only` remains the default.
- **Phase B (pending collateral)**: P1 running + P2 pending; cancel G2
  through the product API → queue-delete named EXACTLY P2, P1 untouched,
  zero job-cancel/interrupt calls, G2 `cancelled`.
- **Phase D (targeted matrix)**: with the targeted capability, cancel G1
  mid-render → `{"cancelled": true}`, G1 `cancelled`; successor P4
  promoted and completed to a published Take; **repeat cancel(P3) while
  P4 was CURRENT returned `{"cancelled": false}` (no-op)**; unknown id →
  no-op; `/interrupt` never called.
- **Phase C (soft cancel × worker death)**: G5 running under worker A
  (subprocess); user cancel → `soft_cancel_selected_at` durable → A
  killed → fresh worker B adopted through the real path → observed P5 to
  REMOTE TERMINAL SUCCESS → **zero /view, zero deletes, zero cancels,
  zero Take/Asset** → `cancelled`.
- **Phase E (terminal-before-cancel)**: P6 reached remote terminal BEFORE
  the cancel request; the late cancel did not retroactively convert it —
  normal terminal won, one Take published, G6 `succeeded`.
- **Envelope facts**: delete of a nonexistent id → 200 empty (no-op); an
  INTERRUPTED job's history terminal is `status_str:"error"` on this build
  (normalizes to FAILED) — SoloRing's hard-cancel path never depends on
  re-observing that state (it transitions `cancelled` on the atomic
  ACCEPTED result), recorded as a dialect fact.
- **Capability conclusion (persisted)**: pending_cancel SUPPORTED
  (targeting prompt_id, product path proven); running_cancel **TARGETED
  proven** on this deployment (atomic + retry-safe live collateral matrix)
  — runtime default remains SOFT_ONLY with explicit config elevation;
  SAFE_SINGLE_FLIGHT stays disabled by design.

Debugging notes (honest): three script iterations were needed — a
read-before-durable race on executor_job_id, missing determinism in
concurrent submission ordering, and Comfy's step-boundary history-write
lag after an interrupt; plus one dead code block. None were product
defects; each is visible in the run history.

## M5B-6 — restart and history-loss characterization: COMPLETE (2026-08-16)

Specimen: `data/m5b6-specimen/`. Full backend suite after the outage-tolerance
product change: **668/668**.

**Product change (the gate's correctness core)**: the observation loop is now
OUTAGE-TOLERANT (`outage_grace_seconds`, default 30 s) — a transient read
failure never terminates the drive (unreachability is an availability fact,
not prompt evidence; the disappearance tracker is not advanced); only an
outage exceeding the window classifies EXECUTOR_UNAVAILABLE. Unit-proven in
`tests/test_m5b6_outage.py` (transient-survival + window-expiry).

**Measured evidence matrix** (live, dedicated instance):

|                         | before restart | after restart |
|-------------------------|----------------|---------------|
| terminal Pterm history  | present + marker | **gone** |
| running P1 queue        | present        | **gone** |
| pending P2 queue        | present        | **gone** |
| markers                 | present        | n/a (history volatile) |
| /view for known ref     | works          | n/a (history identity gone) |

This deployment keeps ALL queue/history state in memory: a clean restart
loses terminal history, the running queue, AND the pending queue (13.0 s and
11.8 s downtime; first-fail 1.67 s after kill).

- **Transient outage (10 s, Comfy untouched)**: P1 kept rendering; the
  generation stayed `submitted`; exactly ONE /prompt total; connectivity
  restored → same P observed → drive continued. No false terminal.
- **Restart while P1 rendered**: post-restart matrix captured BEFORE any
  worker reaction; the worker then classified reachable-absence as
  **EXECUTOR_JOB_LOST exactly 5.0 s after ready** (the configured
  disappearance grace — measured from first conclusive absence, not from
  downtime start, not reset by the unreachable phase). Zero resubmission,
  zero uploads, zero cancellations caused by the loss.
- **cancel_job(lost P1) → `{"cancelled": false}`** (idempotent no-op against
  vanished ids). A retry remains a NEW Generation/attempt; attempt A stays a
  consumed frame.
- **COMFY_HISTORY_LOST stays conservative**: the runtime emits
  EXECUTOR_JOB_LOST (no durable restart-evidence source exists in v0.1);
  the LEDGER records that a controlled restart positively caused history
  loss on this deployment. The two facts stay distinct, exactly as
  required.
- **No output-directory recovery**: with history identity gone, SoloRing
  cannot prove output identity — interrupted, even though the .webp may
  physically remain in Comfy's output dir.
- The interrupted-history dialect finding from M5B-5 (`status_str:"error"`
  for acknowledged cancellations) is preserved as a diagnostic distinction;
  no wire change was made for it.

Grace evaluation: the 5 s disappearance grace matched the live transition
exactly (5.0 s measured) — kept unchanged. Debugging notes (honest): four
script iterations — a Popen-detached Comfy died with the script's job tree,
a communicate() wedge on the PS relaunch (pipe-handle inheritance), a
stability wait for a flapping window, and a teardown-only proxy
wait_closed() hang after all evidence was captured. All harness defects,
documented in the script; the product change was unit-gated first.

## M5B-7 — final live release gate: COMPLETE (2026-08-17)

Specimen: `data/m5b7-specimen/`. Full backend suite after all M5B product
changes: **669/669 ×2**; stress 3/3 clean on authority/race files; frontend
tsc + 4/4 component tests + production build; bundle scan clean; migration
head 0005, foreign_key_check empty. Deployment profile:
`docs/EXECUTOR_PROFILE.md`.

**Mandatory item 1 — observation cadence**: `SOLORING_COMFY_
OBSERVATION_POLL_SECONDS` (default 1.0 s) is now the single cadence for
every path; the pre-fix 0.05 s default produced the M5B-4 busy loop.
Measured live: **2.0 reads/s, 1.0 s terminal-detection latency** (was
~32 reads/s). The final render: 531 history + 529 queue reads over 529.3 s
— exactly the configured cadence.

**Mandatory item 2 — mechanical capability binding**: `targeted` mode now
requires a characterization record whose executor fingerprint matches the
LIVE deployment (version probe at drive start); record
missing/incomplete/drifted/unreachable → **fails closed to SOFT_ONLY** with
a loud error. Proven live twice (absent record and incomplete record each
failed closed before the good record engaged).

**Final aggregate generation** (release v3, real render, production
cadence, targeted capability mechanically bound): **529.3 s**, exactly ONE
/prompt, ONE upload, ONE /view, one Take/Asset/Blob, 279/0 heartbeat
successes, ticker max gap 0.047 s, bridge threads differ (deadlock guard),
approved through the normal API, `succeeded`.

**UI review (mandatory)**: in the REAL frontend, the take with
`detected_media_type=null` renders — the captured logical `output_kind:
video` drives preview at the presentation boundary; browser decoded the
animated WebP at 848×480 (`complete=true`); Approve clicked in the UI,
canon re-evaluated ("Working state matches approved canon"). No detector
lie; no backend change to serving.

**Stability finding (honest)**: the first four gate attempts crashed the
executor with a native access violation at CLIP-vision weight load — torch
**cu126** on this 20-series GPU/driver (ComfyUI 0.33's own warning). Every
crash was classified correctly by the outage tolerance (EXECUTOR_UNAVAILABLE,
zero resubmission). Upgrading the ComfyUI venv to torch 2.13.0+**cu130**
resolved it; the fingerprint records cu130.

## M5 close-out: every M5B item resolved

| item | state |
|---|---|
| real /prompt | LIVE PROVEN (M5B-3/7) |
| marker round-trip | LIVE PROVEN |
| real upload identity | LIVE PROVEN |
| real /view streaming | LIVE PROVEN (bridge threads differ, bounded) |
| worker-death adoption | LIVE PROVEN (M5B-4) |
| pending cancellation collateral | LIVE PROVEN (M5B-5) |
| targeted running cancellation | LIVE PROVEN |
| retry-safe targeted cancellation | LIVE PROVEN |
| restart/history volatility | LIVE PROVEN (M5B-6) |
| transient outage recovery | LIVE PROVEN |
| terminal-before-cancel precedence | LIVE PROVEN |
| UI review of null-detected video take | LIVE PROVEN (M5B-7) |
| observation cadence bounded | LIVE PROVEN (2.0 reads/s) |
| capability mechanically bound | LIVE PROVEN (fail-closed ×2) |
| response-lost after accepted POST | ADVERSARIAL-DOUBLE PROVEN (M5A) |
| death during /view | ADVERSARIAL-DOUBLE PROVEN (M5A) |
| real WS reconnect | DEFERRED — v0.1 is explicitly HTTP-authoritative; documented in EXECUTOR_PROFILE.md |
| raw WS transport beyond endpoint/framing | DEFERRED (same) |

No M5B item remains pending.

## M5 final-verification patch (2026-08-17) — exact fingerprint binding

The final source verification held M5B-7 on one blocker: the live version
probe compared only `comfyui_version`, so same-version/different-commit
drift could still engage TARGETED. Fixed without another render:

- **ONE versioned contract** (`executors/comfy/capability_record.py`,
  schema v1): the characterization record and the deployment attestation
  share strict loaders; `scripts/m5b5_live_cancellation.py` now EMITS the
  record through the shared builder (never hand-edited).
- **Local deployment attestation**: `scripts/launch_comfy.py` (the pinned
  launcher) reads the live git revisions of the ComfyUI checkout and the
  GGUF custom node at launch and writes
  `data/comfy-fingerprint/deployment_attestation.json`.
  `resolve_capability` requires record.commit == attestation.commit
  (comfyui AND gguf) == live version. Any miss fails closed to SOFT_ONLY.
- **Regressions** (`tests/test_m5b7_binding.py`, 9 tests): the audit
  reproduction (same version, different commit) → SOFT_ONLY; gguf drift →
  SOFT_ONLY; missing record/attestation → SOFT_ONLY; version drift and
  unreachable probe → SOFT_ONLY; exact → TARGETED; strict record and
  attestation contract tampering.
- **Live probe** (no GPU cost): exact attestation → TARGETED engaged;
  tampered attestation (commit 9×40) → fail-closed drift log + SOFT_ONLY;
  removed attestation → SOFT_ONLY.
- **Final-gate assertion**: `scripts/m5b7_final_gate.py` stages record +
  attestation into the specimen and FAILS unless
  `resolve_capability(...).mode == TARGETED` before recording the proof.
- Docs: README stale re-gating line removed; this file's deferral section
  retitled as historical; executor profile corrected to "RTX 30-series
  GPU" and now documents the attestation mechanism.

Suite: **678/678 ×2** (669 + 9 binding regressions); stress 3/3; frontend
tsc + 4/4 + production build.

## Final verification patch 2 (2026-08-17) — process-bound attestation

The second final-verification hold narrowed to the cancellation-capability
attestation boundary; both holes are closed (no GPU rerender):

1. **Exact characterized contract** (`capability_record.py`): the record
   loader now requires mode==TARGETED, endpoint==`POST
   /api/jobs/{prompt_id}/cancel`, targeting_key==`prompt_id`,
   uniqueness_guarantee==`proven`, retry_safety==`safe` — EXACT values, so
   a record characterizing an unproven contract (`POST /interrupt`,
   `unproven`, …) is INVALID and resolves SOFT_ONLY. Adversarial tamper
   cases added for each field.
2. **Process-bound attestation (schema v2)**: `launch_comfy.py` verifies
   BOTH git trees are CLEAN (commit equality != source equality), launches,
   waits for readiness, proves the listener PID owns :8188, captures the OS
   process-creation fingerprint, and only then ATOMICALLY publishes the
   attestation. `resolve_capability` re-verifies at use time that the
   attested PID + creation fingerprint still own the executor port — a
   stale attestation cannot survive a manual same-version replacement.
3. **No unsafe bypass**: `client=None` targeted resolution fails closed.

Live proofs (no GPU cost): exact v2 attestation → TARGETED (against the
running server); attested pid replaced in the file → SOFT_ONLY with the
stale-attestation drift log; no client → SOFT_ONLY; dirty GGUF tree → the
launcher REFUSES (exit 1, server untouched) and succeeds again after
`git checkout --` (exit 0, fresh attestation).

Suite: **680/680 ×2** (678 + 2 new binding regressions, now 11 in
`test_m5b7_binding.py`); stress 3/3; frontend tsc + 4/4 + production build.

## Final verification patch 3 (2026-08-17) — executor-instance binding

The third hold narrowed to WHICH executor instance the attestation covers;
both defects are closed (no GPU rerender):

1. **Origin-bound attestation (schema v3)**: the attestation now carries
   `executor_origin` (`http://127.0.0.1:8188`, loader-enforced loopback —
   v0.1 is a local-only dedicated deployment). `resolve_capability`
   requires the normalized CLIENT origin to EQUAL the attested origin
   before TARGETED: a client pointed at a remote same-version executor
   fails closed on the loopback policy, and even `localhost` vs
   `127.0.0.1` fails closed on origin equality. The safety proof now
   applies to the executor receiving the cancellation request.
2. **Launcher proves lineage**: after readiness the launcher reads back
   the launched PID and walks `ParentProcessId` (bounded CIM ancestry)
   requiring the :8188 listener to BE the launched process or its
   verified descendant (the venv-shim child). A pre-existing foreign
   listener that dodged the kill pattern can no longer be attested with
   our commits — proven directly: an unrelated live PID is refused.
3. **Untracked source counts as dirty** (only inert suffixes .log/.txt/
   .png/.json/.csv allowed).
4. **m5b7 gate self-contained**: `comfy_cancellation_mode="targeted"` is
   set BEFORE the capability assertion.

Live proofs (no GPU cost): exact v3 attestation + local client → TARGETED;
remote-origin client (`http://10.55.66.77:8188`) → SOFT_ONLY (loopback
policy); alias `localhost` → SOFT_ONLY (origin equality); unrelated-PID
descendant check → refused. Suite: **683/683 ×2** (680 + 3 origin
regressions, now 14 in `test_m5b7_binding.py`); stress 3/3; frontend tsc +
4/4 + production build.

## Final verification patch 4 (2026-08-17) — executable extension set pinned

The fourth hold found that `custom_nodes/` sits outside the attestation:
the pinned ComfyUI `.gitignore` ignores the whole directory, so additional
imported Python changed the executed deployment without dirtying either
attested tree. Closed with the upstream mechanism, exactly as prescribed:

- **Canonical launch** now runs `--disable-all-custom-nodes
  --whitelist-custom-nodes ComfyUI-GGUF` — the executed extension set is
  mechanically enforced, not an assumption. Live-verified after relaunch:
  GGUF nodes present; the previously-present `websocket_image_save`
  custom node is NO LONGER loaded.
- **Attestation schema v4** records `custom_node_policy` and the loader
  requires EXACTLY `{"disable_all": true, "whitelist": ["ComfyUI-GGUF"]}`.
  Old v3 attestations are invalid → SOFT_ONLY (migration behavior
  live-proven: the prior v3 file rejected with the schema-version drift
  log; the fresh v4 whitelisted launch → TARGETED).
- Regressions: v3-no-policy → SOFT_ONLY; four policy tamper shapes
  rejected (disable_all=false, extra whitelisted node, empty whitelist,
  missing block); a launcher-args scan proving the flags pin exactly
  ComfyUI-GGUF and nothing else.
- Stale v1/v2 attestation docstrings corrected.

Suite: **686/686 ×2** (683 + 3 new regressions, now 17 in
`test_m5b7_binding.py`); stress 3/3; frontend tsc + 4/4 + build.

## Final verification patch 5 (2026-08-17) — structurally exact policy

The fifth verification found the v4 policy check validated the two
characterized fields but accepted EXTRA keys in `custom_node_policy`
(`{"disable_all": true, "whitelist": […], "unexpected": …}` passed). One
line closes it — `set(policy) == {"disable_all", "whitelist"}` — with a
fifth tamper regression proving the extra-key shape now rejects. The two
stale v1 attestation docstrings (launcher + loader) were corrected to v4.
Suite: **686/686 ×2** (binding suite 17/17 with the strengthened shape);
the running v4 attestation still resolves TARGETED live.

## Historical: pre-M5B deferral list (all items now resolved above —
## retained for the record, superseded by the M5 close-out table)
- Any behavior against a **real ComfyUI HTTP surface**: actual wire dialect
  of the deployed version, real /upload/image auto-rename behavior, real
  /view streaming semantics, real queue/history schemas under load.
- **WebSocket**: M5A-7 proved WS event normalization and telemetry/authority
  semantics against doubles (`wire.normalize_ws_event` +
  `WsObservationAdapter`: terminal WS events are never lifecycle authority;
  they trigger targeted-HTTP reconciliation). What remains for M5B is the
  real /ws connection, framing, reconnect, and live telemetry behavior —
  the socket transport itself is not built.
- Capability report from live evidence (default SOFT_ONLY stands until M5B
  characterizes the deployment; hard cancel requires TARGETED + retry-safe).
- Rediscovery/observation grace tuning against real queue latencies
  (defaults: 5 s submission, 5 s disappearance; M5B may tune).
- **The async↔sync /view streaming bridge under real load** (mandatory M5B
  transport proof per the M5A closure review): `/view` transfer active
  concurrently with worker lease heartbeat, Generation heartbeat, and async
  observation/polling — no deadlock, bounded event-loop latency. The
  `run_coroutine_threadsafe(...).result()` bridge is safe only while the
  synchronous consumer runs off the loop thread; a same-thread execution
  would deadlock. The MockTransport doubles cannot reproduce real socket
  scheduling.
- End-to-end latency/soak behavior, Comfy restart mid-execution, and
  history-eviction (COMFY_HISTORY_LOST) classification with positive
  evidence — the M5A-7 conservative default (COMFY_JOB_LOST) applies.

## Configuration surface (backend only; SOLORING_ namespace)
- `SOLORING_EXECUTOR` — `fake` (default) | `comfy`; applies at NEW Generation
  creation only; worker dispatches from the persisted row value.
- `SOLORING_COMFY_BASE_URL` — executor base URL (default
  `http://127.0.0.1:8188` when unset). No other Comfy config exists; no
  Comfy value ever reaches the web frontend.
