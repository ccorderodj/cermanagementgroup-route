# CER Route - H-1: Mobile Supervisor Filter in User Activity

**Deliverable:** One self-contained corrective checkpoint (H-1)  
**Project:** CER Route (standalone application)  
**Module / surface:** Administration / User Activity Explorer  
**Implementation status:** INSTRUCTIONS APPROVED FOR IMPLEMENTATION; not yet certified as implemented  
**Scope control:** Minimal Web/Mobile UI correction with security verification; no new RTE or sub-checkpoint

## 1. Context and verified baseline

CER Route has two distinct Activity experiences. They must not be conflated:

- **User Activity (administration/consolidated explorer):** `/admin/route/activity`, with existing `GET /api/activity-explorer` and `route.activity.read` permission. It displays data for supervisors within the authorized company, including an administrator's own route activity if that administrator also executes fieldwork and is included in the existing eligible set.
- **My Activity (supervisor execution experience):** `/route/activity`, reached only from the bottom Activity tab of the **My Route** mobile execution shell. In the prior diagnosis this was intentionally an unfinished scaffold. Implementing it is **not** part of H-1.

A prior code-only diagnosis reported:

- Existing component: `features/RouteActivityExplorer/ui/ExplorerFilterBar.tsx`.
- Existing page: `pages/RouteActivityExplorerPage/ui/RouteActivityExplorerPage.tsx`.
- The page passed `showFields={!esMovil}` to the filter bar; that bar rendered the relevant fields conditionally, leaving the supervisor selector unavailable in the mobile layout.
- The existing API accepts `range` (`day`/`week`/`month`/`year`), `date`, and `supervisor_user_id` and validates a supplied supervisor ID within the authenticated company, returning 404 if it is not eligible.
- The admin page and API use the existing `route.activity.read` capability; current admin access is company-wide per the previous diagnosis, **not** a newly invented supervisor hierarchy.

**Evidence classification:** These are previously documented **AS-BUILT** findings, not confirmation of the current branch. Verify the current implementation before editing. H-2 and R-1 have been closed operationally; preserve their behavior.

**Product decision for H-1:** The Product Owner explicitly authorizes a narrow exception to the approved V0.7 mobile layout: the **existing supervisor selector** must be usable from the mobile presentation of User Activity. This does not authorize a screen redesign or additional filters.

## 2. Objective

Make the existing supervisor filter visible, accessible and functional on mobile in **User Activity**, with the same results, permissions, company isolation and selection semantics as its existing desktop implementation. Keep the correction minimal and fully regression-tested.

## 3. Scope

### FR1 - Supervisor selector available on mobile

1. On a mobile viewport, an authenticated, authorized user opening `/admin/route/activity` can see and operate the existing supervisor selector.
2. Reuse `ExplorerFilterBar`, the current options/data source and existing selection state. No second or independently implemented filter.
3. Preserve existing labels, selection meanings, available options, initial/default selection and any existing reset/All behavior. Do not invent a new default.
4. The selector must fit the current mobile layout without horizontal scrolling, clipping, overlaps, unclickable options or interference with results navigation.
5. Do not change the corresponding desktop behavior.
6. If `showFields={!esMovil}` currently controls several unrelated fields, do **not** simply enable all of them on mobile. Expose only the approved supervisor selector, using the smallest compatible adjustment to the existing component/props. Keep all other mobile controls as currently approved unless indispensable to preserve a pre-existing behavior; document any unavoidable effect.

### FR2 - Real filtering and consistent data

1. Choosing a supervisor must use the existing `supervisor_user_id` request parameter and refresh the current Explorer results for that supervisor.
2. The selected supervisor displayed by the control must match the supervisor actually used by the request and the returned summary/detail.
3. Preserving and clearing selection must follow the already implemented desktop behavior, including when the date or range changes, when the selected option is no longer available, and when the page reloads (only if existing behavior supports persistence).
4. Supervisor filtering must work with the existing day/week/month/year ranges and date anchor without changing calculations, metrics, or grouping.
5. Include ongoing `IN_PROGRESS` activities according to the Explorer's current backend behavior. Do not change how activity counts, trips, miles, or time are calculated.
6. Handle loading, empty results and request failures with the current UI patterns; avoid displaying stale data as if it belonged to a newly selected supervisor.

### FR3 - Responsive / interaction quality

1. Validate narrow phones and landscape, with touch and keyboard/accessibility behavior appropriate to the existing selector.
2. Keep the current visual hierarchy, styles, typography, navigation and existing mobile cards/lists.
3. Avoid adding menus, dialogs, panels, routes or a new mobile page.
4. No new labels for the Activity screens: naming above explains the scope; it is not authorization to rename visible UI.

## 4. Roles, permissions and scope

- Preserve page and endpoint requirement `route.activity.read`. Rendering a selector must **not** create or grant access.
- An unauthenticated user and a user without the required capability must remain denied according to the existing authentication/authorization contract; do not relax guards, role seeds, permissions or tests.
- Server-side `supervisor_user_id` validation remains mandatory. Selecting or tampering with an out-of-company or otherwise non-eligible supervisor ID must produce the **existing** non-disclosing response (reported as 404 in the earlier diagnosis).
- The available supervisor choices must come from the existing authorized tenant/company dataset; do not build a client-side global supervisor directory or leak identities across tenants.
- Do not add new role types, personal scope rules, elevated admin grants, ACL overrides, or access to `/route/activity`.
- The previously reported `test_provisioning_alignment` role-capability count mismatch (`route_admin` 14 vs fixture 12) is **outside H-1**. Do not make that test pass by silently changing RBAC or expected privilege counts. Report its status separately if it persists.

## 5. Existing components to reuse

Inspect and reuse the current equivalents of:

- `RouteActivityExplorerPage.tsx` (existing breakpoint and selection state).
- `ExplorerFilterBar.tsx` (existing supervisor selector).
- Current Activity Explorer client API/service and response schemas.
- `GET /api/activity-explorer` and existing backend supervisor authorization.
- Existing mobile responsive styles and UI test infrastructure.

These paths are reference points from the diagnostic, **not** instructions to introduce duplicates if the repository has evolved.

## 6. Data model and API impact

**Expected:** No migration, no new table/column, no new endpoint, no API contract change and no role/permission migration.

Use the existing `supervisor_user_id` filter and current selection-options source. If current code reveals a material contract/security gap, stop that specific expansion and document the evidence and smallest alternatives for PO approval; do not silently widen this checkpoint.

Do not touch timestamps, timezone IANA handling, `session_date`, trip/activity ownership, mileage, or offline sync.

## 7. Edge cases

- Authorized user on a phone selects supervisor A, then B; all shown data belongs to B after loading.
- A supervisor with no results in the selected period: existing empty state, not another supervisor's data.
- Change period/date after selecting a supervisor: retain/reset behavior matches desktop.
- Page opened directly at a narrow width and desktop resized to mobile after selection.
- Several same-day WorkSessions for one supervisor: retain H-2/R-1 aggregation and detail reconciliation.
- An administrator who is an eligible fieldwork user: filtering can include their own records if the desktop/current API already supports them.
- Network failure, slow request or rapid selection: no stale cross-selection data displayed as current.
- Directly manipulated supervisor ID from another tenant: existing server-side rejection; no data leak.
- Caller without `route.activity.read`: no access even if the frontend UI is forced to render.

## 8. Acceptance criteria

- **AC01:** Supervisor selector is visible, readable and operable at typical mobile widths on `/admin/route/activity`.
- **AC02:** Choosing supervisor A or B sends the correct existing filter parameter and displays the corresponding data; desktop and mobile match under equivalent filters.
- **AC03:** Date/range selectors and filter-reset semantics remain correct; no unintended mobile controls appear.
- **AC04:** Existing Today/Live, consolidated User Activity counts, trip details and mile totals remain unchanged by H-1.
- **AC05:** Unauthenticated and unauthorized callers remain blocked by existing guards.
- **AC06:** Requests for foreign-tenant or non-eligible `supervisor_user_id` are rejected server-side using the existing safe status; modifying UI state cannot bypass authorization.
- **AC07:** The admin User Activity view is the **only** Activity view changed. `/route/activity`, My Route bottom navigation and the admin menus remain unchanged.
- **AC08:** No database migrations, no changes to business rules and no new permission grants.
- **AC09:** Desktop layout is unchanged; mobile selector has no horizontal overflow, obstruction or inaccessible tap targets.
- **AC10:** Existing `IN_PROGRESS` activity visibility and H-2/R-1 reconciled aggregates/detail remain intact.

## 9. Required validation

**Before changing code:** establish the actual branch/commit baseline and confirm the current filter implementation, API route and guard behavior. If T-1/T-2 is concurrently in progress, isolate changes and avoid merging or overwriting its files before certification.

**Automated tests (required):**

1. Mobile E2E: visible supervisor selector; switch between two eligible supervisors; assert request/selection/results align.
2. Mobile E2E: change range/date; verify selection and results follow existing semantics.
3. Responsive E2E or screenshot review at approximately 360, 390 and 430 CSS px (plus desktop): no overlap/overflow; current cards/navigation intact.
4. Security integration: request with foreign-company and invalid/non-eligible `supervisor_user_id` returns existing safe denial and no information; unauthenticated/forbidden access remains denied.
5. Regressions for Explorer totals/detail and ongoing activities; no change to H-2/R-1 behavior.
6. Explicitly distinguish new/passing tests, pre-existing unrelated failures, and tests not executed. Do not claim an entire suite ran if it did not.

**Manual validation:** Phone browser using an authorized admin test account; select two supervisors; change period; inspect correct details. Include a screenshot of the selector and filtered results and state the environment/build under test. Do not use an account outside its permitted tenant.

## 10. Out of scope / Do not change

- `/route/activity` supervisor-only My Activity (intentionally separate pending functionality).
- H-3 Current/Last Activity, T-1/T-2 timezone/business day, and P-2 unclosed WorkSession recovery.
- End Work / Keep working, odometer and offline cancellation incidents.
- Any new supervisor administration UI, role/provisioning change, new data access policy or reporting feature.
- Any change to API aggregation, metric formulas, ActivityExecution status handling or reconciled mileage.
- V0.7 mobile navigation and other visual redesigns. **Only the targeted mobile supervisor filter is an approved UI exception.**

## 11. Deliverables and certification

Provide one `CER_ROUTE_H1_MOBILE_SUPERVISOR_FILTER_IMPLEMENTATION_REPORT.md` containing:

1. Baseline branch and commit SHA; exact AS-BUILT confirmed on the starting branch.
2. Expected vs Implemented, including screenshots mobile and desktop.
3. Files/components modified and the actual minimal fix; explain if the old `showFields` prop affected more than the supervisor selector.
4. Security/tenant/permission checks and their executed test evidence.
5. Mobile E2E, desktop regression, full test summary (passed/failed/skipped/not run), and any pre-existing unrelated failures clearly isolated.
6. API/schema/database/permissions impact (state **none** where accurate).
7. Remaining issues classified **Completed / Partial / Blocked / Pending Validation** with exact evidence.
8. Commit SHA, MR link and merge/deployment status.

**Definition of Done:** On a phone, an authorized administrative user can select an eligible supervisor and see exactly that supervisor's User Activity, just as on desktop; other users/tenants cannot access unauthorized data; other views and business logic remain intact. Compiling or showing the selector without successful filtering and authorization evidence is **not** completion.

**Release governance:** Submit the MR and MD for CER Product Owner validation. Do not merge or deploy without approval. Do not create additional checkpoints for this corrective unit.
