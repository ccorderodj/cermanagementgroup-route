# CER Route — RTE02-A02 Final Closure Instructions 008

## Context

RTE02-A02 is functionally close to completion, but CER has identified four final items that must be resolved before certification:

1. **CER Route role assignment must be constrained by product context, not only by the authenticated actor.**
   - Today, a Core/Superadmin user can still receive the full tenant role catalog when entering the CER Route user-management surface.
   - This violates the approved CER Route product model.
2. **A residual `roles.read` grant remains on the aligned tenant for `route_admin`.**
   - The final template no longer requires it.
3. **Vehicles UX needs to be standardized to a list-first pattern.**
4. **Standardized Lists UX needs the same list-first/modal pattern and visual cleanup.**

RTE03 and RTE04 business behavior must remain unchanged.

RTE05 must not start.

---

# Current State

## Confirmed as already completed

- CER Route has two functional product roles:
  - **Administrador**
  - **Supervisor**
- Existing technical identifiers may remain:
  - `route_admin`
  - `supervisor`
- Both roles can use the operational Mobile / My Route experience.
- Only Administrador can use CER Route Admin.
- Supervisor is **Read + Execute** only.
- `route.standardvalues.read` exists as an explicit read permission.
- The direct CER Route escalation into Core roles from `route_admin` is already blocked server-side.
- The 8 Standardized Lists / 28 approved values are provisioned in the reviewed tenant.
- Supervisor has the expected operational capabilities.
- Existing provisioning is idempotent and respects renamed/deactivated/deleted seeded values.
- RTE03 / RTE04 business behavior remains unchanged.

---

# Objective

Complete RTE02-A02 so CER can certify it.

The final state must satisfy:

1. `CER Route > Users` always exposes and accepts only:
   - Administrador
   - Supervisor
2. This must remain true even when the authenticated actor is:
   - Superadmin
   - Core Owner
   - Core Admin
   - CER Route Administrador
3. Core/Foundation roles remain available to Core/Foundation management surfaces, but never through the CER Route user-management contract.
4. Remove the obsolete `roles.read` grant from the CER Route Administrador in the aligned tenant.
5. Standardize Vehicles and Standardized Lists UX using the approved list-first + modal interaction pattern.
6. Preserve all existing lifecycle, security, data, API and business rules.
7. Deliver a final evidence-first closure report and STOP.

---

# Scope

## In Scope

- CER Route role-selection UX.
- CER Route assignable-role contract.
- Server-side Route-context enforcement for assignable roles.
- Removal of residual `roles.read` from the aligned Route Administrator role.
- Vehicles UX restructuring.
- Standardized Lists UX restructuring.
- Targeted browser/API regression.
- Final RTE02-A02 delivery report.

## Out of Scope

Do not:

- redesign Core/Foundation RBAC;
- fix the separate Core `manager -> owner` exposure in this checkpoint;
- create CEO / COO / RM / OSM roles;
- introduce multi-role membership;
- change RTE03 Work Session rules;
- change RTE04 Trip/Odometer rules;
- change Standardized Value business lifecycle;
- change vehicle business lifecycle;
- start RTE05;
- change the 28 approved values;
- change tenant-isolation behavior;
- change platform superuser behavior.

The Core `manager -> owner` exposure must remain documented as a separate Core Security Gap.

---

# Confirmed Product Decisions

## PD-01 — CER Route roles

The only CER Route product roles are:

- **Administrador**
- **Supervisor**

Technical codes may remain:

- `route_admin`
- `supervisor`

Do not expose technical codes in normal product UX.

---

## PD-02 — Product context governs Route role assignment

The user-management boundary is determined by the **CER Route product context**, not by the authority level of the authenticated user.

Therefore:

### From CER Route > Users

Allowed assignable roles are always exactly:

- Administrador
- Supervisor

This applies even if the caller is:

- Superadmin
- Owner
- Admin
- Administrador Route

### From Core/Foundation user management

Core/Foundation role behavior remains outside this checkpoint.

Do not reuse the CER Route product-role limitation to change the behavior of Core user-management surfaces.

---

## PD-03 — Both CER Route roles can execute My Route

- Administrador = Read + Execute + Manage/Admin
- Supervisor = Read + Execute only

Do not alter this approved model.

---

# Functional Requirements

## FR-01 — CER Route Users must expose exactly two roles

Inside `CER Route > Users`:

Role selector must display exactly:

- Administrador
- Supervisor

It must not display:

- Owner
- Admin
- Manager
- Viewer
- any other Core/Foundation role
- technical role codes

This must be true for every authorized actor using the CER Route user-management surface, including Superadmin.

---

## FR-02 — Server-side Route-context assignment enforcement

The CER Route user-management contract must reject any attempt to assign a non-Route product role.

Allowed target roles:

- `route_admin`
- `supervisor`

Rejected target roles:

- `owner`
- `admin`
- `manager`
- `viewer`
- any other non-Route role
- any role from another tenant

This must apply to:

- create user;
- update/change role;
- direct API calls bypassing the frontend.

The implementation must preserve Core/Foundation user-management behavior outside CER Route.

Do not solve this with frontend filtering alone.

---

## FR-03 — Superadmin browser scenario

Add explicit browser validation for the scenario that exposed the current gap:

1. Sign in as Superadmin / Application Administrator.
2. Open `CER Route > Users`.
3. Open Add User / Edit User.
4. Assert the role selector contains exactly:
   - Administrador
   - Supervisor
5. Assert no Core role label appears.
6. Assert no technical code appears.
7. Attempt direct API assignment of `owner` from the CER Route contract.
8. Expect rejection and no write.

This is a mandatory acceptance test.

---

# Residual Capability Cleanup

## FR-04 — Remove `roles.read` from Route Administrador

The aligned tenant currently has one obsolete grant:

`route_admin -> roles.read`

The final role template does not require it.

CER approves a **targeted, controlled cleanup** of this obsolete grant for the aligned tenant.

Requirements:

- remove only the obsolete `roles.read` grant from `route_admin`;
- do not change global bootstrap semantics;
- do not create a generic revocation engine;
- do not add `roles.read` back to the Route template;
- do not remove the permission row from the system if Core still uses it;
- preserve audit/evidence of the cleanup.

Final expected counts in the aligned tenant:

- Administrador: **12 capabilities**
- Supervisor: **2 capabilities**

If the repository already has a safe controlled mechanism for this reconciliation, reuse it.

Do not perform an undocumented manual database edit.

---

# UX Standardization

## FR-05 — Vehicles: list-first UX

Current permanent `Add a vehicle` form must be removed from the main page.

### New pattern

Page opens with:

- title / description;
- primary action button:
  - `Add Vehicle`
- inactive filter;
- existing vehicle list/table.

### Add Vehicle

Pressing `Add Vehicle` opens a modal/dialog using the existing vehicle fields:

- Unit
- Make
- Model
- Year
- Fuel grade
- Operational MPG

On successful save:

- close modal;
- refresh list;
- show created vehicle;
- preserve normal validation/error handling.

### Existing lifecycle

Keep current row contextual menu and existing behavior for:

- Edit
- Deactivate
- Reactivate
- Delete
- blocked delete rules
- assignments/history rules

Do not change vehicle business rules.

---

## FR-06 — Standardized Lists: container + contextual create modal

The current permanent `Add a value` input must be removed.

### Group navigation

The 8 list groups must appear in a defined visual container/panel.

Keep:

- selected-state indication;
- approved group labels;
- active counts.

The 8 groups remain exactly:

1. Client Visit Activities
2. Recruiting Activities
3. Employee Visit Reasons
4. Delivery Types
5. Office Purposes
6. Other Activities
7. Outcomes
8. Received By

### Contextual creation

The currently selected group must expose a clear primary action:

`Add Value`

This opens a modal/dialog.

The modal must already know which list is selected.

Do not ask the user to reselect the list.

Minimum modal behavior:

- selected list context visible;
- Label input;
- Cancel;
- Add/Save;
- existing validation preserved.

On successful save:

- close modal;
- refresh current list;
- update count;
- preserve current selection.

---

## FR-07 — Standardized Lists table cleanup

Remove the visible `Actions` column header if the column only contains contextual row menus.

Keep the row `...` contextual menu aligned to the far right.

Reorder controls must be visually associated with ordering, not mixed ambiguously with the row action menu.

Preferred layout:

- Order
- Label
- Status
- contextual menu at far right without unnecessary `Actions` heading

If up/down controls remain, place them visually with Order or in a clearly understandable ordering affordance.

Do not change reorder behavior itself.

---

# Standardized Values — Do Not Change

The 28 approved values remain unchanged.

Do not modify:

- labels;
- order;
- spelling;
- counts;
- seed keys;
- active/inactive semantics;
- delete/tombstone semantics;
- idempotency behavior.

---

# Roles & Permissions — Final Target

| Capability / Experience | Administrador | Supervisor |
|---|---:|---:|
| Mobile / My Route | Yes | Yes |
| Work Session execute | Yes | Yes |
| Trip execute | Yes | Yes |
| Odometer execute | Yes | Yes |
| Read operational Standardized Values | Yes | Yes |
| Manage Standardized Values | Yes | No |
| Manage Route users | Yes | No |
| Assign Administrador | Yes | No |
| Assign Supervisor | Yes | No |
| Assign Core/Foundation roles from CER Route | No | No |
| Manage Vehicles / Assignments | Yes | No |
| Odometer exception administration | Yes | No |
| Historical adjustments | Yes where already approved | No |
| `roles.read` | No | No |
| Platform superuser | No | No |

---

# Security / Audit

Validate and preserve:

- tenant isolation;
- server-side role assignment enforcement;
- no client-trusted tenant scope;
- no platform privilege escalation;
- no frontend-only authorization;
- user/role changes audited;
- targeted `roles.read` cleanup evidenced;
- Supervisor denied from Admin/Manage endpoints;
- cross-tenant role assignment remains non-disclosing.

---

# Acceptance Criteria

RTE02-A02 may be marked Completed / Ready for CER Certification only if all are true.

## Roles

- `CER Route > Users` shows exactly Administrador and Supervisor.
- This is true when authenticated as:
  - Superadmin;
  - Core Owner/Admin where applicable;
  - Route Administrador.
- Core roles do not appear in the CER Route selector.
- Direct API attempts to assign Core roles through the CER Route contract fail.
- Core/Foundation role-management behavior outside CER Route remains unchanged.

## Capabilities

- Route Administrador has exactly 12 expected capabilities.
- Supervisor has exactly 2 expected capabilities.
- `roles.read` is absent from Route Administrador.
- Supervisor remains Read + Execute only.

## Vehicles UX

- no permanent Add Vehicle form on the main page;
- list appears first;
- Add Vehicle action opens modal;
- create works;
- lifecycle actions still work;
- inactive filter remains functional.

## Standardized Lists UX

- 8 groups appear inside a defined container;
- counts remain correct;
- no permanent Add Value form;
- Add Value opens contextual modal;
- modal creates under the selected group;
- current group remains selected after save;
- table no longer has an unnecessary `Actions` header;
- reorder remains understandable and functional;
- lifecycle actions remain intact.

## Values

- exact 28 approved values remain intact;
- no duplicates;
- no renamed values;
- no resurrected deleted/deactivated values.

## Regression

- RTE02 / A01 / A02 focused backend tests green;
- Core user-management regression green where touched;
- RTE03 access smoke green;
- RTE04 access smoke green;
- Administrator Mobile/My Route green;
- Supervisor Mobile/My Route green;
- no RTE03/RTE04 business-rule changes.

---

# Tests Required

## Role context

Mandatory discriminating tests:

1. Route Administrador → Route Users selector = 2 roles.
2. Superadmin → Route Users selector = 2 roles.
3. Core Admin/Owner → Route Users selector = 2 roles, where supported.
4. Route contract create `owner` → rejected.
5. Route contract update to `owner` → rejected.
6. Same for `admin`, `manager`, `viewer`.
7. Cross-tenant role → rejected.
8. Core management surface behavior remains unchanged.

## Capability cleanup

- assert exact Route Administrator capability set;
- assert exact Supervisor capability set;
- assert `roles.read` absent from Route Administrator;
- assert Route Users still works without `roles.read`.

## Vehicles browser

- list-first page;
- Add Vehicle modal open/cancel/save;
- newly created row visible;
- Edit;
- Deactivate;
- Show inactive;
- Reactivate;
- Delete / blocked delete where applicable.

## Standardized Lists browser

- all 8 groups visible inside container;
- counts correct;
- contextual Add Value modal;
- create value under selected group;
- cancel;
- lifecycle menu;
- reorder;
- inactive filter;
- exact approved values preserved.

## Regression

Run serially against controlled test databases.

Do not count discarded/invalid concurrent test runs as evidence.

---

# Documentation Correction

The prior summary stated:

`331 backend + 6 browser`

but the detailed report supports:

- **325 backend**
- **6 browser**
- **331 total**

Correct this in the final report.

Do not change test evidence to fit a number; report the actual final execution counts.

---

# Checkpoints

## A02-FC1 — Role Context Closure

- CER Route context always returns only Administrador + Supervisor.
- Superadmin scenario validated.
- API contract blocks Core roles.

## A02-FC2 — Capability Cleanup

- remove residual `roles.read`;
- prove 12 / 2 final capability counts;
- prove Route Users remains functional.

## A02-FC3 — Vehicles UX Standardization

- list-first;
- Add Vehicle modal;
- lifecycle regression.

## A02-FC4 — Standardized Lists UX Standardization

- contained group navigation;
- contextual Add Value modal;
- Actions/reorder cleanup;
- lifecycle regression.

## A02-FC5 — Final Regression & Evidence

- backend;
- browser;
- access matrix;
- provisioning/value integrity;
- RTE03/RTE04 access smoke;
- final report.

---

# Deliverables

Create a new incremental report:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_A02_FINAL_CLOSURE_REPORT_002.md`

Do not overwrite Delivery Report 001.

The report must include:

1. exact final role model;
2. evidence that Route context governs role assignment;
3. Superadmin browser evidence;
4. API bypass evidence;
5. final 12/2 capability matrix;
6. evidence `roles.read` was removed safely;
7. Vehicles before/after UX behavior;
8. Standardized Lists before/after UX behavior;
9. exact 28-value integrity evidence;
10. backend test counts;
11. browser test counts;
12. corrected total counts;
13. Expected → Implemented → Evidence → Gap;
14. remaining Core `manager -> owner` gap listed separately as out-of-scope;
15. confirmation RTE03/RTE04 behavior unchanged;
16. confirmation RTE05 not started.

Use unique incremental filenames for any additional report.

---

# STOP Conditions

STOP and return to CER if:

- fixing Route role context requires redesigning Core RBAC globally;
- Core/Foundation roles must be deleted/renamed to satisfy Route UX;
- multi-role membership becomes necessary;
- removing `roles.read` requires a broad bootstrap revocation redesign;
- Vehicles or Standardized Lists changes require new business rules;
- any RTE03/RTE04 behavior must change;
- the 28 approved values would need reinterpretation;
- a new product decision is required.

After A02-FC5 and the final report:

# STOP

Do not continue with RTE04 closure or RTE05 until CER reviews and certifies RTE02-A02.
