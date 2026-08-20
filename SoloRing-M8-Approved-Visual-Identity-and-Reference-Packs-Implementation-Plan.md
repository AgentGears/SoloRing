# SoloRing M8 — Approved Visual Identity and Reference Packs Implementation Plan

**Plan revision:** r5 freeze candidate  
**Predecessor baseline:** M7 @ `479c3a6b77e37282e0f1e5da34321622e292c1c1`  
**Predecessor tree:** `b34c98d`  
**Predecessor migration:** `0008_narrative_continuity_state`  
**M8 migration:** `0009_m8_visual_identity`

M8 implementation is not authorized until this plan passes the same freeze/source-gate protocol used by the closed M7 milestone. The predecessor baseline above is binding: M8 extends it; M8 does not reinterpret or silently replace M7 contracts.

---

# 0. Architecture Pattern Register Binding

The Architecture Pattern Register is part of the M8 freeze contract. Patterns are classified here as **PRIMARY**, **INHERITED**, or **AUDIT** so implementation and source review can verify the exact architectural obligations rather than relying on implicit alignment.

| Role | APR | M8 binding |
|---|---|---|
| PRIMARY | APR-012 | Shot detail, readiness, visual-pack hashing, and capture use one semantic resolver/builder path. |
| PRIMARY | APR-014 | Current visual state is derived before capture; after ShotRevision capture it is immutable historical fact. |
| PRIMARY | APR-015 | Semantic readiness and visual readiness are explicit preconditions before expensive execution. |
| PRIMARY | APR-020 | M9/execution consumes captured immutable visual inputs, never mutable current authority. |
| PRIMARY | APR-023 | Missing/inconsistent immutable visual provenance fails closed. |
| PRIMARY | APR-030 | Visual revisions, approvals, and capture-dependent writes use authority-preserving transactional fences. |
| PRIMARY | APR-031 | Multi-query semantic/visual reads use one coherent transaction on one connection. |
| PRIMARY | APR-032 | Concurrent identical immutable visual captures converge. |
| PRIMARY | APR-040 | Inspection and final capture derive from the same current-state authority. |
| PRIMARY | APR-050 | Visual Identity UI exposes SoloRing authority; it never becomes authority itself. |
| PRIMARY | APR-051 | Unresolved semantic/visual state is represented honestly; no fabricated readiness or hashes. |
| PRIMARY | APR-060 | Semantic production fact precedes visual realization. |
| PRIMARY | APR-061 | Approved visual identity is explicit, inspectable production authority. |
| INHERITED | APR-003 | Production authority points downward into execution infrastructure. |
| INHERITED | APR-004 | Model/executor churn remains behind stable SoloRing boundaries. |
| INHERITED | APR-013 | Current state and historical state remain isolated. |
| INHERITED | APR-016 | No empty higher-schema alternative is permitted. |
| INHERITED | APR-017 | Corruption never invents UUID/timestamp/row-order tie-breakers. |
| INHERITED | APR-021 | Blob and canonical snapshot hashes identify bytes, not semantic provenance by themselves. |
| INHERITED | APR-022 | Feature realization follows semantic value identity, not transition-row identity. |
| INHERITED | APR-024 | Database provenance relationships remain authority; filesystem layout does not. |
| INHERITED | APR-025 | Exact Rerun is isolated from mutable current-state resolvers. |
| INHERITED | APR-044 | Feature-film scale may increase rows, not per-item query round trips. |
| AUDIT | APR-070 | Semantic source gates precede publication/freeze. |
| AUDIT | APR-071 | Supplied evidence and independently reproduced evidence remain distinct. |
| AUDIT | APR-072 | Race/isolation/scale test names must match the interleavings and conditions they mechanically prove. |
| AUDIT | APR-073 | Closure artifacts must faithfully represent the frozen source tree. |

No APR entry authorizes additional scope beyond this M8 plan. If a pattern conflicts with the frozen predecessor baseline, the predecessor contract remains authoritative until explicitly amended.

Register availability is confirmed against **SoloRing Architecture Pattern Register v1** (2026-08-18): every APR identifier cited in this section exists in that supplied architecture artifact, including APR-003, APR-004, APR-021, APR-024, APR-060, APR-061, APR-070, APR-071, and APR-073. This table is the M8-specific binding instantiation of those register texts; it does not replace the register text.

---

# 0.1 Predecessor Source-Fit Audit

M8 is designed against the frozen M7 source seams below. These seams are part of the freeze contract and must be re-checked against the exact predecessor baseline before implementation begins.

| M7 seam | Frozen predecessor behavior | M8 extension | Required proof |
|---|---|---|---|
| `_snapshot_one_read` | Pins one coherent current semantic read. | M8 visual reads occur downstream of successful M7 semantic readiness, inside the same checked-out connection/read transaction. | No hybrid semantic/visual state under proven writer interleavings. |
| `build_capturable_snapshot` | Builds the canonical capturable M6/M7 snapshot and selects the existing lower schema. | Adds a schema-4 visual block only for a valid non-empty effective visual pack; lower-schema bytes remain unchanged otherwise. | Golden byte/hash fixtures for schemas 1/2/3 and schema-4 base compatibility. |
| `readiness_projection` | Emits the existing two-row M7 readiness matrix. | Preserves both predecessor rows exactly and appends one M8 `visual_continuity` row; no predecessor row is renamed, reordered, or reinterpreted. | Projection fixture plus semantic-blocked visual projection. |
| Fenced ShotRevision write | Persists parent then M6/M7 normalized child projections in frozen order. | Appends M8 normalized visual rows after the predecessor child writes: parent → M6 dependencies → M7 feature states → M7 relation states → M8 visual anchors → M8 visual items. | Source audit plus rollback/atomicity regression. |
| Shot read model | Uses additive server-authoritative readiness fields/issues. | Adds `visual_continuity_ready`, `visual_reference_pack_hash`, and `visual_continuity_issues` without changing existing M7 fields. | API schema regression and frontend fetch-boundary tests. |
| Immutable capture reuse | Existing M7 reuse validates canonical bytes/projections rather than trusting hash identity alone. | Extends fail-closed reuse-integrity validation to VisualAnchorRevision reuse and schema-4 ShotRevision visual projections. | Corruption UPDATE→fail→restore→positive-control reuse loops. |
| Frontend pattern | Server-fed pure presentation panels with narrow client islands and fetch-boundary tests. | VisualFacet/Anchor/Shot panels follow the same pattern; browser code never re-resolves applicability or hashes. | Typecheck, component tests, fetch-boundary tests, production build. |

Source-fit corrections pinned by r4:

* M7A already implements ContinuityFeature supersession via `supersedes_feature_id`, single-successor lineage, and tombstone-inclusive keys. M8 never silently transfers authority across different `feature_id` values, including along a supersession edge.
* `continuity_features.entity_id` is `NOT NULL` in `0008`; every M8 Feature VisualFacet is entity-scoped in this milestone. There is no nullable/non-entity Feature realization branch in M8.
* M8 derives feature-value JSON/hash server-side through M7's existing `canonicalize_value` authority. Clients never author a `(feature_value_json, feature_value_hash)` pair.
* No Asset deletion route and no Blob-GC implementation exist in the predecessor source. M8 retention therefore relies on restrictive provenance FKs and a prohibition on adding future deletion/GC paths without honoring those roots; M8 does not claim that an existing GC implementation already enforces this.

---

## 1. Objective

M8 establishes SoloRing's authoritative visual-continuity layer.

The milestone answers a production problem that semantic continuity alone cannot solve:

> A production fact can say what is true, but feature-film continuity also requires an approved visual definition of what that fact looks like.

Examples:

```text
Semantic authority
"Eva has a fresh cut on the left forehead."

Visual authority
"The cut has this approved placement, shape, scale,
orientation, edge character, color, and surrounding-skin appearance."
```

and:

```text
Semantic authority
"This Shot takes place in the Grand Meridian hotel lobby."

Visual authority
"The lobby has these approved architectural,
material, furnishing, signage, palette, and decor characteristics."
```

M8 introduces approved visual identity without allowing:

* prompt text;
* the first generated result;
* a Comfy workflow;
* a model embedding;
* an IP-Adapter representation;
* a LoRA;
* a filesystem folder;
* a model-specific reference weighting;

to become production authority.

The required authority direction is:

```text
Semantic Production State
        ↓
Stable Visual Concern
        ↓
Approved State-Specific Visual Realization
        ↓
Immutable Shot Capture
        ↓
M9 Model-Specific Realization
        ↓
Executor
```

### Exit criterion

> SoloRing can define persistent visual concerns, curate exact state-specific visual realizations, explicitly approve them, resolve the correct approved reference pack for a Shot, and immutably capture that authority without depending on any particular generation model.

---

# 2. Milestone Boundary

## 2.1 Included

M8 implements:

* `VisualFacet` as the stable production concern whose appearance may need control;
* entity-scoped VisualFacets;
* ContinuityFeature-scoped VisualFacets;
* required/optional facet policy;
* feature-value policy overrides;
* explicit `not_applicable` feature-value policy;
* state-specific `VisualAnchor` realizations;
* mutable VisualAnchor working reference sets;
* immutable VisualAnchorRevisions;
* immutable VisualAnchorRevision item provenance rows;
* explicit visual-anchor approval;
* explicit unapproval;
* active semantic uniqueness;
* exact M7 `value_hash` consumption;
* mandatory EntityRevision visual context for every Feature realization under the `0008` baseline;
* primary/supporting/detail/context reference roles;
* one canonical primary reference per approvable realization;
* free-form bounded view labels;
* deterministic item ordering;
* deterministic canonical serialization;
* canonical revision hashes;
* concurrent identical revision convergence;
* coherent revision capture under concurrent working edits;
* current visual-reference resolution;
* set-oriented/batched resolver queries;
* Shot-level visual continuity readiness;
* honest unresolved-state reporting;
* non-empty visual reference pack hashing;
* immutable visual-reference capture into ShotRevision schema 4;
* normalized immutable ShotRevision visual-provenance rows;
* historical/current-state isolation;
* Exact Rerun isolation from current visual state;
* promotion of existing Assets, including generated output Assets, into visual-authority working sets;
* Blob/Asset retention through immutable visual provenance;
* VisualFacet, VisualAnchor, revision, and historical provenance inspection;
* Visual Identity UI;
* Shot visual-continuity inspector;
* query-shape and feature-film-scale gates;
* downgrade-safety preflight;
* final source-gate verification.

## 2.2 Explicitly excluded

M8 does **not** implement:

* IP-Adapter;
* reference-attention implementation;
* ControlNet;
* InstantID;
* PuLID;
* face embeddings;
* CLIP embeddings as production identity;
* LoRA training;
* character LoRAs;
* model-specific reference weighting;
* Comfy node mappings for visual authority;
* executor-specific reference materialization;
* automatic reference selection by an LLM;
* automatic visual approval;
* visual similarity scoring as authority;
* per-model reference optimization;
* facial tracking;
* roto;
* masks;
* compositing;
* paint fixes;
* 3D reconstruction;
* meshes;
* NeRF;
* Gaussian splats;
* depth reconstruction;
* camera solving;
* arbitrary-view spatial authority;
* editorial;
* grading;
* audio;
* cross-project/franchise Asset sharing;
* visual-authority caching/materialized resolver tables;
* relationship-specific composite visual authority.

The boundary remains:

```text
M8
What must remain visually controlled,
and what approved reference material defines it?

M9
How does a particular model realize that approved authority?

M10
How are geometry, world layout, camera relation,
and arbitrary-view spatial continuity constrained?
```

M8 may materially improve location continuity through approved location references, but it does not claim that 2D reference packs guarantee spatially correct arbitrary viewpoints.

---

# 3. Governing Architecture

M8 preserves SoloRing's authority rule:

```text
SoloRing production state
        ↓
immutable captured state
        ↓
execution-specific materialization
        ↓
executor
```

Never:

```text
executor representation
        ↓
defines SoloRing production truth
```

M8 extends the production graph as follows:

```text
Entity / ContinuityFeature
        ↓
VisualFacet
stable production concern
        ↓
VisualAnchor
exact semantic/design-state binding
        ↓
mutable working reference items
        ↓
VisualAnchorRevision
immutable approved-candidate pack
        ↓
explicit approval
        ↓
Approved VisualAnchorRevision
        ↓
VisualReferencePack resolver
        ↓
current inspection + readiness
        ↓
ShotRevision schema 4
        ↓
M9 model-specific realization
```

The existing Blob/Asset distinction remains authoritative:

```text
Blob
= immutable physical byte identity

Asset
= provenance identity
```

M8 never creates a second media-storage authority.

---

# 4. Core Semantic Distinctions

## 4.1 Semantic production fact

Defines what is narratively or physically true.

Example:

```text
Feature:
Eva.forehead_injury

Effective value:
fresh-left-cut
```

Semantic truth remains authoritative even when no visual realization exists.

## 4.2 VisualFacet

A stable SoloRing production concern describing **what aspect of appearance must be controlled**.

Examples:

```text
Eva / identity
Eva / face
Eva / hair
Eva / wardrobe

Grand Meridian Lobby / identity
Grand Meridian Lobby / signage
Grand Meridian Lobby / material-palette

Eva.forehead_injury / cut-realization
```

A VisualFacet is stable across state-specific realizations.

It is not a reference image.

It is not a model conditioning object.

It answers:

> Which visual concern matters?

## 4.3 VisualAnchor

A state-specific realization binding for one VisualFacet.

Examples:

```text
Facet:
Eva / face

Anchor:
Eva EntityRevision 3 / face
```

and:

```text
Facet:
Eva.forehead_injury / cut-realization

Anchor:
feature value = fresh-left-cut
visual context = Eva EntityRevision 12
```

A VisualAnchor answers:

> For this exact semantic/design state, which visual realization is being curated?

## 4.4 VisualAnchorRevision

An immutable canonical snapshot of one VisualAnchor's curated reference pack.

It answers:

> What exact reference material defined this realization at this revision?

## 4.5 Approved VisualAnchorRevision

The immutable VisualAnchorRevision currently designated as authority for that exact state-specific VisualAnchor.

Approval is explicit.

## 4.6 VisualReferencePack

The deterministic collection of approved state-specific visual realizations applicable to one current Shot state.

Before Shot capture it is derived current state.

After Shot capture it is historical fact.

---

# 5. Critical Feature-Film Rule

A generated appearance is never authoritative merely because it exists.

Example:

```text
Generation 41
↓
Take approved
↓
output Asset exists
```

This does **not** mean:

```text
all future Shots must reuse Generation 41's appearance
```

Authority promotion is deliberately separate:

```text
approved Take
↓
output Asset
↓
user deliberately adds Asset to a VisualAnchor working set
↓
VisualAnchorRevision captured
↓
VisualAnchorRevision explicitly approved
↓
that revision becomes current visual authority
```

The same rule applies to:

* faces;
* bodies;
* hair;
* wardrobe;
* hotel interiors;
* props;
* scars;
* dirt;
* wounds;
* damage;
* signage;
* makeup;
* any other controlled visual facet.

Generation never performs authority promotion automatically.

---

# 6. Why VisualFacet Exists

A visual requirement must survive changes in the exact state being realized.

Without VisualFacet, this unsafe sequence is possible:

```text
Eva EntityRevision 3 / face
required + approved
        ↓
Eva changes to EntityRevision 4
        ↓
rev3 face anchor no longer applies
        ↓
no rev4 face anchor exists
        ↓
no applicable required anchor exists
        ↓
readiness incorrectly becomes true
```

VisualFacet closes this hole:

```text
VisualFacet:
Eva / face
requirement = required
        ↓
current EntityRevision = 4
        ↓
no matching approved VisualAnchor for rev4
        ↓
visual continuity NOT ready
```

The same rule applies to ContinuityFeature visual realization.

---

# 7. VisualFacet Target Semantics

A VisualFacet targets stable semantic identity.

M8 supports two target kinds.

## 7.1 Entity VisualFacet

Bind to the stable Entity identity, not an EntityRevision.

Example:

```text
Entity:
Eva

VisualFacet:
face
requirement = required
```

State-specific VisualAnchors then bind the facet to exact EntityRevisions:

```text
Eva rev3 / face
Eva rev4 / face
Eva rev7 / face
```

## 7.2 ContinuityFeature VisualFacet

Bind to stable ContinuityFeature identity.

Example:

```text
ContinuityFeature:
Eva.forehead_injury

VisualFacet:
cut-realization
requirement = required
```

State-specific VisualAnchors then bind to exact canonical feature values, with entity-revision visual context where required.

---

# 8. `facet_key`

Every VisualFacet has an explicit stable machine key.

Examples:

```text
identity
face
hair
wardrobe
lobby-overview
reception-desk
signage
material-palette
cut-realization
damage-detail
```

Use:

```text
^[a-z0-9][a-z0-9._-]{0,127}$
```

Rules:

* 1–128 characters;
* lowercase ASCII;
* no whitespace;
* immutable after creation;
* unique within the facet target while active.

The `facet_key` grammar is intentionally **not** the M7 ContinuityFeature-key grammar. A VisualFacet key names a visual-production concern and permits `.`/`_`/`-` under the regex above; this asymmetry is deliberate and must not be normalized away during source review.

Human-readable naming belongs in `label` and `description`.

---

# 9. VisualFacet Requirement Policy

`VisualFacet.requirement` is:

```text
required
optional
```

It belongs to the stable visual concern, not to the state-specific VisualAnchor.

## 9.1 Required entity facet

If an Entity VisualFacet is required and the EntityRevision is part of the Shot's resolved semantic state:

```text
matching active VisualAnchor missing
→ not ready
```

```text
matching VisualAnchor exists but has no approved revision
→ not ready
```

```text
approved revision exists and provenance is valid
→ satisfied
```

## 9.2 Optional entity facet

If no matching approved realization exists:

```text
do not block readiness
```

If an approved realization exists:

```text
include it in the VisualReferencePack
```

## 9.3 Feature facet default policy

For a feature-targeted facet, the facet-level requirement is the default policy for effective feature values.

However, a feature value may explicitly override that policy.

This is necessary for cases such as:

```text
forehead_injury = none
```

where the production may declare:

```text
cut-realization
→ not_applicable for value "none"
```

while still requiring visual realization for:

```text
fresh
healing
scarred
```

---

# 10. Feature-Value Policy Overrides

Feature VisualFacets support explicit value-policy overrides.

Policy values:

```text
required
optional
not_applicable
```

Resolution:

```text
exact value-policy override exists?
├─ yes → use override
└─ no  → use VisualFacet.requirement
```

Feature absent/cleared with no effective semantic value:

```text
facet not applicable
```

`not_applicable` means:

```text
no VisualAnchor required
no approved realization included
no readiness failure
```

This produces fail-safe behavior for new values:

```text
facet requirement = required
new previously unseen effective value appears
no override exists
        ↓
required by default
        ↓
missing realization blocks readiness
```

---

# 11. M7 Feature Identity and Value-Hash Authority

M8 consumes M7's existing canonical feature-value authority. It does **not** accept or invent an independent value/hash identity.

The authoring flow is:

```text
user selects ContinuityFeature
        ↓
server enumerates/validates a legal value under the current M7 Feature schema
        ↓
M7 `canonicalize_value`
        ↓
exact canonical feature_value_json
+
exact feature_value_hash
        ↓
M8 persists the server-derived pair
```

For enum-style features, the UI selects one of the server-provided legal members. For other frozen M7 value types, request data is validated through the same M7 value-authority primitive before any M8 row is written.

Clients never submit an authoritative:

```text
(feature_value_json, feature_value_hash)
```

pair. Any hash or JSON supplied merely for display/concurrency diagnostics is ignored as authority and must be verified against the server-derived M7 result.

Feature-targeted VisualAnchors and feature-value policies persist:

```text
feature_value_json
feature_value_hash
```

as the exact server-derived M7 canonical identity.

The integrity condition remains:

```text
SHA-256(exact bytes emitted by M7 canonicalize_value)
==
feature_value_hash
```

M8 may call the same shared M7 primitive to verify stored integrity, but it must never maintain a second canonicalizer or hash implementation.

---

# 12. Existing M7 Feature Supersession Contract

M7A already implements ContinuityFeature supersession through:

```text
supersedes_feature_id
single-successor lineage
tombstone-inclusive feature keys
```

M8 does **not** interpret a supersession edge as permission to transfer visual authority.

Required rule:

> Different `feature_id` means different M8 semantic target identity, even when the newer feature explicitly supersedes the older feature.

Therefore:

```text
old feature_id
→ VisualFacet / VisualAnchor authority

new superseding feature_id
→ no inherited M8 authority by default
```

Production may explicitly create/rebind the corresponding VisualFacet and state-specific realizations for the successor Feature. Existing M8 history is never rewritten and current authority never migrates silently.

---

# 13. Feature Realization and EntityRevision Context

A feature visual realization may depict the owning Entity's exact current design.

Because every ContinuityFeature is entity-scoped under predecessor `0008`, every state-specific Feature VisualAnchor identity includes:

```text
feature_id
+
feature_value_hash
+
visual_context_entity_revision_id
```

Example:

```text
Eva rev12
forehead_cut = fresh
```

is not automatically the same visual realization as:

```text
Eva rev13
forehead_cut = fresh
```

Even though the semantic injury value is identical.

Required behavior:

```text
same feature value
+
different owning EntityRevision
→ distinct VisualAnchor state binding by default
```

If production intentionally wants to reuse the same visual reference pack across EntityRevisions, that reuse is explicit:

```text
copy/rebind working references
↓
capture new VisualAnchorRevision
↓
approve for the new state binding
```

No accidental inheritance.

M8 has no non-entity-scoped Feature branch. Under predecessor migration `0008`, `continuity_features.entity_id` is `NOT NULL`, so every Feature realization requires an exact `visual_context_entity_revision_id`. Supporting a future project-scoped/non-entity Feature would require an explicit schema/contract revision and new tests; it is not a dormant M8 branch.

---

# 14. VisualFacet Schema

Conceptual schema:

```text
visual_facets

id                     UUID PK
project_id             UUID NOT NULL

target_kind            TEXT NOT NULL
entity_id               UUID NULL
feature_id              UUID NULL

facet_key               TEXT NOT NULL
label                   TEXT NULL
description             TEXT NULL
requirement             TEXT NOT NULL

created_at              TEXT NOT NULL
updated_at              TEXT NOT NULL
deleted_at              TEXT NULL
```

`target_kind`:

```text
entity
feature
```

`requirement`:

```text
required
optional
```

Row-shape CHECK:

```text
target_kind = entity
→ entity_id NOT NULL
→ feature_id NULL
```

```text
target_kind = feature
→ feature_id NOT NULL
→ entity_id NULL
```

Database CHECKs enforce the local NULL shape.

Application-level fenced validation additionally verifies:

* target exists;
* target belongs to the same Project;
* target is semantically valid for the declared kind;
* target is not invalid/deleted under the owning M6/M7 contract.

---

# 15. VisualFacet Active Uniqueness

Prevent duplicate active stable facets.

Entity facets:

```text
UNIQUE ACTIVE (
    entity_id,
    facet_key
)
WHERE target_kind = 'entity'
  AND deleted_at IS NULL
```

Feature facets:

```text
UNIQUE ACTIVE (
    feature_id,
    facet_key
)
WHERE target_kind = 'feature'
  AND deleted_at IS NULL
```

Do not resolve duplicate facets through tie-breaking.

Legal state makes them impossible.

Corrupted duplicate state fails closed.

---

# 16. Feature Value Policy Schema

Conceptual schema:

```text
visual_facet_value_policies

visual_facet_id         UUID NOT NULL
feature_value_hash      TEXT NOT NULL
feature_value_json      TEXT NOT NULL
policy                  TEXT NOT NULL
created_at              TEXT NOT NULL

PRIMARY KEY(
    visual_facet_id,
    feature_value_hash
)
```

Policy:

```text
required
optional
not_applicable
```

Only feature-targeted VisualFacets may own these rows.

Authoring requests identify the target Feature value in its M7-native typed form (for example, by selecting an enumerated member). The server derives `feature_value_json` and `feature_value_hash` through M7 `canonicalize_value`; clients never choose either persisted value directly.

The server validates:

```text
server-derived feature_value_hash belongs to visual_facet.feature_id
```

and verifies the exact canonical M7 value/hash pair before persistence.

Updates use atomic full-set replacement:

```text
PUT /visual-facets/{id}/value-policies
```

Invalid proposed sets roll back entirely.

---

# 17. VisualAnchor Schema

Conceptual schema:

```text
visual_anchors

id                               UUID PK
visual_facet_id                  UUID NOT NULL

entity_revision_id               UUID NULL
feature_value_hash               TEXT NULL
feature_value_json               TEXT NULL
visual_context_entity_revision_id UUID NULL

approved_revision_id             UUID NULL

created_at                       TEXT NOT NULL
updated_at                       TEXT NOT NULL
deleted_at                       TEXT NULL
```

The owning VisualFacet determines the binding shape.

Entity VisualFacet:

```text
entity_revision_id NOT NULL
feature_value_hash NULL
feature_value_json NULL
visual_context_entity_revision_id NULL
```

Feature VisualFacet:

```text
entity_revision_id NULL
feature_value_hash NOT NULL
feature_value_json NOT NULL
visual_context_entity_revision_id NOT NULL
```

Every M8 Feature realization is entity-scoped because predecessor `0008` requires `continuity_features.entity_id NOT NULL`.

These semantic binding fields are immutable after creation.

A VisualAnchor has no mutable label/description identity of its own; presentation metadata belongs to the stable VisualFacet.

---

# 18. VisualAnchor Active Uniqueness

An exact state binding may have only one active VisualAnchor per VisualFacet.

Entity realization:

```text
UNIQUE ACTIVE (
    visual_facet_id,
    entity_revision_id
)
WHERE entity_revision_id IS NOT NULL
  AND deleted_at IS NULL
```

Feature realization:

```text
UNIQUE ACTIVE (
    visual_facet_id,
    feature_value_hash,
    visual_context_entity_revision_id
)
WHERE feature_value_hash IS NOT NULL
  AND visual_context_entity_revision_id IS NOT NULL
  AND deleted_at IS NULL
```

There is no non-entity feature uniqueness branch in M8.

No runtime UUID/timestamp tie-breaker is permitted.

---

# 19. VisualAnchor Working Items

Working membership is mutable.

Conceptual schema:

```text
visual_anchor_items

visual_anchor_id        UUID NOT NULL
asset_id                UUID NOT NULL

role                    TEXT NOT NULL
view_key                TEXT NULL
position                INTEGER NOT NULL

created_at              TEXT NOT NULL

PRIMARY KEY(
    visual_anchor_id,
    asset_id
)

UNIQUE(
    visual_anchor_id,
    position
)
```

Positions are:

* zero-based;
* contiguous;
* global across the working reference pack;
* server assigned.

The same Asset may appear only once in one VisualAnchor working set.

The same Asset may appear in different VisualAnchors in the same Project.

---

# 20. Item Roles

Closed M8 roles:

```text
primary
supporting
detail
context
```

Meaning:

```text
primary
→ canonical human-facing hero reference for this realization

supporting
→ additional views proving the same identity

detail
→ close detail evidence

context
→ wider contextual evidence
```

M8 authority requires exactly one canonical primary in every captured VisualAnchorRevision.

This does **not** mean M9 must weight only one image most strongly.

M9 may use supporting images with equal or greater numerical conditioning weight if a specific model requires it.

M8's `primary` is a production-authority concept, not a model-weight concept.

---

# 21. Working Primary Semantics

Working state may temporarily contain:

```text
0 primary items
```

but never:

```text
>1 primary items
```

Therefore:

```text
PUT working set with two primary items
→ reject immediately
```

A working set with zero primary items is valid draft state but cannot be captured as a VisualAnchorRevision.

Revision capture requires:

```text
at least one item
exactly one primary
```

Approval re-validates immutable revision integrity and fails closed if corruption violates that invariant.

---

# 22. `view_key`

Optional human/production metadata.

Examples:

```text
front
left-profile
right-profile
three-quarter-left
rear
wide
reception-facing
elevator-facing
north-wall
close-detail
```

Rules:

```text
NULL
→ NULL

blank/whitespace-only
→ NULL

non-empty
→ trim and persist
```

Maximum:

```text
64 characters
```

No global enum.

No model meaning.

No automatic interpretation by M8.

Recommended vocabularies may later be provided by UI guidance without becoming database authority.

---

# 23. Atomic Working-Set Replacement

Endpoint:

```text
PUT /visual-anchors/{id}/items
```

The client submits desired membership/order.

The server:

1. validates the complete proposed set;
2. verifies every Asset belongs to the same Project;
3. rejects duplicate Asset IDs;
4. rejects >1 primary;
5. normalizes `view_key`;
6. assigns contiguous positions `0..N-1` in submitted order;
7. replaces the working set atomically;
8. updates `visual_anchors.updated_at` with database time.

Invalid replacement:

```text
no partial mutation
```

Full-set PUT remains the only M8 working-item mutation API.

Item-level PATCH is deferred until actual production scale demonstrates a need.

---

# 24. Asset Provenance Rule

VisualAnchor items reference existing:

```text
Asset
+
Blob
```

They do not copy media bytes.

Generated output promotion:

```text
Take
→ output Asset
→ existing Blob
→ VisualAnchor working item
```

The Asset remains:

```text
kind = output
```

Never rewrite provenance to make it appear to be an uploaded reference.

Visual authority is the VisualAnchor approval decision, not a mutation of Asset provenance.

---

# 25. Cross-Project Safety

All current-state associations must belong to one Project.

Reject:

```text
Project A VisualFacet
+
Project B Entity
```

Reject:

```text
Project A VisualFacet
+
Project B ContinuityFeature
```

Reject:

```text
Project A VisualAnchor
+
Project B EntityRevision
```

Reject:

```text
Project A VisualAnchor
+
Project B visual-context EntityRevision
```

Reject:

```text
Project A VisualAnchor
+
Project B Asset
```

Use stable domain errors.

Database FKs prove row existence.

Application-level fenced validation proves Project and semantic ownership relationships.

---

# 26. VisualAnchorRevision Schema

Conceptual schema:

```text
visual_anchor_revisions

id                   UUID PK
visual_anchor_id     UUID NOT NULL
revision_number      INTEGER NOT NULL

snapshot_json        TEXT NOT NULL
snapshot_hash        TEXT NOT NULL

created_at           TEXT NOT NULL

UNIQUE(
    visual_anchor_id,
    revision_number
)

UNIQUE(
    visual_anchor_id,
    snapshot_hash
)
```

Revision numbers are per VisualAnchor and start at 1.

Revisions are append-only and non-deletable in M8.

---

# 27. Immutable VisualAnchorRevision Item Rows

Canonical revision bytes remain the hash authority, but immutable normalized item rows are also created for:

* FK-backed Asset/Blob retention;
* provenance inspection;
* queryability;
* corruption cross-checking.

Conceptual schema:

```text
visual_anchor_revision_items

visual_anchor_revision_id UUID NOT NULL
position                  INTEGER NOT NULL

asset_id                  UUID NOT NULL
blob_hash                 TEXT NOT NULL
role                      TEXT NOT NULL
view_key                  TEXT NULL

PRIMARY KEY(
    visual_anchor_revision_id,
    position
)

UNIQUE(
    visual_anchor_revision_id,
    asset_id
)
```

Foreign keys use restrictive deletion semantics.

These rows are immutable.

They are written from the same frozen in-memory canonical value used to produce `snapshot_json`.

They never become an independent second semantic interpretation.

---

# 28. Canonical VisualAnchorRevision Snapshot

Canonical shape:

```json
{
  "schema_version": 1,
  "visual_facet": {
    "visual_facet_id": "...",
    "facet_key": "cut-realization",
    "target": {
      "kind": "feature",
      "feature_id": "..."
    }
  },
  "state_binding": {
    "kind": "feature_value",
    "feature_value_hash": "...",
    "feature_value_json": "...",
    "visual_context_entity_revision_id": "..."
  },
  "items": [
    {
      "asset_id": "...",
      "blob_hash": "...",
      "role": "primary",
      "view_key": "front-detail",
      "position": 0
    },
    {
      "asset_id": "...",
      "blob_hash": "...",
      "role": "supporting",
      "view_key": "three-quarter-left",
      "position": 1
    }
  ]
}
```

Entity realization uses:

```json
{
  "state_binding": {
    "kind": "entity_revision",
    "entity_revision_id": "..."
  }
}
```

Do not include:

* `approved_revision_id`;
* requirement policy;
* timestamps;
* working-row IDs;
* original filenames;
* local paths;
* executor paths;
* model names;
* embeddings;
* LoRAs;
* Comfy node IDs;
* display-only labels/descriptions.

Requirement is capture/readiness policy, not visual realization identity.

---

# 29. Canonical Ordering

Working order and canonical order are the same.

Items are canonicalized by:

```text
position
asset_id
```

`position` is authoritative global pack order.

`asset_id` is a final corruption-safe deterministic tiebreaker only; legal state already guarantees unique positions.

Do not reorder by role.

Role remains item metadata.

This prevents UI order and canonical order from diverging.

---

# 30. Canonical Serialization

Use the exact SoloRing canonical JSON serializer already used by hashed immutable artifacts:

```python
def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
```

For VisualAnchorRevision:

```text
snapshot_bytes
=
canonical_json_bytes(snapshot)
```

```text
snapshot_json
=
snapshot_bytes.decode("utf-8")
```

```text
snapshot_hash
=
SHA-256(snapshot_bytes)
```

The exact stored bytes are the exact hashed bytes.

The same canonical function is used by:

* VisualAnchorRevision capture;
* working-vs-approved comparison;
* VisualReferencePack hashing;
* ShotRevision schema-4 capture.

No alternative serializer is permitted.

---

# 31. VisualAnchorRevision Capture — Coherent Two-Phase Contract

Working edits may race revision capture.

A captured revision must represent one state that actually existed atomically.

## 31.1 Read phase

Use:

```text
one checked-out connection
one explicit coherent read transaction
```

Read:

* VisualFacet;
* VisualAnchor;
* complete working item set;
* Assets;
* Blob rows;
* semantic target/context identity.

Validate:

* current rows are active/valid;
* same-Project invariants;
* at least one item;
* exactly one primary;
* positions contiguous;
* Asset/Blob provenance valid;
* referenced Blob files exist;
* feature hash/value integrity valid.

Freeze one immutable in-memory snapshot value.

Close the read transaction.

## 31.2 Canonicalize/hash phase

Outside a DB write transaction:

```text
canonicalize frozen value
↓
compute SHA-256
```

## 31.3 Write phase

Use:

```text
one checked-out connection
BEGIN IMMEDIATE
```

Then:

```text
lookup by visual_anchor_id + snapshot_hash
↓
existing?
├─ yes
│   ↓
│   validate reuse integrity
│   ↓
│   exact stored snapshot_json bytes == recomputed canonical bytes?
│   AND
│   normalized visual_anchor_revision_items exactly project the recomputed snapshot?
│       ├─ yes → reuse existing revision
│       └─ no  → INTERNAL_INVARIANT_VIOLATION
│                 no repair
│                 no recapture
│                 no replacement row
└─ no
    ↓
    allocate revision_number
    ↓
    insert VisualAnchorRevision
    ↓
    insert immutable revision-item rows
    ↓
    COMMIT
```

Reuse-by-hash is therefore not trust-by-hash. The existing immutable row must prove that its stored canonical bytes and normalized projection are exactly the same artifact the caller just recomputed.

Normalized-item equality is exact and ordered. It includes at least:

```text
item count
position
asset_id
blob_hash
role
view_key
```

Any mismatch is corruption and fails closed with the existing exact code:

```text
INTERNAL_INVARIANT_VIOLATION
```

Concurrent identical captures converge on one revision.

Concurrent before/after working states may create distinct revisions.

No capture may contain a hybrid state that never existed.

### 31.4 Required reuse-integrity regression

The M8B gate includes a corruption loop with a positive control:

```text
capture revision R
↓
identical recapture
→ reuses R
↓
direct SQL UPDATE corrupts R.snapshot_json
   or one normalized revision-item field
↓
identical recapture
→ INTERNAL_INVARIANT_VIOLATION
→ no new revision
→ no repair
↓
restore the exact original DB value
↓
identical recapture
→ reuses R again
```

Test setup/teardown must restore the database explicitly so the positive control proves reuse behavior rather than merely observing a permanently corrupted fixture.

---

# 32. Revision-Number Allocation

Per VisualAnchor:

```text
COALESCE(MAX(revision_number), 0) + 1
```

inside the same write transaction.

Two uniqueness dimensions:

```text
(visual_anchor_id, revision_number)
(visual_anchor_id, snapshot_hash)
```

Use bounded conflict-aware retry consistent with ShotRevision precedent.

Raw database integrity exceptions must not escape the service boundary.

---

# 33. Working vs Approved Visual State

VisualAnchor detail returns:

```text
working_snapshot_hash
approved_snapshot_hash
working_state_differs_from_approved
```

Rules:

```text
working set not capturable
→ working_snapshot_hash = NULL
```

Examples of non-capturable working state:

* no items;
* zero primary;
* invalid Asset/Blob provenance.

The frontend never computes these hashes independently.

The same canonical builder used by revision capture produces the working hash.

---

# 34. Approval Semantics

Approval is explicit.

Endpoint:

```text
POST /visual-anchor-revisions/{id}/approve
```

Request includes:

```json
{
  "expected_approved_revision_id": "... or null"
}
```

Approval uses:

```text
one checked-out connection
BEGIN IMMEDIATE
```

Transaction:

```text
verify VisualAnchor active
↓
verify revision belongs to VisualAnchor
↓
verify immutable revision snapshot/hash integrity
↓
verify normalized revision items match snapshot
↓
verify current approved pointer
↓
revision already approved?
├─ yes → idempotent 200
└─ no
    ↓
    expected pointer matches current?
    ├─ no → 409 approval conflict
    └─ yes
        ↓
        set approved_revision_id
        updated_at = db_now
        COMMIT
```

Approval never modifies working items.

Approval never modifies the revision.

---

# 35. Unapproval

Production must be able to revoke current visual authority without immediately supplying a replacement.

This is a deliberate asymmetry with the M6 entity-approval contract: M6-F5 forbids entity unapproval, while M8 visual unapproval is allowed because withdrawing a visual realization fails current visual readiness closed rather than erasing semantic Entity authority. Historical ShotRevisions remain unaffected.

Endpoint:

```text
POST /visual-anchors/{id}/unapprove
```

Request:

```json
{
  "expected_approved_revision_id": "..."
}
```

Use `BEGIN IMMEDIATE`.

Rules:

```text
approved_revision_id already NULL
→ idempotent 200
```

```text
expected pointer mismatch
→ 409
```

```text
success
→ approved_revision_id = NULL
→ updated_at = db_now
```

If the owning VisualFacet is required for current Shots, those Shots become not ready.

Historical ShotRevisions remain unchanged.

---

# 36. Editing After Approval

Approval never freezes mutable working state.

Example:

```text
approved revision 4
        ↓
user adds better side view
        ↓
working state differs
        ↓
revision 4 remains authority
        ↓
user captures revision 5
        ↓
revision 5 is not authority yet
        ↓
explicit approval
        ↓
revision 5 becomes current authority
```

Historical uses of revision 4 remain unchanged.

---

# 37. VisualFacet Mutation Boundary

Immutable after creation:

```text
project_id
target_kind
entity_id
feature_id
facet_key
```

PATCH may mutate only:

```text
label
description
requirement
```

Requirement change is a production-policy mutation.

Use a short write transaction with database time.

Concurrent requirement changes versus Shot capture are safe because Shot current-state resolution reads requirement policy inside the same coherent read transaction as semantic state and visual authority.

A capture observes one complete before-state or after-state.

---

# 38. VisualFacet Deletion

VisualFacet uses soft deletion.

Deletion removes the stable visual concern from **current** resolution only.

It never deletes:

* VisualAnchors;
* VisualAnchorRevisions;
* immutable revision items;
* historical ShotRevision visual state.

Safety rules:

```text
facet requirement = required
→ DELETE rejected
→ first explicitly change requirement to optional
```

```text
active VisualAnchors remain
→ DELETE rejected
→ anchors must first be unapproved/deleted explicitly
```

This makes removal of a production requirement deliberate rather than accidental.

No restore endpoint in M8.

---

# 39. VisualAnchor Deletion

VisualAnchor uses soft deletion.

Rules:

```text
approved_revision_id IS NOT NULL
→ DELETE rejected
→ explicit unapprove required first
```

After deletion:

* excluded from current resolution;
* working items remain stored;
* immutable revisions remain stored;
* historical ShotRevisions remain unchanged.

For a required VisualFacet, deleting the only realization for the current state causes readiness to fail.

No automatic facet deletion.

---

# 40. Asset and Blob Retention

Immutable visual authority must not rot.

Required invariant:

> Any Asset/Blob referenced by an immutable VisualAnchorRevision or captured ShotRevision visual state is a retention root.

The predecessor source currently has **no Asset deletion route and no Blob-GC implementation**. M8 therefore does not claim to extend a collector that already exists. Retention is enforced structurally now and constrains any future deletion/GC implementation.

Required current mechanism:

* VisualAnchorRevision item rows use restrictive FKs to Asset and Blob;
* ShotRevision visual provenance rows use restrictive FKs to Asset and Blob;
* direct hard deletion of a referenced Asset/Blob is rejected by the FK graph;
* no M8 API introduces Asset or Blob deletion;
* missing physical Blob bytes are corruption, not ordinary absence.

Future-path rule:

```text
any future Asset delete service
or Blob GC implementation
        ↓
must treat immutable M8 provenance references as live roots
        ↓
may never remove referenced authority bytes/provenance
```

If Assets later gain soft deletion, historical loaders must remain capable of resolving their captured provenance. A soft-delete filter may affect current browsing but must not erase immutable historical lookup.

---

# 41. Generated Output Promotion

M8 explicitly supports:

```text
generate candidate
↓
approve Take
↓
inspect output
↓
decide an aspect should become reusable canon
↓
add output Asset to VisualAnchor working set
↓
capture VisualAnchorRevision
↓
approve revision
```

No dedicated provenance rewrite occurs.

The output Asset remains an output Asset.

No automatic metadata is needed beyond existing Asset/Take/Generation provenance.

The UI may suggest likely VisualFacets based on historical Shot dependencies, but that suggestion has no authority until the user explicitly chooses the target and completes revision approval.

---

# 42. Current Visual Reference Resolver

M8 introduces one deterministic current-state resolver, but it is explicitly **downstream of the frozen M7 semantic resolver/readiness gate**. It is not a peer resolver that can construct partial visual authority when semantic state is unresolved.

Conceptual API:

```python
resolve_visual_reference_pack(
    semantic_resolution: M7SemanticResolution,
    *,
    conn,
) -> VisualResolutionResult
```

The public Shot/readiness path may still accept `shot_id`, but internally `_snapshot_one_read` first produces the coherent M7 semantic result and only then calls the M8 visual resolver with that already-pinned semantic state.

Required ordering:

```text
_snapshot_one_read
        ↓
existing M7 narrative + continuity resolution/readiness
        ↓
semantic ready?
├─ no
│   ↓
│   DO NOT resolve partial Feature-facet visual state
│   visual_continuity_ready = false
│   visual_reference_pack_hash = NULL
│   effective visual pack = NULL
│   surface the existing semantic blocker(s) honestly
│
└─ yes
    ↓
    current VisualFacets
    + feature-value policies
    + exact state-specific VisualAnchors
    + current approved VisualAnchorRevisions
    ↓
    M8 VisualResolutionResult
```

Semantic blockers include the predecessor M7 causes such as:

```text
NARRATIVE_CONTEXT_REQUIRED
CONTINUITY_RELATION_ENDPOINT_REQUIRED
```

M8 does not wrap these in near-duplicate visual error codes.

A semantically ready resolver output contains:

```text
visual_continuity_ready
blocking M8 issues
resolved facet statuses
canonical effective VisualReferencePack or NULL
visual_reference_pack_hash or NULL
```

---

# 43. One Resolver / One Builder Rule

These operations must call the exact same semantic implementation:

```text
Shot detail readiness
Shot visual inspector
VisualReferencePack hash
ShotRevision capture
```

Required conceptual path:

```text
authoritative current semantic inputs
        ↓
one deterministic M8 resolver
        ↓
one canonical VisualResolutionResult
        ↓
├── readiness projection
├── inspector projection
├── effective pack hash
└── ShotRevision capture input
```

Forbidden:

```text
API resolver
+
separate capture resolver
```

The frontend never reproduces applicability or hash logic.

---

# 44. Coherent Current-State Read

Semantic readiness and visual readiness are one composed current-state interpretation.

Use:

```text
one checked-out connection
one explicit read transaction
one `_snapshot_one_read`-style coherent unit
```

The exact ordering inside that unit is:

```text
1. pin/read M7 narrative + semantic state
2. evaluate existing M7 readiness
3. if M7 is not ready: project M8 as blocked; perform no partial visual realization
4. if M7 is ready: resolve VisualFacets/policies/anchors/approvals from the same pinned DB snapshot
5. produce the combined readiness projection + capturable current state
```

It must not combine:

```text
Entity state at moment A
+
Feature state at moment B
+
VisualFacet requirement at moment C
+
anchor approval at moment D
```

into one canonical result.

A concurrent writer may commit before the snapshot is established or after it is established. The reader must observe one complete before-state or one complete after-state according to the proven SQLite snapshot interleaving; it may never observe a hybrid.

---

# 45. Entity Facet Applicability

For each resolved EntityRevision dependency:

```text
find active VisualFacets targeting the stable owning Entity
```

For each facet:

```text
find active VisualAnchor where
visual_facet_id = facet.id
AND entity_revision_id = resolved EntityRevision
```

Required facet:

```text
anchor missing
→ VISUAL_REALIZATION_REQUIRED
```

```text
anchor exists, approved_revision_id NULL
→ VISUAL_ANCHOR_APPROVAL_REQUIRED
```

Optional facet:

```text
anchor missing or unapproved
→ omit from effective pack
→ no blocking issue
```

Approved applicable anchors enter the effective pack after provenance validation.

---

# 46. Feature Facet Applicability

For each resolved effective ContinuityFeature value:

```text
find active VisualFacets targeting feature_id
```

For each facet:

```text
resolve policy:
value override if present
else facet.requirement
```

`not_applicable`:

```text
no anchor lookup required
```

`required` / `optional`:

construct exact state binding:

```text
feature_value_hash
+
visual_context_entity_revision_id
```

Then find the active matching VisualAnchor.

Required:

```text
anchor missing
→ VISUAL_REALIZATION_REQUIRED
```

```text
anchor unapproved
→ VISUAL_ANCHOR_APPROVAL_REQUIRED
```

Optional:

```text
missing/unapproved
→ omit
```

Approved applicable realization enters the effective pack.

---

# 47. No Transition-Row Authority

Visual applicability depends on semantic state identity, not authoring-row identity.

Required:

```text
same feature_id
+
same canonical value_hash
+
same visual EntityRevision context
→ same state-specific VisualAnchor applicability
```

regardless of:

```text
FeatureTransition UUID
creation time
row insertion order
```

If an equivalent semantic value is recreated through another transition record, the same VisualAnchor remains applicable.

---

# 48. Approved Revision Integrity

Current resolution does not trust `approved_revision_id` as an opaque pointer.

For every applicable approved revision, verify:

```text
revision belongs to VisualAnchor
↓
canonical(snapshot_json)
↓
SHA-256
↓
== snapshot_hash
```

Verify normalized immutable revision items exactly match snapshot contents.

Verify referenced Asset/Blob provenance remains valid.

Corruption:

```text
fail closed
```

No approved authority is silently omitted.

This applies even to optional facets: once an optional realization is approved and applicable, it is current authority and corruption cannot be ignored.

---

# 49. Canonical VisualReferencePack

Canonical non-empty shape:

```json
{
  "schema_version": 1,
  "anchors": [
    {
      "visual_facet_id": "...",
      "facet_key": "face",
      "visual_anchor_id": "...",
      "visual_anchor_revision_id": "...",
      "visual_anchor_snapshot_hash": "...",
      "target": {
        "kind": "entity",
        "entity_id": "...",
        "entity_revision_id": "..."
      },
      "items": [
        {
          "asset_id": "...",
          "blob_hash": "...",
          "role": "primary",
          "view_key": "front",
          "position": 0
        }
      ]
    }
  ]
}
```

Feature entry target includes:

```text
feature_id
feature_value_hash
feature_value_json
visual_context_entity_revision_id when applicable
```

Requirement policy is not part of VisualReferencePack visual identity.

It gates capture but does not change what the approved visual realization looks like.

---

# 50. VisualReferencePack Anchor Ordering

Canonical anchor ordering must be exact and semantic.

Use target-kind rank:

```text
entity = 0
feature = 1
```

Entity anchor sort key:

```text
0,
entity_id,
entity_revision_id,
facet_key,
visual_facet_id,
visual_anchor_revision_id
```

Feature anchor sort key:

```text
1,
feature_id,
feature_value_hash,
visual_context_entity_revision_id or "",
facet_key,
visual_facet_id,
visual_anchor_revision_id
```

UUIDs are lowercase canonical UUID strings.

Legal uniqueness means the final IDs do not decide between conflicting semantic authorities; they only make canonical serialization mechanically total.

If semantically duplicate applicable state exists illegally, resolution fails before sorting.

---

# 51. VisualReferencePack Hash

Only a valid, non-empty effective pack receives a hash.

```text
pack_bytes
=
canonical_json_bytes(pack)
```

```text
visual_reference_pack_hash
=
SHA-256(pack_bytes)
```

Rules:

```text
readiness false
→ hash = NULL
```

```text
readiness true
+
effective approved visual pack empty
→ hash = NULL
```

```text
readiness true
+
non-empty pack
→ canonical hash
```

Never fabricate a hash for unresolved or semantically empty visual authority.

---

# 52. Combined M7 + M8 Shot Readiness

Shot current-state response gains the additive M8 fields:

```text
visual_continuity_ready
visual_reference_pack_hash
visual_continuity_issues
```

The existing M7 `readiness_projection` remains authoritative for its two predecessor rows. M8 appends one third row:

```text
existing M7 row 1     # unchanged
existing M7 row 2     # unchanged
visual_continuity      # new M8 row
```

No existing row is renamed, reordered, or semantically redefined.

## 52.1 Semantic precondition

If M7 semantic resolution is not ready:

```text
continuity_state_ready = false
        ↓
visual_continuity_ready = false
visual_reference_pack_hash = NULL
effective visual pack = NULL
```

`visual_continuity_issues` surfaces the existing M7 semantic blocker codes/details honestly, including as applicable:

```text
NARRATIVE_CONTEXT_REQUIRED
CONTINUITY_RELATION_ENDPOINT_REQUIRED
```

M8 does not fabricate a partial visual pack and does not substitute a visual wrapper code for an existing semantic cause. Feature-facet applicability is not evaluated against unresolved M7 effective values.

## 52.2 Semantically ready M8 rules

When M7 is ready, M8 evaluates:

```text
required facet + missing exact realization
→ VISUAL_REALIZATION_REQUIRED
→ visual_continuity_ready = false
```

```text
required exact realization + no approval
→ VISUAL_ANCHOR_APPROVAL_REQUIRED
→ visual_continuity_ready = false
```

```text
optional exact realization missing/unapproved
→ readiness unaffected
→ omit from effective pack
```

```text
applicable approved realization/projection corrupt
→ INTERNAL_INVARIANT_VIOLATION
→ no pack/hash produced
```

```text
feature value policy = not_applicable
→ no realization required
```

Optional missing approvals are not blocking issues. Detailed inspector output may still show them as informational status.

## 52.3 Combined execution gate

Current-state Shot capture and any Generation path that performs/currently requires capture are blocked unless **both** conditions are true:

```text
continuity_state_ready == true
AND
visual_continuity_ready == true
```

Existing M7 blocker precedence is preserved. If M7 is not ready, the capture/generation path raises the existing M7 cause before any M8 builder runs. Only after semantic readiness succeeds may an M8 blocking code be raised.

---

# 53. Shot Capture and Generation Gate

ShotRevision capture performs the composed predecessor-first pipeline:

```text
one coherent `_snapshot_one_read` unit
        ↓
resolve existing M7 narrative/semantic current state
        ↓
M7 ready?
├─ no → raise existing M7 blocker
│        no M8 builder invocation
└─ yes
    ↓
    resolve VisualFacet policies
    ↓
    resolve exact applicable VisualAnchors
    ↓
    validate approvals/provenance
    ↓
    M8 ready?
    ├─ no → raise first canonical M8 blocker
    └─ yes
        ↓
        build one canonical current Shot state
        ↓
        capture
```

All current-state resolution occurs on one checked-out connection and one coherent read transaction.

Required combined gate:

```text
continuity_state_ready == true
AND
visual_continuity_ready == true
```

If either is false, current-state ShotRevision capture fails. A required visual failure does **not** silently fall back to a lower schema. A semantic failure does not run a partial M8 resolver.

The public Generation path must reuse this same capture gate; it may not bypass M7/M8 readiness by constructing a Generation from partially resolved current state.

When multiple M8 blockers exist, the resolver's canonical facet/target ordering determines the first raised M8 code; the full ordered blocker set remains available in the readiness projection.

---

# 54. ShotRevision Schema Version 4 — Total Selection Lattice

Existing lower schemas remain byte-stable. Version selection is total over the reachable state space and explicitly identifies unreachable combinations.

| Semantic dependencies | Effective M7 Feature/Relation state | Effective approved visual authority | Result |
|---|---|---|---|
| none | none | empty | exact schema 1 |
| none | none | non-empty | **UNREACHABLE BY CONSTRUCTION** |
| none | non-empty | empty | **UNREACHABLE BY CONSTRUCTION** — M7 effective state requires semantic dependencies |
| none | non-empty | non-empty | **UNREACHABLE BY CONSTRUCTION** |
| present | empty | empty | exact schema 2 |
| present | empty | non-empty | schema 4 with the exact schema-2 semantic base + visual block |
| present | non-empty | empty | exact schema 3 |
| present | non-empty | non-empty | schema 4 with the exact schema-3 semantic base + visual block |

The load-bearing unreachable cell is:

```text
zero semantic dependencies
+
non-empty visual authority
```

because M8 facets become applicable only through resolved dependency EntityRevisions and/or effective entity-scoped Feature values. If implementation ever constructs this cell, it is `INTERNAL_INVARIANT_VIOLATION`; schema selection must not invent a representation for it.

For dependency-bearing Shots, the four reachable M7/visual cells are therefore frozen explicitly:

```text
M7 empty  + visual empty     → schema 2
M7 empty  + visual non-empty → schema 4 over schema-2 base
M7 present + visual empty    → schema 3
M7 present + visual non-empty→ schema 4 over schema-3 base
```

---

# 55. No Empty Schema-4 Alternative

Never emit:

```json
{
  "schema_version": 4,
  "visual_reference_pack": {
    "schema_version": 1,
    "anchors": []
  }
}
```

when lower schema already represents the exact effective production semantics.

Examples:

```text
optional facets exist
+
none approved
+
no required failure
→ effective visual authority empty
→ preserve lower schema
```

```text
required facet unresolved
→ capture blocked
→ do not emit lower schema as workaround
```

Schema versions represent captured semantic content, not which resolver code happened to execute.

---

# 56. Schema-4 Visual Block

Schema 4 extends the exact lower canonical Shot snapshot with:

```json
{
  "visual_reference_pack": {
    "schema_version": 1,
    "anchors": [
      {
        "visual_facet_id": "...",
        "facet_key": "...",
        "visual_anchor_id": "...",
        "visual_anchor_revision_id": "...",
        "visual_anchor_snapshot_hash": "...",
        "target": {},
        "items": []
      }
    ]
  }
}
```

The lower semantic portion is produced by the existing canonical Shot builder unchanged.

M8 does not reimplement M6/M7 semantics.

The complete schema-4 ShotRevision bytes are canonicalized and hashed through the same existing ShotRevision mechanism.

---

# 57. Normalized ShotRevision Visual Provenance

Schema-4 canonical bytes are historical hash authority.

M8 also writes immutable normalized provenance rows from the same frozen in-memory visual pack for:

* queryability;
* Asset/Blob retention;
* historical UI;
* corruption detection.

Conceptual anchor table:

```text
shot_revision_visual_anchors

shot_revision_id              UUID NOT NULL
position                      INTEGER NOT NULL

visual_facet_id               UUID NOT NULL
facet_key                     TEXT NOT NULL
visual_anchor_id              UUID NOT NULL
visual_anchor_revision_id     UUID NOT NULL
visual_anchor_snapshot_hash   TEXT NOT NULL

target_kind                   TEXT NOT NULL
entity_id                     UUID NULL
entity_revision_id            UUID NULL
feature_id                    UUID NULL
feature_value_hash            TEXT NULL
feature_value_json            TEXT NULL
visual_context_entity_revision_id UUID NULL

PRIMARY KEY(
    shot_revision_id,
    position
)
```

Conceptual item table:

```text
shot_revision_visual_anchor_items

shot_revision_id              UUID NOT NULL
anchor_position               INTEGER NOT NULL
item_position                 INTEGER NOT NULL

asset_id                      UUID NOT NULL
blob_hash                     TEXT NOT NULL
role                          TEXT NOT NULL
view_key                      TEXT NULL

PRIMARY KEY(
    shot_revision_id,
    anchor_position,
    item_position
)
```

These rows are immutable projections of canonical ShotRevision bytes.

They never become a second authority.

Any mismatch between canonical snapshot and normalized historical rows is corruption and fails closed.

ShotRevision reuse integrity extends the existing M7 rule. If a schema-4 ShotRevision is found by `(shot_id, snapshot_hash)` during capture reuse, the code must verify before returning it:

```text
stored snapshot_json bytes
== recomputed canonical schema-4 bytes

AND

existing M6/M7 normalized projections
== predecessor canonical projections

AND

shot_revision_visual_anchors/items
== exact projection of the recomputed visual block
```

Any mismatch raises `INTERNAL_INVARIANT_VIOLATION`. Reuse never repairs, backfills, recaptures, or silently creates a replacement revision.

---

# 58. Historical Isolation

After ShotRevision capture:

> The resolved visual reference pack is historical fact.

Historical loading must not consult:

```text
current VisualFacet rows
current VisualFacet requirement
current feature-value policy rows
current VisualAnchor working items
current VisualAnchor approved_revision_id
current FeatureTransitions
current Entity approval/topology
```

Historical loader uses:

```text
ShotRevision canonical captured bytes
+
immutable ShotRevision visual-provenance rows
+
Asset/Blob storage by captured identity
```

Current state never repairs or substitutes missing historical authority.

---

# 59. Exact Rerun Isolation

Exact Rerun of a Generation whose ShotRevision captured visual state uses only historical captured visual authority.

Example:

```text
Generation G
captured VisualAnchorRevision 4
        ↓
later current approval becomes revision 7
        ↓
Exact Rerun G
→ still uses revision 4 capture
```

Hard source-gate proof:

```text
monkeypatch current M8 resolver to raise
↓
Exact Rerun historical Generation
↓
must still succeed
```

Additionally assert no Exact Rerun reads of:

```text
visual_facets current policy
visual_facet_value_policies
visual_anchors.approved_revision_id
visual_anchor_items
current FeatureTransitions
current Entity approvals
```

Historical Blob resolution by captured Asset/Blob identity is allowed and required.

---

# 60. Current Approval Changes Never Rewrite History

Example:

```text
Shot 20 captured
→ Eva face VisualAnchorRevision 3

later:
VisualAnchorRevision 4 approved
```

Required:

```text
historical Shot 20
→ revision 3 forever

new current capture
→ revision 4
```

No historical backfill.

No migration of old ShotRevision bytes.

---

# 61. Forehead-Cut Example

Stable concern:

```text
VisualFacet:
Eva.forehead_injury / cut-realization
requirement = required
```

Value policies:

```text
none
→ not_applicable

fresh
→ required

healing
→ required

scarred
→ required
```

Current state:

```text
Eva EntityRevision 12
forehead_injury = fresh
```

State-specific realization:

```text
VisualAnchor:
feature_id = forehead_injury
feature_value_hash = hash(fresh)
visual_context_entity_revision_id = Eva rev12
        ↓
Approved VisualAnchorRevision
        ↓
primary/detail/supporting Assets
        ↓
Shot VisualReferencePack
        ↓
ShotRevision schema 4
        ↓
M9 conditioning
```

If Eva becomes EntityRevision 13 while the wound remains fresh:

```text
old rev12 cut realization does not automatically apply
```

If no rev13/fresh realization exists and the facet is required:

```text
visual continuity not ready
```

If a model produces a different cut:

```text
failed realization of authority
```

not:

```text
new authority
```

---

# 62. Hotel-Lobby Example

Stable Entity VisualFacets:

```text
Grand Meridian Lobby
│
├── identity              required
├── reception-desk        required
├── signage               required
└── material-palette      optional
```

For Lobby EntityRevision 2:

```text
identity VisualAnchor
├── primary / reception-facing
├── supporting / elevator-facing
└── supporting / entrance-facing

reception-desk VisualAnchor
├── primary / front
└── detail / brass-trim

signage VisualAnchor
├── primary / wide
└── detail / hotel-logo

material-palette VisualAnchor
├── primary / lobby-wide
├── detail / floor
└── detail / wall
```

If the Lobby moves to EntityRevision 3:

```text
required facets remain required
```

but rev2 anchors do not automatically apply.

Each required facet needs an approved rev3 realization before current Shots using Lobby rev3 are visually ready.

M8 defines approved appearance.

M10 later defines enough spatial authority to constrain layout and arbitrary camera views.

---

# 63. Relation Visual Authority Boundary

M7 Relations may express facts such as:

```text
Eva wears Red Dress
Eva carries Bag
Bag contains Letter
```

M8 does not yet define composite multi-entity visual realization of such relations.

Explicit boundary:

> M8 controls individual Entity/design facets and ContinuityFeature-state visual realization. Relationship-specific composite visual authority is deferred.

M9 may realize current semantic relations using separately approved Entity/Feature authority, but it may not create persistent relational visual canon.

If relationship-specific approved appearance becomes necessary, it must be introduced as a separate SoloRing authority problem rather than smuggled into M9 model prompts.

---

# 64. Resolver Query Strategy

M8C must implement set-oriented resolution.

Required pattern inside one coherent read transaction:

```text
1. resolve M6/M7 semantic state

2. collect:
   Entity IDs
   EntityRevision IDs
   Feature IDs
   feature value hashes
   entity-revision visual contexts

3. batch fetch all applicable VisualFacets

4. batch fetch all value-policy overrides

5. batch fetch all candidate exact-state VisualAnchors

6. batch fetch all approved VisualAnchorRevisions

7. batch fetch immutable revision items + Asset/Blob provenance

8. build result in memory
```

Forbidden:

```text
one query per Entity
one query per Feature
one query per facet
one query per anchor
one query per item
```

Do not rely on one enormous many-table JOIN as the only performance strategy.

Prefer collect-IDs + batch-fetch phases with bounded query count.

---

# 65. Query-Shape Gate

Feature-film scale should increase row volume, not round trips per visual concern.

Gate compares:

```text
small representative Shot
vs
large representative Shot/Project state
```

Required:

```text
bounded query count independent of facet/item count
```

Record:

* query count;
* row count;
* wall-clock observation;
* memory observation where practical.

Do not invent an arbitrary wall-clock pass/fail threshold in M8.

The binding gate is deterministic correctness plus bounded query shape.

---

# 66. Representative Scale Fixture

Project volume alone is not a sufficient scale proof. The fixture must stress the **target Shot's dependency/facet dimension**, not merely place 2,500 unrelated Shots in the same database.

Required fixture shape:

```text
~2,500 total Shots
multiple recurring Entities
multiple Locations
multiple EntityRevisions
multiple ContinuityFeatures
multiple Feature values
several required/optional VisualFacets per recurring Entity/Feature
feature-value policies
multi-view VisualAnchors
multiple VisualAnchorRevisions
historical schema-4 ShotRevisions

AND

one designated target Shot wired to a representative multi-entity,
multi-feature, multi-facet dependency set large enough to exercise
all batch-fetch dimensions in one resolution
```

The target Shot must exercise:

* entity facet resolution;
* feature facet resolution;
* requirement changes;
* state-specific realization changes;
* optional approved anchors;
* not-applicable feature values;
* multi-item approved packs.

Freeze the exact target-Shot counts as named fixture constants in the test source and report them with the evidence. The gate compares a small fixture and the representative target fixture through the same production resolver entrypoint.

Direct SQL bulk wiring is allowed for scale-only scaffolding where service-layer construction would make the fixture prohibitively slow, provided the test:

* discloses every table wired directly;
* preserves all frozen invariants/constraints;
* does not use direct SQL to bypass the semantic behavior being measured;
* constructs the designated target Shot's meaningful semantic/visual state so the production resolver performs the actual applicability work.

Measure:

```text
query count
row count
resolver wall-clock observation
output determinism
target-Shot dependency/facet cardinalities
```

Do not invent a premature wall-clock pass/fail threshold. The binding gate is bounded query shape plus deterministic correctness across the target dimension.

---

# 67. API Surface

## VisualFacets

```text
GET    /projects/{id}/visual-facets
POST   /projects/{id}/visual-facets

GET    /visual-facets/{id}
PATCH  /visual-facets/{id}
DELETE /visual-facets/{id}
```

## Feature-value policies

```text
PUT /visual-facets/{id}/value-policies
```

## State-specific VisualAnchors

```text
GET    /visual-facets/{id}/anchors
POST   /visual-facets/{id}/anchors

GET    /visual-anchors/{id}
DELETE /visual-anchors/{id}
```

Semantic state-binding fields are immutable, so no general VisualAnchor PATCH is required.

## Working items

```text
PUT /visual-anchors/{id}/items
```

## Revisions

```text
GET  /visual-anchors/{id}/revisions
POST /visual-anchors/{id}/revisions
GET  /visual-anchor-revisions/{id}
```

## Approval

```text
POST /visual-anchor-revisions/{id}/approve
POST /visual-anchors/{id}/unapprove
```

## Shot inspection

```text
GET /shots/{id}/visual-continuity
```

Shot detail also returns lightweight visual readiness/hash fields.

---

# 68. Stable Error Codes — Closed M8 Table

The following table is the **exact closed M8 error vocabulary** for this milestone. Implementation must not add spelling variants, near-duplicates, or ad-hoc M8 wrappers without reopening the frozen plan. Existing predecessor/global codes remain separate and are reused where they already express the condition.

| Error code | HTTP | Exact trigger |
|---|---:|---|
| `VISUAL_FACET_NOT_FOUND` | 404 | Requested active VisualFacet does not exist (malformed/missing ID follows the normal entity-not-found policy). |
| `VISUAL_FACET_TARGET_INVALID` | 409 | VisualFacet target kind/identity is semantically invalid for the requested Project, including cross-Project Entity/Feature targeting or a target that violates the frozen entity/feature shape. |
| `VISUAL_FACET_VALUE_POLICY_INVALID` | 422 | Submitted feature-value policy/value cannot be validated through the owning M7 Feature's current frozen value domain/canonicalizer, or a value policy is supplied for an Entity facet. |
| `VISUAL_FACET_DELETE_BLOCKED` | 409 | VisualFacet deletion is attempted while it is `required` or while active VisualAnchors remain; details identify the blocking reason. |
| `VISUAL_ANCHOR_NOT_FOUND` | 404 | Requested active VisualAnchor does not exist. |
| `VISUAL_ANCHOR_TARGET_INVALID` | 409 | Requested state-specific binding does not belong to the owning VisualFacet/M7 semantic target, including wrong EntityRevision, feature value, or visual-context EntityRevision. |
| `VISUAL_ANCHOR_ASSET_PROJECT_MISMATCH` | 409 | Working-set mutation references an Asset outside the VisualFacet/Anchor Project. |
| `VISUAL_ANCHOR_ITEM_INVALID` | 422 | Working-set item payload violates the closed role/view/duplicate-Asset/order input contract other than the dedicated multiple-primary condition. |
| `VISUAL_ANCHOR_MULTIPLE_PRIMARY` | 422 | Proposed working set contains more than one `primary` item. |
| `VISUAL_ANCHOR_PRIMARY_REQUIRED` | 409 | Revision capture is requested from a valid draft working set that has items but zero `primary` items. |
| `VISUAL_ANCHOR_REVISION_NOT_FOUND` | 404 | Requested VisualAnchorRevision does not exist. |
| `VISUAL_ANCHOR_APPROVAL_REQUIRED` | 409 | A required exact VisualAnchor exists but has no approved revision at current Shot readiness/capture time. |
| `VISUAL_REALIZATION_REQUIRED` | 409 | A required VisualFacet applies to the resolved semantic state but no exact active state-specific VisualAnchor exists. |
| `VISUAL_ANCHOR_APPROVAL_CONFLICT` | 409 | Approve or unapprove request supplies an expected current approval pointer that no longer matches the stored pointer. |
| `VISUAL_ANCHOR_DELETE_BLOCKED` | 409 | Delete is attempted while the VisualAnchor still has an approved revision; explicit unapproval is required first. |

Inherited codes used by M8 composition are not redefined:

| Existing code | HTTP | M8 use |
|---|---:|---|
| `NARRATIVE_CONTEXT_REQUIRED` | 409 | M7 semantic precondition fails before M8 visual resolution. |
| `CONTINUITY_RELATION_ENDPOINT_REQUIRED` | 409 | M7 relation/semantic readiness fails before M8 visual resolution. |
| `ASSET_NOT_FOUND` | 404 | A working-set mutation or revision-capture validation references an Asset that does not exist under the existing Asset lookup contract. |
| `BLOB_NOT_FOUND` | 404 | Reserved for direct Blob-identity lookup failures outside immutable M8 provenance. A registered Blob whose physical bytes are missing during M8 working-set/revision validation is corruption and maps to `INTERNAL_INVARIANT_VIOLATION` per §40 and §91. |
| `INTERNAL_INVARIANT_VIOLATION` | 500 | Stored canonical/projection corruption, impossible schema-lattice state, illegal duplicate semantic authority, hash mismatch, missing immutable provenance expected by a committed row, or any other state impossible under legal M8 writes. |

Consequences of the closed table:

* `VISUAL_ANCHOR_REVISION_MISMATCH`, `VISUAL_ANCHOR_STATE_AMBIGUOUS`, `VISUAL_REFERENCE_PROVENANCE_INVALID`, `VISUAL_REFERENCE_PACK_UNRESOLVED`, `VISUAL_FACET_PROJECT_MISMATCH`, `VISUAL_FACET_REQUIRED`, `VISUAL_FACET_HAS_ACTIVE_ANCHORS`, and `VISUAL_ANCHOR_UNAPPROVE_CONFLICT` are **not** M8 codes. Their former situations map to the exact table above or to `INTERNAL_INVARIANT_VIOLATION`.
* Approval and unapproval share `VISUAL_ANCHOR_APPROVAL_CONFLICT`; they do not define symmetric spelling variants.
* Corruption never receives a user-correctable M8 domain code merely to keep the UI running. It fails closed as an invariant violation.

Use the existing SoloRing error envelope unchanged.

---

# 69. UI — VisualFacet Workspace

Entity and Feature inspection gain a Visual Identity workspace.

Entity example:

```text
Eva

Visual Identity

✓ face              required
✓ wardrobe          required
○ hair              optional
! identity           required — rev4 realization missing
```

Feature example:

```text
Forehead injury

Visual Facet:
cut-realization
required

Value policies:
none       not applicable
fresh      required
healing    required
scarred    required
```

Actions:

* create facet;
* set required/optional;
* configure feature-value overrides;
* inspect exact state realizations;
* create realization for current EntityRevision/Feature value;
* inspect approved/current working state.

---

# 70. UI — VisualAnchor Curation

VisualAnchor view shows:

```text
State binding
Approved revision
Working state
Working differs from approved
Primary reference
Supporting/detail/context references
View labels
Revision history
```

Actions:

```text
add existing Asset
add generated output Asset
set/change primary
set role
set view key
reorder
capture revision
approve revision
unapprove
soft-delete realization
```

The UI clearly separates:

```text
working set
```

from:

```text
captured revision
```

from:

```text
approved authority
```

---

# 71. UI — Generated Take Promotion

Take/Asset inspection may offer:

```text
Add to Visual Identity…
```

The UI may suggest likely targets based on historical semantic dependencies, for example:

```text
Eva / face
Eva.forehead_injury / cut-realization
Grand Meridian Lobby / identity
```

But:

* user chooses the VisualFacet/VisualAnchor;
* the Asset is added only to working state;
* no revision is captured automatically;
* no approval occurs automatically.

The authority chain remains visible.

---

# 72. UI — Shot Visual Continuity Inspector

Shot view exposes current facet-level status:

```text
Visual Continuity

✓ Eva / face
✓ Eva / wardrobe
✓ Eva / forehead cut
✓ Grand Meridian Lobby / identity
! Grand Meridian Lobby / signage
  required realization for Lobby rev3 is not approved
```

For each row expose:

* stable VisualFacet;
* current semantic/design state;
* matching VisualAnchor if any;
* current approved VisualAnchorRevision if any;
* primary Asset;
* reference count;
* blocking issue if any.

No model/executor terminology appears in this authority UI.

---

# 73. UI — Historical Visual Provenance

Historical ShotRevision view shows captured authority:

```text
Visual References at Capture
```

Example:

```text
Eva / face
Captured realization: Eva rev3
Captured VisualAnchorRevision: 4
Current approved realization: Eva rev4 / revision 2
```

The UI must never present current approval as though it were historical execution input.

If an Asset later becomes hidden/soft-deleted, historical UI still displays captured Asset ID/Blob identity and retained bytes.

---

# 74. Migration

Predecessor baseline is frozen for this plan:

```text
M7 commit:
479c3a6b77e37282e0f1e5da34321622e292c1c1

M7 tree:
b34c98d

predecessor migration:
0008_narrative_continuity_state
```

M8 therefore creates:

```text
0009_m8_visual_identity.py
```

Its Alembic `down_revision` must reference the actual revision identifier declared by `0008_narrative_continuity_state.py`; do not substitute the filename if Alembic's internal revision token differs.

Create:

```text
visual_facets
visual_facet_value_policies
visual_anchors
visual_anchor_items
visual_anchor_revisions
visual_anchor_revision_items
shot_revision_visual_anchors
shot_revision_visual_anchor_items
indexes
constraints
```

Existing ShotRevision rows remain byte-for-byte unchanged.

M8 does not rewrite historical schema 1/2/3 snapshots.

---

# 75. Downgrade Safety

M8 downgrade performs a preflight.

Refuse downgrade if any meaningful M8 state exists, including:

```text
visual_facets rows
visual_facet_value_policies rows
visual_anchors rows
visual_anchor_revisions rows
```

or if any:

```text
ShotRevision schema_version >= 4
```

exists.

Do not silently destroy feature-film continuity authority to complete an Alembic downgrade.

An empty never-used M8 schema may downgrade normally.

---

# 76. Required Indexes

At minimum support:

```text
visual_facets(project_id, deleted_at)
visual_facets(entity_id, facet_key, deleted_at)
visual_facets(feature_id, facet_key, deleted_at)

visual_facet_value_policies(
    visual_facet_id,
    feature_value_hash
)

visual_anchors(
    visual_facet_id,
    entity_revision_id,
    deleted_at
)

visual_anchors(
    visual_facet_id,
    feature_value_hash,
    visual_context_entity_revision_id,
    deleted_at
)

visual_anchors(approved_revision_id)

visual_anchor_items(
    visual_anchor_id,
    position
)
visual_anchor_items(asset_id)

visual_anchor_revisions(
    visual_anchor_id,
    revision_number
)

visual_anchor_revision_items(asset_id)
visual_anchor_revision_items(blob_hash)

shot_revision_visual_anchors(
    shot_revision_id,
    position
)

shot_revision_visual_anchor_items(asset_id)
shot_revision_visual_anchor_items(blob_hash)
```

Inspect SQLite's automatically generated PK/UNIQUE indexes before freezing the migration.

Do not add redundant custom indexes without a demonstrated query need.

---

# 77. M8A — Stable Visual Concern and Schema Core

Build:

* bind to the frozen M7 `canonicalize_value` / value-hash authority;
* VisualFacet model;
* entity/feature facet targeting;
* `facet_key` policy;
* requirement semantics;
* feature-value policy overrides;
* VisualAnchor state-specific binding;
* EntityRevision context for feature realizations;
* active uniqueness;
* working items;
* VisualAnchorRevision schema;
* immutable revision-item provenance;
* ShotRevision visual provenance tables;
* constraint names;
* indexes;
* migration;
* ORM models;
* stable errors.

Gate:

```text
M7 regression suite
+
migration suite
+
target/project integrity
+
active uniqueness
+
value-hash alignment
+
constraint tests
```

---

# 78. M8B — Curation, Canonical Revision, Approval

Build:

* atomic working-set PUT;
* global contiguous positions;
* role validation;
* one-primary working rule;
* free-form bounded view keys;
* canonical VisualAnchorRevision snapshot;
* coherent two-phase revision capture;
* revision convergence;
* immutable revision-item projection;
* working-vs-approved comparison;
* explicit approval with expected pointer;
* explicit unapproval;
* VisualAnchor deletion rules;
* VisualFacet deletion rules;
* generated-output Asset promotion workflow.

Gate:

```text
working-state tests
+
mechanically proven revision race tests
+
hybrid-capture rejection proof
+
VisualAnchorRevision reuse-integrity corruption UPDATE→fail→restore loop
+
positive-control identical reuse after restore
+
approval conflict tests
+
unapproval tests
+
Asset provenance tests
+
all prior tests
```

---

# 79. M8C — Resolver and Readiness

Build:

* one `VisualReferenceResolver` semantic path;
* coherent read transaction;
* entity facet applicability;
* feature facet applicability;
* feature-value policy resolution;
* exact state-specific VisualAnchor matching;
* EntityRevision-context matching;
* approval/provenance verification;
* required/optional semantics;
* `not_applicable` semantics;
* canonical VisualReferencePack;
* exact anchor ordering comparator;
* pack hashing;
* set-oriented batch query strategy;
* readiness issue taxonomy;
* Shot visual-continuity endpoint.

Gate:

```text
M7 semantic-not-ready → visual false/NULL without M8 partial resolution
+
combined readiness_projection preserves two M7 rows + appends one visual row
+
existing M7 blocker precedence on capture/generation
+
resolver determinism
+
requirement survival across EntityRevision changes
+
requirement survival across Feature value changes
+
not-applicable edge cases
+
semantic value/transition independence
+
EntityRevision context safety
+
provenance corruption failures
+
bounded query-shape tests
+
all prior tests
```

---

# 80. M8D — Immutable Shot Capture and History

Build:

* ShotRevision schema 4;
* complete schema-selection lattice;
* no-empty-schema-4 guard;
* visual-reference-pack capture;
* normalized immutable historical visual provenance;
* historical snapshot/projection cross-validation;
* current/historical isolation;
* Exact Rerun isolation;
* zero-current-M8-table-read source gate for Exact Rerun;
* Blob/Asset retention verification;
* downgrade preflight.

Gate:

```text
schema-version compatibility
+
total lattice including zero-dependency/non-empty-visual unreachable invariant
+
M6/M7 byte-stability fixtures
+
schema-4 ShotRevision reuse-integrity corruption loop
+
required-unresolved capture blocking
+
optional-empty lower-schema preservation
+
approval-change historical isolation
+
EntityRevision-change historical isolation
+
Feature-transition-change historical isolation
+
Exact Rerun monkeypatch gate
+
Blob retention tests
+
all prior tests
```

---

# 81. M8E — Visual Continuity UI

Build:

* VisualFacet workspace;
* requirement editor;
* feature-value policy editor;
* state-specific VisualAnchor browser;
* VisualAnchor working-set editor;
* primary selection;
* role/view labeling;
* revision history;
* approval/unapproval controls;
* generated-Take-to-working-set flow;
* Shot Visual Continuity inspector;
* historical visual provenance viewer;
* explicit current-vs-captured distinction.

Gate:

```text
frontend typecheck
+
component tests
+
API integration tests
+
production build
```

---

# 82. M8F — Failure, Race, Scale, and Source Gate

Exercise:

```text
deleted semantic target
cross-Project Entity target
cross-Project Feature target
cross-Project EntityRevision context
cross-Project Asset
missing Asset
missing Blob file
zero primary at revision capture
multiple primary at working PUT
position gap/collision
revision-number collision
identical concurrent revision capture
working edit during revision capture
approval race
stale expected approval pointer
unapproval race
requirement optional→required during Shot capture
requirement required→optional during Shot capture
EntityRevision change with missing required realization
Feature value change with missing required realization
Feature value not_applicable override
same semantic Feature value via new transition UUID
same feature value across different EntityRevision context
VisualAnchor soft deletion
VisualFacet deletion guard
approved anchor deletion guard
current approval change after Shot capture
current working edit after Shot capture
historical provenance mismatch
snapshot hash mismatch
normalized revision-item mismatch
VisualAnchorRevision reuse with corrupted snapshot_json
VisualAnchorRevision reuse with corrupted normalized item row
ShotRevision schema-4 reuse with corrupted visual projection
Exact Rerun with current M8 resolver disabled
Exact Rerun query-spy current-table prohibition
direct Asset/Blob deletion rejected by restrictive immutable-provenance FKs
source audit confirms no Asset delete route / Blob-GC implementation was silently added
representative target-Shot resolver query shape
```

## 82.1 Race proof mechanics

A test called a race must mechanically prove the intended interleaving. **No sleeps are permitted as synchronization.**

Use `asyncio.Event`/threading `Event` barriers at the actual semantic/transaction seams. For writer competitors, an event is set at the competitor's `BEGIN IMMEDIATE` entry, and a separate event records commit completion.

Required resolver/capture forms include:

### Competitor commits before first pinned read

```text
reader enters the pinned `_snapshot_one_read` unit
reader blocks before its first semantic SELECT
        ↓
competitor reaches BEGIN IMMEDIATE
→ set begin_immediate_entered Event
competitor mutates + COMMIT
→ set competitor_committed Event
        ↓
reader is released
reader performs first pinned semantic read
        ↓
reader must observe the complete AFTER state
```

### Competitor commits after snapshot establishment

```text
reader performs the first read that establishes its DB snapshot
→ set snapshot_established Event
        ↓
competitor reaches BEGIN IMMEDIATE
→ set begin_immediate_entered Event
competitor mutates + COMMIT
→ set competitor_committed Event
        ↓
reader performs remaining semantic/M8 reads
        ↓
reader must observe the complete BEFORE state
never a hybrid
```

Apply these forms to the state dimensions that matter: M7 semantic source mutations, VisualFacet requirement/policy mutations, VisualAnchor approval changes, and VisualAnchor working-set edits during VisualAnchorRevision capture.

## 82.2 Scale proof mechanics

The scale gate exercises the designated multi-entity/multi-feature/multi-facet target Shot described in §66, not merely a database containing many unrelated rows. Small and representative fixtures call the same production resolver. Query count must remain bounded by query classes, not target cardinality.

Direct-SQL bulk wiring is permitted only under the disclosure/invariant rules in §66.

Then perform the final semantic source audit against:

```text
predecessor M7 commit 479c3a6b77e37282e0f1e5da34321622e292c1c1
predecessor tree b34c98d
this M8 r5 frozen contract
```

---

# 83. Critical Test — Required Entity Facet Survives Revision Change

```text
Eva / face
requirement = required

Eva rev3 current
rev3 face approved
→ ready

switch current semantic dependency to Eva rev4
no rev4 face VisualAnchor
→ NOT ready
→ VISUAL_REALIZATION_REQUIRED
```

This test closes the original vacuous-readiness hole.

---

# 84. Critical Test — Required Feature Facet Survives Value Change

```text
forehead_injury / cut-realization
requirement = required

fresh value
approved fresh realization
→ ready

change effective value to healing
no healing realization
→ NOT ready
```

If:

```text
none value
policy = not_applicable
```

then:

```text
no realization required
→ readiness unaffected
```

---

# 85. Critical Test — EntityRevision Context Prevents Accidental Reuse

```text
Eva rev12
forehead_injury = fresh
approved rev12/fresh realization
```

Then:

```text
Eva changes to rev13
forehead_injury remains fresh
```

Required:

```text
rev12/fresh anchor does not automatically apply
```

If required:

```text
NOT ready until rev13/fresh realization approved
```

---

# 86. Critical Test — Generated Output Is Never Automatic Authority

```text
generated output exists
→ not authority
```

```text
Take approved
→ not M8 authority
```

```text
output Asset added to working VisualAnchor
→ still not authority
```

```text
VisualAnchorRevision captured
→ still not authority
```

```text
explicit approval succeeds
→ current visual authority changes
```

No earlier step may change current VisualReferencePack.

---

# 87. Critical Test — Historical Isolation

Capture:

```text
ShotRevision S
with VisualAnchorRevision A3
```

Then mutate current state:

```text
approve A4
change working items
reorder references
change VisualFacet requirement
change feature-value policies
change FeatureTransitions
change current EntityRevision
soft-delete current VisualAnchor
```

Required:

```text
historical S
→ exactly A3
→ same captured Asset IDs
→ same Blob hashes
→ same captured visual pack bytes
```

---

# 88. Critical Test — One Semantic Path

Prove:

```text
Shot detail
visual inspector
readiness
pack hash
ShotRevision capture
```

all consume one resolver/builder result.

A deliberate test perturbation of the canonical resolver must affect every **current-state** consumer.

There must be no hidden second applicability implementation.

Historical/Exact Rerun paths are intentionally separate because they consume immutable captured state rather than current resolution.

---

# 89. Critical Test — No Empty Schema 4

Fixture:

```text
M8 code deployed
+
Shot has lower-schema semantic state
+
no effective approved visual authority
```

Required:

```text
captured ShotRevision bytes
=
exact previous lower-schema bytes
```

and:

```text
snapshot_hash unchanged
```

Cases include:

* no VisualFacets;
* only optional facets with no approved realizations;
* feature facets whose current values are `not_applicable`.

---

# 90. Critical Test — Required Unresolved State Never Falls Back

```text
required VisualFacet applies
+
exact realization missing/unapproved
```

Required:

```text
ShotRevision capture fails
```

Forbidden:

```text
capture lower schema
```

Forbidden:

```text
schema 4 with empty/partial visual pack
```

---

# 91. Critical Test — Blob Retention

```text
Blob referenced by VisualAnchorRevision item
→ GC ineligible
```

```text
Blob referenced by schema-4 historical ShotRevision item
→ GC ineligible
```

Attempted hard Asset deletion while referenced:

```text
rejected
```

Missing physical Blob bytes:

```text
integrity failure
not silent omission
```

---

# 92. Rejected / Deferred Enhancements

Do not add to M8 merely because they may be useful later:

* `shots.visual_reference_pack_hash` materialized cache;
* `VisualAnchorRevision.is_approved` duplicate authority flag;
* approval-history table;
* draft-revision status column;
* batch approval;
* bulk-create APIs;
* item-level PATCH;
* global view-key enum;
* view-key semantic inference;
* cross-project Asset sharing;
* franchise/project-group authority;
* visual similarity scores;
* automatic anchor creation;
* automatic generated-output promotion;
* relationship-specific composite visual authority;
* arbitrary wall-clock resolver threshold.

Introduce them only when a concrete SoloRing production problem requires them.

---

# 93. M8 / M9 Boundary

M8 ends here:

```text
Approved Visual Authority
        ↓
Captured Immutable VisualReferencePack
```

M9 begins here:

```text
Captured Immutable VisualReferencePack
        ↓
model capability selection
        ↓
model-specific conditioning
        ↓
executor materialization
```

M9 may map the same captured authority into:

* reference images;
* identity embeddings;
* adapter inputs;
* model-specific weights;
* LoRA selection;
* conditioning graphs;
* other future mechanisms.

None of those mechanisms may redefine M8 authority.

M9 receives immutable captured M8 authority as input.

---

# 94. M8 / M10 Boundary

M8 solves:

> What visual aspects must remain controlled, and what approved reference material defines them for this exact semantic/design state?

M10 solves:

> Where are things in the world, and how should arbitrary camera viewpoints observe them consistently?

For the hotel lobby:

```text
M8
approved appearance
materials
furnishing appearance
signage
important reference views
visual details
```

```text
M10
stable spatial relationships
layout
geometry/depth/world representation
camera relation
arbitrary-view spatial continuity
```

Feature-film-level continuity ultimately needs both.

---

# 95. M8 Definition of Done

M8 closes only when:

* [ ] VisualFacet exists as stable SoloRing production concern independent of models.
* [ ] Entity VisualFacets target stable Entity identity, not EntityRevision.
* [ ] Feature VisualFacets target stable ContinuityFeature identity.
* [ ] `facet_key` is immutable and actively unique per semantic target.
* [ ] Required/optional policy lives on VisualFacet, not state-specific VisualAnchor.
* [ ] Feature-value policy overrides support `required`, `optional`, and `not_applicable`.
* [ ] A new effective value on a required feature facet fails safe unless explicitly exempted.
* [ ] M8 consumes the exact M7 canonical feature `value_hash` and does not invent another hash path.
* [ ] Feature VisualAnchors capture canonical value JSON for self-describing provenance.
* [ ] Entity-scoped feature realizations include exact EntityRevision visual context.
* [ ] Same feature value does not automatically cross EntityRevision design changes.
* [ ] VisualAnchor state bindings are immutable after creation.
* [ ] Active exact-state VisualAnchor duplicates are prevented by schema constraints.
* [ ] Working reference membership remains mutable.
* [ ] Working positions are global, contiguous, and server-owned.
* [ ] The same Asset cannot appear twice in one VisualAnchor working set.
* [ ] Working state may have zero primary but never multiple primaries.
* [ ] VisualAnchorRevision capture requires exactly one primary.
* [ ] Every approved visual authority has exactly one canonical primary reference.
* [ ] View keys remain bounded human production metadata, not model authority.
* [ ] VisualAnchorRevision snapshots are canonical and byte-tested.
* [ ] Concurrent identical revision captures converge.
* [ ] Concurrent working edits cannot produce hybrid captured revisions.
* [ ] Immutable revision-item rows exactly project canonical revision bytes.
* [ ] Approval changes only through explicit fenced approval.
* [ ] Stale concurrent approval attempts conflict rather than silently overwrite.
* [ ] Current approval can be explicitly revoked.
* [ ] Generated output never becomes visual authority automatically.
* [ ] Output Asset provenance is never rewritten during promotion.
* [ ] VisualFacet deletion cannot silently remove a required production concern.
* [ ] Approved VisualAnchor deletion requires explicit unapproval first.
* [ ] VisualAnchor soft deletion never destroys immutable revisions/history.
* [ ] Cross-Project Entity, Feature, EntityRevision, and Asset references are rejected.
* [ ] Immutable VisualAnchorRevision Asset/Blob references are retention roots.
* [ ] Historical schema-4 Asset/Blob references are retention roots.
* [ ] Missing immutable Blob bytes are corruption.
* [ ] One current-state resolver/builder path powers inspection, readiness, hashing, and capture.
* [ ] Current M6/M7/M8 semantic reads are transactionally coherent.
* [ ] Entity facet applicability uses the exact resolved EntityRevision.
* [ ] Feature facet applicability uses exact M7 value hash and exact visual EntityRevision context when required.
* [ ] Feature transition UUID never defines visual applicability.
* [ ] Optional missing realizations do not block readiness.
* [ ] Applicable approved optional realizations are included and must be provenance-valid.
* [ ] Required missing realizations block Shot capture.
* [ ] Unresolved state never receives a fabricated pack hash.
* [ ] Effective empty visual authority preserves exact lower ShotRevision schema.
* [ ] Required unresolved visual state never falls back to a lower schema.
* [ ] Any non-empty approved visual authority produces schema 4 regardless of whether M7 effective state is empty.
* [ ] Schema-4 canonical bytes contain complete historical visual authority.
* [ ] Normalized historical visual rows exactly project canonical schema-4 bytes.
* [ ] Current M8 edits never rewrite historical ShotRevisions.
* [ ] Exact Rerun never invokes current visual resolution.
* [ ] Exact Rerun source gate proves no reads of current M8 authority tables.
* [ ] Resolver query count is mechanically bounded at representative feature-film scale.
* [ ] M8 UI exposes authority without model-specific vocabulary.
* [ ] Current versus historical authority is visually explicit.
* [ ] Relationship-specific composite visual authority remains explicitly deferred.
* [ ] M8 introduces no model embeddings, LoRAs, adapter state, or Comfy identity.
* [ ] M8 makes no false claim of arbitrary-view spatial continuity.
* [ ] downgrade refuses to destroy meaningful M8/schema-4 state.
* [ ] full backend suite passes.
* [ ] full frontend suite/typecheck/build passes.
* [ ] final source gate confirms the frozen contract.

---

# 96. Handoff State

At M8 completion:

```text
Narrative / Semantic Truth
        ↓
Entity + EntityRevision
ContinuityFeature + effective value
        ↓
VisualFacet
stable visual concern
        ↓
VisualAnchor
exact semantic/design-state realization
        ↓
Approved VisualAnchorRevision
        ↓
Deterministic VisualReferencePack
        ↓
Immutable ShotRevision schema 4
        ↓
Historical Visual Provenance
```

The production meaning is:

```text
"The cut exists"
= semantic continuity

"This aspect of the cut must be visually controlled"
= VisualFacet

"For this exact wound state and this exact Eva design,
this approved reference pack defines the cut"
= state-specific approved VisualAnchorRevision

"Make this particular model preserve that authority"
= M9 realization

"Keep the world and camera geometrically consistent
through arbitrary viewpoints"
= M10 spatial continuity
```

The governing M8 rule is:

> Semantic truth defines what is true. VisualFacet defines what appearance concerns require control. Approved state-specific visual realization defines exactly what those concerns look like. ShotRevision freezes the authority that applied at capture time. Models only realize that authority downstream.
