# CER Route — RTE04 Development Instructions 001
## Trip Foundation + Odometer Evidence

**Prerequisites:** RTE03 — COMPLETED / CERTIFIED; RTE02-A01 — COMPLETED / CERTIFIED  
**Required delivery report:** `Report Delivery Rodrigo/CER_ROUTE_RTE04_DELIVERY_REPORT_001.md`

---

## Context

CER Route already has a real tenant-scoped Supervisor Work Session (`Start Work` / `End Work`), authoritative current-state recovery, offline durable actions, idempotency, multi-device reconciliation, vehicle/MPG snapshot, Core Files, audit, RBAC, Route Admin configuration, Vehicles, Supervisor designations, assignments and the eight Standardized Lists.

RTE04 is the first checkpoint that introduces actual displacement inside an active Work Session.

The certified product model distinguishes:

- **Work Session** — the Supervisor's workday;
- **Trip** — a real displacement during that workday;
- **Activity** — what is executed after arriving.

RTE04 implements the **Trip foundation** and the newly approved **Odometer Evidence** capability. It must not collapse Trip and Activity into one object, and it must not redefine Routing Mileage.

The future Activity execution block remains a later checkpoint. RTE04 must leave a clean extension point for it rather than simulating it.

---

## Current State

### Existing components to reuse

Reuse the existing implementation wherever semantically appropriate:

- `work_session` domain and `route.worksession.execute`;
- `GET /worksessions/current` as the authoritative Supervisor recovery contract;
- generic IndexedDB/offline queue and idempotency mechanism delivered in RTE03;
- Work Session occurrence/receipt time semantics from RTE03 closure;
- Supervisor Mobile shell / `RouteMyRoutePage`;
- Vehicle assignment and Work Session vehicle/MPG snapshot;
- Core Files for private odometer photographs;
- Core audit infrastructure;
- Core tenant identity and authorization;
- Standardized Values delivered in RTE02-A01;
- existing Route Admin shell;
- `route.records.adjust` if the existing capability model can own Admin approval of one-time odometer exceptions. If it is not yet active in the catalog, activate the already-approved capability rather than inventing a parallel permission. If a semantic conflict is discovered, STOP and document it before creating a new capability.

Do not duplicate any of these mechanisms.

---

# Objective

After RTE04, a Supervisor with an `ACTIVE` Work Session must be able to:

1. select the reason/context for a real displacement;
2. create a Trip in planning state;
3. satisfy the initial odometer evidence requirement when vehicle travel applies;
4. start the Trip;
5. remain `On Route` while the Trip is in transit;
6. change the plan while in transit without destroying the original intent;
7. arrive and record the Trip as arrived;
8. complete a special HOME Trip directly on `Arrived Home`;
9. recover the same Trip correctly after reload, reconnect, reauthentication or second-device access;
10. follow the approved End Work review behavior when a Trip is still in transit;
11. capture final odometer evidence when ending a workday that actually involved the session vehicle.

RTE04 must also provide the minimal Route Admin capability required to review one-time **manual odometer entry exceptions**.

---

# Scope

RTE04 includes:

- Trip domain foundation;
- Trip Purpose/context selection;
- Trip states and legal transitions;
- Start Trip;
- On Route state;
- Change Plan while in transit;
- Arrived;
- HOME / Arrived Home behavior;
- End Work review behavior for an `IN_TRANSIT` Trip;
- current-state recovery extended with the current Trip and odometer requirement state;
- offline/idempotent Trip transitions;
- Start Odometer evidence;
- End Odometer evidence;
- private photo evidence;
- OCR-assisted reading suggestion;
- Supervisor confirmation/correction of the OCR suggestion;
- one-time manual-entry exception workflow when no photo can be obtained;
- Admin review/approve/reject of odometer exceptions;
- audit, tenant isolation and security for all of the above;
- browser-level evidence for critical Supervisor flows.

---

# Out of Scope

Do **not** implement in RTE04:

- Activity execution block;
- multi-select Activity execution;
- Activity timer/start/complete;
- Outcome/Notes completion flow;
- GPS/geolocation capture;
- GPS permission UX;
- Recovery Window for location;
- Missing Location Event;
- breadcrumbs;
- routing provider integration;
- official Routing Mileage calculation;
- Haversine mileage;
- fuel reference ingestion;
- fuel estimate;
- Today/Live;
- Activity Explorer;
- Reports/export;
- Admin post-close corrections;
- maps;
- route optimization;
- client or employee master-data catalogs;
- mid-session vehicle switching;
- RTE05+ functionality.

Do not create fake placeholders that look like completed Activity/GPS/Mileage functionality.

---

# Confirmed Product Rules — Trip

## 1. Start Work does not create a Trip

`Start Work` continues to create only the Work Session.

A Trip is created only when the Supervisor actually begins a displacement.

A Work Session with zero Trips remains valid.

Do not regress RTE03 by creating an automatic or artificial Trip on Start Work.

---

## 2. Trip Purpose is not Activity

Trip Purpose/context answers **why the Supervisor is moving**.

Activity answers **what was actually performed after arrival**.

Do not combine these concepts in the data model, API or UI.

The system-defined Route contexts remain:

- Client Visit;
- Recruiting;
- Employee Visit;
- Check Delivery;
- Office;
- Other;
- HOME / Return Home as the special terminal travel context.

Do not make these tenant-created dynamic Activity Types.

The existing V0.7 Updated flow remains authoritative for the timing of each context field.

Known free-text fields must remain free text:

- Client Visit — Destination;
- Recruiting — Area / Location;
- Employee Visit — Employee / Reference;
- Check Delivery — Employee / Reference;
- Office — Office;
- Other — Area / Location.

Do not create catalogs for these fields.

Where V0.7 places a Standardized Value before travel, preserve that timing. Where a field belongs to post-arrival Activity execution, defer it to RTE05. **Do not move a field between pre-trip and post-arrival merely to simplify implementation.** If the repository baseline does not make the timing of a field determinable, STOP on that field and report the ambiguity rather than inventing a new flow.

---

## 3. Trip state model

Required conceptual states:

`PLANNING → IN_TRANSIT → ARRIVED`

with terminal paths:

- operational Trip: later Activity completion closes it in RTE05;
- HOME Trip: `Arrived Home` closes the Trip directly to `CLOSED` in RTE04;
- explicit `End Work Anyway` while `IN_TRANSIT`: Trip becomes `INTERRUPTED`.

RTE04 may leave an operational Trip in `ARRIVED` awaiting the future Activity execution checkpoint. It must not fabricate an Activity or silently close that operational Trip.

At most one non-terminal Trip may exist for one Work Session at a time.

A Trip may exist only inside an `ACTIVE` Work Session.

The server is authoritative for transition legality.

---

## 4. Start Trip

`Start Trip` transitions a valid planned Trip to `IN_TRANSIT`.

Before the transition succeeds:

- Work Session must still be `ACTIVE`;
- no conflicting current Trip may exist;
- required pre-trip context must be valid;
- the Start Odometer requirement must be resolved when vehicle travel applies.

Do not implement GPS or official mileage as part of Start Trip in this checkpoint.

---

## 5. Change Plan

`Change Plan` is available **only while the Trip is `IN_TRANSIT`**.

It must preserve traceability:

- original purpose/context is immutable;
- every plan change is appended as historical evidence;
- current purpose/context is derived from the latest valid change;
- multiple consecutive changes are allowed and reportable later.

Do not overwrite the original plan.

After `Arrived`, Change Plan is unavailable. A new displacement after arrival requires a new Trip after the current operational stop is completed in the appropriate later flow.

RTE04 does not implement location evidence on Change Plan. Do not fabricate coordinates or a location reference merely to satisfy a future schema.

---

## 6. Arrived

For an operational Trip:

`IN_TRANSIT → ARRIVED`

Arrival ends the travel leg but does **not** auto-start an Activity and does not close the Trip.

RTE04 must preserve this state for RTE05 to extend.

Do not calculate official Miles on arrival in this checkpoint.

---

## 7. HOME Trip

HOME is a special Trip context.

`Arrived Home` closes the HOME Trip directly:

`IN_TRANSIT → CLOSED`

No Activity block is created for HOME.

The Work Session remains `ACTIVE` after Arrived Home.

Arriving home must never implicitly execute End Work.

---

# Confirmed Product Rules — End Work with Trip

If the Supervisor invokes End Work while a Trip is `IN_TRANSIT`, End Work is a **review/finalization action**, not a destructive automatic close.

The user must receive:

- a clear review that travel is still active;
- `Continue Working`;
- explicit `End Work Anyway`.

### Continue Working

- leaves the Trip `IN_TRANSIT`;
- leaves the Work Session `ACTIVE`;
- restores the same current Trip/context;
- is traceable as needed but does not create a new Trip.

### End Work Anyway

- explicitly interrupts the Trip;
- Trip becomes `INTERRUPTED`;
- no fake Arrived event is created;
- the workflow then proceeds toward the normal End Work finalization path, including final odometer evidence when required.

RTE05 will later add the rule that an `IN_PROGRESS` Activity blocks End Work. Do not invent an Activity blocker before that domain exists.

---

# Odometer Evidence — Product Model

## 1. Authority separation

This checkpoint introduces **Odometer Evidence**, not official mileage authority.

The two concepts must remain independent:

- **Routing Mileage** — future official road-distance fact calculated from routing endpoints;
- **Odometer Distance** — Work Session / vehicle evidence used for reference and later validation.

Never overwrite, replace or derive official Routing Mileage from odometer readings.

Do not label Odometer Distance as `Miles` without qualification.

Future UI may compare Routing Miles vs Odometer Distance, but no automatic discrepancy rule or override is approved in RTE04.

---

## 2. Start Work does not immediately force odometer capture

Key rule:

> **Start Work ≠ Start Driving.**

After Start Work:

- Work Session becomes `ACTIVE` exactly as today;
- if a session vehicle applies, Start Odometer becomes `PENDING`;
- the Supervisor lands on the normal `What's Next` / work context;
- the application displays a discreet persistent actionable message such as:

`Odometer pending — Capture before first trip >`

Do not immediately block the user with a full-screen odometer prompt after Start Work.

The Supervisor may perform non-driving work while Start Odometer is pending.

---

## 3. Contextual prompt before first travel

When the Supervisor selects the first travel-oriented Trip/context while Start Odometer is still `PENDING`, open odometer capture contextually before actual travel begins.

The selected Trip/context must be preserved.

After successful odometer capture, return the Supervisor to the exact Trip/context they selected. Do not make them choose it again.

If the user closes the odometer capture without completing it:

- status remains `PENDING`;
- return to the same Trip/context;
- Start Trip remains unavailable until the requirement is resolved.

---

## 4. Hard Start Trip guard

`Start Trip` must not succeed when vehicle travel applies and Start Odometer is unresolved.

Valid resolved states before Start Trip are:

- `PHOTO_CONFIRMED`; or
- `MANUAL_EXCEPTION_CONFIRMED`.

If no session vehicle applies, or the vehicle odometer requirement is legitimately not applicable, use `NOT_REQUIRED` rather than fabricating a reading.

The server must enforce this rule independently from the UI.

---

## 5. Primary odometer evidence

Primary evidence is:

> **photo + Supervisor-confirmed odometer reading**

The original photo is retained as evidence through Core Files.

Do not use a public permanent file URL.

The confirmed reading and the original photo must remain associated with:

- tenant/company;
- Supervisor;
- Work Session;
- session vehicle snapshot;
- evidence type `START` or `END`;
- capture time;
- confirmation time;
- confirming user;
- method/status.

Exact table/field layout is delegated to Development as long as these semantics remain queryable and auditable.

A conceptual model may include an `odometer_evidence` record with fields equivalent to:

- id;
- work_session_id;
- vehicle_id / vehicle snapshot reference;
- evidence_type (`START`, `END`);
- confirmed_reading;
- file_id;
- ocr_detected_reading;
- evidence_method;
- captured_at;
- confirmed_at;
- confirmed_by;
- status;
- exception_request reference where applicable.

Do not duplicate the Vehicle master to store daily odometer readings.

---

## 6. OCR is assistive only

Required sequence:

1. Supervisor captures/selects the odometer photo through the approved mobile experience.
2. OCR may attempt to read the displayed value.
3. If OCR produces a candidate, show it as a suggestion.
4. Supervisor confirms or corrects the value.
5. Store the OCR suggestion and confirmed reading independently when both exist.

OCR must never autonomously establish a critical mileage fact.

If OCR fails but a usable photo exists:

- Supervisor manually types the value visible in the photo;
- this remains normal `PHOTO_CONFIRMED` evidence;
- no Admin exception is required.

The OCR provider/library/implementation is a delegated technical choice. Avoid coupling the domain to a specific external OCR vendor.

---

## 7. No-photo manual entry is exceptional

There are two different meanings of “manual” and they must never be conflated:

### Normal

Manual confirmation/correction of a reading while a photo exists.

- no Admin approval;
- evidence remains `PHOTO_CONFIRMED`.

### Exception

Manual entry when **no photo exists**.

- not available as a normal button;
- requires `Request Manual Entry Exception`;
- requires a simple reason;
- requires Admin approval;
- approval is one-time and narrowly scoped;
- only after approval may the Supervisor enter the reading manually.

Approved simple reasons:

- Camera unavailable;
- Permission / camera problem;
- Unable to obtain usable photo;
- Other.

Do not turn this into a broad free-form permission or permanent role capability.

---

## 8. Start Odometer exception states

Conceptually:

`PENDING`

→ `PHOTO_CONFIRMED`

or

`PENDING → EXCEPTION_REQUESTED → EXCEPTION_APPROVED → MANUAL_EXCEPTION_CONFIRMED`

or

`PENDING → NOT_REQUIRED`

Admin may also reject the request / require photo, returning the Supervisor to a state where Start Trip remains blocked until valid evidence is produced.

While Start Odometer exception is pending:

- Supervisor may continue non-driving work;
- Start Trip remains blocked.

---

## 9. One-time Admin approval scope

Approval must be scoped to exactly:

- tenant;
- Supervisor;
- Work Session;
- vehicle/session vehicle;
- evidence type `START` or `END`;
- one authorization/use.

After it is consumed, it cannot be reused for another day, vehicle or evidence type.

Persist:

- no-photo fact;
- reason;
- request timestamp;
- requester;
- approval/rejection timestamp;
- Admin actor;
- approved evidence type;
- manual confirmation timestamp and value if completed.

Do not make no-photo evidence appear as photo evidence.

---

# Admin Odometer Exception UX

Provide the minimum usable Route Admin surface for pending odometer exception requests.

An authorized Admin must be able to:

- see pending requests;
- identify Supervisor, Work Session, vehicle and START/END evidence type;
- see reason and request time;
- Approve Manual Entry;
- Reject / Require Photo;
- see final resolution state.

The request must be tenant-scoped and audited.

Use `route.records.adjust` for this approval authority if it fits the existing capability model as expected.

At minimum, the Admin experience must expose pending requests in-product with a visible pending indicator/queue. Do not introduce a new cross-platform notification architecture merely for RTE04. If an existing notification component can be reused safely, reuse it; otherwise the actionable Admin queue is sufficient for this checkpoint.

Email is not required.

---

# End Odometer

## 1. When it is required

Do not ask for final odometer at `Arrived Home`.

Arrived Home ends displacement; End Work closes the workday evidence.

When the Supervisor selects `End Work` and the Work Session actually used the session vehicle for one or more Trips, require final odometer evidence before normal completion of the workday.

Normal sequence:

`End Work → Final Odometer → photo/OCR suggestion → Supervisor confirms → Work Session ENDED`

If no vehicle Trip occurred during the session:

- final odometer is `NOT_REQUIRED`;
- do not force meaningless photos;
- do not fabricate an Odometer Distance of zero.

If a Start Odometer was captured but no vehicle Trip ultimately occurred, preserve that evidence but do not invent an End reading merely to calculate zero distance.

---

## 2. Derived Odometer Distance

When both valid Start and End readings exist for the same session vehicle:

`Odometer Distance = End Reading - Start Reading`

Validate:

- End Reading must be greater than or equal to Start Reading;
- both evidence points belong to the same Work Session and session vehicle;
- no silent overwrite is permitted.

If the values are inconsistent, do not silently correct them and do not publish a fabricated distance.

Persist sufficient evidence/status for later Admin review/correction capability, but **do not build the general post-close correction workflow in RTE04**.

---

# DECISION REQUIRED — End Odometer no-photo exception

One product decision remains intentionally unresolved and must **not** be invented by Development:

If the Supervisor is trying to End Work, cannot obtain the required END odometer photo, and submits a manual-entry exception request, should the Work Session:

### Option A — remain ACTIVE until Admin approval and final manual reading

Advantages:
- End Work never completes without finalized odometer evidence when vehicle travel occurred;
- strongest evidence integrity.

Risk:
- Supervisor may be unable to fully close the workday while waiting for an Admin.

### Option B — end with an explicit pending odometer exception

Advantages:
- Supervisor can finish the workday without waiting for Admin availability.

Risk:
- introduces a post-session unresolved evidence state and later completion semantics that must be designed carefully.

**CER has not yet approved A or B.**

Development may implement the shared request/approval model used by both START and END, and the normal END photo path, but must **STOP before choosing the terminal Work Session behavior for an unresolved END manual-entry exception**.

Do not infer the answer from the START exception behavior.

---

# Offline / Reconnect Requirements

Trip and odometer flows must remain compatible with the RTE03 offline contract.

## Trip actions

Mutating Trip actions must be durable/idempotent and reconciled against authoritative server state.

At minimum cover:

- create planned Trip;
- Start Trip;
- Change Plan;
- Arrived / Arrived Home;
- End Work Anyway / interrupted Trip where applicable.

Do not create a second queue implementation if the RTE03 queue can be extended.

## Odometer photo while offline

A photo captured while offline must not be represented as server-persisted evidence until it is actually persisted/synchronized.

If supporting offline odometer capture:

- retain the photo and confirmed reading durably on-device until upload;
- protect it from accidental loss across page/app reopen to the practical limits of the existing client technology;
- upload evidence before any queued Start Trip that depends on it;
- preserve the same idempotency key / action identity on retry;
- remove local sensitive file content after authoritative synchronization when safe.

If the application cannot safely preserve photo evidence offline with the current technical approach, STOP and report the limitation rather than letting Start Trip bypass the odometer guard.

An OCR failure or OCR unavailability while offline must not block manual confirmation from an existing photo.

Manual no-photo exception approval requires server/Admin authority; do not fabricate offline approval.

---

# Current-State Recovery

Extend the existing authoritative Work Session current-state contract rather than creating a competing source of truth.

The Supervisor must be able to reopen/reload/reconnect/re-authenticate and recover enough state to know:

- active Work Session;
- current non-terminal Trip, if any;
- legal next Trip action;
- Start Odometer state;
- End Odometer state when relevant;
- pending exception state when relevant.

A second device must resolve the same server-side Work Session/Trip.

If Device A has unsynchronized local photo evidence, Device B must not assume it exists. The server remains authoritative; Device B may require a new capture or wait for Device A synchronization.

---

# Data Model Impact

Development chooses the exact normalized schema, but the domain must support these concepts without future destructive redesign:

### Trip

Required semantics:

- tenant/company;
- Work Session;
- Supervisor through Work Session ownership;
- ordered trip sequence;
- original purpose/context immutable;
- current purpose/context;
- state;
- planned/created occurrence evidence;
- started occurrence/receipt evidence consistent with RTE03 time semantics;
- arrived occurrence/receipt evidence;
- closed/interrupted occurrence where applicable;
- version/concurrency mechanism where repository conventions require it.

### Trip Purpose Change

Append-only history sufficient to answer:

- original plan;
- every intermediate change;
- final plan;
- who/when changed it.

Do not overwrite prior changes.

### Odometer Evidence

Store photo-linked confirmed facts and provenance as described above.

### Odometer Exception Request

Store request, scope, reason, state, approver/rejector, timestamps and one-time authorization semantics.

Do not place daily readings on the Vehicle master.

---

# API / Service Contracts

Exact route naming is delegated, but the API surface must support the following operations with server-side authorization and tenant scope:

### Supervisor

- create/prepare Trip;
- read current Trip;
- Start Trip;
- Change Plan;
- Arrive;
- Arrive Home;
- obtain current Work Session + Trip + odometer requirement state;
- create/upload START odometer photo evidence;
- confirm/correct OCR-suggested START reading;
- request START manual-entry exception;
- enter manual START reading after approval;
- create/upload END odometer photo evidence;
- confirm/correct END reading;
- request END manual-entry exception;
- enter manual END reading after approval;
- invoke End Work review / Continue Working / End Work Anyway as applicable.

### Admin

- list pending odometer exception requests;
- inspect request context;
- approve one-time manual entry;
- reject/require photo;
- read resolution history.

Use consistent HTTP/idempotency/error conventions from the existing application.

Cross-tenant or another Supervisor's Trip/evidence must not be exposed through object IDs.

---

# Mobile UX Requirements

Supervisor remains **mobile-only / mobile-first**.

Principles:

- one primary action at a time;
- minimal typing while driving;
- no implementation/debug messages;
- no desktop Supervisor workflow;
- preserve state/context across odometer interruption;
- use a large bottom sheet or full-screen mobile modal for odometer capture rather than a tiny desktop-style dialog;
- camera action, OCR suggestion and numeric confirmation must be legible and usable with one hand;
- errors should describe the action required, not internal technical causes.

Suggested normal flow:

`Work ACTIVE`

→ What's Next

→ choose Trip context

→ if Start Odometer unresolved, odometer capture

→ return to same context

→ Start Trip

→ On Route

→ optional Change Plan

→ Arrived

→ RTE04 stops at Arrived for operational Trips; RTE05 will add Activity execution

For HOME:

`Return Home → Start Trip → On Route → Arrived Home → Trip CLOSED → Work still ACTIVE`

---

# Security / Audit

## Authorization

All lifecycle rules are enforced server-side.

Supervisor actions must require the existing authorized field-execution capability model.

Admin manual-entry approvals require Admin authority and minimum privilege.

Do not grant Admin approval authority to Supervisor merely because the Supervisor owns the Work Session.

## Tenant isolation

Every Trip, odometer evidence record, exception request and file must be tenant-scoped.

Cross-tenant IDs must not reveal existence.

## File security

Odometer photographs may contain dashboard, VIN or other vehicle information.

Requirements:

- private Core Files storage;
- authenticated/authorized retrieval;
- file type and size validation;
- malware scanning according to existing Core Files policy where applicable;
- no public permanent URL;
- no secrets in filenames or logs.

The exact retention period for odometer photos is **not approved**. Do not invent an auto-delete policy in RTE04. Preserve the evidence until CER defines retention policy.

## Audit

Audit at least:

- Trip create;
- Start Trip;
- Change Plan;
- Arrived / Arrived Home;
- Trip interruption;
- odometer photo evidence creation;
- Supervisor confirmed/corrected reading;
- exception request;
- approval/rejection;
- manual exception reading confirmation;
- End Work review outcome where relevant.

Sensitive audit must identify actor, tenant, entity, action and timestamp while avoiding photo binary content or secrets in logs.

---

# Business Rules / Edge Cases

Handle and test at minimum:

1. Start Trip without active Work Session → reject.
2. Second current/non-terminal Trip in one Work Session → reject.
3. Replayed Start Trip → idempotent; no duplicate Trip/transition.
4. Replayed Arrived → no duplicate transition.
5. Change Plan before Start Trip → reject unless the approved PLANNING UI simply edits uncommitted planning data; once `IN_TRANSIT`, historical changes must append.
6. Change Plan after Arrived → reject.
7. HOME Arrived → Trip closes, Work Session stays ACTIVE.
8. Operational Arrived → Trip stays ARRIVED; no fake Activity/close.
9. End Work while IN_TRANSIT → review; Continue Working restores same Trip.
10. End Work Anyway → Trip `INTERRUPTED`, no fake Arrived.
11. Start Odometer pending + no vehicle Trip yet → non-driving work allowed.
12. Start Trip with required Start Odometer unresolved → reject server-side.
13. OCR fails but photo exists → manual confirmation allowed without Admin.
14. No photo + no approval → manual entry unavailable.
15. Approved exception cannot be reused for another Work Session/vehicle/evidence type.
16. End reading < Start reading → reject or unresolved evidence state; never negative distance.
17. No vehicle Trip in session → End Odometer NOT_REQUIRED.
18. Vehicle assignment changes after Start Work → current session continues using its historical session vehicle snapshot; do not silently swap vehicle context.
19. Deleted/deactivated Vehicle master after session start must not destroy historical session/odometer evidence.
20. Reload/reconnect during PLANNING/IN_TRANSIT/ARRIVED restores the authoritative Trip.
21. Second device does not create another Trip.
22. Offline queued Trip actions preserve ordering.
23. Offline Start Trip cannot outrun required odometer evidence in the queue.
24. OCR/provider unavailable must not convert a valid photo into a manual-exception case.
25. No official Routing Mileage value is produced anywhere in RTE04.

---

# Acceptance Criteria

## Trip Foundation

- [ ] Start Work still creates no Trip.
- [ ] A valid Trip can be created only inside an ACTIVE Work Session.
- [ ] Only one non-terminal Trip exists per Work Session.
- [ ] Trip progresses through PLANNING → IN_TRANSIT → ARRIVED for operational travel.
- [ ] HOME Arrived closes the Trip directly.
- [ ] Arrived Home does not end the Work Session.
- [ ] Change Plan is available only IN_TRANSIT.
- [ ] Original plan survives one or multiple Change Plan operations.
- [ ] Operational Arrived does not auto-create or auto-complete Activity.
- [ ] End Work while IN_TRANSIT provides Continue Working and explicit End Work Anyway.
- [ ] End Work Anyway interrupts rather than fabricating arrival.
- [ ] current-state recovery returns the authoritative current Trip.
- [ ] Trip mutations are idempotent/offline-compatible.

## Start Odometer

- [ ] Start Work does not immediately force odometer capture.
- [ ] Persistent pending indication appears when required.
- [ ] First travel context opens capture when still pending.
- [ ] Cancel/close returns to the same context and leaves PENDING.
- [ ] Start Trip is server-blocked until required Start Odometer is resolved.
- [ ] Photo + confirmed reading produces PHOTO_CONFIRMED.
- [ ] OCR result is only a suggestion.
- [ ] OCR failure with a photo still allows normal manual confirmation.
- [ ] No-photo manual entry requires a one-time Admin-approved exception.
- [ ] Pending Start exception allows non-driving work but not Start Trip.
- [ ] No applicable vehicle case becomes NOT_REQUIRED without fake reading.

## End Odometer

- [ ] Arrived Home does not ask for final odometer automatically.
- [ ] End Work after actual session-vehicle travel requests final odometer.
- [ ] End reading validates against Start reading.
- [ ] Odometer Distance is derived only from valid Start/End evidence.
- [ ] No vehicle Trip means End Odometer NOT_REQUIRED.
- [ ] No official Routing Mileage is changed or created.
- [ ] Normal END photo path can finish Work Session correctly.
- [ ] The unresolved no-photo END exception terminal behavior is not silently chosen without CER decision.

## Admin Exception Workflow

- [ ] Pending request is visible/actionable in Route Admin.
- [ ] Request identifies Supervisor, Work Session, vehicle, START/END and reason.
- [ ] Admin can Approve Manual Entry or Reject/Require Photo.
- [ ] Approval is one-time and scope-bound.
- [ ] Unauthorized users cannot approve/reject.
- [ ] Every decision is audited.

## Security / Regression

- [ ] Tenant isolation holds for Trip, evidence, files and exception requests.
- [ ] Photo retrieval is private/authorized.
- [ ] RTE03 Start/End Work baseline is preserved except for the explicitly approved Trip/odometer guards/review integration.
- [ ] RTE02-A01 Admin lifecycle/configuration remains green.
- [ ] No Activity/GPS/Routing Mileage/RTE05+ domain is implemented.

---

# Tests Required

Use discriminating tests, not only happy-path status assertions.

## Trip integration tests

At minimum include named tests proving:

- zero-Trip Work Session remains valid;
- Trip requires ACTIVE Work Session;
- DB/service prevents second non-terminal Trip;
- repeated Start Trip changes state once;
- second device resolves same Trip;
- Change Plan preserves original + two consecutive changes;
- Change Plan after Arrived fails;
- operational Arrived remains ARRIVED and does not create Activity;
- HOME Arrived closes Trip and leaves Work Session ACTIVE;
- End Work in transit does not silently end;
- Continue Working restores same trip;
- End Work Anyway produces INTERRUPTED;
- cross-tenant / other-Supervisor Trip IDs do not leak data;
- offline/replay ordering does not corrupt Trip state.

## Odometer tests

At minimum prove:

- Start Work with session vehicle produces PENDING without blocking work;
- Start Work without applicable vehicle context produces correct NOT_REQUIRED behavior when appropriate;
- Start Trip hard guard fails while Start Odometer unresolved;
- photo evidence + manual confirmation succeeds even when OCR returns nothing;
- OCR suggestion can be corrected and both suggestion/confirmed value remain distinguishable;
- no-photo manual entry is impossible before Admin approval;
- approval is scoped and single-use;
- approval for START cannot authorize END;
- approval for one Work Session cannot authorize another;
- rejected exception does not unlock Start Trip;
- end < start cannot produce negative distance;
- session with vehicle Trip requires End Odometer on normal End Work path;
- session without vehicle Trip does not require End Odometer;
- odometer values never modify Routing Mileage.

## Browser-level Supervisor validation

Use the existing real-browser harness or an equivalent repeatable browser-level validation for at least:

1. Start Work → odometer pending banner → select travel context → capture/confirm → return to same context → Start Trip.
2. Close odometer capture → same context restored → Start Trip remains blocked.
3. On Route → Change Plan → same Trip continues.
4. Arrive operational → state restored after reload, no fake Activity completion.
5. HOME → Arrived Home → Trip closed, Work Session still active.
6. End Work after vehicle travel → final odometer normal photo path → session ends.
7. No-photo START exception request → Admin approve → Supervisor manual entry → Start Trip unlocked.

If camera/OCR cannot be exercised with physical hardware in this checkpoint, browser tests may mock the camera/OCR boundary **only if the report clearly separates mocked device boundary from real domain/browser behavior**. Real-device camera validation remains a later hardware-validation track.

## Regression

Report:

- targeted Trip tests;
- targeted Odometer tests;
- authorization/tenant tests;
- browser E2E results;
- full backend suite;
- frontend typecheck;
- frontend lint;
- production build;
- schema/migration consistency required by the implementation.

---

# Do Not Change

Do not change the following approved decisions:

- CER Route remains independent from CER ERP;
- Supervisor remains mobile-only;
- Start Work can exist without Trip;
- one active Work Session per Supervisor;
- RTE03 occurrence/receipt time semantics;
- Work Session vehicle/MPG snapshot semantics;
- Trip Purpose ≠ Activity;
- Change Plan only while IN_TRANSIT;
- Change Plan is append-only history, not overwrite;
- HOME Arrived closes Trip but not Work Session;
- free-text fields remain free text;
- eight Standardized List codes remain fixed;
- Outcomes remain tenant data;
- Routing Mileage remains the future official road-distance fact;
- Haversine is not official fallback;
- odometer is independent evidence, not Routing Mileage;
- photo + Supervisor-confirmed reading is primary odometer evidence;
- OCR is assistive only;
- no-photo manual entry requires one-time Admin approval;
- no mid-session vehicle switching requirement;
- no automatic discrepancy enforcement between routing and odometer;
- exact odometer-photo retention duration remains undecided and must not be invented.

Do not re-open RTE02-A01 frontend technical debt as part of this checkpoint.

---

# Internal Checkpoints

Use these as functional checkpoints, not code-level micromanagement.

### RTE04-C1 — Trip Domain Foundation

Deliverable:
- Trip model/state invariants;
- current Trip contract;
- purpose/context planning;
- tenant/authorization/idempotency foundations;
- migration/tests.

### RTE04-C2 — Mobile Trip Lifecycle

Deliverable:
- Supervisor PLANNING / Start Trip / On Route / Change Plan / Arrived / HOME flow;
- current-state restoration;
- End Work review while IN_TRANSIT;
- offline queue integration;
- browser evidence.

### RTE04-C3 — Start Odometer Evidence

Deliverable:
- PENDING/NOT_REQUIRED model;
- persistent UX indicator;
- photo + OCR suggestion + Supervisor confirmation;
- Start Trip hard guard;
- offline-safe ordering;
- Start manual-exception request/approval/confirmation;
- Admin exception queue.

### RTE04-C4 — End Odometer

Deliverable:
- normal END photo/confirmation path;
- derived Odometer Distance;
- no-trip NOT_REQUIRED behavior;
- integration with End Work.

**Decision gate:** unresolved END no-photo exception terminal behavior must be returned to CER before choosing Option A or B.

### RTE04-C5 — Validation / Delivery

Deliverable:
- targeted and discriminating tests;
- browser flows;
- security/tenant/audit evidence;
- regression;
- delivery report.

---

# Deliverables

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE04_DELIVERY_REPORT_001.md`

The report must be evidence-first and include:

1. exact as-built Trip state model;
2. exact as-built Odometer state model;
3. APIs/services/components added or changed;
4. data/schema impact;
5. Mobile UX flows actually implemented;
6. Admin exception workflow actually implemented;
7. offline/idempotency behavior;
8. security, tenant isolation and audit evidence;
9. Expected → Implemented → Evidence → Gap matrix;
10. test results with named discriminating tests;
11. browser validation evidence;
12. any `PARTIAL`, `PENDING VALIDATION`, `DEVIATION`, `TECHNICAL DEBT`, or `DECISION REQUIRED`;
13. explicit confirmation that no Activity execution, GPS, Routing Mileage, fuel, reports or RTE05+ functionality was started;
14. explicit statement of the unresolved END no-photo decision if CER has not supplied it before delivery.

Do not report `Completed` merely because the code compiles.

Suggested status only when all approved RTE04 scope is evidenced:

`RTE04 — Completed / Ready for CER Validation`

If the END no-photo product decision remains unresolved at delivery time, use:

`RTE04 — Partial / CER Decision Required`

for that specific reason rather than inventing a terminal behavior.

---

# STOP Conditions

STOP and return to CER before implementing a new product decision if any of the following becomes necessary:

- deciding whether an unresolved END odometer manual exception blocks End Work or allows an ended/pending session;
- moving a V0.7 field between pre-trip and post-arrival because its approved timing cannot be determined;
- creating a new Trip Purpose or configurable Activity Type;
- creating catalogs for approved free-text fields;
- changing Work Session session-date/time semantics;
- allowing more than one non-terminal Trip per Work Session;
- automatically closing an operational Trip at Arrived;
- enabling Change Plan after Arrived;
- using odometer as official Routing Mileage;
- implementing Haversine as official mileage;
- inventing a GPS/location behavior in RTE04;
- introducing route optimization;
- adding permanent manual-entry permission instead of one-time exception approval;
- creating a public odometer-photo URL;
- inventing an odometer-photo retention duration;
- implementing mid-session vehicle switching;
- beginning Activity execution, GPS, Routing Mileage, fuel, reports or any RTE05+ scope.

After producing `CER_ROUTE_RTE04_DELIVERY_REPORT_001.md`, **STOP**.

Do not continue into RTE05 or later checkpoints until CER reviews the RTE04 delivery.
