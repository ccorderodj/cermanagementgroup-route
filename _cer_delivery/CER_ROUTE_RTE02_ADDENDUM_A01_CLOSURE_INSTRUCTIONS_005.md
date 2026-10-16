# CER Route — RTE02 Addendum A01 Closure Instructions 005
## Final Admin UX Validation

**Baseline delivery:** `Report Delivery Rodrigo/CER_ROUTE_RTE02_ADDENDUM_A01_DELIVERY_REPORT_001.md`  
**Purpose:** Close the two remaining functional validation points for RTE02-A01 without expanding scope.  
**Required delivery report:** `Report Delivery Rodrigo/CER_ROUTE_RTE02_ADDENDUM_A01_CLOSURE_DELIVERY_REPORT_002.md`

---

## Current State

RTE02-A01 has implemented and evidenced the approved lifecycle behavior for Vehicles, Supervisor designations and Standardized List values, including:

- Delete distinct from Deactivate;
- Reactivate as a separate action;
- historical integrity through retained records;
- exact initial values for the eight Standardized Lists;
- idempotent provisioning;
- server-side authorization;
- tenant isolation;
- audit;
- regression coverage.

Two items remain before CER functional certification:

1. The delivery confirms a tenant-level User Delete backend flow and the new `users.delete` capability, but does not demonstrate that the existing Admin user interface actually exposes and completes that action.
2. The Addendum is primarily an Admin UX change, but the new lifecycle interactions were validated by typecheck/lint/build rather than by browser-level execution.

This closure is limited to validating and, only if needed, completing those two items.

---

## Objective

Provide sufficient functional evidence that an authorized Route Admin can perform the approved lifecycle actions from the actual Admin UI, without Postman, direct API calls, database access or developer intervention.

The result must prove:

- User Delete is reachable and usable from the existing Core user-management UI;
- lifecycle actions for Vehicles, Supervisors and Standardized List values behave correctly in a browser;
- the implementation already delivered for RTE02-A01 remains otherwise unchanged.

---

## Confirmed Decisions

### 1. User Delete must be available from normal Admin UI

The approved tenant-level User lifecycle remains:

- Create;
- Read;
- Edit;
- Deactivate/Suspend;
- Reactivate/Restore;
- Delete.

Delete must remain distinct from Deactivate.

The existing Core User domain and `SecurityUsersPanel` must be reused. Do not create a Route-specific user model or duplicate user-management surface.

If `SecurityUsersPanel` already exposes Delete correctly, no new implementation is required; provide browser evidence.

If it does not, add only the minimum UI integration necessary to expose the already implemented tenant-level Delete behavior.

Delete must:

- require confirmation;
- be permission-controlled;
- remove the user from the normal tenant Admin/access experience;
- not destroy the shared/platform `user` identity;
- not introduce re-enrollment or reused-email logic.

---

### 2. Browser validation is required for the Admin lifecycle UX

Validate the actual browser behavior for the lifecycle surfaces changed by RTE02-A01.

At minimum validate:

#### Vehicles
- Active row exposes Edit + Deactivate + Delete contextually.
- Inactive row exposes Reactivate + Delete.
- Delete requires confirmation.
- Vehicle with a current assignment cannot be deleted and the UI explains why.
- After ending the blocking assignment, Delete can proceed.

#### Supervisor Designations
- Active designation exposes the approved lifecycle actions.
- Inactive designation can be restored or deleted.
- Delete requires confirmation.
- Current assignment blocks invalid Delete and the reason is shown.
- Underlying Core User remains intact.

#### Standardized List Values
- Active value exposes Edit + Deactivate + Delete.
- Inactive value exposes Reactivate + Delete.
- Delete requires confirmation.
- Deleted value disappears from normal Admin lists and operational selectors.
- Inactive filtering/view works.

#### Users
- Existing Core Admin user-management UI exposes the supported tenant lifecycle.
- Delete is available only to an authorized role.
- Delete requires confirmation.
- Deleted tenant membership no longer appears as a normal active/inactive user entry for that tenant.
- The same platform identity is not physically destroyed.

---

## Scope

Only:

1. browser-level validation of the RTE02-A01 Admin lifecycle;
2. minimal User Delete UI integration if currently missing;
3. defect correction only when the browser validation reveals behavior that directly contradicts the approved RTE02-A01 criteria;
4. targeted tests/evidence for any code changed by this closure;
5. final closure report.

---

## Out of Scope

Do not implement:

- identity re-enrollment;
- same-person/different-person matching;
- generic/reused email reassignment;
- Redux/DataTable refactor;
- unrelated frontend technical debt;
- Work Session changes;
- Trip;
- Activity;
- odometer;
- camera;
- OCR;
- GPS/geolocation;
- routing mileage;
- fuel;
- Reports;
- Today/Live;
- RTE04 functionality.

Do not use this closure to refactor existing Route Admin architecture.

---

## Acceptance Criteria

RTE02-A01 can be certified when all of the following are demonstrated:

- [ ] User Delete is executable from the normal Admin UI.
- [ ] User Delete reuses Core user management; no duplicate Route user domain exists.
- [ ] User Delete requires confirmation.
- [ ] User Delete is authorized server-side and unavailable to users lacking `users.delete`.
- [ ] User Delete removes only the tenant membership/access experience and preserves shared platform identity.
- [ ] Vehicle Deactivate / Reactivate / Delete behaves correctly in the browser.
- [ ] Supervisor designation Deactivate / Reactivate / Delete behaves correctly in the browser.
- [ ] Standardized List value Deactivate / Reactivate / Delete behaves correctly in the browser.
- [ ] Active and inactive rows expose only contextually valid lifecycle actions.
- [ ] Blocked Delete displays a clear business reason.
- [ ] Deleted records do not leak back into ordinary Admin active/inactive lists or operational selectors.
- [ ] No RTE03 behavior changes.
- [ ] No RTE04 or odometer functionality starts.
- [ ] Any code modified by this closure passes the relevant backend/frontend regression checks.

---

## Tests / Evidence Required

### Browser-level evidence

Use an actual browser automation or equivalent repeatable browser validation.

Evidence must show the resulting state, not only that a button was clicked.

At minimum prove:

1. **Vehicle lifecycle**
   - deactivate;
   - show inactive;
   - reactivate;
   - delete;
   - blocked delete with current assignment.

2. **Supervisor lifecycle**
   - deactivate/remove;
   - restore;
   - delete;
   - Core User survives.

3. **Standardized List lifecycle**
   - edit;
   - deactivate;
   - show inactive;
   - reactivate;
   - delete;
   - operational selector no longer returns deleted value.

4. **User lifecycle**
   - authorized Admin can see and execute Delete;
   - unauthorized role cannot;
   - confirmation is required;
   - deleted membership loses tenant access;
   - shared Core identity remains.

If browser automation cannot validate a specific server-side historical property, pair the browser result with the existing integration test that proves that property.

### Regression

If no code changes are required:
- report the browser validation results and confirm the existing RTE02-A01 backend regression remains applicable.

If code changes are required:
- run targeted tests for the changed behavior;
- run relevant authorization tests;
- frontend typecheck;
- frontend lint;
- production build;
- full backend regression if backend code changes.

---

## Do Not Change

Do not change:

- the tombstone strategy already implemented;
- Delete vs Deactivate semantics;
- Vehicle Assignment lifecycle;
- Core ownership of Users;
- terminal User Delete behavior under the current no-re-enrollment model;
- the eight Standardized List codes;
- the 28 approved initial values;
- provisioning/idempotency rules;
- RTE03 Work Session behavior;
- Routing Mileage definition;
- approved future odometer design.

The pre-existing Route Admin Redux/DataTable debt is not part of this closure.

---

## Deliverables

Create a new report:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_ADDENDUM_A01_CLOSURE_DELIVERY_REPORT_002.md`

The report must include:

1. whether User Delete UI already existed or required a minimal correction;
2. exact browser evidence for Users, Vehicles, Supervisors and Standardized Lists;
3. Expected → Implemented → Evidence → Gap matrix;
4. any code/components changed in this closure;
5. targeted test results for any changed code;
6. browser validation result;
7. remaining `PENDING VALIDATION`, if any;
8. confirmation that RTE03 was not changed;
9. confirmation that RTE04/odometer was not started;
10. proposed final status: `RTE02-A01 — Completed / Ready for CER Certification`.

---

## STOP Conditions

STOP and return to CER before implementing if browser validation reveals that closing this Addendum would require:

- redesigning Core identity;
- implementing re-enrollment;
- changing tenant membership semantics beyond the already approved Delete behavior;
- introducing a Route-specific user model;
- refactoring Route Admin to Redux/DataTable;
- changing the eight fixed list codes;
- changing the approved initial values;
- changing RTE03;
- starting Trip, odometer, camera, OCR, GPS, routing mileage or any RTE04 functionality.

After creating `CER_ROUTE_RTE02_ADDENDUM_A01_CLOSURE_DELIVERY_REPORT_002.md`, **STOP**.

Do not continue into RTE04 or the odometer checkpoint until CER reviews and certifies RTE02-A01.
