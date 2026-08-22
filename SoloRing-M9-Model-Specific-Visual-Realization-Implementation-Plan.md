# SoloRing M9 — Model-Specific Visual Realization Implementation Plan

**Plan status:** **frozen M9 implementation contract**; implementation is **not authorized** by this document.  
**Predecessor baseline:** **M8 @ `6879474a1d57177616edba29c9dcff98ef0d8714`**  
**Predecessor tag:** `M8`  
**Predecessor tree:** the published M8 r4 source-gated tree, authoritative artifact `SoloRing-M8-r4.zip` SHA-256 `8baac0adf22defb2969d0af677ec5d119ad6f65a5c9f6f5720aaf01974a9c78f`.  
**Certified M8 plan hash of record:** `28c1e457ff7b9ef21e36ed2d184ba3cb305a940fe3c226d933c1f2757cd3d6ff`.  
**Planning boundary:** M9 planning only. No implementation, publication, tagging, branch-protection change, or M10 work is authorized by this plan.

**r3 source-fit disposition:** the published M8 artifact has been re-audited through the M9 review cycle. `generation_inputs.reference_role` exists in migration `0002` and the ORM, so the base no-migration projection remains source-fit. The current deployment attestation pins ComfyUI/GGUF revisions and the executable custom-node policy but does **not** pin model-weight bytes; the baseline workflow identifies five model-bearing loader artifacts by mutable filename only. M9 therefore requires an immutable, content-addressed `ExecutionModelFingerprint` captured with schema-2 packages and referenced by every non-empty M9 Generation. The audit also proves that published `Settings` exposes `comfy_base_url` but no model-root filesystem mapping, so r3 freezes an explicit schema-1 Comfy model-root adapter contract for `unet`, `vae`, `clip`, and `clip_vision`; schema-2 execution may not silently skip live byte verification when any required root is unavailable.

---

# 0. Milestone mandate

M9 installs the execution layer that turns SoloRing's **captured semantic state + approved visual authority** into a deterministic, inspectable, immutable, model-specific conditioning request.

The governing direction is:

```text
M7 semantic production truth
        ↓
M8 approved visual authority
        ↓
ShotRevision historical capture
        ↓
M9 canonical CapturedVisualAuthority value
        ↓
ONE model-specific realization compiler
        ↓
Generation immutable execution specification
        ↓
executor-specific translation/materialization
        ↓
model execution
```

Never:

```text
model prompt / adapter weights / Comfy graph / embedding / LoRA
        ↓
defines M8 authority
```

M9 answers:

> Given the exact visual authority captured for this Shot, and given this exact model/workflow capability package, what conditioning inputs and parameters must this Generation use?

M9 does **not** answer:

> What does Eva look like?

That was settled by M8.

M9 also does **not** answer:

> Where is Eva in three-dimensional space, where is the hotel desk, or what should a reverse-angle camera see?

That remains M10 territory.

The defining M9 invariant is:

> **Current state may create a new future Generation. Current state may never reinterpret a historical Generation.**

---

# 1. Architectural exit criterion

M9 closes only when SoloRing can prove this chain end to end:

```text
captured ShotRevision schema 4
+ reconstructed/cross-validated captured M8 visual authority
+ exact captured workflow package release
+ exact captured RealizationProfile
+ exact captured ExecutionModelFingerprint
        ↓
ONE deterministic realization compiler
        ↓
immutable Generation workflow spec schema 2
+ immutable GenerationInputs
        ↓
exact historical executor translation
+ live model/runtime compatibility verification
        ↓
submitted payload demonstrably contains every required realized binding
```

with these guarantees:

1. model-specific realization never mutates or redefines M8 authority;
2. a required M8 visual facet that the selected realization package cannot support blocks **new Generation creation** before expensive execution;
3. optional visual authority may be omitted only under the frozen atomic-facet rules and every omission is inspectable;
4. the selected reference set is deterministic, facet-atomic, and provenance-complete;
5. preview and capture use the same canonical authority value and the same compiler;
6. the exact realization profile, workflow package, and execution-model fingerprint are captured before Generation persistence;
7. Generation execution consumes only captured immutable state plus a live environment that is verified against the captured requirements;
8. Exact Rerun copies the original realization specification and inputs verbatim and never recompiles;
9. changing current M8 state, profile, package, or model installation never changes a historical Generation or rerun specification;
10. executor translation binds only explicitly declared captured channels/model bindings—no graph heuristics;
11. process success is not misrepresented as proof that the model visually obeyed the references;
12. feature-film scale increases rows/bytes processed, not SQL round trips per facet/anchor/item;
13. the source gate proves package coherence, historical isolation, model-byte identity, no-authority-transfer, bounded query shape, and race behavior mechanically.

M9's reproducibility claim after closure is deliberately bounded:

```text
exact captured logical execution specification
+ exact captured reference bytes
+ exact captured model-weight bytes required by the package
```

It still does **not** claim byte-identical rendered media across GPU/driver/library changes unless a later source gate separately proves that stronger environment property.

---

# 2. Architecture-pattern applicability

The Architecture Pattern Register is a standalone project architecture artifact. M9 binds only the patterns owned by this problem.

## 2.1 PRIMARY M9 bindings

| Pattern | M9 binding |
|---|---|
| **APR-003** — authority points downward | M8/ShotRevision authority is input to M9; realization cannot redefine it. |
| **APR-004** — hide external churn | Stable SoloRing realization/profile contracts sit above Comfy/model-specific node details. |
| **APR-015** — explicit readiness | New Generation creation refuses known unsupported/incomplete required realization before queueing expensive work. |
| **APR-020** — immutable execution inputs | Realization selection, profile identity, model identity, parameters, bindings, and selected Blob identities are captured in the Generation. |
| **APR-021** — content identity where bytes matter | Realization profile bytes, workflow artifacts, and selected media remain hash-addressed. |
| **APR-023** — fail closed on incomplete provenance | Historical realization/profile/input mismatch is corruption, never a reason to rebuild from current state. |
| **APR-026** — logical vs byte reproducibility | M9 promises exact captured execution specification; byte-identical media still requires a fully pinned compatible environment and may remain non-guaranteed. |
| **APR-040** — inspection/execution parity | The realization preview/inspector displays the exact compiler output that Generation creation captures. |
| **APR-041** — process success != production success | Successful conditioning/submission proves request conformance, not visual identity success; Take approval remains creative acceptance. |
| **APR-044** — bounded query shape | M9 reconstruction/compilation must batch captured visual rows and Asset/Blob provenance. |
| **APR-050** — UI exposes authority | UI edits/selects execution configuration only through server contracts; it never invents realization state locally. |
| **APR-051** — honest unresolved state | Unsupported required facets, over-capacity channels, missing profiles, and package drift are shown explicitly, with no fabricated readiness. |
| **APR-060** — semantic fact precedes realization | M9 consumes M7/M8 truth; it never authors semantic facts. |
| **APR-062** — model-specific realization below state | This milestone is the direct implementation home of APR-062. |
| **APR-070** — source gate before publication | Implementation report alone cannot close M9. |
| **APR-071** — evidence classification | Supplied test evidence and independently reproduced evidence stay distinct. |
| **APR-072** — tests prove their names | Realization races/isolation/scale tests mechanically establish the claimed condition. |
| **APR-073** — artifact fidelity | Closure artifact must faithfully represent Git-tracked source bytes and the exact captured realization package. |

## 2.2 INHERITED bindings

M7/M8 historical and concurrency rules remain binding where M9 crosses them:

- APR-012 — one resolver/canonical builder;
- APR-013 — current/history isolation;
- APR-016 — no empty higher-schema alternative;
- APR-017 — corruption never invents tie-breakers;
- APR-024 — database provenance graph, not filesystem convention;
- APR-025 — Exact Rerun current-state isolation;
- APR-030 — fenced derived writes;
- APR-031 — explicit coherent reads;
- APR-032 — identical capture convergence where the domain defines identity;
- APR-033 — mechanically forced race proofs.

## 2.3 Deliberately not owned by M9

- APR-063 spatial authority is M10.
- APR-064/068 post-production correction/tracking may later realize or repair continuity but do not enter M9's durable authority model.
- APR-066 editorial/finishing remains deferred.
- APR-042 optimized/reference-path equivalence is not activated unless M9 introduces a semantically risky optimization.

---

# 3. Frozen predecessor source-fit audit

M9 is designed against the published M8 tree at `6879474a1d57177616edba29c9dcff98ef0d8714` and the authoritative `SoloRing-M8-r4.zip` tree.

| Predecessor seam | Published behavior / verified fact | M9 extension | Required proof |
|---|---|---|---|
| `generation/service.py::create_generation_request` | Captures exact workflow package; captures/reuses ShotRevision; derives GenerationInputs/prompt/parameters; persists immutable Generation. | Capture schema-2 package release, construct canonical M8 authority value, compile M9, then assemble legacy + realization inputs before persistence. | One immutable creation path; no second post-persistence realization. |
| `generation/input_mapping.py` | Pure legacy ShotReference mapping from captured ShotRevision references. | Keep it as the legacy mapper; M9 compiler emits only realization-backed input projection. Final merge/cardinality is Generation assembly, not compiler logic. | Golden legacy fixtures unchanged; no combined-cardinality logic inside `compile_realization()`. |
| `Generation.model/model_version` | Nullable columns already exist. | Populate from captured profile/model identity only when non-empty M9 realization exists. | No migration required for logical model id/version. |
| `generation_inputs.reference_role` | **Mechanically verified present** in migration `0002_temporal_domain_storage.py` and `GenerationInput` ORM. | Reuse `(input_key, position, asset_id, blob_hash, reference_role)` for selected M8 reference bytes. | Exact projection validation against RealizationSpec. |
| `workflow_spec_json/hash` | Logical workflow spec schema 1 captured at Generation creation. | Add workflow-spec schema 2 only when non-empty M9 realization exists. | No empty schema-2; exact schema-1 bytes for no-realization cases. |
| `workflows/manifest.py` | Strict manifest schema 1; legacy input bindings use `source_role`. | Add manifest schema 2 with discriminated `shot_reference` / `realization_channel` sources. | Recursive unknown-field rejection; schema-1↔schema-2 legacy binding compatibility fixture. |
| `workflow-package.json` + artifact store | Descriptor binds exact manifest + template hashes; capture verifies one coherent release before DB work. | Package schema 2 binds manifest + template + RealizationProfile + ExecutionModelFingerprint. | Descriptor-before/after race proof; one complete A or B, never hybrid. |
| `executors/comfy/bindings.py` | Exact manifest node/field validation; no graph heuristics. | Validate realization input bindings **and** exact model-fingerprint node/field/name bindings against captured template. | Missing/mismatched target fails before queue/submission. |
| `executors/comfy/translate.py` | Pure captured logical spec + historical manifest/template + materialized inputs → executor payload. | Consume schema 2 without current M8/profile; bind realization channels from captured logical inputs/parameters only. | Pure fixture-pinned translation; compiler/profile unavailable during worker execution. |
| `worker/comfy_pipeline.py` | Retrieves historical manifest/template and materializes immutable GenerationInputs. | Also retrieve/verify captured profile + ExecutionModelFingerprint; verify live model bytes/runtime requirements before translation/submission. | Current installed package is irrelevant to historical execution. |
| `settings.py::Settings` | Published M8 exposes `comfy_base_url` but no filesystem mapping for Comfy model-loader roots. | Add explicit optional `Path` settings `comfy_model_root_unet`, `comfy_model_root_vae`, `comfy_model_root_clip`, and `comfy_model_root_clip_vision`; schema-2 worker verification resolves fingerprint root keys only through this closed mapping. | Unset/unreadable required root fails `EXECUTION_MODEL_INCOMPATIBLE`; no filename-only or directory-search fallback. |
| `generation/rerun.py` | Copies durable Generation specification and GenerationInputs under `BEGIN IMMEDIATE`. | Copy schema-2 spec/model fields/input set verbatim; never invoke M9 compiler/current profile/current M8. | Query spy + compiler/current-resolver monkeypatch failure. |
| M8 ShotRevision schema 4 | Captures approved visual authority + normalized historical provenance. | M9 reconstructs one canonical `CapturedVisualAuthority` value and revalidates the captured `visual_reference_pack_hash`. | Current M8 can change with no historical effect. |
| Deployment attestation v4 | Pins exact ComfyUI commit, ComfyUI-GGUF commit, live serving process, and whitelist policy. | Retain this as runtime-code/extension identity; do not pretend it identifies model weights. | Stable fields verified against captured ExecutionModelFingerprint runtime requirements. |
| Baseline `workflow.json` | Names Hunyuan model artifacts by mutable filenames (`*.gguf`, `*.safetensors`). | Add content hashes for every model-bearing loader binding in ExecutionModelFingerprint. | Live file bytes must hash to the captured identities before submission. |

## 3.1 Source-fit conclusion

The published baseline already contains the durable relational containers M9 needs:

- `Generation.model` / `model_version`;
- immutable `workflow_spec_json/hash`;
- immutable `GenerationInputs`, including `reference_role`;
- captured workflow artifact store;
- pure Comfy translation;
- Exact Rerun copy semantics.

Therefore **the base M9 architecture requires no database migration**. There is no `0010` migration in this plan.

M9 does require an execution-configuration extension in `Settings`, not a relational migration: four explicit model-root `Path | None` fields under §6.4. They are worker/deployment configuration only and never historical identity; historical identity remains the captured fingerprint hashes and bytes.

The published runtime/package identity is, however, under-bound for model-weight identity: workflow bytes select model files by name, while deployment attestation v4 pins executor/custom-node revisions but not model-file content. M9 therefore closes this gap with a content-addressed `ExecutionModelFingerprint` package artifact (§6.3, §27).

If implementation discovers any additional relational requirement not representable safely in the existing tables, that is a plan-change event. Stop and return to architecture review before adding `0010`; do not invent a migration merely for milestone symmetry.

---

# 4. Core authority model

## 4.1 M8 authority remains sovereign

M8 says:

```text
Eva / face
→ exact state-specific VisualAnchor
→ approved VisualAnchorRevision
→ captured visual authority
```

M9 may decide:

```text
use primary only
strength = 0.85
channel = identity_reference
model = X
adapter mode = Y
```

Those are **realization decisions**, not visual authority.

Changing M9 realization policy must never:

- create/update a VisualFacet;
- create/update a VisualAnchor;
- approve/unapprove a VisualAnchorRevision;
- alter a ShotRevision;
- change the meaning of a Feature value;
- promote a generated result into authority.

## 4.2 M9 authority is execution authority only

M9 introduces one durable execution concept:

### `RealizationSpec`

An immutable canonical value nested in a Generation's logical workflow specification.

It answers:

> Exactly how did this Generation ask this model/workflow to realize the captured M8 visual authority?

It is historical execution provenance.

It is not current production truth.

## 4.3 `RealizationProfile`

A versioned SoloRing-native **execution configuration artifact** shipped with a workflow package.

It describes:

- model identity;
- logical realization channels;
- exact M8 facet selectors supported by each rule;
- allowed M8 reference roles;
- per-channel capacity;
- deterministic item-selection policy;
- model-specific parameter overrides;
- which workflow logical input keys receive the selected bytes.

It does **not** contain:

- current Shot IDs;
- VisualAnchor IDs;
- approved-reference choices for a particular Shot;
- executor-local filenames;
- Comfy prompt IDs;
- mutable filesystem paths;
- current DB state.

The profile is configuration used to compile a Generation, not a production-state authority.

---

# 5. The critical M9 rule

> **A model-specific conditioning representation is never allowed to become visual authority.**

The exact one-way relationship is:

```text
Approved M8 visual authority
        ↓
M9 selects/materializes references and parameters
        ↓
model-specific execution request
```

Never:

```text
model embedding / LoRA / prompt / adapter settings
        ↓
M8 reference pack rewritten to match it
```

If a model cannot faithfully represent an M8 requirement, the result is:

```text
M9 NOT READY for that model/workflow
```

not:

```text
M8 authority weakened until the model accepts it
```

---

# 6. Realization package structure

A Comfy workflow package that supports M9 contains **four** captured artifacts:

```text
manifest.json
workflow.json
realization-profile.json
execution-model-fingerprint.json
```

plus one package descriptor that binds all four raw-byte hashes.

The descriptor defines a `PackageReleaseIdentity`:

```text
schema_version
workflow_id
workflow_version
manifest_hash
workflow_template_hash
realization_profile_hash          # schema 2 only
execution_model_fingerprint_hash  # schema 2 only
```

The release identity is a complete package fact. A profile or model fingerprint is never selected independently from a different release.

## 6.1 Package schema 1 remains valid

Existing package schema 1 remains the exact legacy contract:

```text
manifest + template
```

It has no M9 realization semantics and no model-weight fingerprint contract.

A schema-1 package may generate only when the captured effective M8 visual authority is empty. Non-empty M8 authority must never be silently ignored; it requires an M9-capable package.

## 6.2 Package schema 2

Exact semantic shape:

```json
{
  "schema_version": 2,
  "workflow_id": "...",
  "workflow_version": 4,
  "manifest_hash": "...",
  "workflow_template_hash": "...",
  "realization_profile_hash": "...",
  "execution_model_fingerprint_hash": "..."
}
```

Rules:

- all hashes are lowercase 64-hex SHA-256 of the exact raw artifact bytes;
- package workflow identity must agree with manifest/profile/fingerprint identities;
- profile model id/version must agree with ExecutionModelFingerprint model id/version;
- all four artifact byte buffers are read, hashed, and parsed from the same captured buffers;
- the descriptor is read before and after artifact capture and must identify the same release;
- artifact-store placement is content-addressed and may occur before DB work, but placement does not imply semantic validity;
- schema 2 missing either profile or model fingerprint is invalid;
- schema 1 cannot claim M9 semantics.

## 6.3 ExecutionModelFingerprint schema 1

Because the frozen M8 deployment does not content-identify model weights, M9 schema-2 packages require this exact execution artifact class.

Semantic shape:

```json
{
  "schema_version": 1,
  "model_id": "hunyuan-video-i2v",
  "model_version": "...",
  "runtime_requirements": {
    "comfyui_commit": "40-lowercase-hex",
    "custom_nodes": {
      "ComfyUI-GGUF": "40-lowercase-hex"
    },
    "custom_node_policy": {
      "disable_all": true,
      "whitelist": ["ComfyUI-GGUF"]
    }
  },
  "artifacts": [
    {
      "artifact_key": "video_unet",
      "storage_root_key": "unet",
      "node": "98",
      "field": "unet_name",
      "declared_name": "hunyuan-video-i2v-720p-Q4_K_M.gguf",
      "sha256": "64-lowercase-hex"
    }
  ]
}
```

Schema-1 rules:

- recursive unknown fields rejected;
- `model_id` / `model_version` are non-empty normalized strings and exactly match the RealizationProfile;
- `comfyui_commit` and every custom-node commit are exact 40-hex Git revisions;
- schema 1 custom-node policy is exactly the characterized whitelist policy unless this plan is revised;
- `artifacts` is non-empty;
- `artifact_key` is unique and is only a package-local execution label;
- `(node, field)` is unique; no two fingerprint entries claim the same loader binding;
- `storage_root_key` is an explicit executor adapter key, never inferred from node class or filename;
- for the baseline Hunyuan package, the allowed root keys are the exact characterized roots required by its model-bearing loaders (`unet`, `vae`, `clip`, `clip_vision`); widening this set requires an explicit adapter-contract revision;
- `declared_name` is the exact template field value, not an arbitrary filesystem path; schema 1 requires it to be a non-empty relative loader name whose resolved path cannot escape the configured root (no absolute path, `.`/`..` traversal, or root escape);
- `sha256` identifies the actual model artifact bytes;
- duplicate content hashes are legal when the same bytes are intentionally referenced by distinct explicit bindings;
- template `(node, field)` and `declared_name` are cross-validated at package validation time;
- before executor submission, the Comfy adapter resolves the explicitly declared `storage_root_key + declared_name`, hashes those live bytes, and requires equality with the historical fingerprint;
- no directory search, newest-file choice, loader-class inference, or filename-only trust is allowed.

The fingerprint plus the existing deployment attestation closes **model-weight + characterized runtime-code identity** without placing model paths or model semantics into M8.

## 6.4 Live Comfy model-root adapter contract

The published M8 `Settings` has no filesystem route from `storage_root_key` to the model bytes loaded by Comfy. M9 schema 1 therefore freezes this worker-side configuration surface:

```text
storage_root_key  → Settings field
unet              → comfy_model_root_unet
vae               → comfy_model_root_vae
clip              → comfy_model_root_clip
clip_vision       → comfy_model_root_clip_vision
```

Each field is:

```text
Path | None
```

and is exposed through the existing `SOLORING_` settings prefix (for example `SOLORING_COMFY_MODEL_ROOT_UNET`). When configured for schema-2 execution, the value must be an **absolute filesystem root visible to the SoloRing worker and mapped to the corresponding loader search root of the characterized Comfy deployment**.

Rules:

1. `storage_root_key` is a logical adapter key; it is **not** an on-disk folder name and may never be converted to a path by string convention.
2. M9A must empirically pin the four root-key → characterized-deployment directory mappings used by the baseline package. In particular, loader behavior supplied by ComfyUI-GGUF must be verified rather than inferred from the node class or filename.
3. For one fingerprint entry, the adapter selects exactly the configured root for its key and resolves the exact captured `declared_name` beneath that root.
4. The resolved path must remain beneath the configured root after filesystem resolution. Path traversal/root escape is invalid and no directory search is attempted.
5. If a schema-2 Generation references a root key whose setting is unset, non-absolute, unreadable, missing, or cannot resolve the declared file safely, worker execution fails **before executor submission** as `EXECUTION_MODEL_INCOMPATIBLE`.
6. There is no fallback to `comfy_base_url`, current package paths, Comfy HTTP filename listings, guessed `models/<key>` directories, or filename-only trust.
7. Schema-1 M9 therefore requires worker-readable access to the same model store used by the characterized Comfy deployment. A remote Comfy installation without an explicitly shared/mounted model-root contract is not schema-1 compatible; a future remote content-attestation API would require a new frozen adapter/fingerprint contract.
8. These Settings paths are mutable deployment configuration and are **not captured historical identity**. Only the fingerprint's content hashes, loader bindings, declared names, and runtime requirements are historical authority for execution.

### 6.4.1 Hashing semantics

For **every schema-2 executor submission attempt**, the worker streams SHA-256 over every unique resolved model file required by the captured fingerprint and compares it with the captured hash before submission.

Schema 1 deliberately has **no persistent hash cache keyed by path, size, mtime, inode, or similar metadata**. Such a cache could miss a same-metadata content replacement and would weaken the exact-byte claim. Duplicate fingerprint bindings resolving to the same live file may share one hash computation **within that single submission attempt** only.

The worker may record bytes hashed and elapsed verification time as diagnostics. M9 freezes no wall-clock correctness threshold; the cost of hashing the large GGUF and companion artifacts on every submission attempt is an accepted schema-1 correctness cost.

---

# 7. RealizationProfile schema 1

The schema-1 profile contract is frozen conceptually by the following exact field set; implementation must encode it with strict recursive unknown-field rejection and golden byte fixtures before M9A exits.

```json
{
  "schema_version": 1,
  "profile_id": "hunyuan-i2v-single-reference",
  "profile_version": 1,
  "workflow_id": "hunyuan_i2v",
  "workflow_version": 4,
  "model": {
    "id": "hunyuan-video-i2v",
    "version": "..."
  },
  "channels": {
    "hero_reference": {
      "input_key": "reference_image",
      "min_items": 1,
      "max_items": 1,
      "allowed_roles": ["primary"]
    }
  },
  "rules": [
    {
      "target_kind": "entity",
      "facet_key": "identity",
      "channel": "hero_reference"
    }
  ],
  "parameter_overrides": {}
}
```

No additional field is legal in schema 1.

## 7.1 Profile identity

- `schema_version` is the document-structure version and is independent of `profile_version`.
- `profile_id` is a human/operational execution-profile lineage key, not a historical content identity.
- `profile_version` increments whenever profile semantics change within that lineage.
- raw `profile_hash` identifies exact captured bytes and is the historical identity used by a Generation.
- UI/history must not imply two versions are semantically equivalent merely because `profile_id` is the same.

## 7.2 Model identity

`model.id` and `model.version` are non-empty execution labels copied into the existing Generation columns for schema-2 Generations.

They must exactly match `ExecutionModelFingerprint.model_id/model_version`.

The content-addressed fingerprint, not these labels, proves exact model artifact identity.

## 7.3 Rule matching

Schema 1 matches exactly:

```text
target_kind
+
facet_key
```

`target_kind` is one of:

```text
entity
feature_value
```

`facet_key` is **exactly the captured M8 `VisualFacet.facet_key`**, using the frozen M8 grammar:

```text
^[a-z0-9][a-z0-9._-]{0,127}$
```

M9 introduces no second visual naming system.

No regex, wildcard, substring, inferred category, semantic similarity, or fallback selector exists in schema 1.

## 7.4 Rule uniqueness and shared channels

At most one rule may match one exact `(target_kind, facet_key)` selector. Duplicate selectors are `REALIZATION_PROFILE_INVALID`; no order-based winner exists.

Different selectors **may intentionally target the same channel**. This is a supported schema-1 shape. Their required/optional facet item sets then compete only under the frozen deterministic channel-capacity rules in §12; no hidden priority exists beyond required-first + canonical M8 order.

Every rule must reference an existing profile channel.

## 7.5 Channels and manifest bijection

A channel is a stable logical realization input understood by the profile and manifest; it is not a Comfy node.

Schema 1 requires a bijection:

```text
one profile channel
↔
exactly one manifest realization_channel input_key
```

Therefore:

- two profile channels may not share one `input_key`;
- one manifest realization input may not be claimed by two channels;
- every profile channel must have exactly one matching manifest `realization_channel` declaration;
- every manifest `realization_channel` declaration must have exactly one matching profile channel;
- there is no channel-level optional escape hatch in schema 1.

Optionality belongs to captured M8 facet requirements and allocation, not to undeclared execution channels.

## 7.6 Capacity

Each channel declares:

```text
0 <= min_items <= max_items
1 <= max_items
```

`max_items` is finite in schema 1.

A channel with `min_items > 0` must be targeted by at least one profile rule or the package is statically invalid.

Capacity is a capability statement, not a suggestion. Facet binding is atomic (§12–§13): capacity never silently truncates a required or optional facet's eligible item set.

## 7.7 Allowed reference roles

`allowed_roles`:

- is non-empty;
- contains only the frozen M8 role vocabulary;
- has no duplicates;
- is interpreted as a membership set, while actual item order always remains the captured M8 item order.

No model may silently reinterpret `context`, `detail`, or `supporting` as `primary`; use is legal only when explicitly listed.

---

# 8. Manifest schema 2 — explicit source classes

M9 must not overload legacy `source_role`. Manifest schema 2 uses one discriminated `source` object per logical input.

### Legacy ShotReference input

```json
{
  "source": {
    "kind": "shot_reference",
    "role": "reference"
  }
}
```

### M9 realization input

```json
{
  "source": {
    "kind": "realization_channel",
    "channel": "hero_reference"
  }
}
```

Rules:

- an input has exactly one source class;
- `shot_reference` requires a valid predecessor ShotReference role;
- `realization_channel` requires exactly one profile channel under the §7.5 bijection;
- one logical `input_key` cannot be supplied by both source classes;
- schema 2 rejects legacy `source_role` alongside `source`; **no dual form exists**;
- schema 1 continues to interpret legacy `source_role` byte-for-byte as today;
- re-authoring an existing legacy input into schema-2 `shot_reference` form must preserve the identical resolved GenerationInput set under a golden compatibility fixture;
- realization input `required/cardinality` constraints remain manifest execution constraints and are validated only after legacy and realization projections are merged (§19, §22).

This preserves legacy composition references while preventing authority blending.

---

# 9. Parameter override contract

RealizationProfile schema 1 may declare exact model-specific parameter overrides.

```json
{
  "parameter_overrides": {
    "identity_strength": 0.85
  }
}
```

The precedence is frozen:

```text
manifest defaults
        ↓
ordinary permitted Generation request overrides (if the predecessor API supports them)
        ↓
M9 RealizationProfile overrides — FINAL for keys it owns
        ↓
strict manifest type/range/enum validation
        ↓
captured resolved parameters
```

Rules:

1. every profile override key must exist in the captured manifest;
2. the final value must pass the existing strict manifest validator with no lossy coercion;
3. profile-owned keys are execution policy; a client cannot supersede them;
4. if a predecessor request supplies the same key, the profile value deterministically wins and the final captured value is authoritative for this Generation;
5. the RealizationSpec records the exact profile override map, and the outer workflow-spec `parameters` records final resolved values;
6. cross-validation requires every RealizationSpec override to equal the corresponding final captured parameter;
7. translation never reapplies profile defaults/overrides;
8. worker execution never consults the current profile to reconstruct parameters;
9. unknown profile parameter names are `REALIZATION_INPUT_BINDING_INVALID`, not ignored.

M9 parameter policy is execution-layer policy only; parameter names never enter M8 visual authority.

---

# 10. Canonical historical M8 authority input

M9 uses one server-owned value type:

```text
CapturedVisualAuthority
```

It has the same normalized semantic shape whether built from current coherent M8 state for preview or reconstructed from a historical ShotRevision for Generation capture/inspection.

For each applicable captured facet it contains:

```text
visual_facet_id
facet_key
requirement_at_capture
target kind + exact target identity
visual_anchor_id
visual_anchor_revision_id
visual_anchor_snapshot_hash
ordered captured items:
    asset_id
    blob_hash
    role
    view_key
    position
```

The cross-facet order is **exactly M8 VisualReferencePack order (§50 of the frozen M8 plan)**:

```text
entity anchors first by:
  entity_id, entity_revision_id, facet_key, visual_facet_id, visual_anchor_revision_id

then feature-value anchors by:
  feature_id, feature_value_hash,
  visual_context_entity_revision_id-or-empty,
  facet_key, visual_facet_id, visual_anchor_revision_id
```

M9 does not invent a second ordering.

## 10.1 Historical reconstruction

For ShotRevision schema 4:

1. reconstruct only captured normalized M8 provenance;
2. batch-load any historical rows required by the frozen M8 schema;
3. fail closed on missing/tampered provenance;
4. recompute the canonical captured VisualReferencePack value/hash;
5. require exact equality with the ShotRevision's captured `visual_reference_pack_hash`;
6. only then expose `CapturedVisualAuthority` to M9.

A mismatch is `INTERNAL_INVARIANT_VIOLATION`, never an M9 readiness issue.

Historical reconstruction performs provenance/DB validation. `compile_realization()` performs **no DB provenance validation beyond validating the already-constructed value's internal schema/invariants**.

## 10.2 Current preview adapter

Current preview uses the canonical M7/M8 coherent resolver and converts the resolved current VisualReferencePack into the **same capture-shaped `CapturedVisualAuthority` value**.

It must not create a preview-specific semantic structure.

Mandatory parity fixture:

```text
same logical M8 state
+ same requirement value
→ current-preview CapturedVisualAuthority
== historical ShotRevision CapturedVisualAuthority
→ byte-identical RealizationSpec under the same package
```

`requirement_at_capture` is intentionally historical allocation input even though the M8 `visual_reference_pack_hash` does not itself cover current requirement policy. The parity fixture therefore pins the requirement value constant. If current requirement policy later changes, preview may legitimately differ from the historical authority value; historical reconstruction must **never** read the current requirement in an attempt to force parity.

## 10.3 Pre-M8 ShotRevisions

ShotRevision schemas 1–3 have no captured M8 authority.

- New Generate from current state may capture/reuse the appropriate current revision first.
- Exact Rerun of an existing schema-1/2/3 historical Generation never gains M9 retroactively.

---

# 11. Realization readiness

M9 readiness is model/workflow-package-specific and remains distinct from M8 `visual_continuity_ready`.

Conceptual current result:

```text
realization_ready
package_release_identity
realization_profile
realization_issues
realization_preview
```

A given Shot may be realizable by one package/profile and not another. **Schema 1 does not expose a multi-model matrix**: the endpoint evaluates exactly the one currently configured/selected package. The multi-model distinction is conceptual, not permission to build a registry/marketplace.

## 11.1 Precedence

New Generate has two different classes of package failure and freezes their precedence explicitly.

### Stage 0 — coherent package capture integrity

Before DB work, the server must be able to capture one coherent release byte set. Missing descriptor/artifact bytes, declared-hash mismatch, or descriptor change during capture fails immediately because no candidate package snapshot exists.

This is capture integrity, not Shot readiness.

### Then predecessor-first semantic ordering

After one coherent byte snapshot exists:

```text
M7 ready?
├─ no → existing M7 blocker
└─ yes
    ↓
M8 ready?
├─ no → existing M8 blocker
└─ yes
    ↓
package/profile/fingerprint structurally valid and mutually bound?
├─ no → exact package/profile/fingerprint validation error
└─ yes
    ↓
M9 realization ready for this CapturedVisualAuthority?
├─ no → exact M9 readiness blocker
└─ yes
    ↓
legacy + realization input assembly/cardinality valid?
├─ no → existing exact workflow input error
└─ yes
    ↓
create Generation
```

Thus a **malformed profile + M7-invalid Shot** returns the M7 blocker, provided the package bytes themselves were coherently capturable. Raw capture-integrity corruption may preempt because no coherent package snapshot can be established.

Corruption discovered in historical M8 provenance at any point fails immediately as invariant corruption.

## 11.2 Empty M8 authority

If the captured effective M8 authority is empty:

```text
M9 realization content = absent
```

A schema-1 or valid schema-2 package may proceed through the legacy path, subject to that package's ordinary manifest cardinality.

No empty RealizationSpec is fabricated.

## 11.3 Non-empty M8 authority

Non-empty captured M8 authority may never be silently ignored.

A schema-1 package is insufficient and returns `REALIZATION_PROFILE_REQUIRED`.

For every **required** captured facet under a schema-2 package:

```text
exact rule exists
AND
allowed item set is non-empty
AND
its entire atomic eligible item set can be allocated
AND
channel minimum/maximum constraints can be satisfied
AND
manifest/profile bindings are valid
```

or Generation creation fails before queueing.

---

# 12. Deterministic facet-atomic allocation

The compiler allocates whole M8 facets, never arbitrary prefixes of a facet's eligible reference set.

Closed optional omission reasons for schema 1:

```text
no_matching_rule
no_allowed_items
capacity_exceeded
channel_minimum_unmet
```

No other omission string is legal.

## 12.1 Required facets first

Process required facets in exact canonical M8 cross-facet order.

For each required facet:

1. find the exact profile rule; missing → `REALIZATION_REQUIRED_FACET_UNSUPPORTED`;
2. filter the facet's captured items by the target channel's `allowed_roles`, retaining captured item order;
3. empty filtered set → `REALIZATION_REQUIRED_FACET_UNSUPPORTED`;
4. the resulting filtered item set is **atomic**;
5. tentatively add the entire set to that channel;
6. if total channel items would exceed `max_items` → `REALIZATION_CAPACITY_EXCEEDED`.

Required authority is never truncated and is never displaced by optional authority.

## 12.2 Optional facets second

Every applicable optional captured facet is audited, including facets with no profile rule.

Process in exact canonical M8 order:

1. no exact rule → omit whole facet as `no_matching_rule`;
2. rule exists but role filtering yields no items → omit whole facet as `no_allowed_items`;
3. whole candidate set would exceed channel `max_items` → omit whole facet as `capacity_exceeded`;
4. otherwise tentatively include the entire facet item set.

There is no partial optional-facet realization in schema 1.

## 12.3 Channel minimum

After required and optional tentative allocation:

- an inactive channel with zero bindings is legal regardless of `min_items`;
- if a channel has any required facet and final binding count is below `min_items`, block with `REALIZATION_CHANNEL_MINIMUM_UNMET`;
- if a channel contains only optional facets and final count is below `min_items`, omit **all** optional facets allocated to that channel with reason `channel_minimum_unmet` and leave the channel inactive;
- no other channel may donate/reorder facets to satisfy the minimum;
- allocation is not rerun with heuristics after an omission.

This makes `min_items` an honest model/input capability constraint without forcing unrelated channels to appear on every Shot.

## 12.4 Why optional omission is legal

M8 `optional` means the production does not require that facet to block capture/execution. M9 may therefore omit it under a frozen capability rule, but only with explicit historical audit.

M9 may never apply this permission to required facets.

---

# 13. Item selection

For one matched facet, item selection is exactly:

```text
captured M8 item order
→ filter items whose role ∈ channel.allowed_roles
→ retain every surviving item
```

The filtered set is the facet's atomic candidate set.

Schema 1 has **no**:

- per-facet top-N truncation;
- visual scoring;
- filename ordering;
- similarity ranking;
- recency preference;
- random sampling;
- “primary wins” behavior unless `allowed_roles` itself restricts the set to `primary`.

If package authors want only the primary reference, they must express:

```json
"allowed_roles": ["primary"]
```

Capacity is then evaluated over the complete resulting atomic candidate sets under §12.

---

# 14. Canonical RealizationSpec schema 1

A non-empty M9 realization is embedded in workflow-spec schema 2 using this frozen semantic field set:

```json
{
  "schema_version": 1,
  "profile": {
    "id": "...",
    "version": 1,
    "hash": "..."
  },
  "model": {
    "id": "...",
    "version": "...",
    "execution_model_fingerprint_hash": "..."
  },
  "visual_reference_pack_hash": "...",
  "parameter_overrides": {
    "identity_strength": 0.85
  },
  "channels": [
    {
      "channel": "hero_reference",
      "input_key": "reference_image",
      "bindings": [
        {
          "visual_facet_id": "...",
          "facet_key": "identity",
          "required": true,
          "visual_anchor_id": "...",
          "visual_anchor_revision_id": "...",
          "visual_anchor_snapshot_hash": "...",
          "target": {
            "kind": "entity",
            "entity_id": "...",
            "entity_revision_id": "..."
          },
          "item": {
            "asset_id": "...",
            "blob_hash": "...",
            "role": "primary",
            "view_key": "front",
            "source_position": 0
          },
          "binding_position": 0
        }
      ]
    }
  ],
  "omitted_optional": [
    {
      "visual_facet_id": "...",
      "target_kind": "entity",
      "facet_key": "wardrobe",
      "reason": "capacity_exceeded"
    }
  ]
}
```

`RealizationSpec.schema_version` evolves independently from the outer workflow-spec schema version.

## 14.1 Included identity

The spec records enough to prove:

- which captured visual authority was being realized;
- exact immutable VisualAnchorRevision provenance;
- exact Asset/Blob bytes selected;
- model/profile/fingerprint identity;
- logical channel/input mapping;
- exact M8 required/optional state affecting allocation;
- exact profile-owned parameter overrides;
- every omitted optional facet and its closed reason.

`visual_reference_pack_hash` must equal the already-verified historical M8 pack hash from §10.

## 14.2 Excluded state

Do not include current M8 pointers, current FeatureTransitions, mutable filesystem paths, current installed package path, prompt IDs, worker IDs, attempt IDs, timestamps as semantic identity, or live capability probes.

Attempt-specific runtime evidence belongs to executor/attempt provenance. The captured `ExecutionModelFingerprint` expresses the Generation's required model/runtime identity; the live attempt proves whether the current worker satisfied it.

---

# 15. RealizationSpec canonical ordering

Ordering is exact and reuses M8 ordering rather than inventing M9 priority.

### Channel order

```text
channel key lexicographically
```

### Binding order inside one channel

```text
required facets first
then optional facets
within each group: exact M8 VisualReferencePack anchor order
within each facet: captured M8 item position
```

`binding_position` is zero-based contiguous **per input_key/channel**. The §7.5 bijection ensures there is no cross-channel position merge.

### Omitted optional order

Exact M8 VisualReferencePack anchor order.

### Parameter override order

Canonical JSON object-key ordering from SoloRing's existing serializer; the compiler does not preserve profile authoring order as semantics.

No database row order, timestamp, UUID discovery order, or profile rule list order resolves conflicts.

---

# 16. Workflow-spec schema 2

Workflow-spec schema 1 remains byte-stable.

## 16.1 No-empty-higher-schema rule

```text
no effective M9 realization content
→ exact workflow-spec schema 1
```

```text
non-empty M9 realization content
→ workflow-spec schema 2
```

Forbidden:

```json
{"schema_version":2,"realization":null}
```

or an empty realization object/channels list when schema 1 expresses identical execution semantics.

## 16.2 Schema-2 additions

Schema 2 preserves all schema-1 fields and adds:

```text
model
realization
```

`model` mirrors the RealizationSpec model identity, including `execution_model_fingerprint_hash` where present. Existing output contract remains unchanged.

The entire logical workflow spec is canonicalized by SoloRing's existing canonical serializer and identified by `workflow_spec_hash`.

Schema 1 defines **no persisted or API-level nested realization hash**. `workflow_spec_hash` is the sole persisted identity covering the nested RealizationSpec. Inspection code may display ordinary fields from the nested value but must not create a second historical identity contract for it.

## 16.3 Package/spec compatibility lattice

| Package | Manifest | Profile/fingerprint | Effective M8 authority | Workflow spec | Result |
|---|---|---|---|---|---|
| v1 | v1 | absent | empty | exact v1 | legal legacy |
| v1 | v1 | absent | non-empty | none | `REALIZATION_PROFILE_REQUIRED` |
| v2 | v2 | present/valid | empty | exact v1 | legal if ordinary manifest cardinality is satisfied |
| v2 | v2 | present/valid | non-empty | v2 | legal if M9 + combined input gates pass |
| v2 | v2 | missing/invalid | any | none | invalid package after predecessor gates |

A workflow-spec v1 may therefore execute using a captured manifest v2 when no M9 realization was captured. The schema-2 manifest's `shot_reference` form must preserve legacy input semantics, and realization-channel inputs simply have no realization-backed bindings in this case; ordinary manifest cardinality decides whether that package can execute the Shot.

When a v2 package yields a v1 workflow spec, profile/fingerprint bytes may have been content-addressed during package capture, but they are **not Generation dependencies** because no M9 realization was used. Historical execution depends only on the artifacts/identities referenced by the persisted v1 Generation.

---

# 17. Generation row model fields

When workflow-spec schema 2 is produced:

```text
Generation.model = realization.profile.model.id
Generation.model_version = realization.profile.model.version
```

When schema 1 is produced:

```text
preserve predecessor behavior
```

For M9-created legacy/no-realization generations, model fields may remain NULL unless the workflow already has an independent explicit model identity contract.

The Generation columns are inspection/index fields; workflow-spec bytes remain the complete historical execution authority.

Mismatch between non-null Generation model fields and schema-2 spec model identity is `INTERNAL_INVARIANT_VIOLATION` on historical load/execution.

---

# 18. GenerationInput projection

Every selected RealizationSpec binding creates exactly one immutable GenerationInput row:

```text
input_key      = channel's unique manifest input key
position       = binding_position
asset_id       = captured M8 Asset identity
blob_hash      = captured M8 Blob identity
reference_role = captured M8 item role
```

The published baseline already has all five fields; no migration is required.

The same Asset may legally appear in multiple input keys if explicitly selected through distinct channels. Because profile channel ↔ manifest input is bijective, one input key has one position namespace.

## 18.1 Realization-local cross-validation

`compile_realization()` validates in memory:

```text
RealizationSpec binding projection
==
its emitted realization GenerationInput projection
```

exactly, including role/Asset/Blob/position.

## 18.2 Persisted historical cross-validation

Before Generation commit and again before worker execution, the Generation assembly/worker validates the persisted realization-backed GenerationInputs against the captured RealizationSpec.

Any missing, extra, mismatched, duplicate, or non-contiguous realization row is `INTERNAL_INVARIANT_VIOLATION`.

Do not regenerate missing GenerationInputs from RealizationSpec during historical execution.

---

# 19. Legacy ShotReference inputs coexist without blending

Manifest schema 2 may contain both source classes on **different** logical input keys:

```text
composition_reference  ← shot_reference
identity_reference     ← realization_channel
```

The assembly pipeline is frozen:

```text
compile_realization(...)
        ↓
realization input projection only

resolve_legacy_inputs(...)
        ↓
legacy ShotReference input projection only

merge_generation_inputs(...)
        ↓
require source classes remain disjoint by input_key

validate_combined_manifest_cardinality(...)
```

Combined cardinality is **not** a responsibility of the pure realization compiler because the compiler does not receive legacy inputs.

Forbidden:

```text
one input_key ← both source classes
```

No precedence or blending rule exists.

---

# 20. The ONE realization compiler

Canonical API:

```python
compile_realization(
    *,
    captured_visual_authority,
    profile,
    manifest,
) -> RealizationResult
```

Pure inputs only.

No DB.  
No filesystem.  
No network.  
No current Shot.  
No current M8 resolver.  
No Settings lookup.  
No Comfy API.  
No legacy ShotReference resolution.

Output contains:

```text
ready
blocking issues
canonical RealizationSpec or NULL
realization-only GenerationInput projection
resolved profile parameter overrides
informational omitted_optional records
```

The same compiler drives:

- current readiness preview after current state is converted to `CapturedVisualAuthority`;
- new Generation compilation after ShotRevision reconstruction;
- server-side realization inspection fixtures.

Generation assembly, not the compiler, resolves legacy inputs and validates combined manifest cardinality.

Worker execution and Exact Rerun **never call this compiler**.

---

# 21. Realization compiler validation order

Given already-constructed `CapturedVisualAuthority`, a validated profile document, and a validated manifest value, the pure compiler performs exactly:

1. validate internal `CapturedVisualAuthority` value invariants;
2. validate profile identity fields against the supplied validated profile value;
3. validate the profile↔manifest channel bijection/value contract supplied to the compiler;
4. build exact `(target_kind, facet_key)` rule index;
5. enumerate every captured required facet in exact M8 order;
6. reject missing required rule;
7. filter required facet items by allowed roles;
8. reject empty required candidate set;
9. allocate complete required facet candidate sets; reject max-capacity overflow;
10. enumerate every optional facet in exact M8 order, including no-rule cases;
11. apply the closed whole-facet omission rules;
12. enforce channel `min_items` semantics from §12.3;
13. resolve/validate profile parameter overrides against the supplied manifest parameter definitions;
14. build canonical RealizationSpec;
15. project realization-only GenerationInputs;
16. cross-validate spec ↔ realization input projection;
17. return ready output.

The compiler does **not**:

- read DB provenance;
- recompute current M8 state;
- resolve legacy inputs;
- validate combined legacy+realization cardinality;
- inspect model files;
- translate Comfy graph fields.

If a blocker occurs, no partial spec/hash is fabricated.

---

# 22. New Generation creation pipeline

For a Comfy package:

```text
CAPTURE RELEASE BYTES
read descriptor + declared artifacts coherently
verify raw declared hashes / descriptor stability
place exact captured artifacts content-addressed
NO DB TRANSACTION OPEN DURING FILE CAPTURE
        ↓
CAPTURE PREDECESSOR STATE
load Shot
capture/reuse ShotRevision under existing M7+M8 gates
M7/M8 blocker? → return predecessor blocker
        ↓
VALIDATE CAPTURED PACKAGE SEMANTICS
parse/strict-validate manifest
if schema 2: parse/strict-validate profile + ExecutionModelFingerprint
cross-validate package/manifest/profile/fingerprint/template bindings
        ↓
BUILD HISTORICAL AUTHORITY VALUE
reconstruct ShotRevision M8 provenance
recompute/cross-check visual_reference_pack_hash
        ↓
COMPILE M9
schema 1 + non-empty authority → REALIZATION_PROFILE_REQUIRED
schema 2 → compile_realization(...)
M9 blocker? → reject; no Generation row
        ↓
ASSEMBLE ALL INPUTS
resolve legacy ShotReference inputs from captured ShotRevision
merge with realization projection by disjoint input keys
validate combined manifest cardinality
        ↓
RESOLVE EXECUTION TEXT/PARAMETERS
prompt from captured ShotRevision intent
ordinary parameters
apply final profile overrides
cross-check against compiler result
        ↓
BUILD WORKFLOW SPEC
no M9 content → exact schema 1
non-empty M9 → schema 2
canonicalize/hash
        ↓
BEGIN EXISTING GENERATION WRITE TRANSACTION
create immutable Generation + GenerationInputs
```

No executor network call occurs during Generation creation.

The exact package/model fingerprint expresses required execution identity; live model-byte/runtime verification occurs before executor submission (§26–§27), not by consulting current package selection during creation.

---

# 23. Package capture coherence and activation

M9 extends the existing M5 descriptor-last commit-marker discipline from two artifacts to four.

Capture must:

```text
read descriptor D1
read manifest bytes once
read template bytes once
read profile bytes once              # schema 2
read model-fingerprint bytes once    # schema 2
hash each exact buffer
require every hash == D1 declaration
read descriptor D2
require D2 identifies exactly the same release as D1
```

Hashing and parsing always use the same captured byte buffers; never re-read an artifact to compute its identity.

A concurrent release switch yields only:

```text
complete BEFORE
or
complete AFTER
or
fail as incoherent
```

never a hybrid.

Failure to establish this current in-memory package snapshot because the descriptor/artifact is missing or unreadable, any D1-declared raw hash does not match the captured manifest/template/profile/fingerprint bytes, or D2 no longer identifies D1's release is exactly `WORKFLOW_PACKAGE_INTEGRITY` (503). No M7/M8 readiness decision is attempted against a package snapshot that never coherently existed.

Historical content-addressed artifact corruption remains historical corruption: existing manifest/template integrity codes continue to apply to their artifact classes, while missing/tampered historical profile/fingerprint bytes fail closed as `INTERNAL_INVARIANT_VIOLATION`; current package capture is never used to repair history.

## 23.1 Installation/activation validation

Where the SoloRing-controlled installer/activation seam exists, schema-2 release activation must run the same structural package validator before the descriptor is made current. A rejected candidate release leaves the previous descriptor current.

Runtime/new-Generation validation remains mandatory defense-in-depth; install-time validation does not weaken capture-time checks.

Do not prescribe a new deployment mechanism if the existing descriptor-last atomic activation can be extended safely. The source gate proves the actual implementation rather than relying on directory layout assumptions.

---

# 24. Workflow/profile/fingerprint binding validation

After predecessor M7/M8 gates and before M9 Shot-specific compilation, validate the captured package semantically.

Schema-2 validation must prove:

### Profile structure

- strict recursive schema 1;
- unique channel keys;
- unique exact selectors;
- every rule references an existing channel;
- `allowed_roles` non-empty/valid;
- `1 <= max_items`, `0 <= min_items <= max_items`;
- every `min_items > 0` channel is reachable from at least one rule;
- model/profile/workflow fields normalized.

### Profile ↔ manifest

- exact channel/input bijection from §7.5;
- no two channels share one input key;
- no manifest realization input is undeclared;
- no channel-level optional exception;
- profile parameter overrides name real manifest parameters;
- schema-2 `shot_reference` declarations are valid predecessor roles;
- source classes do not blend on one input key.

### Manifest/template

- every declared input/parameter/output node/field binding exists under the existing exact validator;
- no graph heuristic repairs a missing target.

### ExecutionModelFingerprint

- strict schema 1;
- model id/version == profile model id/version;
- runtime requirements use frozen exact commit/policy forms;
- every artifact entry has unique key and unique `(node,field)`;
- every `(node,field)` exists in captured template;
- exact template field value == `declared_name`;
- `storage_root_key` belongs to the frozen adapter vocabulary;
- `declared_name` satisfies the schema-1 safe-relative-loader-name contract from §6.3/§6.4;
- hashes are valid lowercase SHA-256;
- package structural validity does **not** require the current worker's model-root Settings to be configured; those are live executor-compatibility facts checked under §26, not Shot/package semantic validity.

### Package cross-identity

```text
package workflow id/version
== manifest workflow id/version
== profile workflow id/version
```

and descriptor raw hashes exactly match the four captured artifacts.

Package validity is not M9 readiness. A valid package can still be unable to realize a particular required Shot facet.

---

# 25. Model capability semantics

M9 distinguishes two capability domains.

## 25.1 Model realization capability

Defined by the captured RealizationProfile:

```text
which M8 facet selectors can this package realize?
through which channels?
with what item roles/capacity?
with what exact model identity?
```

## 25.2 Executor transport/runtime capability

Defined by existing Comfy capability/attestation infrastructure:

```text
can this Comfy deployment upload, submit, observe, fetch, cancel safely?
```

They are orthogonal.

A transport capability report must never be used to infer model visual capability.

A RealizationProfile must never be used to infer cancellation safety or transport availability.

---

# 26. Runtime environment verification

M9 separates three identity layers:

```text
A. captured logical execution request
   workflow spec + GenerationInputs

B. captured required model/runtime identity
   ExecutionModelFingerprint

C. live executor state
   deployment attestation + actual model artifact bytes
```

Before submission of a schema-2 historical Generation, worker validation must prove:

1. historical manifest/template/profile/model-fingerprint artifacts exist and match their captured hashes;
2. live deployment attestation satisfies the fingerprint's frozen stable runtime requirements (ComfyUI commit, required custom-node commit(s), exact custom-node policy);
3. every historical fingerprint artifact binding still matches the captured template node/field/name;
4. every fingerprint `storage_root_key` resolves through the exact Settings mapping in §6.4, and every explicitly resolved live model file hashes to the captured expected SHA-256;
5. every referenced model file is re-hashed on this submission attempt under §6.4.1; no path/stat metadata cache may substitute for content hashing;
6. materialized GenerationInput Blob bytes pass existing historical integrity validation;
7. only then may translation/submission occur.

The live process PID/start fingerprint remains deployment liveness evidence; it is not historical Generation identity.

GPU, driver, torch, nondeterministic kernels, and executor scheduling are **not** claimed pinned by ExecutionModelFingerprint schema 1 unless explicitly added by a later contract. That is why M9 still promises logical + model-byte reproducibility, not byte-identical media.

---

# 27. Model-weight identity — resolved architecture decision

The M8-baseline audit answers the original decision gate:

```text
Does captured workflow/package + deployment attestation uniquely identify model weights?
→ NO
```

Evidence from the frozen published tree:

- workflow template fields select `*.gguf` / `*.safetensors` by filename;
- package descriptor hashes manifest/template bytes, not model files;
- deployment attestation v4 pins ComfyUI commit, ComfyUI-GGUF commit, serving process identity, and custom-node whitelist;
- deployment attestation v4 has no model-artifact content hashes.

Therefore M9 schema 2 **must** implement `ExecutionModelFingerprint` as frozen in §6.3.

This is not optional M9A research anymore; it is a required implementation contract.

M9A must mechanically inventory every model-bearing loader field in the baseline Hunyuan workflow and populate the fingerprint with exact content hashes. The initial baseline includes **five** explicit model-bearing template fields, so fingerprinting only the main UNet is insufficient:

```text
node 10 / vae_name   → hunyuan_video_vae_bf16.safetensors
node 97 / clip_name  → llava_llama3_vision.safetensors
node 98 / unet_name  → hunyuan-video-i2v-720p-Q4_K_M.gguf
node 99 / clip_name1 → clip_l.safetensors
node 99 / clip_name2 → llava_llama3_fp8_scaled.safetensors
```

The frozen M8 deployment pin also records ComfyUI `b963f4ad210a42841ab23dfc28a84143a0cce227` and ComfyUI-GGUF `6ea2651e7df66d7585f6ffee804b20e92fb38b8a`; schema-1 fingerprint runtime requirements must use those characterized revisions for the baseline package unless a separately frozen package/runtime revision is introduced.

Worker execution must fail closed with `EXECUTION_MODEL_INCOMPATIBLE` if any required live model/runtime identity differs. Live filesystem paths are worker-local resolution details selected only through the frozen `storage_root_key` → Settings adapter in §6.4.

The published baseline provides no such model-root Settings today, so adding those four worker configuration fields is an explicit M9 implementation obligation. It is not a database migration and it does not turn local paths into historical provenance.

Schema 1 deliberately accepts the cost of content-hashing the complete required model set before every submission attempt. M9A/M9D evidence records the observed cost, but correctness may not be weakened by an mtime/size/stat cache.

Never substitute:

- mutable filename;
- mtime/size;
- “same model version” label;
- current package profile;
- current deployment process alone.

APR-026 wording at M9 close must state exactly what is pinned and what remains non-deterministic.

---

# 28. Comfy translation

`build_comfy_prompt` remains a pure executor adapter.

For schema 2 it consumes:

```text
captured workflow spec schema 2
+ captured manifest schema 2
+ captured template
+ materialized GenerationInputs
+ generation/attempt marker
```

and mutates only fields explicitly declared by the manifest.

It does **not** receive the current RealizationProfile as semantic input.

The profile has already been compiled away into:

```text
captured input bindings
+ captured parameters
+ captured RealizationSpec provenance
```

The worker may load the captured profile for integrity/audit verification, but translation semantics do not need to rerun the M9 compiler.

This is crucial for Exact Rerun and historical isolation.

---

# 29. No graph heuristics

M9 must not add translation behavior such as:

- "find the first IP-Adapter node";
- "find a node whose title contains face";
- "use the newest LoRA loader";
- "set every weight-like widget to profile strength";
- "infer reference channel from filename";
- "bind primary to whichever image node appears first".

Every mutation is an explicit captured manifest binding.

Missing target → fail.

External node vocabulary stays behind manifest/translator boundaries.

---

# 30. Exact Rerun

Exact Rerun semantics remain total and simple:

```text
copy source Generation durable specification verbatim
copy source GenerationInputs verbatim
fresh execution-attempt lifecycle
```

For schema-2 source:

```text
workflow_spec_json/hash copied verbatim
model/model_version copied verbatim
GenerationInputs copied verbatim
```

Never call:

- current M8 resolver;
- M9 realization compiler;
- current installed realization profile;
- current workflow package selector;
- current model selection logic.

## 30.1 Mandatory source gate

With a historical schema-2 Generation:

1. mutate current M8 approvals/policies;
2. replace current realization-profile file;
3. monkeypatch `compile_realization` to raise;
4. monkeypatch current M8 resolver to raise;
5. create Exact Rerun;
6. assert new Generation's durable spec/model fields/inputs exactly equal the source;
7. use an SQL query spy to prove rerun creation reads no current M8 tables and no package/profile files.

Historical worker execution may read only captured artifact-store bytes identified by the source Generation—not mutable installed package files.

---

# 31. Generation creation versus Exact Rerun

This distinction is binding:

### New Generate

```text
current state
→ new ShotRevision capture/reuse
→ captured M8 authority
→ current selected captured workflow/profile package
→ NEW M9 compile
```

### Exact Rerun

```text
historical Generation
→ copy exact historical M9 result
```

A rerun is never "rerun today's best realization profile against the old ShotRevision."

That would be a new Generation request, not Exact Rerun.

---

# 32. Historical corruption semantics

For schema-2 Generation load/execution, fail closed if any historical facts disagree:

- stored workflow-spec bytes vs `workflow_spec_hash`;
- nested profile hash vs historical profile artifact bytes;
- nested ExecutionModelFingerprint hash vs historical fingerprint artifact bytes;
- profile model id/version vs fingerprint model id/version;
- nested model identity vs Generation `model/model_version` columns;
- RealizationSpec selected Asset/Blob/role/position vs GenerationInputs;
- GenerationInput Blob identity vs registered historical Blob;
- physical historical Blob bytes vs captured hash during materialization;
- historical manifest channel definition vs captured workflow-spec input keys;
- historical package/profile/fingerprint workflow identity contradictions;
- captured visual-reference-pack hash vs reconstructed historical M8 authority.

Historical corruption maps to `INTERNAL_INVARIANT_VIOLATION` unless an already-frozen lower-layer integrity code is semantically exact for the damaged artifact.

Live model/runtime mismatch is **not historical corruption**: if the captured fingerprint is valid but the current environment cannot satisfy it, use `EXECUTION_MODEL_INCOMPATIBLE`.

Never repair a Generation, recompile from current M8, substitute the current profile/fingerprint, replace model bytes, or silently drop a broken binding.

---

# 33. Output acceptance boundary

M9 must not overclaim what conditioning proves.

Successful request conformance proves:

```text
the exact captured M8 references and M9 parameters were bound into the intended model workflow
```

It does **not** prove:

```text
the generated pixels actually preserve Eva's face/cut/location perfectly
```

The model may ignore or imperfectly follow conditioning.

Therefore:

- existing technical media validation remains mandatory;
- Take approval remains the creative/canon decision;
- a generated output never changes M8 authority automatically;
- M9 UI may display "conditioning applied" but must not label the output "continuity verified" unless a later explicit QC subsystem proves that property.

Automated visual-similarity/identity scoring is out of M9's binding scope unless separately specified and source-gated.

---

# 34. New-generation realization-readiness endpoint

Add a server-owned current inspection endpoint, e.g.:

```text
GET /shots/{shot_id}/realization-readiness
```

Schema 1 evaluates **exactly one currently configured/selected workflow package**.

Response must include enough package identity to make staleness inspectable:

```json
{
  "ready": true,
  "package": {
    "schema_version": 2,
    "workflow_id": "...",
    "workflow_version": 4,
    "manifest_hash": "...",
    "workflow_template_hash": "...",
    "realization_profile_hash": "...",
    "execution_model_fingerprint_hash": "..."
  },
  "model": {"id": "...", "version": "..."},
  "profile": {"id": "...", "version": 1, "hash": "..."},
  "visual_reference_pack_hash": "...",
  "issues": [],
  "channels": [
    {
      "channel": "hero_reference",
      "input_key": "reference_image",
      "min_items": 0,
      "max_items": 1,
      "used_items": 1,
      "active": true
    }
  ],
  "facet_statuses": [
    {
      "visual_facet_id": "...",
      "target_kind": "entity",
      "facet_key": "identity",
      "requirement": "required",
      "status": "selected",
      "channel": "hero_reference",
      "input_key": "reference_image",
      "selected_items": [
        {
          "asset_id": "...",
          "blob_hash": "...",
          "role": "primary",
          "view_key": "front",
          "source_position": 0,
          "binding_position": 0
        }
      ],
      "reason": null,
      "issue_code": null
    }
  ],
  "omitted_optional": []
}
```

`facet_statuses` is the server-owned per-facet inspection contract used by M9E. Its exact schema-1 rules are:

- one row for every applicable `CapturedVisualAuthority` facet, in exact canonical M8 cross-facet order;
- `requirement` is exactly `required` or `optional` from `requirement_at_capture`/current preview state;
- `status` is the closed enum `selected`, `required_blocked`, or `optional_omitted`;
- `channel` / `input_key` are the exact matched execution binding when one exists, otherwise `null`;
- `selected_items` is the exact server-selected item projection in captured item order and is empty for non-selected facets;
- `reason` is `null` for selected facets, otherwise one of `no_matching_rule`, `no_allowed_items`, `capacity_exceeded`, `channel_minimum_unmet`;
- `issue_code` is `null` for selected/optional-omitted rows and is the exact blocking M9 code for `required_blocked` rows (`REALIZATION_REQUIRED_FACET_UNSUPPORTED`, `REALIZATION_CAPACITY_EXCEEDED`, or `REALIZATION_CHANNEL_MINIMUM_UNMET`);
- `omitted_optional` remains the canonical RealizationSpec-style omission projection and must agree exactly with the subset of `facet_statuses` whose status is `optional_omitted`.

`channels` is also server-owned: one row per profile channel in lexicographic channel order, with exact input key, declared min/max, final `used_items`, and whether the channel is active after allocation. The frontend does not recompute capacity or facet mapping.

Server flow:

```text
coherently capture one current package release in memory
resolve M7/M8 current state coherently
convert current visual pack → canonical CapturedVisualAuthority
validate captured package semantics
run ONE compile_realization()
return result + exact package identity
```

No current-state DB/file read occurs inside the compiler itself.

## 34.1 Inspection is preview, not reservation

The response is explicitly current inspection and may become stale immediately after return.

UI must label it as current/evaluated-against-package, not “locked” or “reserved.”

New Generate repeats package capture + ShotRevision capture and compiles from those newly captured facts.

Mandatory parity proof: when current state and a historical ShotRevision represent the same M8 authority **including the same requirement value** and package bytes are unchanged, preview and capture produce byte-identical RealizationSpec. A later current requirement-policy change may honestly change preview while the historical capture remains unchanged.

---

# 35. Generation API additions

Generation read responses should expose captured M9 information additively when present:

```text
model
model_version
workflow_spec_schema_version
realization_profile_id
realization_profile_version
realization_profile_hash
visual_reference_pack_hash
realization_summary
```

These may be projected from `workflow_spec_json`; do not add denormalized DB columns solely for UI convenience.

Historical API output must come from the captured Generation, not current profile/M8 state.

---

# 36. M9 UI

M9 adds execution-inspection UI, not a new creative-authority editor.

## 36.1 Shot realization panel

Show server-derived current inspection:

```text
M8 visual continuity ready / not ready
M9 realization ready / not ready
Executor availability / current environment compatibility — separately labeled
Evaluated package release hashes
Selected workflow/model
Profile id/version/hash
ExecutionModelFingerprint hash
Required facets:
    current captured-authority state
    mapped channel
    selected references
Optional facets:
    included / omitted + exact closed reason
Channel capacity usage
Profile-owned parameter overrides + final resolved values
```

The panel must state that current readiness is **not reserved** and identify the exact package hashes used for evaluation.

## 36.2 Honest blockers

Examples:

```text
Face — required — no exact profile rule
Cut realization — required — whole facet exceeds channel capacity
Wardrobe — optional — omitted: capacity_exceeded
Hair — optional — omitted: no_allowed_items
```

Do not report an M8 continuity failure when M8 is ready and only the selected model/profile is incapable.

Do not report runtime model-file drift as M9 semantic un-readiness; show it as execution-environment incompatibility.

## 36.3 Historical Generation inspector

Show historical facts distinctly:

```text
Captured package workflow/manifest/template hashes
Captured profile id/version/hash
Captured model id/version
Captured ExecutionModelFingerprint hash
Captured M8 pack hash
Per-channel selected references with Asset + Blob identity
Captured profile parameter overrides and final parameters
Captured optional omissions
Current profile/model/package status — informational only
```

Historical captured values remain authoritative for that Generation.

## 36.4 No M8 mutation controls

M9 panels may link to M8 visual-identity editors for production-authority changes, but M9 UI exposes no direct M8 create/update/approve/unapprove/promotion controls.

---

# 37. Baseline model-realization capability

M9 must close with at least one **real executor-backed** model-realization path, not only abstract schema.

The published baseline currently has a Hunyuan I2V workflow with a single `reference_image` input.

M9 should characterize that workflow honestly as a limited baseline capability, for example:

```text
one realization channel
finite cardinality = 1
explicit exact facet selectors supported by the profile
allowed role = primary
```

The exact selector set is **package content**, not new schema semantics. M9A must pin the baseline profile's selector fixture only after empirical characterization of the workflow's demonstrated capability; changing that selector set later is a new profile version/hash, not an M9 architecture change.

Do **not** claim the baseline workflow can simultaneously enforce arbitrary `face + wardrobe + cut + lobby` facets if it has only one logical reference-image input.

Required state outside the proven capability must block or require a different workflow/profile.

---

# 38. Future model mechanisms without schema redesign

The profile/channel architecture must be able to express future realization packages such as:

- multiple reference-image channels;
- identity-specific conditioning;
- detail/wound-specific conditioning;
- adapter strengths;
- LoRA-like execution configuration;
- model-specific embeddings;
- future control images generated from authoritative state;

without promoting any of those mechanisms into M8 authority.

M9 schema 1 does not need to implement all of them.

The stable abstraction is:

```text
captured M8 authority
→ exact profile selector
→ logical channel(s)
→ captured parameters + selected bytes
→ explicit workflow binding
```

---

# 39. Derived conditioning artifacts

Some future realization mechanisms may derive bytes from M8 references before model execution, for example an embedding or preprocessed control artifact.

M9 schema 1 should **not** introduce a generic derived-artifact pipeline unless the baseline implementation actually requires it.

If the selected baseline workflow only consumes image references, keep M9 schema 1 byte selection direct.

If a required baseline model mechanism produces derived bytes, then before implementation freeze the plan must add:

- content-addressed derived artifact identity;
- source-Blob provenance;
- algorithm/version/model identity;
- deterministic/reproducibility claim;
- storage/retention policy;
- Exact Rerun behavior;
- unknown-dependency packaging behavior.

Do not hide derived bytes inside an opaque cache.

---

# 40. Prompt boundary

M9 does not make prompt text visual authority.

Existing prompt compilation continues from captured Shot intent.

A realization profile may not rewrite M8 semantic facts by injecting contradictory prompt content.

If M9 later requires profile-specific prompt augmentation, it must be explicitly captured as execution text and provenance, and must derive from captured authority—not become a second semantic interpretation.

For M9 schema 1, preferred scope is **no new prompt compiler semantics** unless the chosen model profile demonstrably requires it.

---

# 41. Error vocabulary

Freeze these M9-owned codes before implementation; no near-duplicates.

| Code | HTTP | Exact trigger |
|---|---:|---|
| `WORKFLOW_PACKAGE_INTEGRITY` | 503 | Stage-0 current package capture cannot establish one coherent descriptor+artifact byte snapshot: required descriptor/artifact unreadable or missing, any declared manifest/template/profile/fingerprint raw-byte hash mismatches the captured buffer, or the descriptor changes across D1/D2. This is capture integrity, not profile/fingerprint structural invalidity. |
| `REALIZATION_PROFILE_INVALID` | 422 | Captured schema-2 RealizationProfile is syntactically/semantically invalid, including duplicate selectors/channels or invalid profile/model/workflow fields. |
| `REALIZATION_PROFILE_REQUIRED` | 409 | Effective captured M8 authority is non-empty but the selected package is schema 1 / has no legal M9 realization contract. |
| `REALIZATION_REQUIRED_FACET_UNSUPPORTED` | 409 | A required captured facet has no exact rule or its allowed-role filter yields no item. |
| `REALIZATION_CAPACITY_EXCEEDED` | 409 | Adding an entire required facet candidate set would exceed channel `max_items`. |
| `REALIZATION_CHANNEL_MINIMUM_UNMET` | 409 | A channel containing required authority ends below its declared `min_items`. |
| `REALIZATION_INPUT_BINDING_INVALID` | 422 | Profile↔manifest/template/channel/parameter bindings violate the frozen package contract. |
| `EXECUTION_MODEL_FINGERPRINT_INVALID` | 422 | Captured/installed ExecutionModelFingerprint document or its template/package cross-bindings are structurally invalid. |
| `EXECUTION_MODEL_INCOMPATIBLE` | 503 | Live runtime/model artifact identity cannot satisfy the captured ExecutionModelFingerprint before submission. |

Closed optional omission reasons are data, not errors:

```text
no_matching_rule
no_allowed_items
capacity_exceeded
channel_minimum_unmet
```

Inherited codes:

| Code | M9 use |
|---|---|
| existing M7 blockers | Preserve predecessor semantics. |
| existing M8 blockers | Preserve visual-authority semantics. |
| `WORKFLOW_VALIDATION_FAILED` | Existing manifest/package validation outside exact M9-owned profile/fingerprint cases. |
| `WORKFLOW_INPUT_CARDINALITY_INVALID` | Final **combined** legacy + realization manifest cardinality failure. |
| `WORKFLOW_MANIFEST_INTEGRITY` | Historical/captured manifest raw-byte identity failure under the inherited artifact contract; Stage-0 four-artifact capture coherence uses `WORKFLOW_PACKAGE_INTEGRITY`. |
| `COMFY_TEMPLATE_INTEGRITY` / `COMFY_TEMPLATE_BINDING_INVALID` | Existing historical template integrity/exact binding failures. |
| `COMFY_TRANSLATION_FAILED` | Historical logical request cannot be translated through exact captured bindings. |
| `EXECUTOR_UNAVAILABLE` | Transport/service unavailable; distinct from model-fingerprint incompatibility. |
| `ASSET_NOT_FOUND` | Direct current authoring lookup only where applicable. |
| `BLOB_NOT_FOUND` | Direct non-historical Blob identity lookup only; immutable historical physical-byte loss is corruption. |
| `INTERNAL_INVARIANT_VIOLATION` | Historical M8/spec/input/provenance corruption or impossible legal-state mismatch. |

## 41.1 Exact precedence

```text
0. cannot establish coherent package byte snapshot
   → `WORKFLOW_PACKAGE_INTEGRITY` immediately

1. M7 blocker
2. M8 blocker
3. captured package/profile/fingerprint structural/binding validation
4. M9 Shot-specific readiness blocker
5. combined legacy + realization workflow-input cardinality
6. Generation persistence
```

Historical corruption discovered at any stage fails immediately and is never demoted to a friendly readiness issue.

---

# 42. Canonical serialization and artifact identity

All M9 canonical semantic JSON uses the existing SoloRing canonical serializer exactly:

```text
sort_keys = true
separators = (",", ":")
ensure_ascii = false
UTF-8
```

No M9-local canonicalizer exists.

Identity rules:

- manifest, workflow template, RealizationProfile, and ExecutionModelFingerprint artifact identities are SHA-256 over their **exact raw captured file bytes**;
- package descriptor fields reference those raw-byte hashes;
- RealizationSpec is a semantic nested value covered by the outer canonical `workflow_spec_hash`;
- schema 1 defines no second persisted/API realization hash identity.

Parsing/re-serialization never replaces raw-file identity for captured package artifacts.

---

# 43. Normalization

Freeze these rules:

- `facet_key`: use the exact M8 grammar/value; lowercase ASCII by M8 contract, no M9 normalization or aliasing;
- `profile_id`, channel keys, model id/version, artifact keys: trimmed, bounded, case-sensitive execution identifiers under their exact schema constraints;
- workflow id/version: existing workflow contract;
- Git commits: lowercase 40-hex;
- SHA-256: lowercase 64-hex;
- UUIDs: canonical lowercase UUID strings;
- `declared_name`: exact captured template string after schema validation; never normalized into a filesystem path;
- `storage_root_key`: closed adapter enum;
- configured `comfy_model_root_*` values: absolute worker-visible filesystem roots; mutable deployment configuration only, never canonical Generation data;
- channel/input positions: compiler-owned zero-based contiguous integers.

Canonical JSON serialization remains the sole semantic ordering mechanism for object keys; authoring insertion order is not semantic.

---

# 44. Realization readiness versus runtime availability/compatibility

Keep three concepts separate:

```text
visual_continuity_ready
= M8 model-independent production authority ready
```

```text
realization_ready
= this captured/current authority can be mapped legally by the selected package/profile
```

```text
executor_available / execution_environment_compatible
= the live runtime is reachable and can satisfy the captured runtime/model fingerprint
```

A temporarily offline Comfy server does not make a profile semantically incapable.

A model file changed under the same filename does not make M8 or M9 authority invalid; it makes the **live execution environment incompatible** with a captured schema-2 Generation.

Likewise, a reachable Comfy server does not make an unsupported required facet realizable.

UI/API must not collapse these into one readiness flag.

---

# 45. Current profile changes

Changing installed `realization-profile.json` legitimately changes **future new Generation compilation**.

It must not change:

- existing Generations;
- existing GenerationInputs;
- Exact Reruns;
- ShotRevisions;
- M8 visual authority.

Historical Generation inspection may show:

```text
Captured profile: v3 / hash A
Current installed profile: v5 / hash B
```

but must never relabel v5 as what the historical Generation used.

---

# 46. Workflow/profile/fingerprint deletion and retention

Content-addressed historical artifacts referenced by a Generation are immutable execution roots.

For schema-2 Generations this includes:

```text
manifest bytes
workflow template bytes
RealizationProfile bytes
ExecutionModelFingerprint bytes
GenerationInput Blob bytes
```

No GC/deletion path may discard a referenced artifact and then rebuild from current package state.

If a future artifact GC is implemented, all historical Generation references are live roots.

A referenced historical artifact row/path whose physical bytes are missing or hash-mismatched is historical corruption/integrity failure, not permission to recapture current bytes.

---

# 47. Package installation atomicity

Schema-2 installation extends the existing descriptor-last release protocol:

```text
write/verify candidate manifest
write/verify candidate template
write/verify candidate profile
write/verify candidate model fingerprint
run package structural/cross-binding validation
publish/swap workflow-package.json descriptor LAST
```

The current descriptor is the commit marker.

If any candidate artifact/validation fails, the previous descriptor remains current.

Generation/readiness capture still independently verifies descriptor stability and declared hashes, so even a non-SoloRing/manual replacement cannot produce a certified hybrid.

---

# 48. Concurrent current-state mutation

M9 compilation starts from an immutable ShotRevision after capture.

Therefore M8 mutations concurrent with M9 compile must not create hybrid M9 state.

Required race proof:

```text
M8 approval/policy/current Feature state changes after ShotRevision capture
        ↓
M9 compiler output remains based solely on the captured ShotRevision
```

This is stronger and simpler than re-resolving current M8 during M9.

---

# 49. Concurrent package mutation

Package capture and DB persistence are separated deliberately.

Required interleavings:

### Form A — switch before capture establishes package bytes

Generation uses complete AFTER package.

### Form B — switch after captured byte buffers are established

Generation uses complete BEFORE package.

Never hybrid.

The test must use events at the actual package-read/switch seam; zero sleeps.

---

# 50. Concurrent duplicate Generation creation

M9 does not redefine Generation identity convergence.

Two distinct user requests may legitimately create two Generations even if their workflow specs are byte-identical, because Generation is an execution request/provenance event, not a deduplicated content artifact.

Do not add `(shot_revision_id, workflow_spec_hash)` uniqueness.

This differs intentionally from immutable ShotRevision/VisualAnchorRevision convergence.

---

# 51. Worker historical validation

Before schema-2 submission, worker validation uses **historical Generation identities only**:

```text
Generation row/workflow_spec
        ↓
historical manifest + template by captured hashes
        ↓
historical RealizationProfile by captured profile hash
        ↓
historical ExecutionModelFingerprint by captured fingerprint hash
        ↓
GenerationInputs by Generation id
        ↓
spec/input/model-column/profile/fingerprint cross-validation
        ↓
live deployment attestation compatibility
        ↓
explicit live model-file SHA-256 verification
        ↓
materialize Blob bytes
        ↓
translate
```

Forbidden worker dependencies:

- current installed package descriptor;
- current RealizationProfile selection;
- current M8 resolver/tables;
- M9 realization compiler;
- graph heuristics for model files or realization channels.

Current installed package may be replaced/removed without altering a queued historical Generation. If the live executor environment cannot satisfy the historical fingerprint, fail exactly as `EXECUTION_MODEL_INCOMPATIBLE`; never substitute current model files.

---

# 52. Input materialization

Existing Comfy input materialization remains correct for M9:

- Blob hash is authoritative byte identity;
- source bytes are hashed before upload;
- same bytes are streamed;
- hash is rechecked after transport;
- attempt namespace prevents remote collision;
- translation uses returned executor-local reference.

M9 must ensure selected visual references enter this path only through immutable GenerationInputs.

No profile may point directly at a local source filename.

---

# 53. Executor submission provenance

The existing `executor_submission_json/hash` remains the exact executor payload identity. M9 adds no competing submission identity.

The provenance chain becomes:

```text
M8 historical authority
        ↓
RealizationSpec + ExecutionModelFingerprint hash
        ↓
workflow spec schema 2
        ↓
GenerationInputs
        ↓
historical manifest/template/profile/fingerprint artifacts
        ↓
verified live runtime/model bytes
        ↓
materialized executor-local references
        ↓
executor_submission_json/hash
```

The captured fingerprint expresses what environment/model bytes are required. Live verification is a prerequisite to producing/submitting the payload; ephemeral live PID/process-start evidence does not rewrite the Generation's historical specification.

This preserves distinct identities for production authority, logical execution request, required model bytes, and actual executor payload.

---

# 54. Realization request conformance gate

Before submission, fixture/source-gate the translator and verifier to prove:

- every required RealizationSpec selected binding appears exactly once in its intended logical input;
- no undeclared M8 Asset appears;
- channel/input order and cardinality are preserved;
- final translated parameter values equal captured workflow-spec parameters;
- profile override audit agrees with those final values;
- historical fingerprint binding `(node,field,declared_name)` agrees with captured template;
- live model bytes hash to the expected historical fingerprints;
- changing current profile/package/M8 does not alter translation;
- current M8 resolver and compiler disabled → historical translation still works;
- missing explicit manifest/model target fails before submission.

This proves request/model-artifact conformance, **not** visual-output quality.

---

# 55. Baseline fake executor

Fake executor must remain compatible with workflow-spec schema 2 as an execution-test backend.

It may ignore model-specific semantics internally, but tests must ensure it does not crash or rewrite the captured spec.

Do not use FakeExecutor success as proof that Comfy/model realization works.

At least one real Comfy-backed profile/translation path is required for M9 closure.

---

# 56. API package behavior

New Generation endpoint remains the normal entry point.

No client supplies:

- profile hash;
- model id;
- selected visual Assets;
- M9 parameters;
- channel bindings.

Those are server-derived from:

```text
captured workflow package
+
captured ShotRevision
```

This prevents the client from bypassing M8 authority by submitting arbitrary conditioning references.

If later user-selectable workflow/profile choice is added, the client may select a **declared package/profile identity**, but the server still derives and validates all realization bindings.

M9 schema 1 should use the existing configured workflow selection unless source-fit explicitly expands workflow choice.

---

# 57. No client-supplied visual override

Explicitly forbidden API shapes in M9:

```json
{"identity_reference_asset_id": "arbitrary-client-asset"}
```

```json
{"visual_anchor_revision_id": "client-selected-old-revision"}
```

```json
{"adapter_strength": 4.0}
```

unless a future execution-override contract is deliberately designed and captured.

M9 v1 uses profile-defined execution policy over captured M8 authority.

---

# 58. UI/current package selection

If the application currently has one installed workflow selected by Settings, M9 keeps that constraint.

Do not add a general model marketplace/profile registry just because M9 introduces profiles.

A future workflow selector can be designed separately.

The M9 UI may display the currently configured package/model/profile and its readiness against the Shot.

---

# 59. Query/statement-shape contract

`compile_realization()` performs zero SQL.

For one target new Generation, historical M8 reconstruction must remain batched:

- existing ShotRevision/history read path;
- batched captured M8 visual authority rows;
- batched captured visual-item rows;
- batched Asset/Blob integrity/liveness as required by the frozen M8 capture contract;
- no query per facet, anchor, item, channel, or rule.

Legacy ShotReference resolution retains predecessor query behavior.

GenerationInput persistence may increase **rows**, but must not perform lookup queries per realization item. Use the existing bulk/transactional persistence shape.

The M9F proof counts both read and write SQL statement classes/round trips through the same production target path:

```text
small legal target
vs
representative legal target
```

Required result:

```text
same count
```

or, only if source-fit proves one unavoidable fixed setup class:

```text
representative == small + frozen justified constant
```

No cardinality-dependent increase is allowed.

---

# 60. Representative scale fixture

Preserve the established feature-film target dimension:

```text
~2,500 Shots
recurring characters + locations
multiple entity + feature-value visual facets
required + optional facets
multi-view anchors
shared realization channels fed by different selector kinds
```

The designated target Shot must exercise at least:

1. one single-reference finite-capacity profile;
2. one multi-channel profile;
3. two different selectors intentionally sharing one channel;
4. required whole-facet capacity success and overflow;
5. optional no-rule, no-allowed-item, capacity, and channel-minimum omissions;
6. one feature-value realization;
7. multi-item/multi-view reference packs;
8. package v2 + empty M8 → exact workflow-spec v1 compatibility path.

Compare small vs representative SQL/statement count through the same production path per §59.

Record, but do not gate on arbitrary thresholds for:

- wall time;
- compiler CPU time;
- RealizationSpec byte size;
- memory use.

Direct-SQL bulk wiring is allowed only for non-target scale volume, must preserve every frozen invariant, and must include mechanical legality assertions/disclosure exactly as established in M8.

---

# 61. Concurrency/race proof mechanics

No sleeps.

Use events/barriers at the actual contested seam.

Required races:

1. package release switch before/after captured profile bytes;
2. M8 current approval change after ShotRevision capture while M9 compilation proceeds;
3. model/profile file replacement while readiness preview is running—preview sees complete before/after package, never mixed bytes;
4. Exact Rerun concurrent with current profile replacement—rerun unchanged;
5. worker execution concurrent with installed package replacement—historical artifact-store package used, not installed current files.

For SQLite write races introduced by M9, events must fire at actual `BEGIN IMMEDIATE` entry/commit, matching the M7D/M8 final proof form.

If M9 adds no new DB write transaction beyond existing Generation creation, do not invent a synthetic write-race test; instead prove the relevant inherited transaction remains unchanged.

---

# 62. Readiness-preview race semantics

Preview is inspection, not reservation, but each response must be internally coherent.

One response must contain:

```text
one complete coherent current M7/M8 interpretation
+
one complete captured-in-memory package release identity
+
one canonical CapturedVisualAuthority value
+
one compiler result
```

Package/profile/fingerprint A/B replacement races are forced at actual artifact-read/descriptor seams:

- switch before snapshot establishment → complete AFTER;
- switch after snapshot establishment → complete BEFORE.

Never mixed artifact hashes.

Generation creation independently repeats package + ShotRevision capture. UI must display the package hashes used by the preview so staleness is inspectable.

---

# 63. Schema compatibility matrix

## 63.1 Workflow package / manifest

| Package | Manifest | Profile | Model fingerprint | Meaning |
|---|---|---|---|---|
| v1 | v1 | none | none | exact legacy package |
| v2 | v2 | required | required | M9-capable package |
| v2 | v1 | any | any | invalid |
| v1 | v2 | any | any | invalid |
| v2 + missing/corrupt profile/fingerprint | v2 | invalid | invalid | fail closed |

## 63.2 Effective authority → workflow spec

| Package | Effective captured M8 authority | Workflow spec |
|---|---|---|
| v1 | empty | exact v1 |
| v1 | non-empty | blocked (`REALIZATION_PROFILE_REQUIRED`) |
| v2 | empty | exact v1 if ordinary manifest cardinality permits |
| v2 | non-empty | v2 if all M9 gates pass |

## 63.3 Manifest-v2 / spec-v1 execution

This combination is explicitly supported for valid schema-2 packages with no effective M9 realization.

- legacy `shot_reference` declarations resolve exactly as predecessor semantics;
- no realization channel has historical realization bindings;
- ordinary required/cardinality rules may still make that package unusable for the Shot;
- profile/fingerprint are not historical Generation dependencies when no M9 realization was captured.

## 63.4 Historical rerun

| Source Generation | Exact Rerun after M9 |
|---|---|
| workflow spec v1 | remains exact v1 |
| workflow spec v2 | remains exact v2 with same model/fingerprint/realization/input set |

No historical object is upgraded in place.

---

# 64. Migration policy

Base M9 plan requires **no Alembic migration**. This is now supported by direct source audit of the published M8 tree, including confirmation that `generation_inputs.reference_role` already exists.

Migration head remains:

```text
0009_m8_visual_identity
```

for the initial M9 implementation.

This is deliberate, not an omission.

M9 evolves captured execution-document schemas and workflow-package artifacts using existing durable Generation columns/tables.

If source-fit discovers a genuine relational requirement not representable safely in existing tables, stop implementation and revise/freeze this plan before adding `0010`.

---

# 65. Workflow artifact-store extension

Extend the existing content-addressed workflow artifact store with two schema-2 historical kinds:

```text
realization_profiles
execution_model_fingerprints
```

Required operations mirror manifest/template storage:

```text
capture exact raw bytes
verify raw SHA-256
place content-addressed with race convergence
retrieve historical bytes by hash
verify hash on read
never fall back to current installed file
```

Missing/corrupt historical profile or fingerprint bytes fail closed.

The artifact store remains filesystem/content-addressed infrastructure; no new DB table is required.

---

# 66. Package descriptor integrity

The package descriptor is the release commit marker and cross-file integrity authority.

Schema 2 must prove:

```text
descriptor.workflow identity
== manifest workflow identity
== profile workflow identity
```

```text
profile model id/version
== ExecutionModelFingerprint model id/version
```

and:

```text
descriptor manifest_hash
== exact captured manifest bytes hash

descriptor workflow_template_hash
== exact captured template bytes hash

descriptor realization_profile_hash
== exact captured profile bytes hash

descriptor execution_model_fingerprint_hash
== exact captured fingerprint bytes hash
```

Descriptor D1/D2 release identity must remain unchanged across capture.

Any disagreement prevents semantic package use; no field is repaired from another artifact.

---

# 67. Runtime profile use prohibition

The worker may load captured profile bytes only to verify historical integrity/diagnostics.

The worker must **not** invoke:

```text
profile rules
→ recalculate which M8 references to use
```

Selection happened once at Generation creation.

This rule is source-gated with a monkeypatch that makes the M9 compiler fail during worker execution while a captured schema-2 Generation still proceeds to translation.

---

# 68. Model/profile/fingerprint evolution

A profile semantic change produces a new `profile_version` and new raw-byte hash.

A model upgrade or any model-file content change produces a new ExecutionModelFingerprint hash and normally a new profile/model version as appropriate.

Reinstalling exact identical raw profile/fingerprint bytes naturally converges on the same content identities.

Future Generations may use new package releases.

Historical Generations retain their original:

```text
profile hash
model id/version
execution-model-fingerprint hash
workflow spec
GenerationInputs
```

and either execute under a compatible live environment or fail closed.

No historical Generation is migrated to a “compatible” new profile/model automatically. No DB migration is required for this evolution.

---

# 69. Relationship to M10

M9 may condition a model on M8 references but cannot guarantee spatial identity under arbitrary camera motion.

Example hotel lobby:

M8:

```text
approved lobby identity / desk / signage / material references
```

M9:

```text
feed appropriate captured references to the selected model/profile
```

M10:

```text
authoritative layout/camera/spatial constraints
```

If M9 cannot create a reverse angle without geometry drift, that does not justify putting guessed 3D state into M9.

---

# 70. Relationship to generated-output promotion

M9 outputs remain ordinary generated output Assets/Takes.

Even if a Generation used strong identity conditioning, its output is not automatically a better authority.

The existing M8 deliberate promotion chain remains:

```text
output Asset
→ manually add to M8 working visual identity
→ capture VisualAnchorRevision
→ explicit approval
```

M9 never closes that loop automatically.

---

# 71. Relationship to model training / LoRA authoring

Training or authoring a LoRA/embedding from M8 reference packs is **not** automatically part of M9 schema 1.

Those are potentially expensive derived-artifact workflows with their own provenance/reproducibility requirements.

M9 may consume such a pinned model-specific artifact in a future realization profile, but creation/training of that artifact requires a separately frozen contract if introduced.

Do not smuggle training into M9 as an implementation detail.

---

# 72. Relationship to automatic visual QC

M9 does not define a universal face/location/wound similarity metric.

Any future automated continuity-QC model would itself be an execution tool downstream of M8 authority and would need:

- versioned evaluator identity;
- captured inputs;
- thresholds with explicit semantics;
- false-positive/negative evaluation;
- no automatic M8 authority mutation.

Deferred.

---

# 73. Source gates for no-authority-transfer

Final source gate uses **both static and dynamic proof**.

## 73.1 Static audit

Inspect every M9 compiler/readiness/capture/worker/executor dependency that touches M8 modules. Read-only historical reconstruction/current preview resolution is allowed only through explicit read contracts.

Any new write-capable path from M9 into:

- VisualFacet;
- value policies;
- VisualAnchor working state;
- VisualAnchorRevision approval;
- generated-output promotion;

is milestone-blocking.

## 73.2 Dynamic SQL mutation spy

Around representative:

```text
realization preview
new Generation creation
worker execution
Exact Rerun creation
```

spy SQL and assert M9 realization/execution causes **zero INSERT/UPDATE/DELETE** against M8 authority tables.

Expected predecessor writes (e.g. ShotRevision/Generation persistence) are separately classified and do not authorize M8 writes.

No automatic approval/promotion is allowed.

---

# 74. API/UI historical honesty

Historical Generation APIs/inspectors must distinguish:

```text
Captured package/profile/model/fingerprint/realization
```

from:

```text
Current installed package/profile/model/runtime status
```

Current state is informational and may be unavailable.

Never render current profile/model/fingerprint as what the historical Generation used.

Historical UI must use content identities where they matter:

- profile hash;
- ExecutionModelFingerprint hash;
- selected Asset IDs + Blob hashes;
- workflow/manifest/template identities.

`profile_id`/`model.version` are labels; they do not replace content identity.

---

# 75. Package/artifact-unavailable behavior

### New Generate

If one coherent current package release cannot be captured, reject before DB work.

If coherent bytes exist but schema-2 profile/fingerprint/package semantics are invalid, apply the exact §11 predecessor/error precedence and reject before Generation persistence.

### Exact Rerun creation

Does not require current installed package/profile/fingerprint availability. It copies the original Generation specification and GenerationInputs verbatim.

### Execution of already queued historical Generation

Requires the historical artifacts referenced by that Generation and a live executor environment satisfying its captured ExecutionModelFingerprint.

Historical artifact loss/corruption never triggers current-package fallback or recompilation.

---

# 76. Environment/model drift

Before submission, if live verification differs from the captured historical requirement:

```text
model file hash mismatch
required model file missing
ComfyUI commit mismatch
required custom-node commit mismatch
custom-node policy mismatch
```

then:

- do not modify workflow spec;
- do not substitute another file/model/profile;
- do not drop conditioning;
- fail as `EXECUTION_MODEL_INCOMPATIBLE` (or historical artifact integrity where the historical bytes themselves are corrupt);
- preserve exact diagnostic detail without turning the live value into historical authority.

A future compatibility declaration that intentionally permits multiple runtime revisions requires a new frozen fingerprint schema/contract; schema 1 uses exact matching.

---

# 77. M9A — Package/profile/fingerprint contract and source-fit closure

Begin only after this plan is frozen and implementation is explicitly authorized.

Scope:

1. re-verify predecessor baseline/tag/tree identity;
2. encode strict RealizationProfile schema 1 exactly;
3. encode strict manifest schema 2 exactly;
4. encode workflow-package schema 2 exactly;
5. encode strict ExecutionModelFingerprint schema 1 exactly;
6. extend artifact store for profile/fingerprint bytes;
7. extend coherent package capture from two to four artifacts;
8. implement package/profile/manifest/template/fingerprint cross-validation;
9. add the exact four `Settings` model-root fields from §6.4 and the closed root-key adapter; empirically verify which characterized Comfy filesystem root each key denotes rather than inferring folder names;
10. inventory every model-bearing loader in the baseline Hunyuan workflow and build the exact initial fingerprint;
11. author the initial **Hunyuan schema-2 release** as an M9A deliverable: workflow package version advances from the published v3 release to v4, with manifest schema 2, `realization-profile.json`, `execution-model-fingerprint.json`, and descriptor hashes that bind the four-artifact release; the published schema-1 v3 bytes remain golden compatibility fixtures and are not rewritten;
12. empirically characterize and fixture-pin the baseline profile selector/capacity set that the single-image Hunyuan path actually demonstrates; do not claim unsupported multi-facet capability;
13. verify `GenerationInputs` source-fit facts remain as audited (`reference_role` included); any contradictory source finding is a STOP/plan-change event;
14. freeze exact error/omission vocabularies in code fixtures, including `WORKFLOW_PACKAGE_INTEGRITY`;
15. preserve schema-1 package/manifest fixtures byte-for-byte.

### M9A gate

- schema documents reject unknown fields recursively;
- exact golden raw-byte hash fixtures for profile + fingerprint;
- profile/fingerprint model identity agreement;
- manifest/profile channel bijection proof;
- schema-1↔schema-2 `shot_reference` legacy equivalence fixture;
- every fingerprint binding exists in template and exact declared filename matches;
- baseline fingerprint covers **all** model-bearing loader fields, not only the UNet;
- all four schema-1 model-root Settings exist, require absolute paths when configured, and map only through the closed adapter vocabulary;
- baseline root-key mappings are empirically pinned against the characterized deployment, including the ComfyUI-GGUF loader search root;
- initial Hunyuan schema-2 v4 package/profile/fingerprint/manifest descriptor is authored and validates; published schema-1 v3 golden bytes remain unchanged;
- package A/B switch proof returns complete A/B only;
- invalid candidate activation cannot replace current descriptor where installer seam applies;
- schema-1 package accepted unchanged;
- no DB migration added;
- exact source-fit ledger recorded.

---

# 78. M9B — canonical authority builder + ONE realization compiler + readiness

Scope:

1. historical `CapturedVisualAuthority` reconstruction from ShotRevision schema 4;
2. current-preview adapter into the same capture-shaped value;
3. visual-reference-pack hash recomputation/cross-check;
4. pure compiler value objects;
5. exact M8 facet-key matching;
6. required whole-facet allocation;
7. optional whole-facet omission with closed reasons;
8. channel minimum semantics;
9. exact shared-channel selector behavior;
10. profile parameter override resolution;
11. readiness-preview endpoint with package identity;
12. preview↔historical authority parity fixtures.

### M9B gate

- current vs historical same logical M8 state **with requirement held constant** → identical `CapturedVisualAuthority`; current requirement changes never leak into historical reconstruction;
- same authority/package → byte-identical RealizationSpec across preview/historical adapter;
- required no-rule/no-allowed-items blocks;
- required whole-facet overflow blocks;
- required channel minimum unmet blocks;
- optional no-rule/no-items/capacity/minimum omissions use exact reasons;
- no partial facet binding;
- two selectors sharing one channel resolve deterministically;
- primary-only channel selects exact primary set by role filtering, not hard-coded primary logic;
- current M8 resolver disabled during historical compiler path → still works;
- compiler performs zero SQL/filesystem/network;
- no partial spec on failure.

---

# 79. M9C — Generation capture / workflow-spec schema 2

Scope:

1. integrate four-artifact package capture with existing Generation creation;
2. apply exact §11 precedence;
3. merge legacy and realization input projections after compiler return;
4. run combined manifest cardinality only at assembly layer;
5. resolve final parameters with profile-last precedence;
6. build canonical workflow-spec schema 2;
7. preserve exact workflow-spec schema 1 for no-realization cases, including package-v2/authority-empty path;
8. populate Generation model fields;
9. persist exact GenerationInputs;
10. add historical Generation M9 projection.

### M9C gate

- no combined cardinality validation inside compiler;
- schema-1 golden bytes unchanged when no M9 content;
- package v2 + empty authority → exact spec v1;
- package v1 + non-empty authority → `REALIZATION_PROFILE_REQUIRED`;
- schema-2 exact canonical fixture;
- profile/model/fingerprint/spec/input cross-validation exact;
- RealizationSpec parameter overrides == final captured parameter values;
- client cannot inject arbitrary M8 reference/model/profile/strength;
- model-column/spec mismatch fails closed;
- persisted input corruption loop fails then positive-control restores/converges.

---

# 80. M9D — Executor translation + model/runtime historical isolation

Scope:

1. parse historical manifest schema 2 and workflow spec schema 1/2 combinations;
2. translate realization-backed input keys only from persisted GenerationInputs;
3. retrieve/verify historical profile + ExecutionModelFingerprint artifacts;
4. verify fingerprint runtime requirements against live deployment attestation;
5. verify every live model artifact byte hash through the exact §6.4 storage-root bindings on every submission attempt;
6. keep translator free of profile-rule evaluation;
7. enforce no graph heuristics;
8. preserve Exact Rerun schema-2 isolation;
9. record request-conformance/runtime compatibility evidence in existing execution provenance seams;
10. keep normal CI hermetic: storage-root/hash behavior uses local fixture roots and small fixture model files; tests requiring the real characterized Comfy deployment/attestation run only in the explicit M9 live-gate lane, following the M5B live-evidence discipline.

### M9D gate

- translated graph contains exact captured selected input bytes/parameters;
- explicit model-fingerprint `(node,field,name)` matches historical template;
- changing a live model file under the same filename → `EXECUTION_MODEL_INCOMPATIBLE` before submission;
- unset/non-absolute/unreadable required model-root mapping → `EXECUTION_MODEL_INCOMPATIBLE` before submission;
- every submission attempt re-hashes content; a stat/mtime cache is absent from schema 1;
- offline CI proves root resolution/hash/drift behavior with fixture files; deployment-attestation compatibility is proven in the designated live gate rather than making CI depend on Comfy;
- required runtime commit/policy drift → `EXECUTION_MODEL_INCOMPATIBLE`;
- missing node/field fails before submission;
- current installed package/profile removed → queued historical Generation still reaches historical validation;
- compiler monkeypatched to fail → worker does not call it;
- current M8 resolver monkeypatched to fail → worker does not call it;
- Exact Rerun copies v2 spec/model/fingerprint/input set exactly;
- query spy proves zero current M8/profile/package-selection reads during rerun/worker semantics;
- Blob/history corruption fails closed before executor submission.

---

# 81. M9E — Realization UI

Scope:

1. Shot realization-readiness panel from server preview;
2. evaluated package-release identity/hashes and non-reservation label;
3. M8 vs M9 vs runtime-compatibility status separation;
4. per-facet channel mapping/status;
5. selected-reference preview from server compiler output;
6. exact optional omission reasons;
7. profile/model/fingerprint identity display;
8. historical Generation realization inspector with Asset/Blob provenance;
9. captured-vs-current profile/package/model distinction;
10. no M8 mutation from M9 UI.

### M9E gate

- frontend typecheck;
- component tests for predecessor-blocked, package-invalid, required-unsupported, min/max-capacity, each optional omission reason, runtime-incompatible, and ready states;
- fetch-boundary tests prove no client-side authority construction/rule matching;
- preview displays exact package hashes used;
- historical Generation remains unchanged after current profile/package/model changes;
- historical inspector renders fingerprint + Blob identity;
- production build clean.

---

# 82. M9F — Failure, race, scale, and source gate

Scope:

1. execute full frozen failure matrix;
2. run package A/B capture/preview races at actual byte-read seams;
3. run current-M8-after-ShotRevision isolation proofs;
4. run Exact Rerun compiler/current-table query-spy proof;
5. run model-file same-name/different-bytes drift proof;
6. run representative scale fixture and small-vs-large SQL statement-count proof;
7. run static + dynamic no-authority-transfer audits;
8. verify archive fidelity against exact gated source tree;
9. run full backend/frontend gates twice consecutively under the project publication protocol.

### M9F gate mechanics

- no sleeps in race proofs;
- Events/barriers fire at real package read/swap or DB transaction seams;
- source-gate independently inspects implementation, not only test names;
- representative target rows are legal production state;
- query/statement count is cardinality-independent per §59;
- model fingerprint covers every package-declared model-bearing artifact;
- zero M8 authority-table mutations caused by M9 paths;
- Exact Rerun/current worker semantics remain independent of current M8/profile/package selection;
- closure artifact regenerated from the exact gated commit with reproducible archive rule.

---

# 83. Critical proof — authority direction

Construct:

```text
M8 required face revision A captured
profile A selects it at strength 0.8
model fingerprint F captures exact model bytes
Generation G succeeds
```

Then change:

```text
current M8 approval → revision B
current profile strength → 1.0
current package/model files → different release
```

Assert historical G still contains:

```text
visual revision A
strength 0.8
profile hash A
execution model fingerprint F
original GenerationInputs
```

and dynamic SQL mutation spy proves G creation/execution/rerun caused no M8 authority mutation.

---

# 84. Critical proof — unsupported required facet

Captured authority contains two required facets, while the selected profile can exactly realize only one.

Generation creation must fail before persistence/queueing.

It must not:

- pick one and drop the other;
- use an optional/generic ShotReference as substitution;
- partially bind a required facet's items;
- weaken M8 requirement state;
- create a queued failed Generation merely to discover capability.

---

# 85. Critical proof — atomic capacity and optional omissions

Fixture includes:

```text
required identity with 2 eligible items
optional hair with 1 item
optional wardrobe with 2 items
shared channel max_items = 3
```

Assert:

- required identity binds both items atomically;
- hair may bind as the next whole optional facet if it fits;
- wardrobe is omitted wholly as `capacity_exceeded` rather than partially binding one item;
- double run yields byte-identical spec.

Separate fixtures prove exact `no_matching_rule`, `no_allowed_items`, and `channel_minimum_unmet` omission reasons plus required minimum failure.

---

# 86. Critical proof — schema lattice / no empty workflow-spec v2

Golden cases:

```text
package v1 + empty M8
→ exact predecessor workflow-spec v1 bytes
```

```text
package v1 + non-empty M8
→ REALIZATION_PROFILE_REQUIRED
```

```text
package v2 + empty M8 + cardinality-valid legacy path
→ exact workflow-spec v1 bytes
```

```text
package v2 + non-empty M8
→ workflow-spec v2
```

No empty realization member/document is emitted.

---

# 87. Critical proof — preview parity and staleness

1. current Shot/package A preview produces `CapturedVisualAuthority X` and RealizationSpec R;
2. capture a ShotRevision representing the same logical M8 state X **with the same requirement value**;
3. historical adapter + package A must produce byte-identical R;
4. switch current package to B;
5. Generate now captures/compiles B, not preview A;
6. preview response's package hashes make the stale A result visibly attributable.

No preview reserves package or Shot state.

Then mutate only the **current** facet requirement after ShotRevision capture and assert:

- current preview may honestly change because its `requirement` changed;
- historical `CapturedVisualAuthority.requirement_at_capture` remains the captured value;
- historical reconstruction performs zero read of current requirement policy to force parity.

---

# 88. Critical proof — package switch coherence

Mechanically force at actual descriptor/artifact-read seams:

### Race 1 — switch before snapshot establishment

Capture/preview uses complete AFTER package B.

### Race 2 — switch after snapshot establishment

Capture/preview uses complete BEFORE package A.

Assert descriptor, manifest, template, profile, and model-fingerprint hashes all belong to the same release.

No mixed A/B set is accepted.

---

# 89. Critical proof — historical worker isolation + model-byte drift

Create schema-2 Generation G, then:

- alter current M8;
- replace/remove current installed profile/package;
- monkeypatch realization compiler/current M8 resolver to throw;
- keep historical artifacts available.

Worker must reconstruct G solely from historical artifacts/inputs.

Then perform two model tests:

### Positive control

Live files/runtime exactly satisfy G's ExecutionModelFingerprint → translation/submission proceeds.

### Drift

Replace one model file with different bytes under the **same filename** → worker fails `EXECUTION_MODEL_INCOMPATIBLE` before submission and does not recompile/substitute.

This is the direct proof that filename identity is not trusted.

---

# 90. Critical proof — reproducibility claim

M9 closure wording must distinguish three levels:

```text
1. exact historical logical request
   → guaranteed by workflow spec + inputs

2. exact historical reference/model artifact bytes
   → guaranteed by Blob hashes + ExecutionModelFingerprint

3. byte-identical rendered media
   → NOT guaranteed by M9
```

Level 3 requires additional determinism over GPU/driver/framework/random kernels/executor behavior that M9 schema 1 does not claim.

Exact Rerun therefore means:

> reproduce the captured logical request and require the captured model/reference artifact identities;

not:

> guarantee identical output bytes.

---

# 91. Failure matrix

At minimum cover every exact class below.

### Package/profile/fingerprint

- missing schema-2 profile;
- missing schema-2 fingerprint;
- Stage-0 descriptor/profile/fingerprint/manifest/template missing or declared raw hash mismatch → `WORKFLOW_PACKAGE_INTEGRITY`;
- historical profile/fingerprint bytes missing/tampered → `INTERNAL_INVARIANT_VIOLATION`;
- profile workflow mismatch;
- fingerprint model/profile mismatch;
- duplicate channel;
- duplicate selector;
- unknown channel in rule;
- empty/invalid allowed roles;
- impossible capacity declaration;
- min-items channel unreachable from rules;
- profile channel without manifest input;
- manifest realization input without profile channel;
- two channels sharing one input_key;
- unknown profile/fingerprint field;
- fingerprint node/field missing;
- fingerprint declared_name differs from template;
- profile parameter name missing from manifest;
- profile parameter value invalid by manifest validator.

### Captured M8 authority / compiler

- historical visual pack hash mismatch;
- required selector unsupported;
- required candidate has no allowed item;
- required whole-facet max overflow;
- required channel minimum unmet;
- optional no rule;
- optional no allowed item;
- optional capacity omission;
- optional channel-minimum omission;
- shared channel fed by entity + feature-value selectors;
- captured VisualAnchor provenance corruption;
- captured Asset/Blob mismatch;
- physical historical Blob missing.

### Generation historical state

- workflow spec hash mismatch;
- model-column mismatch;
- fingerprint-hash/spec mismatch;
- GenerationInput missing/extra;
- wrong role/position/Asset/Blob;
- non-contiguous realization positions;
- historical profile/fingerprint missing/corrupt;
- historical manifest/template corrupt.

### Translation/runtime

- realization input missing materialized value;
- duplicate input slot;
- explicit node/field missing;
- current installed package differs/remains unavailable;
- current M8 differs;
- same model filename with different bytes;
- required model-root setting unset/non-absolute/unreadable;
- resolved declared model name escapes the configured root;
- required model file missing;
- ComfyUI/custom-node revision mismatch;
- custom-node policy mismatch;
- executor unavailable.

Every case maps to one frozen result/error class; no friendly recovery reconstructs historical state from current state.

---

# 92. Rejected M9 enhancements

Do **not** add during M9 unless the frozen plan is explicitly amended:

- M8 auto-promotion from successful Generations;
- model training/fine-tuning pipeline;
- generic LoRA/embedding registry as production authority;
- spatial reconstruction;
- camera/layout authority;
- automatic face similarity scoring as canon acceptance;
- per-frame continuity state;
- profile marketplace;
- arbitrary client-provided conditioning Asset overrides;
- model selection optimizer/agent;
- cache/materialized DB tables for realization readiness;
- new database migration merely for convenience;
- filesystem profile path as historical identity;
- profile rules with wildcard/regex/AI semantic matching;
- executor graph heuristics;
- trusting model filenames without content hashes;
- persistent model-hash caches based on path/mtime/size/stat metadata in fingerprint schema 1;
- inferring model-root directories from `storage_root_key` names or loader classes;
- partial facet truncation hidden behind channel capacity.

---

# 93. Definition of done

M9 is complete only when all statements below are true.

## Authority

- [ ] M8 approved/captured state remains sole visual authority.
- [ ] M9 compiler/executor causes zero M8 authority writes, proven statically and dynamically.
- [ ] Model/profile/fingerprint concepts remain execution-layer facts.

## Package/profile/model identity

- [ ] RealizationProfile schema 1 strict/frozen.
- [ ] Manifest schema 2 strict/frozen with exact source discriminator.
- [ ] Workflow package schema 2 binds manifest/template/profile/fingerprint hashes.
- [ ] ExecutionModelFingerprint schema 1 strict/frozen.
- [ ] Every baseline model-bearing loader artifact is content-hashed.
- [ ] Exact schema-1 model-root Settings/adapter exist and baseline root mappings are empirically characterized.
- [ ] Every submission attempt performs exact content hashing with no persistent stat/mtime cache.
- [ ] Initial Hunyuan schema-2 v4 package/profile/fingerprint is authored and fixture-pinned; published v3 schema-1 bytes remain golden unchanged.
- [ ] Historical profile/fingerprint bytes are content-addressed retention roots.
- [ ] Package A/B switch cannot create mixed capture.
- [ ] Schema-1 package remains accepted unchanged.
- [ ] No DB migration exists.

## Authority builder/compiler/readiness

- [ ] ONE canonical `CapturedVisualAuthority` shape for preview + historical reconstruction.
- [ ] Historical visual-reference-pack hash is recomputed/cross-validated.
- [ ] ONE pure realization compiler.
- [ ] Required unsupported/no-item/min/max failures exact.
- [ ] Facet binding is atomic.
- [ ] Optional omission reasons are closed/deterministic/inspectable.
- [ ] Shared-channel selectors deterministic.
- [ ] Preview includes exact package identity and is labeled non-reserving.
- [ ] Preview exposes server-owned `facet_statuses` and channel-capacity rows; frontend performs no facet/channel reconstruction.
- [ ] Preview↔historical byte-parity proof holds only with requirement constant, and current requirement drift never contaminates historical reconstruction.

## Historical capture

- [ ] Workflow spec v2 captures complete M9 realization provenance.
- [ ] Workflow spec v1 bytes remain exact when realization absent, including package-v2/empty-authority path.
- [ ] Generation model fields match nested spec identity.
- [ ] RealizationSpec fingerprint hash matches historical fingerprint artifact.
- [ ] GenerationInputs exactly project RealizationSpec selected bindings.
- [ ] Combined legacy+realization cardinality is assembly-layer validation only.
- [ ] Historical corruption fails closed.

## Execution

- [ ] Comfy translator uses only explicit historical bindings.
- [ ] No current profile/package/M8 lookup defines historical execution.
- [ ] Worker does not invoke realization compiler.
- [ ] Live model bytes are hash-verified against captured fingerprint.
- [ ] Required runtime commits/policy are verified.
- [ ] Same filename/different bytes fails before submission.
- [ ] Submitted payload contains exact captured realization inputs/parameters.

## Exact Rerun

- [ ] Copies v1/v2 spec/model/input set verbatim.
- [ ] Current M8 resolver disabled → rerun creation still works.
- [ ] M9 compiler disabled → rerun creation still works.
- [ ] Current installed package/profile unavailable → rerun creation still works.
- [ ] Query spy proves no current M8/profile/package-selection reads for rerun semantics.

## UI

- [ ] M9 readiness shown separately from M8 readiness and executor availability.
- [ ] Preview shows package/profile/model/fingerprint identity used for evaluation.
- [ ] Required/optional mapping and exact omission reasons visible.
- [ ] Historical captured values never replaced by current values.
- [ ] Browser does not reimplement M8 authority construction or M9 rule matching.

## Scale/audit

- [ ] Small vs representative target has cardinality-independent SQL/statement count.
- [ ] Representative direct-SQL noise is legal and mechanically asserted.
- [ ] Race tests use actual barriers/events, zero sleeps.
- [ ] Full backend/frontend gates green twice.
- [ ] Closure archive fidelity verified from exact gated source.
- [ ] Publication remains unauthorized until source-gate PASS + explicit authorization.

---

# 94. Milestone sequence

```text
M9A — package/profile/fingerprint contracts + source-fit implementation
        ↓
M9B — canonical M8 authority value + ONE compiler + readiness
        ↓
M9C — Generation schema-2 capture + combined input assembly
        ↓
M9D — historical Comfy translation + live model/runtime verification
        ↓
M9E — realization inspection UI
        ↓
M9F — failure/race/scale/no-authority-transfer source gate
```

No later slice begins until the preceding slice's frozen gate is green.

M9A is not a place to invent new semantics: r3 freezes the compiler boundary, package lattice, allocation semantics, fingerprint requirement, error vocabulary, and precedence. Any source fact contradicting those assumptions is a STOP/plan-change event.

---

# 95. M9/M10 boundary

M9 exit is:

```text
Captured Approved Visual Authority
        ↓
Captured Model-Specific Realization Specification
+ exact reference bytes
+ exact required model-weight/runtime identity
        ↓
Verified Executor Conditioning Request
```

M9 can therefore say **which approved references and exact model bytes were requested through which captured execution mechanism**.

M10 begins when SoloRing must answer:

```text
Where is everything?
What is the authoritative geometry/layout?
What should a new camera viewpoint observe?
How do staging, screen direction, camera pose, and spatial relations persist?
```

M9 must not preempt those decisions with ad hoc depth/mesh/pose fields merely because a model would benefit from them.

---

# 96. Final milestone statement

After M9, SoloRing should be able to say, with provenance:

> At Shot capture, this was the approved semantic and visual authority. For this Generation, SoloRing used this exact captured workflow package and RealizationProfile, selected these exact approved reference bytes under one deterministic facet-atomic compiler, applied these exact captured model-specific parameters through these exact logical channels, required these exact content-addressed model-weight bytes and characterized runtime revisions, and captured the complete logical execution request immutably. Changing current references, profiles, packages, or model files cannot rewrite that history; incompatible live model/runtime state fails rather than silently substituting.

It should **not** claim:

> The resulting video bytes are guaranteed identical across arbitrary hardware/runtime changes.

Nor:

> Every arbitrary camera view is spatially identical.

The latter belongs to M10.

---

# 97. Authorization boundary

The r3 review closure freezes the four corrections raised against r2:

1. live model-byte access is executable through the exact §6.4 Settings/root adapter and fails closed when unavailable;
2. no persisted/API nested realization hash exists in schema 1;
3. Stage-0 four-artifact package capture failures map exactly to `WORKFLOW_PACKAGE_INTEGRITY`;
4. readiness preview has a frozen server-owned per-facet/channel response shape sufficient for M9E without client-side rule reconstruction.

It also freezes the four judgment calls: requirement-sensitive preview parity, always-hash model verification, baseline Hunyuan schema-2 v4 package authoring in M9A, and hermetic CI with separate live-deployment evidence.

This document authorizes **planning only**.

The r3 architecture is **frozen as the M9 implementation contract** at the exact bytes/hash of this document. Implementation begins only after explicit implementation authorization.

The published M8 baseline remains immutable.

Publication, M9 tagging, M10 planning/implementation, branch-protection changes, and unrelated housekeeping remain separate authorization boundaries.
