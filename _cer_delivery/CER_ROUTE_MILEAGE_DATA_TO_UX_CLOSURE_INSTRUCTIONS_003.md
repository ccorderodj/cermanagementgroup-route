# CER Route — Mileage Data-to-UX Final Closure
## Today / Live + Activity Explorer
### Product Owner Instructions for Development Agent
### Revision 003

## 1. Context

CER confirms the following as the current starting point:

- TomTom routing is already connected.
- When CER Route sends the required routing coordinates, TomTom returns the road-distance result.
- The mileage result is already persisted in PostgreSQL.
- The existing extraction/query previously used by Development demonstrated that the database can return the calculated mileage and related routing fields.
- Historical sample rows may already have been deleted; they are not required for this closure.
- The current product problem is that mileage that exists at data level is not being surfaced reliably in the administrative UX.

Therefore, **do not treat this task as a routing-provider installation problem**.

This task is the final closure of the path:

`persisted mileage → read model/query → API → UX`

This work does **not reopen RTE06** and does not redefine Official Miles.

---

# 2. Objective

Make persisted Official Miles available consistently in the existing CER Route administrative surfaces:

1. **Today / Live**
2. **Activity Explorer**

and leave the mileage read contract reusable by the future Reports module.

The final result must prove that one mileage fact stored in the database is the same mileage fact presented by the APIs and UX.

---

# 3. Confirmed Product Rule

The authoritative mileage source is the existing mileage domain.

Use the existing persisted mileage result, including the current repository names such as:

- `TripMileage`
- `TripMileage.total_meters`
- mileage state
- mileage segments/provenance where required for audit

Do not calculate Official Miles again in the frontend or in a second reporting formula.

Do not substitute:

- odometer delta;
- Haversine / straight-line distance;
- destination text;
- GPS trace accumulation;
- client-side calculations.

Odometer remains separate evidence.

---

# 4. Existing SQL / Extraction as Diagnostic Reference

Development already has the SQL/SELECT that produced the previous mileage CSV.

Use that query as a **diagnostic reference** to understand the relationships and prove which persisted fields contain the expected mileage.

Do not automatically make that entire denormalized SELECT the production API contract.

Important:

If the query joins Trips, Activities, events or other one-to-many records, the same mileage may appear on several rows.

Therefore:

- never sum repeated event-level rows as if each were a new Trip;
- aggregate Official Miles once per authoritative Trip mileage record;
- for a Work Session/day, sum each eligible calculated Trip exactly once;
- if `TripMileage.total_meters` already represents the full Trip, do not also add its segment distances to the same total;
- segment rows are provenance/audit detail, not an additional mileage fact.

Development must explicitly prove that the final read model cannot double-count mileage because of joins.

---

# 5. First Step — Trace One Calculated Record

Use the next available real or controlled Trip that reaches a successful calculated mileage state.

For that single Trip record the following chain must be demonstrated:

```text
company / tenant
→ supervisor
→ Work Session
→ session_date
→ Trip
→ TripMileage
→ state = calculated
→ total_meters
→ converted Official Miles
→ Today / Live API
→ Today / Live UX
→ Activity API
→ Activity UX
```

Use identifiers and numeric values in the closure report.

Do not include raw coordinates unless strictly necessary for debugging, and do not place them in the final report.

---

# 6. Determine Where the Current Break Exists

For the same calculated Trip compare:

```text
DATABASE VALUE
    ↓
READ MODEL VALUE
    ↓
API VALUE
    ↓
RENDERED VALUE
```

Classify the actual defect precisely.

## Case A — Database has mileage, read model does not

Correct the query/read model.

Inspect:

- joins;
- mileage-state filter;
- Work Session relationship;
- Trip relationship;
- tenant/company filter;
- Supervisor filter;
- `session_date`;
- date/time boundary;
- accidental inner joins;
- duplicate rows;
- grouping.

## Case B — Read model/API has mileage, UI does not

Correct frontend mapping/rendering only.

## Case C — Today / Live works but Activity does not

Correct the Activity read path while preserving the shared mileage semantics.

## Case D — Activity works but Today / Live does not

Correct the Today / Live read path while preserving the shared mileage semantics.

## Case E — Both APIs already return the expected value

Verify deployed frontend/version and determine why the visible environment differs.

Do not create a second mileage implementation.

---

# 7. Shared Mileage Read Logic

Prefer one reusable server-side mileage aggregation rule rather than duplicating business logic per screen.

The implementation detail is Development's decision, but the product invariant must be:

```text
Calculated TripMileage
        ↓
shared authoritative aggregation
        ├── Today / Live
        ├── Activity Explorer
        └── future Reports
```

The shared rule must be capable of returning, as applicable:

- Official Miles per Trip;
- Official Miles per Work Session/business day;
- Official Miles per Supervisor and period;
- whether unresolved mileage exists (`mileage_pending` or existing equivalent).

Do not introduce a new persistence table merely for UI convenience unless Development can demonstrate it is necessary.

A repository/service/query/read-model abstraction is acceptable.

---

# 8. Today / Live Requirements

Today / Live must consume persisted calculated mileage.

For the current business day:

### Per Supervisor

Return/display:

- `official_miles`
- existing pending indicator when one or more relevant Trips are unresolved

### Summary

Return/display:

- `total_miles`

Rules:

1. sum each calculated Trip once;
2. use `WorkSession.session_date` as the business-day authority;
3. unresolved Trips must not become final zero silently;
4. mileage from another Supervisor must not bleed into the row;
5. mileage from another tenant must never appear;
6. Work Sessions with zero Trips remain valid and show truthful zero/no mileage according to the existing UX.

Desktop and mobile must show the same underlying value.

Do not redesign Today / Live.

---

# 9. Activity Explorer Requirements

Activity Explorer must consume the same authoritative mileage fact.

### Day view

The day's mileage summary must equal the calculated mileage belonging to that Supervisor/business day.

### Activity / stop presentation

Where V0.7 requires mileage on the activity/stop card, show the appropriate Trip mileage.

Important:

A Trip may contribute mileage to the day total even if it has no Activity Execution card.

That is not lost mileage.

### Week / Month / Year

Aggregates must be built from the same authoritative calculated Trip mileage without double counting.

Do not redesign Activity Explorer.

---

# 10. Reports Boundary

The Reports module is not part of this closure if its actual UI/API has not yet been implemented.

Do **not** build the Reports screen in this task.

However, the mileage read logic produced here must be reusable by Reports later.

Document the intended reusable contract, for example conceptually:

```text
supervisor
period
work_session
trip
official_miles
mileage_state/pending
```

The future Reports implementation must consume this same mileage source rather than invent another mileage formula.

---

# 11. Pending / Exceptional Mileage

Preserve existing semantics.

A Trip that is not yet calculated must not be represented as a truthful final numeric zero.

Use the existing product behavior for:

- pending calculation;
- not calculable;
- calculation failed.

This closure is primarily about surfacing already-calculated persisted mileage, not redefining exception handling.

---

# 12. Business-Day Semantics

All administrative mileage grouping must follow the authoritative `WorkSession.session_date`.

A Work Session crossing midnight remains associated with its start/business date according to the existing certified rule.

Do not regroup mileage using UTC `CURRENT_DATE` or browser calendar date independently.

---

# 13. Tenant / Authorization

All reads remain server-side tenant scoped.

Validate:

- tenant A cannot retrieve tenant B mileage;
- Supervisor A mileage does not appear under Supervisor B;
- existing RTE07/RTE08 capability rules remain unchanged.

Do not modify role architecture or capability alignment in this task.

---

# 14. Mandatory Validation Scenarios

## MV-01 — One real calculated Trip

Database contains a calculated mileage with positive `total_meters`.

PASS required.

## MV-02 — DB → Today / Live API

The same Trip contributes the expected Official Miles to the correct Supervisor/day.

PASS required.

## MV-03 — Today / Live API → UX

Desktop and mobile display that value.

PASS required.

## MV-04 — DB → Activity API

The same Trip contributes the expected Official Miles to the correct day.

PASS required.

## MV-05 — Activity API → UX

The visible Activity experience displays/aggregates the same value.

PASS required.

## MV-06 — Multiple Trips

At least two calculated Trips in one Work Session/day aggregate correctly and each Trip is counted once.

PASS required.

## MV-07 — Join duplication protection

Create or use a Trip associated with multiple joined rows/events/activities and prove that mileage is not duplicated.

PASS required.

## MV-08 — Pending plus calculated

One calculated Trip + one unresolved Trip:

- calculated miles remain visible;
- unresolved mileage remains truthfully indicated;
- unresolved Trip is not silently counted as zero final.

PASS required.

## MV-09 — Cross-midnight Work Session

Mileage remains under authoritative `session_date`.

PASS required.

## MV-10 — Tenant / Supervisor isolation

No cross-tenant or cross-supervisor leakage.

PASS required.

---

# 15. Tests Required

Add or adjust discriminating tests at the layer where the actual defect is found.

At minimum cover:

- Trip mileage → Today / Live aggregation;
- Trip mileage → Activity aggregation;
- two Trips summed once each;
- event/activity join does not multiply mileage;
- calculated + pending combination;
- business-day boundary;
- Supervisor isolation;
- tenant isolation;
- desktop/mobile rendering where UI code changes.

Run affected regression for:

- mileage;
- Work Session / Trip;
- Today / Live;
- Activity Explorer;
- authorization/wiring;
- frontend typecheck/build when applicable.

Do not count synthetic green tests as final evidence without also showing one persisted calculated Trip through the actual read path.

---

# 16. Development Autonomy

Development decides the best technical implementation after inspecting the current repository.

Acceptable approaches may include:

- fixing the existing query;
- extracting a reusable repository/read service;
- introducing a dedicated read model;
- refactoring duplicated aggregation logic;
- using an SQL view if technically justified.

Do not impose a PostgreSQL VIEW simply because the previous extraction used SQL.

The mandatory outcome is one authoritative mileage fact reaching all applicable consumers correctly and without duplication.

---

# 17. Do Not Change

Do not change:

- TomTom/routing business semantics;
- Official Miles definition;
- RTE06 state machine;
- odometer rules;
- OCR;
- fuel calculation;
- location/privacy rules;
- roles/capabilities;
- hierarchy;
- Today / Live design;
- Activity V0.7 design;
- Reports UI;
- historical calculated mileage values.

---

# 18. Acceptance Criteria

This Mileage closure is ready for CER certification only when:

1. a persisted real/controlled calculated Trip is demonstrated;
2. its `total_meters` and Official Miles are known;
3. Today / Live API returns the correct value;
4. Today / Live displays the correct value;
5. Activity API returns the correct value;
6. Activity displays/aggregates the correct value;
7. multiple Trips aggregate once each;
8. joins cannot duplicate mileage;
9. pending mileage remains truthful;
10. business-day semantics remain correct;
11. tenant/Supervisor isolation remains correct;
12. no new mileage formula was introduced;
13. no odometer/Haversine fallback was introduced;
14. affected regression is green;
15. no unexplained gap remains in the DB → API → UX path.

No `PARTIAL` closure.

---

# 19. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_MILEAGE_DATA_TO_UX_CLOSURE_REPORT_003.md`

Include:

1. Executive Result
2. Starting Data Fact
3. Existing SQL/Extraction Assessment
4. Authoritative Mileage Source
5. Root Cause Found
6. Read Model / Query Correction
7. Today / Live Trace
8. Activity Explorer Trace
9. Duplication / Aggregation Validation
10. Pending Behavior
11. Tenant / Supervisor Isolation
12. Tests / Regression
13. Expected → Implemented → Evidence → Gap
14. Remaining Issues
15. Proposed Status

For the principal validation record show:

```text
Trip ID
→ TripMileage state
→ total_meters
→ Official Miles
→ Today / Live API value
→ Today / Live rendered value
→ Activity API value
→ Activity rendered/aggregate value
```

No raw coordinates or secrets in the report.

---

# 20. Status Rule

If all criteria are green, propose:

`ROUTE MILEAGE DATA-TO-UX CLOSURE COMPLETE / READY FOR CER CERTIFICATION`

Do not declare `ROUTE MILEAGE CLOSED`; CER owns final certification.

If a real product decision is unexpectedly required:

`ROUTE MILEAGE CLOSURE BLOCKED — CER DECISION REQUIRED`

with:

`fact → impact → options → recommendation`

---

# 21. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_MILEAGE_DATA_TO_UX_CLOSURE_REPORT_003.md`

**STOP.**

Do not start Reports.

Do not start RTE09.

Do not resume RTE10-A01.

Wait for CER review.
