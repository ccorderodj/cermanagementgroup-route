# RTE-LOC-02 — Periodic Location Capture (Implementation V1.0)

**Module:** CER Route / Location History · **Checkpoint:** RTE-LOC-02 · **Priority:** U1 → U2 → U3 · **Status:** APPROVED FOR DEVELOPMENT, NOT FOR PRODUCTION ENABLEMENT

## Context / Authoritative baseline
Use **RTE-LOC-01_AS_IS_GPS_DATA_AND_ARCHIVE_DIAGNOSTIC_REPORT.md** and **RTE-LOC-02_PRECHECK_RESULT.md** as evidence. Inspect only cited files and their direct dependencies; reconcile against current `dev` before editing. The approved design is **independent, optional, reversible periodic capture**, not a new Location Engine.

**Approved decisions:** Default **OFF**; when enabled, capture every **300 seconds** during active WorkSession while the Web app can run; interval configurable **per tenant**, with dedicated permission granted **on demand** (no automatic role assignment); separate offline queue and SQL table; read-only unified timeline with current event points. Keep both capture and archived data for later route reconstruction feasibility testing. **No current routing/mileage consumer may read periodic samples.**

## Objective
Implement reliable periodic GPS sampling by reusing the current browser geolocation primitive, with **zero functional change** to existing event captures, operational flows, routing providers, official mileage and End Work. An isolated failure of this feature must not block normal work.

## Scope / Do Not Change
- Existing `location_fix` (append-only), `missing_location_event`, Start Work / Start Trip / Arrived / Activity / End Work, `trip_mileage*`, TomTom/OSRM/Valhalla and routing APIs: **no behavioral, schema or calculation changes**.
- **No** routing reconstruction, maps, route scoring, fuel allocation, DigitalOcean archive job, export, or automatic production activation here (RTE-LOC-03 later).
- Reuse **GPS acquisition**, not the event-specific persistence/deduplication contract. No new microservice, daemon, second GPS engine or capture cron in DigitalOcean.
- Preserve location-required blocking and the exception allowing safe closure when GPS permission disappears.

## U1 — P0: offline isolation + notice (must pass before U2)
1. Audit/fix existing IndexedDB queue paths in `offlineQueue.ts` / `logout.ts`: every pending operational action and location evidence record is attributed to **tenant + authenticated user** (and work session where applicable) when enqueued; flush **only** matching-owner records. Do not silently relabel old ownerless records or send them as the next user: quarantine/migrate safely, with documented disposition. Same browser: logout A → login B never sends A's queue. Do not erase A's queue as a workaround. Preserve legitimate recovery for A.
2. Reuse existing location permission gate (`LocationGate.tsx`, `permission.ts`, server `permission_gate.py`). **No new consent modal or duplicate acceptance flow**. Keep the current UI and button; add just a short factual text when periodic capture is enabled: **“CER Route records your location periodically while you use the app during your workday.”** Correct obsolete assertion in `privacyNotice.ts` that routes are never tracked between events; reuse existing notice where actually shown, and identify any remaining legal/content signoff before production. Do not claim permission equals privacy acceptance.
3. Diagnose the five previously failing RTE-06 offline E2E tests. Verify whether geolocation permission probes consume mocked `getCurrentPosition` calls. Fix the test harness **only if confirmed**; otherwise correct the actual product defect. Record baseline versus corrected results, not merely green counts.

**Gate U1:** cross-user/cross-tenant queue isolation and permission/closure regression demonstrated; no periodic capture activated yet.

## U2 — new independent capture (no existing-engine changes)
**Configuration / UX**
- Add under existing **CER Route Configuration** a small **Periodic Location Capture** settings section: Enable/Disable + interval in seconds + current effective status. Defaults: `enabled=false`, `interval_seconds=300` for all tenants. Proposed safe validation range **60–3600 s** (use unless current standards require stricter bounds; document variance). Never make GPS event captures depend on this switch.
- Persist settings in **Route domain** keyed by `company_id`, not platform/Core policy. `route.locationcapture.manage` is the dedicated **server-enforced** capability, assigned on demand; executors may read only effective config. Validate values, isolate tenants, audit actor/old/new/time, protect simultaneous edits (optimistic version or equivalent). Changes take effect in active clients on next config refresh/cycle without page reload.

**Client / location lifecycle**
- In existing My Route lifecycle (`RouteMyRoutePage.tsx`), run one foreground-only periodic sampler per authenticated **tenant + user + WorkSession** when ON, GPS permission available and session active. Use the existing geolocation acquisition primitive (a timed `getCurrentPosition` call; do not run continuous GPS merely to wait 300 s). Avoid simultaneous requests, overlapping timers and duplicate tabs (reuse existing primitives or tab leadership). Record only actual samples with timestamps, never synthetic points.
- Start while a valid work session is already active; stop immediately at End Work, logout, account/tenant switch, revoked permission, OFF or component disposal. When browser returns to foreground, check whether sampling is due and refresh config; do not claim reliable execution with screen locked, tab suspended or app closed.
- Failures/back-pressure must be bounded, visible in technical metrics and **must not** block existing operation. Keep event GPS calls independent.

**Storage / API / offline lane**
- Add separate `location_sample` storage (monthly archive-friendly, partitioned by `server_received_at` if compatible with the project's migration conventions), with at least: `company_id`, `work_session_id`, server-derived `user_id`, `client_sample_id` UUID, lat/lon, accuracy, `device_captured_at`, `server_received_at`, `interval_seconds_applied`. Preserve relevant permission/quality metadata only if available; no extra device fingerprint/PII. Uniqueness/idempotency for `(company_id, client_sample_id)` or equivalent compatible with partition constraints. Do not modify `location_fix`.
- Add authenticated bulk ingestion (`POST /api/location/samples`, max 50 per batch or equivalent) with tenant + authenticated user + active/legitimate recently closed WorkSession validation, spatial/time/accuracy checks, idempotent retry, per-item accepted/duplicate/rejected. Never trust user/tenant from client payload. Bound retention of unsent points and reject stale/future timestamps using existing security standards; don't invent a long grace silently.
- Create a **separate IndexedDB store/lane** for periodic samples in the existing offline infrastructure. Scope each record/flush by tenant, user, work session; bounded size, retry, concurrency control and no cross-session replay. **OFF** stops creation and sending of periodic samples; preserve queued samples for a documented controlled disposition, not an automatic replay upon switching ON. Operational queue remains unaffected.
- Server/API must reject periodic ingest when the feature is disabled, except for any explicitly designed and tested policy for already queued samples (default: no upload when OFF). Never interfere with or delay existing event evidence submissions.

**Unified timeline (read-only)**
- Build `location_point_timeline` (SQL view or equally lightweight read model) as a **UNION ALL** of existing `location_fix` (`source=event`) and new `location_sample` (`source=periodic`). Output at minimum company, session, derived user, source, timestamp, coords and precision. Associate samples to a trip **provisionally** via matching tenant+session and capture time between trip start and actual arrival/end; do not assign a trip if ambiguous. Respect journeys crossing midnight and distinguish captured vs received timestamps. Tenant/role/scope enforced by backend access path; **no public unscoped location query endpoint**.
- No routing engine, mileage calculator, third-party provider or current map endpoint reads this view in RTE-LOC-02.

## U3 — tests, evidence and delivery
**Minimum acceptance matrix:**
- **Isolation:** A offline → logout → B login/flush; different tenant; ownerless legacy queue; repeat under offline/online transitions.
- **Switch:** OFF means zero new periodic samples and no periodic sends, while Start Trip/Arrived GPS and work actions stay identical. ON = first due sample on schedule; 300 s by default; change interval and OFF without reload; unauthorized update 403; tenant segregation.
- **Lifecycle:** start session, End Work, logout, GPS revoke, background/foreground, two tabs, failed GPS, slow request, long-lived and midnight-crossing session; no duplicate or synthetic samples.
- **Ingest:** duplicate idempotent, 50-item boundary, tenant/session spoofing, timestamps, accuracy, retry/queue retention and bounded errors. Effective authorization checked server-side.
- **Timeline:** event+periodic chronological union; safe trip attribution vs ambiguous intervals, no cross-tenant points, no mutation of `location_fix`.
- **Regression:** existing route operations, event GPS, routing providers and official mileage **unchanged**. Run relevant integration/unit/E2E including five RTE-06 tests. Report any legacy failures transparently.
- **Privacy:** updated short wording, no new permission/consent UI, server-side access control, audit of settings, no raw coordinates in application logs.

## Deliverables / token discipline
1. Minimal code + migration(s) + UX in current Configuration + focused tests. Preserve current navigation baseline; no unrelated refactors.
2. **`RTE-LOC-02_IMPLEMENTATION_REPORT.md` ≤ 900 words**: U1/U2/U3 = Completed/Partial/Blocked; files/migrations/API/UI touched; `Expected → Implemented → Evidence → Gap`; exact test commands/results; screenshots only for new settings and permission text; remaining risks and deployment steps.
3. Stop after **U1** and report if cross-user queue isolation fails, cannot be secured without architectural change, or product behavior differs materially from diagnostic. Otherwise finish U2/U3 and submit MR, but keep feature **OFF** until PO authorizes production pilot. **Do not begin RTE-LOC-03.**

**Efficiency:** work from diagnostics' exact paths; one targeted inspection of changed files; implement only missing deltas; tests by changed surface then relevant regression; concise delivery, no repeated discovery narrative. Unknown behavior must be labeled `PENDING VALIDATION`, never invented as implemented.
