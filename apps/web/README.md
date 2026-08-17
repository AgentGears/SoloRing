# SoloRing web (apps/web)

Next.js 14 + React + TypeScript frontend. Status: **M6 complete** —
project/shot editors, reference assets, Story World (entities, revisions,
explicit approval), narrative structure (sequences → scenes → ordered
shots), Shot semantic dependencies, takes/revisions with continuity
hashes, and generation/rerun surfaces are wired against the M6 backend.

## Run

```bash
npm install
SOLORING_API_ORIGIN=http://127.0.0.1:8000 npm run dev   # http://localhost:3000
```

`SOLORING_API_ORIGIN` is the single backend-origin setting (M2 §4.2):

- `next.config.mjs` uses it as the browser `/api/*` rewrite target;
- `src/lib/api.server.ts` uses it for Server Component requests.

It is server-only (no `NEXT_PUBLIC_` prefix) and must never appear in client
bundles. The legacy `SOLORING_API_URL` name is removed — do not reintroduce it.

## Architecture boundary

- Browser calls go through the Next.js rewrite (`/api/*`).
- Backend Blob URLs stay canonical (`/blobs/...`); `src/lib/api.client.ts`
  contains the only mapper to `/api/blobs/...` and rejects non-canonical input.
- Server Components fetch the absolute origin; data pages are dynamic and the
  production build never contacts FastAPI.
- The frontend implements no canonicalization, hashing, or canon comparison.

## Build gate

```bash
SOLORING_API_ORIGIN=http://127.0.0.1:65534 npm run build   # FastAPI stopped
```

`node_modules/` and `.next/` are gitignored; `package-lock.json` is committed.

> `npm install` reports 2 high-severity advisories in transitive dependencies
> (triage pending; not auto-fixed since `npm audit fix --force` is breaking).
