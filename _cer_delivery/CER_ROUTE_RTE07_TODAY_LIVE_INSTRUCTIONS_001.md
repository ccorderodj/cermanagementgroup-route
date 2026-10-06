# CER Route — RTE07
## Today / Live Operations
### Product Owner Instructions for Development Agent
### Revision 001

## 1. Context

RTE07 implements the approved **Today / Live** administrative experience for CER Route.

This checkpoint is **not a UX redesign**.

The authoritative visual and interaction baseline is the approved CER Route V0.7 mockup shipped with the RTE01 package:

`_cer_delivery/CER_ROUTE_RTE01_PACKAGE_V1_0/04_Mockup_Reference_V0_7/standalone.html`

Development must locate and use that executable HTML/CSS/JS baseline before changing Today / Live.

The current domain already provides the operational facts needed by Today / Live through Work Sessions, Trips, Activities and Official Mileage. RTE07 consumes those facts; it must not redefine them.

RTE10-A01 remains paused. Do not touch OCR, odometer capture, photo retention or related pilot work in this checkpoint.

---

# 2. UX Authority — Mandatory

## 2.1 Visual baseline

For Today / Live, V0.7 is the product-approved source of truth for:

- page structure;
- information hierarchy;
- summary presentation;
- supervisor list presentation;
- labels and terminology;
- ordering;
- selection behavior;
- detail presentation;
- desktop philosophy;
- mobile philosophy;
- responsive behavior;
- drill-in / back behavior.

**Implementation rule:**

> Implement the approved Today / Live experience. Do not redesign it.

If the current repository contains a partially implemented Today / Live page, compare it against V0.7 and align it to the approved baseline rather than treating the existing implementation as a new design authority.

## 2.2 Desktop fidelity

Preserve the approved Admin desktop philosophy:

- existing Admin/sidebar shell;
- Today / Live content in the approved structure;
- summary area in the same visual priority/order;
- supervisor list remains the main operational surface;
- selecting a supervisor opens the approved detail experience;
- desktop detail follows the V0.7 panel behavior rather than creating a new dashboard.

## 2.3 Mobile fidelity

Preserve the approved Admin Mobile philosophy:

- **list-first**;
- large KPI cards must not push the supervisor list below the fold;
- summary information collapses into the compact mobile presentation;
- supervisor list renders immediately below it;
- selecting a supervisor uses the V0.7 `adminMobileDetail` philosophy:
  - full-screen detail/push;
  - clear back action;
  - no desktop side panel squeezed into a narrow viewport.

Do not simplify, remove, reorder or reinterpret the mobile experience merely because the viewport is smaller.

## 2.4 Fidelity gate

Before implementation, Development must map:

`V0.7 element → current component/data source → implementation plan`

If a visible V0.7 element cannot be backed truthfully by the current domain, do **not** substitute another metric or invent a new concept.

Classify it:

`BASELINE / DOMAIN MISMATCH`

and STOP only if the mismatch requires a product decision.

---

# 3. Objective

Deliver a responsive Today / Live administrative view that lets an authorized user understand the current operational state of CER Route supervisors for the current business day, using the approved V0.7 UX.

The view must be based on authoritative server-side domain state and current official mileage facts.

It must remain useful on both desktop and mobile without introducing continuous tracking, maps or new monitoring concepts.

---

# 4. Scope

RTE07 includes:

1. Today / Live page implementation/alignment to V0.7.
2. Responsive desktop and mobile behavior from the approved mockup.
3. Today summary values shown by the mockup.
4. Supervisor list shown by the mockup.
5. Supervisor current operational state shown by the mockup.
6. Current/most-relevant operational activity/context shown by the mockup.
7. Today's Official Miles shown where the mockup requires mileage.
8. Supervisor selection and detail experience.
9. Server-side authorized data set.
10. Automatic freshness while the page is visible.
11. Loading, empty and recoverable error behavior that preserves the approved page structure.
12. Tests for data accuracy, authorization, responsive fidelity and freshness.

---

# 5. Out of Scope

Do not implement or redesign:

- Activity Explorer;
- Reports;
- exports;
- organizational hierarchy;
- CEO / COO / RM / OSM hierarchy rules;
- new map or live map;
- continuous GPS tracking;
- background location tracking;
- new location collection;
- new mileage algorithm;
- odometer/OCR;
- Work Session lifecycle;
- Trip lifecycle;
- Activity lifecycle;
- new Admin dashboard concepts;
- new KPI framework;
- new navigation architecture;
- WebSocket infrastructure solely for this checkpoint;
- RTE08+ functionality.

If a future hierarchy will later narrow Today / Live visibility, RTE07 must remain compatible with that future change, but **must not implement the hierarchy here**.

---

# 6. Existing Components to Reuse

Development must inspect and reuse the existing repository before creating anything parallel.

Reuse where applicable:

- approved V0.7 Today / Live markup/behavior as UX reference;
- existing Admin shell/sidebar;
- existing navigation/page-key infrastructure;
- existing responsive tokens/theme/components;
- existing `DataTable` / `DataTablePagination` if the approved list is implemented as a table/list through those shared components;
- existing Work Session domain;
- existing Trip domain;
- existing Activity domain;
- existing Official Mileage result;
- existing user/supervisor identity/profile data;
- existing company/tenant resolution;
- existing RBAC/capability catalog;
- existing Axios/Zod/API patterns;
- existing loading/error primitives.

Do not create a second source of truth for current state, mileage or supervisor identity.

---

# 7. Functional Requirements

## FR-01 — Today means business/session date

Today / Live must use the authoritative CER Route business day semantics.

Do not derive "today" by naïvely applying UTC date boundaries to event timestamps.

Use the existing Work Session `session_date` / approved business-day semantics.

## FR-02 — Supervisor list is the primary operational surface

The page must expose the authorized supervisors in the structure and order defined by V0.7.

Do not replace the supervisor list with large dashboard cards.

On mobile, the list must remain visible near the top of the experience as defined by the baseline.

## FR-03 — Current operational state must be authoritative

The state shown for each supervisor must be computed from persisted/current domain state, not guessed by the frontend.

The UI must not manufacture a new workflow state.

Map existing Work Session / Trip / Activity states to the **exact Today / Live presentation used by V0.7**.

If the mockup uses a human-readable label that has no direct one-to-one internal enum, Development may map internal states to the approved visible label, but must document the mapping and keep the server/domain state authoritative.

## FR-04 — Current activity/context

Where V0.7 presents the supervisor's current activity, latest operational context, destination or equivalent context, populate it from the relevant authoritative Trip/Activity facts.

Do not redefine "current activity" independently of V0.7.

If no current Activity exists, use the approved V0.7 representation for that state rather than substituting unrelated historical data.

## FR-05 — Today's mileage

Where V0.7 shows miles:

- use **Official Miles** only;
- aggregate for the current `session_date`;
- do not use odometer delta as Official Miles;
- do not use raw GPS/Haversine as Official Miles;
- do not silently replace a Pending official mileage result with another estimate.

The visible representation of zero/pending/unavailable must follow the approved UX or the smallest truthful neutral state consistent with it.

## FR-06 — No map / no surveillance interpretation

Today / Live is an operational status view, not a tracking map.

Do not add:

- maps;
- moving markers;
- background tracking;
- continuous coordinates;
- "last seen GPS" concepts;
- GPS accuracy warnings;
- location diagnostics.

Location evidence may support already-approved domain facts, but RTE07 does not expand collection or expose raw location telemetry.

## FR-07 — Supervisor detail

Selecting a supervisor must open the approved detail experience.

Desktop:
- use the V0.7 desktop detail/panel philosophy.

Mobile:
- use full-screen detail/push;
- preserve a clear back action;
- return to the same Today / Live list context.

Do not create a separate mobile product concept.

## FR-08 — Refresh / freshness

Today / Live must refresh automatically while the page is visible.

Product outcome:

- no manual reload should be required for ordinary operational updates;
- a change made by a Supervisor should become visible to Today / Live within a reasonable Live window, target approximately **30 seconds** while the tab is visible;
- avoid unnecessary refresh work while the tab is hidden/backgrounded.

Development chooses the implementation mechanism.

Do not introduce WebSockets solely for RTE07 unless there is a demonstrated need that cannot be met by the current architecture.

## FR-09 — Empty states

Support truthfully:

- no supervisors available in the authorized scope;
- supervisors who have not started work today;
- active workday with zero Trips;
- active Trip;
- arrived state;
- Activity in progress;
- between Trips / working state as represented by the baseline;
- ended workday;
- mileage still Pending where applicable.

Do not hide a Supervisor merely because they have no active Work Session today if the V0.7 list expects the Supervisor to remain visible.

## FR-10 — Error handling

A refresh/read failure must not convert uncertainty into a false operational state.

Examples:

- API failure ≠ "Supervisor not working";
- mileage read failure ≠ `0 miles`;
- missing current Activity ≠ fabricated historical Activity.

Preserve the last known truthful screen where appropriate or use an existing recoverable error/loading state.

Development chooses the technical mechanism.

---

# 8. Roles & Permissions

Use the existing Today / Live read capability if present:

`route.live.read`

Do not create a broader administrative permission if the existing capability already represents the requirement.

Authorization must be server-side.

Current checkpoint scope:

- an authorized CER Route Admin can read Today / Live for the set currently authorized by the backend;
- a Supervisor must not gain access to other supervisors' Today / Live data merely because the frontend route can be guessed;
- another tenant's data must never be returned.

**Do not implement organizational hierarchy in RTE07.**

The frontend must not decide data scope by role name or hierarchy.

The backend/service must return only the authorized set so a future hierarchical scope resolver can replace/narrow the authorized set without redesigning the Today / Live UI.

If the current access model cannot safely provide the required authorized set, report the exact gap before inventing hierarchy rules.

---

# 9. Data Model Impact

Prefer **no new domain persistence** for Today / Live.

Today / Live is a read model/aggregate over existing operational facts.

Before adding any table or persisted snapshot, prove why the existing:

- Work Session;
- Trip;
- Activity;
- Official Mileage;
- Supervisor/User

cannot produce the approved screen.

Do not persist a duplicate "current status" record merely for the dashboard.

Indexes/query optimizations are permitted where justified by measured query behavior and consistent with existing domain ownership.

---

# 10. API / Service

Provide/reuse an API/service contract appropriate for Today / Live.

The contract should support the approved UI without causing the frontend to reconstruct domain rules from many unrelated endpoints.

Expected product-level output, shaped as needed by Development, includes the facts required by V0.7 such as:

- supervisor identity/display information;
- workday/session state for today;
- approved visible operational state;
- current Activity/context where applicable;
- today's Official Miles / mileage state;
- timestamp/freshness information where the baseline requires it;
- detail data required by the approved supervisor detail view.

Requirements:

- company/tenant scope server-side;
- capability check server-side;
- no client-provided company authority;
- avoid N+1 behavior across the supervisor list;
- no raw coordinate payload unless V0.7 explicitly requires it — it currently does not;
- response validated through existing API/schema patterns.

Development may use one aggregate endpoint or a small cohesive contract based on repository conventions.

---

# 11. Web / Mobile Requirements

## Desktop

Validate at a representative Admin desktop viewport, including approximately:

`1280 × 900`

Confirm:

- baseline structure;
- summary hierarchy;
- supervisor list prominence;
- supervisor detail panel behavior;
- no horizontal breakage;
- no new dashboard layout.

## Mobile

Validate at a representative narrow viewport, including approximately:

`390 × 844`

Confirm:

- list-first;
- compact summary;
- supervisor list visible without large KPI blocks pushing it away;
- touch usability;
- no horizontal overflow;
- full-screen supervisor detail;
- back action;
- return to prior list context.

Responsive implementation may use current design-system breakpoints. Visible behavior must remain faithful to V0.7.

---

# 12. Security / Privacy / Audit

RTE07 is primarily read-only.

Confirm:

- tenant isolation;
- `route.live.read` or approved equivalent enforced server-side;
- no cross-tenant supervisor data;
- no privilege inferred only from frontend navigation;
- raw location data is not unnecessarily exposed;
- no new PII beyond what V0.7 already requires for the operational supervisor list/detail;
- no Today / Live read needs a new audit event unless the existing platform policy already audits equivalent read access.

Do not weaken existing privacy boundaries to make Live feel "more live."

---

# 13. Edge Cases

Validate at minimum:

1. authorized tenant with no supervisors;
2. Supervisor exists but has not started today;
3. Start Work with zero Trips;
4. active Trip `IN_TRANSIT`;
5. Trip `ARRIVED`;
6. Activity `IN_PROGRESS`;
7. Activity completed and Supervisor between Trips;
8. HOME Trip / return-home flow as represented by current domain;
9. ended Work Session;
10. Official Mileage = 0;
11. Official Mileage Pending;
12. current data changes during an open Today / Live page;
13. temporary API/read failure during refresh;
14. another tenant's Supervisor ID/resource;
15. mobile open detail → back to list;
16. page/tab hidden and later visible again;
17. multiple supervisors changing state around the same refresh interval.

---

# 14. Visual Non-Negotiables

Do not:

- redesign Today / Live;
- invent new KPI cards;
- replace the approved list with a different dashboard;
- add a map;
- add charts unless V0.7 already contains them;
- reorder the main information hierarchy;
- change terminology because another label seems clearer;
- squeeze the desktop detail panel into mobile;
- replace mobile full-screen detail with a modal simply for convenience;
- remove approved visible elements because the backend mapping requires work;
- create a new mockup.

If V0.7 and current certified product behavior conflict because of an approved change made after V0.7, the certified product rule wins **only for that conflicting behavior**. Document the conflict; do not use it as permission to redesign unrelated parts of the page.

---

# 15. Development Autonomy

Development owns the technical implementation:

- query composition;
- DAO/service structure;
- aggregate endpoint shape;
- React component decomposition;
- state management;
- polling/freshness mechanism;
- caching;
- loading implementation;
- performance optimization;
- test fixtures.

Development does **not** own reinterpretation of:

- visible UX;
- information hierarchy;
- mobile/desktop philosophy;
- business states;
- Official Miles semantics;
- authorization scope;
- product terminology.

Preferred decision order:

`reuse existing → V0.7 fidelity → authoritative domain facts → server-side scope → low coupling → testability → performance`

---

# 16. Checkpoints

## CP1 — Baseline Mapping + Data Contract

Before broad UI implementation:

1. locate and inspect the exact V0.7 `standalone.html`;
2. identify the Today / Live desktop structure;
3. identify the Today / Live mobile structure and `adminMobileDetail` behavior;
4. map each visible field to an authoritative existing domain source;
5. identify/reuse `route.live.read`;
6. define the read contract/service needed by the page;
7. verify no product decision is required.

If a material mockup/domain mismatch exists, STOP with:

`mockup element → available domain fact → mismatch → options → recommendation`

Otherwise continue.

## CP2 — Today / Live Functional Implementation

Implement:

- authorized Today read model;
- summary;
- supervisor list;
- current state/context;
- Official Miles;
- supervisor detail;
- automatic freshness;
- loading/empty/error behavior.

Validate backend data accuracy and authorization.

## CP3 — Visual Fidelity + Responsive Closure

Validate and align:

- desktop V0.7 fidelity;
- mobile V0.7 fidelity;
- list-first mobile behavior;
- detail interaction;
- responsive layout;
- refresh behavior;
- regression;
- screenshots/evidence at desktop and mobile sizes.

Do not close with known visual deviations hidden as "technical limitations."

---

# 17. Acceptance Criteria

RTE07 Development is complete only when:

1. The exact V0.7 Today / Live baseline was located and used.
2. Today / Live preserves the approved desktop structure and hierarchy.
3. Today / Live preserves the approved mobile/list-first philosophy.
4. Mobile supervisor detail follows the approved full-screen/back behavior.
5. Desktop supervisor detail follows the approved panel behavior.
6. Authorized supervisors are displayed from server-authorized scope.
7. Unauthorized/cross-tenant supervisor data cannot be read.
8. Current operational state is derived from authoritative domain state.
9. Current Activity/context follows the V0.7 semantics.
10. Today's mileage uses Official Miles only.
11. `session_date`/business-day semantics are respected.
12. No map or continuous tracking was introduced.
13. No duplicate current-status persistence was introduced without justified need.
14. Page updates automatically within the defined Live freshness target.
15. Read failure does not become a false business state.
16. Empty/no-session/active/ended states are handled truthfully.
17. Desktop validation is green.
18. Mobile validation is green.
19. No horizontal mobile overflow or unusable desktop layout.
20. Existing Work Session / Trip / Activity behavior is unchanged.
21. Typecheck/lint/build and affected regression are green.
22. No unauthorized hierarchy/RBAC redesign occurred.
23. No `PARTIAL`, `GAP`, `BLOCKED` or unresolved `DECISION REQUIRED` remains inside RTE07 scope.

---

# 18. Tests Required

Provide executed evidence for:

## Data / Backend
- tenant isolation;
- capability enforcement;
- current business day via `session_date`;
- supervisor with no session;
- active session;
- ended session;
- zero Trips;
- current Trip;
- current Activity;
- Official Miles aggregation/state;
- multiple supervisors;
- no N+1 / acceptable query behavior if relevant.

## Freshness
- Today / Live changes after underlying supervisor state changes;
- visible-page automatic refresh;
- hidden/background tab does not perform unnecessary aggressive work;
- foreground returns to fresh state.

## Desktop Browser
At approximately `1280×900`:
- summary;
- list;
- supervisor selection;
- detail panel;
- refresh;
- empty state;
- no structural deviation from V0.7.

## Mobile Browser
At approximately `390×844`:
- compact summary;
- list immediately prominent;
- tap supervisor;
- full-screen detail;
- back action;
- list context restored;
- no horizontal overflow;
- labels/touch targets usable.

## Visual Evidence
Provide screenshots for at least:

1. desktop Today / Live default/list;
2. desktop supervisor detail;
3. mobile Today / Live list;
4. mobile supervisor detail.

Compare them explicitly against V0.7.

---

# 19. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE07_TODAY_LIVE_IMPLEMENTATION_REPORT_001.md`

Keep it evidence-driven.

Include:

1. Executive Result
2. V0.7 Baseline Located
3. V0.7 → Implementation Mapping
4. As-Built Data Contract
5. Today / Live Functional Behavior
6. Desktop Fidelity
7. Mobile Fidelity
8. Roles / Authorization / Tenant Isolation
9. Freshness
10. Official Mileage Semantics
11. Edge Cases
12. Tests / Regression
13. Expected → Implemented → Evidence → Gap
14. Deviations, if any
15. CER Validation Checklist
16. Proposed Status

Any visible deviation from V0.7 must be listed explicitly as:

`baseline → implemented → reason → CER approval required?`

Do not bury visual differences inside technical notes.

---

# 20. Status Rule

Development may propose:

`RTE07 IMPLEMENTATION COMPLETE / READY FOR CER VALIDATION`

only when:

- V0.7 fidelity is demonstrated on desktop and mobile;
- functional data is truthful;
- authorization is enforced;
- relevant regression is green;
- no known RTE07 gap remains.

Development must not declare:

`RTE07 CLOSED`

Final certification belongs to CER.

---

# 21. Do Not Change

Do not use RTE07 to change:

- approved Work Session states;
- Trip states;
- Activity states;
- Official Mileage rules;
- location collection;
- odometer/OCR;
- odometer exceptions;
- tenant model;
- platform Superadmin behavior;
- general RBAC architecture;
- organizational hierarchy;
- Activity Explorer;
- Reports;
- RTE08+;
- unrelated Admin pages.

---

# 22. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE07_TODAY_LIVE_IMPLEMENTATION_REPORT_001.md`

**STOP.**

Do not start RTE08 or any other checkpoint without CER authorization.
