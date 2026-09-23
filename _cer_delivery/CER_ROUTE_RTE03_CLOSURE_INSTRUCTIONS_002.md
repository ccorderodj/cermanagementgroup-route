# CER Route — RTE03 Closure Instruction 002
## Work Session Offline Time Semantics + Evidence Closure

**Applies to:** `feature/rte03-work-session`  
**Baseline delivery:** `Report Delivery Rodrigo/CER_ROUTE_RTE03_DELIVERY_REPORT_001.md`  
**Purpose:** Close the remaining RTE03 validation/correctness gap without starting RTE04 or the approved odometer delta.  
**Output:** `Report Delivery Rodrigo/CER_ROUTE_RTE03_CLOSURE_DELIVERY_REPORT_002.md`

---

## Current State

The RTE03 delivery demonstrates that the Work Session foundation, database invariant, APIs, capability enforcement, server-side idempotency, audit, mobile Work Session UI, auth-continuity implementation, migration, and regression suite are implemented.

One correctness issue remains before CER certification:

- `started_at` / `ended_at` are currently described as server-clock authoritative timestamps.
- Start/End Work can be queued offline and synchronized later.
- Therefore, for an offline action, server processing time can differ materially from the time the Supervisor actually pressed Start Work / End Work.
- `session_date` is currently derived from server `started_at` plus the device UTC offset.
- A Start Work performed offline before local midnight and synchronized after midnight can therefore be assigned to the wrong local work date.

This conflicts with the existing D-10 requirement that lifecycle events preserve the time they actually occurred and that the Work Session belongs to the local calendar date of Start Work.

The current delivery also states that IndexedDB/offline behavior is implemented but has not been browser/device validated. That evidence must remain classified honestly.

---

## Objective

Close RTE03 by correcting offline Start/End Work time semantics so that synchronization delay is never represented as the operational occurrence time, while preserving:

- server receipt/audit provenance;
- the existing one-active-session invariant;
- idempotency;
- tenant isolation;
- auth continuity;
- offline queue durability design;
- zero-Trip Work Sessions;
- current RTE03 API/state model unless a change is necessary to satisfy the corrected contract.

Do not broaden this closure into Trip, Activity, odometer, geolocation, routing mileage, or RTE02-A01 work.

---

## Confirmed Decisions

### 1. Occurrence time and server receipt time are different facts

For any queued lifecycle action, the implementation must preserve enough information to distinguish:

- when the Supervisor performed the action; and
- when the server received/committed the action.

A delayed synchronization must never silently make the server receipt time appear to be the actual Start Work or End Work occurrence time.

### 2. `session_date` follows the local date of the actual Start Work action

If Start Work occurs locally on Friday and synchronizes on Saturday, the Work Session remains Friday.

This rule also applies when synchronization is delayed for minutes or hours.

### 3. Server authority and device evidence must remain explicit

Do not erase server timestamps or treat an untrusted client clock as magically authoritative.

The technical mechanism for reconciling server receipt, device-captured occurrence evidence, UTC offset, offline provenance, and clock-skew handling is delegated to Development.

The resulting model must preserve provenance honestly and must not fabricate precision that the available evidence cannot support.

### 4. Online behavior must not regress

Normal online Start Work / End Work should remain operationally immediate and retain the existing server-authorized identity, tenant, permission, idempotency and audit controls.

### 5. Existing RTE03 scope remains fixed

The current Work Session states remain:

`ACTIVE -> ENDED`

No Trip/Activity state is introduced in this closure.

---

## Scope

Implement only what is required to correct and prove the time/offline semantics above.

This may include, only if required:

- Work Session timestamp/provenance fields;
- schema/API response adjustments;
- service logic;
- migration amendment/new migration consistent with the current unmerged branch;
- offline action payload;
- Mobile display of Work Session start/end time;
- tests;
- delivery documentation.

Preserve the existing public contracts where possible. If a contract must change, document why and prove compatibility with the current RTE03 frontend.

---

## Out of Scope

Do not implement:

- Trip;
- Trip Purpose;
- Start Trip / Arrived / Change Plan / Home Trip;
- Activity execution;
- geolocation;
- routing mileage;
- fuel calculations;
- odometer;
- camera capture;
- OCR;
- odometer exception workflow;
- RTE02-A01 Delete/Deactivate UX;
- Standardized List seed changes;
- Today/Live;
- Reports;
- RTE04 functionality.

The newly approved odometer requirement is a future product delta and is intentionally not part of this RTE03 closure.

---

## Functional / Data Rules

1. An offline Start Work must retain the actual action occurrence evidence across app close/reopen and delayed synchronization.
2. An offline End Work must retain the actual action occurrence evidence across delayed synchronization.
3. Server receipt/commit time must remain separately available for traceability.
4. `session_date` is computed once from the best approved evidence of the actual Start Work occurrence and its local offset, then remains immutable.
5. A queued/replayed action must not create a second Work Session or change an already-established occurrence time.
6. Reauthentication must not discard the queued lifecycle occurrence evidence.
7. A second device must still resolve the same authoritative Work Session.
8. No client payload may choose `user_id` or `company_id`.
9. Any uncertainty caused by missing or suspicious client time evidence must be represented honestly; do not silently relabel receipt time as occurrence time.
10. The correction must remain compatible with later Trip and odometer extensions.

---

## Tests / Evidence Required

### A. Discriminating offline-time tests

Add tests that would fail under the current server-receipt-time behavior.

At minimum prove:

1. **Offline Start across midnight**
   - Supervisor performs Start Work Friday at 11:50 PM local.
   - Action synchronizes Saturday morning.
   - Work Session `session_date` remains Friday.
   - Stored provenance distinguishes occurrence evidence from server receipt/commit time.

2. **Offline End delayed sync**
   - Supervisor performs End Work at 5:00 PM.
   - Action synchronizes materially later.
   - Historical operational end occurrence remains 5:00 PM evidence, not the later sync time.
   - Server receipt/commit time remains traceable.

3. **Replay**
   - Replaying the same queued Start/End action does not alter the original occurrence evidence or timestamps.

4. **Online control case**
   - Online Start/End behavior remains unchanged and valid.

5. **Cross-midnight Work Session**
   - Start Friday, End Saturday remains assigned to Friday.

6. **Clock-skew / suspicious evidence**
   - Prove the selected technical strategy does not silently accept contradictory timing as unquestioned server fact.
   - Document the chosen handling and provenance.

### B. Offline queue evidence

Because the delivery report itself states there is no JS test runner and no real-device validation, provide at least one browser-level validation of the implemented queue flow before claiming the browser behavior confirmed.

Demonstrate:

- action queued while offline;
- IndexedDB persistence survives page/app reopen;
- reconnect flushes in order;
- server reconciliation returns the authoritative session;
- no duplicate Work Session;
- reauthentication does not discard the pending action.

If real iOS/Android hardware is still unavailable, classify real-device V-1/V-4 evidence as `PENDING VALIDATION`; do not report it as completed.

### C. Regression

Re-run and report:

- Work Session integration tests;
- auth continuity tests;
- authorization/permission tests;
- full backend suite;
- frontend typecheck;
- frontend lint;
- production build;
- Alembic heads/check and required migration roundtrip;
- bootstrap/idempotent role capability behavior if touched.

---

## Acceptance Criteria

RTE03 closure is acceptable when:

- [ ] Offline synchronization delay is not represented as lifecycle occurrence time.
- [ ] Offline Start Work across local midnight preserves the correct `session_date`.
- [ ] Offline End Work preserves its occurrence evidence independently from server receipt time.
- [ ] Occurrence and server receipt/commit provenance are distinguishable.
- [ ] Replays do not modify original lifecycle occurrence evidence.
- [ ] One ACTIVE Work Session remains DB-enforced.
- [ ] Auth continuity and reauthentication preserve queued actions.
- [ ] Multi-device behavior still resolves one authoritative Work Session.
- [ ] Tenant isolation and server-side authorization remain intact.
- [ ] Audit remains intact.
- [ ] Browser-level offline queue behavior has evidence, or any unavailable real-device portion is explicitly `PENDING VALIDATION`.
- [ ] Full regression is green.
- [ ] The report no longer marks unvalidated real-device behavior as confirmed.
- [ ] No RTE04, RTE02-A01, odometer, OCR or routing mileage functionality was started.

---

## Do Not Change

Do not change unless strictly required by the closure correction:

- Work Session lifecycle `ACTIVE -> ENDED`;
- one ACTIVE session per Supervisor;
- `route.worksession.execute`;
- Supervisor-only default grant;
- Core tenant/user authority;
- vehicle/MPG snapshot behavior;
- zero-Trip Work Session validity;
- `GET /worksessions/current` as the authoritative current-state envelope;
- existing idempotency mechanism;
- Mobile-only Supervisor V1;
- certified Routing Mileage definition.

Do not redefine routing mileage using odometer data.

---

## Deliverable

Create a new report; do not overwrite delivery 001:

`Report Delivery Rodrigo/CER_ROUTE_RTE03_CLOSURE_DELIVERY_REPORT_002.md`

The report must include:

1. previous behavior vs corrected behavior;
2. exact model/schema/API changes;
3. occurrence-time vs server-receipt semantics;
4. migration status and single Alembic head;
5. offline-across-midnight test evidence;
6. delayed End Work evidence;
7. replay/idempotency evidence;
8. browser-level offline validation evidence;
9. any real-device items still `PENDING VALIDATION`;
10. auth/time regression results;
11. full regression;
12. branch, base, final candidate commit, push status and MR status;
13. Expected → Implemented → Evidence matrix;
14. confirmation no RTE04/RTE02-A01/odometer work was started.

---

## STOP Conditions

STOP and return to CER without choosing a new product rule if the correction requires any of the following:

- redefining what `session_date` means;
- allowing more than one active Work Session;
- changing Routing Mileage authority;
- changing the approved odometer future design;
- introducing a new timezone configuration/catalog;
- changing tenant identity or authorization boundaries;
- starting Trip/Activity/RTE04 scope;
- starting RTE02-A01 within this branch.

After producing delivery 002, **STOP**. Do not merge to `dev` and do not begin RTE04 until CER reviews and certifies the closure.
