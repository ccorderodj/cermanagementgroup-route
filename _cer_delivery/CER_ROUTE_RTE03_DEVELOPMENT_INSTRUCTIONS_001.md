# CER Route — RTE03 Development Instructions

**Checkpoint:** RTE03 — Supervisor Work Session  
**Instruction delivery:** 001  
**Roadmap position:** RTE02 → **RTE03** → RTE04  
**Current RTE02 baseline:** `Report Delivery Rodrigo/CER_ROUTE_RTE02_DELIVERY_REPORT_002.md`  
**Authoritative product/technical baseline:** `Report Delivery Rodrigo/CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_001.md`  
**Target:** `Completed — ready for CER certification`  
**Do not start RTE04.**

---

# 1. Context

RTE03 is the approved roadmap checkpoint for the **Supervisor Work Session**.

Its purpose is to make the Supervisor workday real before Trip lifecycle is introduced.

RTE02 already provides:

- CER Route product identity;
- tenant-aware Core authentication and authorization;
- Supervisor and Route Admin roles;
- Mobile-only Supervisor shell;
- Route Admin configuration;
- Core User management;
- Route Supervisor designation/profile;
- Vehicle master;
- effective-dated Supervisor ↔ Vehicle assignments;
- the eight tenant-configurable Standardized Lists;
- audit, tenant isolation and concurrency patterns.

RTE03 must build on those foundations and introduce the first operational Route entity:

`Work Session`

The approved roadmap sequence is:

`RTE02 Application Foundation + Access Model`
→ `RTE03 Supervisor Work Session`
→ `RTE04 Trip Lifecycle`

RTE03 must **not** pre-build Trip, Activity, location or mileage behavior.

---

# 2. Objective

At RTE03 completion, a Route Supervisor must be able to:

1. open CER Route on Mobile;
2. see whether there is already an active Work Session;
3. execute **Start Work**;
4. have exactly one authoritative active Work Session;
5. close/reopen/resume the application and recover the same current Work Session;
6. resume the same active Work Session from another device without creating a second session;
7. execute **End Work** when no later-domain blocker exists;
8. preserve the correct start date even when the session crosses midnight;
9. retain the vehicle/MPG context applicable at Start Work;
10. survive authentication expiry / reauthentication without losing Work Session continuity;
11. preserve accepted Start/End actions through temporary loss of connectivity using the approved durable/offline action approach;
12. produce an auditable historical Work Session record.

RTE03 does **not** implement travel.

A valid completed Work Session may contain **zero Trips**.

---

# 3. Confirmed Requirements

## 3.1 Work Session lifecycle

The Work Session state machine in RTE03 is:

`none → ACTIVE → ENDED`

### Start Work

`Start Work`:

- creates the Work Session;
- does **not** create a Trip;
- does **not** create an Activity;
- does **not** fabricate travel;
- captures the applicable Vehicle/MPG snapshot if one exists;
- establishes `session_date` once;
- records the real event chronology/provenance required by the approved time model.

### End Work

In RTE03 there are no Trips or Activities yet.

Therefore an otherwise valid active Work Session may transition:

`ACTIVE → ENDED`

through End Work.

Future RTE04/RTE05 domain blockers must be designed for extension, but **must not be simulated in RTE03**.

Do not implement fake:

- “Trip in transit” review;
- Activity blocker;
- End Work Anyway;
- Continue Working.

Those rules become operational only when those domains exist.

---

# 4. One Active Work Session

A Supervisor may have **at most one ACTIVE Work Session**.

This must be enforced at the strongest appropriate persistence layer, not only by a Python/application pre-check.

Expected behavior:

- first Start Work succeeds;
- repeated Start Work while ACTIVE does not create a second session;
- server returns the authoritative existing active session / conflict contract consistent with repository conventions;
- concurrent Start Work requests cannot create two active sessions;
- another device never creates a second active Work Session.

The database must make the invalid state impossible.

---

# 5. Work Session Without Trip

**Confirmed Requirement A-1.**

A Work Session is independent of Trip creation.

Valid cases include:

- Supervisor starts work and performs no travel;
- Supervisor starts work before later deciding to travel;
- Supervisor ends a Work Session with zero Trips.

RTE03 must have a named test proving:

> Start Work followed by End Work produces a valid Work Session with zero Trips and no artificial Trip row.

RTE03 must not create the Trip table merely to prove this.

---

# 6. Vehicle and MPG Snapshot

RTE02 established:

- Vehicle master;
- Supervisor assignment history;
- current Vehicle derived from the open assignment;
- a Supervisor with no Vehicle assignment is a valid configuration state.

RTE01 established that historical fuel estimates must not change when a Vehicle's `operational_mpg` changes.

Therefore the Work Session must retain the applicable vehicle context at Start Work.

At minimum the session model must support:

- Vehicle reference used at Start Work, when one exists;
- `mpg_snapshot` captured at Start Work, when one exists.

The Work Session must never recalculate its historical MPG snapshot from the current Vehicle master later.

## 6.1 No current Vehicle

Do not invent a rule that a Work Session requires travel.

A Supervisor with no current Vehicle assignment may still have a valid Work Session.

For such a session:

- Vehicle reference may be null;
- MPG snapshot may be null;
- Start Work remains valid;
- no travel/mileage behavior is implied.

Future Trip rules may impose additional requirements when actual travel begins. That belongs to RTE04+, not RTE03.

## 6.2 Assignment changes during an active session

The session snapshot is historical.

If Admin changes the Supervisor's Vehicle Assignment after Start Work:

- the already-active Work Session keeps the Vehicle/MPG snapshot captured at Start Work;
- do not silently replace it mid-session;
- the new assignment applies to a future Work Session unless a later explicit CER rule says otherwise.

---

# 7. Time / Timezone — D-10

The approved product rule is:

> A Work Session belongs to the **local calendar date at Start Work**, even if it ends after midnight.

Required behavior:

- every event stores enough time/offset context to reconstruct chronology;
- `session_date` is computed once at Start Work;
- `session_date` is never recomputed at End Work;
- crossing midnight never creates a second Work Session automatically;
- the Supervisor never chooses a timezone;
- there is no timezone catalog;
- time handling never blocks Start Work or End Work.

The development team owns the exact technical implementation.

The RTE01 recommendation may be used as guidance:

- timezone-aware timestamps;
- device UTC offset/event context;
- server receipt/order context;
- server remains authoritative for ordering;
- device timestamp is evidence and must not be blindly trusted.

The final implementation decision must be documented in the RTE03 report.

---

# 8. Authentication Continuity — D-09

RTE03 is the first checkpoint where an operational session may stay active for many hours.

The product requirement is:

> Authentication expiry must not cause the active Work Session to disappear, duplicate, reset or become unrecoverable.

Before hardening RTE03, inspect the current Core authentication implementation and determine the cleanest solution.

CER does **not** prescribe refresh-token mechanics.

The team must design and document the technical solution for:

- credential/session renewal or reauthentication;
- active Work Session recovery after auth expiry;
- revocation behavior;
- minimum privilege;
- secure recovery of pending offline actions;
- mobile UX.

Acceptance is behavioral:

- after authentication interruption and valid reauthentication, the Supervisor returns to the same active Work Session;
- no duplicate Work Session is created;
- accepted pending actions remain recoverable according to the offline durability model;
- an invalid/revoked identity cannot continue executing protected actions merely because a local session exists.

Do not weaken Core authentication to achieve continuity.

---

# 9. Capability / Authorization

RTE03 activates the previously certified capability:

`route.worksession.execute`

This capability now has real protected endpoints and must therefore be registered according to repository permission-catalog invariants.

Grant it to the **Supervisor** role.

Do not grant it merely because a user can access Admin.

A Route Admin who must also act as a field Supervisor must receive authorization through the repository's supported role/access model; do not silently make all Route Admins field executors.

Server-side rules:

- only an authenticated, authorized tenant member may execute Work Session actions;
- the session always belongs to the authenticated Supervisor;
- the client never supplies another Supervisor identity as authority;
- a Supervisor cannot execute or mutate another Supervisor's Work Session;
- cross-tenant reads/writes must not leak existence;
- platform-superuser boundaries remain unchanged.

---

# 10. Data Model Impact

Implement the `work_session` domain.

The exact physical model is delegated to Development, but it must represent the approved semantics.

Expected minimum information:

- `id`;
- `company_id`;
- authoritative Supervisor/User relationship;
- `status` (`ACTIVE`, `ENDED` or repository-normalized equivalents);
- `session_date`;
- Start Work occurrence/context;
- End Work occurrence/context;
- `started_at`;
- `ended_at` nullable while ACTIVE;
- time/offset provenance required by D-10;
- Vehicle reference snapshot, nullable;
- `mpg_snapshot`, nullable;
- optimistic-concurrency/version metadata where appropriate;
- audit-compatible identifiers/timestamps.

Use `BusinessEnum` / database CHECK according to Foundation conventions.

## 10.1 Required database invariant

Enforce one ACTIVE Work Session per Supervisor with a database-level constraint, expected to be a partial unique index or an equivalent repository-approved mechanism.

Do not rely on:

`SELECT first → if none → INSERT`

as the sole guarantee.

## 10.2 Tenant-safe references

All references must preserve tenant isolation at the database/API layers according to the patterns established in RTE02.

Do not add duplicate identity fields.

---

# 11. API / Contracts

RTE03 is API-first.

The exact route layout may follow repository conventions, but the expected contract includes at minimum:

### Current state

`GET /api/.../worksessions/current`

Purpose:

- authoritative current Supervisor Work Session;
- returns no active session or the active session;
- later checkpoints can extend the response with open Trip / Activity state without breaking the contract;
- client renders from this state rather than trusting stale local UI state.

### Start Work

`POST /api/.../worksessions`

Purpose:

- create ACTIVE Work Session;
- snapshot applicable Vehicle/MPG;
- establish immutable `session_date`;
- support idempotent replay where required by offline handling.

### End Work

`POST /api/.../worksessions/{id}/end`

Purpose:

- end the authenticated Supervisor's ACTIVE Work Session;
- idempotent/replay-safe according to the selected action contract;
- cannot mutate another user's session.

If additional read endpoints are technically necessary for the RTE03 UI or tests, keep them narrow and document why.

Do not add Admin reporting/history APIs merely because Work Sessions now exist; broader Today/Live/Reports belong later.

---

# 12. State Restoration

`GET /worksessions/current` is the server source of truth.

On:

- app open;
- app resume;
- reconnect;
- valid reauthentication;
- device transfer;

the Supervisor experience must reconcile against the server.

RTE03 response only needs the domain currently implemented:

- active Work Session;
- applicable current session context;
- next legal Work Session-level actions.

Do not fake future open Trip or Activity data.

Design the response so RTE04/RTE05 can extend it cleanly without creating a second competing “current state” endpoint.

---

# 13. Multiple Devices — A-6

CER's approved rule:

> A second device resumes/transfers the same active Work Session; it never creates a second Work Session.

RTE03 must establish this at Work Session level.

Required behavior:

- Device B opens while Device A has an ACTIVE session;
- Device B retrieves the same authoritative session;
- no duplicate session is created;
- actions from either device are subject to the same server state;
- replay/idempotency prevents duplicated state changes.

Do not introduce visible “device ownership” of the Work Session unless technically necessary.

The exact transfer/session-token mechanism is delegated.

---

# 14. Offline / Durable Action Foundation

RTE01 explicitly identified offline action durability as required for the field workflow and scheduled it into RTE02/RTE03.

RTE03 must establish the reusable offline action foundation for the Supervisor operational flow.

At this checkpoint it only needs to support RTE03 actions:

- Start Work;
- End Work;
- current-state reconciliation.

Do not implement Trip/Activity queue actions yet.

Required properties:

### Durability

An action the UI reports as accepted must first be committed to the selected durable local storage mechanism.

### Idempotency

Replaying the same queued action must not create a second state transition.

Use the Foundation's existing idempotency mechanism where appropriate instead of creating a parallel framework.

### Ordering

Queued Work Session actions must reconcile in a deterministic order.

### Recovery

Pending actions must survive the supported app lifecycle conditions and remain recoverable after reconnect / valid reauthentication.

### Honest boundaries

Do not claim absolute durability against:

- user clearing site data;
- browser storage eviction;
- uninstall;
- device loss/destruction.

The implementation/report must state real boundaries.

The exact browser storage/service-worker mechanism is a technical choice.

---

# 15. Supervisor Mobile UX

Replace the RTE02 `NotBuiltYet` behavior for **My Route** only to the extent required by RTE03.

## No active session

The Supervisor sees a clear primary action:

`Start Work`

Keep the V0.7 interaction principle:

- mobile-first;
- one primary action;
- minimal text;
- no table;
- no Admin chrome.

## Active session

Show enough real information to orient the Supervisor:

- workday active state;
- Start Work time / date as appropriate;
- current/started Vehicle context if applicable;
- an `End Work` action;
- a clear placeholder/disabled continuation for Trip functionality only if needed to avoid dead-end UX.

Do not implement a fake Trip flow.

## Ended

After End Work:

- UI reconciles to no current active session;
- next normal state again allows Start Work;
- historical session does not disappear from persistence.

Do not introduce desktop Supervisor experience.

---

# 16. Location Is Out of Scope in RTE03

Although Start Work and End Work will later carry location evidence, RTE03 does **not** implement geolocation.

Therefore RTE03 must not create:

- `location_fix`;
- `missing_location_event`;
- GPS permission UX;
- Recovery Window;
- breadcrumbs;
- background location;
- location notifications.

Design Work Session events so later location evidence can attach without destructive redesign.

Do not fabricate temporary coordinates or mock GPS data.

---

# 17. End Work Boundary for Future Domains

RTE01 defines important future End Work rules when a Trip or Activity exists.

RTE03 must preserve extension points but not implement fake future-domain behavior.

When RTE04/RTE05 introduce those domains, End Work will eventually need to enforce:

- Trip `IN_TRANSIT` review;
- Continue Working;
- explicit End Work Anyway;
- Activity `IN_PROGRESS` rejection;
- no fabricated Arrived or Outcome.

For RTE03:

- there is no Trip/Activity table;
- therefore these blockers cannot exist;
- a valid ACTIVE Work Session can simply end.

Do not hardcode the Work Session service in a way that makes later blockers impossible to add cleanly.

---

# 18. Audit

Audit at minimum:

- Work Session created / Start Work;
- Work Session ended / End Work;
- any security-sensitive state correction if technically introduced;
- relevant auth/session continuity events only if they belong in the existing Core audit model.

Audit must preserve:

- actor;
- tenant;
- target Work Session;
- action;
- timestamp/context;
- relevant state transition.

Do not record secrets/tokens.

Do not create a second audit system.

---

# 19. Edge Cases

Cover at minimum:

1. Supervisor presses Start Work twice.
2. Two concurrent Start Work requests.
3. Two devices start/resume simultaneously.
4. Supervisor has no Vehicle assignment.
5. Admin changes Vehicle assignment after session start.
6. Vehicle master MPG changes after session start.
7. Session crosses midnight.
8. Start Work near UTC/local date boundary.
9. Daylight-saving transition.
10. Device clock is skewed.
11. Authentication expires while Work Session is ACTIVE.
12. Reauthentication restores same session.
13. End Work replayed twice.
14. End Work for another Supervisor's session.
15. Cross-tenant session id supplied directly.
16. Offline Start Work queued and later synchronized.
17. Offline End Work queued and later synchronized.
18. Replayed queued action.
19. Out-of-order Start/End action delivery.
20. Supervisor role/capability removed while an active session exists.
21. User access suspended while an active session exists.
22. Work Session with zero Trips completes successfully.
23. Vehicle assignment missing does not create fake Vehicle/MPG.
24. No geolocation row/domain is created by RTE03.

For permission revocation/suspension, prioritize security: an existing historical ACTIVE record may remain in the database, but revoked credentials must not continue authorizing new protected operations.

Document the operational recovery implications rather than bypassing authorization.

---

# 20. Tests Required

Create named tests aligned with repository conventions.

At minimum prove:

## Work Session persistence

- one ACTIVE session per Supervisor is database-enforced;
- zero-Trip session is valid;
- Start Work stores the correct tenant/Supervisor;
- End Work closes the correct session;
- historical session remains after End Work.

## Vehicle snapshot

- current assignment is resolved at Start Work;
- Vehicle reference snapshot is retained;
- MPG snapshot is retained;
- later Vehicle MPG change does not alter the session snapshot;
- later reassignment does not alter an already-started Work Session;
- no Vehicle produces null snapshot values without blocking Start Work.

## Time

- Friday 20:00 → Saturday 00:41 remains Friday `session_date`;
- local date, not UTC date, governs `session_date`;
- session_date is immutable after Start Work;
- DST boundary does not create a second day/session;
- skewed device time does not corrupt authoritative ordering.

## Authorization

- Supervisor with `route.worksession.execute` can execute own session;
- user without capability cannot;
- Supervisor cannot mutate another Supervisor's session;
- cross-tenant direct id returns repository-standard not-found behavior;
- capability removal prevents new protected actions.

## Concurrency

- two simultaneous Start Work requests create only one ACTIVE session.

## Current-state restoration

- no active session returns the correct empty/current state;
- active session returns same session after reopen/reconnect;
- second device resolves same session.

## Auth continuity

- valid reauthentication resumes the same session;
- no duplicate session after auth interruption;
- revoked/suspended identity cannot continue protected actions.

## Offline/idempotency

- accepted queued Start Work survives the selected supported lifecycle test;
- accepted queued End Work survives the selected supported lifecycle test;
- replaying the same idempotency key changes state once;
- out-of-order contradictory actions do not corrupt the state machine.

## Architecture regression

- permission catalog;
- public/private surface;
- page wiring;
- navigation wiring;
- Alembic single head;
- full backend suite;
- frontend typecheck/lint/build.

Use PostgreSQL, not SQLite.

---

# 21. Acceptance Criteria

RTE03 may be proposed for certification only when:

### Domain

- [ ] `work_session` exists as a tenant-scoped Route domain.
- [ ] Start Work creates one ACTIVE Work Session.
- [ ] Start Work creates no Trip.
- [ ] End Work transitions the session to ENDED.
- [ ] A session with zero Trips is valid.
- [ ] historical sessions remain persisted.

### Integrity

- [ ] One ACTIVE session per Supervisor is database-enforced.
- [ ] concurrent Start Work cannot create duplicates.
- [ ] server remains authoritative.
- [ ] replay is idempotent.

### Vehicle

- [ ] applicable Vehicle snapshot is captured when present.
- [ ] MPG snapshot is captured when present.
- [ ] snapshots do not mutate when master/assignment changes.
- [ ] no Vehicle assignment does not block Work Session.

### Time

- [ ] `session_date` is established once at Start Work.
- [ ] midnight crossover remains assigned to start date.
- [ ] Supervisor never configures timezone.
- [ ] DST/skew handling is documented and tested.

### Access

- [ ] `route.worksession.execute` is now a real protected capability.
- [ ] Supervisor role receives the capability.
- [ ] no unauthorized/cross-tenant execution.
- [ ] revoked access does not continue merely because local state exists.

### Mobile

- [ ] My Route uses real Work Session state.
- [ ] Start Work is functional.
- [ ] End Work is functional.
- [ ] reopen/resume restores authoritative session.
- [ ] second device receives same active session.
- [ ] no Supervisor Desktop introduced.

### Continuity

- [ ] auth interruption does not destroy/duplicate the Work Session.
- [ ] offline/durable action foundation exists for Start/End Work.
- [ ] idempotency/reconciliation are proven.
- [ ] durability boundaries are documented honestly.

### Scope

- [ ] no Trip lifecycle implemented.
- [ ] no Activity implementation.
- [ ] no geolocation implementation.
- [ ] no mileage/routing implementation.
- [ ] no Today/Live/Admin operational dashboard.
- [ ] no RTE04+ business behavior started.

### Quality

- [ ] migration is valid.
- [ ] exactly one Alembic head.
- [ ] full backend suite green.
- [ ] frontend checks green.
- [ ] architecture/invariant nets green.
- [ ] audit verified.
- [ ] tenant isolation verified.

---

# 22. Internal Checkpoints

Execute RTE03 in controlled units.

## RTE03-C1 — Auth/time technical closure

Objective:

- inspect current Core authentication;
- finalize and document D-09 implementation;
- finalize and document D-10 implementation;
- establish reusable time/event contract.

Deliverable:

- implementation decision recorded;
- focused tests for auth continuity/time behavior;
- no Work Session UI yet required.

Do not weaken Core security.

---

## RTE03-C2 — Work Session domain + migration

Deliverable:

- Work Session model;
- state enum/constraint;
- tenant-safe relationships;
- one-active partial unique constraint;
- Vehicle/MPG snapshot;
- migration;
- DAO/service;
- audit.

Verification:

- PostgreSQL constraints;
- concurrency;
- midnight/date rules;
- snapshot immutability.

---

## RTE03-C3 — API + capability + authoritative current state

Deliverable:

- `route.worksession.execute` registered and enforced;
- Supervisor role updated;
- Start Work endpoint;
- End Work endpoint;
- `GET current` contract;
- idempotency/replay protections required for Work Session.

Verification:

- permission tests;
- tenant isolation;
- ownership;
- concurrent Start Work;
- current-state restoration.

---

## RTE03-C4 — Supervisor Mobile + offline continuity

Deliverable:

- My Route real Work Session experience;
- Start Work;
- active session state;
- End Work;
- reopen/resume;
- second-device resume;
- durable action foundation for Start/End Work.

Verification:

- no fake Trip behavior;
- offline/reconnect tests;
- auth-recovery tests;
- mobile shell remains separate from Admin.

---

## RTE03-C5 — Regression + closure

Deliverable:

- complete regression;
- Expected vs Implemented;
- technical decisions;
- deviations;
- known risks;
- RTE04 readiness;
- final numbered delivery report.

Do not start RTE04.

---

# 23. V-1 Client Technology Validation

RTE01 requires real-device validation before the Supervisor client technology is considered hardened.

If real iOS and Android devices are available during RTE03:

- execute the relevant V-1 lifecycle tests;
- record device/browser/OS;
- test app resume, suspension, local queue persistence and auth continuity;
- distinguish measured behavior from assumption.

If real devices are not available:

- leave V-1 as `Pending Validation`;
- do not falsely certify device-specific behavior;
- this does not justify silently changing CER's Mobile-only decision.

Do not implement geolocation merely to perform V-1 in this checkpoint.

---

# 24. Repository Workflow — Mandatory

The RTE02 direct-to-`dev` mistake must not repeat.

For RTE03:

1. start from the approved current integration baseline;
2. create a dedicated RTE03 branch before implementation;
3. recommended branch name:
   `feature/rte03-work-session`
4. all RTE03 commits remain on that branch;
5. do not commit RTE03 directly to `dev`;
6. run local validation and full regression on the branch;
7. prepare the CER delivery report;
8. do **not merge RTE03 to `dev` before CER review/certification**, unless CER explicitly instructs otherwise;
9. after CER certification, proceed through the normal MR/merge process.

Do not rewrite shared Git history to achieve this.

The delivery report must state:

- source branch;
- base commit;
- candidate commit;
- MR status;
- whether anything was merged;
- confirmation no direct RTE03 commit was made to `dev`.

---

# 25. Report Delivery Folder

Use only:

`Report Delivery Rodrigo/`

Return:

`Report Delivery Rodrigo/CER_ROUTE_RTE03_DELIVERY_REPORT_001.md`

If CER requests a correction:

- `_002`
- `_003`
- etc.

Never overwrite an earlier report.

Do not leave duplicate report copies at repository root.

---

# 26. Required Delivery Report

The RTE03 report must include:

1. checkpoint/delivery metadata;
2. branch/base/candidate commit;
3. status C1–C5;
4. actual implementation summary;
5. Work Session model;
6. migration and Alembic head;
7. database invariants;
8. Start Work contract;
9. End Work contract;
10. current-state contract;
11. `route.worksession.execute` registration/enforcement;
12. Supervisor role update;
13. Vehicle/MPG snapshot behavior;
14. no-Vehicle behavior;
15. D-09 technical decision and evidence;
16. D-10 technical decision and evidence;
17. mobile UX implemented;
18. multi-device behavior;
19. offline/durable action implementation;
20. idempotency/reconciliation;
21. security/tenant isolation;
22. audit evidence;
23. tests added;
24. exact commands/results;
25. V-1 status;
26. Expected vs Implemented;
27. deviations;
28. risks/debt;
29. explicit confirmation that RTE04 was not started;
30. RTE04 readiness assessment;
31. proposed status.

If complete, propose:

`RTE03 — Completed / Ready for CER Certification`

CER performs final certification.

---

# 27. Do Not Change

Do not reopen or modify:

- RTE01 A-1 through A-8;
- RTE01 D-01 through D-10;
- RTE02 Core User reuse;
- Supervisor profile as thin extension;
- current Vehicle derived from assignment;
- historical Vehicle Assignment model;
- Mobile-only Supervisor V1;
- shared frontend bundle;
- no Supervisor Desktop;
- no odometer;
- no map requirement;
- no ERP dependency;
- no manual Supervisor timezone;
- no artificial Trip at Start Work;
- one Work Session may have zero Trips;
- future Trip/Activity lifecycle rules.

---

# 28. Out of Scope

Do not implement in RTE03:

- Trip table/domain;
- Trip Purpose;
- Start Trip;
- On Route;
- Arrived;
- Change Plan;
- Return Home Trip;
- Activity Block;
- Activity selections;
- Outcomes/Notes execution;
- geolocation;
- GPS permission;
- Recovery Window;
- Missing Location Event;
- routing provider;
- mileage;
- breadcrumbs;
- fuel reference ingestion;
- fuel estimate;
- Today/Live;
- Activity Explorer;
- Reports/export;
- Admin post-close corrections;
- location retention;
- in-platform notification;
- maps;
- odometer;
- Supervisor Desktop;
- CER ERP integration.

---

# 29. Definition of Done

RTE03 is not complete because Start Work and End Work buttons render.

It is complete only when:

- the Work Session is a real tenant-scoped domain;
- one active session is impossible to duplicate;
- Start/End are secure and auditable;
- vehicle/MPG historical context is preserved;
- start-date semantics survive midnight/timezone conditions;
- current state is recoverable after app interruption;
- second-device use resumes rather than duplicates;
- authentication interruption does not destroy continuity;
- the first reusable offline operational action foundation is proven;
- tests and migrations are clean;
- repository workflow is respected;
- no RTE04 scope has leaked in;
- evidence is returned in the numbered delivery report.

**Stop after RTE03 and wait for CER certification.**
