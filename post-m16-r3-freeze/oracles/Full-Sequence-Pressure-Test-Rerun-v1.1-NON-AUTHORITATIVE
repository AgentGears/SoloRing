# SoloRing Full-Sequence Product Pressure Test — v1.1 Architecture Rerun

**Document:** SoloRing Full-Sequence Product Pressure Test — v1.1 Architecture Rerun  
**Version:** 1.0-rerun-1  
**Date:** 2026-09-01  
**Status:** Architecture pressure-test result — not an implementation plan and not implementation authorization  
**Architecture under test:** SoloRing Product & Production Architecture v1.1  
**Architecture SHA-256:** `8c15126f6abbdb8657291d8ee94fef36eedb013a5d682c7d7586e5c0ad46b00e`  
**Unchanged pressure-test specification:** SoloRing Full-Sequence Product Pressure Test v1.0  
**Pressure-test SHA-256:** `d25116eb0d61eaac2012e15872bf6e22c45c0644466669af3c913ca65cfec996`  
**Predecessor architecture v1.0 SHA-256:** `7dcb13b795dd2fad77c58b5c342644246ad9f8ae86a0a5d4c2fb2d625d8a5447`  
**Implementation baseline:** M10F @ `6f5d9771e3e67fa4097b7b7babab238d1f57a57e`

---

# 0. Rerun mandate

This document reruns the **same product-pressure scenario, same Shot cases, same adversarial negatives, and same cross-sequence invariants** defined by SoloRing Full-Sequence Product Pressure Test v1.0.

The pressure-test specification is not edited to make the revised architecture pass. Its exact SHA-256 remains:

```text
d25116eb0d61eaac2012e15872bf6e22c45c0644466669af3c913ca65cfec996
```

Only the architecture under test changes:

```text
Product & Production Architecture v1.0
        ↓
CR-1 through CR-5 corrected
CL-1 through CL-5 made explicit
        ↓
Product & Production Architecture v1.1
```

The rerun asks one question:

> **Does v1.1 now support the unchanged full-sequence product test without authority ambiguity, identity loss, temporal contradiction, hidden current-state dependence, or model/executor memory becoming production truth?**

A capability that is intentionally future work may remain unimplemented without failing this architecture test, provided the authority boundary, historical behavior, and failure semantics are coherent enough to assign ownership in the next capability map.

---

# 1. Overall rerun result

```text
PASS — ARCHITECTURE FIT FOR CAPABILITY & OWNERSHIP MAPPING
```

The five v1.0 architecture blockers are closed at product/authority-contract level:

| Finding | v1.0 | v1.1 rerun |
|---|---|---|
| CR-1 — state/spatial subject for addressable Production Instances | FAIL | **CLOSED / PASS** |
| CR-2 — CompositionRevision ↔ SpatialWorldRevision binding | FAIL | **CLOSED / PASS** |
| CR-3 — within-Shot event ↔ Shot/end persistent handoff | FAIL | **CLOSED / PASS** |
| CR-4 — instance identity across Composition Revisions | FAIL | **CLOSED / PASS** |
| CR-5 — Production Revision substitution compatibility | FAIL | **CLOSED / PASS** |

The rerun still identifies **known capability gaps** in performance/rigging/contact authoring and other future domains. Those no longer represent contradictions in the product architecture; they can now be assigned to explicit owners and milestones without inventing missing authority semantics during implementation.

No implementation, schema, migration, executor integration, repository publication, milestone authorization, or release action follows from this PASS.

---

# 2. Correction closure trace

## 2.1 CR-1 — durable state/spatial authority subject

### Original failure

The test required persistent facts such as:

```text
chair-07 fallen
vase-main broken
lamp-main supported_by desk-main
```

but v1.0 did not define whether an addressable Production Instance that was not a CreativeEntity could itself be recognized by state/spatial authority.

### v1.1 contract

v1.1 now requires every continuity-significant addressable occurrence to resolve to exactly one durable authority subject:

```text
existing CreativeEntity
        or
stateful addressable Production Instance
```

An occurrence already bound to a CreativeEntity does not acquire a duplicate competing subject. A production-only occurrence may use its stable Production Instance identity when it needs independent persistent state or spatial continuity.

Display names, hierarchy paths, representation paths, array positions, and renderer labels are explicitly invalid identity substitutes.

### Rerun effect

`chair-07` and `vase-main` can now remain persistent state targets across Shots and compatible Composition Revisions without polluting semantic identity with one CreativeEntity per incidental production occurrence.

**Disposition: CLOSED.**

---

## 2.2 CR-2 — Composition ↔ Spatial binding

### Original failure

v1.0 said the reusable Composition Revision and selected SpatialWorldRevision “must agree” but did not define a mechanically provable relationship.

### v1.1 contract

v1.1 now requires a versioned immutable binding sufficient to prove:

```text
authority subject
        ↕
exact addressable composition instance
        ↕
exact Production Revision
        ↕
spatial frame/track/placement authority
        ↕
realization basis / origin / unit interpretation
```

The binding is not a second transform authority. It declares which domain owns placement and how the production realization is interpreted relative to that authority.

Publication/capture readiness requires complete and unique required bindings, compatible basis/origin/scale semantics, and one coherent binding used by preview and final observation compilation.

Historical Shots pin the exact binding value/identity or enough exact immutable inputs plus a versioned deterministic rule to reconstruct the same value without current-state queries.

**Disposition: CLOSED.**

---

## 2.3 CR-3 — within-Shot event and persistent handoff

### Original failure

v1.0 could resolve persistent state at Shot boundaries and represent time-varying Performance, but it did not close:

```text
uninjured at Shot start
→ cut appears at 3100 ms
→ fresh injury persists after Shot/end
```

without incorrectly treating the whole Shot as already injured or letting generated pixels author downstream state.

### v1.1 contract

v1.1 now separates:

```text
SHOT-START RESOLVED STATE
        +
SPARSE SHOT-LOCAL STATE-CHANGING EVENT / PERFORMANCE AUTHORITY
        +
EXPLICIT SHOT/END PERSISTENT TRANSITION
```

A persistent event:

- targets the same durable authority subject as its downstream state;
- has immutable Shot-relative timing when captured;
- preserves the actual Shot-start state;
- does not require per-frame database authority;
- requires an explicit Shot/end transition if the consequence persists;
- must agree exactly with that Shot/end terminal state.

Take approval remains separate from persistent-consequence adoption.

**Disposition: CLOSED.**

---

## 2.4 CR-4 — addressable instance identity across Composition Revisions

### Original failure

v1.0 did not explicitly guarantee that:

```text
Lobby 8: chair-07 → Chair Revision 2
Lobby 9: chair-07 → Chair Revision 3
```

retains one occurrence identity.

### v1.1 contract

Addressable instance identity now belongs to the composition lineage rather than one Composition Revision row.

Publishing a new revision preserves the identity of every surviving occurrence by default. Source Production Revision change, compatible realization update, or Shot-local source substitution does not mint a new occurrence identity.

Identity-changing operations are explicit and lineage-bearing:

```text
remove
replace-as-new-occurrence
split
merge
occurrence fork
```

Any persistent state, spatial binding, relationship, Shot reference, or performance targeting a removed or transformed identity must be resolved explicitly. There is no name/proximity retargeting.

**Disposition: CLOSED.**

---

## 2.5 CR-5 — Production Revision substitution compatibility

### Original failure

Using a newer revision of the “same” Production Object could invalidate existing origin, scale, contact, rig, look, relationship, or observation assumptions.

### v1.1 contract

Every relevant consumer now receives one explicit compatibility verdict:

```text
COMPATIBLE_AS_IS
COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION
REQUIRES_REVIEW
INCOMPATIBLE
```

Assessment may cover:

```text
basis / handedness
origin / pivot
scale / dimensions / bounds
attachment / contact interfaces
rig / deformation contract
performance assumptions
look/material binding
consumption closure
required representations
observation/compiler requirements
```

A deterministic translation is permitted only if meaning-preserving for the consuming contract. Materially determinative translations are pinned where published/captured use depends on them and never rewrite historical source revisions.

**Disposition: CLOSED.**

---

# 3. Clarification closure

The unchanged pressure test also requested five clarifications. v1.1 now makes them explicit:

| Clarification | v1.1 result |
|---|---|
| CL-1 — clock labels vs canonical topology | Human-readable times are annotations; canonical narrative topology remains authority unless a future story-clock domain is separately adopted. |
| CL-2 — derivation bundle adoption granularity | Camera, geometry, motion, lighting, identity matches, relationships, etc. remain independently adoptable under their owning domains. |
| CL-3 — Shot-local source substitution | Existing addressable occurrence identity is preserved by default; a new occurrence requires an explicit identity-changing operation. |
| CL-4 — Take approval vs persistent consequences | The Review product surface must expose/adopt persistent consequences separately from Take approval. |
| CL-5 — confidence | Confidence is evidence/review prioritization only; it never outranks existing authority or adoption. |

---

# 4. Unchanged Shot/detail-case rerun

## 4.1 Shot 21 — first persistent lobby interior

**Expected:** same reusable lobby and exact approved revisions can be captured and later revisited.

**v1.1:** unchanged core path remains coherent.

**Verdict: PASS.**

## 4.2 Shot 22 — reverse angle behind reception desk

**Original:** PASS WITH CR-2 clarification.

**v1.1:** Lobby Composition 8 and SpatialWorldRevision 11 are joined by the exact composition-to-spatial binding. The reception desk and other authority-bound occurrences have unique instance↔subject↔spatial bindings, and the camera change does not mint a new world.

**Verdict: PASS.**

## 4.3 Shot 23 — Shot-local chair edit

The filmmaker chooses “this Shot only.” `chair-07` retains occurrence identity while the local typed override remains below reusable composition/world-state authority.

**Verdict: PASS.**

## 4.4 Shot 24 — chair falls during the Shot

**Original:** FAIL CR-3.

**v1.1 resolution:** 

```text
Shot/start: chair-07 upright
intra-Shot event: chair-07 fall at authored time
Take approval: visual result only
separate consequence adoption
Shot/end transition: chair-07 fallen
```

The same durable `chair-07` subject is used throughout. Event terminal state and Shot/end persistent transition must agree.

**Verdict: PASS.**

## 4.5 Shot 25 — forehead injury appears during Shot

**Original:** FAIL CR-3.

Eva's existing semantic authority subject is uninjured at Shot start. The Shot-local injury event occurs at its authored time. If the consequence is adopted, explicit Shot/end continuity becomes `fresh`. Later healing transitions remain ordinary boundary state.

**Verdict: PASS.**

## 4.6 Shot 26 — immediate aftermath with no prompt repetition

**Original:** FAIL CR-1 for instance state.

State resolution now yields:

```text
Eva injury = fresh
chair-07 = fallen
```

from canonical authority subjects and narrative transitions, independent of prior generated pixels.

**Verdict: PASS.**

## 4.7 Shot 27 — vase breaks inside Shot

**Original:** FAIL CR-1 / CR-3.

`vase-main` can be a stateful Production Instance subject. Its in-Shot break event and adopted Shot/end `broken` state obey the same handoff contract as `chair-07`.

**Verdict: PASS.**

## 4.8 Shot 28 — possession and door state

Boundary-only before/after transitions remain valid. If production requires exact within-Shot timing, the same sparse event + Shot/end handoff contract applies.

**Verdict: PASS.**

## 4.9 Off-screen interval

Persistent world state remains resolvable without continuous rendering or Shot-output chaining.

**Verdict: PASS.**

---

# 5. Production-update rerun

## 5.1 Chair Production Revision 3

**Original:** Product update concept PASS, but the full return workflow later exposed CR-5.

Before `chair-07` moves from Chair Revision 2 to 3, v1.1 requires compatibility assessment against its spatial placement, contact/relationship assumptions, any performance assumptions, required representations, and other relevant consumers.

Allowed paths:

```text
COMPATIBLE_AS_IS
→ update may proceed

COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION
→ proceed with exact meaning-preserving translation pinned when required

REQUIRES_REVIEW
→ explicit production review

INCOMPATIBLE
→ block until owning authority changes deliberately
```

**Verdict: PASS.**

## 5.2 Publishing Lobby Composition 9

**Original:** FAIL CR-4.

The new composition preserves every surviving addressable occurrence identity. Therefore:

```text
chair-07 remains chair-07
```

while its source may change from Chair Revision 2 to 3 after compatibility succeeds.

Removed instances with live state/relationships cannot disappear silently.

**Verdict: PASS.**

## 5.3 Composition 9 versus SpatialWorldRevision 11

**Original:** FAIL CR-2.

Publication/readiness now validates one exact complete binding between Composition 9 and SpatialWorldRevision 11. Any required authority-bound instance that is missing, duplicated, incompatible, or differently mapped from preview blocks publication/capture/execution.

**Verdict: PASS.**

---

# 6. Shot 51 — return after production upgrades

This is the central unchanged stress case.

The Shot must combine:

```text
Lobby Composition 9
SpatialWorldRevision 11
same durable chair-07 occurrence
Chair Production Revision 3
existing chair-07 fallen persistent state
exact Composition 9 ↔ SpatialWorldRevision 11 binding
successful Production Revision compatibility verdict
new camera
```

v1.1 now gives every seam one authority rule:

1. **CR-1:** `chair-07` is a recognized persistent state/spatial subject.
2. **CR-2:** Composition 9 is mechanically bound to the exact spatial authority.
3. **CR-4:** `chair-07` survives the composition revision as the same occurrence.
4. **CR-5:** Chair Revision 3 cannot enter the occurrence unless its existing contracts are compatible or explicitly translated/reviewed.
5. Historical Shots remain pinned to Lobby 8 / Chair Revision 2.

The fallen state is therefore neither lost nor inferred from the prior video.

**Verdict: PASS.**

This closes the headline v1.0 blocker:

> Update the reusable lobby during production, return later in story time, preserve the exact same continuity-significant chair and its fallen state, shoot it from a new camera, and leave all earlier captured Shots unchanged.

---

# 7. Control-bandwidth rerun

## 7.1 Shot 52 — healing-injury hero close-up

The exact injury state/appearance can remain a hard requirement while incidental detail has narrower authority. An executor that cannot honor a hard required property fails capability readiness before queueing.

**Verdict: PASS at architecture level.**

## 7.2 Shot 53 — lower-control lobby insert

The same production world can compile a lower-bandwidth observation while authoritative identity/state remains unchanged.

**Verdict: PASS.**

---

# 8. Component replacement and promotion rerun

## 8.1 Chandelier Revision 4 approved

Approval creates a newer reusable Production Revision without changing published compositions or captured Shots.

**Verdict: PASS.**

## 8.2 Shot 54 — use Chandelier Revision 4 locally

The Shot-local source substitution preserves the existing chandelier occurrence identity by default. Compatibility still applies if that occurrence participates in binding/relationship contracts.

**Original:** PASS WITH CR-4 clarification.

**Verdict: PASS.**

## 8.3 Promote update to Lobby Composition 10

The new published composition preserves surviving occurrence identities and validates a new exact Composition 10 ↔ applicable SpatialWorldRevision binding.

**Original:** FAIL CR-2 / CR-4.

**Verdict: PASS.**

---

# 9. Generated invention and promotion rerun

A generated key-card holder remains downstream invention until the filmmaker explicitly promotes it to a candidate Production Object, reviews it, publishes it, and explicitly includes it in a later Composition Revision.

The new object does not become authority merely because a Take contained it.

**Verdict: PASS.**

---

# 10. Physical contact and performance rerun

## 10.1 Shot 58 — exact hand-to-desk interaction

The unchanged test intentionally requires exact contact involving:

```text
Eva physical realization
Reception Desk exact realization
root/world placement
local performance
contact relationship/constraint
camera
```

v1.1 improves revision substitution by placing contact/attachment interfaces and performance assumptions under the general compatibility verdict. It also preserves the separation between root placement, local performance, and relationships.

However, the architecture still deliberately does not freeze the implementation-level character rig/deformation system, contact authoring UI, or complete performance representation.

**Verdict: BLOCKED BY KNOWN CAPABILITY GAP, NOT AN ARCHITECTURE DEFECT.**

This is acceptable for architecture-planning readiness because the missing work now has an explicit authority owner and compatibility boundary.

---

# 11. Flashback rerun

Shot 59 is produced later but occurs at an earlier canonical narrative position.

It resolves:

```text
injury = none
chair-07 = original pre-fall state
vase-main = intact
```

Human-readable clock labels remain annotations; canonical narrative topology determines eligibility. Current Production Revision choices may differ if deliberately selected, but story-state facts remain earlier-state facts.

**Verdict: PASS.**

---

# 12. Candidate-world ingestion rerun

One derivation may propose camera, identity matches, geometry, motion, deformation, lighting, and relationships. v1.1 explicitly permits independent adoption of those outputs.

High confidence can prioritize review but cannot auto-approve or override existing authority.

The filmmaker may adopt only the camera trajectory while rejecting geometry and identity matches.

**Verdict: PASS.**

---

# 13. Performance-candidate rerun

Tracked/reconstructed/generated/simulated performance remains:

```text
candidate
→ compatibility/contact review
→ explicit adoption
→ immutable Performance Revision
```

It does not redefine character identity, wardrobe, physical body, or story-state facts.

The exact first implementation-level Performance representation remains future work.

**Verdict: BLOCKED BY KNOWN PERFORMANCE CAPABILITY GAP, NOT AN ARCHITECTURE DEFECT.**

---

# 14. Simulation rerun

A simulated lamp fall remains a candidate result. If the filmmaker rejects it, existing story/world state remains authoritative.

A support relationship may move from inferred → validated → authoritative only through its owning review/adoption path.

Production Revision changes affecting contact/support interfaces are now compatibility-gated.

**Verdict: PASS at architecture level.**

---

# 15. Executor replacement rerun

## 15.1 Unsupported hard control

An executor that cannot satisfy required injury/camera/identity/spatial controls fails before queueing rather than silently weakening the Shot.

**Verdict: PASS.**

## 15.2 Compatible alternative executor

The same ShotRevision can compile a different exact observation specification for a compatible executor and create a new Generation/Take without redefining the Shot.

**Verdict: PASS.**

---

# 16. Historical isolation rerun

## 16.1 Exact Rerun of original Shot 22

Historical execution resolves only from the captured graph:

```text
historical ShotRevision
exact historical Production Revisions
exact historical Composition Revision
exact historical composition↔spatial binding
exact historical authority-subject identities
exact historical execution inputs
```

It does not consult current Lobby 9/10, current Chair revision, current state resolvers, or current compatibility verdicts to reinterpret history.

**Verdict: PASS.**

## 16.2 Missing historical representation/closure

Missing or corrupt required historical closure fails closed. No current/latest/regenerated approximation is substituted.

**Verdict: PASS.**

---

# 17. Adversarial negative-scenario rerun

All twenty-four unchanged negative cases now have explicit fail-safe behavior.

| ID | Required behavior under v1.1 | Rerun |
|---|---|---|
| N-01 | Unpublished required Production Revision blocks readiness | PASS |
| N-02 | Incompatible composition/spatial transforms block; explicit binding cannot choose by order | PASS |
| N-03 | Mutable unpublished dependency blocks publication closure | PASS |
| N-04 | Tracking reference must pin exact revision before capture | PASS |
| N-05 | Generated prop cannot register directly into reusable authority | PASS |
| N-06 | Reconstructed identity match remains candidate until review | PASS |
| N-07 | Rejected simulation outcome cannot override story/world authority | PASS |
| N-08 | Conflicting placement claims block; no incidental tie-break | PASS |
| N-09 | Silent new identity for surviving `chair-07` violates stable-occurrence rule and blocks publication | PASS |
| N-10 | Incompatible Chair Revision substitution blocks via compatibility verdict | PASS |
| N-11 | Mid-Shot injury captured only as all-Shot end state is invalid; sparse event + handoff required | PASS |
| N-12 | Take approval cannot auto-create persistent Shot/end transition | PASS |
| N-13 | Deleting current working composition cannot erase historical captured graph | PASS |
| N-14 | Missing old historical representation/closure fails closed | PASS |
| N-15 | Executor unable to honor hard requirements blocks before queue | PASS |
| N-16 | Flashback cannot inherit later state from editorial order | PASS |
| N-17 | Local edit cannot become reusable state without explicit scope/promotion | PASS |
| N-18 | Same bytes via different derivations preserve distinct provenance | PASS |
| N-19 | Multiple consumer representations for one Production Revision are valid | PASS |
| N-20 | Compatibility translation cannot rewrite historical source bytes | PASS |
| N-21 | Candidate-world derivation cannot force one opaque all-or-nothing approval | PASS |
| N-22 | Stateful instance without recognized authority subject blocks readiness | PASS |
| N-23 | Removed occurrence with live state/relationships blocks until explicit retirement/migration decision | PASS |
| N-24 | Preview/final different composition↔spatial mapping blocks because one exact binding owns both | PASS |

No negative case requires a display-name/path/proximity fallback or executor-specific convention to determine production truth.

---

# 18. Cross-sequence invariant rerun

## 18.1 Identity invariants

| Invariant | Result |
|---|---|
| Eva identity survives visual/physical/renderer evolution | PASS |
| Lobby identity survives camera/view changes | PASS |
| Production Object identity survives representation changes | PASS |
| Addressable occurrence identity survives composition publication when occurrence survives | PASS — v1.1 stable lineage |
| Source Production Revision changes do not automatically mint a new occurrence | PASS |
| State never retargets by display name/path/proximity | PASS |

## 18.2 Temporal invariants

| Invariant | Result |
|---|---|
| Persistent state resolves from canonical narrative position, not edit order | PASS |
| Off-screen time requires no continuous rendering | PASS |
| Shot-local changes persist only through explicit adoption/promotion | PASS |
| Mid-Shot event can establish downstream state without changing Shot-start truth | PASS — v1.1 sparse event contract |
| Shot/end handoff agrees with authoritative terminal event state | PASS — v1.1 required equality |

## 18.3 Authority invariants

All six original authority invariants pass. The Composition↔Spatial binding now removes the only unresolved cross-domain authority seam exposed by the test.

## 18.4 Historical invariants

All six original historical invariants pass. Compatibility/binding decisions used by captured work are immutable historical inputs or reconstructible only from exact pinned immutable identities under versioned deterministic rules.

## 18.5 Execution invariants

All four original execution invariants pass. Preview and final execution are required to consume the same exact authority/binding state; observation remains downstream and replaceable.

---

# 19. Residual capability gaps

The rerun deliberately does **not** turn every future feature into architecture closure work.

The following remain real capability/design gaps but no longer block the production model:

| Capability | Rerun classification |
|---|---|
| Reusable Production Revision persistence/publication | Architecture coherent; implementation absent |
| Composition + instance authoring | Architecture coherent; implementation absent |
| Stateful Production Instance integration with current state/spatial resolvers | Architecture coherent; implementation extension required |
| Composition↔Spatial binding persistence/resolver | Architecture coherent; implementation design required |
| Sparse within-Shot event authority | Architecture coherent; implementation design required |
| Production Revision compatibility evaluator(s) | Architecture coherent; domain-specific implementation required |
| Performance Revision | Authority/lifecycle coherent; representation/editor unresolved |
| Character rig/deformation | Future capability |
| Exact contact authoring/validation | Future performance/physical-relationship capability |
| Physical relationship vocabulary | Authority semantics coherent; exact vocabulary future |
| Candidate-world ingestion | Architecture coherent; implementation absent |
| Observation capability negotiation | Architecture coherent; implementation contract future |
| Editorial/finishing authority | Explicitly future independent domain |

These items are now appropriate inputs to a Capability & Ownership Map because their authority boundaries and historical rules are sufficiently clear to assign responsibility without improvising core semantics inside a milestone.

---

# 20. Filmmaker UX rerun

The corrected architecture continues to expose production decisions in filmmaker language rather than implementation nouns.

The sequence can be expressed through actions such as:

```text
This Shot only
From this story moment onward
Approve Take
Review persistent consequences
Update available
Update reusable set
Keep same occurrence
Replace as new occurrence
Requires compatibility review
Promote to reusable object
Fork
```

Two v1.1 UX consequences are especially important:

1. **Persistent consequence review:** approving a visual Take does not silently adopt the fallen chair, injury, broken vase, or other downstream state.
2. **Compatibility review:** when a reusable revision update affects physical/spatial/performance assumptions, the user sees an actionable review requirement rather than a silent technical substitution.

The architecture does not require the filmmaker to manage authority-table names, immutable hashes, compatibility payload bytes, or binding internals directly.

**Verdict: PASS at product-model level.**

---

# 21. Final architecture verdict

## 21.1 Disposition

```text
PASS — ARCHITECTURE FIT FOR CAPABILITY & OWNERSHIP MAPPING
```

Version 1.1 survives the unchanged full-sequence pressure test without the five load-bearing contradictions found in Version 1.0.

The central product workflow now has a complete authority explanation:

```text
publish Lobby Composition 8
        ↓
chair-07 receives stable occurrence identity + durable authority subject
        ↓
Composition 8 binds exactly to applicable spatial authority
        ↓
chair-07 falls during Shot 24 through a sparse authored event
        ↓
separate persistent consequence adoption creates agreeing Shot/end state
        ↓
chair-07 remains fallen off screen
        ↓
Chair Revision 3 becomes available later
        ↓
compatibility assessment permits/reviews/blocks substitution
        ↓
publish Lobby Composition 9 while preserving chair-07 identity
        ↓
validate exact Composition 9 ↔ spatial binding
        ↓
return at later narrative position from a new camera
        ↓
resolve same chair-07 occurrence as fallen using newer compatible realization
        ↓
earlier captured Shots remain pinned to Lobby 8 / Chair Revision 2
```

No step depends on generated-video memory, scene-file names, latest/current historical lookup, renderer object identity, or automatic upward authority transfer.

## 21.2 What the PASS does not mean

This PASS does **not** mean:

```text
all capabilities are implemented
all database schemas are designed
character animation is solved
physical simulation is solved
all renderer constraints are technically achievable
all product UI is designed
implementation is authorized
publication/tagging is authorized
```

It means the product architecture is now coherent enough to answer the next planning question:

> **Which capabilities are missing, which authority domain owns each one, what order should they be implemented in, and what existing M10F contracts must each capability preserve or extend?**

---

# 22. Recommended next artifact

Proceed to the **SoloRing Capability & Ownership Map**, followed by the implementation roadmap derived from it.

The map should distinguish at least:

```text
already implemented capability
architecture-defined but unimplemented capability
architecture-defined capability requiring extension of an existing authority domain
new execution-only capability
future design domain not yet ready for implementation
```

It should assign each missing product operation to exactly one primary authority owner and list the dependent authorities it consumes, while preserving the rule that milestone planning must not invent product semantics that this architecture has not authorized.
