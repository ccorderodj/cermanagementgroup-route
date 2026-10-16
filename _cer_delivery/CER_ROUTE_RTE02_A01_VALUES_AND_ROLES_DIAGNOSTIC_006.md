# CER Route — RTE02-A01 Diagnostic: Standard Values + Roles 006
## Diagnose current tenant/UX state before changing product behavior

**Purpose:** Determine why the approved default Standardized Values are not visible in the UX being reviewed, and audit the current role model shown in the CER Route user form.

**Important:** Do not start by changing code. First establish the actual cause with evidence from the same environment and tenant that the Product Owner is reviewing.

---

## Context

CER approved exactly eight Standardized Lists and 28 initial values in RTE02-A01.

The approved Route-specific operational roles are:

- `route_admin`
- `supervisor`

The underlying CER Application Foundation already contained Core tenant roles such as:

- `owner`
- `admin`
- `manager`
- `viewer`

RTE02 reused the existing Core User/Role management UI rather than creating a separate CER Route user-management domain.

The current UX being reviewed shows six roles in the role selector:

- Admin
- Manager
- Owner
- Route_admin
- Supervisor
- Viewer

This diagnostic must establish why all six are exposed, whether they are assignable by `route_admin`, and whether that behavior is aligned and secure for CER Route.

---

# 1. Objective

Produce an evidence-first diagnosis answering two questions:

1. Why are the 28 approved initial Standardized Values not visible in the exact CER Route tenant/environment currently being reviewed?
2. Why does the CER Route User form expose six roles when CER Route defined only two Route-specific operational roles?

Correct only issues that are clearly implementation/configuration defects within already-approved RTE02-A01 behavior.

If resolution requires changing the approved role model or lifecycle semantics, STOP and report the decision required.

---

# 2. Standardized Values — Required Investigation

## 2.1 Confirm exact environment and tenant

Identify the exact environment and tenant being rendered in the browser.

Record:

- application/environment;
- company/tenant id;
- company name;
- subdomain used by the request;
- configured `BOOTSTRAP_COMPANY_SUBDOMAIN`;
- database actually connected to the running application.

Do not assume the browser is using the same tenant/database that was used by automated tests.

---

## 2.2 Verify approved source

Use:

`_cer_delivery/CER_ROUTE_RTE02_ADDENDUM_A01_DEVELOPMENT_INSTRUCTIONS_004.md`

as the approved source.

Confirm the code still defines exactly these 28 values, in this order:

### Client Visit Activities
- Staffing Follow-up
- Service Review
- Attendance Follow-up
- Safety Follow-up

### Recruiting Activities
- Candidate Sourcing
- Hiring Event
- Referral Follow-up

### Employee Visit Reasons
- Attendance Issue
- Document Follow-up
- Transportation Issue
- Employee Support

### Delivery Types
- Payroll Check
- Document Delivery
- Equipment Delivery

### Office Purposes
- Paperwork
- Meeting
- Pickup / Drop-off
- Administrative Follow-up

### Other Activities
- Housing Visit
- Transportation Support
- Supply Pickup

### Outcomes
- Completed
- Follow-up Required
- Escalated
- No Contact

### Received By
- Employee
- Authorized Person
- Office Staff

Do not substitute labels or infer values from the old mockup.

---

## 2.3 Inspect actual tenant data

For the exact tenant being reviewed, report for every Standardized List:

- list code;
- total rows;
- active rows;
- inactive rows;
- deleted/tombstoned rows;
- label;
- sort order;
- `seed_key`;
- `is_active`;
- `deleted_at`.

Produce a matrix:

`Approved Value → DB State → API State → UI State`

Do not modify the data before capturing this evidence.

---

## 2.4 Verify provisioning history/state

Determine whether `provision_standard_values()` was applied to the exact tenant.

Check:

- whether the expected `seed_key` rows exist;
- whether the tenant existed before A01 provisioning;
- whether bootstrap was run against the correct CER Route subdomain;
- whether the current environment was created/restored after the bootstrap;
- whether a different database/environment was seeded;
- whether any of the values were later renamed, deactivated or deleted.

Remember the approved idempotency behavior:

- renamed seeded value is not reset;
- deleted seeded value is not resurrected;
- deactivated seeded value is not automatically reactivated.

If this explains the UX, classify the exact cause rather than calling it a frontend defect.

---

## 2.5 Inspect API response used by the UX

Using the authenticated session for the same tenant, inspect:

- `GET /api/standard-values/lists`
- each `GET /api/standard-values/{list_code}`
- the Admin pagination/list call if different;
- `include_inactive` behavior where applicable.

For each list, show:

`Database → API response → rendered rows`

Determine whether the values disappear:

- before the API;
- in API filtering;
- in frontend state;
- in rendering.

---

## 2.6 Browser validation

Open the actual CER Route Admin UI and validate all eight lists.

Capture whether:

- each list is visible;
- approved rows are visible;
- active/inactive filters alter results correctly;
- the row count matches API data;
- refresh/reload changes the result;
- tenant switching changes the result.

Do not consider the issue diagnosed solely from unit/integration tests.

---

# 3. Standardized Values — Allowed Corrections

After diagnosis:

### If the cause is missing provisioning in the current tenant/environment
Use the already-approved provisioning mechanism for that tenant and verify the resulting UX.

Do not create a second seeding mechanism.

### If the values exist in DB/API but the UI does not render them
Correct only the wiring/filter/state defect and add browser evidence.

### If the values were intentionally deactivated/deleted
Do not silently resurrect them.

Report the exact state to CER because the approved lifecycle intentionally preserves tenant decisions.

### If bootstrap points to the wrong tenant
Correct environment configuration using the existing mechanism; do not hardcode a tenant id/subdomain.

---

# 4. Roles — Required Investigation

## 4.1 Inventory every role in the current CER Route tenant

For each visible role, report:

- id;
- code/name;
- origin: Core/Foundation vs CER Route;
- system/default/custom flag if available;
- active/inactive state;
- capabilities actually granted;
- number of current users assigned.

At minimum investigate:

- `owner`
- `admin`
- `manager`
- `viewer`
- `route_admin`
- `supervisor`

Do not infer role behavior from labels.

---

## 4.2 Confirm product origin

Establish from repository history and RTE02 implementation evidence:

- which roles existed before CER Route;
- which roles RTE02 created;
- which Core roles received Route capabilities during bootstrap;
- which roles are currently intended for actual CER Route field/admin operation.

The final report must distinguish:

**Core/Foundation role** vs **CER Route operational role**.

---

## 4.3 Explain the current dropdown

Trace the exact source of the role selector shown in the CER Route Users form.

Verify whether:

- `SecurityUsersPanel` is reused directly;
- `entities/Roles/fetchRoles` retrieves every company role;
- the frontend applies no CER Route-specific filtering;
- the backend returns every tenant role.

State exactly why the UI currently shows six options.

---

# 5. Security Audit — Critical

The current UX exposes `Owner`, `Admin`, `Manager`, and `Viewer` to a CER Route user-management form.

Do not assume this is harmless.

Test server-side whether a user holding only the current `route_admin` permissions can:

1. create a new user assigned to `owner`;
2. create a new user assigned to `admin`;
3. change an existing `supervisor` to `owner`;
4. change an existing `supervisor` to `admin`;
5. assign `manager`;
6. assign `viewer`;
7. assign `route_admin`;
8. assign `supervisor`.

This must be tested against the API directly, not inferred from the UI.

The existing protections against:

- setting `is_superuser`;
- creating/editing roles;
- assigning a role from another tenant;

do **not by themselves prove** that a Route Admin cannot assign an already-existing more-powerful Core role.

If `route_admin` can assign `owner` or `admin`, classify:

`SECURITY GAP / PRIVILEGE ESCALATION`

and STOP before broadening the fix beyond the approved boundary.

---

# 6. CER Route Role Model — Current Product Interpretation

For this diagnostic, use the following product distinction:

## CER Route operational roles

### `route_admin`
Purpose:
- administer CER Route configuration within the tenant;
- manage Route users using permitted Core user-management operations;
- manage supervisors, vehicles, assignments and Standardized Values;
- later administer approved Route records/exceptions according to capabilities.

It is **not** a platform superuser.

### `supervisor`
Purpose:
- Mobile-only field user;
- execute Work Session / Trip / Activity behavior as delivered by the corresponding checkpoints;
- access only their own operational context as applicable;
- no Route administration.

These are the **two roles created specifically for CER Route**.

## Core/Foundation roles

`owner`, `admin`, `manager`, `viewer` predate CER Route and are not additional CER Route personas.

Do not delete, rename or repurpose these Core roles during this diagnostic.

---

# 7. UX Alignment to Evaluate

The Product Owner expects CER Route operational user assignment to be understandable as:

- Route Admin
- Supervisor

Therefore determine whether the CER Route Users form should expose only the CER Route assignable roles for ordinary Route user creation/editing.

Do not implement filtering until the security/current-state audit above is complete.

If no architectural dependency prevents it, the preferred UX target is:

- ordinary CER Route user creation offers `Route Admin` and `Supervisor`;
- Core roles remain in Core/Foundation and are not deleted;
- an existing user already holding a Core role remains representable without silently changing that role;
- a Route Admin cannot use the CER Route user form/API to escalate someone to a Core role beyond their authority.

If achieving this requires changing the shared Core user-management contract for other products, STOP and propose the narrowest safe option rather than globally filtering roles.

---

# 8. Required Tests

Add or identify tests proving:

### Standardized Values
- exact 8 lists / 28 approved values;
- current tenant receives expected provisioning when appropriate;
- API returns active values;
- Admin UI renders them;
- wrong tenant cannot see them;
- deleted/deactivated semantics remain unchanged.

### Roles
- exactly two Route-specific role templates exist: `route_admin`, `supervisor`;
- Core roles remain intact;
- role dropdown behavior is intentional and tested;
- `route_admin` cannot assign a role that exceeds its permitted authority;
- Supervisor cannot administer users;
- cross-tenant role assignment remains rejected;
- no `is_superuser` path is introduced.

---

# 9. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_A01_VALUES_AND_ROLES_DIAGNOSTIC_001.md`

The report must contain:

1. exact environment/tenant inspected;
2. root cause of missing Standardized Values;
3. 28-value DB/API/UI matrix;
4. whether provisioning was applied to the tenant;
5. corrections made, if any;
6. complete current role inventory;
7. origin and purpose of every visible role;
8. why the dropdown shows six roles;
9. direct API privilege-escalation test results;
10. Expected vs Implemented vs Evidence vs Gap;
11. classification of each finding:
   - AS-BUILT / ALIGNED
   - CONFIGURATION/ENVIRONMENT
   - UX GAP
   - FUNCTIONAL GAP
   - SECURITY GAP
   - DECISION REQUIRED
12. recommendation for CER Route role-selector UX;
13. tests/evidence;
14. confirmation that RTE04/RTE05 behavior was not changed by this diagnostic.

---

# 10. Do Not Change

Do not:

- delete Core/Foundation roles;
- rename roles globally;
- change role capabilities merely to make the dropdown look simpler;
- resurrect deleted Standardized Values without evidence/authorization;
- create another Standardized Values seeding path;
- hardcode tenant IDs;
- create duplicate Route user management;
- change RTE03/RTE04/RTE05 business flows;
- weaken server-side authorization.

---

# 11. STOP Conditions

STOP and return to CER if any of the following is found:

- `route_admin` can assign `owner` or `admin`;
- fixing the selector requires changing shared Core behavior for other applications;
- approved values were deliberately deleted/deactivated and restoring them would override tenant action;
- the current tenant is not the tenant the Product Owner believes is being reviewed;
- role behavior differs materially from the documented Route/Core split;
- resolution requires a new product decision.

After producing the diagnostic report, **STOP** for CER review.
