# CER Route — RTE05 Final Closure Instructions 002

## Context

RTE05 was delivered as:

`Report Delivery Rodrigo/CER_ROUTE_RTE05_DELIVERY_REPORT_001.md`

The implementation is functionally complete except for two closure gaps identified by CER during final review.

This instruction is **not a reopening or redesign of RTE05**.

Only the two deltas below are authorized.

RTE02-A02, RTE03 and RTE04 remain certified baseline.

Do not begin RTE06.

---

# Objective

Close RTE05 by correcting:

1. the `Received By` terminalization rule for Check Delivery;
2. the visible/navigation access to **My Route** for both Administrador and Supervisor.

Then run focused regression, produce closure evidence, and STOP for CER certification.

---

# Current State

## Confirmed RTE05 baseline

Already implemented and to be preserved:

- one Activity execution block per Trip;
- 1..N selected Activities where applicable;
- one start / one end / one duration / one Outcome / one Notes;
- Complete and Leave as controlled terminal actions;
- Outcome required for both;
- Trip closes after terminalization;
- Work Session remains ACTIVE;
- End Work blocked while ARRIVED unresolved or Activity IN_PROGRESS;
- current-state recovery;
- idempotency/concurrency;
- offline queue behavior;
- tenant isolation;
- audit;
- historical snapshots;
- no RTE06+ functionality.

Do not modify these behaviors except where explicitly stated below.

---

# Delta 1 — Check Delivery / Received By

## Confirmed decision

For `Check Delivery`:

### Complete
- `Outcome` = required
- `Received By` = required
- `Notes` = optional

### Leave
- `Outcome` = required
- `Received By` = optional
- `Notes` = optional

Rationale:

A Supervisor may leave a Check Delivery stop without anyone having received the item. The system must not force a fabricated receiver simply to terminalize the visit.

Do not derive this rule from specific Outcome labels.

`Outcome` is tenant-configured data and must remain independent from this validation.

---

## Functional Requirements — Delta 1

### D1-FR01 — Backend validation

For Check Delivery:

- Complete without `Received By` → reject.
- Complete with valid `Received By` → allow.
- Leave without `Received By` → allow.
- Leave with valid `Received By` → allow.

For every other context:

- `Received By` remains invalid/not applicable.

Preserve tenant/list validation and historical label snapshot behavior.

---

### D1-FR02 — UX

On Check Delivery terminalization:

- when action = **Complete**, `Received By` must be visibly required;
- when action = **Leave**, `Received By` must not block confirmation;
- if a receiver is selected on Leave, preserve it;
- Outcome remains required for both;
- Notes remains optional.

Do not introduce conditional behavior based on specific Outcome names.

---

# Delta 2 — My Route Navigation / Discoverability

## Confirmed product model

Both CER Route functional roles use the same operational experience:

- **Administrador**
- **Supervisor**

There is only one **My Route** experience.

Do not create a second operational UI for Administrador.

Do not place My Route under `Configuration`.

My Route is an operational area of CER Route.

---

## D2-FR01 — Administrador navigation

An authenticated CER Route **Administrador** must have a visible, normal navigation path to:

**CER Route → My Route**

The user must not need to know or manually enter a direct URL.

Administrador must retain access to:

- My Route
- Users
- Supervisors
- Vehicles
- Standardized Lists
- Odometer Exceptions

The exact menu placement is delegated, but My Route must be visually distinguishable from configuration/admin areas.

---

## D2-FR02 — Supervisor navigation

An authenticated **Supervisor** must have visible/direct access to:

**CER Route → My Route**

Supervisor must not see CER Route administrative/configuration options:

- Users
- Vehicles
- Standardized Lists
- Odometer Exceptions
- other Admin-only Route configuration

Do not rely only on hidden menu items; existing server authorization must remain the real enforcement.

---

## D2-FR03 — Same operational experience

Administrador and Supervisor must reach the same My Route operational component and workflow.

Do not fork the Mobile experience by role.

Role differences are:

- Administrador: Execute + Admin/Manage
- Supervisor: Execute + Read only

---

## D2-FR04 — Entry / landing behavior

Validate the actual signed-in experience.

If the current application has a role-based landing/entry decision:

- Supervisor should naturally reach or be able to immediately enter My Route;
- Administrador must have a clear visible choice/access to My Route in addition to Admin.

Do not invent a new dashboard solely for this closure.

---

# Scope

## In Scope

- Check Delivery Complete/Leave validation.
- Check Delivery terminal UX.
- CER Route navigation.
- My Route discoverability.
- role-based menu visibility.
- browser validation.
- focused backend regression.
- focused RTE05 regression.

## Out of Scope

Do not change:

- Activity execution model;
- Trip lifecycle;
- Work Session lifecycle;
- Outcome catalog;
- 28 Standardized Values;
- Supervisor capabilities;
- Administrador capabilities;
- Users role model;
- Vehicles;
- Odometer business rules;
- GPS/location;
- routing mileage;
- fuel;
- Reports;
- Live;
- RTE06+ functionality;
- Core/Foundation navigation architecture beyond what is necessary to expose CER Route My Route correctly.

---

# Security / Permissions

Preserve server-side enforcement.

Navigation visibility must reflect permissions but must not replace authorization.

Validate:

- Administrador can enter My Route.
- Supervisor can enter My Route.
- Supervisor remains denied from Admin endpoints/pages.
- Direct URL to Admin remains denied for Supervisor.
- No new capability is required unless a real technical blocker proves otherwise.

If implementation appears to require a new capability, STOP and report why before adding it.

---

# Acceptance Criteria

## AC-01 — Check Delivery Complete

Given a Check Delivery execution:

- Complete with no Received By → rejected;
- Complete with valid Received By + Outcome → terminalizes successfully;
- Trip becomes CLOSED;
- Work Session remains ACTIVE.

## AC-02 — Check Delivery Leave

Given a Check Delivery execution:

- Leave with Outcome and no Received By → succeeds;
- Leave with Outcome + Received By → succeeds;
- Trip becomes CLOSED;
- Work Session remains ACTIVE.

## AC-03 — Outcome

Outcome remains required for both Complete and Leave.

No Outcome-label-specific branching exists.

## AC-04 — Administrador navigation

From normal signed-in navigation:

- CER Route visibly exposes **My Route**;
- clicking it opens the operational experience;
- Admin configuration remains available.

A direct URL is not sufficient evidence.

## AC-05 — Supervisor navigation

From normal signed-in navigation:

- Supervisor can visibly reach My Route;
- Supervisor does not see Admin configuration options;
- My Route operational flow opens successfully.

## AC-06 — Shared experience

Administrador and Supervisor reach the same My Route operational flow.

No duplicated My Route component/experience is introduced.

## AC-07 — Regression

- RTE05 execution remains green.
- RTE04 regression remains green where affected.
- RTE02-A02 role/access model remains green.
- No RTE06+ scope started.

---

# Tests Required

## Backend

Add or update focused tests proving:

1. Check Delivery Complete without Received By → reject.
2. Check Delivery Complete with Received By → success.
3. Check Delivery Leave without Received By → success.
4. Check Delivery Leave with Received By → success.
5. Outcome still required for both.
6. Received By rejected for non-Check-Delivery contexts.
7. Trip closure and Work Session state remain correct.

Run relevant RTE05 + affected RTE04 regression.

---

## Browser

Mandatory browser validation using normal navigation:

### Administrador
1. sign in as Administrador;
2. verify visible My Route navigation entry;
3. click My Route;
4. confirm operational screen loads;
5. confirm Admin configuration remains accessible.

### Supervisor
1. sign in as Supervisor;
2. verify visible/direct My Route access;
3. confirm operational screen loads;
4. confirm Admin configuration is not offered.

### Check Delivery
1. arrive at Check Delivery;
2. Complete without Received By cannot finish;
3. Complete with Received By finishes;
4. separate journey: Leave without Received By finishes;
5. Outcome required in both.

Do not validate My Route only through a manually entered URL.

---

# Expected → Implemented → Evidence → Gap

Final report must include:

| Expected | Implemented | Evidence | Classification |
|---|---|---|---|

Use:

- AS-BUILT / CONFIRMED
- PARTIAL
- PENDING VALIDATION
- NOT IMPLEMENTED / GAP
- DEVIATION
- TECHNICAL DEBT
- DECISION REQUIRED

---

# Deliverables

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE05_FINAL_CLOSURE_REPORT_002.md`

Do not overwrite the previous RTE05 report.

The report must include:

1. exact code/UI delta;
2. Check Delivery validation matrix;
3. backend evidence;
4. Administrador navigation evidence;
5. Supervisor navigation evidence;
6. browser evidence from normal navigation;
7. confirmation both roles use the same My Route experience;
8. permission regression;
9. RTE05 regression;
10. affected RTE04 regression;
11. frontend typecheck/lint/build;
12. Expected → Implemented → Evidence → Gap;
13. confirmation no RTE06+ work started;
14. proposed final status.

Use an incremental filename for any additional report.

---

# Do Not Change

Do not change:

- Activity execution architecture;
- one-block semantics;
- Outcome model;
- Trip state model;
- Work Session rules;
- role capabilities;
- standardized values catalog;
- RTE04 odometer behavior;
- End Work rules outside this already-approved RTE05 integration;
- Core roles;
- later Route modules.

---

# STOP Conditions

STOP and return to CER if:

- a new role/capability appears necessary;
- My Route requires redesigning the entire application shell;
- Supervisor must receive Admin permissions to see My Route;
- the Check Delivery change requires changing Outcome semantics;
- the correction affects Trip/Activity lifecycle beyond the explicit rule above;
- any new product decision is required.

After implementation, regression and final report:

# STOP

Do not begin RTE06 until CER certifies RTE05.
