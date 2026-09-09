# Post-M13 Next.js Critical Security Remediation — Implementation Record

Frozen R2 (`4c3d1846bba75b1395dd504c3d01e03542ad120dba93c40e7ed88b4012fd3d31`). Base: `post-m13-hygiene @ 3adead55ca052808260bc4939403bd1fdcc29e13` (tree `d9e0c9b5`). SEC0 evidence: `post-m13-next-security-SEC0-inventory.md`.

## SEC1 — framework dependency transition (commit adc9fef)

Exact pins applied (`next 15.5.25`, `react 19.2.8`, `react-dom 19.2.8`,
`@types/react 19.2.18`, `@types/react-dom 19.2.7` — no carets). Lockfile
regenerated; `npm ci` clean (177 packages); `npm ls` — all five deduped
at target, zero invalid/unmet peers, no `--force`/`--legacy-peer-deps`;
postcss stays 8.5.28 (override RETAINED per frozen §7.4).

Pre-compat gates on the transitioned framework (SEC2 worklist record):
`tsc --noEmit` 0 errors; frontend tests 28 files / 124 passed with
ZERO React-19 source edits (frozen §9 produced no work);
`next build` failed on exactly the two frozen synchronous-param pages
(`PageProps` constraint) — no other compatibility failures anywhere.

## SEC2 — narrow Next-15 compatibility (commit 259c164)

`projects/[id]/production/page.tsx` and `projects/[id]/world/page.tsx`
became Promise-shaped `params` with `await` — identical in shape to the
four routes already migrated. No other source edits (the failing-build
owner rule of §9 admitted nothing else). Gates: `next build` GREEN (six
dynamic routes), tsc 0, fe 124 passed.

## SEC3 — runtime/proxy compatibility

Harness: `scripts/next_security_smoke.py` (stub backend + production
`next start -p 3000` + five mechanical probes). Result — ALL PROBES
GREEN:

```text
/                            -> 200, fixture project name rendered
/projects/p1 (dynamic route) -> 200, fixture rendered
/api/security-probe          -> 200, body EXACTLY the stub body (proxy)
/_next/static/<asset>        -> 200, 173019 B, application/javascript
no-store                     -> backend /projects reads 2 -> 3 across
                                two page requests (no server fetch
                                caching between them)
```

**Production compatibility fact discovered (recorded):** in Next 15 the
`/api/:path* -> SOLORING_API_ORIGIN/:path*` rewrite destination is
resolved at BUILD time into `routes-manifest.json`; server-component
reads (`api.server.ts` → `apiOrigin()`) still read the environment at
request time. A deployment must therefore build AND start under the
same `SOLORING_API_ORIGIN`. The frozen §12 sequence is unaffected (it
builds then starts in one environment); the smoke harness builds under
the stub origin before starting. First harness run failed exactly
because of this (rewrite proxied to the build-time origin while server
components correctly used the runtime env) — fixed by building under
the stub origin; no product source was changed. No FastAPI/backend
change was made or needed (frozen §10/STOP-7 respected).

no-store source proof: the single server-side fetch site remains
`apps/web/src/lib/api.shared.ts` with `cache: "no-store"` (unchanged by
this slice; enforced by the security validator's source scan).

## SEC4 — security closure

- **Next exception REMOVED** (frozen §11.1): the hygiene baseline
  `docs/hygiene/npm-audit-runtime-exceptions.json` now carries
  `"exceptions": []` plus a successor note; the frozen HYG-04 validator
  ACCEPTS the live clean audit against the empty baseline (verified).
- **`scripts/next_security_validate.py`** proves the closure
  mechanically: five exact pins in package.json AND the lockfile;
  postcss override retained with a safe resolved version; Next major
  exactly 15; baseline exceptions EMPTY; neither target GHSA anywhere
  in the audit; zero high/critical; every dynamic page Promise-params;
  forbidden async-request APIs absent; no-store line intact.
  `--pins-only` serves the CI pre-test gate; `--root` serves the
  negative matrix. Live runs at closure: pins-only rc=0; full
  (pins+tree+audit) rc=0.
- **Automated negative matrix**
  (`tests/test_post_m13_next_security.py::test_nsec_sec_04_validator_negative_matrix`,
  18 cases): accepts only the exact frozen shape; rejects pin drift in
  either file, override drift, vulnerable postcss, Next major 16, any
  surviving exception, either target GHSA, any runtime high/critical,
  synchronous params, lost no-store, forbidden APIs. Plus offline
  proofs: predecessor lock reproduces 14.2.35 (BASE:03), SEC0 evidence
  carries both GHSAs (BASE:04), lock peer-graph static satisfaction
  (PKG:04), override retention (PKG:05), locked-next range membership
  (SEC:01/02 offline half). 23/23 green.
- **Live audit at closure:** `npm audit --omit=dev` → **0 findings at
  every severity**; both target Critical GHSAs absent; hygiene
  validator and security validator both ACCEPT.

### Precision note (advisory-range encoding)

The frozen plan §2.2 quotes 2xp9's second affected segment as a bare
`<16.3.3` (GitHub's advisory-UI rendering). Read literally that segment
would also swallow 15.5.24 — contradicting the same advisory's
"patched: 15.5.24" statement. The vendor's patched-versions fact
lower-bounds that segment at 16.0 (it is the 16.x line), and the
offline range proof encodes it that way; the authoritative closure
signal remains the live-audit absence of both GHSAs, which does not
depend on this encoding.

## Source-review corrections (review of 9137c13, frozen R2 unchanged)

Independent source review of `9137c135…` (tree `1dd1c170…`) found four
conformance/proof blockers; all corrected additively, no plan
revision:

1. **F1 — clean-checkout typegen/tsc ordering.** CI now runs
   `npx next typegen` immediately before `npx tsc --noEmit` (Next
   15.5's documented CI sequence), and the Windows §12 sequence gains
   the same step. Empirical nuance, recorded exactly: on this
   toolchain (TS 5.9.3) a clean-state `tsc` does NOT error on the
   unresolved `./.next/types/routes.d.ts` reference in the
   Next-15-regenerated `next-env.d.ts` — `tsc --listFilesOnly` proves
   the route types silently drop out of the program (present after
   typegen, absent before). The defect was therefore a silently
   weaker CI typecheck rather than a red one; the typegen step
   restores route-type validation either way. This also explains why
   the `next-env.d.ts` regeneration only surfaced during SEC6's
   CI-style build.
2. **F2 — postcss semver proof.** The validator's and PKG:05's
   `>=8.5.23 <9` bounds compared version STRINGS (lexicographic
   ordering falsely admits e.g. `8.5.3`). Both now compare numeric
   semver tuples; a six-row regression matrix (8.5.22 and 8.5.3 and
   9.0.0 reject; 8.5.23, 8.5.28, 8.10.0 accept) drives the validator
   itself through `--pins-only` on synthesized lockfiles.
3. **F3 — allowlist exact-path enforcement.** Both boundary
   validators matched allowlist entries by prefix even for exact-file
   entries (authorizing e.g. `next_security_validate.py.bak`). Both
   now use `path_allowed`: directory entries (trailing `/`) alone may
   prefix-match; everything else requires exact equality. An
   automated negative proof exercises BOTH validators' real allowlists
   (near-prefix `.bak`/`-anything`/`.orig` siblings rejected; exact
   files and directory prefixes accepted).
4. **F4 — final-head Windows proof.** The tracked SEC5 evidence was
   for `6bd48dc`/`11aca88b`, whose tree lacked the later
   `next-env.d.ts` typegen change; the proof map's CLOSE:02 wording
   overstated it. Correction: the full §12 sequence (F1-corrected,
   with `next typegen`) is rerun on the exact final correction head
   AFTER the correction commit, with no source changes afterward;
   identity and mechanical results are reported in the re-review
   handoff (no post-proof commits, per the review instruction, so the
   identity loop cannot restart).

Closure-status correction: **NSEC-CLOSE:01 (Linux CI) is PENDING PR
CI** — zero Actions runs exist for the branch head because no PR is
authorized; the workflow source carries every gate and the cell
completes when an authorized PR's CI runs green.
