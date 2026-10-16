# CER Route — RTE02 Addendum A01 Development Instructions 004
## Admin UX Lifecycle + Initial Standardized Values

**Applies after:** RTE03 — COMPLETED / CERTIFIED  
**Purpose:** Complete the approved RTE02 Admin UX/lifecycle delta before starting RTE04.  
**Required delivery report:** `Report Delivery Rodrigo/CER_ROUTE_RTE02_ADDENDUM_A01_DELIVERY_REPORT_001.md`

---

## Current State

RTE02 already provides the CER Route administrative foundation for:

- Core user management reused from the existing platform;
- Route Supervisor designation/profile;
- Vehicles;
- Vehicle assignments;
- the eight Route Standardized Lists;
- tenant-scoped server-side authorization and audit;
- Mobile Supervisor shell and Admin shell.

RTE03 is already functionally certified and must be treated as part of the current baseline.

This Addendum does **not** reopen RTE02 architecture. It closes an approved Admin UX/lifecycle improvement identified during product navigation review.

The approved delta is:

1. distinguish **Deactivate / Reactivate** from **Delete**;
2. expose lifecycle actions through usable, state-aware Admin UX;
3. preload the eight Standardized Lists with the exact approved V0.7 initial values;
4. ensure deleted/renamed seeded values are not recreated automatically;
5. preserve historical integrity and audit;
6. keep existing Core/User ownership boundaries intact.

---

## Objective

Make CER Route Admin usable for normal maintenance without requiring Postman, manual API calls, database access, or developer intervention.

After this Addendum, an authorized Route Admin must be able to:

- manage Route users through the existing Core user-management UI;
- designate/remove/restore Route Supervisors;
- create/edit/deactivate/reactivate/delete Vehicles according to the approved rules;
- manage Vehicle Assignments through create/read/end/replace/history;
- manage all values in the eight Standardized Lists through create/edit/reorder/deactivate/reactivate/delete;
- see the approved initial Standardized List values already provisioned for the tenant.

---

## Confirmed Decisions

### 1. Deactivate / Reactivate and Delete are different actions

**Deactivate**
- temporarily removes the record from operational use;
- retains it in the normal Admin experience when viewing inactive records;
- can be reversed with Reactivate.

**Delete**
- removes the record from the normal Admin experience;
- the deleted record must not continue appearing in ordinary active/inactive lists or selectors;
- historical/audit integrity must remain preserved internally;
- implementation may use a safe physical delete or a tombstone/retained-reference strategy as technically appropriate;
- the internal persistence strategy must not leak tombstones back into normal Admin UX.

Delete must **not** be implemented as a synonym for Deactivate.

---

### 2. Admin actions must be state-aware, not five simultaneous CRUD buttons

Do not render:

`Create / Update / Deactivate / Reactivate / Delete`

as five permanent row buttons.

Use contextual UX:

**Page-level**
- `+ Add Vehicle`
- `+ Add Value`
- equivalent primary Create actions where applicable.

**Active row**
- `Edit`
- secondary actions in contextual menu (`...`) or equivalent:
  - `Deactivate`
  - `Delete`

**Inactive row**
- `Reactivate`
- `Delete`
- do not show `Deactivate` simultaneously.

**Delete**
- must be visually secondary/destructive;
- requires confirmation;
- if blocked, explain the business reason in normal language;
- backend remains authoritative even if the UI disables/hides an invalid action.

Mobile Admin, if the current Admin UI is responsive, must preserve the same semantics using an appropriate compact menu/action sheet rather than cramped desktop buttons.

---

### 3. Users remain Core-owned

Do not create a Route-specific duplicate user model, authentication model, or Route user API if the existing Core User capability already owns that concern.

Route Admin must continue to use the existing Core user-management surface.

Approved user lifecycle:

- Create user + tenant membership + role using existing Core behavior;
- Read;
- Edit supported identity/profile fields;
- Deactivate/restore tenant membership using the existing supported mechanism;
- Delete from the **normal tenant Admin/access experience** without incorrectly destroying a shared/platform identity that may belong to other tenants or platform concerns.

The exact safe Core implementation of tenant-level Delete is delegated to Development.

### Explicitly deferred

Do **not** add in this Addendum:

- same-person / different-person matching;
- reused/generic email reassignment;
- identity re-enrollment;
- automatic identity matching;
- advanced rehiring/re-enrollment logic.

If the same person may return under the current model, normal operational guidance remains to use **Deactivate** rather than inventing identity recovery behavior in this sprint.

---

### 4. Supervisor lifecycle

Supervisor designation is a Route concern layered over Core User.

Required behavior:

- designate an eligible Core User as a Route Supervisor;
- view Supervisor designation;
- deactivate/remove the Route designation from the normal Route experience;
- restore/reactivate the designation when allowed;
- Delete removes the Route designation/profile from the normal Route Admin experience;
- deleting a Supervisor designation must **not** automatically delete the underlying Core User;
- historical operational references must remain valid.

If an active business constraint prevents the action, reject it server-side and explain the reason to the Admin.

---

### 5. Vehicle lifecycle

Required actions:

- Create;
- Read;
- Edit;
- Deactivate/Retire;
- Reactivate/Restore;
- Delete.

Rules:

- an active/current Vehicle Assignment must block Vehicle Delete until the assignment is resolved;
- the UI should communicate the reason, for example: `Delete unavailable — end the current vehicle assignment first.`
- historical assignments and historical Work Session snapshots must remain valid;
- Delete must not silently corrupt historical references.

Do not change the existing approved Vehicle master fields or fixed FuelGrade model.

---

### 6. Vehicle Assignments do not receive destructive Delete

Vehicle Assignment lifecycle remains:

- Create;
- Read;
- End;
- Replace;
- History.

Do not add a normal destructive Delete action for assignment history.

Existing rule remains:

- one current assignment per Supervisor;
- do not introduce a new rule that a Vehicle can belong to only one Supervisor unless already enforced by an approved requirement.

---

### 7. Standardized List codes are product-defined; values are tenant data

The eight fixed list codes remain product-defined and cannot be created/deleted by tenants.

Tenant Admin manages only the **values** inside those lists.

Each list value must support:

- Create;
- Read;
- Edit;
- Reorder;
- Deactivate;
- Reactivate;
- Delete;
- View inactive values.

Delete removes the value from the normal Admin experience and operational selectors while preserving any required historical references.

`Outcomes` remains tenant-configurable data. Do not convert it into a hardcoded BusinessEnum.

---

## Initial Standardized Values

Provision the following exact initial values.

Do not replace them with synonyms.  
Do not add extra values.  
Do not rediscover them from the prototype; this file is the approved source for this Addendum.

### Client Visit Activities

1. `Staffing Follow-up`
2. `Service Review`
3. `Attendance Follow-up`
4. `Safety Follow-up`

### Recruiting Activities

1. `Candidate Sourcing`
2. `Hiring Event`
3. `Referral Follow-up`

### Employee Visit Reasons

1. `Attendance Issue`
2. `Document Follow-up`
3. `Transportation Issue`
4. `Employee Support`

### Delivery Types

1. `Payroll Check`
2. `Document Delivery`
3. `Equipment Delivery`

### Office Purposes

1. `Paperwork`
2. `Meeting`
3. `Pickup / Drop-off`
4. `Administrative Follow-up`

### Other Activities

1. `Housing Visit`
2. `Transportation Support`
3. `Supply Pickup`

### Outcomes

1. `Completed`
2. `Follow-up Required`
3. `Escalated`
4. `No Contact`

### Received By

1. `Employee`
2. `Authorized Person`
3. `Office Staff`

---

## Fields That Must Remain Free Text

Do **not** create or restore catalogs for:

- Client Visit destination;
- Recruiting Area / Location;
- Employee / Reference;
- Office;
- Other Area / Location.

These remain free text according to the approved V0.7 update.

Do not seed the old prototype collections for:

- `clientRefs`;
- `employeeRefs`;
- `recruitingAreas`;
- `offices`.

---

## Provisioning / Bootstrap Rules

Initial Standardized Values must be provisioned idempotently.

Required behavior:

- a fresh tenant receives the approved initial values;
- re-running bootstrap/provisioning does not create duplicates;
- an Admin-renamed seeded value is **not** reset to its original name on the next bootstrap;
- an Admin-deleted seeded value is **not** silently resurrected on the next bootstrap;
- an Admin-deactivated seeded value is **not** silently reactivated on the next bootstrap;
- provisioning must be tenant-safe.

Development may choose the technical mechanism, but the observable behavior above is required.

---

## Roles & Permissions

Reuse the existing Core and Route capabilities wherever they already own the operation.

Do not create orphan or duplicate capabilities only to make this Addendum appear isolated.

Requirements:

- all authorization remains server-side;
- tenant scope is mandatory;
- Route Admin must not gain platform-superuser privileges;
- Supervisor must not gain Admin lifecycle permissions merely because they can execute Work Sessions;
- Delete must be permission-checked server-side;
- UI visibility/disabled state is not a substitute for backend authorization.

If an existing Core capability is insufficient for a required operation, document the exact gap before introducing a new capability.

---

## Security / Audit

All sensitive lifecycle changes must remain auditable.

At minimum, audit the relevant lifecycle actions:

- Create;
- Edit;
- Deactivate;
- Reactivate;
- Delete;
- Supervisor designation changes;
- Vehicle assignment create/end/replace;
- Standardized value reorder when it changes persisted order.

Audit must identify, where applicable:

- tenant;
- actor;
- entity;
- action;
- timestamp;
- prior/current state or sufficient before/after context;
- reason when the existing UX/domain already supports one.

Do not log passwords, secrets, or protected credentials.

Historical operational records must remain interpretable after Admin Delete actions.

---

## Scope

Implement only the approved RTE02-A01 delta:

1. contextual Admin lifecycle UX;
2. true Delete semantics separate from Deactivate;
3. User tenant-level Delete behavior using Core ownership boundaries;
4. Supervisor designation Delete behavior;
5. Vehicle Delete behavior;
6. Standardized List value Delete behavior;
7. exact initial values for all eight lists;
8. idempotent provisioning behavior;
9. required authorization/audit/tests;
10. regression against the now-certified RTE03 baseline.

---

## Out of Scope

Do not implement in this Addendum:

- Work Session changes;
- Start Work / End Work changes;
- Trip;
- Activity execution;
- geolocation;
- routing mileage;
- odometer;
- camera;
- OCR;
- odometer exception workflow;
- fuel calculation;
- Today/Live;
- Reports;
- post-close operational corrections;
- new Supervisor Desktop;
- new identity-reenrollment architecture;
- generic/reused-email reassignment;
- new tenant-defined Standardized List codes;
- RTE04 functionality.

---

## Acceptance Criteria

### Admin UX

- [ ] Create actions are page-level primary actions where appropriate.
- [ ] Active records expose Edit plus contextual Deactivate/Delete actions.
- [ ] Inactive records expose Reactivate/Delete, not Deactivate.
- [ ] Delete requires confirmation.
- [ ] Blocked Delete explains the business reason.
- [ ] Normal Admin maintenance does not require Postman, direct API use, DB access, or developer assistance.

### Users

- [ ] Existing Core User management is reused.
- [ ] No duplicate Route user domain is introduced.
- [ ] Tenant-level Delete removes the user from the normal tenant Admin/access experience.
- [ ] Delete does not incorrectly destroy shared/platform identity.
- [ ] Deactivate/Reactivate remains available separately.
- [ ] No advanced identity re-enrollment behavior is introduced.

### Supervisors

- [ ] Admin can designate an eligible Core User as Route Supervisor.
- [ ] Admin can deactivate/remove and restore designation according to current rules.
- [ ] Delete removes the Route designation/profile from normal Route Admin UX.
- [ ] Underlying Core User is preserved.
- [ ] Historical references remain valid.

### Vehicles

- [ ] Create/Edit/Deactivate/Reactivate/Delete are usable from Admin.
- [ ] Vehicle with current assignment cannot be deleted.
- [ ] Backend independently enforces the Delete restriction.
- [ ] Historical assignments and Work Session vehicle snapshots remain valid.

### Assignments

- [ ] Create/Read/End/Replace/History remain usable.
- [ ] No destructive Delete was added.

### Standardized Lists

- [ ] All eight list codes are visible and manageable.
- [ ] Values support Create/Edit/Reorder/Deactivate/Reactivate/Delete/View inactive.
- [ ] Deleted values disappear from normal active/inactive Admin lists and operational selectors.
- [ ] List codes themselves cannot be deleted by tenant Admin.
- [ ] Outcomes remain tenant data.

### Initial Values

- [ ] All exact values in this instruction are provisioned.
- [ ] No extra prototype catalogs are created.
- [ ] Free-text fields remain free text.
- [ ] Provisioning is idempotent.
- [ ] Renamed values are not reset.
- [ ] Deleted values are not resurrected.
- [ ] Deactivated values are not silently reactivated.

### Security / Regression

- [ ] Server-side authorization is enforced for every lifecycle action.
- [ ] Cross-tenant access is rejected.
- [ ] Audit covers lifecycle changes.
- [ ] RTE03 Work Session behavior remains unchanged.
- [ ] Existing backend test suite remains green.
- [ ] Frontend typecheck/lint/build remain green.
- [ ] No RTE04 or odometer functionality was started.

---

## Tests / Evidence Required

The delivery report must identify exact tests/evidence for the following.

### Discriminating lifecycle tests

For each entity where Delete is introduced, prove separately:

- Deactivate removes it from operational use but it remains available through inactive view;
- Reactivate restores it;
- Delete removes it from normal Admin experience;
- Delete is not merely another name for Deactivate.

Do not rely on a single test where both outcomes could be explained by the same status flag.

### User tests

Prove:

- authorized Route Admin can execute the supported tenant-level lifecycle;
- unauthorized user cannot;
- one tenant cannot delete/deactivate another tenant's membership;
- platform/shared identity integrity is preserved;
- no superuser escalation occurs.

### Supervisor tests

Prove:

- delete/remove designation does not delete Core User;
- restore/designate behavior works;
- historical references remain valid.

### Vehicle tests

Prove:

- active/current assignment blocks Delete;
- after the blocking assignment is properly ended, Delete follows the approved lifecycle;
- historical Work Session snapshot remains readable after Vehicle lifecycle changes.

### Standardized List tests

For each list code or through a parameterized test covering all eight:

- initial exact values exist;
- create;
- edit;
- reorder;
- deactivate;
- reactivate;
- delete;
- show inactive;
- deleted values do not appear in normal selectors;
- tenant isolation.

### Provisioning tests

Prove:

1. fresh tenant receives initial values;
2. rerun creates no duplicates;
3. renamed seed remains renamed;
4. deleted seed remains deleted;
5. deactivated seed remains deactivated.

### Regression evidence

Report:

- targeted backend tests;
- authorization tests;
- full backend suite;
- frontend typecheck;
- frontend lint;
- production build;
- any schema/migration validation required by the implementation.

---

## Do Not Change

Do not modify the following product decisions while implementing this Addendum:

- RTE03 Work Session lifecycle or behavior;
- Routing Mileage definition;
- Mobile-only Supervisor decision;
- Vehicle/MPG Work Session snapshot;
- one current assignment per Supervisor;
- fixed FuelGrade values;
- eight fixed Standardized List codes;
- Outcomes as tenant-configurable data;
- free-text fields listed above;
- Core User ownership of identity/authentication;
- Vehicle Assignments as non-destructive historical lifecycle;
- approved odometer design for the upcoming Trip checkpoint.

Do not introduce odometer behavior early.

---

## Deliverables

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_ADDENDUM_A01_DELIVERY_REPORT_001.md`

The report must contain only evidence material to this Addendum:

1. implemented Admin UX changes;
2. lifecycle behavior by entity;
3. exact initial values provisioned;
4. provisioning/idempotency behavior;
5. server-side authorization;
6. audit behavior;
7. relevant data/schema changes;
8. Expected → Implemented → Evidence → Gap matrix;
9. tests and regression results;
10. any remaining `PENDING VALIDATION`, `DEVIATION`, or `TECHNICAL DEBT`;
11. confirmation that RTE03 behavior was not changed;
12. confirmation that RTE04/odometer was not started.

Proposed delivery status may be:

`RTE02-A01 — Completed / Ready for CER Validation`

CER performs the final functional certification.

---

## STOP Conditions

STOP and return to CER before implementing a new product decision if any of the following becomes necessary:

- changing Core identity semantics beyond the tenant-level lifecycle required here;
- creating a new Route-specific User identity model;
- designing reused/generic-email reassignment or re-enrollment;
- changing Vehicle Assignment exclusivity rules;
- changing fixed Standardized List codes;
- converting Outcomes into a hardcoded enum;
- changing any approved free-text field into a catalog;
- altering RTE03 Work Session behavior;
- implementing Trip, odometer, camera, OCR, geolocation, routing mileage, or any RTE04 scope.

After producing `CER_ROUTE_RTE02_ADDENDUM_A01_DELIVERY_REPORT_001.md`, **STOP**.

Do not continue into RTE04 or the odometer checkpoint until CER reviews and certifies this Addendum.
