# SoloRing M14 R2 — Freeze Erratum E-1

**Status:** PLAN FREEZE ERRATUM — NARROW CORRECTION — NOT IMPLEMENTATION AUTHORIZATION BY ITSELF
**Date:** 2026-09-11
**Frozen plan amended:** M14 R2 frozen plan SHA-256 `68f910f5ff132fe00345fc41fa07f25e650d74ccd3f7ec445822194c03bde860` (118,086 B / 3,132 ln) — the frozen document itself is NOT modified; this erratum is its narrow successor for exactly the sections below.
**Trigger:** M14B-4 closure exposed frozen-plan STOP #20: §15 freezes `visual.identity` and `continuity.instance_feature` as UNSUPPORTED in the initial v2 profile, but the §17 grammar (whose every capability entry must resolve to a materializer) has NO honest representation of "known but unsupported" — omitting the rows necessarily yields UNKNOWN under §8.10, conflating the two verdicts the plan mechanically distinguishes.

## E-1a — §8.10 verdict law (amended)

```text
exact supported tuple                                    → SUPPORTED
exact unsupported tuple (unsupported_capabilities)       → UNSUPPORTED
property declared by the profile (EITHER list), exact
requested tuple absent                                   → UNSUPPORTED
property absent from BOTH supported and unsupported
declarations                                             → UNKNOWN
PERMITTED_INFERENCE                                      → non-blocking, capability null
```

## E-1b — §17 profile grammar (amended)

The closed observation field set gains exactly one field:

```json
"unsupported_capabilities": [
  {"property": "...", "preservation": "...", "source_contract": "..."}
]
```

Entries carry NO materializer (they claim absence of support, never support). Validation: closed three-key entries; property/preservation within the frozen vocabularies; a tuple declared both supported and unsupported rejects; the combined tuple set stays unique.

## E-1c — §18 descriptor semantics (amended)

Descriptor schema 4 REQUIRES a RealizationProfile schema 3. A hash-coherent schema-4 descriptor over a schema-2 profile rejects at semantic validation: descriptor 4 exists because profile schema 3 / WorkflowSpec schema 4 introduce the new execution semantics, and a schema-4 wrapper without them claims the version without the semantics it identifies.

## E-1d — §15 matrix and §41 negatives (wording alignment)

The v2 matrix rows `visual.identity → UNSUPPORTED` and `continuity.instance_feature → UNSUPPORTED` are now mechanically exact (the profile declares them in `unsupported_capabilities`). N1/N2 assert UNSUPPORTED; the separate fifth negative (a property absent from both lists, e.g. a test profile with `occurrence.placement` removed) remains the distinct UNKNOWN proof. No other matrix row changes.

## E-1e — affected golden vectors (regenerated)

```text
99b8390d812d4301acd873786b463b1a3ee6dc7e3e9f137385229faaf0506f95  observation block      (was 8a8d7f89…)
71072e913fa7e5b4e763f73c2e98f214f81834e5e539d486a9df7d2e09b4cc0b  full profile fixture   (was 3c7b92a9…)
fbe711f9d16d33877a26f59070ed62b545e78f97ecaa2f3182910acbc1f082f1  WorkflowSpec schema 4  (was ab588364…)
2b319394735ab80da8c5e19e1b415db47511c3b3db4d33b4be11095125a3036a  NegotiationResult      (UNCHANGED — same requirements, verdicts, echoes)
49195475e3ce29c25f650f3e265d7f90400a3bb221e11f794c38f937cc1f8988  WorldObservationSpec   (UNCHANGED)
dd3511218c673e7f2727d8226c3d73bfd85222bd5f9a5edb3d2e4779146f66d0  MaterializerContract   (UNCHANGED)
```

## E-1f — implementation surfaces (recorded)

```text
server/soloring/observation/capability.py      grammar + amended verdict law
server/soloring/spatial/production_package.py  production_unsupported_capabilities()
                                               + the v2 observation block carries it
server/soloring/realization/packages.py        descriptor-4 ⇒ profile-3 (E-1c)
tests/fixtures/m14/*.json + m14_pins.json      regenerated vectors + pins + erratum record
```

## Scope boundary

No other section, gate, architecture, authorization, or proof-cell ownership changes. M14B-5 remains separately authorized after this erratum's audit.
