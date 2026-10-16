# CER Route — RTE02-A02 Access Alignment & Closure Instructions 007

## Context

RTE02 / RTE02-A01 are being reopened **only for a controlled access-model and environment alignment** after the diagnostic:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_A01_VALUES_AND_ROLES_DIAGNOSTIC_001.md`

The diagnostic confirmed three facts:

1. The current CER Route user-management surface exposes Core/Foundation roles and allows a `route_admin` actor to assign `owner` / `admin`, producing a real privilege escalation.
2. The approved 8 Standardized Lists / 28 initial values are correct in code, but the reviewed tenant has zero `standard_value` rows because provisioning was never applied there.
3. The reviewed tenant is also missing later Route capabilities; in particular, `supervisor` has no `route.worksession.execute`, so the environment is not aligned with RTE03/RTE04.

CER has now approved a simplified final V1 access model for CER Route.

This instruction supersedes the previous assumption that Route Admin is Admin-only and cannot execute the field workflow.

---

# Current State

## Confirmed

- CER Route must expose **two functional product roles only**:
  - **Administrador**
  - **Supervisor**
- Both roles must be able to use the CER Route operational/mobile experience.
- **Administrador** must additionally have the CER Route Admin experience.
- **Supervisor** is an operational user: **Read + Execute**, never Admin/Manage/Adjust.
- CEO / COO can be represented by the **Administrador** role.
- RM / OSM / Supervisor can be represented by the **Supervisor** role.
- Do **not** create CEO, COO, RM or OSM security roles in this checkpoint.
- Core/Foundation roles (`owner`, `admin`, `manager`, `viewer`) remain in Core and must not be deleted, renamed or repurposed.
- Core/Foundation roles must not appear as assignable roles inside the CER Route product experience.
- The Route user flow must not permit assigning a Core/Foundation role through direct API calls either.
- The Mobile UX remains the already-approved app-style CER Route experience; it is not an Admin web view compressed for mobile.

## Technical compatibility

Prefer preserving existing internal technical identifiers when that avoids destructive migrations:

- existing technical `route_admin` may remain the internal code for the product role displayed as **Administrador**;
- existing technical `supervisor` may remain the internal code displayed as **Supervisor**.

Do not create a second Administrator role merely to change the visible label.

---

# Objective

Close RTE02-A02 with an aligned, secure and testable CER Route access model:

1. exactly two CER Route functional roles in the product UX;
2. both roles can execute the operational route workflow;
3. only Administrador can use CER Route administration;
4. Supervisor remains Read + Execute only;
5. no CER Route actor can escalate into Core/Foundation roles through the CER Route user-management flow;
6. Standardized Values and missing Route capabilities are provisioned into the correct validation tenant using the existing provisioning mechanism;
7. RTE02-A01 behavior remains intact;
8. the resulting access model is ready for targeted RTE03/RTE04 regression after this checkpoint.

---

# Scope

## In Scope

- CER Route role presentation and assignability.
- CER Route role authorization.
- CER Route Users UX.
- Server-side protection of role assignment from the CER Route Administrator actor.
- Administrator access to both Admin and Mobile/My Route.
- Supervisor access to Mobile/My Route only.
- Explicit separation of Read / Execute / Manage.
- Standardized Values read authorization.
- Existing provisioning/bootstrap alignment for the reviewed CER Route tenant.
- Exact 8 lists / 28 initial values.
- Missing Route capability grants in the target tenant.
- Regression of RTE02/RTE02-A01 access/configuration behavior.
- Targeted access smoke tests into RTE03/RTE04 only to prove both product roles can enter the operational experience.

---

# Out of Scope

Do not:

- start RTE05;
- change Trip, Activity, odometer, Routing Mileage, GPS, fuel or reporting business rules;
- create CEO / COO / RM / OSM security roles;
- build organizational hierarchy or team scope;
- introduce multi-role memberships;
- redesign Core/Foundation role hierarchy;
- delete `owner`, `admin`, `manager` or `viewer`;
- convert Core roles into CER Route roles;
- change platform `is_superuser`;
- create a parallel user identity model;
- create a second Standardized Values provisioning mechanism;
- perform a destructive rename of existing role technical codes solely for UX naming;
- broaden this checkpoint into a general Core RBAC redesign.

A separate Core security concern exists because the shared Core user-management contract may also allow other Core roles to assign stronger Core roles. Do not silently redesign the entire Core hierarchy in this checkpoint. Close the CER Route attack surface defined here and clearly report any remaining Core-only exposure.

---

# Existing Components to Reuse

Reuse where appropriate:

- Core `Users` / `UserCompany` identity and tenant membership.
- Existing Core user-management service/API primitives.
- Existing `SecurityUsersPanel` components where reuse can be safely product-scoped.
- Existing role catalog and role-fetch infrastructure.
- Existing CER Route `route_admin` and `supervisor` role records/templates.
- Existing RBAC enforcement and `require_permissions`.
- Existing audit infrastructure.
- Existing Standard Values domain and `provision_standard_values()`.
- Existing `app/db/scripts/bootstrap.py`.
- Existing mobile `RouteMobileShell` / My Route experience.
- Existing tenant isolation by subdomain/company.

Do not duplicate these domains.

---

# Functional Requirements

## FR-01 — Exactly two CER Route roles in product UX

CER Route must present only:

- **Administrador**
- **Supervisor**

as functional/assignable Route roles.

The Route Users create/edit experience must not present:

- Owner
- Admin
- Manager
- Viewer

or any other Core/Foundation role as a CER Route assignment choice.

This is a product UX requirement, not a deletion of Core roles.

---

## FR-02 — Administrador experience

Administrador must have:

### Operational experience
- access to the same app-style My Route / Mobile experience as Supervisor;
- ability to execute the currently delivered Work Session / Trip / odometer workflow;
- ability to read the same operational values required to complete those flows.

### Administrative experience
- CER Route Admin navigation;
- Route user management within the allowed Route role boundary;
- Supervisors setup;
- Vehicles / assignments;
- Standardized Values management;
- odometer exception administration / `route.records.adjust`;
- other already-delivered Route administration consistent with current checkpoints.

Administrator does not become a platform superuser.

---

## FR-03 — Supervisor experience

Supervisor must have:

### Read
Only the operational information needed to perform their own Route workflow.

### Execute
The currently delivered operational workflow, including RTE03/RTE04 commands applicable to the authenticated user.

### Must not have
- user administration;
- role administration;
- vehicle configuration administration;
- Standardized Values create/edit/deactivate/delete/reorder;
- exception approval/rejection;
- historical adjustments;
- Core/Foundation security administration.

Supervisor = **Read + Execute**, not Edit/Manage/Adjust.

---

## FR-04 — Both roles use the same Mobile operational experience

Do not create separate mobile applications for Administrador and Supervisor.

Both roles use the existing CER Route mobile-first, app-style experience.

Role differences affect authorization and available Admin navigation, not the fundamental operational Mobile UX.

---

## FR-05 — Server-side Route role assignment policy

The CER Route Administrator must be able to assign:

- Administrador
- Supervisor

and must be rejected server-side if attempting to assign:

- owner
- admin
- manager
- viewer
- any other Core/Foundation role
- any role from another tenant

This must hold for both:

- create user;
- update/change user role.

The protection must not depend on hiding items in the frontend.

Direct API submission of a Core role id/code from an Administrador must fail.

Use the narrowest server-side policy that preserves the shared Core identity model.

Do not implement the previously proposed generic rule:

> caller may only grant capabilities the caller already holds

because it conflicts with the approved model: Administrador must be able to create a Supervisor even though the two roles intentionally have different capability sets.

---

## FR-06 — Preserve Core/Foundation roles

`owner`, `admin`, `manager`, `viewer` remain valid Core/Foundation roles.

They are not CER Route product personas.

Do not delete, rename, repurpose, or migrate them merely to simplify CER Route.

If Core/Foundation management surfaces exist, their behavior is outside this product UX alignment unless a change is strictly required to prevent the CER Route escalation.

---

# Business Rules

## BR-01 — Role vs organizational title

Security role and organizational title are separate concepts.

For V1:

- CEO / COO may use Administrador.
- RM / OSM / Supervisor may use Supervisor.

Do not create title-specific authorization rules in this checkpoint.

---

## BR-02 — Administrator and Supervisor both execute Route

The previous RTE03 assumption that Route Admin must not hold `route.worksession.execute` is superseded by this approved product decision.

Update role grants/tests accordingly.

Do **not** alter Work Session lifecycle semantics.

---

## BR-03 — Read / Execute / Manage remain separate

Do not use `route.worksession.execute` as a generic authorization shortcut for unrelated catalog administration.

For Standardized Values:

- both Administrador and Supervisor need read access to the operational values required by Route workflows;
- only Administrador may manage those values.

Implement an explicit read-only authorization contract.

Preferred target if consistent with the existing catalog:

`route.standardvalues.read`

with:

- Administrador → read + manage
- Supervisor → read only

If the repository has a materially better established read contract, it may be reused, but the final behavior must preserve the same Read / Execute / Manage separation and be documented.

---

## BR-04 — No privilege escalation through Route Users

An Administrador may create/manage CER Route users but may not use that authority to become, create, or grant a Core/Foundation security authority.

The server is authoritative.

---

# Standardized Values Provisioning

Use the approved A01 source and existing provisioning implementation.

The target is exactly 8 lists / 28 initial values:

## Client Visit Activities
1. Staffing Follow-up
2. Service Review
3. Attendance Follow-up
4. Safety Follow-up

## Recruiting Activities
1. Candidate Sourcing
2. Hiring Event
3. Referral Follow-up

## Employee Visit Reasons
1. Attendance Issue
2. Document Follow-up
3. Transportation Issue
4. Employee Support

## Delivery Types
1. Payroll Check
2. Document Delivery
3. Equipment Delivery

## Office Purposes
1. Paperwork
2. Meeting
3. Pickup / Drop-off
4. Administrative Follow-up

## Other Activities
1. Housing Visit
2. Transportation Support
3. Supply Pickup

## Outcomes
1. Completed
2. Follow-up Required
3. Escalated
4. No Contact

## Received By
1. Employee
2. Authorized Person
3. Office Staff

Do not change labels, order, spelling or counts.

---

# Provisioning / Environment Alignment

## Gate before writing target-environment data

Before running bootstrap/provisioning, confirm that the environment and tenant being modified are the same environment/tenant being used for CER visual validation.

Record:

- environment/mode;
- database;
- tenant id;
- tenant name;
- subdomain.

If this cannot be established, **STOP**.

## Once confirmed

Use only the existing approved bootstrap/provisioning mechanism.

Do not manually insert rows and do not create a second seed script.

The aligned tenant must receive:

- the 28 initial Standardized Values if they have never been provisioned;
- missing registered Route capabilities;
- correct grants for Administrador and Supervisor.

Provisioning must remain idempotent.

A second run must not:

- duplicate values;
- reset renamed seed values;
- reactivate deactivated seed values;
- resurrect deleted seed values;
- overwrite tenant-authored values.

---

# Roles & Permissions — Target Matrix

The exact technical implementation may reuse current capability codes, but the resulting authority must satisfy this matrix.

| Area | Administrador | Supervisor |
|---|---:|---:|
| Mobile / My Route | Yes | Yes |
| Read own operational state | Yes | Yes |
| Execute Work Session | Yes | Yes |
| Execute Trip flow | Yes | Yes |
| Execute odometer flow | Yes | Yes |
| Read operational Standardized Values | Yes | Yes |
| Manage Standardized Values | Yes | No |
| Manage Route users | Yes | No |
| Assign Administrador | Yes | No |
| Assign Supervisor | Yes | No |
| Assign Core roles | **No** | No |
| Manage vehicles / assignments | Yes | No |
| Review odometer exceptions | Yes | No |
| Historical/admin adjustments | Yes when capability exists | No |
| Core role administration | No through CER Route | No |
| Platform superuser | No | No |

---

# Web / Mobile Requirements

## CER Route Admin

- Role selector shows exactly:
  - Administrador
  - Supervisor
- No Owner/Admin/Manager/Viewer choices.
- Route user-management experience should represent Route users, not expose Core/Foundation role taxonomy as product choices.
- If the shared `SecurityUsersPanel` requires adaptation, prefer configuration/composition over duplicating the user-management domain.

## Mobile / My Route

- Preserve the already-approved app-style mobile UX.
- Administrador and Supervisor both can enter it.
- No desktop Admin chrome inside the operational mobile experience.
- Do not fork the operational flow by role unless authorization genuinely requires a difference.
- Supervisor must never receive Admin controls simply because both roles share the Mobile experience.

---

# Security / Audit

Required:

- server-side role-assignment enforcement;
- tenant-scoped checks;
- no client-provided tenant authority;
- no `is_superuser` exposure;
- audit create/update/deactivate/delete user actions as currently approved;
- audit role changes with actor, target, old role, new role, timestamp and tenant;
- direct API attempts by Administrador to grant Core roles must be rejected and tested;
- cross-tenant role assignment remains non-disclosing;
- Supervisor cannot administer users or approve exceptions.

Do not treat frontend filtering as authorization.

---

# Edge Cases

Validate at minimum:

1. Administrador creates Supervisor.
2. Administrador creates another Administrador.
3. Administrador changes Supervisor → Administrador.
4. Administrador changes Administrador → Supervisor.
5. Administrador attempts to create Owner → rejected server-side.
6. Administrador attempts to create Admin → rejected.
7. Administrador attempts to create Manager → rejected.
8. Administrador attempts to create Viewer → rejected.
9. Administrador attempts equivalent role escalation by update → rejected.
10. Direct API submission bypassing frontend selector → rejected.
11. Role from another tenant → rejected without existence leakage.
12. Supervisor attempts to create/edit users → rejected.
13. Administrator enters Mobile/My Route and can Start Work.
14. Supervisor enters Mobile/My Route and can Start Work.
15. Supervisor can read required Standardized Values but cannot manage them.
16. Administrador can read and manage Standardized Values.
17. Provisioned values appear as exact 28 approved values.
18. Bootstrap second run creates no duplicate/change.
19. Existing deleted/deactivated seeded values are not resurrected.
20. Core roles remain in Core/Foundation but are absent as Route assignment choices.

---

# Acceptance Criteria

RTE02-A02 is a completion candidate only when all are true:

### Access model
- CER Route visibly exposes only **Administrador** and **Supervisor** as product roles.
- Administrator can access Admin + Mobile.
- Supervisor can access Mobile and cannot access Route administration.
- Both can execute the currently delivered operational Route flow.

### Security
- Administrador cannot grant any Core/Foundation role through CER Route.
- Direct API escalation tests fail with an authorization response.
- Supervisor cannot administer users/roles/configuration.
- No platform-superuser path exists.
- Tenant isolation remains intact.

### Read / Execute / Manage
- Operational catalog read is separate from manage.
- Supervisor can read required values.
- Supervisor cannot create/edit/delete/reorder/deactivate/reactivate them.
- Execute is not used as a generic substitute for Admin/Manage authorization.

### Provisioning
- Correct tenant/environment confirmed before changes.
- Exact 8 lists / 28 values exist after approved provisioning when previously absent.
- Role/capability grants match the current catalog.
- Supervisor is no longer left with zero operational capabilities.
- Bootstrap/provisioning remains idempotent and respects lifecycle semantics.

### Regression
- RTE02 / RTE02-A01 focused suites green.
- User lifecycle remains intact.
- Vehicles / assignments / Standardized Values behavior remains intact.
- Targeted RTE03/RTE04 access smoke proves:
  - Administrador can enter operational Mobile and execute Start Work;
  - Supervisor can enter operational Mobile and execute Start Work;
  - required operational Standardized Values can be read by both.
- Do not certify RTE04 from this checkpoint; this regression only proves access compatibility.

---

# Tests Required

At minimum:

## Authorization
- discriminating tests for every role assignment path;
- create and update;
- direct API bypass;
- another tenant;
- Supervisor denied;
- Administrator allowed only for the two Route roles.

## Role UX
- browser test role selector contains exactly Administrador and Supervisor;
- Core roles absent from CER Route assignment UX.

## Mobile access
- browser/API smoke for Administrator Mobile;
- browser/API smoke for Supervisor Mobile;
- Admin navigation visible only to Administrator.

## Standardized Values
- exact approved catalog test independent from implementation constant;
- API read for Supervisor;
- manage rejected for Supervisor;
- read/manage accepted for Administrator;
- browser renders all eight lists after provisioning;
- tenant isolation.

## Provisioning
- first run adds what is missing;
- second run no-op/idempotent;
- deleted/deactivated values not resurrected;
- database role grants match code catalog.

## Regression
Run the focused RTE02/A01 suites plus the minimum RTE03/RTE04 access tests affected by the new role grants.

If changes touch shared Core user-management behavior, run the relevant Core authorization/user-management regression suite as well.

---

# Do Not Change

Do not change:

- RTE03 Work Session lifecycle or time semantics;
- RTE04 Trip state machine;
- odometer business rules;
- END Option B;
- Routing Mileage definition;
- Activity/RTE05 behavior;
- free-text decisions;
- Standardized Values labels/order;
- tenant isolation model;
- Core role meanings;
- platform superuser model;
- existing audit primitive.

Do not begin RTE05.

---

# Deliverables

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_A02_DELIVERY_REPORT_001.md`

The report must include:

1. as-built role model;
2. visible labels vs technical identifiers;
3. exact permission matrix;
4. server-side role-assignment policy;
5. evidence that Core roles cannot be assigned through CER Route;
6. evidence that Administrator can use Admin + Mobile;
7. evidence that Supervisor can use Mobile only;
8. Read / Execute / Manage separation;
9. exact environment/tenant provisioned;
10. Standardized Values pre/post evidence;
11. capability/grant pre/post evidence;
12. provisioning idempotency evidence;
13. browser evidence;
14. test results;
15. Expected → Implemented → Evidence → Gap;
16. any remaining Core-only security exposure explicitly separated from CER Route;
17. confirmation that RTE03/RTE04 business behavior was not changed;
18. confirmation RTE05 was not started.

Use a unique incremental filename for any additional report. Do not overwrite previous reports.

---

# Checkpoints

## A02-C1 — Access Model Alignment
- two product roles;
- visible labels;
- Administrator/Supervisor target grants;
- Administrator gains operational execution;
- Supervisor remains Read + Execute only.

## A02-C2 — Route User Assignment Security
- Route role assignment whitelist/policy server-side;
- UI selector aligned;
- direct API escalation closed;
- Core roles preserved but outside Route assignment experience.

## A02-C3 — Read / Execute / Manage Separation
- operational Standardized Values read contract;
- Supervisor read only;
- Administrator read + manage;
- no execute-as-generic-read shortcut.

## A02-C4 — Provisioning Recovery
- confirm exact validation tenant/environment;
- run existing approved bootstrap/provisioning;
- 28 values present;
- missing capabilities/grants aligned;
- second run idempotent.

## A02-C5 — Validation & Closure Candidate
- focused backend regression;
- browser role-selector validation;
- Administrator Mobile smoke;
- Supervisor Mobile smoke;
- Standardized Values browser validation;
- security regression;
- final delivery report.

---

# STOP Conditions

STOP and return to CER before broadening the implementation if:

- the only proposed solution requires deleting or renaming Core/Foundation roles;
- fixing CER Route requires redesigning the entire shared Core role hierarchy;
- multi-role membership becomes necessary;
- the target tenant/environment cannot be proven before provisioning;
- existing tenant data would need destructive reinterpretation;
- the implementation would give Supervisor any Admin/Manage/Adjust authority;
- the implementation would remove Administrator access to the operational Mobile experience;
- a new product decision outside this document is required.

After completing A02-C5 and producing the delivery report:

# STOP

Do not continue with RTE04 closure or RTE05 until CER reviews and certifies RTE02-A02.
