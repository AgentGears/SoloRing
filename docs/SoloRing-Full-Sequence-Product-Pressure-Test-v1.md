# SoloRing Full-Sequence Product Pressure Test

**Document:** SoloRing Full-Sequence Product Pressure Test  
**Version:** 1.0  
**Date:** 2026-09-01  
**Status:** Product/architecture validation — not an implementation plan and not implementation authorization  
**Predecessor baseline:** M10F @ `6f5d9771e3e67fa4097b7b7babab238d1f57a57e`  
**Normative foundation:** SoloRing Architecture Pattern Register v2.0  
**Architecture under test:** SoloRing Product & Production Architecture v1.0  
**Purpose:** Pressure-test the proposed SoloRing production model against one realistic, nonlinear, multi-shot film sequence and identify architecture defects, authority ambiguities, capability gaps, UX failures, and historical-integrity risks before capability ownership or implementation planning begins.

---

# 0. Test mandate

This document is an adversarial product test of architecture, not a demonstration written to make the architecture look correct.

The question is:

> **Can a filmmaker make, revise, shoot, revisit, and historically reproduce one continuity-dense feature-film sequence without depending on hidden executor memory, destructive updates, ambiguous authority, or unreasonable production bookkeeping?**

The pressure test applies these governing rules:

```text
FILMMAKER INTENT
        ↓
SOLORING PRODUCTION AUTHORITY
        ↓
CURRENT RESOLUTION
        ↓
IMMUTABLE CAPTURE
        ↓
OBSERVATION / MATERIALIZATION
        ↓
EXECUTION
        ↓
TAKE CANDIDATE
        ↓
REVIEW
        ↓
EXPLICIT ADOPTION
```

No generated, imported, reconstructed, simulated, tracked, or otherwise derived result receives upstream authority merely because it exists or looks plausible.

This document does **not** authorize:

- repository mutation;
- schema design or migration;
- code implementation;
- new milestone execution;
- publication, tagging, or release work;
- executor or model integration;
- changes to existing immutable tags or historical data.

A pressure-test failure is a design finding, not implementation authorization.

---

# 1. Source architecture under test

The test treats the following SoloRing-native principles as binding inputs:

1. Current working state and immutable historical state are separate.
2. ShotRevision is the historical production-resolution boundary.
3. Semantic, visual, and spatial/cinematic authority remain above execution-specific realization.
4. Creation does not imply adoption.
5. Production identity is independent of representation and derivation.
6. Published reusable production revisions are immutable and consumption-closed.
7. Composition references exact reusable production identities.
8. Continuity-significant instances have durable identity.
9. Edit scope is explicit when one edit could have multiple production meanings.
10. Persistent world state exists independently of observations and editorial order.
11. Geometry, appearance, motion, and physical relationships remain separable production concerns.
12. Renderer observations are compiled from authoritative captured state.
13. Working references may track current approved state; published/captured history is pinned.
14. Historical compatibility translates execution rather than rewriting history.
15. Existing spatial authority remains technology-neutral and cannot be rewritten by generated/reconstructed output.
16. Exact historical execution must fail closed when required captured provenance or retained artifacts are missing.

The test deliberately attacks the boundaries between these principles rather than testing each in isolation.

---

# 2. Test methodology

## 2.1 A Shot is not enough to pass

A case passes only when all four dimensions are coherent:

```text
FILMMAKER EXPERIENCE
What is the user trying to do, and what does SoloRing ask/show?

AUTHORITY EFFECT
Which production authority is allowed to change?

HISTORICAL EFFECT
Which captured/published identities must remain untouched?

EXECUTION EFFECT
What may be materialized or inferred downstream without becoming authority?
```

A technically possible operation fails the product test if the filmmaker must understand implementation internals to use it safely.

## 2.2 Finding classes

Every issue found by the sequence is classified as one of:

| Class | Meaning |
|---|---|
| **PRODUCT MODEL DEFECT** | The filmmaker's intended production operation cannot be represented unambiguously. |
| **AUTHORITY DEFECT** | Two domains can claim the same fact or no domain clearly owns it. |
| **IDENTITY DEFECT** | A continuity-significant subject cannot retain stable identity through the required operation. |
| **TEMPORAL DEFECT** | Story-time or within-Shot state cannot be resolved with the required semantics. |
| **HISTORICAL DEFECT** | Mutable current state can reinterpret or replace captured history. |
| **UX DEFECT** | The architecture may be coherent, but the filmmaker interaction is unsafe or unreasonable. |
| **CAPABILITY GAP** | The architecture can express the requirement, but the capability is not yet implemented. |
| **EXECUTION GAP** | Production truth can be captured, but no current execution path can realize it. |
| **CLARIFICATION** | The architecture is sufficient but requires a more explicit normative statement. |

## 2.3 Severity

```text
P0  blocks a trustworthy product architecture or historical correctness
P1  blocks an important feature-film workflow or creates major UX risk
P2  valuable correction or scaling concern; does not invalidate the core architecture
P3  future-domain question intentionally outside the immediate product architecture
```

## 2.4 Pass semantics

A scenario is:

- **PASS** when the current architecture already defines the required authority, identity, temporal, historical, and UX behavior sufficiently.
- **PASS WITH CLARIFICATION** when the model is coherent but wording/ownership must be made explicit before implementation.
- **BLOCKED BY KNOWN GAP** when the architecture deliberately reserves the domain but does not yet define enough to implement it.
- **FAIL — ARCHITECTURE CORRECTION REQUIRED** when the scenario exposes a contradiction or missing load-bearing contract in the current architecture.

---

# 3. Production scenario

The test uses one sequence from the fictional feature **The Grand Meridian**.

The sequence is deliberately small enough to reason about precisely and rich enough to pressure:

- repeated set use from unrelated cameras;
- reusable set components;
- addressable repeated props;
- local versus persistent edits;
- intra-Shot state changes;
- off-screen persistence;
- injury continuity;
- wardrobe/possession state;
- physical relationships;
- asset and composition upgrades during production;
- performance reuse and compatibility;
- candidate-world ingestion;
- generative invention and promotion;
- variable renderer-control requirements;
- executor replacement;
- flashbacks and nonlinear editorial order;
- historical rerun and historical corruption.

---

# 4. Initial production state

## 4.1 Characters

```text
Eva
  Semantic identity                Eva EntityRevision 5
  Approved visual identity         Eva Visual revision 8
  Physical body/face realization   Eva Physical Production Revision 3
  Hair realization                 Eva Hair Production Revision 2
  Wardrobe                         Hotel Outfit Production Revision 4

Night Clerk
  Semantic identity                Clerk EntityRevision 2
  Approved visual identity         Clerk Visual revision 3
  Physical realization             Clerk Physical Production Revision 1
```

## 4.2 Location

```text
Grand Meridian Lobby
  Location semantic revision       7
  Spatial world revision           11
  Published composition revision   Lobby Composition 8
```

## 4.3 Reusable set components

```text
Lobby Shell Production Revision      7
Reception Desk Production Revision   4
Chandelier Production Revision       3
Chair Production Revision            2
Vase Production Revision             1
Elevator Bank Production Revision    5
Desk Lamp Production Revision        2
```

## 4.4 Addressable composition instances

Lobby Composition 8 contains:

```text
Reception Desk instance              desk-main
Chandelier instance                  chandelier-main
Chair instances                      chair-01 ... chair-14
Vase instance                        vase-main
Desk Lamp instance                   lamp-main
Elevator Bank instance               elevators-main
```

`chair-07`, `vase-main`, `lamp-main`, and `desk-main` are explicitly continuity-significant during the sequence.

The test intentionally does **not** assume whether an addressable production instance is itself a CreativeEntity. That question is part of the pressure test.

## 4.5 Initial persistent story/world state

At the narrative boundary immediately before Eva arrives:

```text
Eva.forehead_injury     = none
Eva.jacket_wetness      = dry
Eva.carrying_bag        = true
Lobby.entrance_door     = locked
chair-07 placement      = canonical composition placement
chair-07 condition      = intact/upright
vase-main condition     = intact/on-desk
lamp-main relation      = supported_by desk-main
```

The human-readable clock labels in this document are production annotations. Normative current SoloRing temporal ordering remains canonical narrative topology/boundaries unless a future story-clock authority is separately defined.

---

# 5. Editorial presentation order versus narrative order

The sequence is intentionally edited nonlinearly.

## 5.1 Narrative chronology

```text
21:58  flashback moment
22:00  Eva arrives
22:02  Eva enters lobby
22:03  desk conversation
22:05  chair collision/fall
22:06  forehead injury
22:08  vase breaks
22:10  Eva exits
00:30  unrelated off-screen sequence
01:00  Eva returns to lobby
01:02  healing-injury close-up
01:05  later lobby action
```

## 5.2 Presentation order in the finished sequence

```text
Shots 20–28          arrival / incident
Shots 40–44          unrelated sequence
Shots 51–58          return to lobby
Shot 59              flashback to 21:58
Shots 60–67          present-time continuation
```

The test therefore requires world state to resolve from narrative position rather than from edit order or previous rendered output.

---

# 6. Shot matrix

This matrix is the compact index. Detailed critical cases follow.

| Shot / operation | Narrative position | Pressure applied | Expected architecture behavior | Result |
|---|---|---|---|---|
| 20 Exterior arrival | 22:00 | Character reuse | Exact Eva identity/appearance/wardrobe captured; no injury | PASS |
| 21 Lobby entrance wide | 22:02 | Same set, new camera | Lobby 8 + spatial world 11 reused | PASS |
| 22 Reverse behind desk | 22:03 | Arbitrary later viewpoint | Same world/components; different camera | PASS WITH CLARIFICATION |
| 23 Chair local staging experiment | 22:04 | Edit scope | `chair-07` move kept Shot-local | PASS |
| 24 Chair collision | 22:05 | Mid-Shot event + persistent consequence | Start upright, fall during Shot, downstream fallen only after explicit adoption | **FAIL — CR-3** |
| 25 Forehead injury | 22:06 | Mid-Shot semantic/visual transition | Starts uninjured, becomes fresh cut during Shot, persists after | **FAIL — CR-3** |
| 26 Immediate aftermath | 22:07 | Off-prompt persistence | Fresh cut + fallen chair resolve automatically | **FAIL — CR-1 until instance binding exists** |
| 27 Vase breaks | 22:08 | Mid-Shot state change | Break during Shot, downstream broken after adoption | **FAIL — CR-3 / CR-1** |
| 28 Exit / possession change | 22:10 | Bag possession + door state | Adopt explicit state changes; no dependence on pixels | PASS WITH CLARIFICATION |
| 40 Unrelated scene | 00:30 | Off-screen persistence | Lobby state remains addressable without rendering | PASS conceptually |
| Chair Production Revision 3 approved | production time | Reusable asset upgrade | Current work sees update; history unchanged | PASS |
| Lobby Composition 9 published | production time | Set upgrade | Exact new revisions pinned; old composition immutable | **FAIL — CR-2 / CR-4** |
| 51 Return wide | 01:00 | New composition + old story state | New chair realization + same `chair-07` fallen state | **FAIL — CR-1 / CR-2 / CR-4 / CR-5** |
| 52 Healing injury close-up | 01:02 | Property-level high control | Exact identity/injury/camera; bounded background inference | PASS conceptually; execution gap possible |
| 53 Lobby insert | 01:03 | Low/medium control | Same production world with more renderer freedom | PASS |
| Chandelier Production Revision 4 approved | production time | Component upgrade | Update offered, not automatic | PASS |
| 54 Shot-local chandelier substitution | 01:04 | Typed replacement override | This Shot may reference v4 without changing Lobby 9 | PASS WITH CLARIFICATION |
| Lobby Composition 10 published | production time | Promote component update | Chandelier v4 adopted into current set | **FAIL — CR-2 / CR-4 binding semantics** |
| 55 New wide with Lobby 10 | 01:05 | Current set evolution | Uses new chandelier; old Shots still pin prior revisions | PASS after CR-2/4 |
| 56 Generated desk detail | 01:05 | Downstream invention | Detail remains Take-local until promoted | PASS |
| Promote key-card holder | production time | Candidate → reusable object | New candidate object with lineage; explicit publication | PASS conceptually |
| 57 Lobby with promoted object | 01:06 | Composition update | New composition revision explicitly includes object | PASS after CR-2/4 |
| 58 Physical-contact close shot | 01:07 | Hand/desk contact | Performance and contact relation can be authoritative separately | BLOCKED BY KNOWN PERFORMANCE GAP |
| 59 Flashback | 21:58 | Nonlinear editorial | No injury, chair upright, vase intact regardless of current state | PASS |
| 60 Candidate-world ingestion | production operation | Partial inverse-production adoption | Match/select/ignore individually; nothing auto-adopted | PASS conceptually |
| 61 Imported camera trajectory Shot | 01:08 | Adopt only camera candidate | Camera adopted without adopting inferred geometry | PASS WITH CLARIFICATION |
| 62 Candidate tracked performance | 01:09 | Performance adoption | Candidate performance review then immutable adoption | BLOCKED BY KNOWN PERFORMANCE GAP |
| 63 Simulation proposes lamp fall | 01:10 | Simulation ≠ truth | Rejected simulation changes nothing upstream | PASS |
| 64 Validated lamp support | 01:10 | Physical relation status | `supported_by` can be validated without becoming narrative event | PASS conceptually |
| 65 Executor lacks required injury control | production execution | Capability mismatch | Fail before queueing; do not weaken Shot | PASS conceptually |
| 66 Compatible alternative execution | production execution | Renderer replacement | Same ShotRevision, new observation/execution spec | PASS conceptually |
| 67 Historical rerun of Shot 22 | historical | Exact pinned graph | Uses exact old revisions/inputs, zero current resolution | PASS conceptually |
| Historical representation missing | historical fault | Fail closed | No current/new replacement allowed | PASS |

The matrix exposes five architecture-correction requirements (`CR-1`–`CR-5`) before a capability/ownership roadmap can be considered stable.

---
# 7. Detailed critical cases

## 7.1 Shot 21 — persistent lobby, first interior view

### Filmmaker intent

> Open the approved Grand Meridian Lobby and shoot Eva entering from the main doors.

### Required current resolution

```text
Location EntityRevision             7
SpatialWorldRevision                11
Lobby CompositionRevision           8
Reception Desk Production Revision  4
Chandelier Production Revision      3
Chair Production Revision           2
Eva exact semantic/visual/physical/wardrobe state
camera plan for Shot 21
```

### Product behavior

The filmmaker selects the lobby and composes the camera. SoloRing should not ask the user to recreate or regenerate the set.

### Authority effect

No reusable production authority changes. This is a new Shot observation of existing approved state.

### Historical effect

ShotRevision captures exact lobby/spatial/component identities used.

### Execution effect

The observation compiler may derive whichever structural/visual controls the selected executor needs. Those derived controls do not become the lobby.

### Verdict

**PASS.** The existing architecture clearly supports this direction.

---

## 7.2 Shot 22 — reverse angle behind the reception desk

### Filmmaker intent

> Use the exact same lobby, but put the camera behind the reception desk looking back toward the entrance.

### Required behavior

The desk, chandelier, chairs, elevator bank, lobby shell, and world-space relationship must remain the same reusable production objects/instances. Only the Shot camera changes.

### Pressure

This is the core product promise: an unseen/reverse side of a set must not be invented as a new set identity merely because the camera moved.

### Finding

The architecture separates spatial authority, reusable physical realization, composition, and camera correctly. However, it currently states only that composition and spatial authority “must agree.” It does not yet define the exact binding that proves that the desk geometry instance used by Lobby Composition 8 is the production realization intended by the desk/world authority in SpatialWorldRevision 11.

For Shot 22, a renderer could theoretically receive:

```text
Spatial authority says desk is at transform A
Composition representation contains desk instance at transform B
```

without a frozen cross-domain mapping proving the two refer to the same addressable production subject and compatible transform basis.

### Verdict

**PASS WITH CLARIFICATION for the product concept, but this case contributes to CR-2.** Reverse-angle reuse is architecturally correct only after the composition↔spatial binding is made mechanically unambiguous.

---

## 7.3 Shot 23 — local chair edit

### Filmmaker intent

The filmmaker drags `chair-07` 300 mm toward the desk to improve composition, but means the change only for this Shot.

### Product behavior

SoloRing recognizes that the operation could mean more than one thing and asks for scope only because the ambiguity is consequential:

```text
Move Chair 7:

[ This Shot only ]
[ From this story moment onward ]
[ Current Lobby working composition ]
[ Create reusable variation ]
```

The filmmaker chooses:

```text
This Shot only
```

### Authority effect

Only Shot-local typed placement override changes.

### Must remain untouched

```text
Lobby Composition 8
canonical chair placement
persistent story/world state
prior/future captured Shots
Chair Production Revision 2
```

### Historical effect

Shot 23 captures the local placement override. Shot 24 starts from the persistent state, not from Shot 23’s local edit.

### Verdict

**PASS.** APR-087/088 and the Product Architecture define this interaction well.

---

## 7.4 Shot 24 — chair collision occurs inside the Shot

This case exposes a load-bearing temporal gap.

### Filmmaker intent

Eva enters the Shot with `chair-07` upright. At `time_ms = 2800`, she collides with it. The chair falls. The filmmaker wants the chair to remain fallen in later narrative time.

### Required truth

At Shot start:

```text
chair-07 = upright at canonical persistent placement
```

During the Shot:

```text
0–2799 ms     chair-07 remains upright
2800 ms       collision event
2800–end      chair-07 moves/falls according to approved performance
```

At Shot end / downstream narrative boundary:

```text
chair-07 persistent state = fallen/displaced terminal placement
```

### Why current boundary-only continuity is insufficient

Current SoloRing continuity/spatial temporal authority is intentionally random-access at narrative boundaries. That is correct for persistent state before/after a Shot, but it does not by itself describe a state transition that occurs **inside** the Shot.

The Product Architecture says performance is time-varying, but it does not yet define the normative handoff between:

```text
Shot-start world state
        +
within-Shot performance/event timing
        +
Shot-end persistent state transition
```

Without that contract, one of several bad outcomes is possible:

1. mark the chair fallen for the whole Shot, contradicting the opening frames;
2. leave persistent state upright and rely on generated pixels to imply the fall;
3. encode the fall only in executor text/motion and separately author downstream state without proving they agree;
4. attempt to make every frame a world-state revision, which the architecture explicitly does not require.

### Required product interaction

After the fall is authored/approved as a production event, SoloRing needs to represent the intended consequence explicitly, for example conceptually:

```text
Within-Shot event/performance:
chair-07 fall begins at 2800 ms
terminal state = transform T_fallen

Persistent handoff:
Shot 24/end
chair-07 persistent placement = T_fallen
```

The Take may be used to review whether the event was realized convincingly, but the event timing and terminal state cannot be extracted from the accepted pixels as upstream authority.

### Required invariant

If a within-Shot event is declared to establish a persistent downstream state, its authoritative terminal state must agree with the Shot/end persistent transition. A mismatch blocks capture/readiness or explicit adoption.

### Verdict

**FAIL — ARCHITECTURE CORRECTION REQUIRED (`CR-3`).**

The architecture needs an explicit within-Shot event/performance → persistent boundary handoff. This does **not** require per-frame database authority.

---

## 7.5 Shot 25 — forehead injury appears during the Shot

This is the same temporal defect in a different authority domain and proves it is not merely a chair-animation issue.

### Filmmaker intent

Eva begins Shot 25 without a cut. At `time_ms = 3100`, an impact creates a left-forehead injury. The final portion of the Shot must show the fresh cut, and all later story-time Shots must resolve the injury as fresh until a healing transition occurs.

### Required decomposition

```text
Semantic event
forehead injury becomes true

Visual realization
fresh-cut approved appearance becomes applicable after event

Performance
impact / reaction / local deformation over time

Persistent world-state handoff
Shot 25/end → injury state = fresh
```

### Existing strength

The architecture correctly states that the injury fact is upstream of its first generated visual depiction. That prevents a generated wound from defining semantic truth.

### Missing contract

The architecture does not yet say how one ShotRevision carries two temporal phases of the same continuity feature:

```text
before 3100 ms: injury = none
at/after 3100 ms: injury = fresh
```

while also producing one downstream persistent state after the Shot.

A Shot-start-only resolved continuity pack cannot express the visible transition without delegating it to unstructured execution intent.

### Verdict

**FAIL — ARCHITECTURE CORRECTION REQUIRED (`CR-3`).**

This is P0 because many film events change visible persistent state during a Shot: injury, damage, doors opening, lights switching, objects changing possession, clothes becoming wet, destruction, blood appearing, and similar continuity facts.

---

## 7.6 Shot 26 — no prompt repetition

### Filmmaker intent

> Shoot the aftermath. Do not re-explain what happened.

### Expected state

```text
Eva.forehead_injury = fresh
chair-07            = fallen
vase-main            = intact
Eva.carrying_bag     = true
```

### Strength

The architecture correctly requires random-access resolution of persistent state and does not depend on Shot 25 pixels or prompt memory.

### Identity pressure

The cut is naturally attached to Eva’s semantic identity. `chair-07`, however, is introduced by the Product Architecture as an **addressable production instance**.

Existing spatial continuity authority is keyed to story-world CreativeEntity identity for movable tracks. The Product Architecture deliberately permits a Production Object or Production Instance not to be a new semantic CreativeEntity.

Therefore this question is unanswered:

> **What durable authority subject does `chair-07` become when persistent story/spatial state must target that exact instance?**

If it remains only a Composition instance, existing temporal/spatial resolvers cannot necessarily own its persistent state. If every continuity-significant prop instance must become a CreativeEntity, the product architecture must say so explicitly and accept the semantic-model cost. If spatial/world-state authority is extended to addressable Production Instance identities, that is a foundational extension to current M10 assumptions.

### Verdict

**FAIL — ARCHITECTURE CORRECTION REQUIRED (`CR-1`).**

The architecture needs an explicit binding/subject rule for continuity-significant addressable production instances.

---

## 7.7 Shot 27 — vase breaks during the Shot

### Filmmaker intent

A vase starts intact, is knocked off the desk at `time_ms = 1700`, breaks, and remains broken later.

### Required state

```text
Shot start:
vase-main condition = intact
vase-main relation  = supported_by desk-main

During Shot:
contact lost
fall occurs
break event occurs

Shot end:
vase-main condition = broken
support relation     = absent / replaced by shard relations as production requires
```

### Pressure findings

This case combines:

- `CR-1`: can persistent state target `vase-main` as a production instance?
- `CR-3`: how does an intra-Shot event hand off to persistent Shot/end state?
- physical relationship status: `supported_by` may be authoritative before the break, but a simulation result showing the exact shard pattern is only a candidate unless adopted.

### Product behavior

SoloRing may offer a consequence review:

```text
Persistent consequences proposed:
✓ Vase condition: broken
✓ Remove support relation: vase-main → desk-main
? Publish exact broken-vase physical realization for later hero shots
```

The third item is intentionally optional. If later Shots only require semantic/visual broken-vase continuity, maximal shard geometry need not be published immediately.

### Verdict

**FAIL until CR-1 and CR-3 are resolved; otherwise the production principle is sound.**

---

## 7.8 Shot 28 — possession and door state

### Filmmaker intent

Eva gives the bag to the clerk and unlocks the lobby entrance before leaving.

### Expected downstream state

```text
Eva.carrying_bag      = false
bag possession        = clerk / desk storage, according to authored fact
Lobby.entrance_door   = unlocked
```

### Finding

Boundary-based persistent transitions are sufficient if the production only requires before/after state and the within-Shot action can be carried by performance intent. If the bag handoff or unlocking must be controlled with exact time-dependent state inside the Shot, CR-3 applies again.

### Verdict

**PASS WITH CLARIFICATION.** Persistent downstream state is supported; time-exact within-Shot transitions require CR-3.

---

## 7.9 Off-screen interval

No lobby Shot exists for more than two narrative hours.

### Required behavior

Nothing about the lobby should depend on continuous generated media.

At 01:00 SoloRing must still resolve:

```text
chair-07 fallen
vase-main broken
door unlocked
bag no longer carried by Eva
injury healing according to later authored transition
```

### Verdict

**PASS conceptually.** This is a core strength of APR-089 and the Product Architecture.

---

# 8. Production-update pressure

## 8.1 Chair Production Revision 3

During production, the filmmaker improves the chair geometry and approves:

```text
Chair Production Revision 3
```

The same reusable Chair Production Object remains the source object.

### Required UX

```text
Chair revision 3 approved.

Lobby Composition 8:
14 instances still pin revision 2

[ Review update ]
```

No captured Shot changes.

### Verdict

**PASS.** Tracking/current-update convenience versus pinned history is well defined.

---

## 8.2 Publishing Lobby Composition 9

The filmmaker accepts Chair Revision 3 for current future lobby work and publishes Lobby Composition 9.

### Required identity rule

The user expects:

```text
chair-07 in Lobby 8
        and
chair-07 in Lobby 9
```

to mean **the same addressable occurrence in the production world**, unless the filmmaker explicitly replaced/forked/removed that instance.

Changing the source Production Revision from Chair 2 to Chair 3 must not silently mint a new instance identity.

### Current gap

APR-086 says continuity-significant instances have durable identity independent of representation hierarchy. The Product Architecture says Composition Revisions pin addressable instance identities. However, neither explicitly states the revision-to-revision identity rule:

> **Publishing a new Composition Revision preserves each surviving addressable instance identity by default; changing the referenced Production Revision does not change the instance identity.**

Without this, persistent state targeted at `chair-07` may become orphaned or accidentally attach to a newly created instance when the set is updated.

### Verdict

**FAIL — ARCHITECTURE CORRECTION REQUIRED (`CR-4`).**

This is an identity invariant, not a UI preference.

---

## 8.3 Composition 9 versus SpatialWorldRevision 11

Lobby Composition 9 now contains the revised chair geometry.

The Shot also resolves SpatialWorldRevision 11.

### Required question

> How does SoloRing mechanically prove that Lobby Composition 9 is a valid reusable production realization of the exact spatial world authority used by this Shot?

The architecture currently describes three placement classes and says incompatible claims fail. But it does not define the versioned binding between:

```text
SpatialWorldRevision
        ↕
CompositionRevision
        ↕
addressable Production Instances
        ↕
exact Production Revisions / representations
```

A deterministic publication/readiness contract needs to know at least conceptually:

- which authority-bound instance realizes which spatial subject/frame/track;
- which composition transform is authoritative versus derived/materialization-only;
- basis/unit interpretation;
- whether required spatial subjects are missing or duplicated;
- whether the production revision is compatible with the authoritative extents/placement contract;
- whether a new Composition Revision requires a new binding or can prove compatibility with an existing one.

### Verdict

**FAIL — ARCHITECTURE CORRECTION REQUIRED (`CR-2`).**

The product model is correct that composition and spatial authority are separate. It is not yet sufficient to make their agreement mechanically provable.

---

# 9. Shot 51 — returning to the lobby after production upgrades

This is the hardest cross-domain case in the sequence.

### Filmmaker intent

> Return to the same lobby later in the story. Use the improved current chair model, but Chair 7 must still be lying where it fell and the vase must still be broken.

### Desired resolution

```text
Location semantic state         unchanged as applicable
SpatialWorldRevision            exact applicable revision
Lobby CompositionRevision       9
Chair Production Revision       3
chair-07 instance identity      SAME durable instance
chair-07 story/spatial state    fallen/displaced
vase-main state                 broken
Eva injury state                healing
```

### Four simultaneous requirements

1. **Instance continuity:** `chair-07` survives the composition revision (`CR-4`).
2. **State subject:** persistent chair state can target `chair-07` (`CR-1`).
3. **World/composition agreement:** Composition 9 is proven compatible with the selected spatial authority (`CR-2`).
4. **Production revision compatibility:** Chair Revision 3 can safely inherit/apply the persistent spatial placement and any relevant performance/contact assumptions created when Chair Revision 2 was active (`CR-5`).

### Why transform-only compatibility is insufficient

A new chair revision could have:

```text
same semantic chair design
same origin convention
same dimensions
→ compatible
```

or:

```text
changed origin
changed scale interpretation
changed dimensions materially
changed collision/contact surface
changed rig/deformation contract
→ requires review or incompatible
```

The architecture currently says compatibility should be explicit for performance versus physical realization, but it does not generalize a minimum compatibility contract for reusable production-revision substitution across spatial state, composition, contact, and performance.

### Verdict

**FAIL — architecture needs CR-1, CR-2, CR-4, and CR-5 before this core product workflow is trustworthy.**

This is the strongest reason not to proceed directly to an implementation roadmap yet.

---
# 10. High-control and low-control rendering pressure

## 10.1 Shot 52 — healing injury hero close-up

### Filmmaker intent

> Keep Eva's identity and healing cut exact enough to survive a hero close-up. The lobby background can remain less constrained.

### Property-level contract

```text
Eva semantic identity             hard / exact production identity
Eva approved visual identity      hard
healing injury fact               hard
healing injury appearance         high-control
face physical realization         high-control
camera                             hard
background set placement          structural
incidental reflections            generative freedom permitted
micro-wrinkles                     generative freedom permitted
```

### Product behavior

The filmmaker should not need to configure low-level executor fields. SoloRing expresses the production requirement and determines whether the selected execution path can honor it.

### Capability mismatch rule

If the selected executor cannot reliably carry the declared hard injury/identity/camera constraints, the Shot is **not silently weakened**. Generation fails readiness/capability negotiation before queueing.

### Verdict

**PASS conceptually.** The authority model is sufficient. The exact observation/capability contract remains a future execution design gap, not a product-model defect.

---

## 10.2 Shot 53 — lower-control lobby insert

### Filmmaker intent

> Give me a brief insert of the empty lobby. Preserve the actual layout and key props, but incidental surface detail may vary.

### Expected contract

```text
camera / major layout      hard/structural
Reception Desk             structurally preserved
Chandelier                 identity preserved
chair-07 fallen state      preserved if visible/relevant
small background detail    may infer
reflections                may infer
minor decorative texture   may infer
```

### Verdict

**PASS.** Adjustable generative freedom is a strong product concept and does not require weaker production authority.

---

# 11. Component replacement, Shot-local substitution, and promotion

## 11.1 Chandelier Revision 4 approved

A revised chandelier is published as a new Production Revision of the same reusable Production Object.

Current Lobby Composition 9 remains pinned to Revision 3 until the filmmaker explicitly updates it.

**Verdict: PASS.**

## 11.2 Shot 54 — use Chandelier Revision 4 locally

The filmmaker wants to preview/use the new chandelier only in Shot 54 without changing the reusable lobby yet.

### Product action

```text
Replace chandelier-main source revision
Revision 3 → Revision 4
Scope: This Shot only
```

### Required preservation

```text
chandelier-main instance identity remains stable
Lobby Composition 9 remains immutable
other current Shots still resolve Lobby 9 as authored
historical Shots unchanged
```

### Finding

Typed replacement selection is already contemplated. The architecture should clarify that a Shot-local source-revision substitution can preserve the addressable instance identity while changing the source Production Revision for that Shot capture.

### Verdict

**PASS WITH CLARIFICATION**, dependent on CR-4's instance-identity rule.

## 11.3 Promote chandelier update to Lobby Composition 10

The filmmaker later accepts the new chandelier for the current reusable lobby and publishes Lobby Composition 10.

### Required behavior

```text
Lobby Composition 9 remains immutable
Lobby Composition 10 references Chandelier Revision 4
chandelier-main instance identity survives
spatial/world binding is revalidated
```

### Verdict

**FAIL until CR-2 and CR-4 are resolved.**

---

# 12. Generated invention and promotion

## 12.1 Shot 56 invents a desk detail

A generated Take includes a distinctive key-card holder on the reception desk that is not present in the captured production world.

### Required behavior

The Take may be approved as a Shot result without changing the lobby.

SoloRing may surface:

```text
Untracked generated detail detected / user-selected:
Key-card holder

[ Keep Take-local ]
[ Create candidate reusable object ]
[ Ignore ]
```

### Filmmaker chooses promotion

```text
Create candidate reusable object
```

This creates a candidate with provenance back to the Take/region/source evidence.

It does **not** immediately modify:

```text
Reception Desk Production Revision 4
Lobby Composition 10
spatial authority
story state
```

After inspection and publication, the key-card holder can be added through a new composition revision.

### Verdict

**PASS.** Candidate → review → adoption handles this cleanly.

---

# 13. Physical contact and performance pressure

## 13.1 Shot 58 — exact hand-to-desk interaction

### Filmmaker intent

Eva places her hand on a specific desk edge while speaking. Contact matters to the shot.

### Required decomposition

```text
Eva identity / physical realization
Reception Desk exact production realization
Eva root/world placement
local Eva performance / hand pose
contact relationship or constraint
camera
```

The architecture correctly states that geometry, world-space trajectory, local deformation/performance, and physical relationships are separable.

### Current limitation

The architecture deliberately does not define a reusable character rig/deformation implementation or a complete Performance Revision compatibility model. Therefore it cannot yet specify how a hand-contact constraint is authored, retargeted, or validated at implementation level.

### Verdict

**BLOCKED BY KNOWN CAPABILITY GAP, not an architecture contradiction.**

The authority decomposition is sound; the performance domain needs targeted design before implementation.

---

# 14. Flashback pressure

## 14.1 Shot 59 — produced later, occurs earlier

Shot 59 is edited after the 01:00 return sequence but occurs at the narrative position before Eva's 22:00 arrival.

### Required story state

```text
forehead injury     = none
chair-07            = canonical/upright
vase-main            = intact
entrance door       = locked
Eva carrying bag    = true
```

### Production-version question

The filmmaker may choose to use a newer current Production Revision for a prop or character physical realization when producing this flashback, provided it remains compatible with the semantic/design state appropriate to that narrative moment.

This is a **current production choice**, not a claim that the earlier narrative state had already experienced later damage.

### Historical rule

Once Shot 59 is captured, its exact chosen production revisions are pinned. Later upgrades do not alter it.

### Verdict

**PASS.** Story-time state and production-version evolution are correctly separable in principle.

### Clarification

The human-readable `21:58` label is not itself a new canonical temporal authority. The current architecture can map the flashback to canonical narrative topology/boundaries. If SoloRing later needs continuous absolute story-clock semantics, that must be designed separately rather than inferred from display labels.

---

# 15. Candidate-world ingestion pressure

## 15.1 Production operation — import a reference video as candidate world evidence

A filmmaker imports reference media showing a similar lobby setup and camera move.

A candidate ingestion process proposes:

```text
candidate camera trajectory
candidate desk match
candidate lamp match
candidate wall geometry
candidate plant object
candidate support relation: lamp-main supported_by desk-main
candidate lighting realization
```

### Required review

The user chooses:

```text
Camera trajectory        ACCEPT as candidate Shot camera
Desk identity match      ACCEPT match to existing desk-main
Lamp identity match      ACCEPT match to existing lamp-main
Wall geometry            REJECT
Plant object             IGNORE
Support relation         VALIDATE as evidence, not new story event
Lighting realization     KEEP AS CANDIDATE only
```

### Required authority behavior

Each accepted piece crosses its **own** authority/adoption path. There is no all-or-nothing “import world = replace production world” action.

The wall rejection cannot be overridden by the fact that the candidate reconstruction used the wall to estimate the camera.

### Verdict

**PASS conceptually.** Candidate-world partial adoption is supported by the architecture's authority direction.

### UX clarification

The product must present candidate evidence by ownership domain rather than presenting one opaque reconstruction bundle with a single Approve button.

---

## 15.2 Shot 61 — adopt only the candidate camera trajectory

The candidate camera move is reviewed and adopted for Shot 61.

### Required behavior

The adopted camera trajectory is now Shot/cinematic authority for this Shot. Candidate reconstructed geometry remains unadopted and must not travel with the camera simply because both came from the same derivation.

### Verdict

**PASS WITH CLARIFICATION.** Derivation bundles can contain outputs with independent adoption status.

---

# 16. Performance-candidate pressure

## 16.1 Shot 62 — tracked/reconstructed candidate performance

A time-varying Eva performance is proposed from reference motion.

### Required lifecycle

```text
source motion evidence
        ↓
candidate Performance
        ↓
review identity/root/contact compatibility
        ↓
explicit adoption
        ↓
immutable Performance Revision
```

### Required separation

Adopting the performance must not redefine:

```text
Eva identity
Eva physical body/face Production Revision
Eva wardrobe
story-state injury fact
```

unless separate explicit actions are taken.

### Verdict

**BLOCKED BY KNOWN PERFORMANCE CAPABILITY GAP.** The architecture has the correct conceptual lifecycle but has intentionally not frozen the implementation-level Performance model.

---

# 17. Simulation pressure

## 17.1 Shot 63 — simulation proposes lamp fall

A simulation run predicts that `lamp-main` should tip over during Eva's movement.

The filmmaker does not want that story event.

### Required result

```text
simulation candidate rejected
        ↓
no world-state transition
no composition change
no physical relationship authority change
```

The next Shot still resolves the lamp upright/on the desk.

### Verdict

**PASS.** A physically plausible outcome is not narrative authority.

## 17.2 Shot 64 — validate support relationship

The filmmaker validates the production fact:

```text
lamp-main supported_by desk-main
```

This relation can support readiness/QC without implying that every future simulation result is canon.

### Verdict

**PASS conceptually.** Exact physical-relation vocabulary remains future work but authority status is clear.

---

# 18. Executor replacement pressure

## 18.1 Shot 65 — selected executor cannot honor required injury control

The filmmaker requests another Take of captured Shot 52 through an executor whose declared capabilities do not support the hard injury/identity preservation contract.

### Forbidden behavior

```text
silently omit injury control
convert hard to advisory
hide requirement in prompt text and hope
queue expensive work anyway
```

### Required behavior

```text
ShotRevision
        ↓
observation/execution capability negotiation
        ↓
required hard property unsupported
        ↓
BLOCK BEFORE QUEUE
```

The user sees a production-facing explanation, for example:

```text
This execution path cannot satisfy 2 required Shot constraints:
- Eva approved identity preservation
- healing forehead injury preservation

Choose a compatible execution path or explicitly change the Shot requirements.
```

### Verdict

**PASS conceptually.** This is already a binding architecture requirement.

---

## 18.2 Shot 66 — compatible alternative executor

A compatible execution path is selected.

### Required historical behavior

```text
same ShotRevision
new Generation
new observation specification
new exact execution provenance
new Take candidates
```

The ShotRevision itself does not change merely because the observation encoding or execution backend changes.

### Verdict

**PASS.** This is one of the architecture's strongest properties.

---

# 19. Historical isolation pressure

## 19.1 Shot 67 — Exact Rerun of original Shot 22

Years later, current production state contains:

```text
Lobby Composition 12
Chair Production Revision 5
Chandelier Production Revision 6
new current Eva appearance
new current observation compiler
```

The rerun source is the original Generation for Shot 22.

### Required historical graph

The rerun must use only the exact captured graph associated with the source Generation, including the applicable historical:

```text
ShotRevision
Lobby Composition 8
SpatialWorldRevision 11
Reception Desk Revision 4
Chandelier Revision 3
Chair Revision 2
exact appearance/continuity/spatial state
exact historical execution specification
exact retained representations/derived artifacts required by that execution
```

### Forbidden queries/behavior

```text
resolve current approved Lobby
resolve current Chair revision
resolve current world state
use current latest appearance
replace missing old representation with a new current one
reconstruct an approved old asset by rerunning its creator
```

### Verdict

**PASS conceptually.** This extends existing historical isolation correctly.

---

## 19.2 Historical representation is missing

One historically required retained representation is missing/corrupt.

### Required result

```text
Exact Rerun → fail closed
```

SoloRing may explain which historical dependency is unavailable and what reproducibility level is therefore impossible.

It must not substitute:

```text
current equivalent-looking representation
newer approved revision
regenerated approximation
new download with same display name
```

### Verdict

**PASS.** APR-023, APR-083, and APR-099 are sufficient.

---

# 20. Adversarial negative scenarios

The following cases are expected to fail safely.

| ID | Adversarial action | Required result |
|---|---|---|
| N-01 | Capture Shot with required Production Revision still unpublished | BLOCK: production readiness incomplete |
| N-02 | Composition and spatial authority claim incompatible transforms for same bound subject | BLOCK: authority conflict; no winner by implementation order |
| N-03 | Publish Lobby 9 while a required referenced component still points to mutable working state | BLOCK: publication closure incomplete |
| N-04 | Capture tracking reference `current approved Chair` without resolving exact revision | BLOCK: captured history may not float |
| N-05 | Generated Take adds new prop and executor attempts to register it directly into Lobby authority | BLOCK: candidate/adoption boundary required |
| N-06 | Reconstruction labels detected chair as existing `chair-07` without review | BLOCK: detected identity is candidate evidence |
| N-07 | Simulation says vase should roll but story authority says it remains | simulation result remains candidate/rejected; story state wins |
| N-08 | Two current domains claim different placement for `chair-07` | BLOCK readiness; no timestamp/ID tie-break |
| N-09 | Publish new Composition Revision but silently assign new identity to surviving `chair-07` | BLOCK/defect under CR-4 |
| N-10 | Apply Chair Revision 3 to `chair-07` despite incompatible basis/origin/contact contract | BLOCK pending compatibility review under CR-5 |
| N-11 | Injury occurs mid-Shot but capture contains only end-state injury for whole Shot | BLOCK/defect under CR-3 |
| N-12 | Take approval automatically creates Shot/end damage transition | BLOCK: output approval is not state adoption |
| N-13 | Current Lobby working composition deleted after historical Shot captured | historical Shot remains readable/executable from captured graph |
| N-14 | Old historical representation missing | Exact Rerun fails closed |
| N-15 | New executor can only honor advisory spatial control while Shot declares hard camera/identity constraints | BLOCK before queue |
| N-16 | Flashback produced later accidentally inherits current broken vase because it follows edit order | BLOCK/defect: narrative resolution required |
| N-17 | Shot-local chair move is accidentally promoted to reusable Lobby working state without scope confirmation | BLOCK/UX defect |
| N-18 | Same Production Object bytes appear through two different derivations | preserve derivation provenance; do not collapse production history by bytes alone |
| N-19 | Same production revision has multiple consumer representations | valid; representation identity remains downstream |
| N-20 | Compatibility translation rewrites old historical representation bytes | BLOCK: translation is execution-only |
| N-21 | Candidate-world bundle has high camera confidence but low geometry confidence and only one global Approve action exists | UX FAIL: adoption must be domain-granular |
| N-22 | Production instance owns persistent state but has no recognized spatial/world-state subject identity | BLOCK/architecture defect under CR-1 |
| N-23 | Addressable instance removed in new composition while downstream persistent state still targets it | BLOCK until explicit migration/retirement decision |
| N-24 | One executor materializes a different world/composition mapping than preview | BLOCK: preview/execution must derive from same binding authority |

---
# 21. Architecture defect register

The test does **not** produce a clean architectural PASS.

It identifies five load-bearing corrections that should be resolved before the Capability & Ownership Map is treated as implementation-roadmap input.

## CR-1 — Continuity-significant Production Instance must have an explicit state/spatial authority subject

**Severity:** P0  
**Class:** AUTHORITY DEFECT + IDENTITY DEFECT  
**Triggered by:** Shots 26, 27, 51; N-22  
**Affected patterns:** APR-063, APR-086, APR-089, APR-090

### Problem

The Product Architecture introduces durable addressable Production Instances that need not themselves be semantic CreativeEntities.

Existing spatial continuity authority, however, is organized around CreativeEntity identity for fixed bindings and movable SpatialTracks.

The full-sequence test requires persistent state on exact production occurrences:

```text
chair-07 fallen
vase-main broken
lamp-main supported_by desk-main
```

The architecture does not yet define whether these subjects:

```text
A. must each bind to a unique CreativeEntity;

B. can become first-class state/spatial subjects as Production Instance identities;

C. use another explicit binding identity shared by semantic, spatial,
   composition, and world-state authority.
```

### Why this is P0

Without a closed rule, SoloRing cannot guarantee that “this exact chair” retains spatial/world-state continuity across Shots and composition revisions.

### Required correction

The Product Architecture must state:

> **Every addressable production occurrence that can own persistent story/world state or independent spatial continuity must resolve to one durable authority subject recognized by the state and spatial resolvers.**

The eventual schema choice is intentionally not frozen by this pressure test.

### Rejected workaround

Do not silently use:

```text
display name
composition path
scene hierarchy
instance array position
renderer object label
```

as the state subject.

---

## CR-2 — Published Composition must have a mechanically provable binding to spatial authority

**Severity:** P0  
**Class:** AUTHORITY DEFECT  
**Triggered by:** Shots 22, 51, Lobby Composition 9/10; N-02, N-24  
**Affected patterns:** APR-040, APR-063, APR-085, APR-088, APR-091

### Problem

The architecture correctly separates:

```text
SpatialWorldRevision
        ≠
CompositionRevision
```

but currently stops at the rule that they “must agree.”

Feature-film reuse requires more than prose agreement. SoloRing must be able to prove which exact composition instance/production revision realizes each required spatial subject and how its placement/basis is interpreted.

### Required correction

A future architecture revision must define a versioned **composition-to-spatial binding contract** conceptually sufficient to prove:

```text
selected SpatialWorldRevision
        ↕
exact authority-bound production subjects
        ↕
exact CompositionRevision instances
        ↕
exact Production Revisions / realizations
```

The contract must make these questions deterministic:

1. Which composition instance realizes each required spatial subject?
2. Which transform is authority and which is derived materialization?
3. Are basis, units, origin, and scale conventions compatible?
4. Are any required bindings missing or duplicated?
5. Does a CompositionRevision update remain compatible with the selected world revision?
6. Can preview and final execution compile from the same exact binding?

### Historical rule

The binding used by a captured Shot must itself be historically pinned or reconstructible solely from other exact captured immutable identities under a versioned deterministic rule.

### Rejected workaround

Do not rely on a DCC/scene-file hierarchy or matching object names to infer the relationship at execution time.

---

## CR-3 — Within-Shot state-changing events need an explicit persistent handoff

**Severity:** P0  
**Class:** TEMPORAL DEFECT + PRODUCT MODEL DEFECT  
**Triggered by:** Shots 24, 25, 27; N-11, N-12  
**Affected patterns:** APR-010–015, APR-060, APR-089, APR-090

### Problem

Current persistent continuity semantics are strong at narrative boundaries, while a Performance may vary through a Shot. The architecture does not yet close the case where a state-changing event happens **inside** one Shot and creates a new persistent state for subsequent Shots.

Examples:

```text
chair falls at 2800 ms
forehead cut appears at 3100 ms
vase breaks at 1700 ms
door unlocks at 4200 ms
bag changes possession at 5000 ms
```

### Required correction

The architecture needs a three-part contract:

```text
SHOT-START RESOLVED STATE
        +
WITHIN-SHOT EVENT / PERFORMANCE AUTHORITY
        +
SHOT-END PERSISTENT HANDOFF
```

A state-changing event must be capturable at Shot-relative time without requiring per-frame database authority.

If the event establishes a persistent downstream fact, the terminal state declared by the Shot-local event/performance must agree with the explicit Shot/end state transition.

### Required historical behavior

A captured Shot must preserve enough immutable information to know:

```text
what state was true at Shot start
when the authoritative state-changing event occurred inside the Shot
what terminal state it established
what state became effective downstream
```

### Rejected workaround

Generated output analysis may propose event timing or terminal state, but it cannot author the persistent transition automatically.

---

## CR-4 — Addressable instance identity must survive Composition Revision evolution by default

**Severity:** P0  
**Class:** IDENTITY DEFECT  
**Triggered by:** Lobby 8→9→10; Shots 51, 54, 55; N-09, N-23  
**Affected patterns:** APR-085, APR-086, APR-087, APR-098

### Problem

The architecture makes addressable instance identity durable inside a composition, but does not explicitly define revision-to-revision continuity.

A production update such as:

```text
chair-07 source:
Chair Revision 2 → Chair Revision 3
```

must normally preserve `chair-07` identity.

Otherwise persistent state, Shot-local references, physical relationships, and provenance can lose their target whenever a new set revision is published.

### Required correction

The architecture must state:

> **Publishing a new Composition Revision preserves the identity of every surviving addressable instance unless the filmmaker explicitly removes, replaces-as-new-identity, splits, merges, or forks that instance. Changing the referenced Production Revision alone does not change instance identity.**

### Required explicit transitions

Operations that alter instance identity must preserve inspectable lineage and affected-state diagnostics.

Examples:

```text
remove instance
fork instance source
replace same occurrence with another source revision
replace occurrence with a genuinely new occurrence
split one occurrence into several
merge occurrences
```

Persistent state targeting a removed/incompatible identity must block or require explicit migration. It must never silently retarget by name or nearest transform.

---

## CR-5 — Production Revision substitution needs a general compatibility verdict

**Severity:** P0 for continuity-critical substitution; P1 for noncritical objects  
**Class:** PRODUCT MODEL DEFECT / CAPABILITY OWNERSHIP GAP  
**Triggered by:** Shot 51; performance/contact future cases; N-10  
**Affected patterns:** APR-081–085, APR-090, APR-098–099

### Problem

The Product Architecture already recognizes compatibility between Performance Revisions and revised physical realizations, but reusable revision substitution affects more than performance.

A newer Production Revision may differ in:

```text
origin / pivot convention
physical scale or dimensions
bounds
attachment points
contact surfaces
rig/deformation contract
material/look binding
required dependencies
representation availability
```

A simple “same Production Object identity” is not enough to prove that an old spatial placement, physical relationship, performance, or observation contract remains valid.

### Required correction

Reusable Production Revision updates need an explicit compatibility result for every relevant consuming contract, conceptually:

```text
COMPATIBLE_AS_IS
COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION
REQUIRES_REVIEW
INCOMPATIBLE
```

The exact persistence shape is not frozen here.

### Historical rule

A compatibility translation used by historical execution is downstream realization/execution provenance. It never rewrites the old Production Revision, old Performance Revision, or old captured Shot.

---

# 22. Required architecture clarifications that are not defects

These findings should be made explicit, but they do not invalidate the product model.

## CL-1 — Narrative time labels versus canonical topology

The pressure-test clock labels are human-readable story annotations.

Current SoloRing already has a canonical random-access narrative ordering through sequence/scene/shot boundaries. The Product Architecture should avoid implying that absolute wall-clock-like story timestamps already exist as production authority.

A future continuous story-clock domain may be useful, but it is not required to satisfy the current full-sequence test so long as every event/Shot can be placed unambiguously in canonical narrative topology.

## CL-2 — Derivation bundles have independently adoptable outputs

One creation/reconstruction/import derivation may produce candidate camera, geometry, lighting, motion, and identity matches. Approval must be per owned production fact, not per opaque bundle.

## CL-3 — Shot-local source substitution preserves instance identity

A Shot-local typed replacement of one Production Revision with another should preserve the addressable occurrence identity unless the filmmaker explicitly requests a new occurrence.

## CL-4 — Production-state consequences should be reviewable separately from Take approval

When a Take depicts an event with possible persistent consequences, the Review workspace should make those consequences separately visible/adoptable. Approval of the Take alone must not authorize them.

## CL-5 — Candidate confidence is evidence, not acceptance priority

High-confidence inference may help review order but never outranks explicit production authority or filmmaker adoption.

---

# 23. Capability gaps revealed but not architecture failures

The sequence confirms several future capabilities are required, while the current architecture already reserves appropriate authority boundaries.

| Gap | Why it is needed | Architecture status |
|---|---|---|
| Reusable Production Revision publication | Physical set/character/prop reuse | Architecture defined; implementation absent |
| Composition + instance authoring | Persistent reusable sets | Architecture defined; implementation absent |
| Generic world-state extension | Persistent prop/door/possession state | Architecture direction defined; instance subject correction needed |
| Performance Revision | Intra-Shot pose/deformation/action | Concept defined; implementation model unresolved |
| Within-Shot event authority | Persistent changes during a Shot | **Architecture correction CR-3 required** |
| Physical relationships | Contact/support/attachment | Concept defined; vocabulary unresolved |
| Candidate-world ingestion | Partial reconstruction/import adoption | Concept defined; implementation absent |
| Observation capability negotiation | Fail before queue on unsupported hard constraints | Architecture defined; execution contract unresolved |
| Production Revision compatibility | Safe asset upgrades | **Architecture correction CR-5 required** |
| Composition↔spatial binding | Make reusable geometry agree with world authority | **Architecture correction CR-2 required** |
| Instance state binding | Persistent state on exact composition occurrence | **Architecture correction CR-1 required** |
| Instance lineage across composition revisions | Preserve `chair-07` through set upgrades | **Architecture correction CR-4 required** |
| Character rig/deformation | Hero character performance | Explicitly future |
| Editorial/finishing authority | Full post-production pipeline | Explicitly future and not required for this test |

---

# 24. Filmmaker UX acceptance findings

The architecture is strongest where it turns authority distinctions into occasional meaningful choices rather than continuous technical configuration.

## 24.1 UX patterns that pass

The following should remain core product behavior:

```text
Approve
Publish
Update available
This Shot only
From this story moment onward
Update reusable set
Create reusable variation
Fork
Promote to reusable object
Review persistent consequences
Choose compatible execution path
```

These phrases correspond to real production consequences the filmmaker understands.

## 24.2 UX patterns that would fail

The product fails if routine filmmaking requires choices such as:

```text
select database authority table
choose foreign-key target
edit canonical JSON
manually manage immutable hashes
choose materialization cache identity
select graph node IDs
manually remap scene hierarchy paths
resolve model-specific control tensors
```

Those remain advanced diagnostics/implementation details.

## 24.3 Scope prompt frequency

SoloRing should not ask for scope on every manipulation.

It should ask only when the same visible edit could legally affect multiple authority domains.

The current editing context may establish a default. For example:

```text
Shot workspace      → default local
Set workspace       → default working composition
Story State workspace → default persistent narrative state
Production Object workspace → default reusable object
```

The UI must still surface a clear scope indicator and require explicit promotion for consequential cross-scope changes.

## 24.4 Consequence review

For state-changing Shots, a useful review surface is:

```text
TAKE APPROVAL
Approve visual result?     [Approve Take]

PERSISTENT CONSEQUENCES
Chair 7 remains fallen     [Adopt] [Ignore]
Forehead injury = fresh    [Adopt] [Ignore]
Vase broken                [Adopt] [Ignore]
```

This keeps Take canon and world-state canon separate without making the filmmaker navigate low-level state machinery.

---

# 25. Cross-sequence invariants

A corrected architecture must satisfy all of these simultaneously.

## 25.1 Identity invariants

1. Eva's story identity survives visual/physical/renderer evolution.
2. Lobby identity survives camera/view changes.
3. Production Object identity survives representation changes.
4. Addressable instance identity survives composition publication when the occurrence survives.
5. Source Production Revision changes do not automatically mint a new addressable instance.
6. State never retargets by display name, hierarchy path, or proximity.

## 25.2 Temporal invariants

1. Persistent state resolves from narrative position, not edit order.
2. Off-screen time requires no continuous rendering.
3. Shot-local changes do not persist unless explicitly promoted/adopted.
4. State-changing events inside a Shot can establish downstream state without marking the whole Shot as already changed at frame zero.
5. Shot/end persistent handoff agrees with the authoritative within-Shot terminal event state.

## 25.3 Authority invariants

1. Semantic fact precedes visual realization.
2. Composition does not override spatial authority by file order.
3. Production realization cannot contradict higher semantic/visual/spatial authority.
4. Simulation/reconstruction/generation remain candidate sources.
5. Take approval does not promote reusable/world-state authority automatically.
6. Different final-image properties may have different authoritative sources.

## 25.4 Historical invariants

1. Published revisions are immutable.
2. Captured Shots pin exact revisions.
3. Current update convenience never floats inside history.
4. Historical rerun performs zero current production resolution.
5. Missing historical closure fails closed.
6. Compatibility translation is execution-only and historically recorded when materially determinative.

## 25.5 Execution invariants

1. Preview and final execution derive from the same production authority/bindings.
2. Renderer controls are observations, not production identity.
3. Unsupported hard requirements fail before expensive execution.
4. A new executor creates a new Generation/observation specification, not a new Shot identity.

---

# 26. Architecture correction gate

Before producing a normative Capability & Ownership Map or implementation roadmap from Product & Production Architecture v1.0, the architecture should be revised narrowly to close `CR-1` through `CR-5`.

The correction should **not** prematurely freeze database nouns or choose implementation technology.

It should add only the load-bearing product/authority contracts needed to make these statements unambiguous:

```text
1. What durable subject owns persistent state for an addressable production instance?

2. How is an exact Composition Revision proven to realize an exact SpatialWorldRevision?

3. How does an event that occurs inside a Shot hand off to persistent state after the Shot?

4. How does one addressable instance retain identity across Composition Revisions?

5. How is compatibility decided when a newer Production Revision replaces an older one
   under existing spatial state, relationships, or performance?
```

A revised Product & Production Architecture should then rerun this exact pressure test without changing the scenario to make the architecture pass.

---

# 27. Final verdict

## 27.1 Overall disposition

```text
CONDITIONAL FAIL — ARCHITECTURE CORRECTION REQUIRED BEFORE ROADMAP
```

This is a productive failure.

The pressure test confirms that the **core SoloRing product direction is coherent**:

```text
persistent production world
+ explicit adoption
+ immutable revisions
+ story-time continuity
+ reusable composition
+ replaceable observation/execution
+ historically pinned Shots
```

The architecture successfully handles:

- same-set reuse across different cameras;
- local versus reusable edit scope;
- explicit candidate/adoption boundaries;
- off-screen world memory;
- nonlinear flashback resolution;
- current production upgrades without historical mutation;
- variable generative-control requirements;
- downstream invention without automatic promotion;
- simulation/reconstruction as candidate sources;
- executor replacement;
- historical rerun and fail-closed missing provenance.

However, the sequence exposes five load-bearing seams that cannot be left as implementation details:

```text
CR-1  persistent state/spatial authority subject for addressable Production Instances
CR-2  CompositionRevision ↔ SpatialWorldRevision binding
CR-3  within-Shot event/performance ↔ Shot-end persistent-state handoff
CR-4  addressable instance identity across Composition Revision evolution
CR-5  Production Revision substitution compatibility
```

Until these are closed, the architecture cannot truthfully guarantee the central workflow:

> **Update the reusable lobby during production, return to it later in story time, keep the exact same continuity-significant chair and its fallen state, render it from a new camera, and preserve every earlier captured Shot unchanged.**

That workflow is essential to the product.

## 27.2 Recommended next artifact

The next artifact should be a **narrow Product & Production Architecture v1.1 correction**, limited to `CR-1`–`CR-5` and the clarifications in §22.

After v1.1, rerun this pressure test verbatim.

Only when it passes should SoloRing proceed to:

```text
Capability & Ownership Map
        ↓
implementation roadmap
        ↓
implementation milestone planning
```

No repository implementation work is authorized by this verdict.
