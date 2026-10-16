# CER Route — RTE09 · Consolidated Reports + Fuel Estimate
## Development Instructions
### Revision 001

## 1. Context

RTE09 is the approved CER Route checkpoint for **Consolidated Reports + Fuel Estimate**.

The product baseline already contains:

- Work Sessions.
- Trips and Activities.
- Official Miles persisted through the mileage domain.
- Shared authoritative mileage read logic already used by Today / Live and Activity Explorer.
- Vehicle assignment and Work Session vehicle/Operational MPG snapshot.
- Fuel Grade on the vehicle domain.
- Existing business-day semantics based on `WorkSession.session_date`.
- Existing Admin navigation with the **Reports** destination defined in the V0.7 mockup.
- Existing Admin UX patterns established by V0.7, including responsive desktop/mobile behavior.
- Existing location, offline, mileage and audit rules.

RTE09 must **not** create another mileage formula or a parallel reporting truth.

It must consolidate the existing operational facts into the Reports experience approved in V0.7 and add the approved fuel-consumption / estimated-cost calculation.

---

# 2. Objective

Deliver the V0.7 **Reports** experience as one consolidated reporting model with:

- Supervisor filter;
- period filter;
- temporal grouping;
- Official Miles;
- time;
- activity count;
- activity-type distribution;
- estimated gallons;
- estimated fuel cost;
- Excel export.

The report must be consistent with Today / Live and Activity Explorer for the same underlying records.

---

# 3. UX Authority — V0.7

The V0.7 mockup is the **visual and interaction authority** for Reports.

Development must inspect the approved V0.7 source before implementing and reproduce:

- page structure;
- accordion behavior;
- section order;
- labels;
- spacing/hierarchy;
- filter placement;
- desktop behavior;
- mobile behavior;
- summary presentation;
- report-detail presentation;
- export action placement where shown.

Do not redesign Reports.

Do not replace the accordion with tabs, cards, a table-only interface, dashboards, charts or another reporting pattern unless V0.7 already shows it.

If the mockup contains a visual/interaction detail not repeated in this document, **the mockup wins**, provided it does not conflict with an explicit product rule below.

---

# 4. Current Product Rules to Preserve

## 4.1 One consolidated reporting model

RTE09 is not a library of independent fragmented reports.

The report must use one coherent reporting/read model that can answer the approved views and aggregations.

## 4.2 Official Miles

Official Miles come only from the existing authoritative mileage domain.

Reuse the shared mileage read rule already established for Today / Live and Activity Explorer.

Do not introduce:

- Haversine;
- GPS accumulated distance;
- odometer delta;
- client-side mileage calculation;
- a third meters→miles formula.

## 4.3 Business day

Grouping must use the existing authoritative CER Route business-day semantics.

`WorkSession.session_date` remains the reporting day authority.

Do not regroup by browser `new Date()`, UTC calendar day or report-generation time.

## 4.4 Multi-Activity execution

A Trip may have one Activity Execution containing multiple selected Activity Types.

For reporting:

- the execution block is one execution;
- its duration is counted once;
- Trip mileage is counted once;
- each selected Activity Type may contribute once to the **distribution by type**;
- multiple selected types must never multiply Trip miles, Work Session time or Activity Execution duration.

---

# 5. Scope

RTE09 includes:

1. Reports page implementation from V0.7.
2. Supervisor filtering.
3. Period filtering.
4. Week / Month / Year consolidated reporting as approved in V0.7.
5. Temporal grouping appropriate to the selected period.
6. Official Miles aggregation.
7. Time aggregation/presentation consistent with existing Route semantics.
8. Activity count.
9. Activity Type distribution.
10. Estimated gallons.
11. Estimated fuel cost.
12. Historical Fuel Reference resolution.
13. Excel export.
14. Required API/read-model/service support.
15. Roles/permissions for Reports.
16. Tests, audit and tenant isolation.
17. Reuse contract for authoritative mileage and fuel calculation.

---

# 6. Out of Scope

Do not add:

- maps;
- live tracking;
- new Today / Live behavior;
- new Activity Explorer behavior;
- odometer changes;
- OCR changes;
- routing-provider changes;
- continuous location tracking;
- hierarchy redesign;
- new Supervisor mobile operational flows;
- payroll;
- reimbursement;
- actual fuel purchases;
- fuel-card transactions;
- vehicle maintenance;
- route optimization;
- billing/invoicing;
- new charts not present in V0.7;
- a new external fuel scraping architecture inside Reports.

The external acquisition/update mechanism for fuel prices may remain a separate infrastructure/data-ingestion concern.

RTE09 consumes authoritative Fuel References through a defined contract.

---

# 7. Existing Components to Reuse

Before introducing new components, inspect and reuse the current baseline.

At minimum:

- Work Session domain.
- Trip domain.
- Activity Execution domain.
- Vehicle assignment.
- Work Session Vehicle/Operational MPG snapshot.
- Vehicle Fuel Grade.
- authoritative mileage model/read functions.
- `WorkSession.session_date`.
- tenant/product access model.
- Admin navigation/layout.
- existing browser/mobile responsive primitives.
- existing Excel/export utilities if available.
- existing audit infrastructure.

Do not duplicate Today / Live or Activity Explorer queries merely because Reports needs similar facts.

---

# 8. Report Filters

## 8.1 Supervisor

Reports must include the approved **Supervisor** filter.

Requirements:

- server-side tenant/scope enforcement;
- no cross-tenant Supervisor IDs;
- the frontend must not define security scope;
- selecting a Supervisor filters all report totals, detail and export consistently;
- if V0.7 defines an All/default behavior, reproduce it exactly.

Do not invent additional employee/client/location filters in this checkpoint.

## 8.2 Period

Use the approved V0.7 report periods:

- Week
- Month
- Year

Preserve the exact V0.7 control and navigation behavior.

The server determines range boundaries using the existing business-day/timezone rules.

---

# 9. Consolidated Report Metrics

For the selected Supervisor/period, the consolidated result must support:

## 9.1 Official Miles

Sum each eligible calculated Trip mileage exactly once.

Unresolved mileage must not become a fabricated numeric zero.

Preserve existing pending/unresolved semantics.

## 9.2 Time

Preserve the time semantics represented in V0.7 and the existing Route domain.

At minimum, the report must not confuse:

- Work Session span;
- driving/travel timestamps;
- Activity Execution duration.

If V0.7 presents a single consolidated Time metric, map it to the existing approved Route definition used by the mockup/baseline and document that mapping in the delivery report.

Do not invent a new time formula silently.

## 9.3 Activities

Provide:

- consolidated Activity Execution count;
- distribution by Activity Type.

For multi-select Activity Execution:

- count the execution block once in the execution total;
- include each selected Activity Type once in type distribution;
- never duplicate mileage or duration because multiple Activity Types were selected.

## 9.4 Fuel

Provide:

- Estimated Gallons;
- Estimated Fuel Cost.

See §11.

---

# 10. Temporal Aggregation

The consolidated report must support the grouping behavior required by the selected V0.7 period.

Expected reporting grain:

- Week → grouped by business day;
- Month → grouped consistently with the V0.7 month presentation;
- Year → grouped consistently with the V0.7 year presentation.

Do not create a different drill model from V0.7.

Totals must reconcile with their child groups.

Example invariant:

`sum(group Official Miles) = report Official Miles`

subject only to explicitly documented display rounding.

---

# 11. Fuel Estimate Business Rules

## 11.1 Formula

Approved deterministic formula:

```text
Estimated Gallons = Official Miles / Operational MPG

Estimated Fuel Cost = Estimated Gallons × Applicable Fuel Reference Price
```

This is an estimate, not an actual fuel purchase.

## 11.2 Miles source

Use Official Miles from the existing mileage domain.

Never use odometer delta as the fuel-estimate miles source.

## 11.3 MPG source

Use the **Operational MPG snapshot associated with the Work Session**, not the vehicle's current MPG value at report-generation time.

Historical reports must not change because the Vehicle master is edited later.

## 11.4 Fuel Grade

Fuel Grade is the standardized vehicle value:

- Regular
- Midgrade
- Premium
- Diesel

Fuel Reference selection must respect the applicable Fuel Grade.

Do not silently substitute another grade if the required grade is unavailable.

## 11.5 Applicable Fuel Reference

Fuel price varies by:

- location;
- date;
- Fuel Grade.

Use the authoritative historical Fuel Reference applicable to the Work Session/reporting fact.

The selected price/reference must preserve enough provenance so that a historical estimate does not silently change after:

- a later fuel-price import;
- a retroactive data correction;
- a new reference becoming available;
- edits to the current vehicle record.

The technical persistence strategy is Development's decision, but the historical result/provenance must remain stable once resolved.

At minimum the calculation must be traceable to:

- Fuel Reference identity or equivalent provenance;
- reference price used;
- Fuel Grade used;
- applicable geographic scope;
- applicable date/effective period;
- source where the current Fuel Reference domain supports it.

## 11.6 Missing input

Fuel estimate is **not available** when any required input is unresolved, including as applicable:

- Official Miles unresolved;
- Operational MPG missing/invalid;
- Fuel Grade missing;
- applicable Fuel Reference missing.

Do not invent a price.

Do not fall back to a national/default price unless such fallback is already an approved Fuel Reference rule in the existing data contract.

---

# 12. Fuel Estimate Display Rule

Preserve the existing product behavior already used in Today / Live:

> Missing or unresolved Estimated Fuel displays as `—`.

Do **not** use `0` to mean “unknown”.

A numeric zero may be shown only when the calculation is genuinely valid and the mathematical result is zero.

Examples:

```text
No applicable Fuel Reference
→ Estimated Fuel: —

MPG missing
→ Estimated Fuel: —

Mileage pending
→ Estimated Fuel: —

Valid inputs + 0.0 Official Miles
→ Estimated Gallons: 0
→ Estimated Fuel Cost: 0
```

This distinction must be preserved in API semantics as `null/unavailable` versus numeric `0`.

Do not make the frontend infer the difference from formatted strings.

---

# 13. Fuel Reference Integration Boundary

RTE09 must consume the authoritative Fuel Reference contract.

Do not couple Reports directly to:

- a scraper;
- a source website;
- a transient CSV file;
- a Scheduled Job implementation;
- a specific external fuel-price provider.

The report/domain contract should remain valid whether Fuel References arrive through:

- Scheduled Job;
- API;
- CSV/import;
- another approved ingestion mechanism.

If the current environment has no applicable reference for a record, the correct report behavior is `—`, not an invented estimate.

Tests must still prove the calculation path using controlled authoritative reference data.

---

# 14. Read Model / API

Implement a server-side report contract capable of returning the V0.7 Reports experience without excessive client-side reconstruction.

Exact endpoint/service structure is Development's decision.

The API must support, at minimum:

- period;
- anchor/reference date;
- Supervisor filter;
- consolidated summary;
- temporal groups;
- Activity Type distribution;
- report detail required by V0.7;
- fuel-estimate fields/status;
- export using the same underlying reporting rules.

The frontend must not recompute:

- Official Miles;
- fuel gallons;
- fuel cost;
- business-day grouping;
- permission scope.

---

# 15. Excel Export

RTE09 includes Excel export from the consolidated report.

The export must use the same server-side reporting truth as the screen.

Approved detailed columns:

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

- correct tenant/scope;
- selected period respected;
- selected Supervisor respected;
- chronological/business-day ordering;
- multi-selected activities represented without multiplying Trip miles or execution duration;
- unavailable fuel fields remain distinguishable from valid numeric zero;
- retired historical values remain readable;
- export totals/details reconcile with the visible report.

Do not create a separate export calculation engine.

---

# 16. Roles & Permissions

Reports belongs to the Admin experience.

Use the existing CER Route product role/capability architecture.

Required product behavior:

- authorized Admin/Route reporting role can access Reports;
- Supervisor operational role cannot access Admin Reports unless a separately approved capability already grants it;
- API authorization is server-side;
- navigation visibility, page access and API use the same effective capability.

If RTE09 introduces a new capability such as a Reports read capability, it must be integrated with the **existing-tenant capability alignment/reconciliation path**, not only bootstrap/seed for new tenants.

Do not recreate the previous stale-role-grant defect.

---

# 17. Security / Privacy / Audit

Validate:

- tenant isolation;
- server-side authorization;
- Supervisor filter cannot expand scope;
- no raw GPS coordinates are exposed in Reports unless V0.7 explicitly requires them — current baseline does not;
- Notes/References are returned only within authorized tenant/scope;
- export follows the same authorization;
- fuel provenance is auditable;
- no secrets/provider credentials appear in API/export;
- report generation does not mutate operational facts.

If report configuration or historical fuel-reference provenance is modified administratively, use existing audit infrastructure as applicable.

---

# 18. Data Model Impact

Development must first inspect the current data model.

Do not create duplicate reporting tables unless necessary.

Potential RTE09 data-model needs may include:

- Fuel Reference history/provenance;
- resolved fuel-calculation provenance/snapshot;
- indexes required for bounded report queries.

Development may choose the implementation, but it must guarantee:

1. historical estimates do not silently drift;
2. the report can identify which price/grade/date/geography produced the estimate;
3. missing inputs remain unresolved rather than fabricated;
4. tenant boundaries remain explicit;
5. migrations are backward compatible.

### Fuel Grade historical consistency

The approved baseline snapshots Vehicle and Operational MPG at Start Work, while Fuel Grade exists on the vehicle domain.

Development must verify whether the current model guarantees historical Fuel Grade consistency.

If editing a Vehicle's Fuel Grade could change a past report, RTE09 must close that gap by preserving the grade/provenance used for the historical calculation.

Do not leave this as an undocumented historical-data ambiguity.

---

# 19. Important Aggregation Rules

The following invariants are mandatory:

### Mileage

One Trip's `TripMileage` contributes once.

### Segments

Mileage segments are provenance, not extra miles.

Do not sum `TripMileage.total_meters` plus its segments.

### Multi-Activity

One execution with three selected Activity Types:

- 1 execution in total Activity Execution count;
- each selected type can receive one occurrence in type distribution;
- miles counted once;
- execution duration counted once.

### Pending mileage

Calculated Trips contribute Official Miles.

Unresolved Trips remain distinguishable and do not silently contribute a final zero.

### Fuel

Fuel is calculated from eligible Official Miles + the corresponding Work Session MPG + applicable historical Fuel Reference.

Do not use a period-level average MPG to replace Work Session-level inputs unless mathematically derived from the underlying per-session calculation.

For mixed vehicles/MPGs/prices, calculate at the appropriate lowest valid grain, then aggregate.

Do not calculate:

```text
Total Period Miles / one arbitrary MPG × one arbitrary price
```

when the period contains different vehicles, MPG values, Fuel Grades, locations or historical prices.

---

# 20. Edge Cases

Validate at minimum:

1. one Supervisor, one Work Session, one Trip;
2. several Trips same day;
3. several Work Sessions in selected period;
4. different vehicles/MPG values across the period;
5. different Fuel Grades across the period;
6. different historical Fuel Reference prices across dates;
7. different applicable geographic references;
8. multi-Activity execution;
9. Activity with long Notes/reference;
10. retired Activity Type remains historically readable;
11. calculated + pending mileage in same period;
12. no mileage;
13. zero-mile valid Work Session;
14. missing MPG;
15. missing Fuel Grade;
16. missing Fuel Reference;
17. valid mathematical zero;
18. Work Session crossing midnight;
19. month/year boundaries;
20. multiple Supervisors;
21. unauthorized Supervisor filter value;
22. cross-tenant identifier attempt;
23. export with missing fuel values;
24. export with multi-Activity execution;
25. empty report period.

---

# 21. Acceptance Criteria

RTE09 is ready for CER certification only when:

1. Reports reproduces the approved V0.7 UX.
2. Accordion structure/interactions match V0.7.
3. Desktop matches V0.7.
4. Mobile matches V0.7.
5. Supervisor filter works and is server-scoped.
6. Week report works.
7. Month report works.
8. Year report works.
9. Business-day grouping uses the authoritative server rule.
10. Official Miles reconcile with the existing mileage domain.
11. No duplicate miles from joins/multi-Activity/segments.
12. Time semantics are documented and match the approved baseline.
13. Activity Execution count is correct.
14. Activity Type distribution is correct.
15. Multi-selected Activity Types do not multiply miles/time.
16. Estimated Gallons uses Official Miles / Work Session Operational MPG.
17. Estimated Fuel Cost uses the applicable historical Fuel Reference.
18. Fuel Grade is respected.
19. Historical fuel estimate/provenance does not silently change.
20. Missing/unresolved fuel estimate displays `—`.
21. Valid numeric zero remains distinguishable from unavailable.
22. Mixed MPG/grade/price periods aggregate correctly from the appropriate grain.
23. Excel uses the same reporting truth as the UX.
24. Excel contains the approved columns.
25. Screen and export reconcile.
26. Tenant isolation passes.
27. Report authorization passes.
28. Existing-tenant capability alignment is handled if a capability is added.
29. Today / Live remains unchanged.
30. Activity Explorer remains unchanged.
31. Mileage engine remains unchanged.
32. Existing location/offline behavior remains unchanged.
33. Affected regression is green.
34. No unexplained `PARTIAL`, `GAP`, `BLOCKED` or unresolved product decision remains inside RTE09.

---

# 22. Tests Required

At minimum implement discriminating tests for:

## Reporting

- Supervisor filter;
- Week;
- Month;
- Year;
- business-day boundary;
- empty period;
- cross-midnight Work Session;
- temporal-group totals reconcile.

## Mileage

- one Trip counted once;
- two Trips aggregate correctly;
- segments do not duplicate total;
- multi-Activity join does not duplicate mileage;
- pending + calculated behavior.

## Time / Activities

- execution count;
- duration counted once;
- multi-select Activity Type distribution;
- retired Activity Type historical readability.

## Fuel

- exact formula;
- Work Session MPG snapshot vs changed current Vehicle MPG;
- different MPG values in same period;
- Fuel Grade-specific reference;
- historical date-specific reference;
- geographic reference;
- missing MPG → unavailable;
- missing grade → unavailable;
- missing reference → unavailable;
- valid zero → numeric zero;
- unresolved → API null/unavailable and UX `—`;
- historical calculation/provenance stability.

## Authorization

- authorized Admin;
- unauthorized Supervisor;
- cross-tenant Supervisor ID;
- export authorization;
- navigation/page/API consistency.

## Export

- approved columns;
- period filter;
- Supervisor filter;
- values reconcile with API/UX;
- multi-Activity does not duplicate miles/duration;
- missing estimate not converted to fake zero.

## Browser

- V0.7 Reports desktop;
- V0.7 Reports mobile;
- accordion interaction;
- filters;
- `—` fuel display;
- Excel action.

Tests must be discriminating. Removing the shared mileage rule, fuel rule, tenant scope or multi-Activity protection must cause tests to fail.

---

# 23. Do Not Change

Do not change:

- V0.7 Reports design;
- Today / Live;
- Activity Explorer;
- My Route operational flow;
- RTE10-A02 location gate;
- Official Miles definition;
- routing/TomTom behavior;
- odometer rules;
- OCR;
- Work Session uniqueness;
- offline queue;
- location evidence/recovery;
- hierarchy model;
- vehicle assignment rules outside the historical fuel-consistency need described here.

Do not introduce actual fuel reimbursement/purchase semantics.

---

# 24. Checkpoints

Development may execute RTE09 internally in small checkpoints, but the final deliverable must close the full RTE09 scope.

Recommended verification sequence:

### RTE09-CP1 — V0.7 Reports inventory + current data audit

- inspect V0.7 Reports;
- inventory exact UX;
- audit current reporting/mileage/fuel data components;
- identify only real data-model deltas.

### RTE09-CP2 — Consolidated read model/API

- Supervisor + period;
- Week/Month/Year;
- miles/time/activities/distribution;
- tenant/authorization.

### RTE09-CP3 — Fuel Estimate

- historical reference resolution;
- MPG/Fuel Grade;
- gallons/cost;
- immutable provenance;
- `—` vs numeric zero.

### RTE09-CP4 — V0.7 Reports UX + Excel

- desktop/mobile;
- accordion;
- filters;
- export;
- responsive fidelity.

### RTE09-CP5 — Regression + Closure Evidence

- integration;
- browser;
- authorization;
- export;
- historical/provenance;
- Expected → Implemented → Evidence → Gap.

These are execution checkpoints, not permission to leave RTE09 Partial.

---

# 25. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE09_CONSOLIDATED_REPORTS_FUEL_ESTIMATE_REPORT_001.md`

Include:

1. Executive Result
2. V0.7 Reports UX Inventory
3. Existing Components Reused
4. Consolidated Reporting Read Model
5. Supervisor / Period Filters
6. Temporal Aggregation
7. Official Miles
8. Time / Activity Semantics
9. Activity Type Distribution
10. Fuel Estimate Formula
11. Fuel Reference Resolution
12. Historical Fuel Provenance
13. Missing Estimate `—` vs Numeric Zero
14. API
15. V0.7 Desktop
16. V0.7 Mobile
17. Excel Export
18. Roles / Permissions / Existing-Tenant Alignment
19. Security / Tenant Isolation
20. Tests / Regression
21. Expected → Implemented → Evidence → Gap
22. Remaining Issues
23. Proposed Status

Include at least one end-to-end evidence case showing:

```text
Supervisor
→ Work Session/session_date
→ Vehicle/Operational MPG
→ Fuel Grade
→ Trips
→ Official Miles
→ applicable Fuel Reference
→ Estimated Gallons
→ Estimated Fuel Cost
→ Report API
→ V0.7 Reports UX
→ Excel row(s)
```

Do not expose raw coordinates or provider secrets.

---

# 26. Proposed Status Rule

If all acceptance criteria are green:

`RTE09 CONSOLIDATED REPORTS + FUEL ESTIMATE COMPLETE / READY FOR CER VALIDATION`

Development must not declare RTE09 closed.

CER owns final certification.

If a genuine product decision is discovered:

`RTE09 BLOCKED — CER DECISION REQUIRED`

with:

`fact → impact → options → recommendation`

Do not leave RTE09 in an unexplained Partial state.

---

# 27. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE09_CONSOLIDATED_REPORTS_FUEL_ESTIMATE_REPORT_001.md`

**STOP.**

Do not start RTE10.

Do not start RTE11.

Do not redesign Today / Live or Activity Explorer.

Wait for CER review and validation.
