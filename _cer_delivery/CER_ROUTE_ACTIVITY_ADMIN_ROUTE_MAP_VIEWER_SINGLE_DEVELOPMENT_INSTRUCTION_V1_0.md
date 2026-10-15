# CER Route — Activity Admin: Route Map Viewer (UX Enhancement)

**Single Development Instruction · V1.0 · 15 October 2026**  
**Owner:** CER Product Owner  
**Domain:** CER Route / Administrative Activity  
**Execution:** Technical assessment -> documented library decision -> controlled implementation -> evidence and CER validation  
**Status:** Authorized to evaluate and implement **only within the approved UX and security boundaries below**. Escalate unresolved dependencies before modifying routing, third-party plans, costs, or existing business rules.

## 1. Context / Current State

CER Route already has an integrated **TomTom Routing engine** for estimated travel mileage. Trips can have origin/destination coordinates, and the system may construct a Google Maps directions link; the existence and persistence of route **geometry (polyline/points)** are **not yet confirmed**.

The existing administrative **CER Route -> Activity** view has approved cards (e.g., Office, Other, Client Visit) with headers showing activity name, span, mileage, and an existing details area containing **Travel, At destination, Reason, Outcome and Note**. Current cards, grouping, metrics, filters, period selectors, visual hierarchy, mobile behavior and calculations are the **design baseline**. **Do not redesign them.**

Example of a link already constructible from stored coordinates (reference only, not a route-geometry contract):
`https://www.google.com/maps/dir/35.054898,-79.0491421/35.366818,-78.5587274`

This link identifies endpoints; it does **not** prove that the actual road polyline used by TomTom is persisted.

**Confirmed product decisions:**
- Administrative Activity **only** for this version; not My Route, personal Activity or other dashboards.
- **One new visible control**, `View Route`, inside each eligible activity card. The control is initially collapsed; on activation it reveals the map **below the existing details in the same card**. It becomes `Hide Route` to collapse the map.
- Route is **estimated on roads**, not an actual GPS trail. Existing TomTom remains the **only routing engine**; do not introduce a new one.
- Map access is **configurable by role** and must additionally respect existing tenant and hierarchy scope (CEO may see Sales within its authorized branch; COO/RM never gain access to Sales just by receiving the map permission).
- Developer chooses the **best compatible map visualization technology** after comparing free/open-source choices with evidence, favoring performance and visual quality without unnecessary infrastructure.
- Existing miles, trip calculations, timestamps, state, time zone, GPS capture and already approved workflows remain intact.

**Technical unknowns to verify, not assumptions:** frontend framework/dependencies; TomTom route response and representation; Trip/TripMileage-to-card relations; whether route shape is stored; availability/terms of existing tile/map display providers; RBAC catalog and per-tenant role configuration.

## 2. Objective

Allow an authorized administrator viewing a permitted activity to click **View Route** and see, under that activity's existing detail, an interactive and visually clear map of the **estimated trip route already associated with the mileage calculation**, without changing any existing Activity content, business logic, or mileage.

The rendering component must be mobile-friendly and **loaded on demand**, only for the selected visible route and authorized viewer.

## 3. Scope / Out of Scope

**In scope:**
1. Audit read-only the current Activity card component, routing data and UI libraries, map resources and RBAC conventions.
2. Compare **at least three viable renderer approaches** for free/open-source visualization; select and justify the best match to the current stack.
3. Minimal backend/data presentation contract for a route associated with a given permitted Activity/Trip, if the existing one is insufficient.
4. New role-configurable `route.activity.map.read` capability **or the existing conventionally named equivalent**, using established roles/permissions/provisioning mechanisms with no implicit permission expansion. Default not granted to ordinary roles until configured.
5. Add only `View Route` / `Hide Route` to eligible card headers; render viewer below the existing details on demand.
6. Focused Web/mobile, RBAC, scope, security, rendering and regression tests; provide reproducible implementation evidence.

**Out of scope (Do Not Change):** routing engine, TomTom mileage computation/parameters, distance stored in TripMileage, pricing/fuel computations, GPS/location sampling, visit/work-session flows, status/state, time-zone/date formatting, trip data migration, role hierarchy model, reports, exports, Today/Live, Activity personal, navigation/sidebar, existing activity headings/fields/ordering/layout and unrelated issues. **No new page, global maps dashboard, route optimizer, tracking feature, routing engine, map server or paid service by default.**

## 4. Checkpoint A — AS-BUILT + Free/Open-Source Options (required before implementation)

Perform a focused read-only scan; document concrete file paths, classes/functions, models, endpoint names, response samples with sensitive values redacted, and dependency versions:

- Current Activity Admin card render and data contract: ActivityExecution, WorkSession, Trip, TripMileage, associations and any aggregations; determine whether a card can represent multiple Trips. Verify exactly how card mileage is calculated/presented.
- Existing TomTom integration: specific API/version, route geometry representation (`points`, `encodedPolyline`, GeoJSON or equivalent), whether retained in DB/cache, and whether a display-only access method is possible **without recalculating the official mileage**. Identify whether drawing historic routes can differ from the original TomTom result.
- Existing Google Maps link construction: prove what it contains; do not treat a URL with two coordinates as a persisted road geometry.
- Current frontend bundling/styling architecture and installed mapping packages (if any). Prefer reuse over adding libraries.
- Role/capability assignment UI and backend checks, plus tenant isolation and period-aware historical scope (`WorkSession.started_at`) already implemented. Identify the safe point to authorize route coordinates **before sending them**.
- Whether the TomTom contract/license permits the proposed display of TomTom routing results over the proposed basemap. Validate terms rather than assuming any pairing is permitted.

### Required comparison: rendering alternatives (not routing alternatives)

Evaluate at least these candidates, unless one is demonstrably incompatible:

| Candidate to evaluate | Questions to answer |
|---|---|
| **Leaflet** (open source) | Lowest implementation cost? Lightweight responsive map, route polyline/GeoJSON, lazy load, interaction and accessibility? |
| **MapLibre GL JS** (open source) | Vector appearance and styling vs bundle/GPU/mobile overhead; need for compatible tile/style provider? |
| **OpenLayers** (open source) | Added GIS complexity vs value for a small embedded card map; loading and maintenance? |

If an existing map renderer or **TomTom-compatible visualization SDK already in the repository** is genuinely cheaper/safer, include it as a fourth candidate, but disclose license and usage restrictions. Do **not** propose OSRM, GraphHopper, Valhalla or another routing engine: that work is explicitly excluded.

For every real option, compare **evidence from this codebase**, not marketing claims: integration fit, initial JS/CSS footprint or measured loading cost, render time on representative routes (including longer polylines), memory/cleanup when collapsed, mobile scroll/touch and 390 px layout, visual finish, attributions, permissive license, data privacy, maintenance, operational dependencies and **real costs** (renderer vs tiles vs API calls). Use a small isolated proof of concept/benchmark if appropriate; avoid product code changes before a selection.

**Important distinction:** a free/open-source JS rendering library does not mean free or unrestricted basemap tiles. Check permitted production tile usage, cache and attribution. Public `tile.openstreetmap.org` is best-effort and has restrictions; do not assume it is an unlimited free production service. Check whether existing TomTom map tiles can be reused under the current arrangement and whether requests incur costs.

**Checkpoint A output:** one concise, evidence-based table of options, tradeoffs and estimated bundle/network cost; one recommended technology and tile source; route-data availability and legal/cost constraints; architectural choice and implementation impact. **Technical selection is delegated to the developer within these approved constraints**. If a viable no-new-cost and compliant solution exists, proceed to B and document the decision in the final MD. If geometry is not available or a provider/API must add paid usage, service/infra or material data retention, **stop and request CER approval with alternatives, not a silent workaround**.

## 5. Functional Requirements / UX Contract

**FR-01 Minimal change:** Keep the Activity Admin page visually and functionally unchanged except for the new route toggle and its conditional map panel. Follow the existing design system; do not recreate the cards, restructure rows, add new fields, or change labels in existing details.

**FR-02 Location:** Position the `View Route` control in the **card header near its existing right-side duration/mileage summary**, without disturbing that summary. When opened, insert the route viewer **after** the complete existing detail area, inside the same card. Button text becomes `Hide Route`; another click collapses it.

**FR-03 Visibility:** Show the button only when **both** (a) the viewer has the map capability **and** administrative Activity access/scope for this exact activity, and (b) there is a valid, renderable trip route. A 0.0-mi display value alone is **not** proof that route data is absent; inspect the real trip fields. If a card aggregates trips, do not mistakenly display one arbitrary route as the whole card's mileage. Resolve using existing trip data without inventing a new UI; if not feasible, raise a decision with evidence.

**FR-04 Route fidelity:** Display the road-following shape representing the **estimated route**, using the existing TomTom route information when available. Draw origin/destination markers if supported with existing data and within the same viewer. **Never depict a straight connector as though it were the road route**, and never label a newly calculated/hypothetical route as the original historic route. Keep the historic/official mileage unchanged. Optional `Open in Google Maps` is a secondary link only if the existing link is available and authorized, not a substitute for the embedded map.

**FR-05 Interaction:** Initially collapsed, with **zero map initialization/tile requests while collapsed**. Opening shows only that activity's map; closing disposes or suspends heavy resources as appropriate. Define sensible loading, unavailable, retry and timeout states **inside the viewer**, without errors/crashes or clearing existing details. Reuse route/data requests efficiently, subject to supplier licensing and current retention rules.

**FR-06 Web/mobile:** At 390 px (or smaller as supported by the app), preserve readable summary and an adequately sized, accessible button; wrap/stack within the existing header if necessary. The expanded map stays inside the card width, with bounded responsive height and no horizontal overflow. Avoid trapping the user's vertical page scroll or hijacking touch interactions; avoid unnecessary animations and full-screen transitions. Respect keyboard and screen-reader operation (`aria-expanded`, meaningful labels, focus and error states). Do not alter the rest of mobile Activity layout.

**FR-07 Filter/period consistency:** Existing Day / Week / Month / Year selectors and supervisor/date selection must behave exactly as now. Changing selected activity, period, date, or supervisor cannot leak a previously loaded map for an unauthorized/unrelated trip; dismiss/reset the viewer where appropriate.

## 6. Roles & Permissions / Security / Audit

- Register/reuse a specific **route visualization read** capability, proposed `route.activity.map.read`, following the app's canonical capability catalog and migration/provisioning conventions. Do not assume an existing `route.activity.read` authorizes viewing coordinates. No broad entitlement by default; let the authorized administrator grant it to the desired **roles in that tenant** through the existing Roles & Permissions workflow. Document any pending approval workflow required for role changes. Do not silently grant it to CEO, COO, RM, Supervisor, Sales or generic Core roles. Admin/Superadmin capabilities are not a substitute for this explicit per-role feature decision unless an already approved override policy proves otherwise.
- **AND condition server-side**: authenticated tenant membership + `route.activity.read` administrative access + `route.activity.map.read` + target/activity/Trip in the actor's period-aware organizational scope. Follow existing `route_admin` contract where applicable, but do not widen any role's access or turn inherited organization roles into tenant-wide readers.
- A viewer permitted for COO or RM still **must not** obtain Sales routes; CEO may obtain Sales only under the existing allowed branch and historical period. Users cannot bypass via direct Trip ID, WorkSession ID, route endpoint, guessing filenames or a retained URL. For unauthorized targets use the existing 403/404 concealment conventions.
- Do not expose exact coordinates, route geometry or link through the current Activity list/detail payload to viewers who lack map permission. If current payload already exposes them, document the exposure and close the new path without breaking existing authorized contracts.
- Keep TomTom secrets server-side. Avoid embedding private API keys in browser-delivered code. Any publicly scoped tile key must follow provider restrictions and documented security controls.
- Route geometry and precise locations are sensitive operational data: no cross-tenant caches, cross-user stale responses, logging exact GPS coordinates, analytics payloads or unintended third-party telemetry. Assess the external provider's exposure and retain required attribution.
- Changes to role permissions must remain subject to the existing approval and audit mechanism. Viewing audit is not automatically required for every map open unless that is the product's existing standard; document the applied choice.

## 7. Data Model / APIs / Compatibility

Prefer a **read-only projection** from existing Trip/TomTom route data, linked through the existing Activity model. Avoid database changes unless impossible otherwise, and raise such a dependency for authorization before proceeding.

If adding a read endpoint is necessary, design one narrowly scoped to a specific authorized activity/trip; enforce permission and time-window checks on the server **before serialization**. Return the minimal geometry/endpoint info needed to render, consistent with existing API and TypeScript validation patterns. No new public unauthenticated route endpoints. Respect provenance, TomTom attribution and any retention limits.

Do not recalculate, replace, or persist revised mileage on map opening; no silent historical route recalculation. If historic geometry is missing, inventory how often and why. Additional on-demand TomTom calls are **not presumed free**; measure/check current quota and provider terms, and request CER approval before a material new cost or change of data provenance.

## 8. Edge Cases

Test explicitly: no trip; no coordinates; same origin/destination; zero-mile but valid trip; malformed/out-of-range coordinates; missing or unusable historic polyline; pending/unresolved mileage; activity with multiple related trips; long polyline; route crossing date boundary; superior reassignment/historic scope; user suspended or permission revoked between loading and clicking; cross-tenant/direct ID; concurrent toggles; slow/no map tiles; browser back/period changes; mobile rotate/narrow viewport; role capability removed after first map viewed.

An unrenderable route must not display a false route, error the entire Activity page or provide a bypass through Google Maps. The UI should fail gracefully and preserve existing card information.

## 9. Acceptance Criteria

| ID | Verification |
|---|---|
| AC-01 | Before/after screenshots show Activity cards, fields, values, spacing, aggregates, selectors and workflows remain unchanged except the approved button/viewer. |
| AC-02 | The only new visible control is a contextually placed `View Route`; click toggles to `Hide Route` and displays/closes map below existing activity details, no new page. |
| AC-03 | Desktop and mobile (at least ~390 px) have no horizontal overflow, trapped scroll or inaccessible toggle. |
| AC-04 | No map loads or tile/API requests are triggered until an eligible, authorized viewer clicks the button. |
| AC-05 | Road-following estimated path is visually identifiable; no false straight line/historic reconstruction; official miles unchanged before/after viewing. |
| AC-06 | Disabled/ungranted role: no button and no access to geometry by API. Authorized role with target outside scope: no access. CEO/Sales and COO/Sales negative cases verified. |
| AC-07 | Tenant isolation, direct object ID checks, revoked grants and period-based history enforced server-side. |
| AC-08 | Role-based grant managed through existing permissions/admin flow and audited per existing standards; no accidental global grants. |
| AC-09 | Technical options comparison includes three open-source renderers (or grounded incompatibility), provider/tiles costs and TOS, performance, UX, selection rationale. |
| AC-10 | Existing Activity/Routing/TripMileage, timezone, state, WorkSession, Today, Reports and RTE08 behavior unchanged; regression evidence supplied. |
| AC-11 | Missing route, tile failure and mobile loading states fail gracefully, without exposing private map data or breaking the Activity card. |

## 10. Tests Required

- **Frontend unit/component:** toggle state, eligibility, async lazy loading, error state, period switch, unmount cleanup, responsive behavior, keyboard/accessibility.
- **Backend integration/security:** positive authorized role, default denied role, off-branch and Sales exclusion, CEO valid Sales scope, historic transfer based on `WorkSession.started_at`, tenant crossover, inactive membership, direct Trip/Activity ID and privilege revocation.
- **E2E desktop/mobile:** actual current Activity card with `View Route`, toggle map and close, unchanged values; 390 px, touch-scroll; hidden control for unauthorized user/ungraficable activity; role grant workflow.
- **Regression:** deterministic mile totals and fuel unchanged; Today, Reports, exports, personal Activity, route execution, status and time-zone behavior preserved. Classify pre-existing suite failures separately with evidence; never describe a failing full suite as all green.

## 11. Deliverables / Evidence / Checkpoints

**One final Markdown implementation report**: `CER_ROUTE_ACTIVITY_ADMIN_ROUTE_MAP_VIEWER_IMPLEMENTATION_REPORT_001.md`, containing:

1. **Checkpoint A — Discovery & decision:** AS-BUILT trace (Activity card -> Trip/TripMileage -> TomTom geometry -> API); matrix of at least three map-rendering alternatives and tile sources with compatibility, performance, aesthetics, cost and license/TOS evidence; selected technology with a **documented developer decision** and tradeoffs. Explicitly distinguish what was confirmed from what was assumed.
2. **Checkpoint B — Controlled implementation:** files changed, minimal data/API permission and UI integration, architecture rationale, fallbacks; commit SHA/branch/MR, any migrations, security/audit considerations and screen captures desktop + mobile of **collapsed** and **expanded** states. Demonstrate that only the planned Activity enhancement was modified.
3. **Checkpoint C — Validation:** Expected -> Implemented -> Evidence -> Gap -> Impact for each AC; automated test commands/results, permission/tenant/branch matrix, performance results (before/after bundle/network where feasible), unresolved limitations and rollout/rollback steps; mark **Completed / Partial / Blocked / Pending Validation** honestly.

Deliver no ZIP, mockup redesign, unrelated changes or separate speculative modules. The developer must **not** merge or deploy without CER certification.

**Decision gate:** The developer may select an open-source **renderer** compatible with the existing project without a further PO decision *only if* the result follows this UX, respects TomTom/data licensing, requires no new paid plan or routing infrastructure, and passes the security criteria. If no such route is technically viable, **stop at Checkpoint A** with the options, quantified impact and a focused question for CER rather than implement a noncompliant workaround.

## 12. Technical Reference (orientation, not mandatory dependency)

- TomTom Routing API — route shape and encoded polyline: https://docs.tomtom.com/routing-api/documentation/tomtom-maps/v1/calculate-route (verify the version the project **actually** uses).
- Leaflet: https://leafletjs.com/ ; license: https://github.com/Leaflet/Leaflet/blob/main/LICENSE
- MapLibre GL JS: https://maplibre.org/maplibre-gl-js/
- OpenLayers: https://openlayers.org/
- OpenStreetMap Foundation tile policy: https://operations.osmfoundation.org/policies/tiles/
- TomTom Map Display API (possible existing compatible tiles, not automatically free): https://docs.tomtom.com/map-display-api/documentation/tomtom-maps/v1/product-information/introduction

**Governing principle:** improve the existing Activity UX with one explicit, permission-controlled, lazy-loaded map; **do not rebuild what CER Route already does**.
