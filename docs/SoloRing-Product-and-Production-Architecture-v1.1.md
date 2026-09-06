# SoloRing Product & Production Architecture

**Document:** SoloRing Product & Production Architecture  
**Version:** 1.1  
**Date:** 2026-09-01  
**Status:** Architecture synthesis — pressure-test corrections integrated; not an implementation plan and not implementation authorization  
**Predecessor baseline:** M10F @ `6f5d9771e3e67fa4097b7b7babab238d1f57a57e`  
**Normative foundation:** SoloRing Architecture Pattern Register v2.0  
**Purpose:** Define the product model, filmmaker experience, production-world architecture, authority boundaries, reusable-production model, story-time state model, Shot resolution contract, observation boundary, and the corrected contracts required by the standalone full-sequence product pressure test before implementation planning.

---

## v1.1 correction record

Version 1.1 is a narrow architecture correction produced after running the standalone **SoloRing Full-Sequence Product Pressure Test v1.0** against Version 1.0. The test scenario itself is not changed to make this architecture pass.

Version 1.1 closes exactly five load-bearing findings:

```text
CR-1  durable authority subject for continuity-significant Production Instances
CR-2  exact Composition Revision ↔ SpatialWorldRevision binding contract
CR-3  within-Shot state event ↔ Shot/end persistent-state handoff
CR-4  addressable instance identity across Composition Revision evolution
CR-5  Production Revision substitution compatibility verdict
```

It also makes five non-defect clarifications explicit:

```text
CL-1  human-readable story-time labels do not replace canonical narrative topology
CL-2  one derivation bundle can expose independently adoptable candidate outputs
CL-3  Shot-local source substitution preserves occurrence identity by default
CL-4  persistent consequences are reviewed/adopted separately from Take approval
CL-5  confidence is evidence, never acceptance authority
```

This revision intentionally does **not** freeze database table names, migration shapes, file formats, renderer technology, rig representation, simulation technology, or a universal relationship vocabulary. Those remain implementation/design work owned by later authorized milestones.

---

# 0. Executive mandate

SoloRing is a filmmaking system for one filmmaker or a very small team to build a persistent movie production and use changing execution technologies without asking those technologies to remember the film.

The product promise is:

> **Make a creative or production decision once, approve it explicitly, and rely on SoloRing to preserve its consequences everywhere they matter across the film.**

SoloRing is not fundamentally a shot generator. It is a persistent production system in which characters, locations, props, appearance, physical realization, story state, composition, staging, cameras, performances, and approved results can remain coherent over feature-film scale.

The governing production direction is:

```text
FILMMAKER INTENT
        ↓
SOLORING PRODUCTION AUTHORITY
        ↓
CANDIDATE CREATION / IMPORT / RECONSTRUCTION / SIMULATION
        ↓
INSPECTION + VALIDATION
        ↓
EXPLICIT ADOPTION
        ↓
IMMUTABLE PRODUCTION REVISIONS
        ↓
STORY-TIME RESOLUTION
        ↓
SHOT RESOLUTION + CAPTURE
        ↓
OBSERVATION / MATERIALIZATION
        ↓
EXECUTION
        ↓
TAKE CANDIDATE
        ↓
REVIEW
        ↓
APPROVAL OR REJECTION
```

No downstream result may redefine upstream production truth automatically.

This document defines architecture and product semantics only. It does not authorize repository mutation, schema migration, implementation, publication, tagging, release work, or a new milestone.

---

# 1. The product

## 1.1 What SoloRing is

SoloRing is a persistent film-production environment with four defining properties:

1. **The film has durable production memory.** What exists, what it looks like, where it is, what happened to it, and what version was approved do not live only in prompts or generated frames.
2. **Creation and truth are different states.** Anything may be proposed by a person, an agent, an importer, a reconstruction process, a simulator, or a generator, but production truth changes only through explicit adoption.
3. **Shots observe a persistent production world.** A Shot does not need to reinvent its characters, locations, prop state, or continuity facts from neighboring generated media.
4. **Execution technology is replaceable.** The production survives changes in renderers, models, conditioning formats, runtime environments, and materialization techniques.

The durable product is the movie production, not the current execution backend.

## 1.2 What SoloRing is not

SoloRing is not:

- a prompt notebook;
- a folder of generated clips;
- a model-specific workflow editor;
- a scene file treated as the canonical film database;
- a cache whose directory structure defines provenance;
- an agent memory treated as production truth;
- a single 3D representation treated as the definition of the world;
- a generator whose latest output silently becomes canon;
- a linear chain in which the previous Shot's pixels are the only memory of what happened.

Those mechanisms may participate in production, but none owns the film merely by participating.

---

# 2. The user

## 2.1 Primary user

The primary SoloRing user is a filmmaker: typically a writer-director, director-animator, virtual-production artist, or technically capable independent creator working alone or with a small team.

The user thinks in production terms:

```text
This is Eva.
This is the Grand Meridian lobby.
This is the desk we approved.
The cut happened before this Shot.
That chair was knocked over and stays there.
Use the same lobby from behind the desk.
Keep this change only in this Shot.
Use the new hair in future work, not in approved history.
Give me four Takes.
This Take is approved.
```

The user should not need to think primarily in storage paths, graph-node identifiers, model-specific conditioning fields, runtime caches, dependency fingerprints, database tables, or executor-specific artifacts.

## 2.2 User-facing mental model

The product should expose a compact filmmaking vocabulary:

| User concept | Product meaning |
|---|---|
| **Project** | The film production and its durable production graph. |
| **Character / Location / Prop / Other Entity** | Persistent story-world identity. |
| **State** | What is true about an entity or the world at a narrative time. |
| **Production Revision** | An immutable approved reusable production realization. |
| **Set / Composition** | A reusable assembly of exact production revisions and instances. |
| **Instance** | One addressable occurrence of a reusable object in a composition or Shot. |
| **Performance** | Approved or candidate motion, pose, deformation, expression, or action realization. |
| **Shot** | Current editable cinematic intent and staging for one view/time interval. |
| **ShotRevision** | Immutable capture of the complete production state used for execution. |
| **Take** | One candidate result of executing a ShotRevision. |
| **Approve** | Explicitly make a candidate the accepted production result or revision. |
| **Publish** | Freeze reusable production state into an immutable revision. |
| **Update** | Explicitly move current working references to a newer approved revision. |
| **Fork** | Create an independently evolving production identity while preserving lineage. |
| **History** | Immutable record of what a captured Shot or published revision actually used. |

Internal architecture may require finer distinctions, but the filmmaker should encounter them only when those distinctions change creative meaning.

---

# 3. Product experience principles

## 3.1 Directing rather than configuring infrastructure

The dominant interaction should be:

```text
choose story moment
open set
place or select characters
stage props
set camera
set performance intent
generate / animate / simulate
review Takes
approve
```

Execution details belong in advanced inspection and troubleshooting surfaces.

## 3.2 Explicit scope when an edit can propagate

If an edit could reasonably mean more than one thing, SoloRing must not silently choose the scope.

Example: the filmmaker moves Chair 7 while working on Shot 42.

Possible meanings include:

```text
this Shot only
this story-time state and downstream continuity
current working lobby composition
canonical reusable chair placement / composition
new reusable variation
```

The UI should make the propagation target explicit at the moment it becomes consequential.

## 3.3 Safe experimentation

The filmmaker should be free to improve current work without fear that historical Shots will mutate.

When a newer approved revision exists, current work may show:

```text
Update available
Chair v2 → Chair v3
14 current instances affected
38 working Shots affected
historical captured Shots unchanged
```

Applying the update creates new current/published state. It never rewrites immutable history.

## 3.4 Creation is cheap; adoption is consequential

SoloRing should encourage rapid candidate creation. The architecture becomes strict at the adoption boundary, not before it.

```text
Generate 8 candidates
Import a model
Build from reference media
Track motion
Run a simulation
Make a manual edit
        ↓
all are candidates
        ↓
review
        ↓
approve selected result
```

This allows creative speed without sacrificing authority integrity.

## 3.5 The product must show uncertainty honestly

A candidate may contain:

```text
observed information
inferred information
generated completion
low-confidence reconstruction
unverified contact
unconstrained background detail
```

SoloRing may summarize or visualize these distinctions where they affect a production decision. It must not present uncertain inferred state as confirmed production truth.

---

# 4. Architecture laws

The following laws are product-level consequences of the Architecture Pattern Register and are binding on future design.

## 4.1 Production authority points downward

```text
semantic / narrative authority
        ↓
visual / spatial / production authority
        ↓
immutable capture
        ↓
observation / materialization
        ↓
execution
        ↓
derived result
```

A derived result can become upstream production truth only through a new candidate → validation → explicit adoption cycle.

## 4.2 Creation does not imply adoption

Successful generation, import, reconstruction, tracking, simulation, or agent authoring does not make a result canonical.

## 4.3 Current state and historical state are different worlds

Current state may evolve. Historical state is read only from captured immutable provenance.

No historical read may silently consult current approvals, current tracking references, current compositions, current world state, or today's execution package to reinterpret the past.

## 4.4 Production identity is independent of representation

A production revision is not a file, scene package, mesh encoding, proxy, render cache, or viewport artifact.

Representations may come and go while the production identity remains the same.

## 4.5 Production identity is independent of derivation

The process that created an approved object is provenance, not the object's production identity.

A production revision may remain usable long after its original creation mechanism is unavailable.

## 4.6 Story-time state persists off-screen

A fact does not cease to exist because the camera stops looking at it.

The world at story time `t` is resolved independently of editorial presentation order.

## 4.7 Different properties can have different authorities

No universal prompt, image, 3D file, or conditioning packet owns every property.

For one Shot, for example:

```text
identity              ← semantic authority
injury existence      ← continuity/world-state authority
approved appearance   ← visual authority
world placement       ← spatial authority
local body performance← performance authority
camera                ← cinematic authority
fine incidental detail← allowed renderer inference
```

The execution layer combines them after authority resolution.

## 4.8 Observation is compiled from authority

Renderer controls are derived products.

```text
captured production state
        ↓
observation compiler
        ↓
renderer-specific controls
```

Depth, masks, structural renders, reference images, motion cues, prompts, geometry projections, and similar artifacts never become the world merely because they are useful to an executor.

## 4.9 Generative freedom is explicit

A renderer may infer detail only inside the envelope SoloRing permits for that Shot/property.

Conceptually, the production system must be able to distinguish:

```text
must preserve exactly
must preserve structurally
must preserve identity / appearance
may vary within defined bounds
may be freely inferred
```

## 4.10 Historical compatibility translates execution, not history

If current execution requires a compatibility translation of older captured data, the translation exists only in the execution view. Historical source identity and bytes remain immutable.

## 4.11 Stateful production occurrences resolve to one durable authority subject

Every addressable production occurrence that can own persistent story/world state or independent spatial continuity must resolve to exactly one durable authority subject recognized by the applicable state and spatial resolvers.

That subject may be:

```text
an existing CreativeEntity identity

or
a durable addressable Production Instance identity
```

but it may not be inferred from display names, hierarchy paths, array positions, file paths, or renderer labels.

If an addressable Production Instance already realizes an exact CreativeEntity occurrence, the existing CreativeEntity remains the authority subject; SoloRing does not create a competing duplicate subject. A production-only occurrence that requires persistent state may use its durable Production Instance identity as the subject.

## 4.12 Composition-to-spatial agreement is an explicit immutable contract

A published Composition Revision and a selected SpatialWorldRevision may remain distinct authorities, but any authority-bound occurrence shared between them must be joined by one mechanically provable, versioned binding.

The binding must prove at least:

```text
which exact production instance realizes each required spatial subject
which transform/placement domain is authoritative
how units, basis, origin, orientation, and scale are interpreted
whether required bindings are complete and unique
whether the exact Production Revision is compatible with the binding
```

Preview, capture, and final execution must resolve the same binding.

## 4.13 Within-Shot state changes require a persistent handoff contract

When a production fact changes at a specific time inside a Shot, SoloRing distinguishes:

```text
Shot-start resolved state
        +
Shot-local state-changing event / performance authority
        +
explicit Shot/end persistent transition when the consequence survives downstream
```

The Shot-local event may be sparse and time-addressed; SoloRing does not require per-frame database authority. If the event creates a persistent downstream fact, its declared terminal state and the explicit Shot/end transition must agree exactly.

## 4.14 Surviving addressable occurrences keep identity across composition publication

Publishing a new Composition Revision preserves the identity of every surviving addressable occurrence by default. Changing the referenced Production Revision, representation, look, or other compatible source realization does not mint a new occurrence identity.

Identity changes require an explicit operation such as removal, replacement-as-new-occurrence, split, merge, or occurrence fork, with lineage and affected-state diagnostics.

## 4.15 Reusable Production Revision substitution requires compatibility evidence

A newer Production Revision may replace an older one under existing composition, spatial, relationship, performance, or observation contracts only after an explicit compatibility assessment for each relevant consumer.

The architectural verdict vocabulary is:

```text
COMPATIBLE_AS_IS
COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION
REQUIRES_REVIEW
INCOMPATIBLE
```

A deterministic translation is allowed only when it is meaning-preserving for the consuming authority contract and is itself versioned/pinned wherever it materially affects published or captured behavior. Compatibility evidence never rewrites historical revisions.

---

# 5. Relationship to the implemented baseline

This architecture extends the existing SoloRing production chain rather than replacing it.

The original durable loop remains valid:

```text
Mutable Shot Working State
        ↓
Immutable ShotRevision
        ↓
Immutable Generation Request
        ↓
Durable execution lifecycle
        ↓
Durable output provenance
        ↓
Candidate Take
        ↓
Explicit approval
```

The baseline already establishes several critical invariants that remain foundational:

- Shot working state is separate from immutable ShotRevision history;
- Generation is a durable execution request rather than creative authority;
- Blob identity is immutable byte identity;
- Asset identity is provenance identity;
- GenerationInputs are historical immutable bindings;
- executor state is downstream of captured creative state;
- canon changes only through explicit approval/rejection;
- Exact Rerun is historical execution isolation;
- semantic continuity is resolved from narrative topology before capture;
- approved visual identity remains separate from model-specific realization;
- spatial/cinematic authority remains separate from renderer-specific realization;
- current spatial authority cannot be reconstructed from generated output;
- historical runtime compatibility does not rewrite captured history.

The new architecture adds the missing horizontal production model around these existing invariants.

---

# 6. The layered production model

SoloRing should be understood as a stack of authority and realization layers rather than one universal scene object.

```text
┌──────────────────────────────────────────────────────────────┐
│  A. STORY / SEMANTIC AUTHORITY                              │
│  identity, narrative facts, relationships, story-time state │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│  B. VISUAL + SPATIAL / CINEMATIC AUTHORITY                  │
│  approved appearance, world facts, staging, camera           │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│  C. REUSABLE PRODUCTION REALIZATION                         │
│  approved geometry/look/rig/etc. realizations and closures  │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│  D. COMPOSITION + INSTANCE ASSEMBLY                         │
│  exact reusable revisions, instances, typed local overlays  │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│  E. STORY-TIME + PERFORMANCE RESOLUTION                     │
│  persistent world state, effective performance, relations    │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│  F. SHOT REVISION                                           │
│  one coherent immutable production state for the Shot       │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│  G. OBSERVATION / EXECUTION                                 │
│  renderer-specific controls, execution spec, runtime         │
└──────────────────────────────────────────────────────────────┘
                           ↓
                       TAKE CANDIDATE
```

Higher layers may constrain lower layers. Lower layers never silently redefine higher ones.

---

# 7. Core conceptual model

This section defines architectural roles. It does not freeze database table names.

## 7.1 CreativeEntity and EntityRevision

Existing SoloRing semantic identity remains the upstream anchor for story-world entities such as characters, locations, props, and other continuity-significant subjects.

An EntityRevision answers:

> What exact semantic/design state of this entity is currently selected for this narrative or production context?

It does not have to contain renderable geometry.

## 7.2 Production Object

A **Production Object** is the filmmaker-facing reusable production identity associated with a physical or visual production realization.

Examples include:

```text
Eva production body/face realization
Grand Meridian reception desk
Lobby chandelier
Hotel chair
Lobby shell
Eva hair realization
Eva wardrobe realization
```

A Production Object is not automatically a new semantic story entity. It may realize an existing CreativeEntity, a part of one, or a production-only component whose identity matters for reuse.

The architecture must preserve this distinction so production modeling does not accidentally duplicate story identity.

## 7.3 Production Revision

A **Production Revision** is an immutable approved version of a Production Object.

It answers:

> What exact reusable production realization did the filmmaker approve for future composition and Shot use?

A Production Revision may bind independently versioned realization domains when genuinely required, for example:

```text
geometry realization
look realization
rig/deformation realization
groom realization
wardrobe realization
other physical production realization
```

The user-facing object should remain coherent even if internal realization identities differ.

## 7.4 Representation

A **Representation** is one consumer-oriented encoding of a Production Revision or Composition Revision.

Examples conceptually include:

```text
editable scene representation
viewport representation
renderer representation
proxy representation
optimized packed representation
simulation representation
```

Representation identity is downstream of production identity.

A representation can be replaced, regenerated, or made obsolete without changing which production revision the Shot used.

## 7.5 Derivation

A **Derivation** records how candidate or approved production content was created.

It may include:

```text
source references
source media
creation tool / agent / process
model or algorithm identity
parameters
runtime identity
manual edits
intermediate stages
validation events
```

Derivation is provenance, not production identity.

## 7.6 Consumption closure

A published Production Revision must retain everything required to use it for the downstream capabilities it declares.

```text
Production Revision
        ↓
consumption closure
        ├── required realization identities
        ├── required dependent production revisions
        ├── required byte identities
        └── required interpretation metadata
```

Historical execution normally consumes this retained closure.

## 7.7 Derivation closure

The derivation closure contains what would be required to recreate the revision from its original creation process.

It may be larger, less stable, or impossible to preserve fully.

The product must never make historical reuse depend on recreating an already approved artifact when the artifact itself can be retained.

## 7.8 Composition

A **Composition** is a reusable assembly of exact Production Revisions and/or nested Composition Revisions.

It answers:

> What reusable production things are assembled here, which instance is which, and what production-local configuration applies?

A Composition may represent a set, room, vehicle interior, prop assembly, modular environment region, or other reusable aggregate.

## 7.9 Composition Revision

A **Composition Revision** is an immutable published composition.

It pins:

```text
exact referenced Production Revisions
exact nested Composition Revisions
addressable instance identities
composition-owned transforms/configuration
typed overlays or optional groups
dependency closure
```

Publishing a new Composition Revision never mutates an older one.

## 7.10 Instance

An **addressable production instance** is one durable occurrence of a reusable Production Revision or nested Composition Revision when the film may need to refer to that exact occurrence later.

Examples:

```text
chair-07 in the Grand Meridian lobby
Reception desk instance
Lobby vase instance
Eva's hotel-room suitcase instance
```

Instance identity is independent of display name, hierarchy path, scene namespace, file location, import order, source Production Revision, or executor label.

### 7.10.1 Authority-subject binding

An addressable occurrence does not automatically become a semantic CreativeEntity. SoloRing distinguishes three cases:

```text
ENTITY-BOUND INSTANCE
The occurrence realizes an existing CreativeEntity occurrence.
The CreativeEntity is the state/spatial authority subject.

INSTANCE-BOUND SUBJECT
The occurrence has no independent story-semantic identity, but it must own
persistent production state or independent spatial continuity.
The durable Production Instance identity is the state/spatial authority subject.

COMPOSITION-LOCAL INSTANCE
The occurrence is addressable for editing/reuse but owns no independent
persistent state or spatial continuity yet.
```

A stateful occurrence must have exactly one effective subject. The subject binding is explicit and historically capturable; it is never reconstructed from a name, path, transform proximity, or renderer object label.

If a composition-local occurrence later becomes continuity-significant, promotion establishes its durable authority-subject role explicitly without rewriting prior published revisions.

### 7.10.2 Identity across Composition Revisions

Addressable instance identity belongs to the reusable composition lineage, not to one revision row. A new Composition Revision references the same stable instance identity for every surviving occurrence.

Normal changes that preserve occurrence identity include:

```text
Production Revision update
representation update
compatible look/realization update
transform/configuration update inside the owning authority rules
Shot-local source substitution
```

Identity-changing operations are explicit:

```text
remove occurrence
replace as genuinely new occurrence
split occurrence
merge occurrences
fork occurrence identity
```

They preserve inspectable lineage and require diagnostics for any persistent state, spatial binding, relationship, Shot reference, or performance that targeted the old identity. Nothing retargets automatically.

### Bulk/procedural instance

High-volume repeated elements may remain prototype + deterministic placement data when no continuity decision addresses each item individually.

Examples might include dense vegetation, debris fields, distant crowd population, or repeated architectural detail.

If one bulk element becomes production-significant, SoloRing may promote it into an addressable instance while preserving provenance.

## 7.11 World state

**World state** is the set of persistent story-time facts that remain true independently of current visibility.

Examples:

```text
vase-main broken
chair-07 displaced
door-main unlocked
Eva jacket wet
Eva forehead injury fresh
Eva bag no longer carried
```

Every persistent state record targets a durable authority subject. Depending on production meaning, that subject is either an existing CreativeEntity or an explicitly stateful addressable Production Instance. Display names and composition paths are never state identity.

World state is not the latest rendered frame.

The authoritative temporal coordinate remains SoloRing's canonical narrative topology unless a future separately designed story-clock domain is adopted. Human-readable clock labels such as `22:05` may annotate the production, but they do not silently replace sequence/scene/Shot boundary ordering.

## 7.12 Performance

A **Performance** is time-varying production realization for a subject.

SoloRing must distinguish at least:

```text
global world-space placement / trajectory
        +
local pose / articulation / deformation / expression
```

A performance may originate from manual animation, tracking, reconstruction, simulation, generative creation, or another source. All such origins produce candidates until adopted.

A captured deformation sequence may be a valid Performance Revision without being a reusable animator-controllable rig.

### 7.12.1 Shot-local state-changing event

A **Shot-local state-changing event** is sparse Shot-relative production authority describing when a persistent or continuity-significant fact changes inside the Shot. It is not generated-frame analysis and is not a requirement for every action.

Conceptually it preserves:

```text
authority subject
owning state/relationship domain
Shot-relative time
pre-event state when needed for validation
terminal state/consequence
source performance/event provenance
whether downstream persistence is intended
```

For an event at Shot start, the existing Shot/start transition should own the state rather than creating a redundant time-zero event. A genuinely intra-Shot event requires a known Shot duration and a valid Shot-relative time.

If downstream persistence is intended, the owning state domain must also contain an explicit Shot/end transition whose terminal value agrees with the event. The event explains **when the Shot changes**; the Shot/end transition explains **what subsequent narrative state inherits**.

## 7.13 Physical relationship

A physical relationship describes production-relevant structure such as support, attachment, containment, contact, grounding, or other constrained relation.

Status must be explicit where it matters:

```text
INFERRED
VALIDATED
AUTHORITATIVE
```

A simulation result or reconstruction inference does not automatically become authoritative story state.

## 7.14 Observation

An **Observation** is a renderer-facing view of captured production truth.

It can contain exactly the control information useful to a particular executor, such as:

```text
camera projection
structural render
depth
surface or instance masks
motion cues
geometry projections
appearance references
text materialization
other deterministic controls
```

Observation artifacts are downstream derivatives.

## 7.15 Candidate

A **Candidate** is any unadopted proposed production result.

Candidate sources are intentionally technology-neutral:

```text
manual authoring
agent authoring
generation
import
reconstruction
tracking
simulation
conversion
repair
```

The source never bypasses adoption.

---

# 8. Authority ownership

## 8.1 Semantic authority

Owns:

```text
who / what something is
narrative facts
continuity-feature state
relationships with story meaning
story-time transitions
```

It does not own renderer implementation.

## 8.2 Visual authority

Owns approved appearance identity and continuity-critical visible realization.

It does not own world-space placement simply because a reference image depicts placement.

## 8.3 Spatial / cinematic authority

Owns reusable world-space facts, continuity-relevant placement, camera constraints, and cinematic geometry already established by the spatial architecture.

It does not own renderable mesh bytes merely because a renderer needs geometry.

## 8.4 Production-realization authority

Owns the approved reusable physical/look/rig/etc. production revisions selected to realize higher authority.

It cannot contradict higher semantic, visual, or spatial authority.

## 8.5 Composition authority

Owns:

```text
which exact reusable revisions are assembled
which addressable instance is which
nested assembly identity
composition-local realization placement/configuration
optional production groups
typed composition overrides
```

Composition does not become a universal override layer over all authority domains.

## 8.6 Performance authority

Owns approved time-varying local subject realization and, where explicitly assigned, motion trajectories not already owned by a higher continuity/spatial contract.

It must remain separable from static geometry identity so a production revision can change without necessarily invalidating a compatible performance.

## 8.7 Execution authority

Execution owns only the mechanics of producing a result from captured state.

It may own:

```text
model-specific parameters
runtime selection
conditioning translation
interpolation implementation
sampling details
cache layout
materialization details
```

It does not own the film's canonical state.

---

# 9. Composition and spatial authority must not overlap ambiguously

The reusable-production layer and the existing spatial layer need a deliberate relationship.

## 9.1 Three placement classes

Every production instance placement should conceptually fall into one of three classes.

### A. Authority-bound placement

The instance corresponds to a continuity-significant spatial fact already owned by semantic/spatial authority.

Example:

```text
Reception desk instance
↕ bound to
approved lobby world frame / exact location state
```

The composition may carry a representation transform needed for materialization, but it must agree with the authoritative spatial fact.

### B. Composition-owned placement

The placement matters to the reusable set/composition but is not independently represented as higher spatial continuity authority.

Example:

```text
small decorative lamp arrangement
wall molding module
background side table
```

Its exact placement is part of the Composition Revision.

### C. Bulk/procedural placement

The element is not individually addressable by default and is represented through a deterministic population rule or packed placement data.

## 9.2 Promotion of significance

If a composition-owned or bulk element becomes continuity-significant, SoloRing must be able to promote it into the appropriate stronger identity/authority class without silently changing history.

Example:

```text
background chair
        ↓
character later sits in that exact chair
        ↓
promote to addressable instance
        ↓
future state can refer to that instance explicitly
```

## 9.3 Conflict rule

If two authority domains claim incompatible placement for the same addressable instance in one effective Shot, readiness fails.

SoloRing does not choose a winner by implementation order.

## 9.4 Composition ↔ Spatial Binding contract

For every authority-bound occurrence, SoloRing must resolve one versioned immutable binding between the exact Composition Revision and the exact SpatialWorldRevision used by a Shot.

Conceptually, each binding entry answers:

```text
authority_subject_ref
        ↕
addressable Production Instance identity
        ↕
exact referenced Production Revision
        ↕
spatial frame/track/placement authority
        ↕
realization basis/origin/unit interpretation
```

The contract does not duplicate spatial transforms as a second authority. It declares which side owns placement and how the production realization is interpreted relative to that authority.

For authority-bound placement, the SpatialWorld/track/frame value remains authoritative; any representation-local transform is derived/materialization state. For composition-owned placement, the Composition Revision remains authoritative and must not masquerade as M10 spatial authority.

## 9.5 Binding completeness and uniqueness

Before publication/capture/execution, the binding resolver must prove:

1. every required spatial subject that must be physically realized by the composition has exactly one compatible instance binding;
2. no one instance is bound to two incompatible spatial subjects;
3. every bound instance still exists in the selected Composition Revision;
4. the exact Production Revision attached to that instance has a compatible basis/origin/scale contract;
5. the selected Composition Revision and SpatialWorldRevision belong to a coherent production context;
6. preview and final observation compilation consume the same exact binding identity/value.

Missing or duplicate required bindings block readiness. No name/path matching occurs at execution time.

## 9.6 Historical binding rule

A captured Shot pins the exact effective composition-to-spatial binding, either by exact immutable binding identity or by other exact immutable identities plus a versioned deterministic rule sufficient to reconstruct the same value without current-state queries.

A later Composition Revision may be compatible with the same SpatialWorldRevision, but it must pass binding and Production Revision compatibility again. Compatibility is not inherited merely because the composition has the same display name or parent identity.

---

# 10. Publication model

## 10.1 Working versus published

A reusable object or composition can have mutable working state.

```text
Working Production Object
        ↓
edit / generate / repair / replace components
        ↓
validate
        ↓
Publish
        ↓
immutable Production Revision
```

Working state is convenient. Published state is historical identity.

## 10.2 Publish-readiness

Publication should fail if the declared reusable capability cannot be consumed deterministically from retained dependencies.

Depending on object type, readiness may include checks such as:

```text
required geometry realization present
required look realization present
units / basis known
bounds known when required
exact dependent revisions pinned
representations registered
required byte identities retained
no unpublished working dependency
semantic/visual/spatial bindings coherent
```

This document does not freeze one universal readiness checklist. Each production-object type must define the minimum closure required for its declared use.

## 10.3 Tracking references in working state

Working state may reference:

```text
current approved Desk
current approved Eva Hair
current approved Lobby Composition
```

for convenience.

When a composition is published or a Shot is captured, every tracking reference is coherently resolved to an exact immutable revision.

No published or captured history contains a floating `latest` reference.

## 10.4 Updates are explicit

A newer approved revision may be offered to current work, but accepting it is an explicit production action.

```text
Desk v4 currently used
Desk v5 approved
        ↓
review affected current compositions / Shots
        ↓
accept update
        ↓
new working state
        ↓
optional new published revision
```

Older history remains pinned.

## 10.5 Composition publication preserves surviving occurrence identity

Publishing a new Composition Revision carries forward the stable identity of every surviving addressable instance.

For example:

```text
Lobby Composition 8
chair-07 → Chair Revision 2

Lobby Composition 9
chair-07 → Chair Revision 3
```

`chair-07` remains the same occurrence. Its persistent world state, subject binding, physical relationships, and downstream references remain targeted at that occurrence unless an explicit identity-changing operation is performed.

A removed occurrence with still-live persistent state or relationships makes publication/readiness incomplete until the filmmaker explicitly retires, migrates, replaces-as-new, splits, merges, or otherwise resolves those dependencies.

## 10.6 Production Revision compatibility assessment

Accepting a newer Production Revision into an existing occurrence requires a compatibility assessment against every consuming contract that matters for that occurrence.

Potential dimensions include:

```text
coordinate basis and handedness
origin / pivot convention
physical scale and dimensions
bounds / occupancy assumptions
attachment and contact interfaces
rig / deformation contract
performance compatibility
look/material binding contract
required dependency closure
required consumer representations
observation/compiler requirements
```

The result is expressed per relevant consumer using:

```text
COMPATIBLE_AS_IS
COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION
REQUIRES_REVIEW
INCOMPATIBLE
```

A working update may be offered automatically only when all required consumers are `COMPATIBLE_AS_IS` or have an already approved meaning-preserving deterministic translation. `REQUIRES_REVIEW` requires an explicit filmmaker/production decision. `INCOMPATIBLE` blocks substitution until the owning authority is deliberately changed.

When a deterministic translation materially affects published or captured state, its exact version/identity and inputs are pinned as production-realization or execution provenance according to the authority it serves. It never rewrites the old Production Revision or old captured Shot.

---

# 11. Edit scope, overrides, promotion, and fork

## 11.1 Explicit edit scope

An edit operation must identify the authority scope it intends to change when that scope is ambiguous.

Examples:

```text
Shot-local
Story-state / continuity
Composition working state
Reusable Production Object
Reusable variation
```

## 11.2 Typed overrides

SoloRing should prefer domain-specific override operations rather than arbitrary `property path → value` as a universal mechanism.

Possible composition-local operations include:

```text
change instance transform
change visibility
replace one referenced production revision
add temporary dressing instance
remove temporary dressing instance
select one optional production group
```

A composition override may not silently rewrite semantic identity, continuity facts, visual identity, or canonical geometry bytes owned by another authority.

A Shot-local replacement of the source Production Revision for an existing addressable occurrence preserves that occurrence identity by default. If the replacement should represent a genuinely different occurrence, the filmmaker must choose an explicit identity-changing operation instead. Compatibility §10.6 still applies to the temporary substitution when it consumes existing spatial, relationship, or performance contracts.

## 11.3 Promotion

A useful local change may be intentionally promoted.

Example:

```text
Shot 42 local Chair 7 damage
        ↓
filmmaker chooses “Make reusable”
        ↓
new candidate reusable chair variation / revision
        ↓
validate
        ↓
explicit publish
```

Promotion preserves provenance from the local source state.

## 11.4 Fork

When the filmmaker wants an object to stop following a reusable source identity, SoloRing creates an explicit fork rather than an untracked loose copy.

```text
Chair revision 4
        ↓ fork
new Production Object identity
        ↓
derived_from = Chair revision 4
```

The new identity may evolve independently while lineage remains inspectable.

---

# 12. Persistent world state and story time

## 12.1 World state is resolved at narrative position

SoloRing must be able to answer:

> What is true in the production world at this canonical narrative position?

without depending on the order in which Shots are rendered or edited. Human-readable clock labels may annotate examples, but current authority is the canonical narrative topology and boundary ordering already established by SoloRing unless a future continuous story-clock domain is separately designed and adopted.

Example:

```text
14:00  vase intact       Eva dry       door locked      no injury
14:07  vase broken       Eva wet       door unlocked    fresh cut
17:00  vase broken       Eva dry       door unlocked    healing cut
```

A Shot at 17:00 resolves the 17:00 state even if it is edited before a flashback Shot at 13:30.

## 12.2 Editorial order is not world chronology

```text
presentation order
    ≠
story-time order
```

Therefore:

```text
Shot A shown first
Shot B shown second
```

is not sufficient to infer that B occurs later in the story.

## 12.3 State transitions

Persistent state changes enter through explicit narrative/production transitions.

Examples:

```text
injury occurs
prop breaks
door unlocks
wardrobe changes
object becomes wet
item changes possession
power goes out
```

The same random-access principles already established for continuity state apply: current effective state is resolved from canonical narrative topology and eligible transitions before capture.

## 12.4 Three continuity mechanisms

SoloRing should keep these conceptually separate:

### Frame continuity

Immediate carry-over across adjacent generated/rendered frames or windows.

### Performance continuity

Where subjects are and what action phase/pose/deformation they occupy.

### World-state continuity

Persistent facts that remain true on or off screen.

A short frame overlap can help frame continuity but cannot substitute for world-state memory.

## 12.5 State-driven realization

A story fact and its visual/physical realization remain separate.

Example:

```text
Continuity fact:
Eva forehead injury = healing
        ↓
Visual authority:
approved healing appearance
        ↓
Production realization:
makeup/texture/geometry realization as needed
        ↓
Shot observation
```

The first generated depiction does not become the semantic definition of the injury.

## 12.6 Within-Shot event and Shot/end persistent handoff

Boundary state and intra-Shot state are separate views of one temporal production contract.

For a state-changing event inside a Shot:

```text
Shot/start
resolve exact starting state
        ↓
within-Shot event at time_ms
state/performance authority changes during the Shot
        ↓
Shot/end
explicit persistent transition declares downstream state
```

Rules:

1. the Shot-local event targets the same durable authority subject as the persistent state it changes;
2. its Shot-relative timing is immutable when captured;
3. the Shot is not treated as though the terminal state were already true at frame/time zero;
4. if persistence is intended, an explicit Shot/end transition is mandatory;
5. the event's terminal consequence and Shot/end transition must agree exactly under the owning state domain;
6. a Shot/end transition without a time-specific event remains valid when only before/after continuity matters;
7. generated output analysis may propose event timing or consequence but cannot create either authority automatically.

This provides sparse time-addressed authority without creating per-frame database state.

## 12.7 Persistent consequence adoption is separate from Take approval

When an approved Take depicts an event that could alter downstream state, the Review experience must expose the proposed persistent consequence separately.

Conceptually:

```text
Approve Take
        ≠
Adopt persistent consequence
```

The filmmaker may approve the visual performance while rejecting, changing, or deferring the proposed persistent state transition. If the consequence is adopted, it enters the owning world/continuity authority through its explicit transition path.

---

# 13. Performance architecture

## 13.1 Performance is not static asset identity

SoloRing must not fuse:

```text
who the subject is
what physical body/rig realizes the subject
where the subject is in the world
how the subject moves locally over time
```

These are related but independently versionable production concerns.

## 13.2 Global and local motion

A useful canonical decomposition is:

```text
WORLD PLACEMENT / ROOT TRAJECTORY
        +
LOCAL PERFORMANCE
pose / articulation / deformation / expression
```

This supports different creation methods while preserving a stable downstream contract.

## 13.3 Candidate performance sources

A performance may be proposed by:

```text
manual animation
performance capture
tracking
reconstruction
generative creation
physical simulation
procedural motion
import
```

Once adopted, downstream execution should consume the approved Performance Revision rather than care how it was created.

## 13.4 Compatibility with revised physical realization

Changing a character's physical Production Revision should not automatically invalidate every Performance Revision. Performance participates in the general Production Revision compatibility contract defined in §10.6.

For performance, the assessment additionally considers rig/deformation topology, control/retarget contracts, root conventions, contact assumptions, and any performance-specific attachment interfaces.

A deterministic retarget/translation is valid only when it preserves the intended performance semantics; otherwise the result is `REQUIRES_REVIEW` or `INCOMPATIBLE`. Any materially determinative translation used by published/captured work is pinned as realization/execution provenance and cannot rewrite the original Performance Revision or physical Production Revision.

## 13.5 Rigging remains a future implementation domain

This architecture reserves a reusable rig/deformation realization role but does not prescribe a skeleton, control system, deformation representation, or animation editor.

The product requirement is the stable separation of identity, physical realization, world placement, and local performance—not a commitment to one implementation mechanism.

---

# 14. Physical relationships and simulation

## 14.1 Physical relationship graph

Some continuity facts are relational rather than simple transforms.

Examples:

```text
lamp supported_by desk
picture attached_to wall
book on desk
cup contained_by tray
door hinged_to frame
hand contacting handle
```

The architecture should permit such relationships where they become production-significant.

## 14.2 Relationship status

A relationship may be:

```text
INFERRED
VALIDATED
AUTHORITATIVE
```

This distinction prevents reconstruction or simulation from silently becoming production truth.

## 14.3 Physical rule versus simulated outcome

A simulation input and a simulation result are different identities.

```text
approved physical rules / initial state
        ↓
simulation execution
        ↓
candidate motion / deformation
        ↓
review
        ↓
optional adoption as Performance Revision or state transition
```

A plausible simulated event is not narrative canon until adopted.

---

# 15. Candidate-world ingestion

SoloRing should eventually support importing existing media or generated material as a **candidate world**, not merely as reference pixels.

## 15.1 Candidate-world output

A world-ingestion process may propose:

```text
entity/object candidates
candidate identity matches
candidate geometry
candidate scale
candidate camera
candidate trajectories
candidate deformation
candidate physical relationships
candidate lighting realization
confidence / evidence metadata
```

One derivation may produce several such outputs, but adoption is never all-or-nothing merely because they share one derivation. Camera, geometry, identity matches, motion, lighting, and relationships remain independently reviewable under their owning authority domains.

Confidence may prioritize inspection or communicate uncertainty, but it is evidence only. A higher confidence score never outranks explicit existing production authority or filmmaker adoption.

## 15.2 Identity matching

Detected labels or tracks are observations, not SoloRing identity.

Every candidate object must resolve through one of these routes:

```text
match to existing production identity
        ↓ review
accept match

or

create new candidate identity
        ↓ review
adopt as new production identity

or

ignore
```

## 15.3 Evidence topology

A reconstructed candidate may contain mixed evidence quality across one object.

Where relevant, provenance should be able to distinguish conceptually:

```text
observed from multiple views
observed from one view
geometrically inferred
generatively completed
unobserved / synthesized
```

This does not require every vertex to become a database fact. It means the architecture must not erase meaningful evidence distinctions before the filmmaker decides whether to adopt the result.

## 15.4 No automatic bootstrap

If a generated image is reconstructed back into geometry, the resulting geometry is another candidate.

```text
generated result
        ↓
reconstruction
        ↓
new candidate
        ↓
review/adoption required
```

Repeated processing never grants authority by repetition.

---

# 16. Shot as the production-resolution boundary

## 16.1 Shot working state

A Shot is current editable intent plus references into the current production world.

The working Shot may track current approved revisions for convenience.

## 16.2 Shot production context

Before capture, SoloRing resolves one coherent production context containing every relevant authority domain.

Conceptually:

```text
ResolvedShotProductionState
│
├── story-time / narrative position
├── exact semantic EntityRevisions
├── effective world/continuity state
├── exact visual authority revisions
├── exact spatial/cinematic authority
├── exact Production Revisions
├── exact Composition Revisions
├── exact addressable instance identities + authority-subject bindings
├── exact Composition ↔ Spatial binding value
├── exact Production Revision compatibility decisions/translations when applicable
├── exact Shot-start world/continuity state
├── exact Shot-local state-changing events when authored
├── exact Shot/end persistent handoffs when applicable
├── exact Performance Revisions / state
├── authoritative physical relationships when required
├── Shot-local typed overrides
└── readiness / unresolved diagnostics
```

This value should be produced by one coherent resolver/builder boundary rather than independently reconstructed by UI, capture, and execution paths.

## 16.3 Readiness

A Shot can exist while not yet safe to capture or execute.

Readiness may fail because:

```text
required production revision missing
tracking reference cannot resolve coherently
required visual authority missing
spatial world unapproved
instance-placement conflict
performance incompatible
world state unresolved
required representation/consumption closure missing
stateful instance lacks one durable authority subject
composition↔spatial binding missing, duplicated, or incompatible
Production Revision substitution lacks required compatibility verdict
within-Shot persistent event disagrees with Shot/end handoff
removed instance still has unresolved persistent state/relationship targets
physical relationship conflict
```

The product should surface precise blocking reasons before expensive execution.

## 16.4 Capture

When captured, all mutable/tracking references become exact pinned identities.

After capture:

```text
ShotRevision
= immutable historical production fact
```

It is never re-resolved from current state.

## 16.5 Historical ShotRevision principle

A ShotRevision must eventually be sufficient to answer:

> Exactly which production world, production revisions, composition revisions, states, performances, camera/staging authority, and execution inputs did this Shot use?

without consulting mutable current production state.

---

# 17. The World Observation Compiler

## 17.1 Purpose

The World Observation Compiler is the architectural boundary between captured production truth and replaceable execution technology.

```text
ShotRevision
        ↓
World Observation Compiler
        ↓
Execution Observation Specification
        ↓
renderer-specific materialization
        ↓
Generation / execution
```

It generalizes the existing principle that model-specific realization sits below captured semantic, visual, and spatial state.

## 17.2 Input

The compiler consumes only immutable captured production state for historical execution, or one coherent resolved current state during preview before capture.

It must not reconstruct missing authority by querying unrelated current state.

## 17.3 Output

The compiler may produce a versioned observation specification whose exact content depends on executor capability.

Possible components include:

```text
camera parameters
structural geometry projection
depth
normals
instance / semantic masks
motion vectors / trajectories
surface identifiers
appearance reference images
approved detail anchors
performance controls
physical contact cues
shot text materialization
other renderer-specific controls
```

These are execution inputs, not production-world identity.

## 17.4 Control bandwidth

The compiler should allow different Shots to request different levels of explicit control.

Conceptually:

### Low control

```text
camera
coarse depth
coarse semantic structure
appearance/style authority
```

Useful where the renderer may infer much of the scene safely.

### Medium control

```text
camera
depth
normals
instance identity
silhouette
motion
selected geometry constraints
```

Useful for normal continuity-critical production.

### High control

```text
exact geometry projection
surface correspondence
material / realization identity
high-detail performance controls
contact constraints
high-resolution approved anchors
```

Useful for hero shots and details where generative freedom must be narrow.

These are product control levels, not frozen encoding formats.

## 17.5 Property-level trust contract

The observation specification should ultimately be able to express why a source is authoritative.

Example:

```text
camera                preserve exactly
Reception Desk shape  preserve structurally/exactly as declared
Eva identity          preserve approved identity
forehead injury       preserve required continuity appearance
cloth micro-wrinkles  may infer
incidental reflection may infer
```

The execution adapter translates that contract into the capabilities of the selected executor.

## 17.6 Capability failure

If an executor cannot realize a production requirement declared hard by the captured Shot, generation must fail before queueing or execution rather than silently ignoring that requirement.

A renderer's inability to honor authority is an execution-capability problem, not permission to weaken the Shot.

## 17.7 Observation history

Observation specifications and materially determinative derived artifacts may be retained as part of historical execution provenance.

Their retention supports reproduction without elevating them into production authority.

---

# 18. Execution and Takes

## 18.1 Generation remains downstream

A Generation executes one immutable captured production state through one exact execution specification.

Generation lifecycle metadata remains mutable operational state; the execution request itself remains immutable.

## 18.2 Take remains a candidate

A successful output import creates a Take candidate.

```text
executor succeeded
        ≠
Take approved
```

## 18.3 Continuity quality control

SoloRing may evaluate a Take against captured production authority.

Useful QC classes can include:

```text
identity adherence
camera adherence
spatial placement adherence
silhouette / depth agreement
continuity-feature presence
appearance consistency
contact uncertainty
sampling disagreement
historical input completeness
```

QC is evidence for review. It does not become production authority by itself.

## 18.4 Approval

Approving a Take changes canon for that Shot through the established explicit approval path.

Approval of a Take does not automatically promote generated details back into reusable production assets, world state, composition, or performance.

If the filmmaker wants a generated detail to become reusable production truth, that detail enters a separate candidate/adoption path owned by the appropriate domain.

---

# 19. Historical reproducibility

## 19.1 Historical execution consumes retained production artifacts

If Shot 42 used Desk Production Revision 4, Exact Rerun should consume retained Desk Revision 4 and its required closure.

It should not rerun the original creator to reconstruct Desk Revision 4.

## 19.2 Reproducibility claims remain graded

SoloRing distinguishes:

```text
same production specification
same captured execution specification
same pinned environment
same execution-path behavior
byte-identical output
```

A weaker claim never implies a stronger one.

## 19.3 Compatibility views

When an older representation requires translation for a current executor:

```text
immutable historical representation
        ↓
execution-only compatibility translation
        ↓
current executor
```

History itself remains unchanged.

## 19.4 Missing historical closure

If a historically required retained artifact is missing or corrupt, execution fails closed.

SoloRing must not silently replace it with a current revision, `latest` revision, regenerated approximation, or newly downloaded equivalent.

---

# 20. Main filmmaker workflows

These workflows are architecture acceptance tests, not UI wireframes.

## 20.1 Approve and reuse a character

```text
Create Eva candidate(s)
        ↓
review identity / appearance
        ↓
approve Eva semantic + visual state
        ↓
create / import / build candidate physical realization
        ↓
review
        ↓
publish Production Revision
        ↓
reuse across Shots
```

Requirements:

- Eva's story identity survives physical-realization changes;
- visual identity survives renderer changes;
- later Production Revisions do not mutate historical Shots;
- Shot capture pins exact revisions.

## 20.2 Build and publish a reusable set

```text
Create/import/build candidate lobby
        ↓
identify reusable components
        ↓
validate spatial authority bindings
        ↓
approve components
        ↓
publish Lobby Composition Revision
```

Requirements:

- set is not one opaque output blob;
- continuity-significant components are addressable;
- production representation can change without changing set identity;
- the composition pins exact referenced revisions.

## 20.3 Replace one set component

```text
Lobby v8 uses Chandelier v3
        ↓
Chandelier v4 candidate
        ↓
approve Chandelier v4
        ↓
Lobby working state reports update available
        ↓
filmmaker accepts
        ↓
publish Lobby v9
```

Historical Lobby v8 and Shots using it remain unchanged. The affected addressable occurrence retains its stable instance identity unless the filmmaker explicitly replaces it as a new occurrence, and the newer Production Revision must pass the compatibility contract for any existing spatial/relationship/performance consumers before publication.

## 20.4 Shot-local prop movement

```text
Shot 42
move Chair 7
        ↓
SoloRing asks scope if ambiguous
        ↓
“this Shot only”
        ↓
Shot-local typed override
```

No canonical lobby or downstream world-state mutation occurs.

## 20.5 Persistent prop movement

```text
Shot 42 start
chair-07 = upright
        ↓
Shot-local event / performance at 2800 ms
chair-07 falls
        ↓
filmmaker separately adopts persistent consequence
        ↓
explicit Shot/end world-state/spatial transition
chair-07 = fallen
        ↓
later Shots resolve the same authority subject as fallen
```

The Shot-local event and Shot/end transition must agree. The rendered result does not itself author either one. `chair-07` remains the same durable occurrence across compatible later Composition Revisions.

## 20.6 Persistent injury

If the cut occurs inside a Shot:

```text
Shot/start
Eva forehead injury = none
        ↓
Shot-local state event at authored time
injury becomes fresh during the Shot
        ↓
explicit Shot/end continuity transition
Eva forehead injury = fresh
        ↓
later narrative boundary
state = healing
        ↓
later boundary
state = scarred/resolved
```

Each later Shot automatically resolves the applicable state from canonical narrative topology. Approving the Take that depicts the injury does not itself adopt the persistent transition.

## 20.7 Update current production without rewriting history

```text
Eva Hair v4 approved
        ↓
current work shows update available
        ↓
filmmaker selectively accepts
        ↓
new current compositions / Shots use v4
```

Approved historical ShotRevisions remain pinned to their prior revision.

## 20.8 Import media as candidate world

```text
Import reference media
        ↓
candidate objects / world / camera / motion
        ↓
confidence + evidence review
        ↓
match / replace / ignore / repair
        ↓
explicit adoption
        ↓
publish selected production revisions
```

No inferred object or hidden generated surface becomes canonical merely because reconstruction succeeded.

## 20.9 Adopt a candidate performance

```text
track / animate / simulate / generate performance
        ↓
candidate Performance
        ↓
inspect against staging / contacts / intent
        ↓
approve
        ↓
immutable Performance Revision
```

## 20.10 Render the same Shot through another executor

```text
same ShotRevision
        ↓
new compatible observation compiler / executor path
        ↓
new Generation
        ↓
new Take candidates
```

The Shot does not change because the renderer changed.

## 20.11 Reproduce historical execution

```text
historical Generation
        ↓
historical ShotRevision
        ↓
exact pinned production revisions
        ↓
exact historical execution inputs
        ↓
Exact Rerun
```

No current state is consulted to reinterpret the Shot.

---

# 21. Grand Meridian full-sequence pressure test

This sequence is a product/architecture pressure test. Names and values are illustrative production content, not schema fixtures.

## 21.1 Initial published production state

### Characters

```text
Eva
  Semantic identity: Eva revision 5
  Visual identity: approved Eva appearance revision 8
  Production body/face: Eva Physical revision 3
  Hair: Eva Hair revision 2
  Wardrobe: Hotel Outfit revision 4
```

### Location

```text
Grand Meridian Lobby
  Location semantic revision: 7
  SpatialWorldRevision: 11
  CompositionRevision: Lobby composition 8
```

### Reusable set components

```text
Lobby Shell revision 7
Reception Desk revision 4
Chandelier revision 3
Chair revision 2
Vase revision 1
Elevator Bank revision 5
```

Lobby composition 8 contains 14 addressable chair instances because chairs participate in staging and continuity.

`chair-07` is a durable addressable Production Instance authority subject because it owns independent persistent placement/state. Its identity is not the display name or composition array position. The lobby's authority-bound instances are joined to SpatialWorldRevision 11 through one exact composition-to-spatial binding value.

### Story-time initial state — 21:55

```text
Eva forehead injury = none
Eva jacket wetness = dry
Eva carrying bag = true
Chair 7 = canonical lobby position
Vase 1 = intact on reception desk
Lobby entrance door = locked
```

## 21.2 Shot 20 — exterior arrival

**Story time:** 22:00

The Shot resolves:

```text
Eva exact identity / appearance / wardrobe revisions
no forehead injury
bag carried
current approved exterior production context
camera plan A
```

Four Takes are generated. Take 3 is approved.

Nothing generated in Take 3 changes world state automatically.

## 21.3 Shot 21 — lobby entrance

**Story time:** 22:02

The Shot selects Lobby composition 8 and SpatialWorldRevision 11.

Camera starts at lobby entrance and moves toward the desk.

The exact same Reception Desk revision 4, Chandelier revision 3, and Chair 7 instance identity used by later reverse angles are captured here.

Requirement proven:

> A new view does not require the location to be regenerated as a new location identity.

## 21.4 Shot 22 — desk conversation reverse

**Story time:** 22:03

Camera is now behind Reception Desk looking toward the entrance.

The Shot shares:

```text
Lobby composition 8
SpatialWorldRevision 11
Reception Desk revision 4
same addressable instances
```

but has a different camera plan.

Requirement proven:

> Reverse-angle geometry is derived from the same persistent world rather than model memory of Shot 21.

## 21.5 Shot 23 — chair movement, Shot-local first draft

During staging, the filmmaker drags Chair 7 thirty centimeters toward the desk.

SoloRing recognizes that this could affect multiple scopes.

The filmmaker chooses:

```text
This Shot only
```

Shot 23 captures a typed local instance-placement override.

Lobby composition 8 remains unchanged. Downstream story state remains unchanged.

Requirement proven:

> A visible edit does not silently become canonical set state.

## 21.6 Shot 24 — chair is actually knocked over

**Story time:** 22:05

The performance has Eva collide with Chair 7.

A generated or simulated candidate motion shows Chair 7 falling. The filmmaker authoritatively places the fall event at a Shot-relative time in the approved performance/event state.

The filmmaker approves the Take and separately adopts the persistent consequence. SoloRing then requires an explicit Shot/end transition on the same `chair-07` authority subject:

```text
Shot/start        chair-07 = upright
within-Shot event chair-07 falls at authored time
Shot/end          chair-07 = displaced/fallen
```

The terminal event state and Shot/end transition must agree.

Requirement proven:

> Approved pixels and persistent world-state adoption are separate actions, and an intra-Shot change has an exact downstream handoff.

## 21.7 Shot 25 — forehead injury occurs

**Story time:** 22:06

A Shot-local continuity event creates the injury at an authored Shot-relative time; an explicit Shot/end transition carries the resulting `fresh` state downstream:

```text
Eva forehead injury = fresh
```

Visual authority for the fresh cut is approved.

The Shot's performance may include the impact, but the semantic existence of the injury is not defined by the first generated wound pixels.

Requirement proven:

> Semantic production fact precedes visual realization.

## 21.8 Shot 26 — immediate aftermath

**Story time:** 22:07

The user does not manually mention the cut or fallen chair.

SoloRing resolves automatically:

```text
forehead injury = fresh
Chair 7 = fallen
Vase = intact
bag = carried
```

The renderer receives the appropriate captured authorities.

Requirement proven:

> World-state continuity persists without prompt repetition.

## 21.9 Shot 27 — vase breaks

**Story time:** 22:08

A candidate impact result shows Vase 1 falling and shattering.

The filmmaker adopts:

```text
Vase 1 = broken
```

A reusable broken-vase production variation may be published if future close-ups require exact physical shards; otherwise the state may remain semantic/visual with sufficient realization for current Shots.

Requirement proven:

> Production effort can scale with continuity importance rather than requiring maximal modeling everywhere.

## 21.10 Shot 28 — Eva exits

**Story time:** 22:10

World state at Shot end includes:

```text
Eva leaves lobby
Chair 7 fallen
Vase 1 broken
forehead injury fresh
```

No requirement exists to keep the lobby in a continuously generated video between this Shot and the next lobby appearance.

## 21.11 Shot 40 — later unrelated sequence

**Story time:** 00:30

The lobby is off-screen.

No lobby frames exist for more than two story hours.

Nevertheless its persistent state remains addressable.

Requirement proven:

> Off-screen state does not depend on continuous rendering.

## 21.12 Production update between work sessions

While editing current work, the filmmaker approves:

```text
Chair Production Revision 3
```

with improved physical geometry.

SoloRing reports:

```text
Lobby composition 8 still pins Chair revision 2.
14 current chair instances use revision 2.
new approved revision 3 available.
```

The filmmaker does not update the historical lobby yet.

Shots 21–28 remain unchanged.

## 21.13 Lobby composition update

The filmmaker accepts Chair revision 3 for current future work and publishes:

```text
Lobby composition 9
```

Lobby composition 9 references Chair revision 3.

It also encodes the current default lobby arrangement; the story-time fallen state of Chair 7 remains a narrative state concern rather than being accidentally folded into the canonical undamaged set.

Requirement proven:

> Reusable-set evolution and story-time damage/state remain separate.

## 21.14 Shot 51 — return to lobby

**Story time:** 01:00

The Shot occurs later in the story and intentionally selects Lobby composition 9 for the current production baseline while resolving story state from 01:00.

SoloRing must reconcile the newer reusable physical revision with the persistent state:

```text
Chair 7 identity persists
Chair physical realization = Chair revision 3
Chair story-state placement = fallen/displaced
Vase state = broken
forehead injury = healing
```

If the newer Chair revision is incompatible with the captured placement/performance contract, readiness fails for explicit review rather than silently substituting.

Requirement proven:

> Production revision updates and persistent continuity state compose explicitly.

## 21.15 Shot 52 — close-up of healing injury

**Story time:** 01:02

The Shot uses a tighter control envelope because the injury is hero detail.

Conceptually:

```text
Eva identity                exact
healing injury appearance   high-control
face structure              high-control
camera                      exact
background lobby detail     medium control
incidental reflections      free within bounds
```

Requirement proven:

> Control bandwidth can vary by property and Shot without changing production authority.

## 21.16 Shot 53 — flashback

**Presented after Shot 52; story time:** 21:58, before the injury and damage.

The Shot resolves:

```text
forehead injury = none
Chair 7 = original placement
Vase = intact
bag = carried
```

Even though current working production now includes later Chair geometry and later story-state transitions, the flashback resolves from narrative time.

If the filmmaker chooses a newer physical Production Revision for current flashback work, that is a current production choice; it does not change the earlier story-state facts.

Requirement proven:

> Editorial order does not define world chronology.

## 21.17 Shot 54 — generated local detail promoted to reusable production

A Take invents a distinctive hotel key-card holder on the Reception Desk.

The filmmaker likes it.

It does not automatically become part of the lobby.

The filmmaker selects:

```text
Promote to reusable production object
```

SoloRing creates a candidate object with lineage to Shot 54 / Take source evidence.

After review and publication, a new Lobby composition revision may explicitly include it.

Requirement proven:

> Useful generative invention can enter production without automatic authority transfer.

## 21.18 Shot 55 — alternative executor

The filmmaker renders Shot 52 through a newly available executor.

The ShotRevision remains unchanged.

A new observation specification is compiled for the new executor.

New Takes are compared against the same captured production authority.

Requirement proven:

> The production is durable even when execution technology changes.

## 21.19 Historical rerun years later

The system is asked to rerun the originally approved Generation for Shot 22.

It must use:

```text
historical ShotRevision
Lobby composition 8
SpatialWorldRevision 11
Reception Desk revision 4
Chandelier revision 3
Chair revision 2
historical appearance / continuity state
historical execution specification
historically required retained artifacts
```

It must not use:

```text
Lobby composition 9
Chair revision 3
current latest appearance
current current-approved references
current world-state resolver
```

Requirement proven:

> Exact historical production identity survives current evolution.

---

# 22. Pressure-test verdict

The architecture passes the Grand Meridian sequence only if all of these statements remain true:

1. The lobby can be shot repeatedly from new cameras without becoming a new location.
2. Reusable components can evolve independently.
3. A local Shot edit does not silently mutate a reusable set.
4. A local edit can be explicitly promoted into reusable production state.
5. A continuity-significant instance remains addressable across revisions.
6. Persistent damage and injury survive off-screen time.
7. Story-time state is independent of editorial order.
8. Production-revision updates do not rewrite historical Shots.
9. Production updates and persistent world state can compose without identity loss.
10. A renderer may receive different control bandwidth by property without becoming authority.
11. Generated inventions can enter production only through adoption.
12. New executors can render the same ShotRevision through new observations.
13. Historical rerun remains pinned to the exact old production graph.
14. Every persistent stateful production occurrence has one durable state/spatial authority subject.
15. Every authority-bound Composition Revision ↔ SpatialWorldRevision relationship is mechanically provable and historically capturable.
16. A state-changing event inside a Shot preserves Shot-start truth, event timing, terminal consequence, and an agreeing Shot/end persistent handoff.
17. Surviving addressable instance identity persists across Composition Revisions by default.
18. A Production Revision substitution is accepted only through an explicit compatibility verdict for all relevant consumers.

If future implementation makes any of these statements false or dependent on undocumented conventions, the design is incomplete.

---

# 23. Product surfaces implied by the architecture

This section identifies product areas, not implementation technology.

## 23.1 Production Library

Purpose:

```text
browse characters / locations / props / production objects
inspect current approved revisions
inspect update availability
publish new revisions
view dependency and provenance history
```

The default presentation should use filmmaker-facing names. Detailed realization and byte provenance belongs in an advanced inspector.

## 23.2 World / Set workspace

Purpose:

```text
open reusable composition
place / duplicate / select addressable instances
edit composition-owned dressing
bind continuity-significant instances to stronger authority
review updates
publish composition revision
```

## 23.3 Story State / Continuity workspace

Purpose:

```text
inspect effective state at narrative boundary
author transitions
review off-screen consequences
see unresolved/conflicting facts
```

The product should present story-time consequences, not raw transition-row mechanics.

## 23.4 Shot workspace

Purpose:

```text
select story moment
resolve current production state
stage camera
stage/adjust performance
apply Shot-local typed overrides
inspect readiness
generate Takes
```

## 23.5 Review workspace

Purpose:

```text
compare Takes
see continuity/QC diagnostics
approve/reject
promote useful candidate details through explicit domain actions
```

## 23.6 History / Provenance inspector

Purpose:

```text
show exactly what a historical ShotRevision / Generation used
show immutable production revisions and representations
show derivation provenance
show compatibility translations used for execution
show reproducibility level actually supported
```

The inspector exists to make the production auditable without forcing all users to manage those details during normal directing.

---

# 24. Capability ownership map

This is an architectural ownership map, not a milestone plan.

| Capability | Authority owner | Current architectural posture |
|---|---|---|
| Story identity | Semantic production authority | Established foundation |
| Narrative continuity state | Story-time/continuity authority | Established foundation, extensible |
| Approved appearance | Visual authority | Established foundation |
| Spatial/cinematic continuity | Spatial/cinematic authority | Established foundation |
| Reusable production realization | Production-realization authority | Architecture defined here; implementation future |
| Reusable composition / instances | Composition authority | Architecture defined here; stable instance lineage + composition↔spatial binding required |
| Production Revision compatibility | Cross-domain publication/readiness contract | Four-verdict architecture defined; per-domain evaluators/translation formats future |
| Generic persistent world state | Story/world-state authority | Architecture defined here; stateful Production Instances are valid durable authority subjects |
| Local performance / deformation | Performance authority | Architectural interface defined; Shot-local state events + terminal handoff integrated |
| Physical relationships | Production/world + physics boundary | Architectural interface defined; implementation future |
| Observation compilation | Execution boundary | Generalized architecture defined; current specialized paths are precedent |
| Generative/physical execution | Execution authority | Replaceable downstream capability |
| Take approval | Shot canon authority | Established foundation |
| Historical rerun | Captured historical graph | Established foundation, must extend to new production revisions |
| Editorial/finishing | Future independent authority domains | Deliberately not defined here |

---

# 25. What remains deliberately unresolved

This architecture should not pretend to have frozen implementation details that have not yet earned authority.

The following remain design questions for later targeted work:

1. Exact persistent noun/schema names for Production Object, Production Revision, Composition Revision, Representation, Derivation, and Performance Revision.
2. Whether geometry/look/rig/groom realization identities require independent first-class persistence in the first implementation slice or can begin inside one published revision manifest.
3. Exact persistence/API shape and domain-specific evaluators for the four-verdict Production Revision compatibility contract, including approved deterministic translation formats.
4. Exact persistence shape for durable Production Instance authority subjects and immutable Composition ↔ Spatial binding values.
5. Exact physical-relationship vocabulary and which relations are authoritative versus validation-only.
6. Exact candidate-world evidence metadata granularity.
7. Exact observation-specification abstraction and how it composes with the existing workflow/execution specification.
8. Exact user-facing control-bandwidth presets and whether they should be named at all in the first product.
9. Character rig/deformation implementation and authoring experience.
10. Editorial, compositing, color, sound, and mastering authority models.
11. Collaborative/multi-user production semantics beyond the current local-first product.

These are not holes to fill casually inside implementation. Each requires a concrete product problem, authority owner, historical rule, and proof contract.

---

# 26. Compatibility and evolution rules

## 26.1 Preserve what already works

Existing M10F authority/history remains valid.

Future reusable-production architecture must extend or migrate it explicitly; it must not reinterpret old ShotRevisions as though they captured production concepts that did not yet exist.

## 26.2 New authority creates a new historical schema only when semantically present

Do not fabricate empty higher-version history for older Shots merely for schema uniformity.

## 26.3 Migration does not invent production decisions

A schema migration may create structural capability. It must not automatically:

```text
approve assets
create canonical compositions
infer identities
adopt reconstruction results
promote generated media
change story state
```

Those are production decisions.

## 26.4 Current convenience must not weaken captured history

Tracking references, automatic update detection, viewport caches, working scene files, and live agent context are conveniences.

At publication/capture, exact immutable identities win.

---

# 27. Source-gate questions for future implementation

Any implementation derived from this architecture should eventually prove, at minimum:

### Authority

- Can generated/imported/reconstructed/simulated results reach production authority without an explicit adoption operation?
- Can any execution path write semantic, visual, spatial, production-realization, composition, or world-state authority as a side effect?
- Can one authority domain silently override another by materialization order?

### Identity

- Does production identity survive representation replacement?
- Does production identity survive loss of the original creation mechanism?
- Are continuity-significant instance identities independent of external hierarchy/path names?
- Does every stateful addressable occurrence resolve to exactly one durable authority subject?
- Do surviving addressable occurrence identities remain stable across Composition Revisions unless an explicit identity-changing operation occurs?

### Publication

- Does a published revision contain an exact consumption closure?
- Can a published revision depend on mutable unpublished working state?
- Do identical concurrent publishes converge where semantically identical?

### History

- Do captured Shots pin exact reusable production/composition revisions?
- Can current updates mutate historical Shot meaning?
- Can Exact Rerun operate with current-state resolvers made unavailable?
- Does compatibility translation leave historical source identity untouched?

### Story time

- Can the system resolve off-screen state directly at a target narrative boundary?
- Can a flashback resolve an earlier world state independent of editorial order?
- Can persistent state transitions be authored without relying on generated-frame adjacency?
- Can an intra-Shot state event preserve the true Shot-start state and hand off an exactly agreeing terminal value to Shot/end?

### Composition

- Can the same reusable object appear in multiple sets while retaining identity?
- Can a Shot-local edit remain local?
- Can a local edit be explicitly promoted?
- Can a canonical object update be offered without silently propagating?
- Does ambiguous placement authority fail rather than choose a winner?
- Is the exact Composition Revision ↔ SpatialWorldRevision binding complete, unique, versioned, and the same for preview/capture/execution?
- Does a Production Revision update carry an explicit compatibility verdict for every relevant consuming contract?

### Observation/execution

- Does inspection and final execution derive from the same captured authority?
- Can the observation format change without changing production identity?
- Does an executor that cannot satisfy a hard production constraint fail before expensive execution?
- Are derived observation artifacts prevented from becoming authority automatically?

### Product experience

- Can the filmmaker perform the Grand Meridian sequence without managing technical artifact identities manually?
- Does the UI expose scope only when the decision matters?
- Does the product show unresolved state honestly?
- Can the filmmaker improve current production without fear of historical mutation?
- Can the filmmaker approve a Take without accidentally approving its persistent consequences?

---

# 28. Architectural acceptance criteria

This architecture is considered sufficiently coherent to guide implementation planning only if it supports all of the following without contradiction:

```text
one approved character reused across a feature
one approved set reused from arbitrary later cameras
one component replaced without rebuilding the entire set
one Shot-local change kept local
one local change promoted intentionally
one persistent injury carried through off-screen story time
one prop-state change carried into later Shots
one flashback resolving earlier state
one reusable asset updated without rewriting historical Shots
one candidate world imported and selectively adopted
one performance imported/generated/simulated and selectively adopted
one Shot rendered through a different executor without redefining the Shot
one historical execution rerun from exact pinned production revisions
one continuity-significant Production Instance carrying persistent state across set revisions
one exact Composition Revision ↔ SpatialWorldRevision binding surviving preview, capture, and execution
one state-changing event occurring inside a Shot with an agreeing Shot/end persistent handoff
one Production Revision upgrade accepted/rejected through the explicit compatibility contract
```

The architecture must also preserve the existing SoloRing invariants for canonical capture, immutable history, provenance, failure semantics, query-shape discipline, recovery, and exact-rerun isolation.

---

# 29. Recommended next artifact

After this architecture is rerun against the unchanged standalone Full-Sequence Product Pressure Test and receives a passing architecture verdict, the next artifact should be a **SoloRing Capability & Ownership Map plus implementation roadmap** that answers:

```text
Which currently missing product capability should be implemented first?
Which authority domain owns it?
Which existing contracts remain unchanged?
Which existing contracts require extension or migration?
What is the smallest end-to-end filmmaker workflow that proves product value?
What historical compatibility must be preserved?
What source-gate evidence will prove closure?
```

The roadmap should be derived from the product workflows and pressure test in this document rather than from available implementation technologies.

---

# 30. Summary invariant

The SoloRing production architecture can be reduced to one product promise:

```text
The filmmaker decides what is true.
SoloRing remembers it as durable production state.
Reusable production revisions make that truth physically usable.
Story time determines which state applies.
A Shot captures one exact production world, including stable occurrence identities, bindings, and any intra-Shot persistent handoffs.
Reusable revision substitution is compatibility-gated rather than assumed.
The observation compiler translates that world for a chosen executor.
The executor produces candidates.
Only explicit adoption can change production truth.
Historical Shots remain exactly what they were.
```

That is the architectural basis for making a feature-length film with generative execution without making the generator responsible for remembering the film.
