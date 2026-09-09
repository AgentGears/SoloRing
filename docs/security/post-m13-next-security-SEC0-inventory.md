# Post-M13 Next.js Critical Security Remediation — SEC0 Inventory

Frozen R2 (`4c3d1846bba75b1395dd504c3d01e03542ad120dba93c40e7ed88b4012fd3d31`). SEC0 evidence record — no product edits in this slice.

## 1. Predecessor identity

```text
branch base (exact)   3adead55ca052808260bc4939403bd1fdcc29e13
tree                  d9e0c9b5cbfaeec902d70b97eed858193f76696a
M13                   384a46d3a5c68d7d81784befc338aa8621b93fbd (immutable)
migration head        0014_m13_authority_complete_world (must remain)
```

## 2. Predecessor package/lock identities (verified mechanically)

```text
package.json   next ^14.2.5 · react ^18.3.1 · react-dom ^18.3.1
lockfile       next 14.2.35 · react 18.3.1 · react-dom 18.3.1 · typescript 5.9.3
overrides      postcss >=8.5.23 <9 (resolved 8.5.28)
```

The checked-in hygiene audit baseline exact-pins `next@14.2.35`.

## 3. Predecessor live audit (2026-09-09, runtime `--omit=dev`)

```text
finding        next — CRITICAL — 23 advisories — range 9.5.0 - 15.5.23
metadata       {critical: 1, high: 0, moderate: 0, low: 0, info: 0, total: 1}

GHSA-p293-qw3h-jr36   PRESENT   (CVE-2026-75604, CVSS 9.0, Windows-hosted unauth RCE)
GHSA-2xp9-vwfh-vxw4   PRESENT   (CVSS 9.5, Image-Optimization AVIF unauth RCE)
```

Both target Critical advisories reproduce at the predecessor — the STOP
condition being remediated. (postcss does not appear: the hygiene
override already remediates it.)

## 4. App Router inventory (re-searched mechanically at SEC0)

Six dynamic route pages under `apps/web/src/app`:

```text
entities/[id]/page.tsx                 params: Promise<{ id: string }>      + await
projects/[id]/page.tsx                 params: Promise<{ id: string }>      + await
shots/[id]/page.tsx                    params: Promise<{ id: string }>      + await
spatial-worlds/[worldId]/page.tsx      params: Promise<{ worldId: string }> + await
projects/[id]/production/page.tsx      params: { id: string }   SYNCHRONOUS
projects/[id]/world/page.tsx           params: { id: string }   SYNCHRONOUS
```

Async-request API search (all NONE): `next/headers`, `cookies(`,
`headers(`, `draftMode(`, `searchParams`, `middleware`, `route.ts`
(route handlers), `experimental-edge`. Also NONE: layout `params`,
`generateMetadata`, `generateStaticParams`. Image inventory: no
`next/image` imports; no `images` config in `next.config.mjs`.
React-19 search: no `ReactDOM.render`, no `useFormState`.

Server-fetch surface: exactly one server-side fetch site
(`src/lib/api.shared.ts:83`, `cache: "no-store"`); `api.server.ts`
routes all server reads through it; remaining fetches are browser
client components. All pages `export const dynamic = "force-dynamic"`.

Rewrite contract: `/api/:path* → ${SOLORING_API_ORIGIN ||
http://127.0.0.1:8000}/:path*` (unchanged from frozen §4.5).

## 5. Codemod dry-run (evidence only — no edits applied)

```text
npx @next/codemod@15.5.25 next-async-request-api src/app --dry --print
result: 2 ok · 9 unmodified · 0 errors · 0 skipped
```

The codemod's own dry-run diff targets EXACTLY the two synchronous
pages (`projects/[id]/production/page.tsx`,
`projects/[id]/world/page.tsx`) with the Promise-params + await shape
— independently confirming the frozen two-page change surface.

## 6. Peer-resolution scratch proof (SEC0 gate)

Scratch lock-only resolution outside the repository (TEMP), exact
target set + retained postcss override, no `--force`/`--legacy-peer-deps`:

```text
next             15.5.25   invalid=None
react            19.2.8    invalid=None
react-dom        19.2.8    invalid=None
@types/react     19.2.18   invalid=None
@types/react-dom 19.2.7    invalid=None
any invalid: False
```

**SEC0 gate: PASS** — the target dependency set resolves without
forced resolution.

## 7. Environment record (Windows deployment class)

```text
OS          Windows 11 10.0.26200 (build 10.0.26200.9168)
Node        v22.20.0
npm         11.5.2
python      .venv (3.12) for backend gates
```

## 8. Freeze-time feasibility re-confirm

Scratch audit preview re-runs (TEMP, 2026-09-09): exact pins + retained
override → 0 findings at every severity; override removed → postcss
8.4.31 high (`<=8.5.22`). Consistent with frozen §21 feasibility
evidence; closure evidence must be reproduced on the implementation
commit in SEC4–SEC6.
