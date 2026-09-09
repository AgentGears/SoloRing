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
