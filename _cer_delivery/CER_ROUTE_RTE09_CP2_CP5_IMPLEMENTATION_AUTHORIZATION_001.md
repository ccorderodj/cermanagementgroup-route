# CER Route — RTE09 · Implementation Authorization
## CP2–CP5 Coding Instruction
### Revision 001

## 1. Context

This instruction authorizes Development to proceed with the implementation of **RTE09 CP2 through CP5**.

The baseline remains:

- `CER_ROUTE_RTE09_CONSOLIDATED_REPORTS_FUEL_ESTIMATE_INSTRUCTIONS_001.md`
- `CER_ROUTE_RTE09_CONSOLIDATED_REPORTS_FUEL_ESTIMATE_REPORT_001.md` — CP1 audit/decision gate
- Approved UX reference: **CER Route Mockup V0.7**

Do not create a new planning phase.

The CP2–CP5 checkpoints already defined in the original RTE09 instruction remain valid. This document resolves the product decisions discovered in CP1 and authorizes coding through the final RTE09 candidate.

Development may execute CP2–CP5 continuously and deliver one final closure report.

---

# 2. Objective

Complete RTE09 by implementing:

- the V0.7 Reports experience;
- consolidated reporting read model/API;
- Supervisor and period filters;
- Week / Month / Year reporting;
- Official Miles;
- Activity time;
- Activity count;
- Activity Breakdown by visit purpose;
- Excel export;
- Operational State required for future fuel-price matching;
- historical Fuel Grade / State preservation;
- Fuel Reference persistence contract in the database;
- Est. Fuel fields in Reports prepared to consume future database fuel prices.

Fuel-price ingestion itself is **not part of RTE09**.

---

# 3. Product Decisions — Final

## D-1 — Operational State

**APPROVED**

Add an **Operational State** to the Supervisor configuration/domain.

Purpose:

- identify the state whose fuel price applies to the Supervisor's Work Session;
- avoid deriving state from company address, vehicle name or GPS.

Requirements:

- standardized U.S. state code;
- nullable/configurable initially;
- tenant scoped;
- editable by authorized administration;
- frozen into the Work Session when `Start Work` occurs.

Expected historical flow:

```text
Supervisor.operational_state
        ↓ Start Work
WorkSession.operational_state_snapshot
```

Changing a Supervisor's Operational State later must not rewrite previous Work Sessions.

Do not derive this value dynamically from the current Supervisor record when producing historical reports.

---

# 4. Fuel Grade Historical Consistency

The CP1 finding is confirmed:

Current Vehicle Fuel Grade alone is insufficient for historical reporting.

RTE09 must preserve the Fuel Grade applicable to the Work Session.

Expected behavior:

```text
Vehicle.fuel_grade
       ↓ Start Work
WorkSession.fuel_grade_snapshot
```

Vehicle edits performed later must not alter historical Fuel Estimate inputs.

Use an additive/backward-compatible migration.

For legacy Work Sessions, Development must choose the safest compatible backfill/migration approach based on the existing frozen vehicle relationship and actual repository data.

Document the chosen approach and any limitation in the final report.

---

# 5. Fuel Reference — Database Contract Only

RTE09 must create or complete the persistent **Fuel Reference** domain in PostgreSQL.

Fuel prices are intended to be loaded later by a **Cron Job / Scheduled Job**.

RTE09 Reports must not:

- call an external fuel-price provider;
- scrape fuel prices;
- own the cron;
- require an administrator to enter prices manually;
- depend on a Fuel Reference UX to work.

The application must consume fuel-price data only after it exists in the database.

Conceptual contract:

```text
fuel_reference
────────────────────────
tenant / applicable scope
state_code
fuel_grade
price_per_gallon
effective_date
source
loaded_at
provenance / source reference as appropriate
```

Development determines exact schema, keys, indexes and constraints.

The design must support historical rows rather than a single mutable current price.

Example:

```text
GA | Regular | 2026-10-05 | 2.91
GA | Regular | 2026-10-12 | 2.87
NC | Regular | 2026-10-12 | 2.83
```

Do not overwrite historical references merely because a newer price arrives.

---

# 6. Fuel Price Ingestion — Out of Scope

The future flow is:

```text
External source
      ↓
Cron / Scheduled Job
      ↓
Fuel Reference rows in PostgreSQL
      ↓
CER Route backend
      ↓
Fuel Estimate
      ↓
Reports
```

RTE09 only prepares the database/domain contract and reporting consumption path.

Do not build the cron job in this checkpoint.

Do not build a provider-specific integration inside Reports.

Do not implement manual Fuel Reference entry UX in this checkpoint.

The V0.7 Fuel Reference configuration screen is therefore **not part of this RTE09 delivery**.

It may be considered separately later for viewing/history/administrative overrides if CER authorizes it.

---

# 7. Fuel Estimate Behavior

The approved future formula remains:

```text
Estimated Gallons = Official Miles / Operational MPG

Estimated Fuel Cost =
    Estimated Gallons × Applicable Fuel Reference Price
```

Inputs:

- Official Miles from the existing authoritative mileage domain;
- Operational MPG snapshot from Work Session;
- Fuel Grade snapshot from Work Session;
- Operational State snapshot from Work Session;
- applicable historical Fuel Reference from PostgreSQL.

Do not use:

- odometer delta;
- Haversine;
- browser calculations;
- current Vehicle MPG;
- current Supervisor State;
- current Vehicle Fuel Grade;
- national/regional fallback unless separately approved.

---

# 8. Missing Fuel Reference — Current Product Rule

Until an applicable Fuel Reference exists in the database:

```text
Estimated Fuel Cost displayed = 0
```

This is the current CER product decision.

However, the system must distinguish internally between:

```text
estimated_fuel_cost = 0
status = waiting_reference
```

and:

```text
estimated_fuel_cost = 0
status = calculated
```

A zero caused by missing fuel-price data must **not** be frozen as a final historical calculation.

When the required Fuel Reference later becomes available, the Work Session/reporting result must be eligible to resolve to the real estimate.

Development may choose the exact status naming/model, but the semantic distinction is mandatory.

Do not use `—` for missing Fuel Reference in RTE09 unless another unrelated missing-input rule already requires it and CER explicitly approves that case.

The final report must document the exact API representation used to distinguish:

- waiting for reference;
- calculated zero;
- calculated positive value.

---

# 9. Historical Fuel Estimate Resolution

Once all required inputs exist:

- Official Miles;
- Operational MPG snapshot;
- Fuel Grade snapshot;
- Operational State snapshot;
- applicable Fuel Reference;

the estimate may be resolved.

Once a real Fuel Reference has been used, preserve sufficient provenance so that the historical result remains traceable.

At minimum retain or make traceable:

- Work Session;
- state used;
- Fuel Grade used;
- MPG used;
- Official Miles used;
- Fuel Reference identity;
- price used;
- effective date;
- source/provenance;
- gallons;
- estimated cost;
- calculation timestamp/status.

Development decides whether this is best represented through a dedicated estimate table, immutable snapshot fields, or another repository-consistent design.

The required product outcome is:

> a real historical estimate must not silently change because a newer fuel price is inserted later.

---

# 10. Fuel Reference Matching Rule

When fuel data exists, resolve by:

1. same Operational State;
2. same Fuel Grade;
3. effective date not later than the Work Session `session_date`;
4. select the most recent applicable reference.

Conceptually:

```text
state_code = WorkSession.operational_state_snapshot
AND fuel_grade = WorkSession.fuel_grade_snapshot
AND effective_date <= WorkSession.session_date
ORDER BY effective_date DESC
LIMIT 1
```

No state match:

- remain `waiting_reference`;
- display Est. Fuel Cost = 0.

No approved regional or national fallback exists.

---

# 11. Reports UX — V0.7 Is Authoritative

CP1 confirmed that Reports V0.7 does **not** use an accordion.

Implement the actual approved V0.7 design.

Required structure:

- `Reports`
- subtitle / approved supporting text
- `Export Excel`
- Supervisor selector with `All Supervisors` default where shown
- Week / Month / Year tabs
- current-period legend
- 4 KPIs:
  - Total miles
  - Activity time
  - Activities
  - Est. fuel cost
- left reporting card:
  - By day / By week / By month according to selected range
- right reporting card:
  - Activity Breakdown
- responsive V0.7 mobile layout

Do not implement an accordion.

Do not redesign the page.

Do not add previous/next period navigation.

The API may keep an anchor/reference date for future extensibility, but no new navigation is added to V0.7 UX.

---

# 12. Activity Breakdown — Final Decision

**APPROVED: V0.7 behavior**

The visible Reports Activity Breakdown is by **visit purpose**, not by selected Activity Type.

Rows:

- Client Visit
- Employee Visit
- Recruiting
- Check Delivery
- Office
- Other

Each row may show the V0.7 measures:

- Miles
- Time
- Events
- Est. Cost

The selected operational activities inside an Activity Execution remain distinct data.

They may appear in:

- API detail/counts where useful;
- Excel `Activity Type` column.

They must not replace the visible V0.7 Purpose breakdown.

Do not multiply:

- Trip miles;
- execution duration;
- event count

because multiple activities were selected within one execution.

---

# 13. Reporting Read Model

Build one consolidated server-side reporting model.

Reuse existing authoritative logic for:

- Official Miles;
- business day;
- period grouping;
- Activity time;
- tenant scope;
- authorization.

Do not create a parallel reporting truth.

The exact repository/query/service implementation is Development's decision.

The frontend must not calculate:

- miles;
- report period boundaries;
- activity duration;
- Fuel Estimate;
- tenant scope.

---

# 14. Periods

Implement exactly:

- Week
- Month
- Year

Use the same grouping semantics already established in Activity Explorer where applicable.

Reports shows the **current** Week / Month / Year as V0.7 defines.

No previous/next controls in this checkpoint.

Use authoritative server-side business-day/date semantics.

Do not use browser-local `new Date()` as reporting authority.

---

# 15. Official Miles

Reports must reuse the existing shared mileage logic already used by Today / Live and Activity Explorer.

Mandatory invariants:

- one calculated TripMileage counted once;
- no duplicate miles through joins;
- segments are provenance, not additional miles;
- multi-Activity execution does not multiply miles;
- unresolved mileage remains truthful;
- no Haversine;
- no odometer fallback;
- no new conversion constant/formula.

For the same source data, Reports must reconcile with Today / Live and Activity Explorer.

---

# 16. Activity Time and Counts

Use the existing Activity Explorer definition for Activity time unless the repository demonstrates a different approved V0.7 rule.

Expected baseline:

- completed Activity Execution duration;
- execution counted once;
- multiple selected activities do not multiply duration.

The final report must state the exact reused time definition.

Do not silently invent a new formula.

---

# 17. Excel Export

Implement Excel export as defined in the original RTE09 instruction.

Approved columns:

- Date
- Supervisor
- Vehicle
- Activity Type
- Reference
- Start
- End
- Duration
- Trip Miles
- Operational MPG
- Fuel Grade
- Reference Fuel Price
- Estimated Gallons
- Estimated Fuel Cost
- Outcome
- Notes

Requirements:

- same authorization as Reports;
- same Supervisor filter;
- same period;
- same business-day semantics;
- same Official Miles;
- same Fuel Estimate semantics;
- no duplicate rows that multiply miles/time because of multi-Activity;
- historical/retired values remain readable.

For `waiting_reference`:

- Est. Fuel Cost follows the approved visible `0` behavior;
- Reference Fuel Price must remain clearly distinguishable as unavailable, not fabricated.

Do not insert a fake fuel price of `0` merely to make the multiplication work.

---

# 18. Roles & Permissions

Use the existing planned capabilities:

- `route.reports.read`
- `route.reports.export`

Do not implement `route.fuelreference.manage` as an active UX capability in this checkpoint because manual Fuel Reference management is not being built.

Reports belongs to the Admin experience.

Supervisor role does not receive Reports access unless an already-approved role template explicitly says otherwise.

Any newly activated Reports capability must use the existing-tenant reconciliation/alignment mechanism.

Do not rely only on new-tenant bootstrap/seed.

Navigation, page and API must use the same effective capability.

---

# 19. Security / Tenant Isolation

Mandatory:

- server-side tenant scope;
- no cross-tenant Supervisor access;
- Supervisor filter cannot expand scope;
- export uses same scope as Reports;
- no raw GPS coordinates in Reports/Excel;
- no provider secrets;
- no direct external fuel-source credentials;
- historical Fuel Reference rows tenant/scope safe;
- report reads must not mutate operational facts except controlled fuel-estimate resolution if the chosen design requires it.

Audit sensitive administrative changes as appropriate.

---

# 20. Data / Migration Requirements

Expected RTE09 data impact now includes at least:

- Supervisor Operational State;
- Work Session Operational State snapshot;
- Work Session Fuel Grade snapshot;
- Fuel Reference historical storage;
- any fuel-estimate/provenance structure Development determines necessary;
- supporting indexes/constraints.

Migrations must be:

- additive where possible;
- backward compatible;
- tenant safe;
- tested against existing data.

Do not rename/drop unrelated operational data.

---

# 21. CP2–CP5 Authorization

The CP2–CP5 checkpoints from the original RTE09 instruction are **authorized now**.

Development should proceed continuously:

## CP2 — Consolidated read model/API

Implement:

- Supervisor filter;
- Week / Month / Year;
- totals;
- groupings;
- Official Miles;
- time;
- Activity Breakdown;
- permissions;
- tenant isolation.

## CP3 — Fuel readiness/domain

Implement:

- Operational State;
- State snapshot;
- Fuel Grade snapshot;
- Fuel Reference database contract;
- matching/resolution logic;
- waiting-reference status;
- historical provenance model;
- Est. Fuel calculation path.

Do **not** implement the cron.

Do **not** implement manual Fuel Reference UX.

## CP4 — V0.7 Reports UX + Excel

Implement:

- V0.7 desktop;
- V0.7 mobile;
- filters;
- KPIs;
- current-period grouping;
- Activity Breakdown by purpose;
- Est. Fuel field with current `0` waiting behavior;
- Excel export.

## CP5 — Regression + Closure Evidence

Complete:

- integration;
- browser;
- Excel;
- authorization;
- tenant isolation;
- migration;
- historical-data behavior;
- Expected → Implemented → Evidence → Gap.

Do not stop for another CER decision unless a genuinely new product blocker is found.

---

# 22. Acceptance Criteria

RTE09 is ready for CER validation only when all of the following are true:

1. Reports matches the approved V0.7 UX.
2. No accordion is introduced.
3. Supervisor filter works.
4. `All Supervisors` works where V0.7 defines it.
5. Week works.
6. Month works.
7. Year works.
8. No previous/next period UX is added.
9. Official Miles reuse the existing authoritative mileage logic.
10. Same source data reconciles across Reports / Today / Activity where comparable.
11. No double-counting from joins, segments or multi-Activity.
12. Activity time uses the approved existing definition.
13. Activity count is correct.
14. Activity Breakdown is by Purpose.
15. Selected Activities remain available for Excel/detail without multiplying miles/time.
16. Supervisor Operational State exists.
17. Operational State is snapshotted into Work Session.
18. Fuel Grade is snapshotted into Work Session.
19. Historical state/grade do not drift after later edits.
20. Fuel Reference persistence exists in PostgreSQL.
21. Fuel Reference supports history/effective dates.
22. Reports does not call an external fuel provider.
23. Cron/provider ingestion is not coupled into Reports.
24. Missing Fuel Reference produces Est. Fuel Cost = 0 as the current visible product behavior.
25. Missing Fuel Reference is internally distinguishable from a valid calculated zero.
26. A missing reference remains eligible for future calculation after data arrives.
27. Valid Fuel Reference resolves by State + Fuel Grade + effective date.
28. No regional/national fallback is introduced.
29. Once calculated with a real Fuel Reference, sufficient provenance is retained.
30. Newer fuel references do not silently rewrite previously finalized historical estimates.
31. Excel contains the 16 approved columns.
32. Excel and screen reconcile.
33. `route.reports.read/export` are enforced server-side.
34. Existing tenants receive approved report capabilities through reconciliation.
35. Supervisor role remains outside Admin Reports unless already authorized.
36. Tenant isolation passes.
37. Mobile V0.7 passes.
38. Desktop V0.7 passes.
39. Existing Today / Live remains unchanged.
40. Existing Activity Explorer remains unchanged.
41. RTE10-A02 remains unchanged.
42. Mileage engine remains unchanged.
43. Offline/location behavior remains unchanged.
44. Affected regression is green.
45. No unexplained Partial / Gap / Blocked item remains within RTE09.

---

# 23. Tests Required

At minimum include discriminating tests for:

### Reports

- Week;
- Month;
- Year;
- All Supervisors;
- specific Supervisor;
- empty period;
- business-day boundary;
- cross-midnight Work Session;
- group totals reconcile.

### Mileage

- one Trip once;
- multiple Trips;
- no segment duplication;
- no multi-Activity duplication;
- calculated + unresolved behavior.

### Activity

- Purpose breakdown;
- execution count;
- duration once;
- multi-selected Activities preserved for detail/Excel.

### Operational State

- configured State snapshots on Start Work;
- later Supervisor edit does not change old Work Session;
- missing State behavior.

### Fuel Grade

- snapshot on Start Work;
- later Vehicle edit does not change old Work Session.

### Fuel Reference

- exact State match;
- exact Fuel Grade match;
- latest effective date <= session_date;
- no future reference selected;
- no national/regional fallback;
- missing reference → waiting status + visible cost 0;
- later reference arrival makes unresolved estimate eligible to calculate;
- calculated true zero remains distinguishable from waiting zero;
- historical finalized result/provenance stability.

### Permissions

- reports read;
- reports export;
- unauthorized Supervisor;
- existing-tenant alignment;
- cross-tenant IDs.

### Excel

- 16 columns;
- filters;
- period;
- same miles;
- same fuel semantics;
- multi-Activity not duplicated;
- unavailable Reference Fuel Price not fabricated.

### Browser

- V0.7 desktop;
- V0.7 mobile;
- Week/Month/Year;
- Supervisor filter;
- Purpose Activity Breakdown;
- Est. Fuel = 0 while waiting;
- Export action.

Mutation/discriminating coverage must prove that removing:

- mileage reuse;
- tenant scope;
- State snapshot;
- Fuel Grade snapshot;
- Fuel Reference date matching;
- multi-Activity protection

causes tests to fail.

---

# 24. Do Not Change

Do not change:

- Today / Live;
- Activity Explorer;
- RTE10-A02 location gate;
- My Route operational UX except the approved Supervisor configuration field needed here;
- Official Miles definition;
- TomTom/routing behavior;
- odometer/OCR;
- offline queue;
- location evidence/recovery;
- hierarchy;
- Work Session uniqueness.

Do not build:

- Fuel Reference manual configuration UX;
- fuel-price cron job;
- scraper/provider integration;
- regional/national fallback;
- GPS-to-state resolution.

---

# 25. Deliverable

Update/complete:

`Report Delivery Rodrigo/CER_ROUTE_RTE09_CONSOLIDATED_REPORTS_FUEL_ESTIMATE_REPORT_001.md`

The final report must replace the CP1 decision-gate status with the actual as-built RTE09 result and include the sections required by the original instruction.

At minimum show one end-to-end reporting case:

```text
Supervisor
→ Operational State
→ Work Session
→ State snapshot
→ Vehicle / MPG snapshot
→ Fuel Grade snapshot
→ Trips
→ Official Miles
→ Fuel Reference lookup/result
→ waiting_reference OR calculated
→ Est. Fuel
→ Reports API
→ V0.7 UX
→ Excel
```

Also include a second evidence case where Fuel Reference does not yet exist and prove:

```text
visible Est. Fuel = 0
internal status != calculated
no fake price exists
future resolution remains possible
```

Do not expose provider secrets or raw coordinates.

---

# 26. Proposed Status Rule

If all acceptance criteria are green, Development may propose:

`RTE09 CONSOLIDATED REPORTS + FUEL READINESS COMPLETE / READY FOR CER VALIDATION`

Development must not declare RTE09 closed.

CER owns final certification.

If a genuinely new product decision is discovered:

`RTE09 BLOCKED — CER DECISION REQUIRED`

with:

`fact → impact → options → recommendation`

Do not stop for matters already resolved in this document.

---

# 27. STOP

After completing CP2–CP5 and updating:

`Report Delivery Rodrigo/CER_ROUTE_RTE09_CONSOLIDATED_REPORTS_FUEL_ESTIMATE_REPORT_001.md`

**STOP.**

Do not start RTE10.

Do not start RTE11.

Do not implement the fuel cron.

Wait for CER review and field validation.
