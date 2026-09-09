# Post-M13 Next.js Critical Security Remediation — Windows Production-Mode Proof (SEC5)

Frozen R2 (`4c3d1846bba75b1395dd504c3d01e03542ad120dba93c40e7ed88b4012fd3d31`) §12. The Windows-host-specific RCE (GHSA-p293-qw3h-jr36, no known workaround on affected Windows-hosted applications) makes this proof mandatory; Linux CI cannot close it.

## Environment (Windows deployment class)

```text
security commit   6bd48dcd899e99d6b4cd07e3b7b95c34e107fbf0
tree              11aca88becfd70aa66f6b5595246e745d6c43417
OS                Windows 11 Pro 10.0.26200 (build 10.0.26200.9168)
Node              v22.20.0
npm               11.5.2
next              15.5.25 (exact pin)
react / react-dom 19.2.8 / 19.2.8 (exact pins)
@types/react      19.2.18 · @types/react-dom 19.2.7 (exact pins)
SOLORING_API_ORIGIN mode   production smoke: stub origin
                            (http://127.0.0.1:8788) set for BOTH the
                            build and `next start -p 3000` — the /api
                            rewrite destination resolves at build time
```

## Frozen §12 sequence — results

```text
npm ci                 added 177 packages in 15s (from the committed
                       lockfile — clean install proof)
npm test               28 files / 124 tests PASSED (rc=0)
npx tsc --noEmit       0 errors (rc=0)
npm run build          GREEN (production bundle under stub origin,
                       six dynamic routes)
npm start              `next start -p 3000` production server
```

## Mechanical probes (scripts/next_security_smoke.py, rc=0)

```text
/                            -> 200, fixture project name rendered
/projects/p1 (dynamic route) -> 200, fixture rendered through the
                               controlled backend fixture
/api/security-probe          -> 200, body EXACTLY the stub body
                               (production /api proxy semantics)
/_next/static/<asset>        -> 200, 173019 bytes,
                               application/javascript; charset=UTF-8
no-store                     -> backend /projects reads 2 -> 3 across
                               two page requests (server reads are not
                               cached between requests)
```

No exploit payload was used; evidence is patched identity + advisory
absence + normal production behavior (frozen §12). Screenshots do not
own this proof — every assertion above is mechanical.

## Security identity at the proof

```text
lockfile next      15.5.25 (above the 15.5.24 patch floor)
GHSA-p293-qw3h-jr36   ABSENT from live runtime audit
GHSA-2xp9-vwfh-vxw4   ABSENT from live runtime audit
runtime audit      0 findings at every severity
Next exception     REMOVED (baseline exceptions EMPTY)
```
