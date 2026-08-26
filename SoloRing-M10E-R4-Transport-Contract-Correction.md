# SoloRing M10E — R4 Transport-Contract Correction

**Revision:** R4 — narrow correction to the frozen R3 implementation contract
**Status:** CONTRACT CORRECTION — accompanies closing candidate `a0842f2…` (superseded by the commit carrying this document)
**Predecessor baseline:** **M10 @ `aa279000fd83536e3c210fb6ce511942eeb88d68`**
**Scope:** ONE correction. R4 changes nothing about the M10E authority
model, durable provenance, WorkflowSpec v3, fingerprints, the golden
oracle, persistence atomicity, or Exact Rerun identity semantics. It
corrects the frozen R3 wording of the worker **executor-transport
contract**, which the pinned live smoke proved was frozen too narrowly.

> **Authorization rule unchanged.** This document authorizes nothing
> beyond correcting the frozen contract text. M10E closure still requires
> the independent §31/E-106 source gate. M10F, GitHub Release, retagging,
> and publication remain unauthorized unless separately authorized.

---

## 1. Why R4 exists

The R3 live-smoke gate (E-090..E-095) executed the real schema-3 path
against the certified pinned executor and established two executor facts
that R3's transport wording did not anticipate:

1. `WanVideoControlnet.control_images` (ComfyUI-WanVideoWrapper @
   `088128b2…`) is an `IMAGE`-typed tensor input. A bare uploaded-filename
   string at that field is not executable: the certified §114 consumption
   shape loads the control frames through `LoadImage` nodes batched into a
   frame video (`ImageBatch`), and the tensor link feeds `control_images`.
2. The M10A production template was a structural fragment (no model chain
   into the applies/sampler, no text/decode/output wiring). R4's sibling
   commit completed it to the **certified §114 executable shape**; that
   completion is a template-authoring fix under R3 §5.2 and is not
   re-litigated here.

R3 E-086 froze "no … per-frame upload protocol … for D0 provenance" with
the intent that **nothing per-frame becomes durable provenance**. The
implemented, live-proven transport splits each retained stream Blob into
its 17 exact PNG frame files for upload — an *attempt-local executor
materialization* — which R3's wording read literally forbids. The
implemented path is correct; the frozen wording was too narrow. R4
corrects the wording and freezes the boundary explicitly.

## 2. The frozen durable/transport boundary (binding)

1. **Durable provenance is exactly one `DerivedSpatialArtifact` + one
   content-addressed Blob per control stream.** Nothing about frames is
   durable: no per-frame DB row, no per-frame package artifact, no
   per-frame WorkflowSpec entry, no per-frame derived identity, and no
   per-frame rerun identity. (Unchanged from R3; restated because E-086's
   correction must not be readable as opening the durable model.)
2. **The retained Blob is the immutable historical identity** of the
   control stream. Its bytes are never re-encoded, re-rendered, or
   re-derived at execution time.
3. **Attempt-local frame materialization:** worker execution MAY
   deterministically split the retained stream Blob into its constituent
   PNG frame files when — and only when — the retained bytes parse as a
   concatenation of complete PNG streams covering **all** bytes (the
   frozen D0 grammar is 17 such frames). Content that does not so parse
   is uploaded whole as a single opaque attempt-local file (legacy
   robustness branch; never treated as frames). The split is a pure
   byte-slice of the verified retained Blob — it is **not** a renderer or
   encoder in the sense of R3 §33 (no byte is produced that the retained
   Blob does not already contain).
4. **Frame uploads are non-durable transport state**, exactly like
   upload filenames, subfolders, and submission markers (R3 §19.1/E-077):
   they are attempt-scoped, may differ between the source execution and
   its rerun, and never become historical identity.
5. **Canonical-order reconstruction identity:** concatenating the uploaded
   frame bytes in canonical frame order MUST reproduce the retained Blob
   bytes exactly. This is a binding acceptance assertion (test-pinned),
   and it is the sense in which the uploaded bytes "are" the retained D0
   bytes.
6. **Translator adapter:** for `format = "soloring.spatial.v1"` the pure
   translator MAY deterministically construct the certified
   `LoadImage×N → ImageBatch×(N−1)` adapter from the verified uploaded
   frame references (N = the uploaded frame count; N = 1 degenerates to
   the single `LoadImage` link). Adapter node ids are namespaced by the
   input key (`{key}::load::{i}` / `{key}::batch::{i}`), MUST be checked
   against template-node collision, and the **chain-head link — not a
   raw filename — binds to the manifest-declared `control_images`
   node/field**. The manifest binding remains the sole binding authority;
   no existing node is ever discovered or chosen heuristically.
7. **Exact Rerun repeats only the attempt-local materialization** of the
   already-retained Blob: the same deterministic split and upload of the
   same retained bytes, still with **zero D0 rematerialization** (no
   compiler, materializer, or registration call; durable identities
   byte/row identical to the source attempt).

## 3. Amended plan text

### §17.4 (Derived translation contract) — amended binding sentence

> For each verified uploaded derived input, the translator must bind the
> control stream to exactly the node/field certified by the captured
> manifest v3. For `format = "soloring.spatial.v1"` the bound value is the
> certified frame-adapter chain-head LINK (§2.6 above) constructed from
> the verified attempt-local frame uploads whose canonical-order
> concatenation reproduces the retained Blob exactly. A raw filename at a
> tensor field is not a valid binding value.

The failure matrix of §17.4 is otherwise unchanged; the
missing/extra/duplicate/mismatch/node/field/format/ownership failures all
still apply, and the adapter adds its own fail-closed condition
(generated-id collision with the captured template).

### §23.2 (D0 work scale) — amended transport note

> A complete multi-frame control artifact is represented by one
> content-addressed Blob/provenance item per control stream. Executor
> transport may materialize that retained artifact into per-frame
> attempt-local uploads (§2.3-2.5); this is bounded transport work
> proportional to the frozen 17-frame grammar, introduces no durable
> per-frame state, and no per-frame DB row, per-frame package read, or
> per-frame durable identity exists.

### §33 (Forbidden shortcuts) — clarifying note

> Deterministic attempt-local splitting of a retained D0 Blob into its
> exact constituent PNG frames is byte-slicing of already-verified
> retained bytes, not a "second renderer/encoder": it produces no byte
> the retained Blob does not contain, and the canonical-order
> concatenation identity is test-pinned. Re-encoding, re-rasterizing, or
> re-deriving frame bytes from authority remains forbidden.

## 4. Amended acceptance criteria

- **E-062** — Worker verifies sibling/provenance/Blob identity and
  uploads the exact retained D0 bytes before translation: either the
  whole retained Blob, or its deterministic attempt-local frame split
  whose canonical-order concatenation reproduces the retained Blob bytes
  exactly (asserted, not assumed).
- **E-063** — Every verified uploaded derived reference participates in
  the pure translation and the control stream binds to the exact
  captured manifest-v3 node/field **through the certified
  soloring.spatial.v1 frame adapter** (chain-head link at the declared
  node/field; no raw filename at the tensor field; no heuristic node
  discovery).
- **E-086** — No per-frame DB row, per-frame package read, or per-frame
  **durable** identity is introduced for D0 provenance. Attempt-local
  executor frame materialization of the retained stream Blob is
  permitted transport state (§2), bounded by the frozen 17-frame grammar,
  and its canonical-order concatenation must reproduce the retained Blob
  exactly.
- **E-091** — Live smoke proves the application's retained D0 Blobs are
  the exact bytes uploaded by the worker (whole or via the frame split's
  reconstruction identity) and reach the certified control node/fields
  through the frame adapter.
- **E-077** — unchanged text, now explicitly covering frame-upload
  transport references as attempt-local non-durable state (the delivered
  regression already asserts exactly this).

## 5. §31 source-gate amendment

Gate question 16 gains: *"Is the executor transport a deterministic
attempt-local materialization of the retained Blobs — one durable
artifact/Blob per stream, frame uploads non-durable, concatenation
identity pinned — with no durable per-frame state anywhere?"* Any "no" is
a closure blocker.

## 6. Source/test agreement map (as delivered)

| R4 clause | Pinning test |
|---|---|
| §2.1-2.2 one durable artifact+Blob per stream | test_m10e_generation (3 siblings/3 artifacts at capacity; convergence) |
| §2.3 deterministic split, all-coverage or opaque | tests/test_m10e_worker_translation.py::test_transport_splits_retained_d0_blob_into_exact_frames |
| §2.5 concatenation identity | same test + test_m10e_rerun.py::test_rerun_transport_references_are_nondurable |
| §2.6 adapter + collision guard + link binding | test_m10e_worker_translation (chain, multi-frame expansion, collision) |
| §2.4/§2.7 non-durable transport, rerun reuse, zero remat | test_m10e_rerun (E-077; spies; mutation isolation) + live smoke steps 10-11 |

## 7. What R4 does NOT change

Every other R3 section and criterion stands unchanged, including the
authority boundary, fingerprint taxonomy, golden-oracle layers, capacity
semantics, atomic persistence, error vocabulary, and the no-migration
posture. R4 adds no new durable error code, no migration, and no
authority surface.

---

# PLAN STATUS

```text
Document                              SoloRing M10E R4 Transport-Contract Correction
Predecessor baseline                  M10 @ aa279000fd83536e3c210fb6ce511942eeb88d68
Corrects                              R3 E-086 / §17.4 / §23.2 / §33 / E-062 / E-063 / E-091 wording
M10E implementation                   DELIVERED (closing candidate carries this document)
M10E closure                          PENDING independent §31/E-106 review
M10F                                  NOT AUTHORIZED
GitHub Release                        NOT AUTHORIZED
M10 tag movement                      FORBIDDEN
```

**End of R4.**
