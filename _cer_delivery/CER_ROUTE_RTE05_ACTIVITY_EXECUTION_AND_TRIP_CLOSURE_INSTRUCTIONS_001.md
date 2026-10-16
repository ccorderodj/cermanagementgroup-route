# CER Route — RTE05 Activity Execution + Outcome + Trip Closure — Development Instructions 001

## Context

RTE02-A02 is **COMPLETED / CERTIFIED**.

RTE03 is **COMPLETED / CERTIFIED**.

RTE04 is **COMPLETED / CERTIFIED**.

RTE05 begins from that certified baseline. Do not reopen or reinterpret prior checkpoints unless implementation evidence proves a direct incompatibility.

RTE05 owns the operational work that occurs **after a non-HOME Trip reaches ARRIVED** and must close the lifecycle that RTE04 intentionally left open.

The principal product requirement is:

`ARRIVED -> Activity Execution -> Complete / Leave + Outcome -> Trip CLOSED`

RTE05 must not fabricate Activity history merely to close a Trip. The user must perform the approved operational flow.

HOME remains the RTE04 exception: a HOME Trip closes directly on arrival and does not create an Activity execution.

---

# Current State

## Certified upstream behavior

### Work Session
- Start Work creates an ACTIVE Work Session.
- Start Work does not automatically create a Trip.
- Only one active Work Session exists per Supervisor.
- The same active session can resume across device/auth continuity.
- Both **Administrador** and **Supervisor** can execute My Route.

### Trip
- A Trip exists only inside an ACTIVE Work Session.
- Primary operational lifecycle:
  - `PLANNING -> IN_TRANSIT -> ARRIVED`
- HOME:
  - `PLANNING -> IN_TRANSIT -> CLOSED`
- Explicit End Work Anyway while IN_TRANSIT:
  - `IN_TRANSIT -> INTERRUPTED`
- Change Plan applies only while IN_TRANSIT.
- Current-state is server authoritative.
- Non-HOME ARRIVED Trips were intentionally not closed by RTE04 because Activity execution belongs to RTE05.

### Roles
- **Administrador** = Read + Execute + approved Route Admin/Manage.
- **Supervisor** = Read + Execute only.
- Both use the same app-style Mobile / My Route experience.
- Supervisor must never obtain Admin/Manage/Adjust authority.

### Standardized Values
Operational read uses:

`route.standardvalues.read`

The certified 8 lists / 28 initial values remain the baseline.

Do not use `route.worksession.execute` as a generic catalog-read permission.

---

# Objective

Implement and validate the complete post-arrival operational execution flow for non-HOME Trips so that:

1. the Supervisor/Administrador resumes from ARRIVED into the correct context-specific execution experience;
2. applicable post-arrival Activities are selected from tenant Standardized Values;
3. multiple selected Activities execute as **one execution block**;
4. one block has one start, one end, one duration, one Outcome and one Notes field;
5. Complete Activity and Leave are the controlled terminal actions;
6. Outcome is required to terminalize the execution;
7. the associated Trip closes only after the required execution flow is terminal;
8. End Work cannot leave unresolved ARRIVED/IN_PROGRESS operational work behind;
9. reload, reauth, device change, replay and offline synchronization preserve authoritative state;
10. history remains readable even if configured values later change;
11. RTE01-RTE04 behavior remains intact;
12. RTE06+ functionality is not introduced.

---

# Scope

## In Scope

- Non-HOME Trips in ARRIVED.
- Context-specific post-arrival UI.
- Post-arrival Activity selection where approved.
- 1..N Activity multi-select where approved.
- One Activity execution block per operational stop.
- Start Activity.
- Active execution state.
- Resume/recovery of active execution.
- Complete Activity.
- Leave.
- Outcome selection.
- Optional Notes.
- Check Delivery post-arrival `Received By`.
- Trip closure after terminal execution.
- End Work guards for unresolved ARRIVED / active execution.
- Current-state extension for execution recovery.
- Read permissions for required configured values.
- Idempotency.
- concurrency.
- offline/reconnect for supported non-binary Activity commands.
- occurrence timestamps.
- audit.
- tenant isolation.
- Web Admin catalog compatibility.
- Mobile/My Route UX.
- backend + browser validation.

---

# Out of Scope

Do not implement:

- GPS/location acquisition;
- Routing Mileage calculation;
- fuel estimation;
- Today / Live Admin tracking;
- Reports;
- payroll;
- CRM;
- organizational hierarchy;
- RM/OSM team scopes;
- new Core/Foundation roles;
- Core `manager -> owner` remediation;
- offline binary odometer photo capture;
- a generic workflow engine;
- AI decision-making for Activity/Outcome/state transitions;
- Admin historical correction UI unless an already-approved shared correction mechanism is being reused without broadening scope;
- new Standardized List types not listed in this document.

Do not alter RTE04 Trip or odometer rules merely to simplify RTE05.

---

# Confirmed Product Decisions

## PD-01 — One execution block, not one timer per selected Activity

For contexts that allow Activity selection at Arrived, the user may select **1..N Activities**.

Those selections belong to **one execution block**.

The block has:

- one start;
- one active period;
- one completion/leave time;
- one duration;
- one Outcome;
- one optional Notes value.

Do not create:

- separate timers per selected Activity;
- separate completion actions per selected Activity;
- separate Outcomes per selected Activity;
- separate Notes per selected Activity.

---

## PD-02 — Outcome is configured tenant data

Outcome is not a hardcoded enum.

Use the approved `Outcomes` Standardized List.

Only active/selectable values are offered for new execution.

Historical records must remain understandable if the catalog value is later renamed, deactivated or deleted.

---

## PD-03 — End Work with active Activity

If an Activity execution is IN_PROGRESS:

- End Work is unavailable in normal UX;
- server-side End Work must reject the action;
- authoritative state must return the active execution;
- reopening the app must return the user to the execution screen.

To leave the execution, the user must use:

- **Complete Activity + Outcome**, or
- **Leave + Outcome**.

Do not auto-close the Activity.

Do not invent an Outcome.

---

## PD-04 — RTE05 closes the ARRIVED lifecycle

RTE04 accepted ARRIVED Trips surviving a Work Session only because Activity execution did not yet exist.

That is no longer the target normal behavior once RTE05 is active.

For a non-HOME operational Trip:

`ARRIVED`

must be resolved through the RTE05 post-arrival flow before the Work Session may end normally.

After a terminal Complete/Leave action with valid Outcome:

`Trip -> CLOSED`

Do not silently close ARRIVED merely because End Work was requested.

Do not backfill or fabricate Activity history for historical RTE04 records that already ended with an ARRIVED Trip.

Historical pre-RTE05 ARRIVED records remain historical facts unless a separately approved correction process is used.

---

# Context Matrix

Preserve the approved separation between pre-trip context and post-arrival execution.

| Trip Context | Pre-trip context already owned by RTE04 | RTE05 post-arrival input |
|---|---|---|
| Client Visit | Destination = free text | **Client Visit Activities**, multi-select 1..N |
| Recruiting | Area / Location = free text | **Recruiting Activities**, multi-select 1..N |
| Employee Visit | Employee / Reference = free text; Employee Visit Reason = pre-trip | Do not add a second Activity catalog merely to duplicate Reason |
| Check Delivery | Employee / Reference = free text; Delivery Type = pre-trip | **Received By**, single, within post-arrival/completion flow |
| Office | Office = free text; Office Purpose = pre-trip | Do not add a second Activity catalog merely to duplicate Purpose |
| Other | Area / Location = free text | **Other Activities**, multi-select 1..N |
| Home | RTE04 | **No Activity. No RTE05 execution block.** |

### Important

Do not move the RTE04 pre-trip fields to Arrived.

Do not create new post-arrival selectors for Employee Visit or Office just to make every context look identical.

The Mobile flow may reuse one execution component internally, but the product must remain context-aware.

---

# Functional Requirements

## FR-01 — Arrival routing

When a non-HOME Trip reaches ARRIVED:

- current state must identify that post-arrival work is unresolved;
- Mobile must route the user into the correct arrival/execution context;
- the user must not be dropped back into a generic "Where to next?" state while the current Trip remains unresolved.

HOME continues to return to normal active-session flow because its Trip is already CLOSED.

---

## FR-02 — Activity selection for Client Visit / Recruiting / Other

For:

- Client Visit;
- Recruiting;
- Other;

the user must select **at least one** active configured Activity before Start Activity.

Allow 1..N selections.

Use the correct list:

- Client Visit Activities;
- Recruiting Activities;
- Other Activities.

Do not mix values across list codes.

Inactive/deleted values must not be offered for new selection.

---

## FR-03 — Employee Visit

Employee Visit already carries its approved pre-trip `Employee Visit Reason`.

Do not require another post-arrival Activity selector unless an existing approved baseline explicitly contains one.

The user must still enter the common execution block so duration, Outcome, Notes and terminal action are recorded.

---

## FR-04 — Office

Office already carries its approved pre-trip `Office Purpose`.

Do not require another post-arrival Activity selector merely to duplicate the Purpose.

The user must still enter the common execution block so duration, Outcome, Notes and terminal action are recorded.

---

## FR-05 — Check Delivery

Check Delivery already carries its approved pre-trip `Delivery Type`.

RTE05 must support `Received By` using the approved Standardized List.

`Received By` is a post-arrival field and must not be moved to pre-trip.

Preserve the existing V0.7 required/optional behavior if it is explicitly represented in the approved baseline/code.

If requiredness is not evidenced and implementation cannot proceed without deciding it, classify `DECISION REQUIRED` and STOP rather than inventing a new rule.

Outcome remains the common terminal Outcome.

---

## FR-06 — Start Activity

Starting execution must:

- require an ARRIVED non-HOME Trip;
- validate required context-specific post-arrival input;
- create or activate only one execution block for that Trip;
- record actual occurrence time;
- preserve separate server receipt/provenance if the existing command pattern supports it;
- be idempotent;
- reject duplicate/concurrent starts deterministically;
- return authoritative execution state.

For Activity-list contexts, the selected 1..N Activities are fixed for that execution once started unless an explicitly approved pre-start edit flow already exists.

Do not permit silent mutation of selected Activities after execution begins.

---

## FR-07 — Execution screen

While execution is active, Mobile must clearly show the current stop/execution context.

At minimum preserve:

- Trip context/destination/reference;
- selected Activity names where applicable;
- execution started state;
- elapsed/duration presentation where supported;
- Complete Activity;
- Leave.

Do not expose Admin configuration controls.

Reload, navigation return, reauthentication and device transfer must restore this execution rather than create another one.

---

## FR-08 — Complete Activity

Complete Activity initiates the existing completion flow.

Before terminalization, require:

- valid Outcome;
- any context-specific post-arrival field that is required by the approved baseline;
- Notes remain optional unless an approved rule says otherwise.

On successful completion:

- execution becomes terminal;
- end occurrence time is stored;
- duration is persisted/derivable from the one start/end pair;
- Outcome is persisted;
- Notes are persisted if supplied;
- terminal action is distinguishable as Complete;
- associated Trip becomes CLOSED;
- Work Session remains ACTIVE;
- Mobile returns to the normal active-session / "What's next?" flow.

---

## FR-09 — Leave

Leave is a controlled terminal path, not an abandonment.

Before terminalization:

- require Outcome;
- capture optional Notes;
- preserve any required context-specific post-arrival input.

On success:

- execution becomes terminal;
- terminal action is distinguishable as Leave;
- duration is preserved;
- associated Trip becomes CLOSED;
- Work Session remains ACTIVE.

Do not treat Leave as a crash, auto-close or missing Outcome path.

---

## FR-10 — Outcome

Outcome:

- comes from active tenant `Outcomes`;
- is required for both Complete and Leave;
- is not inferred automatically;
- is not generated by AI;
- must remain historically readable if the configured value later changes.

Do not hardcode the four seeded labels as an application enum.

---

## FR-11 — Notes

Notes are optional.

Preserve them with the execution historical fact.

Apply normal input validation and safe rendering.

Do not make Notes mandatory to compensate for missing structured data.

---

## FR-12 — Trip closure

For non-HOME operational Trips:

- no Activity execution terminalization -> Trip remains unresolved;
- valid Complete/Leave + Outcome -> Trip CLOSED.

Trip closure and Activity terminalization must be atomic enough that the system cannot persist:

- terminal Activity with non-closed Trip due to ordinary partial failure; or
- closed Trip with missing required terminal execution facts.

Use the repository's existing transaction/idempotency conventions.

---

# End Work Integration

## FR-13 — End Work from ARRIVED with unresolved RTE05 work

Once RTE05 is active, a non-HOME Trip in ARRIVED with unresolved post-arrival work must block normal End Work.

Expected behavior:

- UI directs the user back to the arrival/execution flow;
- server rejects End Work;
- authoritative state identifies the unresolved Trip/execution state;
- no Trip is silently closed;
- no Activity is fabricated;
- no Outcome is invented.

This closes the temporary RTE04 lifecycle gap for new RTE05 operation.

---

## FR-14 — End Work while execution IN_PROGRESS

Preserve D-07:

- End Work unavailable in UX;
- server rejects it;
- restore active execution;
- exit requires Complete or Leave + Outcome.

---

## FR-15 — End Work after Activity terminalization

Once the execution is terminal and its Trip is CLOSED:

- the Work Session remains ACTIVE;
- user may continue with another Trip or End Work subject to existing RTE04 odometer/end-work rules.

Do not bypass END odometer or any other certified RTE04 blocker.

---

# Current-State Contract

Extend the existing authoritative current-state contract rather than creating an independent competing state endpoint.

It must be sufficient for the client to determine, at minimum:

- active Work Session;
- current/non-terminal Trip;
- Trip context/state;
- whether post-arrival work is unresolved;
- active execution if one exists;
- selected Activities where applicable;
- start occurrence time;
- terminalization pending state if applicable;
- what the client should resume.

Avoid exposing internal Admin-only data.

Do not duplicate Work Session/Trip truth in client state.

---

# Data Model Impact

Exact schema design is delegated, but the domain must preserve the following facts.

## Execution block

Conceptually requires:

- tenant/company;
- Work Session;
- Trip;
- Supervisor/user;
- execution state;
- start occurrence timestamp;
- server receipt/provenance where consistent with existing command patterns;
- terminal occurrence timestamp;
- terminal action: Complete or Leave;
- duration or sufficient immutable facts to derive it;
- Outcome reference + historical representation;
- Notes;
- version/concurrency metadata as needed;
- audit timestamps.

## Selected Activities

For multi-select contexts, preserve 1..N selected Standardized Values associated with the execution block.

Historical readability must survive later:

- rename;
- deactivate;
- delete/tombstone

of the configured list value.

Use the existing project's historical-reference/snapshot conventions rather than fragile live-name dependency.

## Check Delivery

Preserve post-arrival `Received By` in the historical execution/stop context using the same history-safe principle.

Do not duplicate Delivery Type, which already belongs to the Trip plan.

---

# API / Commands

Remain API-first.

Required capabilities/commands conceptually include:

- obtain authoritative current state including execution;
- obtain active post-arrival Standardized Values through existing read contract;
- Start Activity execution;
- Complete Activity with Outcome / Notes / applicable post-arrival fields;
- Leave with Outcome / Notes / applicable post-arrival fields.

Exact endpoint naming is delegated.

Prefer command semantics over exposing the execution block as unrestricted CRUD.

All mutations must be:

- tenant-safe;
- server-authorized;
- idempotent where client retry/replay is possible;
- concurrency-safe;
- auditable.

Do not create a new parallel Standardized Values API.

---

# Offline / Reconnect

Activity commands are deterministic non-binary operational commands and should reuse the established durable queue pattern where technically applicable.

At minimum validate:

- queued Start Activity preserves occurrence time;
- queued Complete/Leave preserves occurrence time;
- command order is preserved;
- replay is idempotent;
- permanent 4xx leaves the queue and returns the authoritative error/state;
- network/5xx may retry;
- reauthentication does not discard valid pending commands;
- a stale queued action cannot close a different/current execution after state has moved on.

Do not create a second offline framework.

If a specific Activity command cannot safely participate in the existing queue, document the exact reason and classify it rather than silently degrading behavior.

---

# Roles & Permissions

## Administrador

May:

- use My Route;
- execute Activity flow;
- read operational Standardized Values;
- use approved CER Route Admin functions.

## Supervisor

May:

- use My Route;
- execute Activity flow;
- read required operational Standardized Values.

Must not:

- create/edit/delete/reorder Standardized Values;
- approve Admin exceptions;
- adjust historical records;
- manage users/vehicles/configuration.

No new Supervisor Manage capability may be introduced for RTE05.

If a new read capability is genuinely required, explain why the existing `route.standardvalues.read` or current operational contract cannot satisfy it before adding one.

---

# Security / Audit

Validate:

- tenant isolation;
- same-tenant user isolation where applicable;
- server-side authorization;
- minimum privilege;
- no frontend-only guards;
- safe Notes rendering/input handling;
- immutable terminal facts for ordinary users;
- audit for start, complete, leave and relevant changes;
- actor, tenant, Trip, Work Session and timestamps traceable;
- old/new values where an approved mutable action exists;
- no cross-tenant Standardized Value IDs accepted;
- no inactive/deleted value accepted for a new execution merely by direct API submission.

---

# Historical Integrity

RTE05 must not reinterpret historical RTE04 records.

Specifically:

- do not auto-create Activity executions for old ARRIVED Trips;
- do not auto-close old ARRIVED Trips;
- do not fabricate Outcome/Notes;
- do not alter old Work Session `ended_at`.

If CER later wants to correct historical records, that belongs to the approved Admin correction/audit mechanism, not this checkpoint.

---

# Edge Cases

Validate at minimum:

1. Arrive Client Visit -> select one Activity -> complete.
2. Arrive Client Visit -> select multiple Activities -> one execution block.
3. Recruiting -> multiple Activities -> Leave + Outcome.
4. Other -> multiple Activities -> Complete + Outcome.
5. Employee Visit -> no redundant post-arrival Activity selector.
6. Office -> no redundant post-arrival Activity selector.
7. Check Delivery -> post-arrival Received By preserved.
8. HOME -> no Activity flow.
9. Start with zero Activities in a multi-select context -> rejected.
10. Direct API supplies Activity from wrong list -> rejected.
11. Direct API supplies inactive/deleted Activity -> rejected.
12. Complete without Outcome -> rejected.
13. Leave without Outcome -> rejected.
14. Notes omitted -> accepted.
15. Duplicate Start retry -> one execution.
16. Concurrent Start from two devices -> one authoritative execution.
17. Duplicate Complete replay -> no duplicate closure/audit corruption.
18. Complete vs Leave concurrently -> one terminal result.
19. Reload while IN_PROGRESS -> execution restored.
20. Reauth while IN_PROGRESS -> execution restored.
21. Second device -> same execution, not another block.
22. End Work while ARRIVED unresolved -> rejected.
23. End Work while IN_PROGRESS -> rejected.
24. After Complete/Leave -> Trip CLOSED, session ACTIVE.
25. New Trip allowed only after prior Trip is CLOSED.
26. Catalog value renamed/deactivated/deleted after historical use -> history remains readable.
27. Stale queued Complete/Leave cannot affect a later execution.
28. Cross-tenant selected value -> rejected/non-disclosing.

---

# Acceptance Criteria

RTE05 may be proposed as complete only if all applicable criteria are evidenced.

## Arrival / execution

- non-HOME ARRIVED restores the post-arrival flow;
- HOME bypasses RTE05;
- context-specific inputs match the approved matrix;
- multi-select contexts require 1..N;
- one execution block is created;
- no duplicate execution from retry/concurrency.

## Execution block

- exactly one start;
- exactly one terminal action;
- one duration;
- one Outcome;
- one optional Notes;
- multi-selected Activities do not create independent timers/outcomes.

## Complete / Leave

- both require Outcome;
- both preserve terminal action;
- both close the Trip;
- neither ends the Work Session;
- normal next-trip flow becomes available after closure.

## End Work

- unresolved ARRIVED blocks;
- IN_PROGRESS blocks;
- no auto-close;
- no invented Outcome;
- after Trip CLOSED, existing RTE04 End Work rules apply.

## Standardized Values

- correct list per context;
- active values only for new operation;
- wrong-list/cross-tenant/inactive/deleted direct API submissions rejected;
- Supervisor can read but not manage;
- historical labels remain readable.

## State continuity

- reload resumes correctly;
- reauth resumes correctly;
- second device resolves same execution;
- current-state is authoritative;
- offline queue/replay does not create duplicate or stale terminal actions.

## Security / audit

- tenant isolation;
- authorization server-side;
- audit for lifecycle;
- Supervisor remains Read + Execute only;
- terminal historical facts are not ordinary-user editable.

## Regression

- RTE02-A02 remains green;
- RTE03 remains green;
- RTE04 remains green;
- no RTE06+ functionality introduced.

---

# Tests Required

Run controlled backend and browser suites and report actual counts/exits.

## Backend

At minimum cover:

- execution state/invariants;
- multi-select association;
- context/list validation;
- Outcome validation;
- Received By validation according to approved baseline;
- Complete/Leave atomicity with Trip close;
- ARRIVED End Work guard;
- IN_PROGRESS End Work guard;
- current-state execution envelope;
- idempotency;
- concurrent start;
- concurrent terminal action;
- occurrence timestamps;
- offline replay ordering where supported;
- stale command rejection;
- tenant isolation;
- same-tenant actor isolation where applicable;
- inactive/deleted value rejection;
- historical readability after catalog lifecycle;
- audit;
- RTE02-A02 access regression;
- RTE03 Work Session regression;
- RTE04 Trip/Odometer regression.

## Browser

At minimum validate these journeys in the production frontend bundle:

1. Supervisor — Client Visit, two Activities, Complete + Outcome.
2. Supervisor — Recruiting, multiple Activities, Leave + Outcome.
3. Supervisor — Employee Visit, no redundant Activity selector, Complete.
4. Supervisor — Check Delivery, post-arrival Received By, Complete.
5. Supervisor — Office, no redundant Activity selector, Complete.
6. Supervisor — Other, multiple Activities, Complete.
7. HOME — no Activity.
8. Reload active execution and resume.
9. Reauth/device continuity for active execution.
10. End Work blocked from unresolved ARRIVED.
11. End Work blocked from IN_PROGRESS.
12. Trip becomes CLOSED after Complete.
13. Trip becomes CLOSED after Leave.
14. Session remains ACTIVE after terminal execution.
15. Administrador executes an RTE05 operational journey.
16. Supervisor cannot access catalog management.
17. Wrong/inactive value rejected through API-backed UI path where practical.
18. Offline/reconnect execution command path where supported.

Use Mobile viewport validation consistent with the existing CER Route test approach.

Real iOS/Android hardware may remain `PENDING VALIDATION` unless actually tested, but must be reported honestly.

---

# Expected -> Implemented -> Evidence -> Gap

The delivery report must compare every material area using:

| Expected | Implemented | Evidence | Classification / Gap |
|---|---|---|---|

Allowed classifications:

- AS-BUILT / CONFIRMED
- PARTIAL
- PENDING VALIDATION
- NOT IMPLEMENTED / GAP
- DEVIATION
- UNAUTHORIZED DECISION
- TECHNICAL DEBT
- DECISION REQUIRED

Do not use "Completed" as a substitute for evidence.

---

# Do Not Change

Do not change without CER approval:

- RTE02-A02 role model;
- RTE03 Work Session lifecycle;
- RTE04 Trip lifecycle before ARRIVED;
- HOME direct close;
- Change Plan timing;
- odometer rules;
- END Option B;
- Routing Mileage definition;
- location/GPS decisions;
- the 28 approved Standardized Values;
- free-text context decisions;
- Outcome as tenant-configured data;
- multi-Activity = one execution block;
- one Outcome / Notes per block;
- D-07 End Work protection;
- D-10 occurrence-time semantics;
- Core/Foundation role model.

---

# Deliverables

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE05_DELIVERY_REPORT_001.md`

The report must include:

1. exact scope implemented;
2. files/components/APIs/data changed;
3. execution state model as-built;
4. context matrix as-built;
5. multi-select evidence;
6. one-block semantics evidence;
7. Complete evidence;
8. Leave evidence;
9. Outcome/Notes evidence;
10. Check Delivery Received By behavior;
11. Trip ARRIVED -> CLOSED evidence;
12. End Work guard evidence;
13. current-state/resume evidence;
14. offline/replay evidence;
15. concurrency/idempotency evidence;
16. roles/permissions evidence;
17. tenant isolation;
18. audit evidence;
19. historical catalog-change evidence;
20. backend test counts;
21. browser test counts;
22. typecheck/lint/build status;
23. Expected -> Implemented -> Evidence -> Gap;
24. pending real-device/mobile validation;
25. confirmation RTE02-A02/RTE03/RTE04 behavior remains intact;
26. confirmation no RTE06+ scope was started;
27. proposed status.

Use unique incremental filenames for any subsequent report.

---

# Checkpoints

## RTE05-C1 — Activity Domain + Authoritative State
- execution block model/invariants;
- selected Activity association;
- current-state extension;
- tenant/security boundaries;
- no duplicate active execution.

## RTE05-C2 — Context-Specific Arrival UX
- Client Visit multi-select;
- Recruiting multi-select;
- Other multi-select;
- Employee Visit no duplicate selector;
- Office no duplicate selector;
- Check Delivery Received By;
- HOME bypass.

## RTE05-C3 — Start + Resume Execution
- Start Activity;
- one-block semantics;
- reload;
- reauth;
- second device;
- occurrence time;
- idempotency/concurrency.

## RTE05-C4 — Complete / Leave + Outcome + Trip Closure
- Outcome;
- optional Notes;
- Complete;
- Leave;
- Trip CLOSED;
- session remains ACTIVE;
- historical integrity.

## RTE05-C5 — End Work Integration + Offline + Final Validation
- unresolved ARRIVED guard;
- IN_PROGRESS guard;
- queue/replay;
- stale command protection;
- security/audit;
- browser journeys;
- regression;
- delivery report.

---

# STOP Conditions

STOP and return to CER if:

- implementation requires changing the certified RTE04 Trip state model before ARRIVED;
- a new post-arrival catalog is required for Employee Visit or Office;
- Check Delivery `Received By` requiredness cannot be established from the approved baseline and blocks implementation;
- multiple selected Activities cannot be represented as one execution block without changing an approved prior decision;
- closing a Trip would require fabricating Activity/Outcome facts;
- End Work behavior requires a new product decision beyond the rules above;
- a new Supervisor Manage/Admin capability appears necessary;
- RTE05 requires GPS, routing mileage, fuel, Reports or other later scope;
- offline behavior requires a second queue architecture;
- historical RTE04 records would need automatic rewriting;
- a new product decision is required.

After RTE05-C5 and the delivery report:

# STOP

Do not begin the next Route checkpoint until CER reviews and certifies RTE05.
