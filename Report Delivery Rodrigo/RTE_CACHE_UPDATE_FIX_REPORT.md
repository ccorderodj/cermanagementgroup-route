# RTE · Stale mobile app after deployment — fix report

**Date:** 2026-10-29 · **Branch:** `fix/stale-app-after-deploy` · **MR:** !__MR__
**Status:** COMPLETED WITH PENDING VALIDATION (implemented and tested locally; Android and iPhone device checks and the production header check pending after deploy)

## Root cause — CONFIRMED

Evidence: production headers (`curl -I`, 2026-10-29), Starlette source and the webpack config.

| Fact | Evidence |
|---|---|
| The entry bundle always has the same URL | `base.html` loaded `/static/javascript/main.js` and `css/main.css`; `buildWebpackConfg.ts` had `filename: '[name].js'` (the hash line was commented out); chunks were named `140.js`, `189.js`… |
| Every file carries a 1980 date | Production: `last-modified: Tue, 01 Jan 1980 00:00:01 GMT` on `main.js` and `main.css` (DO buildpack) |
| No freshness directive | Production: `Cache-Control: private` (no `max-age`); local: no `Cache-Control` at all |
| So the browser applies heuristic freshness | 10 % of the time since `Last-Modified` ≈ 4.6 years: `main.js` is reused without asking the server. The HTML is fresh, but it points to the same cached URL |
| Revalidating alone would not fix it | Starlette ETag = `md5(mtime-size)` (`starlette/responses.py:334`). With a fixed mtime, a new build of the same size returns **304** |
| Not the CDN | `cf-cache-status: BYPASS` on assets and HTML |
| Not a Service Worker | There is none in the repo |
| Chunks were worse | An old cached `main.js` loaded **new** `140.js` content under the same name: silent mismatch |

Not the cause (by elimination, UNVERIFIED in the field): stale API data, missing permissions or an incomplete deploy. The symptom matches old code exactly, and with the old fixed names the build identifier was not observable.

## Changes

| File | Change |
|---|---|
| `app/core/build.py` (new) | `build_id()` = 12-hex SHA-256 of `main.js` + `css/main.css`. `StaticConBuild`: hashed chunks `public, max-age=31536000, immutable`; everything else `no-cache`; every static response gets `X-CER-Build` |
| `app/main.py` | `/static` served with `StaticConBuild` |
| `app/core/utils/web_routers.py` | `build_id()` available in all templates |
| `app/templates/base.html`, `403.html`, `404.html` | `main.js?v=<build>`, `main.css?v=<build>`, `<meta name="cer-build">`; dead commented script tag removed |
| `app/core/middleware/security_headers_middleware.py` | HTML responses `Cache-Control: no-cache` (setdefault: explicit headers win) |
| `app/configwebpack/build/buildWebpackConfg.ts`, `buildPlugins.ts` | `chunkFilename: '[name].[contenthash].js'` / `css/[name].[contenthash].css`; dead commented blocks removed |
| `shared/lib/appUpdate/` (new) | On `visibilitychange`→visible, `pageshow` (bfcache) and `online`: one `HEAD main.js?check=…` (at most once per 60 s, skipped offline, static so no session and no 401 → login); a different `X-CER-Build` raises the notice |
| `widgets/AppUpdateNotice/` (new), `index.tsx` | Notice "A new version is available… **Later** / **Reload**". Never reloads by itself. `ChunkErrorBoundary`: a missing chunk (`ChunkLoadError`, `CSS_CHUNK_LOAD_FAILED`) shows the notice instead of a blank page; other errors behave as before |
| `docs/ARCHITECTURE.md` | The mechanism |

No Service Worker, PWA, new dependency, new endpoint, public-surface change, storage clearing, or change to GPS, offline queue, routing, mileage, RBAC or tenant scope.

## How an update propagates

1. **Any navigation or reopen after the deploy:** the HTML is revalidated and requests `main.js?v=<new>` → the new UI loads **automatically**. CER Route is server-routed, so every page change is a full load.
2. **A tab left open** (e.g. My Route all day): when it returns to the foreground or reconnects, the notice appears. It applies on **Reload**, a user-approved refresh. **There is no hot replacement.**
3. **What a reload preserves:** session (cookie), WorkSession and trips (server), offline queue and GPS evidence (IndexedDB, keyed by user and tenant, untouched). Unsaved typing in an open form is lost only if the user presses Reload, which the notice warns about.

## Tests

| Check | Result |
|---|---|
| `npm run check` (tsc + eslint) | exit 0 |
| `npm run build:prod` | exit 0; `main.js` + `css/main.css` + 41 JS and 1 CSS chunks, **all hashed**; 2 pre-existing size warnings |
| `tests/test_static_build.py` (new): same size + same 1980 date → different build; entries `no-cache`, chunks `immutable`; `HEAD` and `304` carry the build | 5/5 PASS |
| `tests/integration/test_stale_bundle_pages.py` (new): real page has `?v=<build>`, the meta tag and `no-cache`; no unversioned bundle URL | 2/2 PASS |
| `tests/e2e/test_stale_bundle_browser.py` (new, Edge, 390 px): new build → notice, **no auto-reload, typed text kept**, Reload → full page; same build → no notice and a second event within 60 s does not probe again; offline → no probe, back online → notice; deleted chunk → notice, not a blank page | 4/4 PASS |
| Wiring, public surface, catalog, frontend source completeness, odometer and route-map headers, login E2E, offline-queue isolation E2E, offline durability E2E (reload/restart keeps pending evidence) | 80 + 57 PASS (run separately; see finding 1) |
| Full regression (local, `-n 3`) | 1773 passed, 2 failed, 15 skipped · 1 h 31 min. **F1** `test_provisioning_alignment` (16 vs 12 `route_admin` capabilities): known, unrelated. **F2** `test_rte09_reports_browser::test_escritorio_…`: `Page.goto: net::ERR_NO_BUFFER_SPACE` on `/login`, Windows socket exhaustion late in the E2E queue (LIKELY environment); file rerun alone: 3/3 PASS |

### Browser and device coverage

| Target | Status |
|---|---|
| Edge desktop (Chromium), mobile viewport | **Tested** (Playwright, local) |
| Chrome Android | **NOT RUN** on a device. Same Chromium engine and APIs (`visibilitychange`, `pageshow`, `online`) |
| Safari iPhone / iOS Chrome / iOS Edge (all WebKit) | **NOT RUN.** WebKit is not installed here. The APIs used are standard and supported; bfcache is covered by `pageshow.persisted` |

## Findings

1. **Mixed invocation errors (UNVERIFIED cause):** one run with 13 paths mixed (root, integration and e2e) produced 56 `fixture 'seeded' not found` errors in files that pass on their own (57/57) and in pairs with the new file (42/42, 73/73). Not reproduced with the new file; it is not a product defect.
2. **CSP:** no inline script was added; the meta tag is data only.

## Residual risks

- **Header rewriting by DO/Cloudflare is UNVERIFIED** until deploy: production added `Cache-Control: private` where the origin sent none. `?v=` and hashed chunks fix the problem even if `no-cache` were overwritten.
- **Tabs opened before this deploy** still run the old `main.js`, which has no notice logic. They get the new version on their next navigation or reopen, because the HTML already arrives fresh, not while they stay open. **This deploy is the one that starts the mechanism.**
- **Rollback** is safe: the old build has different `?v=` and chunk names. Tabs of the rolled-back build see the notice. The deleted chunks of the other build show the notice, not a blank page.
- Device validation (Android and iPhone) is pending.

## Deployment and rollback

1. Merge into `dev` → normal DO deploy. No migrations, env vars or data changes.
2. Check in production: `curl -I https://cerroute.cermanagementgroup.com/static/javascript/main.js` must show `Cache-Control: no-cache` and `X-CER-Build`. A page's source must show `main.js?v=…`.
3. Field test: on an Android phone and an iPhone, open My Route, deploy any change, bring the tab back → notice → Reload → new UI. No data clearing.
4. Rollback: redeploy the previous commit. Nothing to clean.
