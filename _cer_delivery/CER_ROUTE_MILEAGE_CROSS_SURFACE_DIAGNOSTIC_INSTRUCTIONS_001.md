# CER Route — Cross-Surface Mileage Diagnostic & Correction
## Today / Live · Activity · Reports
### Product Owner Instructions for Development Agent
### Revision 001

## 1. Context

Field/product validation has identified a common symptom across CER Route administrative surfaces:

> **Miles are not being shown in Today / Live, Activity, and Reports.**

This must be treated first as a **cross-surface mileage data-path incident**, not as three independent UI defects.

The certified product rule for Official Miles remains unchanged:

- Official Miles come from the routing mileage domain;
- only successfully calculated road mileage is published as Official Miles;
- odometer delta is not Official Miles;
- Haversine/straight-line distance is not an Official Miles fallback;
- a pending calculation must not be silently represented as a final zero;
- a previously consolidated calculated mileage is a historical fact and must not be silently recalculated.

Do not redesign any of the affected pages.

---

# 2. Objective

Determine exactly where the mileage pipeline is breaking and apply the **smallest correction** required so that already-authorized Official Miles propagate truthfully to:

1. **Today / Live**
2. **Activity Explorer**
3. **Reports**, if that surface is currently implemented

The investigation must determine whether the problem originates in:

`capture / endpoints → mileage calculation → persistence → retry/sweeper → read model → API → frontend`

Do not begin by patching the three screens independently.

---

# 3. Important Scope Rule for Reports

Before changing Reports, establish its current as-built status.

If Reports is:

- implemented and consuming real CER Route data → include it in the correction;
- only a scaffold/placeholder or belongs to a later checkpoint not yet implemented → **do not build Reports in this task**.

In the second case, report:

`REPORTS NOT YET IMPLEMENTED / NOT PART OF THIS CORRECTION`

and continue diagnosing the shared mileage pipeline through Today / Live and Activity.

Do not pull RTE09+ scope into this incident.

---

# 4. Certified Mileage Semantics — Do Not Change

## 4.1 Official Miles

Official Miles are the persisted road-routing result for a Trip.

The calculation uses authoritative operational waypoints already defined by the Route domain.

Do not substitute:

- odometer delta;
- destination text;
- guessed address;
- raw GPS trace accumulation;
- Haversine;
- straight-line distance;
- a manually entered value.

## 4.2 Mileage states

Preserve the existing mileage lifecycle and actual technical enum names in the repository.

Conceptually the states are:

- Pending Calculation
- Calculated
- Not Calculable
- Calculation Failed

Only a successful calculated result contributes a numeric Official Miles total.

## 4.3 Pending is not zero

A Trip still awaiting calculation must not appear as a truthful final `0 mi`.

Where the certified surface already supports pending indication, preserve it.

Do not manufacture a mileage value merely to populate the UI.

## 4.4 Historical calculated results

If a Trip already has a valid calculated mileage record, do not recalculate it merely because the UI currently fails to display it.

Trace and fix the read/display path.

---

# 5. Mandatory Diagnostic Method

Use at least one **real affected Trip from the current development/shared tenant** where CER knows actual travel occurred.

Preferably trace two cases:

- one recent normal Trip;
- one historical Trip that should already have mileage.

For each selected Trip record:

```text
Tenant
→ Supervisor
→ Work Session
→ Trip
→ Start Trip evidence
→ Change Plan waypoint(s), if any
→ Arrived evidence
→ TripMileage
→ Mileage state
→ total_meters
→ segments/provenance
→ Today / Live read
→ Activity read
→ Reports read, if implemented
→ visible UI
```

Do not rely only on synthetic tests.

---

# 6. Diagnostic Checkpoints

## D1 — Confirm the exact affected records

For a real user/day where the issue is visible, identify:

- tenant/company;
- Supervisor;
- `session_date`;
- Work Session id;
- Trip id(s);
- Trip state;
- whether the Trip reached its terminal operational state;
- whether travel actually occurred according to the recorded workflow.

Record identifiers in the technical report as appropriate without exposing unnecessary sensitive data.

---

## D2 — Mileage persistence

For each affected Trip, inspect the actual mileage record.

Determine:

- does a `TripMileage`/current mileage record exist?
- current mileage state;
- `total_meters`;
- attempt count;
- next retry time if applicable;
- terminal reason if applicable;
- calculated timestamp if applicable;
- provider/method/version;
- whether segment rows exist.

Classify each affected Trip into exactly one branch:

### Branch A
`CALCULATED with total_meters > 0`

Meaning: mileage domain has the value; downstream read/display is wrong.

### Branch B
`PENDING`

Meaning: calculation pipeline has not completed.

### Branch C
`NOT CALCULABLE`

Meaning: required evidence was insufficient.

### Branch D
`CALCULATION FAILED`

Meaning: evidence existed but routing failed after the approved contingency.

### Branch E
`NO MILEAGE RECORD`

Meaning: calculation was never created/triggered or persistence is broken.

Do not proceed to frontend correction before this classification is known.

---

## D3 — Authoritative waypoint evidence

If mileage is not `CALCULATED`, inspect whether the Trip has the evidence required by the certified mileage engine:

- Start Trip point;
- each authoritative Change Plan waypoint, if applicable;
- Arrived point;
- evidence level/provenance;
- Missing Location events where applicable.

Determine whether the result is correctly pending/exceptional or whether a valid set of points exists and the engine failed to advance.

Do not fabricate missing points.

---

## D4 — Calculation trigger

Confirm how mileage calculation is initiated for the current Trip lifecycle.

Verify that closing/arriving a Trip actually schedules or invokes the mileage process expected by the current implementation.

Check for:

- missing trigger;
- transaction ordering issue;
- job not enqueued;
- retry metadata not initialized;
- event/command path that bypasses mileage;
- HOME / Change Plan path inconsistency.

If different Trip closure paths behave differently, document each path.

---

## D5 — Routing provider in the actual environment

Inspect the **actual current environment configuration and adapter selected at runtime**.

Do not assume the provider is unconfigured based on an older report.

Prove:

- which routing adapter is active;
- whether its required configuration is present;
- whether the application can reach it;
- whether a real route request succeeds;
- returned distance and status;
- whether errors are classified transient/permanent correctly.

Do not expose secrets in the report.

If the configured provider is healthy, continue downstream.

If it is not healthy, identify whether this is:

`APPLICATION CONFIGURATION`
or
`DEVOPS / ENVIRONMENT`

without changing product semantics.

---

## D6 — Retry / sweeper

For Trips in `PENDING`, verify the automatic resolution path.

Confirm:

- scheduler/job registration exists;
- the mileage sweep is actually running in the affected environment;
- due records are found;
- retry attempts advance;
- stale pending records do not remain indefinitely;
- successful retry becomes `CALCULATED`;
- exhausted retry reaches the correct truthful terminal state.

A green unit test is not sufficient if the deployed scheduler/job is not actually executing.

---

## D7 — Session / aggregate mileage read

If affected Trips are already `CALCULATED`, verify the existing aggregate/read contracts.

Trace:

`TripMileage.total_meters → miles conversion → session/day/supervisor aggregation`

Check:

- only correct tenant;
- correct Supervisor;
- correct `session_date`;
- `CALCULATED` status filtering;
- meters-to-miles conversion;
- decimal/rounding behavior;
- no accidental inner join dropping mileage rows;
- no filter using the wrong Trip/Work Session state;
- no current-date/UTC mismatch.

---

# 7. Today / Live Validation

The current Today / Live implementation is expected to source mileage from calculated Trip mileage for the business day.

Trace the exact affected Supervisor through:

`TripMileage → GET /api/live/today → official_miles / total_miles → rendered UI`

Verify:

1. API response contains the expected numeric value when a calculated Trip exists.
2. Supervisor row displays it.
3. Total Miles Today includes it.
4. Detail view displays the same authoritative total where applicable.
5. Pending mileage is represented truthfully using the already-certified pending behavior.
6. Desktop and mobile agree.

If API is correct and UI is wrong, classify as:

`TODAY/LIVE PRESENTATION/WIRING DEFECT`

If API is already wrong, correct the shared read model rather than patching labels.

---

# 8. Activity Explorer Validation

RTE08 maps Activity mileage from the Trip mileage domain.

Trace:

`TripMileage → Activity Explorer read contract → Day summary / Activity card → UI`

Verify:

1. a calculated Trip returns its mileage;
2. the day summary includes the correct miles;
3. the Activity card/stop shows the expected Trip miles where V0.7 requires them;
4. pending mileage is not presented as a final zero;
5. Year / Month / Week grouping does not lose mileage during aggregation;
6. Supervisor/date filters do not exclude the mileage relationship;
7. desktop and mobile remain faithful to V0.7.

If the shared TripMileage value is correct but Activity is wrong, classify the precise read-model or presentation defect.

Do not redesign Activity Explorer.

---

# 9. Reports Validation

First determine whether Reports is currently a real implemented read surface.

If implemented, trace:

`TripMileage → Reports backend/read model → report aggregation → rendered/exported result`

Verify all periods and supervisor filtering currently supported by the implementation.

At minimum prove that a calculated Trip included in the selected period contributes the same Official Miles value as Today / Live and Activity.

If Reports is not yet implemented, do not add it here.

Document that fact and stop that branch of the diagnostic.

---

# 10. Cross-Surface Consistency Rule

For the same Trip and same authoritative calculated mileage:

```text
Trip Official Miles
       │
       ├── Today / Live
       ├── Activity
       └── Reports (if implemented)
```

must represent the **same fact**.

Aggregates may differ only because the surfaces use different approved periods/groupings.

There must not be three independently calculated mileage definitions.

---

# 11. Root Cause Classification

The final report must classify the issue using one or more of:

- `MILEAGE RECORD NOT CREATED`
- `WAYPOINT EVIDENCE GAP`
- `ROUTING PROVIDER / ADAPTER`
- `ENVIRONMENT CONFIGURATION`
- `RETRY / SWEEPER NOT EXECUTING`
- `MILEAGE STUCK PENDING`
- `MILEAGE TERMINALISED TRUTHFULLY`
- `READ MODEL FILTER / JOIN DEFECT`
- `BUSINESS-DAY FILTER DEFECT`
- `UNIT CONVERSION / AGGREGATION DEFECT`
- `TODAY/LIVE UI WIRING DEFECT`
- `ACTIVITY UI WIRING DEFECT`
- `REPORTS UI/READ DEFECT`
- `REPORTS NOT IMPLEMENTED`
- `DEPLOYMENT / VERSION DRIFT`
- other, with evidence.

Do not use “miles not showing” as the root cause.

---

# 12. Correction Authorization

After the root cause is demonstrated, Development is authorized to make the **minimum correction** needed to restore already-certified mileage behavior.

Development may correct:

- missing wiring;
- incorrect query/filter/join;
- incorrect aggregation;
- missing calculation trigger;
- retry/sweeper execution bug;
- environment-aware adapter selection bug;
- UI binding defect;
- other technical defect that violates already-certified mileage semantics.

Development must STOP for CER if the proposed correction would require:

- changing what Official Miles means;
- introducing an odometer fallback;
- introducing Haversine/straight-line fallback;
- changing authoritative waypoint rules;
- altering Work Session / Trip / Activity business states;
- inventing new Reports functionality;
- changing V0.7 UX;
- changing historical mileage automatically.

---

# 13. Tests Required

## T1 — Real affected Trip trace

Provide one end-to-end trace from a real affected Trip through persistence and at least Today / Live + Activity.

Required.

## T2 — Calculated mileage propagation

Create/use a Trip with a known `CALCULATED` mileage value.

Assert exact propagation to:

- Today / Live API;
- Today / Live UI;
- Activity API;
- Activity UI;
- Reports API/UI if implemented.

Required.

## T3 — Pending mileage

Create/use a pending Trip.

Assert it is not presented as final zero.

Preserve each surface's approved pending behavior.

Required.

## T4 — Exceptional mileage

Validate at least one `not_calculable` or `calculation_failed` case to prove no fabricated mileage is shown.

Required.

## T5 — Business day

A Work Session crossing midnight must keep its mileage in its authoritative `session_date`.

Required.

## T6 — Multiple Trips

Two or more calculated Trips in one Work Session must aggregate correctly.

Required.

## T7 — Multiple Supervisors

Mileage from one Supervisor must not bleed into another.

Required.

## T8 — Tenant isolation

Tenant A mileage must not appear in Tenant B.

Required.

## T9 — Change Plan

A Trip with Change Plan waypoints must preserve the certified summed routed mileage.

Required if the underlying mileage engine is touched.

## T10 — Regression

Re-run the affected:

- mileage engine;
- Work Session / Trip;
- Today / Live;
- Activity Explorer;
- Reports tests if Reports exists;
- TypeScript/lint/build as applicable.

---

# 14. Do Not Change

Do not use this incident to change:

- RTE07 visual design;
- RTE08 visual design;
- V0.7 hierarchy;
- Official Mileage definition;
- odometer rules;
- OCR;
- location privacy behavior;
- role model;
- capability alignment;
- fuel calculation;
- hierarchy/data scope;
- Reports scope if not already implemented;
- RTE09+.

---

# 15. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_MILEAGE_CROSS_SURFACE_DIAGNOSTIC_REPORT_001.md`

The report must include:

1. Executive Result
2. Field Symptom Reproduced
3. Real Affected Trip Trace
4. Mileage Persistence State
5. Waypoint Evidence
6. Calculation Trigger
7. Runtime Routing Provider / Environment
8. Retry / Sweeper
9. Today / Live Trace
10. Activity Explorer Trace
11. Reports Trace / Current Status
12. Root Cause
13. Correction Applied, if authorized
14. Cross-Surface Consistency
15. Tests / Regression
16. Expected → Implemented → Evidence → Gap
17. Remaining Issues
18. Proposed Status

For each affected surface use:

`expected value → API value → rendered value → classification`

---

# 16. Status Rule

If a shared defect is found and corrected, and all applicable surfaces are green:

`MILEAGE CROSS-SURFACE CORRECTION COMPLETE / READY FOR CER VALIDATION`

If the data is truthfully not calculable because required evidence is missing:

`MILEAGE DATA EXCEPTION CONFIRMED — NO FABRICATED VALUE`

and explain the affected Trips and reason.

If resolution requires a new product decision:

`MILEAGE CROSS-SURFACE REVIEW BLOCKED — CER DECISION REQUIRED`

with:

`fact → impact → options → recommendation`

Do not leave unexplained blank mileage as acceptable.

---

# 17. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_MILEAGE_CROSS_SURFACE_DIAGNOSTIC_REPORT_001.md`

**STOP.**

Do not start RTE09.

Do not resume RTE10-A01.

Do not redesign Today / Live or Activity.

Wait for CER review.
