# SoloRing Architecture Pattern Register

**Document:** SoloRing Architecture Pattern Register  
**Version:** 2.1  
**Created:** 2026-08-18  
**Revised:** 2026-09-01  
**Current implementation baseline:** M10F @ `6f5d9771e3e67fa4097b7b7babab238d1f57a57e`  
**Purpose:** Durable design reference for applying proven architectural patterns when a concrete SoloRing production problem arises, without importing non-SoloRing product vocabulary, schemas, subsystem boundaries, or authority models.

---

## 0. Governing rules

### 0.1 This register is not a backlog

This register is **not a roadmap**, **not an implementation plan**, and **not authorization to change the repository**.

A pattern enters implementation only when a real SoloRing product or production problem makes it relevant and the owning work is separately authorized.

The adoption path is:

```text
research observation / prior SoloRing lesson
        ↓
extract durable invariant
        ↓
translate into SoloRing-native vocabulary
        ↓
identify the actual SoloRing production problem
        ↓
apply only inside the authority boundary that owns that problem
        ↓
make the invariant testable
        ↓
source gate
```

The anti-pattern is:

```text
interesting implementation
        ↓
copy its nouns / object model / lifecycle
        ↓
reshape SoloRing around it
```

**SoloRing product semantics, authority boundaries, provenance, historical integrity, and filmmaker experience remain primary.**

### 0.2 Repository research-separation rule

External project names, product names, paper names, and implementation-specific research vocabulary do **not** belong in this register or in normative SoloRing repository artifacts.

Research may influence architecture only after translation into a SoloRing-native invariant.

```text
research source
    ↓
private comparative analysis
    ↓
SoloRing-native principle
    ↓
repository architecture
```

The repository records **what SoloRing requires**, not where the idea was observed.

### 0.3 Product-first architecture rule

Architecture exists to protect the film and the filmmaker's decisions, not to preserve earlier abstractions for their own sake.

```text
preserve existing contract
    when it still serves the product

migrate existing contract
    when a better product requires change

replace existing abstraction
    when it prevents the intended product
```

Historical data remains valid through explicit compatibility or migration whenever a foundational abstraction evolves.

### 0.4 Pattern-ID stability

Pattern identifiers are durable references. Version 2 retains all Version 1 pattern IDs `APR-001` through `APR-073`; existing IDs are not repurposed for unrelated meanings. New durable principles begin at `APR-080`.

### 0.5 Version 2.1 integration record

Version 2.1 preserves every Version 2.0 pattern and adds five binding production-world laws established by the accepted Product & Production Architecture v1.1 and its unchanged full-sequence pressure-test rerun.

The added patterns are:

```text
APR-100  one durable authority subject for continuity-significant occurrences
APR-101  explicit immutable Composition ↔ Spatial binding
APR-102  within-Shot state change ↔ persistent Shot/end handoff
APR-103  surviving addressable occurrence identity across composition publication
APR-104  compatibility evidence before reusable Production Revision substitution
```

These additions close authority seams exposed by the full-sequence product test. They do not authorize implementation, schema changes, publication, tagging, or milestone work.

---

# 1. Register semantics

## 1.1 Pattern statuses

| Status | Meaning |
|---|---|
| **ADOPTED** | Already embodied in implemented SoloRing architecture. |
| **BINDING** | Must be enforced when the owning subsystem is implemented or extended. |
| **CANDIDATE** | Strong pattern; apply only if the target production problem requires it. |
| **STUDY** | Useful direction requiring more product or implementation evidence before becoming a contract. |
| **REJECTED-AS-AUTHORITY** | The technique may be usable downstream, but it must not become SoloRing production authority. |

## 1.2 Pattern priority

Priority does **not** authorize work.

| Priority | Meaning |
|---|---|
| **P0** | Foundational correctness, authority, historical integrity, or feature-film continuity. |
| **P1** | Strong architecture, execution-safety, or production-scale pattern. |
| **P2** | Valuable product, performance, or tooling pattern. |
| **P3** | Exploratory; defer until a concrete problem exists. |

## 1.3 Required use

When designing or reviewing a SoloRing subsystem:

1. State the filmmaker-facing production problem first.
2. Identify which production facts require durable authority.
3. Search this register for matching trigger conditions.
4. Apply only patterns whose scope genuinely matches.
5. Translate the pattern into SoloRing-native contracts.
6. Define failure semantics before implementation.
7. Define historical behavior before adding mutable current-state behavior.
8. Define the proof required at source gate.
9. Do not create persistent schema merely to “implement a pattern.”
10. If a relevant pattern is intentionally not applied, record why.
11. Update this register only when architecture actually changes or a durable lesson is established.

---

# 2. Vocabulary and architectural sovereignty

## APR-001 — Preserve SoloRing vocabulary

**Status:** BINDING  
**Priority:** P0  
**Area:** Governance / architecture

### Invariant

Persistent SoloRing concepts must be named according to SoloRing's own production domain.

### Rationale

Vocabulary determines architecture. Imported nouns often carry hidden assumptions about authority, lifecycle, mutability, versioning, and execution.

### Gate

Every new persistent noun must answer:

1. What SoloRing production fact does this represent?
2. Which SoloRing authority owns it?
3. Why can an existing SoloRing concept not represent it?
4. Would the concept still make sense if the current implementation technology disappeared?

---

## APR-002 — Extract principles before adopting mechanisms

**Status:** BINDING  
**Priority:** P1  
**Area:** Governance / design method

### Invariant

Borrow the **reason a mechanism works**, not the mechanism by default.

### Example

Observation:

```text
an execution system can seek directly to a target temporal position
```

SoloRing principle:

```text
authoritative temporal state should be resolvable directly at a target
without depending on accumulated playback history
```

### Failure mode

Copying a mechanism whose constraints belong to another implementation domain.

---

## APR-003 — Creative / production authority points downward

**Status:** ADOPTED / BINDING for future layers  
**Priority:** P0  
**Area:** Authority boundaries

### Invariant

```text
SoloRing production authority
        ↓
captured immutable state
        ↓
production realization / materialization
        ↓
execution-specific observation
        ↓
executor
        ↓
derived result
```

Never automatically:

```text
derived result
        ↓
rewrites upstream production authority
```

### Current examples

- Shot state → ShotRevision → Generation execution.
- ContinuityFeature / transitions → effective state → immutable capture.
- EntityRevision identity remains independent of execution implementation.
- Model-specific realization stays below captured production state.

### Failure modes

- execution workflow becomes character identity;
- generated appearance becomes continuity truth because it exists;
- reconstructed geometry becomes canonical geometry without adoption;
- simulation outcome becomes story fact automatically;
- an execution/editor representation becomes production authority.

---

## APR-004 — External churn must be hidden behind SoloRing boundaries

**Status:** BINDING  
**Priority:** P1  
**Area:** Integration discipline

### Invariant

Fast-moving execution APIs, file formats, models, runtimes, and infrastructure must never shape durable SoloRing contracts directly.

### Required shape

```text
SoloRing stable contract
        ↓
adapter / materializer / compiler
        ↓
replaceable implementation
```

### Gate

Changing implementation technology must not require rewriting historical SoloRing production state.

---

# 3. Temporal state and continuity

## APR-010 — Random-access temporal resolution

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Narrative continuity

### Invariant

Effective state at a target narrative boundary is resolved **directly from canonical topology and eligible state transitions**, not by operationally replaying every prior Shot.

### Existing SoloRing realization

```text
current Project topology
+ semantic dependencies
+ active transitions
+ target Shot / boundary
        ↓
canonical narrative ordering
        ↓
eligible history
        ↓
effective state
```

### Apply when

Future temporal state is added: relationships, wardrobe evolution, damage, injury, environment state, physical state, lighting state, performance state, or other story-time facts.

### Failure modes

- correctness depends on visiting earlier Shots;
- mutable playback history becomes authority;
- timestamps substitute for narrative order where narrative order owns semantics.

---

## APR-011 — Position semantics must be explicit at boundaries

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Temporal semantics

### Invariant

Every temporal system must define whether state at a target boundary includes or excludes transitions at that same boundary.

### Existing rule

```text
transition_rank <= target Shot/start rank
```

Therefore:

- target Shot/start applies to target Shot;
- target Shot/end does not;
- prior Shot/end applies downstream.

### Gate

Boundary inclusion/exclusion is pinned by tests; it is never inferred from iteration behavior.

---

## APR-012 — One current-state resolver, one canonical builder

**Status:** ADOPTED / BINDING for extensions  
**Priority:** P0  
**Area:** State materialization

### Invariant

Inspection, hashing, readiness, capture, and future observation compilation must not develop independent interpretations of current production truth.

### Required conceptual shape

```text
authoritative current inputs
        ↓
one deterministic resolver
        ↓
one canonical materialized current state
        ↓
├── working-state projection
├── working hash
├── readiness
├── capture input
└── downstream observation input
```

### Failure modes

- Shot detail and capture resolve independently;
- preview and execution disagree semantically;
- duplicate canonicalization code drifts;
- one consumer silently omits a production-state source.

---

## APR-013 — Current-state and historical-state isolation

**Status:** ADOPTED / BINDING for future extensions  
**Priority:** P0  
**Area:** Historical integrity

### Invariant

Current topology, current approvals, and current transitions may resolve **current working state only**.

Historical state comes exclusively from captured immutable provenance.

### Required historical direction

```text
Generation
→ ShotRevision
→ captured production revisions
→ captured continuity state
→ captured spatial state
→ captured provenance
```

Never:

```text
historical execution
→ today's topology / approvals / transitions / latest revisions
```

### Failure semantics

Missing or inconsistent historical provenance is an invariant failure, not permission to consult current state.

---

## APR-014 — Resolved current state becomes historical fact at capture

**Status:** ADOPTED / BINDING for future state domains  
**Priority:** P0  
**Area:** Capture

### Invariant

Before capture, production state may be derived from mutable current topology.

After capture, the resolved result is immutable historical fact.

> Narrative and production state is resolved from mutable current topology only before capture. Once captured into a ShotRevision, that resolved state is historical fact and is never resolved again from current state.

---

## APR-015 — Explicit readiness before expensive execution

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Safety / API

### Invariant

SoloRing distinguishes:

```text
state exists
state is resolvable
state is safe to capture
state is safe to execute
```

rather than discovering known incompleteness halfway through expensive work.

### Apply when

Adding visual identity, reusable production realizations, world-state resolution, observation compilation, spatial state, editorial state, or delivery state.

---

## APR-016 — No empty higher-schema alternative

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Canonical history

### Invariant

Higher historical schema versions exist only when their additional semantic content exists.

### Rationale

Avoid multiple byte representations for the same semantic state.

---

## APR-017 — Corruption must never invent tie-breakers

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Determinism / invariants

### Invariant

If legal state guarantees uniqueness, corrupted state fails.

Never recover by silently ordering on incidental identifiers, creation timestamps, database iteration order, insertion order, or implementation-specific paths.

---

# 4. Immutability, provenance, and identity

## APR-020 — Capture immutable execution inputs

**Status:** ADOPTED / BINDING for future layers  
**Priority:** P0  
**Area:** Provenance

### Invariant

Execution consumes captured immutable inputs, not reconstructed mutable current state.

### Existing realization

- ShotRevision;
- GenerationInputs;
- captured workflow/execution specification;
- pinned executor identities;
- immutable byte identities;
- historical entity, continuity, and spatial dependencies.

---

## APR-021 — Content-addressed identity where bytes matter

**Status:** ADOPTED / BINDING for future byte-bearing layers  
**Priority:** P1  
**Area:** Integrity

### Invariant

Where exact bytes matter, retain stable content identity.

### Caution

Content identity proves **byte identity**, not semantic provenance or production identity by itself.

---

## APR-022 — Separate semantic provenance from incidental record identity

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Provenance

### Invariant

Semantic hashes include facts that change production meaning and exclude incidental record identity where recreated equivalent state should remain semantically equivalent.

Audit provenance may retain incidental identifiers separately.

---

## APR-023 — Fail closed on incomplete provenance

**Status:** ADOPTED / BINDING for future layers  
**Priority:** P0  
**Area:** Historical validation

### Invariant

If captured historical state is incomplete or inconsistent:

```text
fail
```

not:

```text
guess
fill from current state
regenerate silently
omit silently
```

---

## APR-024 — Provenance authority is a graph, not a filesystem convention

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Data model

### Invariant

SoloRing relationships define production provenance.

Files, directories, caches, object-store paths, and execution workspaces are storage or materialization mechanisms, not the production graph.

### Existing distinction

```text
Blob  = immutable byte identity
Asset = provenance identity
```

---

## APR-025 — Exact Rerun is historical execution isolation

**Status:** ADOPTED / BINDING for future state layers  
**Priority:** P0  
**Area:** Reproducibility

### Invariant

Exact Rerun uses the historical captured graph and must not invoke mutable current-state resolvers.

### Gate pattern

Make current-state resolution unavailable; Exact Rerun must still operate from captured history when all required historical material remains available.

---

## APR-026 — Logical reproducibility and byte reproducibility are different claims

**Status:** ADOPTED  
**Priority:** P1  
**Area:** Reproducibility

### Invariant

Distinguish at least:

1. same durable creative/production specification;
2. same captured execution specification;
3. same fully pinned execution environment;
4. same execution-path behavior;
5. byte-identical output.

A lower claim never silently implies a stronger one.

---

# 5. Transactions and concurrent mutation

## APR-030 — Derived writes require one authoritative transaction fence

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Concurrency

### Invariant

If a write depends on validation or derived current state, verification and write occur under one authority-preserving transaction.

### Required conceptual form

```text
one authoritative transaction
verify
resolve prospective state
validate
write
commit
```

---

## APR-031 — Read coherence is explicit, not assumed

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Concurrency / reads

### Invariant

Multi-query semantic reads that must represent one database moment use one explicit coherent read boundary.

### Apply when

- resolving current state;
- building capture inputs;
- computing working hashes;
- publishing production revisions;
- compiling observations from a coherent Shot state.

---

## APR-032 — Identical concurrent captures should converge

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Idempotency

### Invariant

If concurrent operations capture the same semantic state, they converge on one historical identity when the domain defines them as identical.

---

## APR-033 — Race proofs must prove the intended interleaving

**Status:** ADOPTED as source-gate method  
**Priority:** P0  
**Area:** Testing

### Invariant

A test named “race” mechanically establishes the contested ordering.

Arbitrary sleeps are not proof of the intended interleaving.

---

# 6. Execution, determinism, and performance

## APR-040 — Inspection and final execution derive from the same authority

**Status:** ADOPTED / BINDING for future layers  
**Priority:** P1  
**Area:** Preview / execution parity

### Invariant

Human-visible current state and final execution state derive from the same canonical SoloRing production state.

This does **not** require the same rendering implementation. It requires the same authoritative semantics.

---

## APR-041 — Successful process execution is not successful production output

**Status:** ADOPTED / BINDING for future media layers  
**Priority:** P0  
**Area:** Quality control

### Invariant

```text
process exited successfully
≠
output satisfies SoloRing production contract
```

### Future application examples

- expected streams/frames exist;
- duration/frame count is correct;
- output is nonempty and decodable;
- continuity constraints are satisfied;
- required identities are preserved;
- delivery profile is valid.

---

## APR-042 — Optimized paths must have a correctness reference

**Status:** CANDIDATE  
**Priority:** P1  
**Area:** Performance

### Invariant

When introducing a faster path that may alter semantics or bytes:

```text
authoritative reference behavior
        ↓
optimized path
        ↓
equivalence proof
        ↓
fallback or fail on disagreement
```

Do not build duplicate reference machinery when an optimization creates no meaningful correctness risk.

---

## APR-043 — Determinism should become statically checkable where practical

**Status:** CANDIDATE  
**Priority:** P2  
**Area:** Tooling / audit

### Invariant

Known nondeterministic or historically unsafe dependencies should be detectable before execution when practical.

### Candidate checks

- current-state resolver referenced by historical path;
- timestamps used as semantic ordering;
- unseeded randomness in canonical materialization;
- mutable locations embedded as production identity;
- noncanonical serialization/hash pairs;
- unknown dependency classes silently omitted from capture.

---

## APR-044 — Bound query count; allow row processing to scale

**Status:** ADOPTED  
**Priority:** P1  
**Area:** Performance

### Invariant

Feature-film scale should increase data volume, not database round trips per item.

### Apply when

Adding production-world state, visual state, relations, composition, instances, or sequence-level continuity.

---

## APR-045 — Unknown execution dependencies fail safe

**Status:** BINDING for future multi-artifact packaging  
**Priority:** P1  
**Area:** Execution integrity

### Invariant

If an execution packager encounters an unrecognized dependency class, prefer explicit refusal or conservative inclusion over silent omission.

---

# 7. Human interfaces and agent behavior

## APR-050 — Structured interfaces expose authority; they do not replace it

**Status:** BINDING  
**Priority:** P1  
**Area:** UI

### Invariant

A visual editor, inspector, timeline, scene view, graph, or other interface is a projection/manipulation surface over authoritative SoloRing state.

It is not the authority itself.

---

## APR-051 — Unresolved state must be shown honestly

**Status:** ADOPTED / BINDING for all future UI  
**Priority:** P0  
**Area:** UI / trust

### Invariant

Never fabricate readiness, match/differs verdicts, working hashes, provenance completeness, confidence, or historical recoverability.

If SoloRing does not know, the interface must say so.

---

## APR-052 — Agent procedures are production roles, not authority

**Status:** BINDING for agent expansion  
**Priority:** P1  
**Area:** Agent architecture

### Invariant

Agents may reason, author, reconstruct, generate, inspect, rank, or propose changes, but their outputs cross the same SoloRing validation and adoption boundaries as any other candidate source.

### Failure modes

- agent memory becomes production truth;
- agent-authored code mutates canonical world state without validation;
- agent prompt context substitutes for captured provenance.

---

## APR-053 — Package operational knowledge separately from durable state

**Status:** CANDIDATE  
**Priority:** P2  
**Area:** Agent/tooling design

### Invariant

Instructions, heuristics, recipes, role-specific knowledge, and execution tactics may evolve quickly without mutating historical production state.

---

# 8. Feature-film continuity patterns

## APR-060 — Semantic production fact precedes visual realization

**Status:** ADOPTED / BINDING for later layers  
**Priority:** P0  
**Area:** Feature-film continuity

### Invariant

A production fact such as:

```text
Eva has a left-forehead cut
```

exists independently of the mechanism that renders it.

### Required direction

```text
ContinuityFeature state
        ↓
captured ShotRevision state
        ↓
approved / generated visual realization
        ↓
execution
```

### Failure mode

The first generated appearance becomes the only definition of the fact by accident.

---

## APR-061 — Approved visual identity must be explicit

**Status:** ADOPTED / BINDING for extension  
**Priority:** P0  
**Area:** Visual continuity

### Invariant

Feature-film visual continuity requires approved, inspectable visual identity rather than prompt-only descriptions.

### Applies to

- character appearance;
- location/set identity;
- wardrobe state;
- prop identity;
- injury or damage realization;
- other continuity-critical visible identity.

### Restraint

Approved visual identity is not automatically a reusable physical production realization. Those are separate concerns.

---

## APR-062 — Model-specific realization stays below captured semantic state

**Status:** ADOPTED / BINDING for future renderers  
**Priority:** P0  
**Area:** Generative realization

### Invariant

```text
SoloRing semantic + visual + spatial production state
        ↓
execution-specific conditioning / materialization
        ↓
executor
```

A model-specific conditioning representation must not become the durable world-state schema.

---

## APR-063 — Spatial continuity requires an authoritative world representation

**Status:** ADOPTED / BINDING for extension  
**Priority:** P0  
**Area:** Spatial continuity

### Invariant

A reusable location cannot be guaranteed by repeatedly describing the same location.

SoloRing requires explicit authoritative spatial facts sufficient to constrain repeated Shots.

### Restraint

Spatial authority does not imply that any one physical representation technology becomes authority.

---

## APR-064 — Post-production correction is downstream of continuity authority

**Status:** BINDING concept  
**Priority:** P1  
**Area:** Corrections / finishing

### Invariant

Tracking, masking, compositing, grading, paint, or other downstream correction may repair a Shot, but does not redefine the underlying story or production fact automatically.

---

## APR-065 — Random-access frame-addressable production state

**Status:** STUDY  
**Priority:** P3  
**Area:** Performance / editorial future

### Idea

Future systems may benefit from asking:

```text
What is the authoritative production state at frame N?
```

without replaying prior frames.

### Restraint

Do not create per-frame authority merely because an executor uses frames.

---

## APR-066 — Editorial and finishing authority must be designed later from first principles

**Status:** STUDY / scope boundary  
**Priority:** P3  
**Area:** Editorial / finishing

### Invariant

Approved Takes will eventually feed editorial, graphics, grading, sound, corrections, and delivery.

Those domains must preserve SoloRing provenance and authority direction without being prematurely absorbed into continuity, asset, or renderer schemas.

---

## APR-067 — Color management authority is distinct from creative grading controls

**Status:** CANDIDATE  
**Priority:** P2  
**Area:** Color

### Invariant

Creative look decisions and technical color-management transforms are separate production concerns.

---

## APR-068 — Tracking/roto geometry supports continuity; it does not define it

**Status:** CANDIDATE  
**Priority:** P2  
**Area:** Corrections / geometry

### Invariant

Tracking determines **where/how** a correction is applied.

Continuity state determines **what is true**.

---

# 9. Source-gate and audit patterns

## APR-070 — Semantic source gates precede publication

**Status:** ADOPTED  
**Priority:** P0  
**Area:** Governance

### Invariant

Implementation reports are not closure.

Closure requires source inspection and evidence against the frozen contract before publication.

---

## APR-071 — Supplied evidence and independently reproduced evidence stay distinct

**Status:** ADOPTED  
**Priority:** P1  
**Area:** Audit honesty

### Invariant

Never relabel supplied results as independently reproduced when the audit environment did not execute them.

---

## APR-072 — Test names must match what they prove

**Status:** ADOPTED  
**Priority:** P1  
**Area:** Testing

### Invariant

A test named after a race, historical-isolation condition, scale property, winning transition, or other semantic claim must mechanically establish that exact condition.

---

## APR-073 — Artifact fidelity is part of closure

**Status:** ADOPTED  
**Priority:** P1  
**Area:** Release evidence

### Invariant

Closure artifacts faithfully represent tracked source bytes and paths.

### Gate examples

- cryptographic digest;
- entry count;
- archive integrity;
- exact delta;
- filename fidelity;
- source-blob equality where applicable.

---

# 10. Production-world patterns

## APR-080 — Creation does not imply adoption

**Status:** BINDING  
**Priority:** P0  
**Area:** Production authority

### Invariant

Generated, reconstructed, simulated, imported, manually authored, or agent-authored results are **candidates** until explicitly adopted into SoloRing production authority.

### Required lifecycle

```text
creation source
        ↓
candidate
        ↓
inspection / validation
        ↓
explicit adoption
        ↓
immutable production revision
```

### Consequences

- successful generation is not approval;
- successful import is not approval;
- physically plausible simulation is not narrative truth;
- reconstruction confidence is not identity authority;
- creative invention is valid once the filmmaker explicitly adopts it.

---

## APR-081 — Production identity is independent of representation

**Status:** BINDING  
**Priority:** P0  
**Area:** Reusable production assets

### Invariant

A reusable production revision is not identical to any one file, scene package, mesh encoding, render cache, proxy, point representation, or other consumer representation.

### Required shape

```text
Production Revision
        ↓
├── Representation A
├── Representation B
└── Representation C
```

The production revision survives representation replacement.

### Related rule

Storage decomposition, collaboration decomposition, streaming decomposition, and optimized execution decomposition do not redefine authoritative composition or production identity.

---

## APR-082 — Production identity is independent of derivation

**Status:** BINDING  
**Priority:** P0  
**Area:** Provenance / reusable assets

### Invariant

What an approved production revision **is** is separate from how it was created.

```text
Production Revision
        ≠
Derivation
```

Derivation may record source material, authoring steps, models, tools, parameters, edits, runtime, and other creation provenance.

### Consequence

Different derivations may converge on equivalent/shared bytes without collapsing provenance identity; different representations may realize one production revision without becoming separate production objects.

---

## APR-083 — Published revisions are immutable and consumption-closed

**Status:** BINDING  
**Priority:** P0  
**Area:** Publication / historical reuse

### Invariant

Once adopted/published, a production revision is immutable and retains the exact dependencies required for its declared downstream use.

SoloRing distinguishes:

```text
CONSUMPTION CLOSURE
what is required to use the approved revision

DERIVATION CLOSURE
what is required to recreate it from its creation process
```

Historical execution normally consumes the retained production revision and its consumption closure. It does **not** rerun the old creator and hope to recreate the asset.

A published revision must not depend on untracked local working state.

---

## APR-084 — Coherent production objects may bind independently revisioned realizations

**Status:** CANDIDATE  
**Priority:** P1  
**Area:** Production realization

### Invariant

One filmmaker-facing production object may coherently bind several independently identifiable realization domains when independent lifecycle, reuse, or historical capture requires it.

Possible domains include:

```text
geometry realization
look realization
rig / deformation realization
groom / wardrobe realization
other physical production realizations
```

### Restraint

Do not expose unnecessary internal revision complexity to the filmmaker. Separate identities only where independent authority or lifecycle genuinely requires them.

---

## APR-085 — Composition references exact production identities

**Status:** BINDING  
**Priority:** P0  
**Area:** Scene / set composition

### Invariant

Reusable sets/scenes are compositions of exact reusable production revisions and instances.

```text
Composition Revision
        ↓
references exact Production Revisions
        ↓
places / groups / binds instances
```

The composition does not redefine referenced asset identity merely by embedding or copying a representation.

Nested reusable assemblies are allowed when the product requires them, but nesting must not obscure exact dependency identity.

---

## APR-086 — Instance identity follows production significance, not representation hierarchy

**Status:** BINDING core / CANDIDATE bulk extension  
**Priority:** P0  
**Area:** Composition / identity

### Invariant

A continuity-significant instance has durable identity independent of display name, hierarchy path, scene namespace, storage path, import order, or renderer label.

Not every repeated element requires such identity.

```text
ADDRESSABLE INSTANCE
continuity-significant; individually referenceable

BULK / PROCEDURAL INSTANCE
prototype + deterministic placement; not individually authoritative by default
```

A bulk instance may be promoted when it becomes production-significant.

---

## APR-087 — Edit scope and promotion target are explicit

**Status:** BINDING  
**Priority:** P0  
**Area:** Product / authoring

### Invariant

When one visible edit could have multiple production meanings, SoloRing must not silently choose the propagation target.

Possible scopes may include:

```text
this instance
this Shot
this story-time state
this composition working state
this reusable production object
```

A useful local change may become a reusable variation or new published revision only through explicit promotion.

When a linked object must become independent, SoloRing preserves lineage through an explicit fork/derivation rather than creating an untracked loose object.

---

## APR-088 — Overrides are typed by authority

**Status:** BINDING  
**Priority:** P0  
**Area:** Composition / authority

### Invariant

SoloRing does not use arbitrary property overriding as a universal escape hatch.

An override mechanism may change only facts owned by its declared authority domain.

A Shot-local composition overlay may, for example, alter:

```text
instance transform
visibility
replacement selection
temporary dressing membership
```

but must not silently:

```text
rewrite character identity
change canonical topology bytes
change continuity facts owned upstream
replace approved visual identity
```

---

## APR-089 — Persistent world state exists independently of observations

**Status:** BINDING  
**Priority:** P0  
**Area:** World continuity

### Invariant

A production fact continues to exist while off-screen.

```text
world state
    ≠
latest generated frame
```

Examples include injuries, damage, doors, displaced props, wardrobe state, knowledge, possession, and other persistent story facts.

A Shot resolves world state at its **story-time position**, independent of editorial presentation order. This supports flashbacks, parallel action, and nonlinear editing without using Shot output order as world chronology.

### Continuity decomposition

SoloRing distinguishes:

```text
FRAME CONTINUITY
immediate visual/temporal carry-over

PERFORMANCE CONTINUITY
where subjects are and what they are doing

WORLD-STATE CONTINUITY
persistent facts that remain true on or off screen
```

No one mechanism substitutes for all three.

---

## APR-090 — Geometry, appearance, motion, and physical relationships remain separable authorities

**Status:** BINDING concept  
**Priority:** P0  
**Area:** Production realization / motion / physics

### Invariant

A reusable object's physical shape, appearance realization, world-space trajectory, local deformation/performance, and physical relationships are related but not inherently the same identity.

For deforming subjects, distinguish:

```text
global world-space placement / trajectory
        +
local shape / pose / deformation over time
```

A reconstructed deformation sequence may be a valid immutable performance without being a reusable animator-controllable rig.

Physical relationships such as support, contact, attachment, containment, or grounding must distinguish status such as:

```text
INFERRED
VALIDATED
AUTHORITATIVE
```

A physical rule or simulation outcome is downstream of production authority until explicitly adopted as story/performance truth.

---

## APR-091 — Renderer observations are compiled from authoritative production state

**Status:** BINDING  
**Priority:** P0  
**Area:** Rendering / generation boundary

### Invariant

Renderer-specific control artifacts are derived from one coherent resolved production state through an explicit observation/materialization boundary.

```text
resolved Production World + Shot state
        ↓
World Observation Compiler
        ↓
renderer-specific observation contract
        ↓
executor
```

Possible observation artifacts include structural renders, depth, masks, motion cues, instance identifiers, geometry projections, appearance references, or text materializations.

The compiler is downstream of authority and can evolve independently of the production model.

---

## APR-092 — Observation artifacts are disposable derivatives, not production authority

**Status:** BINDING  
**Priority:** P0  
**Area:** Rendering boundary

### Invariant

Depth maps, masks, conditioning videos, structural renders, prompts, caches, latent inputs, and similar renderer controls may be captured for execution reproducibility, but do not become the canonical production world merely because an executor consumed them.

Generated visual refinement likewise does not repair or update underlying production geometry, world state, assets, or composition unless separately adopted through the owning authority path.

---

## APR-093 — Different properties may have different authoritative sources

**Status:** BINDING  
**Priority:** P0  
**Area:** Multi-authority rendering

### Invariant

No single conditioning representation is required to describe every production fact.

Different domains may own different properties of the final observation:

```text
camera / spatial placement
appearance / identity
continuity state
performance / motion
shot intent
physical relationships
```

The observation compiler resolves these domains before execution.

### Failure mode

A giant prompt, one image, or one execution representation becomes the de facto owner of every property.

---

## APR-094 — Generative freedom is explicit, bounded, and adjustable by Shot

**Status:** BINDING concept / CANDIDATE control levels  
**Priority:** P0  
**Area:** Generative rendering

### Invariant

The executor may infer unconstrained detail only inside an explicitly permitted envelope.

A production contract should be able to distinguish conceptually:

```text
must preserve exactly
must preserve structurally
must preserve identity / appearance
may vary within bounds
may be freely inferred
```

Different Shots may use different observation richness or control bandwidth without changing authoritative production truth.

This allows production effort to concentrate on hero and continuity-critical elements while permitting more generative freedom elsewhere.

---

## APR-095 — Structural truth need not be photorealistically complete

**Status:** CANDIDATE  
**Priority:** P1  
**Area:** Physical realization / rendering

### Invariant

A reusable physical realization is sufficient when it reliably constrains the intended downstream executions; it need not necessarily encode every final visual detail itself.

### Restraint

The minimum sufficient representation is a product/evidence question, not permission to omit continuity-critical structure.

Production identity remains above whichever physical representation supplies the required constraints.

---

## APR-096 — Reconstruction is inverse production, not automatic authority

**Status:** BINDING  
**Priority:** P0  
**Area:** Reconstruction / candidate worlds

### Invariant

Reconstruction from images/video may propose objects, geometry, camera, motion, deformation, lighting, and physical relationships, but all outputs remain candidate production state until adopted.

Recognition/tracking labels are observations, not SoloRing identity.

A reconstructed artifact may mix evidentiary origins such as:

```text
multi-view observed
single-view observed
geometrically inferred
generatively completed
unobserved / synthesized
```

When the production decision depends on that distinction, SoloRing must preserve enough provenance to expose it.

Creative invention is acceptable after explicit adoption; invention without adoption is not authority.

---

## APR-097 — Derived outputs never bootstrap authority automatically

**Status:** BINDING  
**Priority:** P0  
**Area:** Feedback loops

### Invariant

A generated, refined, simulated, or reconstructed result may become input to another candidate-producing process, but its invented content must never climb into authority automatically.

```text
derived result
        ↓
new candidate
        ↓
inspection / validation
        ↓
explicit adoption
        ↓
new production revision
```

This rule prevents self-reinforcing hallucinations from acquiring false authority through repeated processing.

---

## APR-098 — Working references may track; published and captured history is pinned

**Status:** BINDING concept  
**Priority:** P0  
**Area:** Versioning / UX / history

### Invariant

Current working state may support convenient references such as “current approved revision.” Capture and publication resolve them to exact immutable revisions.

```text
working tracking reference
        ↓
coherent resolution
        ↓
exact revision
        ↓
published/captured history
```

When a newer approved reusable revision becomes available, current work may detect and offer the update, but consequential propagation is explicit.

Published composition revisions and captured Shots never resynchronize themselves against newer source state.

---

## APR-099 — Historical compatibility translates execution, not history

**Status:** BINDING  
**Priority:** P0  
**Area:** Compatibility / Exact Rerun

### Invariant

If a current executor requires translation of an older captured representation, translation occurs in an execution-only compatibility view while the original historical identity remains immutable.

Never silently load, upgrade, rewrite, and then treat the rewritten artifact as the historical source.

This extends the existing historical-isolation rule to reusable production assets, compositions, and future observation formats.

---


## APR-100 — Continuity-significant occurrences resolve to one durable authority subject

**Status:** BINDING  
**Priority:** P0  
**Area:** Instance identity / world-state / spatial continuity

### Invariant

Every addressable production occurrence that can own persistent story/world state or independent spatial continuity resolves to **exactly one** durable authority subject recognized by the applicable state and spatial resolvers.

The subject may be:

```text
an existing CreativeEntity identity

or

a durable addressable Production Instance identity
```

If an occurrence already realizes an exact CreativeEntity occurrence, the CreativeEntity remains the authority subject; SoloRing does not create a duplicate competing subject.

A production-only occurrence may use its durable Production Instance identity when it needs independent persistent state or spatial continuity.

### Forbidden identity substitutes

The authority subject is never inferred from:

```text
display name
hierarchy path
array position
file/storage path
representation namespace
renderer label
transform proximity
```

### Gate

A continuity-significant occurrence without one unique durable authority subject is not ready for capture or execution.

---

## APR-101 — Composition-to-spatial agreement is an explicit immutable binding

**Status:** BINDING  
**Priority:** P0  
**Area:** Composition / spatial integration

### Invariant

A published Composition Revision and an applicable SpatialWorldRevision remain distinct authorities, but every authority-bound occurrence shared between them is joined by one mechanically provable, versioned binding.

The binding must be sufficient to determine at least:

```text
which exact production instance realizes each required spatial subject
which authority owns placement
how realization basis / origin / orientation / units / scale are interpreted
whether required bindings are complete and unique
whether the exact Production Revision is compatible with the binding
```

### Historical rule

Preview, capture, and final observation compilation resolve the same binding. Captured history pins the exact binding identity/value, or exact immutable inputs plus a versioned deterministic rule sufficient to reconstruct the same value without consulting current state.

### Failure mode

Missing, duplicated, incompatible, or preview/final-divergent bindings block publication/readiness. Implementation order never chooses a winner.

---

## APR-102 — Within-Shot state changes require an explicit persistent handoff

**Status:** BINDING  
**Priority:** P0  
**Area:** Temporal continuity / performance handoff

### Invariant

When a production fact changes at a specific time inside a Shot, SoloRing distinguishes:

```text
Shot-start resolved state
        +
Shot-relative event / performance timing
        +
explicit Shot/end persistent transition when the consequence survives downstream
```

Shot-relative timing authority and persistent terminal-state authority are separate facts and may have different owning domains. Capture must bind them coherently.

### Rules

- a Shot-start change is owned by the existing Shot/start boundary transition rather than a redundant time-zero event;
- a genuine intra-Shot event requires valid Shot-relative timing within the Shot duration;
- the event targets the same durable authority subject as its downstream state;
- generated pixels do not author the transition;
- approving a Take does not automatically adopt the persistent consequence;
- if persistence is intended, event terminal state and explicit Shot/end transition agree exactly.

### Restraint

This pattern does not require per-frame database authority.

---

## APR-103 — Surviving addressable occurrences retain identity across composition publication

**Status:** BINDING  
**Priority:** P0  
**Area:** Composition evolution / instance identity

### Invariant

Publishing a new Composition Revision preserves the durable identity of every surviving addressable occurrence by default.

Normal changes that do **not** mint a new occurrence identity include:

```text
compatible Production Revision update
representation update
compatible look / realization update
composition-owned transform/configuration update
Shot-local source substitution
```

Identity changes require an explicit lineage-bearing operation, for example:

```text
remove occurrence
replace as genuinely new occurrence
split occurrence
merge occurrences
fork occurrence identity
```

### Gate

Any state, spatial binding, relationship, Shot reference, or performance targeting an occurrence that is removed or identity-transformed must be resolved explicitly. SoloRing never retargets by name, path, proximity, or source similarity.

---

## APR-104 — Reusable Production Revision substitution requires compatibility evidence

**Status:** BINDING  
**Priority:** P0  
**Area:** Version substitution / cross-domain compatibility

### Invariant

A newer Production Revision may replace an older revision under existing composition, spatial, relationship, performance, look, or observation contracts only after explicit compatibility assessment for every relevant consumer.

The architectural verdict vocabulary is:

```text
COMPATIBLE_AS_IS
COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION
REQUIRES_REVIEW
INCOMPATIBLE
```

Compatibility assessment may need to cover:

```text
basis / handedness
origin / pivot
scale / dimensions / bounds
attachment / contact interfaces
rig / deformation contract
performance assumptions
look/material bindings
consumption closure
required representations
observation/compiler requirements
```

### Historical rule

A deterministic translation is allowed only when meaning-preserving for the consuming contract. Materially determinative translation identity is versioned and pinned wherever published/captured behavior depends on it.

Compatibility evidence never rewrites historical Production Revisions or captured history.

---

# 11. Explicit rejected authority transfers

These are architectural non-goals even if the corresponding techniques remain useful downstream.

## R-001 — Execution/editor project files as SoloRing production authority

**Disposition:** REJECTED-AS-AUTHORITY

Project files may be working or generated representations. SoloRing authority remains above them.

---

## R-002 — Model prompt text as continuity truth

**Disposition:** REJECTED-AS-AUTHORITY

Prompts materialize captured state; they do not define durable character, location, world-state, or continuity identity.

---

## R-003 — Filesystem cache/ledger as provenance authority

**Disposition:** REJECTED-AS-AUTHORITY

Caches may accelerate execution. SoloRing's provenance graph remains authoritative.

---

## R-004 — Incidental identifiers as semantic ordering fallback

**Disposition:** REJECTED-AS-AUTHORITY

Corrupt state fails explicitly rather than inventing order from incidental identifiers, timestamps, paths, or insertion behavior.

---

## R-005 — Generated/reconstructed/simulated output as automatic production truth

**Disposition:** REJECTED-AS-AUTHORITY

All such outputs enter through candidate → validation → adoption.

---

## R-006 — One representation technology as the definition of a production object

**Disposition:** REJECTED-AS-AUTHORITY

Production identity survives representation change.

---

## R-007 — Creation derivation as the only way to reuse a production object

**Disposition:** REJECTED-AS-AUTHORITY

Approved production artifacts are retained for consumption. Historical reuse does not depend on the continued availability of their original creator.

---

## R-008 — Current “latest approved” state inside captured history

**Disposition:** REJECTED-AS-AUTHORITY

Capture resolves current convenience references to exact immutable revisions.

---

## R-009 — One universal conditioning source as owner of every visual property

**Disposition:** REJECTED-AS-AUTHORITY

Different production facts may have different authorities. Rendering combines them downstream.

---

## R-010 — Editorial order as world chronology

**Disposition:** REJECTED-AS-AUTHORITY

Story-time/world-state chronology remains independent of presentation order.

---

# 12. Trigger index for future architecture work

This section is a lookup aid, not a roadmap.

| Production problem | Patterns to inspect first |
|---|---|
| Reusable set or prop | APR-080–088, APR-098–104 |
| Reusable character physical realization | APR-060–063, APR-080–084, APR-090 |
| Set composition / nested assemblies | APR-085–088, APR-100–104 |
| Shot-local versus global edits | APR-087–088, APR-102–103 |
| Persistent injury / damage / wardrobe | APR-010–014, APR-060, APR-089, APR-100, APR-102 |
| Flashbacks / nonlinear editorial | APR-010–014, APR-089 |
| Import footage as a candidate world | APR-080, APR-096–097 |
| Generated candidate asset | APR-080–084 |
| Simulation-driven performance | APR-080, APR-090, APR-097 |
| New generative renderer | APR-003–004, APR-062, APR-091–095, APR-098–099 |
| New renderer conditioning format | APR-004, APR-091–094 |
| Execution-backend upgrade | APR-004, APR-025–026, APR-092, APR-099, APR-104 |
| Exact historical rerun | APR-013–014, APR-020–026, APR-083, APR-098–104 |
| Feature-film-scale scene | APR-044, APR-085–086, APR-095 |
| Agent authoring | APR-052–053, APR-080, APR-087, APR-097 |
| Physical contact/support | APR-090 |
| Reconstruction confidence | APR-096–097 |
| Stateful addressable production occurrence | APR-086, APR-089–090, APR-100 |
| Composition ↔ spatial agreement | APR-085–088, APR-101 |
| Persistent fact changes inside a Shot | APR-010–014, APR-089–090, APR-102 |
| Composition revision preserves occurrence identity | APR-085–088, APR-098, APR-103 |
| Production Revision substitution / upgrade | APR-081–085, APR-098–099, APR-104 |

---

# 13. Product-level architectural test

A future SoloRing production architecture is not complete merely because its schemas are internally consistent.

It must support, without authority ambiguity or historical mutation, at least the following filmmaker operations:

```text
approve one character and reuse that identity across the film
approve one set and shoot it from arbitrary later cameras
replace one set component without rebuilding the entire set
publish a new composition revision while preserving surviving occurrence identities
change a persistent fact inside a Shot and hand the adopted consequence to downstream story state
make a change local to one Shot without mutating the canonical set
promote a useful local change into reusable production state
carry an injury or damage state through off-screen story time
return to an earlier story state for a flashback
update a reusable asset without changing captured historical Shots
import generated / reconstructed / simulated work as candidates
adopt only the parts the filmmaker accepts
render the same Shot through a different executor without redefining the Shot
rerun an old Shot from its exact captured production revisions
```

If the architecture makes any of these depend on hidden implementation conventions, mutable current state, or executor memory, the architecture is incomplete.

---

# 14. Summary invariant

The register can be reduced to one governing production direction:

```text
FILMMAKER INTENT
        ↓
SOLORING PRODUCTION AUTHORITY
        ↓
IMMUTABLE PRODUCTION REVISIONS + STORY/WORLD STATE
        ↓
SHOT RESOLUTION AND CAPTURE
        ↓
OBSERVATION / MATERIALIZATION
        ↓
RENDERING / GENERATION / SIMULATION / CORRECTION
        ↓
CANDIDATE RESULT
        ↓
REVIEW
        ↓
EXPLICIT ADOPTION WHEN THE RESULT SHOULD CHANGE PRODUCTION TRUTH
```

No downstream system gets to skip the adoption boundary and redefine the film by accident.
