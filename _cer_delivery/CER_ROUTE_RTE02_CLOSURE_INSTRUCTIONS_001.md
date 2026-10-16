# CER Route — RTE02 Gap Closure Instructions

**Checkpoint:** RTE02 — Closure of Admin Configuration / CRUD Gap  
**Instruction delivery:** 001  
**Current status:** `Partial`  
**Previous delivery:** `CER_ROUTE_RTE02_DELIVERY_REPORT_001.md`  
**Target after this correction:** `Completed — ready for CER certification`  
**Do not start RTE03.**

---

# 1. Context

The main RTE02 implementation is accepted as technically aligned:

- CER Route product identity is implemented.
- Route tenant roles are implemented.
- Only the three Route capabilities currently backed by real endpoints were registered.
- Supervisor Mobile shell and Route Admin shell exist.
- Vehicle master exists.
- Supervisor ↔ Vehicle assignment history exists.
- The eight approved Standardized Lists exist.
- Tenant isolation, audit, concurrency and PostgreSQL constraints were tested.
- The current vehicle is correctly derived from the open assignment rather than duplicated.
- `GET /api/supervisors/me` is accepted as an authenticated self-service endpoint and does not require the administrative `route.vehicles.read` capability.
- The existing pagination test generalization is accepted.
- No RTE03+ lifecycle has been started.

RTE02 is **not yet certified** because Admin Configuration is not fully operable from the product UI.

The RTE02 report itself identifies that a Supervisor profile can currently be created only through API and does not have a dedicated Admin action.

CER has now clarified a broader product requirement:

> **CER Route Admin must be able to create and maintain users and administer, through normal product UI, all currently existing Route catalogs/configuration domains.**

This requirement closes a gap that was not represented in the original mockup.

---

# 2. Confirmed Product Requirement

## 2.1 Admin Configuration must be operational, not API-only

For every CER Route configuration/master-data domain currently implemented in RTE02, the normal Admin experience must provide the applicable CRUD operations.

For historical/master data, `Delete` does **not** automatically mean physical deletion.

The required lifecycle pattern is:

`Create → Read → Update → Deactivate/Reactivate`

when physical deletion would break history, audit or references.

Effective-dated relationship records such as Vehicle Assignments follow:

`Create → Read → End/Replace`

and are not destructively deleted as normal operation.

---

# 3. RTE02 Configuration Scope to Close

The Route Admin Configuration area must provide functional management for:

1. **Users**
2. **Supervisor Route designation/profile**
3. **Vehicles**
4. **Vehicle Assignments**
5. **Standardized Lists / Catalog Values**

No configuration domain implemented in RTE02 may depend on manual API calls for normal Admin operation.

---

# 4. Users — CRUD Requirement

## 4.1 Reuse Core User Management

Do **not** create a second CER Route user model.

The existing Core `User` remains the authoritative identity.

Before implementation, inspect the repository's existing:

- Core User APIs;
- Core User UI/components;
- Core user-management capabilities;
- Core role-assignment rules;
- tenant membership rules;
- activation/deactivation lifecycle;
- password/invitation/onboarding mechanisms if already present;
- audit behavior.

Reuse those capabilities instead of duplicating them inside the Route domain.

Do not invent a `route.users.manage` capability if the Core already provides the correct authorization contract.

---

## 4.2 Required Admin User experience

From CER Route Admin → Configuration, an authorized Admin must be able to:

### Create

- create a user within the current tenant using the existing Core flow/contracts;
- capture the fields required by Core;
- create the required tenant membership;
- assign the appropriate permitted tenant role(s);
- designate the user as a Route Supervisor when applicable.

### Read

- list tenant users;
- search/filter using existing reusable capabilities where available;
- open a user detail;
- see active/inactive state;
- see relevant tenant role(s);
- identify whether the user has a Route Supervisor profile;
- if Supervisor, see current Vehicle assignment when one exists.

### Update

- edit the user attributes that Core allows tenant administration to change;
- activate/deactivate according to Core policy;
- manage the Route Supervisor designation;
- manage permitted tenant role assignment through the existing Core authorization model.

### Delete semantics

Normal Admin operation must **not physically delete** a user that has or may have historical references.

Use Core deactivate/disable semantics or the repository-equivalent lifecycle.

A deactivated user must remain historically resolvable.

---

# 5. Route Admin Permissions for User Management

The current `route_admin` role only has `users.read` plus the RTE02 Route capabilities.

That is insufficient for the new confirmed requirement if Core requires additional capabilities to create/update/deactivate users.

The agent must:

1. inspect the existing Core capability catalog;
2. identify the **minimum existing Core user-management capabilities** required for:
   - create;
   - update;
   - activate/deactivate;
   - tenant membership;
   - permitted role assignment;
3. grant only those existing capabilities required by the approved Admin workflow;
4. document exactly which capabilities were added and why.

Do not create duplicate Route-specific user permissions.

### Privilege boundary

Route Admin must never gain platform-level administration through this change.

In particular:

- never grant or manage `is_superuser` through Route Admin;
- do not allow cross-tenant user administration;
- do not bypass existing Core role-assignment safeguards;
- do not allow a Route Admin to assign privileges that the existing Core authorization model prohibits;
- preserve minimum privilege.

At minimum, the UI must support assigning/removing the **Supervisor** tenant role/designation required by CER Route.

If existing Core policy permits broader tenant-role administration, reuse that policy rather than inventing a new Route rule.

If the repository reveals a material unresolved privilege-escalation ambiguity, document it explicitly rather than silently weakening Core controls.

---

# 6. Supervisor Route Profile

Creating a Core User and creating a Route Supervisor profile are distinct concepts.

A user becomes a Route Supervisor only when the corresponding Route profile/designation is created according to the existing RTE02 domain model.

The Admin UI must support this without requiring direct API use.

Required behavior:

- select an eligible existing tenant user;
- create/designate the Route Supervisor profile;
- prevent duplicate Supervisor profiles for the same tenant user;
- show whether a user is already a Route Supervisor;
- allow the Admin to proceed naturally to Vehicle Assignment;
- preserve Core User as the identity source of truth.

Do not duplicate:

- name;
- email;
- authentication data;
- tenant identity;
- role data

inside `supervisor_profile`.

If removing Supervisor designation would conflict with historical/future Route records, prefer deactivate/end semantics rather than destructive deletion. Do not invent physical-delete behavior that can break history.

---

# 7. Vehicles — Complete CRUD/Lifecycle UI

The existing Vehicle domain remains approved.

Verify that the Admin UI fully supports the normal lifecycle:

- Create Vehicle;
- Read/list/search/detail;
- Update Vehicle;
- Deactivate/retire;
- Reactivate/restore.

Retirement must preserve history.

The existing rule remains accepted:

> A Vehicle with an active/current assignment cannot be retired silently.

No odometer, maintenance, insurance, registration, telematics or fleet-management scope is added.

---

# 8. Vehicle Assignments — Complete Administrative Lifecycle

Vehicle Assignment is effective-dated history, not a destructive CRUD entity.

The Admin UI must support:

- view current assignment;
- view assignment history;
- create assignment;
- end current assignment;
- replace/reassign;
- handle a Supervisor with no current Vehicle.

Required rules remain:

- one current assignment per Supervisor;
- no cross-tenant assignment;
- history is retained;
- no destructive deletion as normal operation;
- the current Vehicle is derived from the open assignment.

Do not impose one-Supervisor-per-Vehicle exclusivity unless such a rule already exists and is approved. CER has not approved that restriction.

---

# 9. Standardized Lists — Full CRUD for Values

The following eight list codes remain fixed product configuration:

1. Client Visit Activities
2. Recruiting Activities
3. Employee Visit Reasons
4. Delivery Types
5. Office Purposes
6. Other Activities
7. Outcomes
8. Received By

The **list codes themselves are not CRUD data**.

The **values inside each list are tenant-owned CRUD/configuration data**.

For every one of the eight lists, Admin UI must support:

- Create value;
- Read/list values;
- Edit value;
- reorder values;
- Deactivate/retire value;
- Reactivate/restore value;
- view inactive/retired values.

Historical references must continue resolving after deactivation.

`Outcome` remains tenant data and must not become a hardcoded enum.

---

# 10. What Is Not an Editable Catalog

Do not over-generalize the new CRUD requirement.

The following remain system/product-defined unless CER later decides otherwise:

- the eight `list_code` identifiers;
- FuelGrade enum values;
- Route business states;
- roles/capabilities catalog structure;
- Activity Type contexts;
- Work Session / Trip / Activity states.

Do not build a dynamic catalog-definition engine or dynamic form builder.

The following approved fields also remain free text and must not be converted into catalogs:

- Client Visit Destination;
- Recruiting Area / Location;
- Employee / Reference;
- Office;
- Other Area / Location.

---

# 11. Admin Information Architecture

The existing mockup did not include the complete Configuration administration now required.

This is a **confirmed extension** of the Admin product surface.

Provide a coherent Admin Configuration experience containing, at minimum:

- Users
- Vehicles
- Vehicle Assignments / Supervisor setup
- Standardized Lists

The developer may choose the cleanest navigation structure consistent with the existing Route Admin shell and Foundation patterns.

Do not create a second Admin application.

Prefer reuse of existing Core User screens/components/APIs if they can be integrated cleanly into CER Route Configuration.

The UX should make the operational relationship clear:

`User → Route Supervisor designation → Vehicle Assignment`

without merging those three concepts into one database entity.

---

# 12. Security and Tenant Isolation

All new/updated Admin functions must remain server-authorized.

Required controls:

- tenant derived from trusted server context;
- no client-controlled tenant switching;
- cross-tenant User access prohibited;
- cross-tenant Supervisor creation prohibited;
- cross-tenant Vehicle assignment prohibited;
- Route Admin cannot obtain platform-superuser privileges;
- role/capability changes follow existing Core authorization;
- deactivated users cannot silently retain unauthorized access;
- mutating calls retain CSRF protection;
- optimistic concurrency where existing Core/domain patterns require it.

Frontend visibility is not authorization.

---

# 13. Audit Requirements

At minimum audit:

### Users

- user creation;
- material user updates;
- activation/deactivation;
- Supervisor designation/profile creation or lifecycle change;
- relevant tenant-role assignment/removal according to Core audit capabilities.

### Existing Route configuration

Continue auditing:

- Vehicle create/update/retire/restore;
- Vehicle Assignment create/end/replace;
- Standard Value create/update/reorder/retire/restore.

Audit must preserve, where supported:

- actor;
- tenant;
- target;
- action;
- timestamp;
- previous/new value or sufficient change context.

Do not create parallel audit mechanisms if Core audit already covers User/Role operations.

---

# 14. Edge Cases to Cover

At minimum validate:

1. User created under Tenant A cannot be viewed/edited by Tenant B.
2. Route Admin cannot create a user for another tenant by submitting a foreign tenant/company id.
3. Duplicate or invalid Core identity data follows existing Core validation.
4. Deactivated user remains historically resolvable.
5. User without Supervisor designation cannot receive a Route Vehicle Assignment if the current domain requires a Supervisor profile.
6. Existing tenant user can be designated as Supervisor from UI.
7. Same user cannot receive two Supervisor profiles.
8. Supervisor with no Vehicle is valid.
9. Reassignment preserves old Vehicle Assignment history.
10. Concurrent assignment creation still cannot produce two current assignments.
11. Retired Vehicle cannot become a new active assignment unless restored according to the existing rule.
12. All eight Standardized Lists support value create/edit/retire/restore.
13. Inactive Standard Value remains historically resolvable.
14. Route Admin cannot create or grant platform-superuser authority.
15. Route Admin without required Core user-management capability is denied server-side.
16. Supervisor cannot access Admin CRUD surfaces.
17. No physical deletion removes historical references.
18. No new Route-specific User identity table is introduced.

---

# 15. Tests Required

Add tests according to repository conventions.

## User management

Prove:

- authorized Route Admin can create a tenant user through the approved Core contract;
- user is scoped to the current tenant;
- user can be updated;
- user can be deactivated/reactivated if supported by Core;
- unauthorized actor is denied server-side;
- cross-tenant access is rejected;
- Route Admin cannot obtain/assign platform-superuser status;
- required Core user-management capabilities are the existing ones, not duplicated Route capabilities.

## Supervisor designation

Prove:

- existing tenant user can become a Route Supervisor;
- duplicate profile is rejected;
- cross-tenant user cannot become a Supervisor;
- UI flow no longer requires manual API execution;
- Supervisor with no Vehicle remains valid.

## Vehicles

Retain and re-run:

- CRUD/lifecycle;
- concurrency;
- retire/restore;
- tenant isolation;
- in-use Vehicle retirement conflict.

## Assignments

Retain and re-run:

- create;
- current resolution;
- end;
- replace;
- history preservation;
- no overlapping current assignment;
- tenant-safe references.

## Standardized Lists

For all eight list codes prove:

- create value;
- update;
- reorder;
- retire/deactivate;
- restore/reactivate;
- list active;
- include inactive;
- historical resolution;
- tenant isolation.

Do not merely test one list and assume the remaining seven are wired correctly unless the test is explicitly parameterized across all eight.

## UI / wiring

Prove:

- Users is reachable from CER Route Admin Configuration;
- Supervisor designation is reachable without direct API use;
- Vehicles reachable;
- Assignments reachable;
- all eight Standardized Lists manageable;
- role/capability navigation visibility works;
- no broken page keys/routes;
- no RTE03+ fake functionality.

## Regression

Re-run:

- full backend suite;
- architecture/invariant tests;
- frontend typecheck;
- frontend lint;
- production build;
- Alembic head/check;
- migration roundtrip if migrations change.

Document exact commands and actual results.

---

# 16. Acceptance Criteria

RTE02 can be proposed for certification only when:

### Users

- [ ] Route Admin Configuration exposes User administration.
- [ ] Authorized Admin can Create User.
- [ ] Admin can list/search/read User.
- [ ] Admin can edit supported User attributes.
- [ ] Admin can deactivate/restore according to Core lifecycle.
- [ ] User operations reuse Core identity and capabilities.
- [ ] No parallel Route User model exists.
- [ ] Cross-tenant operations are impossible.
- [ ] Platform-superuser authority is not exposed.

### Supervisor setup

- [ ] Existing tenant User can be designated as Route Supervisor through UI.
- [ ] Duplicate Supervisor profile is prevented.
- [ ] Supervisor role/designation and Route profile are not confused with User identity.
- [ ] Supervisor can exist without a Vehicle.
- [ ] Vehicle Assignment can follow from Supervisor setup normally.

### Vehicles

- [ ] Create.
- [ ] Read.
- [ ] Update.
- [ ] Retire/deactivate.
- [ ] Restore/reactivate.
- [ ] Historical references preserved.

### Assignments

- [ ] Create.
- [ ] Read current/history.
- [ ] End.
- [ ] Replace/reassign.
- [ ] No destructive normal delete.
- [ ] One current assignment per Supervisor.

### Standardized Lists

- [ ] All eight lists visible.
- [ ] Values can be created.
- [ ] Values can be read.
- [ ] Values can be edited.
- [ ] Values can be reordered.
- [ ] Values can be deactivated.
- [ ] Values can be reactivated.
- [ ] Historical values remain resolvable.
- [ ] Outcome remains tenant data.
- [ ] No free-text field was turned back into a catalog.

### Security / quality

- [ ] Server-side authorization verified.
- [ ] Tenant isolation verified.
- [ ] Audit verified.
- [ ] Existing Route/Admin functionality has no regression.
- [ ] One Alembic head remains.
- [ ] Backend tests green.
- [ ] Frontend checks green.
- [ ] No RTE03+ functionality started.

---

# 17. Do Not Change

Do not reopen any certified RTE01 decision.

Do not alter the accepted RTE02 technical decisions unless this closure requires a justified correction.

In particular preserve:

- only real exercised Route capabilities are registered;
- remaining certified Route capabilities arrive with their real future surfaces;
- `GET /api/supervisors/me` remains self-service/minimum privilege;
- current Vehicle derives from current assignment;
- one current Vehicle Assignment per Supervisor;
- `supervisor_profile` remains thin;
- one `standard_value` table with eight closed list codes;
- Outcome remains tenant configurable;
- no physical deletion of historical configuration as normal operation;
- Mobile-only Supervisor;
- no Work Session / Trip / Activity implementation in RTE02.

---

# 18. Report Delivery Folder — Mandatory

Create and use the following folder at the repository root for CER delivery reports:

`Report Delivery Rodrigo/`

This follows the same delivery-governance pattern used in CER Time.

Move/store CER Route delivery reports there instead of leaving them scattered at repository root.

Do **not** keep duplicate report copies in multiple locations.

The previous RTE02 report should be preserved in the delivery folder as historical evidence where practical:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_DELIVERY_REPORT_001.md`

The new closure report must be:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_DELIVERY_REPORT_002.md`

If another correction is required:

- `CER_ROUTE_RTE02_DELIVERY_REPORT_003.md`
- `CER_ROUTE_RTE02_DELIVERY_REPORT_004.md`
- etc.

Never overwrite an earlier delivery report.

---

# 19. Environment Drift — Must Be Clean Before RTE03

The RTE02 report identified:

- database company subdomain: `cerroute`
- local `.env`: `certime`

This is not classified as an RTE02 implementation defect, but it must not be carried into RTE03.

Align the local development environment with CER Route using the existing configuration mechanisms.

Requirements:

- no hardcoded workaround;
- do not mutate production/business data merely to make bootstrap pass;
- document what was changed;
- bootstrap must run idempotently against the intended CER Route tenant;
- confirm the resulting environment is consistent before proposing RTE02 closed.

---

# 20. Required Delivery Report

Return one report only:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_DELIVERY_REPORT_002.md`

The report must include:

1. RTE02 status by C1–C5.
2. Gap-closure work performed.
3. User-management Core components reused.
4. Existing Core capabilities reused and any changes to `route_admin`.
5. User CRUD/lifecycle implemented.
6. Supervisor-designation UI implemented.
7. Vehicle CRUD/lifecycle status.
8. Vehicle Assignment administrative lifecycle status.
9. CRUD/lifecycle status for each of the eight Standardized Lists.
10. APIs changed/reused.
11. UI/pages/components changed/reused.
12. migrations, if any.
13. security/tenant isolation evidence.
14. audit evidence.
15. tests added/updated.
16. exact commands and results.
17. Expected vs Implemented matrix for this closure.
18. environment-drift resolution.
19. confirmation reports are stored under `Report Delivery Rodrigo/`.
20. confirmation no RTE03+ functionality was started.
21. proposed final status.

If all requirements are met, propose:

`RTE02 — Completed / Ready for CER Certification`

CER performs the final certification.

---

# 21. Closure Rule

Do not treat RTE02 as closed merely because the APIs exist.

For CER certification, every configuration capability currently introduced by RTE02 must be usable through the normal Admin product experience.

The closure standard is:

> **No normal RTE02 administration task requires Postman, direct API execution, direct database editing, or developer intervention.**

Once this condition, the security controls, tests and acceptance criteria above are satisfied, return Delivery 002 and stop.

**Do not start RTE03.**
