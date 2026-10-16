# CER Route — RTE02 Development Instructions

**Checkpoint:** RTE02 — Application Foundation, Access Model, Navigation, Profiles, Vehicles & Configuration  
**Instruction delivery:** 001  
**Authority:** CER Product / Architecture Governance  
**Prerequisite:** RTE01 — **Completed / Certified**  
**Authoritative baseline:** `CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_001.md`

---

# 1. Context

RTE01 is certified and establishes the approved CER Route technical and product baseline.

RTE02 is the **first implementation checkpoint**. Its purpose is to convert the verified CER Application Foundation into the CER Route application foundation without starting the operational Work Session / Trip / Activity lifecycle that belongs to later checkpoints.

The certified RTE01 baseline confirms that the repository already provides reusable cross-cutting capabilities including:

- multi-tenancy;
- authentication and CSRF protection;
- server-side authorization;
- capability catalog;
- append-only audit;
- PostgreSQL + Alembic;
- `BaseDAO`;
- optimistic concurrency;
- `BusinessEnum`;
- React/Jinja page-key shell;
- Redux Toolkit;
- Axios;
- Zod;
- DataTable;
- structured logging and monitoring.

CER Route business domain remains new.

RTE02 must establish the application identity, access model, navigation/shells and the first configuration/master-data capabilities required by later Route checkpoints.

---

# 2. Current State

At RTE02 start:

- repository baseline: CER Application Foundation;
- CER Route domain implementation: not started;
- product code added by RTE01: none;
- current application identity still reflects the generic CER Application foundation;
- Route roles/capabilities are not yet implemented;
- Supervisor mobile shell does not exist;
- CER Route Admin navigation does not exist;
- `supervisor_profile` does not exist;
- Vehicle master and assignment history do not exist;
- Admin-managed Route standard values do not exist;
- Work Session / Trip / Activity execution does not exist and must remain out of RTE02.

The RTE01 certified baseline explicitly authorizes RTE02 to establish:

1. CER Route application identity;
2. Route access model;
3. Route navigation/shells;
4. Supervisor profile foundation;
5. Vehicles and vehicle assignments;
6. Admin-managed standardized lists/configuration.

---

# 3. Objective

Deliver a usable and tested CER Route application foundation on top of the existing platform.

At RTE02 completion:

- the product identifies itself as **CER Route**;
- Route access is governed by server-side capabilities and tenant roles;
- **Supervisor** and **Route Admin** roles exist without duplicating platform administration;
- the application has a Mobile-only Supervisor shell and a responsive Admin shell;
- Supervisor field profile foundation exists without duplicating Core user identity;
- Admin can manage Vehicles and Supervisor vehicle assignments;
- Admin can manage the approved configurable standard-value lists;
- tenant isolation, permissions, audit and history are verified;
- later Route lifecycle functionality can be built without restructuring these foundations.

RTE02 must not simulate or pre-build RTE03+ operational behavior.

---

# 4. Scope

## 4.1 Application identity

Adapt the existing `APP_*` / product identity configuration so CER Route is presented as **CER Route** rather than the generic CER Application foundation.

Reuse the existing configuration mechanism. Do not create a parallel branding/configuration system.

Do not alter tenant resolution, base-domain rules or environment behavior unless technically required and documented.

---

## 4.2 Route access model

Establish the Route authorization model using the existing Core RBAC/capability infrastructure.

The certified RTE01 target capability set is:

- `route.worksession.execute`
- `route.live.read`
- `route.activity.read`
- `route.reports.read`
- `route.reports.export`
- `route.vehicles.read`
- `route.vehicles.manage`
- `route.standardvalues.manage`
- `route.fuelreference.manage`
- `route.records.adjust`

### Capability introduction rule

Do **not** create orphan/dead permissions merely to populate the final catalog early.

If the repository invariant requires each registered capability to protect a real endpoint or surface:

- introduce in RTE02 the Route capabilities actually exercised by RTE02;
- preserve the certified target list in the delivery report;
- add the remaining capabilities in the checkpoint that introduces their protected endpoint/surface.

At minimum RTE02 must exercise:

- `route.vehicles.read`
- `route.vehicles.manage`
- `route.standardvalues.manage`

Do not invent new Route capabilities to duplicate existing Core user/tenant/platform permissions unless a genuine Route-domain authorization boundary requires one. If one is necessary, document the reason.

Authorization must be enforced server-side.

---

## 4.3 Tenant roles

Create the Route tenant roles:

### Supervisor

Purpose:
- Route field user;
- Mobile-only product experience;
- no tenant configuration administration;
- no access to other supervisors' Route records by default.

RTE02 does **not** need to grant future Work Session capabilities before those endpoints exist if doing so would violate repository permission invariants.

### Route Admin

Purpose:
- Route operational/configuration administrator within the tenant;
- access to RTE02 vehicle/configuration management;
- later Route read/report/admin capabilities as those modules are implemented.

### Boundaries

- Do not convert `is_superuser` / platform admin into a tenant role.
- Do not duplicate Core identity, tenant, user-management or platform-admin concepts.
- Role creation/seeding must be safe and idempotent according to repository patterns.
- Existing tenants must not lose existing users/roles because Route roles are introduced.

---

# 5. Existing Components to Reuse

Reuse the Foundation wherever applicable:

- tenant/company resolution;
- existing User model;
- Roles / Permissions / capability catalog;
- authentication;
- CSRF;
- audit infrastructure;
- `BaseDAO`;
- pagination;
- `ensure_version` / optimistic concurrency;
- `BusinessEnum`;
- transaction helpers;
- Alembic;
- React/Jinja page-key pattern;
- existing navigation wiring conventions;
- Redux Toolkit;
- Axios client;
- Zod schemas;
- DataTable / pagination primitives;
- existing form/dialog/sheet primitives;
- logging/monitoring;
- test architecture nets.

Do not build parallel substitutes for existing Core capabilities.

---

# 6. Functional Requirements

## 6.1 Supervisor profile foundation

CER Route must use the existing Core `users` identity.

A Supervisor Route profile is a **thin field-domain extension**, not a second person/user record.

The profile must:

- reference the existing tenant-scoped user;
- contain only Route-specific field attributes actually required at this checkpoint;
- not duplicate name, email, authentication, role membership or tenant identity;
- support resolving the Supervisor's current vehicle assignment;
- preserve future extensibility without becoming a miscellaneous user-data table.

The current/active vehicle should have one authoritative source. If it is derived from `vehicle_assignment`, do not also maintain an independent mutable copy that can drift.

The exact storage pattern is a technical decision for the developer, provided the single-source-of-truth rule is preserved.

---

## 6.2 Vehicle master

Implement a tenant-scoped Vehicle master sufficient for the certified baseline.

Required domain attributes:

- make;
- model;
- year;
- unit / internal vehicle identifier;
- fuel grade;
- operational MPG;
- concurrency/version metadata according to Foundation pattern.

Fuel grade follows the certified baseline model and must use an appropriate controlled enum / DB constraint consistent with Foundation conventions.

Expected supported grades from the certified model:

- Regular;
- Midgrade;
- Premium;
- Diesel.

Vehicle data is operational configuration, not fleet-maintenance functionality.

### Vehicle lifecycle

Vehicle history must remain safe for later Work Sessions and fuel estimates.

Do not make destructive deletion the normal lifecycle for a Vehicle that has historical references.

Prefer the existing repository lifecycle convention (active/inactive or equivalent) if available.

Do not add:

- maintenance scheduling;
- VIN integrations;
- insurance;
- registration;
- telematics;
- odometer capture;
- fuel accounting;
- route optimization.

Those are outside RTE02.

---

## 6.3 Vehicle assignments

Implement effective-dated Supervisor ↔ Vehicle assignment history.

The model must support determining which Vehicle applied to a Supervisor at a point in time.

Required behavior:

- tenant-scoped;
- assignment references an existing Route Supervisor / Core user and Vehicle;
- effective start is retained;
- assignment end/replacement is retained;
- history is not overwritten;
- a Supervisor must not have two simultaneously active/current Vehicle assignments.

Do **not** assume that one Vehicle can belong to only one Supervisor unless an existing approved rule requires it. CER has not approved that exclusivity.

Assignment changes must be auditable.

The current assignment should be resolvable without copying historical Vehicle values into the profile.

---

## 6.4 Standardized configurable values

Implement the tenant-scoped Admin-managed `standard_value` concept approved in RTE01.

The **closed list codes** are:

1. Client Visit Activities
2. Recruiting Activities
3. Employee Visit Reasons
4. Delivery Types
5. Office Purposes
6. Other Activities
7. Outcomes
8. Received By

The list codes are product-defined.

The **values inside each list are tenant data**.

Expected value attributes:

- list code;
- label;
- sort order;
- active/inactive;
- version/concurrency metadata where appropriate;
- tenant/company ownership.

### Rules

- Admin may create values.
- Admin may edit appropriate display/configuration attributes.
- Admin may reorder values.
- Admin may deactivate/reactivate values.
- Normal operation must not hard-delete values in a way that destroys historical meaning.
- A deactivated value must remain resolvable by historical records.
- Values must never leak across tenants.
- Outcomes are configurable tenant data and must **not** become a `BusinessEnum`.
- Do not create catalogs for the approved free-text fields.
- Do not create configurable Activity Types.
- Do not create a dynamic form builder.

The following remain free text and must **not** become `standard_value` catalogs:

- Client Visit destination;
- Recruiting Area / Location;
- Employee / Reference;
- Office;
- Other Area / Location.

---

# 7. Navigation / Web / Mobile Requirements

## 7.1 One product, two shells

Use the existing single React/Jinja application bundle.

Do not create a second independent frontend application.

Establish:

### Supervisor shell

- **Mobile-only in V1**;
- full-viewport/mobile-first;
- no desktop sidebar;
- no data-table-driven supervisor experience;
- follows the existing page-key / shell architecture;
- navigation foundation aligned with the certified RTE01 direction:
  - My Route
  - Activity
  - Me

RTE02 creates the shell/navigation foundation only.

Do not implement fake Work Session / Trip / Activity behavior.

If a destination requires a placeholder because its real module is later, it must:

- contain no fake business data;
- contain no simulated completed functionality;
- be clearly an implementation scaffold;
- not be represented in the delivery report as the future module being complete.

### Admin shell

Reuse/adapt the existing responsive Admin shell.

Prepare Route navigation structure for:

- Today / Live
- Activity
- Reports
- Configuration

Only RTE02 configuration areas are expected to be functional now.

Future areas may be wired as non-business scaffolds only if needed by the architecture; no fake operational data or false completion.

### Configuration in RTE02

Admin must be able to reach and operate:

- Vehicles;
- Vehicle Assignments / Supervisor field setup as appropriate;
- Standardized Lists.

Do not redesign the approved V0.7 product beyond what is necessary to establish this foundation.

---

# 8. Data Model Impact

Expected new Route-domain persistence in RTE02 includes, as technically appropriate:

- `supervisor_profile`
- `vehicle`
- `vehicle_assignment`
- `standard_value`

All Route-domain records must be tenant/company-scoped.

Apply repository invariants for:

- foreign keys;
- company scoping;
- composite tenant-safe references where required;
- `BusinessEnum` + DB `CHECK`;
- optimistic concurrency;
- indexes;
- effective dating/history;
- migration naming/order.

Maintain a **single Alembic head**.

Do not add Work Session, Trip, Activity, Location Fix, Mileage Result, Fuel Reference, Notification or Record Correction domain tables unless a minimal dependency is genuinely required for RTE02. If such a dependency is discovered, stop and document it rather than silently expanding scope.

---

# 9. API Requirements

RTE02 is API-first.

Implement server-side APIs for the RTE02 functional configuration domains using existing `/api/v1` conventions.

The exact route naming may follow repository conventions, but the delivery report must document the final contract.

At minimum the API must support, according to permissions:

### Vehicles
- list/search/paginate;
- retrieve;
- create;
- update;
- activate/deactivate or repository-equivalent lifecycle;
- safe concurrency behavior.

### Vehicle assignments
- resolve current assignment;
- view assignment history;
- create/change assignment;
- end/replace assignment safely.

### Standard values
- list by list-code;
- create value;
- update value;
- reorder if supported through the selected implementation;
- activate/deactivate;
- include historical inactive values when explicitly requested/required by Admin.

### Supervisor profile foundation
Expose only the API surface actually required by RTE02 UI and assignments.

Do not create a broad generic profile endpoint that duplicates Core User APIs.

---

# 10. Roles & Permissions

Server-side authorization is mandatory.

Minimum RTE02 matrix:

| Action | Supervisor | Route Admin |
|---|---:|---:|
| Use Supervisor mobile shell | Yes | Not required as normal persona |
| View/manage all Vehicles | No | Yes, according to `route.vehicles.*` |
| Manage Vehicle assignments | No | Yes |
| Manage Standard Values | No | Yes, `route.standardvalues.manage` |
| Manage tenant users / Core roles | No Route-specific grant | Existing Core authorization only |
| Platform administration | No | No, unless separately platform-authorized |

Do not use frontend hiding as authorization.

Cross-tenant resource access must follow Foundation behavior, including returning the repository-standard not-found behavior rather than leaking resource existence.

---

# 11. Security / Audit

RTE02 must preserve:

- tenant isolation;
- authenticated access;
- server-side authorization;
- CSRF protections;
- minimum privilege;
- Core user identity as source of truth;
- append-only audit for sensitive/configuration changes;
- optimistic concurrency where Foundation expects it;
- no trust in client-supplied tenant identity.

Audit at minimum:

- Vehicle create/update/status change;
- Vehicle assignment create/end/change;
- Standard Value create/update/reorder/status change;
- role/capability bootstrap changes where Foundation audit supports them.

Audit must identify, as supported by the Foundation:

- actor;
- tenant;
- action;
- target;
- timestamp;
- changed values or sufficient change context.

Do not expose secrets or introduce external providers in RTE02.

---

# 12. Out of Scope

Do **not** implement in RTE02:

- Work Session execution;
- Start Work / End Work;
- Trip lifecycle;
- Change Plan;
- Activity execution;
- multi-Activity block behavior;
- geolocation acquisition;
- Recovery Window;
- Missing Location Event;
- mileage calculation;
- routing provider;
- mileage sweeper;
- breadcrumbs;
- offline operational action queue hardening for Route lifecycle;
- in-platform notifications;
- fuel-price ingestion;
- fuel estimate calculation;
- Today/Live operational data;
- Activity Explorer business data;
- reporting/export business logic;
- post-close corrections;
- raw-location retention jobs;
- odometer;
- maps;
- route optimization;
- Supervisor Desktop;
- dynamic forms;
- CER ERP integration.

Do not start RTE03+ merely because foundational hooks are convenient to add.

---

# 13. Edge Cases

At minimum cover:

1. Admin attempts to access a Vehicle belonging to another tenant.
2. Admin attempts to assign a Vehicle from another tenant.
3. User is assigned Supervisor role but has no Vehicle assignment.
4. Supervisor changes Vehicle; historical assignment must remain visible.
5. Two concurrent requests attempt to create overlapping/current assignments for one Supervisor.
6. Vehicle is deactivated while historical assignments exist.
7. Standard Value is deactivated after it has been used historically.
8. Same label exists in different tenants.
9. Same label exists in different list codes within one tenant.
10. Concurrent Admin edits trigger the repository's expected version/conflict handling.
11. Route Admin lacks a capability manually — server denies even if UI route is known.
12. Future navigation route is not yet implemented — shell must not fabricate data or falsely imply feature completion.

---

# 14. Acceptance Criteria

RTE02 is complete only when all applicable criteria below have evidence.

## Foundation / identity

- [ ] Product-facing identity is CER Route.
- [ ] Generic CER Application identity no longer leaks into normal Route UI where product identity is expected.
- [ ] Existing tenant resolution continues to work.
- [ ] Existing platform administration remains intact.

## Access

- [ ] Supervisor and Route Admin roles exist according to Foundation conventions.
- [ ] RTE02 Route capabilities are in the capability catalog and exercised by real protected surfaces/endpoints.
- [ ] No orphan capability is introduced solely for future work if repository invariants prohibit it.
- [ ] Server-side permission enforcement is proven.
- [ ] Cross-tenant access is denied without existence leakage.

## Shell / navigation

- [ ] Supervisor mobile shell exists and does not depend on a desktop sidebar.
- [ ] Admin Route navigation exists.
- [ ] Configuration is reachable and usable.
- [ ] No future Route feature is represented as implemented when it is only scaffolding.
- [ ] Existing page/navigation wiring tests remain green.

## Supervisor profile / vehicles

- [ ] Route profile does not duplicate Core User identity.
- [ ] Vehicle master is tenant-scoped.
- [ ] Vehicle assignment history is effective-dated.
- [ ] One Supervisor cannot have overlapping/current assignments.
- [ ] Historical assignment is retained after reassignment.
- [ ] No cross-tenant assignment is possible.
- [ ] Vehicle configuration changes are auditable.

## Standard values

- [ ] All eight approved list codes are supported.
- [ ] Values are tenant-specific.
- [ ] Outcome remains tenant data, not enum code.
- [ ] Approved free-text fields have not been turned back into catalogs.
- [ ] Values can be deactivated without destroying history.
- [ ] No configurable Activity Type or dynamic form builder is introduced.
- [ ] Changes are audited.

## Technical quality

- [ ] Alembic has one head.
- [ ] Upgrade from the current Foundation baseline succeeds.
- [ ] New database constraints are verified against PostgreSQL.
- [ ] Backend test suite is green.
- [ ] Frontend typecheck/lint/check is green.
- [ ] Architecture/invariant tests are green.
- [ ] No RTE03+ business lifecycle is implemented.

---

# 15. Tests Required

Create or update named tests as appropriate for repository conventions.

At minimum prove:

### Tenant isolation
- Vehicle from Company A cannot be retrieved/updated from Company B.
- Standard Values do not cross tenant boundaries.
- Vehicle assignments cannot cross tenants.

### Permissions
- Route Admin with required capability can manage RTE02 resources.
- User without capability is denied server-side.
- Supervisor cannot administer Vehicles or Standard Values.
- Platform admin boundary is not converted into tenant RBAC.

### Vehicles
- Vehicle create/read/update lifecycle.
- optimistic-concurrency conflict where applicable.
- deactivate/retire behavior preserves history.
- valid fuel-grade constraint.

### Assignments
- current assignment resolves correctly.
- reassignment closes/ends prior effective assignment rather than overwriting it.
- assignment history remains readable.
- overlapping active/current assignments for one Supervisor are prevented at the strongest appropriate layer.
- cross-company user or Vehicle references are rejected.

### Standard Values
- values can be created per approved list code;
- invalid list code rejected;
- values are tenant-scoped;
- deactivate/reactivate works;
- deactivated values remain resolvable for historical use;
- Outcome is not hardcoded as a BusinessEnum;
- duplicate labels are handled according to the implemented documented rule without cross-list/tenant corruption.

### Navigation / shell
- Route page wiring.
- role/capability-driven navigation visibility.
- Supervisor shell wiring.
- Admin shell wiring.
- no broken page-key registration.
- no future placeholder contains fake business data.

### Regression
Re-run the repository's baseline backend, architecture and frontend checks.

Document the exact commands and real results.

---

# 16. Parallel Validation Track

RTE01 identifies **V-1** as a technical validation to run during RTE02/RTE03:

> real-device lifecycle/location behavior on candidate Supervisor client technologies.

If real iOS/Android hardware and the necessary environment are available during RTE02, begin V-1 and document observations.

If not available:

- mark V-1 as `Pending Validation`;
- do not self-certify device behavior;
- do not block the configuration/foundation portion of RTE02;
- do not harden D-03 beyond the certified delegated-decision status.

Do not run V-4 as if the Route lifecycle/offline operational queue already exists; that belongs when the relevant implementation is present.

---

# 17. Do Not Change

Do not reopen or modify certified RTE01 decisions.

In particular, do not change:

- Mobile-only Supervisor V1;
- one product / shared frontend bundle direction;
- Work Session / Trip / Activity lifecycle;
- HOME Trip terminal rule;
- multi-Activity one-block model;
- configurable Outcomes;
- Change Plan rule;
- location evidence levels;
- Missing Location handling;
- road-distance mileage definition;
- no Haversine official fallback;
- no odometer in V1;
- historical Miles immutability;
- raw telemetry vs historical provenance separation;
- fuel variability model;
- Admin-only post-close corrections;
- no Supervisor timezone configuration;
- no ERP dependency.

If RTE02 implementation reveals a contradiction with a certified decision, stop that affected part and report it. Do not silently decide a new product rule.

---

# 18. Checkpoints

Execute RTE02 in the following controlled sequence.

## RTE02-C1 — Product identity + access foundation

Deliverable:
- CER Route identity;
- Route RBAC integration strategy applied;
- Supervisor / Route Admin role foundation;
- only RTE02-used capabilities registered/protected;
- navigation registry/shell wiring foundation.

Verification:
- application starts;
- permission/catalog nets pass;
- no existing platform access regression.

Do not proceed if Core authorization or tenant isolation is broken.

---

## RTE02-C2 — Supervisor/Admin shells

Deliverable:
- Mobile-only Supervisor shell;
- Route Admin shell/navigation;
- page-key / routing wiring;
- Configuration entry point.

Verification:
- no duplicate frontend application;
- no broken routes;
- no fake RTE03+ business implementation;
- role-aware navigation.

---

## RTE02-C3 — Supervisor profile + Vehicles

Deliverable:
- thin supervisor Route profile foundation;
- Vehicle master;
- Vehicle assignment history;
- Admin APIs/UI;
- tenant/security/audit constraints.

Verification:
- current assignment;
- reassignment history;
- no overlap for same Supervisor;
- cross-tenant tests;
- audit evidence.

---

## RTE02-C4 — Standardized Lists

Deliverable:
- `standard_value` domain;
- eight approved list codes;
- Admin configuration UI/API;
- create/edit/reorder/deactivate/reactivate behavior;
- historical-safe lifecycle.

Verification:
- tenant isolation;
- no free-text fields reintroduced as catalogs;
- Outcome configurable;
- no dynamic form builder;
- audit.

---

## RTE02-C5 — Regression + closure

Deliverable:
- migration verification;
- backend/frontend/invariant test results;
- Expected vs Implemented matrix;
- unresolved technical items;
- RTE03 readiness assessment;
- final RTE02 delivery report.

Do not start RTE03 during C5.

---

# 19. Deliverables

The implementation itself must remain in the repository according to the team's normal development workflow.

For CER governance, return **one delivery report**:

`CER_ROUTE_RTE02_DELIVERY_REPORT_001.md`

Do not reuse a generic report filename.

If CER requests corrections, increment the delivery number:

- `CER_ROUTE_RTE02_DELIVERY_REPORT_002.md`
- `CER_ROUTE_RTE02_DELIVERY_REPORT_003.md`
- etc.

Never overwrite an earlier CER delivery report.

The report must include:

1. checkpoint / delivery number;
2. repository baseline used;
3. summary of what was actually implemented;
4. status by RTE02-C1 … C5: `Completed / Partial / Blocked`;
5. files/components changed;
6. migrations added and resulting Alembic heads;
7. data model implemented;
8. APIs implemented;
9. Web/Admin UI implemented;
10. Supervisor Mobile shell implemented;
11. roles/capabilities actually registered and where they are enforced;
12. security/tenant isolation/audit evidence;
13. tests added;
14. exact test commands and results;
15. Expected vs Implemented matrix;
16. deviations;
17. technical recommendations/decisions made by Development;
18. items intentionally deferred to future checkpoints;
19. any new risk discovered;
20. confirmation that no RTE03+ business lifecycle was started;
21. proposed status:
   - `Completed — ready for CER certification`
   - `Partial`
   - `Blocked`

Do not self-certify the checkpoint. CER will perform final validation.

---

# 20. Definition of Done

RTE02 is not done because pages render or code compiles.

It is done only when:

- product identity is aligned;
- access model is server-enforced;
- roles/capabilities are coherent;
- tenant isolation is proven;
- Supervisor/Admin shells are correctly separated;
- Vehicles and assignments are functional and historical-safe;
- standardized lists are functional and tenant-configurable;
- audit is present;
- migrations are valid;
- regression suite is green;
- no certified RTE01 decision was changed;
- no RTE03+ scope was implemented;
- evidence is documented in the incrementally numbered delivery report.

**Target status:** `Completed — ready for CER certification`
