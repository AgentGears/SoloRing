# SoloRing Product & Production Architecture

**Document:** SoloRing Product & Production Architecture  
**Version:** 1.0  
**Date:** 2026-09-01  
**Status:** Architecture synthesis — not an implementation plan and not implementation authorization  
**Predecessor baseline:** M10F @ `6f5d9771e3e67fa4097b7b7babab238d1f57a57e`  
**Normative foundation:** SoloRing Architecture Pattern Register v2.0  
**Purpose:** Define the product model, filmmaker experience, production-world architecture, authority boundaries, reusable-production model, story-time state model, Shot resolution contract, observation boundary, and full-sequence pressure test that future implementation planning must satisfy.

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

An **addressable production instance** has durable identity because the film may need to refer to that exact occurrence later.

Examples:

```text
Chair 7 in the Grand Meridian lobby
Reception desk instance
Lobby vase instance
Eva's hotel-room suitcase instance
```

Instance identity is independent of display name, hierarchy path, scene namespace, file location, import order, or executor label.

Not every repeated element needs addressable identity.

### Bulk/procedural instance

High-volume repeated elements may remain prototype + deterministic placement data when no continuity decision addresses each item individually.

Examples might include dense vegetation, debris fields, distant crowd population, or repeated architectural detail.

If one bulk element becomes production-significant, SoloRing may promote it into an addressable instance while preserving provenance.

## 7.11 World state

**World state** is the set of persistent story-time facts that remain true independently of current visibility.

Examples:

```text
vase broken
chair displaced
door unlocked
Eva's jacket wet
forehead injury fresh
bag no longer carried
power disabled
room evacuated
```

World state is not the latest rendered frame.

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

## 12.1 World state is resolved at narrative time

SoloRing must be able to answer:

> What is true in the production world at story time `t`?

without depending on the order in which Shots are rendered or edited.

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

Changing a character's physical Production Revision should not automatically invalidate every Performance Revision.

Compatibility must be explicit.

Possible outcomes:

```text
compatible as-is
compatible through deterministic retarget/translation
requires review
incompatible
```

Any translation used historically is execution/realization provenance and cannot rewrite the original performance history.

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
├── exact addressable instance state
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

Historical Lobby v8 and Shots using it remain unchanged.

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
Shot 42
Eva knocks over Chair 7
        ↓
performance / event occurs
        ↓
filmmaker adopts persistent consequence
        ↓
story-time world-state transition
        ↓
later Shots resolve Chair 7 displaced
```

The rendered result does not itself author the transition.

## 20.6 Persistent injury

```text
Scene event:
Eva receives forehead cut
        ↓
continuity transition
        ↓
state = fresh
        ↓
later narrative boundary
state = healing
        ↓
later boundary
state = scarred/resolved
```

Each Shot automatically resolves the applicable state from story time.

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

A generated or simulated candidate motion shows Chair 7 falling.

The filmmaker approves the Take and separately adopts the persistent consequence:

```text
Chair 7 state transition at 22:05
upright canonical placement
→ displaced/fallen placement
```

Requirement proven:

> Approved pixels and persistent world-state adoption are separate actions.

## 21.7 Shot 25 — forehead injury occurs

**Story time:** 22:06

A story event creates:

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
| Reusable composition / instances | Composition authority | Architecture defined here; implementation future |
| Generic persistent world state | Story/world-state authority | Architecture defined here; implementation future/extension |
| Local performance / deformation | Performance authority | Architectural interface defined; implementation future |
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
3. Exact compatibility rules between Performance Revisions and revised physical realizations.
4. Exact physical-relationship vocabulary and which relations are authoritative versus validation-only.
5. Exact candidate-world evidence metadata granularity.
6. Exact observation-specification abstraction and how it composes with the existing workflow/execution specification.
7. Exact user-facing control-bandwidth presets and whether they should be named at all in the first product.
8. Character rig/deformation implementation and authoring experience.
9. Editorial, compositing, color, sound, and mastering authority models.
10. Collaborative/multi-user production semantics beyond the current local-first product.

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

### Composition

- Can the same reusable object appear in multiple sets while retaining identity?
- Can a Shot-local edit remain local?
- Can a local edit be explicitly promoted?
- Can a canonical object update be offered without silently propagating?
- Does ambiguous placement authority fail rather than choose a winner?

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
```

The architecture must also preserve the existing SoloRing invariants for canonical capture, immutable history, provenance, failure semantics, query-shape discipline, recovery, and exact-rerun isolation.

---

# 29. Recommended next artifact

After this architecture is independently reviewed and accepted, the next artifact should be a **SoloRing Capability & Ownership Map plus implementation roadmap** that answers:

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
A Shot captures one exact production world.
The observation compiler translates that world for a chosen executor.
The executor produces candidates.
Only explicit adoption can change production truth.
Historical Shots remain exactly what they were.
```

That is the architectural basis for making a feature-length film with generative execution without making the generator responsible for remembering the film.
