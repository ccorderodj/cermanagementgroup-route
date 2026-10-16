# CER Route — RTE04 Final Closure & Validation Instructions 004

## Context

RTE02-A02 is now **COMPLETED / CERTIFIED** and becomes part of the active baseline for RTE04.

RTE03 remains **CERTIFIED**.

RTE04 already has substantial implementation delivered under:

- `CER_ROUTE_RTE04_DEVELOPMENT_INSTRUCTIONS_001.md`
- `CER_ROUTE_RTE04_CER_DECISIONS_AND_CONTINUATION_002.md`
- `CER_ROUTE_RTE04_C1_CLOSURE_AND_CONTINUATION_003.md`
- `Report Delivery Rodrigo/CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`

This instruction is **not a restart of RTE04**.

The purpose is to take the existing RTE04 implementation, align it with the now-certified RTE02-A02 access/value baseline, revalidate the full RTE04 scope, close any remaining implementation gaps, and return a final closure candidate to CER.

RTE05 must not start.

---

# Current State

## Certified dependencies

### RTE02-A02

CER Route has exactly two product roles:

- **Administrador**
- **Supervisor**

Current approved authority:

### Administrador
- Read
- Execute
- Admin / Manage
- Can use the same Mobile / My Route operational experience as Supervisor
- Can also access CER Route Admin

### Supervisor
- Read
- Execute
- No Admin / Manage / Adjust

Both roles may execute the currently delivered Route operational flow.

`route.standardvalues.read` is the explicit read capability for operational standardized values.

The 8 approved lists / 28 approved Standardized Values are provisioned and are part of the active baseline.

`CER Route > Users` exposes only Administrador and Supervisor.

Do not reopen RTE02-A02.

---

## RTE04 implemented baseline to preserve

RTE04 covers:

**Trip Foundation + Odometer Evidence**

It does not include RTE05 Activity execution.

Implemented RTE04 areas already reported include:

- Trip planning and lifecycle;
- Change Plan;
- arrival;
- HOME direct close behavior;
- interrupted Trip path through explicit End Work Anyway;
- START odometer evidence;
- END odometer evidence;
- OCR assistive flow;
- no-photo exception flow;
- Admin exception decision;
- Option B for END no-photo exception;
- offline command queue behavior for supported non-photo commands;
- occurrence-time preservation;
- concurrency protection;
- malware scanning / scan verdict;
- authoritative current-state integration;
- standardized pre-trip value consumption;
- mobile My Route flow.

Do not rebuild these areas unless validation proves a defect.

---

# Objective

Produce the final RTE04 closure candidate by:

1. validating the existing RTE04 implementation against the certified RTE02-A02 baseline;
2. correcting only confirmed RTE04 defects;
3. proving both Administrador and Supervisor can execute the operational Route flow;
4. proving Supervisor retains no administrative authority;
5. revalidating Trip and odometer state/invariant behavior;
6. preserving all approved RTE01–RTE03 decisions;
7. identifying any remaining product decision without inventing one;
8. returning one final evidence-first report to CER;
9. stopping before RTE05.

---

# Scope

## In Scope

### Trip Foundation
- Trip creation inside an ACTIVE Work Session.
- PLANNING.
- Start Trip / IN_TRANSIT.
- Change Plan while IN_TRANSIT.
- Arrived.
- HOME arrival behavior.
- interruption through approved End Work Anyway behavior.
- current Trip restoration/resume.
- tenant isolation.
- idempotency / concurrency.
- occurrence timestamps.

### Pre-trip context
Validate the currently implemented pre-trip fields:

- Employee Visit → Employee Visit Reason
- Check Delivery → Delivery Type
- Office → Office Purpose

These must use the approved Standardized Values contract and current certified role permissions.

Do not move post-arrival fields into RTE04.

### Odometer Evidence
- START evidence.
- END evidence.
- photo evidence.
- OCR suggestion.
- Supervisor confirmation/correction.
- manual no-photo exception request.
- Admin approve/reject.
- START hard guard before driving.
- END Option B.
- evidence persistence.
- audit.
- security.
- malware scan verdict.
- concurrency.

### Mobile
- app-style My Route experience.
- Administrador operational access.
- Supervisor operational access.
- state restoration.
- error/retry behavior.
- offline queue for supported actions.

---

# Out of Scope

Do not implement:

- RTE05 Activities;
- post-arrival Activity multi-select;
- Outcomes execution flow;
- Received By post-arrival flow;
- GPS/location acquisition;
- routing mileage calculation;
- fuel estimation;
- Reports;
- Live Admin tracking;
- organizational hierarchy;
- RM/OSM data scopes;
- offline binary odometer photo capture;
- new Core/Foundation role changes;
- Core `manager -> owner` remediation.

Do not change RTE02-A02 role model.

---

# Confirmed Business Rules

## BR-01 — Work Session

A Trip may exist only inside an ACTIVE Work Session.

Start Work does not automatically create a Trip.

---

## BR-02 — Trip purpose and Activity are different concepts

RTE04 owns the travel plan / destination context.

RTE05 will own what was actually performed after arrival where applicable.

Do not implement RTE05 behavior to make RTE04 easier to close.

---

## BR-03 — Trip lifecycle

Use the existing RTE04 state model and guards.

Expected primary lifecycle:

`PLANNING -> IN_TRANSIT -> ARRIVED`

For HOME:

`PLANNING -> IN_TRANSIT -> CLOSED`

For explicit End Work Anyway while IN_TRANSIT:

`IN_TRANSIT -> INTERRUPTED`

Do not fabricate ARRIVED or Activity completion.

---

## BR-04 — Change Plan

Change Plan is available only while Trip is IN_TRANSIT.

After Arrived, Change Plan no longer applies.

A different destination after arrival belongs to a new Trip.

Preserve original plan history and append-only change evidence.

---

## BR-05 — Standardized Values

Operational read must use:

`route.standardvalues.read`

Both Administrador and Supervisor can read required values.

Only Administrador may manage the catalogs.

Do not restore the old `route.worksession.execute` shortcut as generic catalog-read authorization.

---

# Odometer Rules

## BR-06 — Start Work is not Start Driving

Do not force START odometer immediately after Start Work.

When vehicle use applies:

1. Work Session becomes ACTIVE.
2. START odometer remains PENDING.
3. My Route remains usable for non-driving work.
4. Persistent pending affordance remains available.
5. Attempting the first Trip requires START odometer resolution.

---

## BR-07 — START evidence

Normal path:

`PENDING -> PHOTO_CONFIRMED`

Photo + Supervisor-confirmed reading is the primary evidence.

OCR is assistive only.

OCR failure with a valid photo does not create an exception: Supervisor may manually enter the visible reading and confirm it as photo-backed evidence.

No-photo manual entry requires the approved exception workflow.

---

## BR-08 — START no-photo exception

Expected path:

`PENDING -> EXCEPTION_REQUESTED -> EXCEPTION_APPROVED -> MANUAL_EXCEPTION_CONFIRMED`

Admin approval is one-time and scoped to the specific:

- tenant;
- Supervisor;
- Work Session;
- Vehicle;
- START;
- exception request.

START Trip must remain blocked until START is resolved.

Supervisor may continue non-driving work while the exception is pending.

---

## BR-09 — END evidence / Option B

If END photo is unavailable and Supervisor requests a manual exception:

- the Work Session may transition to ENDED once all other approved End Work blockers are resolved;
- `ended_at` remains the actual End Work occurrence;
- END odometer remains unresolved;
- Odometer Distance remains pending;
- later Admin approval allows a bounded manual END completion attached to the already-ended session;
- resolving END evidence must not reopen the Work Session;
- resolving END evidence must not change `ended_at`;
- resolving END evidence must not permit a new Trip;
- no-photo evidence must remain distinguishable from photo-backed evidence.

---

## BR-10 — Odometer validation

- END reading must be >= START reading.
- Evidence belongs to the Work Session / vehicle snapshot.
- Do not silently overwrite confirmed readings.
- Post-close corrections remain Admin-only and audited.
- Routing Mileage and Odometer Distance remain independent facts.
- Odometer must never overwrite official Routing Mileage.

---

# Security / Audit

Validate:

- tenant isolation;
- server-side authorization;
- Supervisor Read + Execute only;
- Administrador Read + Execute + approved Route Admin;
- no cross-tenant odometer evidence access;
- private photo storage;
- validation of file type/size;
- malware scanning / truthful scan verdict;
- no public permanent photo URL;
- exception decisions audited;
- role-independent server guards;
- idempotent command handling;
- no duplicate Trip / Work Session / odometer evidence from replay or concurrent devices.

---

# Required Revalidation After RTE02-A02

The following is mandatory because the access model changed after the original RTE04 delivery.

## RV-01 — Administrador operational execution

Prove an Administrador can:

- enter My Route;
- Start Work;
- read required Standardized Values;
- plan a Trip;
- resolve START odometer;
- Start Trip;
- Change Plan where valid;
- Arrive.

Do not infer this from capability tables alone.

Validate via API and browser.

---

## RV-02 — Supervisor operational execution

Prove Supervisor can execute the same operational flow while being denied:

- Standardized Values management;
- Vehicles management;
- Users management;
- odometer exception approval;
- historical adjustment.

---

## RV-03 — Required pre-trip Standardized Values

Browser-validate at minimum:

### Employee Visit
- required Employee Visit Reason options load;
- selection persists;
- Start Trip accepts valid selection.

### Check Delivery
- required Delivery Type options load;
- selection persists;
- Start Trip accepts valid selection.

### Office
- required Office Purpose options load;
- selection persists;
- Start Trip accepts valid selection.

No Route workflow may depend on Admin/Manage permissions merely to read these values.

---

# Known Defects Previously Closed — Must Remain Closed

Regression tests must prove the following do not return.

## KD-01 — Standardized Values 403
Supervisor must be able to read operational values without `route.standardvalues.manage`.

## KD-02 — Concurrent odometer row creation
Concurrent devices/tabs must not produce transaction failure / 500.

## KD-03 — Concurrent Admin exception decision
Only one terminal decision may win. Conflicting concurrent decision must fail deterministically.

## KD-04 — Permanently rejected offline commands
Permanent 4xx actions must not remain queued forever.

An abandoned End Work must never replay later and close the Work Session without a new user action.

## KD-05 — Occurrence timestamp
Queued Trip actions must preserve actual occurrence time rather than sync/processing time.

## KD-06 — Malware scanning
Valid uploaded evidence must pass through the existing scan path and store truthful verdict:

- rejected → refuse/store nothing;
- not configured/unavailable → do not falsely mark clean.

## KD-07 — Query/connection regression
The prior odometer state query churn must remain resolved.

---

# Product Decisions Still Requiring CER Confirmation

Do **not** invent or silently change these behaviors.

Validate the current implementation and report exact as-built evidence.

## DR-01 — End Work from operational ARRIVED Trip

The current RTE04 implementation previously reported that an operational Trip in `ARRIVED` does not block End Work and is not automatically closed.

For this instruction:

- do not invent an Activity;
- do not fake Trip completion;
- do not change the behavior merely to achieve a green test;
- document exactly what currently happens to:
  - Work Session;
  - Trip state;
  - current-state endpoint;
  - future resumability;
  - historical consistency.

If the behavior creates an invalid or impossible persistent state, classify:

`DECISION REQUIRED`

and STOP before changing product behavior.

---

## DR-02 — Photo submitted after Work Session already ended under END exception

The current implementation previously chose to prevent a new post-close END photo from replacing the approved manual-exception path.

For this instruction:

- do not broaden that behavior;
- validate it exactly;
- distinguish `captured_at` from `uploaded_at` if those concepts exist;
- remember that offline binary photo capture is not implemented in RTE04.

If current behavior requires a product decision to close, classify:

`DECISION REQUIRED`

and STOP before changing it.

---

# Offline Boundary

Binary odometer photo capture while offline remains:

`PENDING VALIDATION / MOBILE HARDENING`

It is not an RTE04 closure blocker provided:

- Start Trip cannot bypass unresolved START evidence;
- UI clearly communicates connectivity requirement where relevant;
- no photo is fabricated;
- queued non-photo actions remain consistent and recoverable.

Do not implement offline binary storage/sync in this checkpoint unless CER separately authorizes it.

---

# Acceptance Criteria

RTE04 is a closure candidate only when all applicable items below are evidenced.

## Trip

- Trip only under ACTIVE Work Session.
- No duplicate active/current Trip caused by replay/concurrency.
- valid PLANNING -> IN_TRANSIT transition.
- Change Plan only IN_TRANSIT.
- Arrived transition valid.
- HOME closes directly as approved.
- End Work Anyway from IN_TRANSIT produces INTERRUPTED, not fake ARRIVED.
- authoritative current state returns correct Work Session + Trip.

## Standardized Values

- Employee Visit Reason works.
- Delivery Type works.
- Office Purpose works.
- Administrador and Supervisor can read them.
- Supervisor cannot manage them.
- no execute-as-read shortcut returns.

## START odometer

- pending after applicable Start Work.
- visible/recoverable pending state.
- Start Trip blocked while unresolved.
- photo path works.
- OCR suggestion is non-authoritative.
- manual confirmation from photo works.
- no-photo exception path works.
- approved manual START works only after scoped Admin approval.

## END odometer

- photo path works.
- END >= START.
- Option B works.
- Work Session may end with approved pending END exception semantics.
- `ended_at` remains immutable.
- later manual resolution does not reopen Work Session.
- Odometer Distance remains pending until valid END reading.

## Security

- tenant isolation.
- Supervisor cannot Admin/Manage.
- Administrator can execute + administer as approved.
- direct API guards match UX.
- private evidence access.
- audit coverage.
- malware scan behavior truthful.

## Reliability

- occurrence time preserved.
- idempotency.
- concurrency.
- offline queue rejection/retry behavior.
- no abandoned End Work replay.

## Regression

- RTE02-A02 access baseline remains intact.
- RTE03 behavior remains intact.
- RTE04 browser and backend regression green.
- RTE05 not started.

---

# Tests Required

Run serially against controlled test databases.

At minimum include:

## Backend
- Trip lifecycle and invalid transitions.
- Trip tenant isolation.
- Change Plan guards/history.
- HOME close.
- IN_TRANSIT End Work review/interruption.
- current-state envelope.
- Standardized Values read authorization.
- START odometer state machine.
- END odometer state machine.
- exception approval/rejection.
- concurrent evidence creation.
- concurrent Admin decision.
- occurrence timestamps.
- queue permanent-error handling.
- audit.
- file validation/scanning.
- RTE02-A02 role regression.
- RTE03 Work Session regression.

## Browser
At minimum:

1. Supervisor full RTE04 operational journey.
2. Administrador full RTE04 operational journey.
3. Employee Visit pre-trip value.
4. Check Delivery pre-trip value.
5. Office pre-trip value.
6. START odometer photo/confirmation.
7. START no-photo exception request.
8. Admin approval path.
9. END photo flow.
10. END Option B flow.
11. IN_TRANSIT End Work → Continue Working.
12. IN_TRANSIT End Work Anyway → INTERRUPTED.
13. state recovery/reopen.
14. offline/reconnect queue for supported actions.
15. rejected queued action does not replay unexpectedly.

Use the existing production frontend bundle and real browser validation pattern already established by the project.

Real iOS/Android hardware remains `PENDING VALIDATION` unless actually tested.

---

# Expected → Implemented → Evidence → Gap

The final report must provide this comparison for every material RTE04 area:

| Expected | Implemented | Evidence | Classification / Gap |
|---|---|---|---|

Use only:

- AS-BUILT / CONFIRMED
- PARTIAL
- PENDING VALIDATION
- NOT IMPLEMENTED / GAP
- DEVIATION
- UNAUTHORIZED DECISION
- TECHNICAL DEBT
- DECISION REQUIRED

Do not mark an item Completed only because an earlier report said so.

---

# Do Not Change

Do not change without CER decision:

- RTE02-A02 role model;
- RTE03 Work Session lifecycle;
- D-07 End Work rules;
- D-10 occurrence-time semantics;
- Routing Mileage definition;
- Trip endpoint-coordinate rules;
- RTE05 Activity behavior;
- Outcome model;
- free-text decisions;
- official 28 Standardized Values;
- Odometer vs Routing Mileage separation;
- END Option B semantics;
- Core/Foundation role model.

---

# Deliverables

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE04_FINAL_CLOSURE_REPORT_003.md`

Do not overwrite `CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`.

The report must include:

1. scope actually validated;
2. exact RTE04 as-built state;
3. RTE02-A02 compatibility evidence;
4. Administrador operational browser evidence;
5. Supervisor operational browser evidence;
6. Trip lifecycle evidence;
7. pre-trip Standardized Values evidence;
8. START odometer evidence;
9. END odometer / Option B evidence;
10. concurrency evidence;
11. offline queue evidence;
12. malware scan evidence;
13. security/audit evidence;
14. backend test counts;
15. browser test counts;
16. frontend build/typecheck/lint status;
17. Expected -> Implemented -> Evidence -> Gap;
18. DR-01 exact as-built result;
19. DR-02 exact as-built result;
20. real-device items still pending;
21. confirmation RTE03 behavior unchanged;
22. confirmation RTE05 not started;
23. proposed closure status.

Use unique incremental filenames for any additional report.

---

# Checkpoints

## RTE04-FC1 — Baseline Reconciliation
- confirm code includes certified RTE02-A02;
- verify role/capability behavior;
- verify 28 values available;
- verify no stale assumptions from pre-A02 RTE04 tests.

## RTE04-FC2 — Trip Foundation Regression
- planning;
- pre-trip context;
- start;
- Change Plan;
- Arrived;
- HOME;
- interrupted path;
- current state;
- concurrency/idempotency.

## RTE04-FC3 — START Odometer Regression
- pending;
- photo;
- OCR;
- confirmation;
- no-photo exception;
- Admin decision;
- Start Trip guard.

## RTE04-FC4 — END Odometer / End Work Regression
- photo;
- validation;
- Option B;
- pending manual resolution;
- immutable ended_at;
- D-07;
- queue behavior;
- DR-01 / DR-02 evidence.

## RTE04-FC5 — Security, Browser & Closure Evidence
- tenant isolation;
- role matrix;
- scanning;
- audit;
- browser journeys;
- full focused regression;
- final report.

---

# STOP Conditions

STOP and return to CER if:

- RTE04 closure requires implementing RTE05 Activity behavior;
- Trip state semantics need reinterpretation;
- DR-01 requires changing current product behavior;
- DR-02 requires changing current product behavior;
- any RTE02-A02 role/capability decision must be reopened;
- END Option B must be changed;
- offline binary photo capture becomes necessary for closure;
- Routing Mileage logic must be introduced into RTE04;
- a new product decision is required.

After RTE04-FC5:

# STOP

Do not begin RTE05 until CER reviews the RTE04 final closure report and explicitly certifies RTE04.
