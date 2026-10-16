# CER Route — RTE04 C1 Closure + Continuation Instructions 003
## Close C1 gaps and continue C2 → C5 under the approved roadmap

**Checkpoint:** RTE04 — Trip Foundation + Odometer Evidence  
**Applies to:** `CER_ROUTE_RTE04_C1_PROGRESS_REPORT_001.md`  
**Status:** RTE04 remains **IN PROGRESS**  
**Next CER-facing completion candidate:** `Report Delivery Rodrigo/CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`

---

## Context

RTE04-C1 has implemented the Trip foundation and is substantially aligned with the approved product model.

The following are already accepted and must not be redesigned in this continuation:

- Trip only exists inside an `ACTIVE` Work Session.
- One non-terminal Trip maximum per Work Session.
- `PLANNING → IN_TRANSIT → ARRIVED`.
- Operational `ARRIVED` remains open for RTE05 Activity execution.
- HOME closes directly on `Arrived Home` while Work Session remains `ACTIVE`.
- `Change Plan` is allowed only while `IN_TRANSIT`.
- Original plan is immutable; plan changes are append-only.
- Tenant isolation and server-side authorization remain authoritative.
- Occurrence/receipt time semantics reuse the certified RTE03 behavior.
- RTE05 Activity execution, GPS, Routing Mileage, fuel and reporting remain out of scope.

C1 is **not yet considered closed** because two functional items remain:

1. `GET /worksessions/current` has not yet been extended with the authoritative current Trip.
2. The three approved pre-trip standardized fields are currently accepted as optional. CER requires them to be resolved before `Start Trip` for their applicable contexts.

---

# 1. Objective

Close the two remaining RTE04-C1 gaps and then continue directly through C2, C3, C4 and C5 according to the approved roadmap, without creating another CER-facing intermediate report unless a new product decision or STOP condition is encountered.

The final output of this controlled sequence must be:

`Report Delivery Rodrigo/CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`

---

# 2. C1 Closure — Required Corrections

## 2.1 Extend current Work Session state with current Trip

Extend the existing authoritative current-state contract rather than creating a parallel recovery endpoint.

`GET /worksessions/current` must return the current active Work Session and, when applicable, its current non-terminal Trip.

Expected conceptual shape:

```text
{
  work_session: ...,
  current_trip: ... | null
}
```

Exact schema/layout is delegated to Development.

### Required behavior

- No active Work Session → existing no-session behavior remains valid.
- Active Work Session with no Trip → `current_trip = null`.
- Active Work Session with `PLANNING`, `IN_TRANSIT`, or operational `ARRIVED` Trip → return that same authoritative Trip.
- CLOSED / INTERRUPTED Trips are not returned as `current_trip`.
- Reload, reconnect, reauthentication and second device must resolve the same current Trip.
- Do not create a duplicate Trip while recovering state.
- Tenant and Supervisor ownership must remain server-enforced.

This current-state envelope must remain extensible for later `current_activity` without requiring a second Supervisor recovery model.

---

## 2.2 Required pre-trip standardized fields

The timing decision already approved by CER remains:

| Context | Field | Timing |
|---|---|---|
| Employee Visit | Employee Visit Reason | Pre-trip |
| Check Delivery | Delivery Type | Pre-trip |
| Office | Office Purpose | Pre-trip |
| Client Visit | Client Visit Activities | Post-arrival / RTE05 |
| Recruiting | Recruiting Activities | Post-arrival / RTE05 |
| Check Delivery | Received By | Post-arrival / RTE05 |
| Other | Other Activities | Post-arrival / RTE05 |

### Requiredness correction

For the three pre-trip fields:

- Employee Visit → **Employee Visit Reason required before Start Trip**
- Check Delivery → **Delivery Type required before Start Trip**
- Office → **Office Purpose required before Start Trip**

A Trip may exist in `PLANNING` while the Supervisor is still completing the form, but `Start Trip` must be rejected until the applicable required pre-trip value is present and valid.

Do not require any RTE05 post-arrival field before departure.

### Server-side validation

The backend must independently enforce:

- required value exists for the applicable pre-trip context;
- value belongs to the correct standardized list;
- value belongs to the same tenant;
- deleted/tombstoned values cannot be newly selected;
- a value from another context/list is rejected;
- contexts without a pre-trip standardized field reject one if supplied.

Frontend validation is additive only and is not the authority.

---

# 3. C1 Acceptance Criteria

C1 is considered closed when all of the following are evidenced:

- [ ] `GET /worksessions/current` returns `current_trip` when a non-terminal Trip exists.
- [ ] No current Trip returns `null`, not a fabricated placeholder.
- [ ] Second device resolves the same Trip.
- [ ] Reload/reconnect/reauthentication resolve the same Trip.
- [ ] Employee Visit cannot `Start Trip` without Employee Visit Reason.
- [ ] Check Delivery cannot `Start Trip` without Delivery Type.
- [ ] Office cannot `Start Trip` without Office Purpose.
- [ ] Correct value for each context allows Start Trip.
- [ ] Wrong-list value is rejected.
- [ ] Post-arrival-only fields remain absent from the RTE04 pre-trip contract.
- [ ] Existing 34 C1 Trip tests remain green.
- [ ] C1 migration/schema invariants remain green.

### Required discriminating tests

Add tests that prove:

1. Employee Visit + no Reason → Start rejected.
2. Employee Visit + valid Reason → Start accepted.
3. Check Delivery + no Delivery Type → Start rejected.
4. Check Delivery + valid Delivery Type → Start accepted.
5. Office + no Purpose → Start rejected.
6. Office + valid Purpose → Start accepted.
7. Wrong standardized list → rejected.
8. Post-arrival context does not require or accept an RTE05 Activity value before departure.
9. `GET current` returns the same current Trip after reopen/second client.

After these tests are green, treat **RTE04-C1 as CLOSED** and proceed directly to C2.

---

# 4. RTE04-C2 — Mobile Trip Lifecycle

Implement the real Supervisor Mobile Trip experience using the certified Work Session and C1 Trip domain.

## Required flow

```text
Start Work
   ↓
Work Session ACTIVE
   ↓
Select travel context / Trip purpose
   ↓
Complete applicable pre-trip fields
   ↓
[START odometer guard will be enforced by C3]
   ↓
Start Trip
   ↓
On Route
   ↓
Change Plan (optional, IN_TRANSIT only)
   ↓
Arrived
```

HOME:

```text
Select Home
   ↓
Start Trip
   ↓
On Route
   ↓
Arrived Home
   ↓
Trip CLOSED
Work Session remains ACTIVE
```

## Mobile UX requirements

- Mobile-only Supervisor experience.
- One primary action at a time.
- No Admin chrome.
- Minimal typing.
- Do not expose engineering/state-machine terminology to the Supervisor.
- Preserve the V0.7 contexts:
  - Client Visit
  - Recruiting
  - Employee Visit
  - Check Delivery
  - Office
  - Other
  - Home

### Free-text fields remain free text

- Client Visit destination
- Recruiting Area / Location
- Employee Visit Employee / Reference
- Check Delivery Employee / Reference
- Office
- Other Area / Location

Do not recreate catalogs for these fields.

### Pre-trip standardized fields

Show only where applicable:

- Employee Visit → Reason
- Check Delivery → Delivery Type
- Office → Purpose

The values come from the already-approved tenant Standardized Lists.

### Post-arrival fields

Do not implement in C2:

- Client Visit Activities
- Recruiting Activities
- Received By
- Other Activities
- Activity execution
- Outcome
- Notes

These remain RTE05.

---

## Change Plan

`Change Plan`:

- available only while `IN_TRANSIT`;
- preserves original plan;
- appends each plan change;
- may change to another approved context and its applicable planning data;
- never overwrites historical intent;
- after `Arrived`, Change Plan is unavailable.

If changing context creates new required pre-trip data, the new plan must satisfy that context before continuing the valid flow.

Do not silently infer missing values.

---

## Offline / reconciliation

Reuse the RTE03 durable action queue for supported non-photo Trip actions.

Do not build a second queue.

Required behavior:

- queued supported actions preserve occurrence time;
- actions replay idempotently;
- order is preserved;
- reconnect reconciles against server-authoritative state;
- reauthentication does not discard pending supported actions;
- second device resolves the same Trip;
- no duplicate Trip is created.

Do not claim unsupported offline behavior.

---

# 5. RTE04-C3 — START Odometer Evidence

Implement START odometer evidence as a Work Session/vehicle evidence concern, independent from Routing Mileage.

## Trigger model

`Start Work ≠ Start Driving`.

After Start Work:

- Work Session becomes ACTIVE normally.
- If vehicle/Trip use may apply and START evidence is unresolved, show:
  `Odometer pending — Capture before first trip >`
- Do not immediately force the odometer popup after Start Work.
- Supervisor can continue non-driving work.

When the Supervisor selects the first travel context and START odometer is unresolved:

- open the odometer capture experience contextually;
- preserve the selected Trip context underneath;
- after successful odometer completion return to that same Trip flow.

## Hard guard

`Start Trip` must not succeed while required START odometer evidence is unresolved.

The guard must be enforced server-side.

---

## START photo evidence

Primary evidence:

**photo + Supervisor-confirmed reading**

Required behavior:

1. capture/upload private odometer photo;
2. optionally attempt OCR;
3. show OCR suggestion when available;
4. Supervisor confirms or corrects the reading;
5. persist original photo;
6. persist confirmed reading separately from OCR suggestion;
7. mark normal photo path as `PHOTO_CONFIRMED`.

OCR is assistive only.

OCR failure with a valid photo must allow the Supervisor to type the visible reading and confirm normally.

This is **not** an Admin exception.

---

## START no-photo exception

No normal "Enter manually" shortcut.

If a usable photo cannot be obtained:

1. Supervisor selects `Request Manual Entry Exception`;
2. reason is captured;
3. state becomes `EXCEPTION_REQUESTED`;
4. Admin is notified/surfaced in the Admin exception queue;
5. Supervisor may continue non-driving work;
6. `Start Trip` remains blocked.

Admin can:

- Approve Manual Entry;
- Reject / Require Photo.

Approval is one-time and scoped to:

- tenant;
- Supervisor;
- Work Session;
- Vehicle;
- START;
- specific exception request.

After approval:

- Supervisor may enter the reading manually;
- resulting evidence is `MANUAL_EXCEPTION_CONFIRMED`;
- no-photo fact remains permanently distinguishable from photo evidence.

---

# 6. RTE04-C4 — END Odometer + End Work

Normal END flow:

```text
End Work
   ↓
resolve existing Trip blockers first
   ↓
END odometer evidence
   ↓
End Work completion
```

Do not ask for END odometer at `Arrived Home`; ask when the Supervisor actually invokes `End Work`.

## Normal END photo path

- private photo;
- OCR suggestion optional;
- Supervisor confirmation/correction;
- confirmed END reading.

Validation:

`End Reading >= Start Reading`

When START and END are valid:

`Odometer Distance = End Reading - Start Reading`

This is informational/reference evidence and must remain separate from official Routing Mileage.

---

## END no-photo exception — CER Option B

If END photo cannot be obtained and the Supervisor submits the approved exception:

- Work Session may transition to `ENDED` once all other blockers are resolved;
- END odometer remains pending;
- `ended_at` remains the real End Work occurrence;
- Work Session is not reopened later;
- Odometer Distance remains pending until END reading is completed.

After Admin approval:

- Supervisor completes the one-time manual END reading against the ended Work Session;
- this does not create or reopen a Trip;
- this does not change `ended_at`;
- evidence remains explicitly manual/no-photo;
- audit captures requester, approver, reason and timestamps.

---

# 7. End Work / Trip interaction

Preserve the approved D-07 behavior.

### If Trip is `IN_TRANSIT`

`End Work` is a review action.

Present:

- Continue Working
- explicit `End Work Anyway`

Continue Working:

- restores the existing active Trip state;
- does not create another Trip;
- does not modify Trip history.

End Work Anyway:

- Trip becomes `INTERRUPTED`;
- no fake Arrived event;
- Work Session may then continue through the applicable END odometer/end-work flow.

### If operational Trip is `ARRIVED`

Do not fabricate Activity completion.

RTE05 owns Activity execution and operational Trip completion.

If closing the Work Session from this state requires a product behavior not already defined by the approved baseline, STOP and report it rather than inventing an Activity outcome.

---

# 8. Odometer Storage / Security

Reuse existing storage primitives.

Do not create a generic platform-wide file registry solely for RTE04.

Required:

- private storage;
- authorized retrieval;
- tenant isolation;
- content-type/size validation;
- malware scanning where supported;
- no public permanent URL;
- preserve original evidence;
- protect evidence from cross-tenant access.

Exact RTE04 evidence table/layout is delegated to Development.

---

# 9. Roles & Permissions

Supervisor execution continues under the approved execution capability.

Admin exception approval must enforce:

`route.records.adjust`

Activate it only when real endpoints enforce it.

Do not grant Admin exception authority to normal Supervisors.

Authorization must remain server-side.

---

# 10. RTE04-C5 — Validation

Before producing the final completion candidate, validate the complete RTE04 scope.

Required evidence:

### Backend / domain
- full Trip integration suite;
- Work Session regression;
- START/END odometer state-machine tests;
- exception request/approval/rejection tests;
- one-time authorization tests;
- tenant isolation;
- permission tests;
- concurrent/idempotent behavior;
- migration/schema checks.

### Browser/mobile
Validate real resulting state for at least:

1. Start Work → select Trip → required pre-trip field → START odometer → Start Trip.
2. On Route → Change Plan → continue same Trip.
3. Operational Arrived → remains ARRIVED without Activity fabrication.
4. HOME → Arrived Home → Trip CLOSED / Work Session ACTIVE.
5. reload/reconnect resumes current Trip.
6. second device resolves same Trip.
7. START photo + manual confirmation.
8. START no-photo exception → Trip blocked.
9. Admin approves START exception → one-time manual entry → Trip can start.
10. END normal photo path.
11. END no-photo exception → Work Session ENDED with pending evidence.
12. later approved END manual entry → distance resolves without reopening session.
13. unauthorized Admin/Supervisor cannot access exception/photo outside scope.

### Regression
Run:

- full backend suite;
- frontend typecheck;
- frontend lint;
- production build;
- architecture/permission nets;
- browser E2E relevant to RTE03/RTE02-A01/RTE04.

Real iOS/Android hardware may remain separately `PENDING VALIDATION` if not available, but do not claim it as validated.

---

# 11. Known Pending Validation

Carry forward explicitly:

- real-device iOS/Android validation;
- offline odometer photo-binary capture is not implemented in RTE04;
- representative real-fleet OCR quality remains pending.

These do not authorize bypassing odometer integrity rules.

---

# 12. Do Not Change

Do not change:

- RTE03 Work Session lifecycle/time semantics;
- RTE02-A01 certified configuration behavior;
- one active Work Session per Supervisor;
- one non-terminal Trip per Work Session;
- HOME arrival behavior;
- Change Plan traceability;
- free-text field decisions;
- timing matrix approved by CER;
- official Routing Mileage definition;
- odometer as independent evidence;
- OCR as assistive only;
- END exception Option B.

Do not implement early:

- RTE05 Activity execution;
- Activity multi-select/timers;
- Outcome/Notes;
- GPS/geolocation;
- routing provider;
- official Routing Mileage;
- fuel calculation;
- Today/Live;
- Reports/export;
- route optimization;
- client/employee master catalogs;
- mid-session vehicle switching.

---

# 13. Deliverable

Do **not** create another CER-facing progress report merely because C1 closes or C2/C3 finishes.

Continue through the roadmap unless a STOP condition is reached.

The next expected CER-facing report is:

`Report Delivery Rodrigo/CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`

It must contain:

- actual implementation status C1–C5;
- Expected → Implemented → Evidence → Gap;
- data/API/UI impact;
- state transitions;
- permissions/security/audit;
- browser evidence;
- odometer evidence behavior;
- exception behavior;
- tests/regression;
- remaining `PENDING VALIDATION`;
- confirmation that RTE05 was not started.

Proposed status may only be:

`RTE04 — Completed / Ready for CER Certification`

if all required RTE04 behavior has evidence.

---

# 14. STOP Conditions

STOP and return to CER only if implementation requires a new product decision, including:

- changing the approved pre-trip/post-arrival timing;
- weakening required pre-trip fields before Start Trip;
- changing Trip terminal semantics;
- inventing a way to close an ARRIVED operational Trip without RTE05;
- weakening START odometer guard;
- reopening an ENDED Work Session for END odometer;
- making OCR authoritative;
- using odometer distance as Routing Mileage;
- creating a new generic platform file domain;
- implementing RTE05 or later scope early;
- any unresolved behavior whose answer would materially change user flow, state, data ownership, security or audit.

If no STOP condition occurs, continue C1 closure → C2 → C3 → C4 → C5, produce `CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`, and **STOP for CER validation**.
