# CER Route — RTE06 Geolocation + Mileage Engine
## Developer / Agent Instructions — Revision 002
## Supersedes `CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_INSTRUCTIONS_001.md`

---

# 1. Context

RTE05 is **COMPLETED / CERTIFIED**.

Before beginning RTE06, CER completed the odometer/OCR pre-flight:

`Report Delivery Rodrigo/CER_ROUTE_ODOMETER_OCR_PREFLIGHT_001.md`

The pre-flight confirmed:

- START odometer behavior with an applicable vehicle is **AS-BUILT / CONFIRMED**.
- The My Route odometer banner/capture flow is **AS-BUILT / CONFIRMED**.
- Photo → reading → Supervisor confirmation → `PHOTO_CONFIRMED` → Trip unblocked is **AS-BUILT / CONFIRMED**.
- OCR wiring exists, but production OCR is **not active**; runtime uses `NoSuggestionReader`.
- The previously observed absence of the odometer banner was caused by **CONFIGURATION / TEST DATA**, not a regression.
- No certified RTE04/RTE05 odometer behavior is missing.

CER has also made two subsequent decisions:

1. **OCR productivo is required before production**, but it is **not part of RTE06**. It is tracked separately as `RTE10-A01 — Odometer OCR Production Hardening & Validation`.
2. `vehicle_assignment.effective_from` **must participate in determining the vehicle applicable at Start Work**.

CER also refined the official mileage rule for `Change Plan`.

This revision incorporates those decisions.

---

# 2. Authoritative Baseline

Use as authoritative baseline:

- `CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_001.md`
- Certified RTE02 / RTE02-A02
- Certified RTE03
- Certified RTE04
- Certified RTE05
- `CER_ROUTE_ODOMETER_OCR_PREFLIGHT_001.md`
- This Revision 002, which **supersedes the earlier RTE06 instruction where it differs**

## CER-approved delta to RTE01 D-02

The original RTE01 mileage endpoint rule defined:

`Start Trip → Arrived`

CER has now approved the following refinement for Trips containing `Change Plan`:

> **Official Trip mileage is the sum of routed road-distance segments through the ordered authoritative location waypoints of the Trip: Start Trip → each Change Plan in occurrence order → Arrived.**

This does **not** create multiple Trips.

This does **not** make destination text an endpoint.

This does **not** convert breadcrumbs into official mileage.

This is an approved product refinement for RTE06 and must be treated as authoritative.

---

# 3. Current State

The current certified product already provides:

- tenant isolation;
- authentication / authorization;
- Route access model;
- Supervisor + Administrador operational My Route;
- Work Session lifecycle;
- one ACTIVE Work Session invariant;
- occurrence-time semantics;
- durable offline action queue;
- Trip lifecycle;
- Change Plan lifecycle;
- HOME lifecycle;
- odometer START/END evidence;
- Activity execution;
- Complete / Leave;
- Outcomes;
- Check Delivery Received By rules;
- Workbench `What's next?`;
- exact RTE05 card/grid UX.

RTE06 introduces:

- location evidence;
- staged acquisition;
- Missing Location Event;
- Trip mileage waypoints;
- road-routing mileage;
- mileage lifecycle;
- retry / contingency / sweeper;
- historical mileage provenance.

---

# 4. Objective

Implement CER Route's production **Geolocation + Official Mileage Engine** while preserving all previously certified operational flows.

RTE06 must:

1. capture location evidence silently at approved lifecycle events;
2. never block the Supervisor because GPS/location acquisition fails;
3. distinguish Fresh / Degraded Cached / Recovered / Missing honestly;
4. correlate evidence to the exact lifecycle action that triggered it;
5. build the authoritative waypoint sequence for each Trip;
6. calculate official `Miles` as routed road distance across that ordered waypoint sequence;
7. preserve the entire logical Trip distance when the Supervisor uses Change Plan;
8. drive every mileage calculation to a terminal state;
9. keep historical mileage immutable;
10. preserve enough provenance for audit after raw location evidence is eventually purged;
11. leave stable read contracts for later Admin/Reports checkpoints without implementing them here.

---

# 5. Scope

## In Scope

### Baseline correction before geolocation
- effective-dated vehicle assignment resolution at Start Work;
- validation that Work Session vehicle/MPG snapshot uses the assignment effective at the occurrence time of Start Work.

### Location evidence
- Start Work;
- Start Trip;
- each Change Plan;
- Arrived;
- Complete Activity;
- Leave Activity;
- End Work;
- Fresh Point;
- Degraded Cached Point;
- Recovered Point;
- Missing Location Event;
- Recovery Window;
- permission-state evidence;
- offline synchronization;
- End Work bounded recovery.

### Official mileage
- authoritative Trip waypoint sequence;
- Start Trip waypoint;
- zero or more Change Plan waypoints;
- Arrived waypoint;
- road-routing adapter;
- segment calculation;
- Trip total calculation;
- plausibility;
- Pending / Calculated / Not Calculable / Calculation Failed;
- retry / contingency;
- sweeper;
- immutable mileage provenance.

### Supporting capabilities
- API/service contracts;
- tenant isolation;
- authorization;
- audit;
- regression;
- provider evaluation;
- technical validation inventory.

---

# 6. Out of Scope

Do not implement in RTE06:

- production OCR engine;
- `RTE10-A01`;
- Admin Today/Live UI;
- Activity Explorer;
- Reports UI;
- fuel price ingestion;
- fuel estimate reporting;
- Admin mileage correction UI;
- map rendering;
- route optimization;
- navigation / turn-by-turn;
- geocoding;
- reverse geocoding;
- Places;
- continuous GPS tracking as official mileage;
- odometer reconciliation with routed mileage;
- raw-location retention duration;
- production purge schedule based on an invented duration;
- new Route roles;
- new business contexts;
- a Route-specific notification inbox.

---

# 7. Existing Components to Reuse

Reuse where appropriate:

- RTE03 durable offline queue;
- existing action idempotency contract;
- Work Session occurrence-time semantics;
- current-state reconciliation;
- Trip lifecycle;
- Change Plan append-only history;
- RTE04 vehicle / assignment / odometer models;
- RTE04 Work Session vehicle + MPG snapshot;
- RTE05 My Route flow;
- Core audit primitives;
- existing platform scheduler;
- existing configuration pattern;
- existing tenant resolution;
- existing permission model.

Do not create a second queue, second scheduler, second audit mechanism, second Trip state machine, or second access model.

---

# 8. Confirmed Requirement — Vehicle Effective Dating

This must be corrected/validated **before relying on the Work Session vehicle snapshot in RTE06**.

## 8.1 Applicable assignment rule

At an instant `T`, a vehicle assignment applies when:

`effective_from <= T`

and:

`effective_to IS NULL OR T < effective_to`

For Start Work, `T` is the **real occurrence time of Start Work**, not merely server receipt time.

## 8.2 Required behavior

### Future assignment
A future assignment must not apply before `effective_from`.

### Active assignment
An assignment whose effective interval contains the Start Work occurrence time applies.

### Ended assignment
An assignment with `effective_to <= Start Work occurrence time` does not apply.

### No applicable assignment
The Work Session may still start.

Result:

- `vehicle_id = null`
- odometer = `NOT_REQUIRED`
- no fake vehicle is assigned

### Applicable assignment
The Work Session snapshots:

- vehicle;
- operational MPG;
- other already-certified vehicle snapshot fields.

The snapshot is historical and immutable for that Work Session.

A later Admin assignment change must not retroactively change an already-started Work Session.

## 8.3 Overlap invariant

The effective-dated assignment model must not permit two vehicle assignments for the same Supervisor to be simultaneously effective for the same instant.

How that invariant is implemented is delegated to Development, but it must be server-side and covered by discriminating tests.

Do not retain a misleading definition of "current" that means only `effective_to IS NULL` if that contradicts the effective-date rule above.

---

# 9. OCR Boundary

OCR is **not part of RTE06**.

Preserve the currently certified odometer rules:

- applicable vehicle → START odometer unresolved before first Trip;
- Start Trip blocked until resolved;
- primary evidence = photo;
- OCR suggestion is assistive only;
- Supervisor confirms/corrects the reading;
- official reading is the Supervisor-confirmed value;
- valid photo + manual reading remains photo-backed even if OCR returns no suggestion;
- no-photo path remains the controlled Admin exception.

`NoSuggestionReader` may remain during RTE06.

Do not select, install, or activate a production OCR engine in this checkpoint.

Production OCR is tracked under:

`RTE10-A01 — Odometer OCR Production Hardening & Validation`

---

# 10. Location Capture Events

Attempt location evidence for these lifecycle events:

1. Start Work
2. Start Trip
3. **Change Plan**
4. Arrived
5. Complete Activity
6. Leave Activity
7. End Work

Do **not** add a required capture event to Start Activity.

Do **not** add a visible GPS step.

Location capture is a background side effect of the operational action.

---

# 11. Staged Acquisition Model

For every applicable lifecycle event:

1. attempt usable current/fresh location;
2. exhaust the implementation's normal current-location acquisition paths;
3. if current acquisition fails, evaluate technically available cached/last-known evidence;
4. cached evidence is eligible only if it meets configured freshness/accuracy criteria;
5. if no valid point exists, enter a bounded silent Recovery Window;
6. if recovery succeeds, persist a Recovered Point using its actual capture timestamp;
7. only after all stages are exhausted may the event become Missing.

The operational action must not wait for this process to complete.

## Evidence levels

Exactly:

- `fresh`
- `degraded_cached`
- `recovered`

`missing` is **not** a `location_fix.evidence_level`.

Missing means:

- no acceptable point exists;
- a `missing_location_event` is created.

The evidence level must be persisted at write time and never reconstructed later.

---

# 12. Supervisor UX

During normal work do not display:

- GPS captured
- GPS failed
- location unavailable
- timeout
- accuracy warning
- retry status
- Missing Location
- routing retry diagnostics

The Supervisor's work continues.

The browser/OS permission prompt still applies.

A one-time plain-language privacy/location explanation must occur before the first platform permission request, consistent with D-08.1.

It must not become a recurring operational message.

---

# 13. Location Privacy Boundary

Normal capture is allowed only while the Work Session is ACTIVE.

Enforce server-side.

Reject evidence that cannot be validly bound to:

- authenticated tenant;
- authenticated Supervisor;
- authoritative Work Session;
- valid lifecycle action.

## End Work exception

End Work itself is never delayed by location.

The Work Session may become ENDED immediately.

Only recovery already initiated for that specific End Work event may complete afterwards.

It:

- remains bounded;
- attaches only to that End Work action;
- cannot start new capture;
- cannot start breadcrumbs;
- cannot reopen the Work Session;
- may result in Recovered or Missing.

---

# 14. Lifecycle Event Correlation

Location evidence must be correlated to the exact action/event that caused it.

Do not correlate by nearest timestamp.

Reuse an existing durable action/idempotency/event identifier if suitable.

If the current architecture lacks a safe correlation key, implement the smallest domain-appropriate mechanism.

Required correlation targets include:

- Start Work action;
- Start Trip action;
- each individual Change Plan action;
- Arrived action;
- Activity Complete action;
- Activity Leave action;
- End Work action.

Multiple Change Plan actions in the same Trip must remain independently identifiable and ordered.

---

# 15. Official Mileage Definition

Official `Miles` is:

> **The sum of routed road-distance segments across the ordered authoritative waypoints of the Trip.**

## 15.1 No Change Plan

Waypoint sequence:

`Start Trip → Arrived`

Official Miles:

`route(Start Trip, Arrived)`

## 15.2 One Change Plan

Waypoint sequence:

`Start Trip → Change Plan #1 → Arrived`

Official Miles:

`route(Start Trip, Change Plan #1)`
`+ route(Change Plan #1, Arrived)`

## 15.3 Multiple Change Plans

Waypoint sequence:

`Start Trip → Change Plan #1 → Change Plan #2 → ... → Arrived`

Official Miles:

sum of road-routing distance between every consecutive waypoint.

Example:

`P0 → P1 → P2 → P3`

Official Miles:

`route(P0,P1) + route(P1,P2) + route(P2,P3)`

## 15.4 One Trip remains one Trip

Change Plan:

- does not close the Trip;
- does not create a replacement Trip;
- does not create a second Work Session;
- does not create separate independent official Trip mileage facts.

The Trip has one final official mileage result composed from one or more routed segments.

---

# 16. Change Plan Location Rule

Every Change Plan while `IN_TRANSIT` is also an authoritative location waypoint attempt.

The system must initiate location acquisition for the Change Plan event at the time of the change.

The capture must be silent and use the same:

Fresh → Degraded Cached → Recovery → Recovered → Missing

model.

## Important

The waypoint is the **actual location evidence associated with Change Plan**.

The new destination/context entered by the Supervisor is **not** the location endpoint.

Do not geocode the destination text.

Do not infer coordinates from:

- destination text;
- client data;
- employee data;
- office data;
- previous location;
- next location.

---

# 17. Change Plan + Missing Location

If a Change Plan occurred and its authoritative waypoint remains Missing after the Recovery Window is exhausted:

- preserve the Change Plan itself;
- preserve its Missing Location Event;
- do not remove it from history;
- do not silently skip the missing waypoint;
- do not calculate the Trip as if the change never occurred;
- do not substitute destination text;
- do not substitute breadcrumb distance;
- do not substitute Haversine;
- do not substitute odometer.

Because the system no longer has sufficient evidence to reconstruct the entire approved waypoint sequence, the Trip must eventually reach:

`Not Calculable`

with a truthful terminal reason.

This is intentional.

CER prefers a truthful `Not Calculable` over an incomplete number presented as complete mileage.

---

# 18. Start Trip / Arrived Rules

## Start Trip
The eligible location evidence associated with Start Trip is the first authoritative mileage waypoint.

## Arrived
The eligible location evidence associated with Arrived is the final authoritative mileage waypoint.

## HOME
HOME follows the same mileage model:

`Start Trip → zero or more Change Plan waypoints → Arrived Home`

HOME still closes on Arrived.

No Activity block is created.

---

# 19. Interrupted Trip

If the Trip becomes `INTERRUPTED` without Arrived:

- do not fabricate an Arrived waypoint;
- do not use End Work as the arrival endpoint;
- do not infer an endpoint;
- do not manufacture mileage.

The mileage lifecycle must reach the truthful terminal exception applicable to insufficient required evidence.

Do not create a Missing Location Event for an Arrived event that never occurred.

---

# 20. What Is NOT Official Mileage

Never use as official Miles:

- odometer distance;
- Haversine / straight-line distance;
- GPS trace length;
- breadcrumbs;
- destination text;
- geocoded destination;
- reverse-geocoded address;
- client master data;
- inferred office coordinates;
- a point borrowed from another lifecycle event;
- a point from another Trip.

Odometer remains an independent Work Session/vehicle evidence source.

---

# 21. Breadcrumbs

Breadcrumbs are optional supporting evidence.

If implemented:

- only while Work Session ACTIVE;
- only while Trip IN_TRANSIT;
- only under the technically permitted foreground/visible conditions;
- low frequency;
- stop when Trip/session ends;
- never become official mileage;
- never replace missing Start Trip / Change Plan / Arrived waypoints.

If not required to deliver RTE06, document that choice rather than adding unnecessary continuous collection.

---

# 22. Routing Provider

CER does not prescribe the provider.

Development must evaluate and select/recommend the technical approach.

Required architecture:

- routing backend-side;
- no credential in Supervisor client;
- provider behind adapter/port;
- domain independent from vendor payloads;
- explicit timeout/error mapping;
- bounded retries;
- observability;
- cost/quota awareness;
- replaceable provider.

Document:

- candidates;
- selected/recommended provider;
- coverage;
- routing quality;
- latency;
- availability;
- quota/cost;
- privacy;
- licensing;
- credentials;
- operational complexity;
- vendor lock-in;
- outage behavior.

If production use requires unapproved spend, contract, or credentials:

- preserve provider-neutral architecture;
- document blocker;
- STOP for external approval.

---

# 23. Routing Segments

Each consecutive waypoint pair produces one logical road-routing segment.

Example:

- segment 1 = Start Trip → Change Plan 1
- segment 2 = Change Plan 1 → Change Plan 2
- segment 3 = Change Plan 2 → Arrived

The implementation may persist segment-level records or equivalent immutable segment provenance.

CER does not prescribe the storage shape.

The final result must make it possible to audit:

- waypoint order;
- coordinates actually routed;
- evidence level of each waypoint;
- capture time;
- accuracy;
- provider;
- method/version;
- distance returned for each segment;
- final Trip total.

---

# 24. Mileage Lifecycle

Exactly these states:

- `Pending Calculation`
- `Calculated`
- `Not Calculable`
- `Calculation Failed`

Definitions:

### Pending Calculation
Transitory.

The system still has an automatic path to resolution.

### Calculated
Terminal success.

All required authoritative waypoints exist and every required routed segment produced a valid, plausible distance.

### Not Calculable
Terminal exception.

Required waypoint evidence is insufficient.

Examples:

- Start Trip Missing;
- Arrived Missing;
- any Change Plan waypoint Missing after recovery;
- Trip INTERRUPTED without required final endpoint.

### Calculation Failed
Terminal exception.

All required waypoint evidence exists, but routing failed to produce a valid result after the bounded contingency path is exhausted.

`Degraded` is quality/provenance metadata, never a mileage state.

No Trip may remain Pending indefinitely.

---

# 25. Segment Failure Rules

If one segment has valid waypoints but the provider temporarily fails:

- Trip mileage remains Pending;
- retry that unresolved segment according to the bounded contingency strategy;
- do not discard already-valid segment provenance;
- do not publish a partial total as final official Miles.

If one required segment permanently fails routing after contingency:

- entire Trip mileage → `Calculation Failed`.

If a required waypoint is permanently Missing:

- entire Trip mileage → `Not Calculable`.

---

# 26. Plausibility

Every routed segment must pass plausibility before consolidation.

Haversine may be used only internally as a diagnostic comparison if useful.

Never publish it as official mileage.

A suspicious routing segment must not be consolidated.

Retry/contingency continues until:

- valid segment result;
- or terminal exception.

Do not hardcode RTE01's indicative thresholds as CER-approved constants.

Thresholds must be configurable and their validation status documented.

---

# 27. Mileage Immutability

Once the Trip mileage becomes `Calculated`:

- no automatic recalculation;
- no provider change alters it;
- no map-data update alters it;
- no threshold change alters it;
- no retry alters it;
- no duplicate job alters it;
- no later breadcrumb alters it.

Future Admin correction belongs to a later controlled scope.

---

# 28. Purge-Safe Provenance

Historical `Calculated` mileage must remain fully explainable after raw location evidence is eventually purged.

Retain enough immutable provenance to explain:

- waypoint order;
- each routed segment;
- coordinates used;
- evidence level for every waypoint;
- capture timestamps;
- accuracy;
- degraded/recovered condition;
- provider;
- method/version;
- segment distances;
- total distance;
- calculation timestamp;
- relevant anomaly/quality indicators.

Raw fix IDs may be retained as soft references, but:

- must not be the only provenance;
- future purge must not delete mileage;
- future purge must not block on a hard dependency;
- future purge must not make mileage unauditable.

Do not invent a retention duration.

---

# 29. Missing Location Event

Create one append-only Missing Location Event when an actual lifecycle event exhausts all location acquisition paths.

Retain as applicable:

- tenant/company;
- Supervisor;
- Work Session;
- Trip;
- lifecycle action ID;
- event kind;
- occurrence timestamp;
- reason code;
- acquisition attempt evidence;
- permission-state evidence;
- last-known/cached metadata;
- notification status.

Reason codes must describe only observable facts.

Do not invent causes such as "GPS hardware off" if the platform cannot prove them.

Every underlying Missing Location Event remains preserved even if notifications are later grouped.

---

# 30. Notification Boundary

D-01 requires in-platform notification of confirmed Missing Location Events, with email optional.

RTE06 must:

- persist Missing Location Event;
- preserve notification status;
- expose a clean internal contract/event for later notification delivery.

Do not create a Route-specific notification platform.

Do not claim D-01 notification delivery complete through email alone.

Admin notification surfacing belongs to the later Admin checkpoint unless a reusable generic platform notification capability already exists and can be reused without expanding this scope.

---

# 31. API / Services

Exact endpoint names are delegated.

Required capabilities:

1. synchronize location evidence linked to lifecycle action;
2. finalize Missing after Recovery Window exhaustion;
3. retrieve authoritative Trip mileage state/result;
4. retrieve ordered mileage waypoint/segment provenance where authorized;
5. trigger/retry calculation internally;
6. sweep stale Pending calculations;
7. expose downstream read/query contract for later Admin/Reports usage.

Server rules:

- tenant from authenticated context;
- authorization server-side;
- action ownership verified;
- no arbitrary cross-user evidence injection;
- duplicate submissions idempotent;
- stale/out-of-order evidence cannot bind to wrong event;
- coordinate ranges validated;
- occurrence time separate from receipt time;
- provider secrets never exposed.

---

# 32. Offline / Queue Integration

Reuse RTE03 queue.

Required:

- lifecycle actions may queue offline;
- location evidence may synchronize later;
- event correlation survives offline;
- `device_captured_at` remains actual capture time;
- `server_received_at` remains receipt time;
- cached/recovered evidence never becomes Fresh because upload happened later;
- Start Trip / Change Plan / Arrived evidence cannot bind to the wrong action;
- duplicate replay does not create duplicate mileage facts;
- reauthentication does not lose evidence;
- second-device transfer does not duplicate mileage waypoints.

Multiple queued Change Plans must preserve occurrence order.

---

# 33. Work Session / Day Mileage Read Contract

RTE06 should expose enough service/query behavior for later RTE07/Reports usage to obtain:

- Trip mileage state;
- Trip calculated Miles;
- Work Session sum of calculated Trip mileage;
- presence/count of unresolved or exceptional Trips.

Do not present a partial sum as if the Work Session were fully resolved.

No Today/Live UI is implemented here.

---

# 34. Roles & Permissions

Do not add a capability unless a demonstrated gap requires CER approval.

Operational location capture uses the existing execution authority.

Expected:

- Supervisor can produce evidence for their own Route flow;
- Administrador using operational My Route can do the same;
- arbitrary cross-user evidence submission rejected;
- cross-tenant rejected;
- background mileage jobs preserve tenant boundaries;
- no Admin location-management screen required.

---

# 35. Security / Audit

Required:

- tenant isolation;
- server-side authorization;
- coordinate validation;
- timestamp sanity;
- exact action correlation;
- explicit provenance;
- append-only location evidence semantics;
- append-only Change Plan history;
- no coordinate fabrication;
- no silent historical mileage mutation;
- provider secrets server-side;
- avoid raw coordinates in ordinary logs/errors;
- audit Missing Location Event creation;
- audit mileage state transitions;
- audit terminalization;
- audit provider/method used;
- preserve enough identifiers for investigation.

Do not claim GPS spoofing is impossible.

Suspicious data may be marked/analyzed, not labeled "verified location".

---

# 36. Web / Mobile Requirements

Preserve the RTE05 My Route UX.

No new GPS screen.

No map.

No extra confirmation step.

No spinner that blocks the operational action while waiting for location.

Change Plan must remain the same user-facing flow:

`Change Plan → choose new context → context fields → return to On Route`

Location capture occurs silently as a side effect.

Do not add a visible "capture waypoint" step.

---

# 37. Use Cases / Required Scenarios

## Effective dating

### E1 — Future assignment
- assignment effective tomorrow;
- Start Work today;
- vehicle not applied;
- odometer NOT_REQUIRED.

### E2 — Current assignment
- effective_from <= occurrence time;
- effective_to null or later;
- vehicle applied;
- odometer START pending.

### E3 — Ended assignment
- effective_to <= occurrence time;
- no applicable vehicle.

### E4 — Offline delayed Start Work
- Start Work occurrence while assignment A applies;
- command reaches server later after assignment changes;
- Work Session still snapshots assignment A based on occurrence time.

### E5 — No overlap
- attempt overlapping effective assignment periods;
- rejected server-side / persistence invariant.

## Location

### G1 — Fresh Start Work
Action succeeds; Fresh evidence attached to exact action.

### G2 — Permission denied
Action succeeds; no custom GPS error; fallback/recovery; Missing if exhausted.

### G3 — Cached fallback
Stored as `degraded_cached`, age/provenance preserved.

### G4 — Recovery succeeds
Stored as `recovered` with real timestamp.

### G5 — Recovery exhausted
Exactly one Missing Location Event; no fabricated coordinate.

## Mileage without Change Plan

### M1
Start Trip Fresh → Arrived Fresh → one routing segment → Calculated.

### M2
Start Trip Missing → Not Calculable.

### M3
Arrived Missing → Not Calculable.

## Mileage with Change Plan

### C1 — One Change Plan
Start Trip P0 → Change Plan P1 → Arrived P2.

Assert:

`Miles = route(P0,P1) + route(P1,P2)`

One Trip only.

### C2 — Two Change Plans
P0 → P1 → P2 → P3.

Assert ordered segments and summed total.

### C3 — Change Plan recovered
Change Plan has no immediate fix but recovers inside window.

Recovered waypoint is used with true timestamp/provenance.

### C4 — Change Plan Missing
Start/Arrived valid, Change Plan Missing.

Trip → Not Calculable.

Do not silently calculate Start→Arrived only.

### C5 — Change Plan offline
Change Plan queued offline.

Evidence/action reconcile later.

Waypoint remains in correct sequence.

### C6 — Duplicate Change Plan replay
Same idempotency key.

One purpose-change record, one corresponding waypoint event, no duplicate segment.

### C7 — Destination text changed
Different destination text must not change routing coordinates.

No geocoding.

### C8 — Change Plan then HOME
Same Trip, HOME semantics preserved, mileage through waypoint sequence.

## Routing / terminal states

### R1 — Provider transient failure
Pending → retry → Calculated.

### R2 — Permanent provider failure
All waypoints valid; contingency exhausted → Calculation Failed.

### R3 — No Pending forever
Sweeper resolves stale Pending.

### R4 — Implausible segment
Not consolidated; contingency continues.

### R5 — One segment fails
No partial final total; final state reflects failure.

## Historical integrity

### H1 — Immutability
Calculated mileage unchanged by provider/config/job replay.

### H2 — Raw fix purge simulation
Delete raw location evidence in test; final mileage + waypoint/segment provenance survive.

### H3 — Odometer independence
Odometer differs from routing total; official Miles unchanged.

## Lifecycle

### L1 — HOME
Mileage works; HOME closes on Arrived; no Activity.

### L2 — INTERRUPTED
No Arrived; no fabricated endpoint; truthful terminal mileage exception.

### L3 — Activity Complete
Location evidence captured; Activity logic unchanged.

### L4 — Activity Leave
Location evidence captured; Activity logic unchanged.

### L5 — End Work recovery
Session ends immediately; bounded event-scoped recovery only.

### L6 — Tenant isolation
No cross-tenant evidence/mileage access.

---

# 38. Technical Validation Inventory

Report actual evidence for:

- **V-1** real iOS Safari / Android Chrome lifecycle behavior;
- **V-2** real CER environment accuracy/acquisition sampling;
- **V-3** routing provider evaluation;
- **V-4** offline queue soak extended with location evidence;
- **V-5** distribution of Fresh / Degraded / Recovered / Missing.

Classify each:

- `CONFIRMED`
- `PENDING VALIDATION`
- `BLOCKED`

Desktop browser emulation is not real-device validation.

Do not convert unavailable evidence into PASS.

---

# 39. Acceptance Criteria

RTE06 may be proposed `Ready for CER Certification` only if:

1. effective_from is respected at Start Work;
2. effective_to is respected at Start Work;
3. Start Work vehicle snapshot uses occurrence time;
4. overlapping effective assignments cannot produce two applicable vehicles;
5. no-vehicle Work Session remains valid;
6. existing odometer behavior remains intact;
7. OCR production integration is not pulled into RTE06;
8. location capture is silent and non-blocking;
9. Fresh / Degraded / Recovered persisted explicitly;
10. Missing is separate;
11. no coordinate fabricated;
12. lifecycle correlation is exact;
13. Start Trip is first mileage waypoint;
14. every Change Plan is an authoritative mileage waypoint attempt;
15. Arrived is final mileage waypoint;
16. destination text is never a routing endpoint;
17. one Trip remains one Trip through Change Plan;
18. official Miles equals sum of routed consecutive waypoint segments;
19. Missing required Change Plan waypoint yields Not Calculable;
20. no silent Start→Arrived shortcut when a Change Plan waypoint is missing;
21. HOME follows the same segmented mileage rule;
22. INTERRUPTED does not fabricate arrival;
23. odometer remains independent;
24. Haversine never becomes official mileage;
25. breadcrumbs never become official mileage;
26. provider is backend-only and replaceable;
27. Pending is transitory;
28. bounded retry/contingency exists;
29. sweeper exists;
30. all terminal mileage states behave correctly;
31. implausible segment is not consolidated;
32. partial routing totals are never published as final official Miles;
33. Calculated mileage is immutable;
34. provenance survives raw-fix purge simulation;
35. tenant isolation proven;
36. offline/replay ordering proven;
37. RTE03/RTE04/RTE05 regressions green;
38. frontend typecheck/lint/build green;
39. migration checks green;
40. no RTE07+ UI/functionality implemented.

---

# 40. Tests Required

At minimum:

- effective-date assignment resolution;
- occurrence-time vehicle snapshot;
- future assignment;
- ended assignment;
- overlapping interval protection;
- odometer regression;
- model constraints;
- migrations;
- evidence-level DB constraints;
- event correlation;
- coordinate validation;
- occurrence vs receipt time;
- permission denied;
- cached fallback;
- Recovery Window;
- Missing finalization;
- Start Trip waypoint;
- one Change Plan waypoint;
- multiple Change Plan waypoints;
- Change Plan missing waypoint;
- Change Plan recovered waypoint;
- Change Plan offline replay;
- duplicate Change Plan idempotency;
- destination text not used for routing;
- Arrived waypoint;
- routing adapter;
- segment aggregation;
- provider failure mapping;
- plausibility;
- mileage state machine;
- sweeper;
- no partial final total;
- historical immutability;
- purge-safe provenance;
- HOME;
- INTERRUPTED;
- Activity Complete/Leave location evidence;
- End Work recovery;
- tenant isolation;
- device transfer;
- reauthentication;
- RTE03 regression;
- RTE04 regression;
- RTE05 regression;
- typecheck;
- lint;
- production build.

Use deterministic fakes/mocks for failure paths.

A live routing-provider validation may be added when approved credentials are available, but the regular automated suite must not depend on network/paid service availability.

Do not weaken existing assertions to obtain green.

For each changed existing test document:

`old expectation → approved CER delta → new expectation`

---

# 41. Checkpoints

## RTE06-CP0 — Baseline Correction: Vehicle Effective Dating

Complete first.

Deliver:

- current resolver audit;
- effective_from/effective_to correction;
- occurrence-time handling;
- overlap protection;
- regression of Work Session snapshot + odometer behavior.

STOP if this requires a new CER product decision.

## RTE06-CP1 — Current State + Technical Decisions

Deliver:

- lifecycle action/correlation audit;
- location architecture;
- V-1..V-5 status;
- routing provider evaluation/status;
- threshold/recovery configuration strategy;
- migration plan;
- waypoint/segment model plan;
- confirmation that OCR production remains out of scope.

STOP if a new product decision is needed.

## RTE06-CP2 — Location Evidence Pipeline

Implement:

- location models;
- lifecycle integration;
- Fresh / Degraded / Recovered;
- Missing Location Event;
- privacy notice;
- active-session boundary;
- Change Plan location capture;
- End Work bounded recovery;
- offline evidence sync.

## RTE06-CP3 — Segmented Mileage Engine

Implement:

- ordered authoritative waypoint sequence;
- segment routing;
- Start Trip / Change Plan(s) / Arrived;
- routing adapter;
- mileage lifecycle;
- segment plausibility;
- aggregation;
- retry/contingency;
- sweeper;
- immutable provenance.

## RTE06-CP4 — Integrated Closure

Validate:

- effective dating;
- location scenarios;
- segmented Change Plan mileage;
- HOME;
- INTERRUPTED;
- offline;
- tenant isolation;
- historical integrity;
- regression;
- build/migration health;
- validation inventory;
- no RTE07+ implementation.

STOP after report.

---

# 42. Do Not Change

Without explicit CER approval, do not change:

- RTE02-A02 roles/capabilities;
- Route navigation;
- RTE05 workbench;
- one ACTIVE Work Session invariant;
- Work Session lifecycle;
- occurrence-time semantics;
- Trip lifecycle;
- Change Plan availability only while IN_TRANSIT;
- Change Plan append-only history;
- HOME lifecycle;
- Activity lifecycle;
- multi-Activity one-block model;
- Outcome rules;
- Check Delivery Received By rule;
- odometer exception model;
- photo-backed manual reading behavior;
- END odometer Option B;
- `/route` guard;
- Standardized Values;
- zero-trip Work Session behavior;
- RTE03 offline/reauth/device-transfer guarantees.

---

# 43. Explicitly Superseded RTE06-001 Rule

The earlier RTE06-001 instruction stated that Change Plan did not create a mileage segment and that official mileage stayed as Start Trip → final Arrived.

That rule is **superseded**.

For RTE06-002:

> Change Plan remains inside the same Trip, but every Change Plan is an authoritative mileage waypoint and therefore splits the Trip's road-routing calculation into consecutive segments.

Do not implement the obsolete RTE06-001 Change Plan mileage rule.

---

# 44. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_REPORT_001.md`

Do not overwrite previous reports.

The report must include:

1. Current State Audit
2. RTE06-CP0 Effective Dating Result
3. Vehicle Assignment Rules As-Built
4. Validation Inventory V-1..V-5
5. Routing Provider Evaluation / Status
6. Architecture / Module Boundaries
7. Data Model / Migrations
8. Lifecycle Event Correlation
9. Location Acquisition Strategy
10. Fresh / Degraded / Recovered
11. Missing Location Event
12. Privacy Notice
13. Active-Session Privacy Boundary
14. End Work Recovery
15. Offline / Queue Integration
16. Breadcrumb Decision
17. Mileage Waypoint Model
18. Change Plan Waypoint Behavior
19. Segment Routing Model
20. Routing Adapter
21. Mileage State Machine
22. Plausibility
23. Retry / Contingency / Sweeper
24. Historical Immutability
25. Purge-Safe Provenance
26. Change Plan / HOME / INTERRUPTED
27. Odometer Independence
28. OCR Boundary / RTE10-A01 Confirmation
29. Day / Work Session Mileage Read Contract
30. Roles / Permissions / Tenant Isolation
31. Security / Audit
32. Scenario Evidence
33. Regression Results
34. Typecheck / Lint / Build / Migration Checks
35. Expected → Implemented → Evidence → Gap
36. Remaining PENDING VALIDATION / BLOCKED Items
37. Confirmation RTE07+ Not Started
38. Proposed RTE06 Status

Use classifications:

- AS-BUILT / CONFIRMED
- PARTIAL
- PENDING VALIDATION
- NOT IMPLEMENTED / GAP
- DEVIATION
- UNAUTHORIZED DECISION
- TECHNICAL DEBT
- DECISION REQUIRED
- BLOCKED

Do not call RTE06 Completed merely because automated tests pass.

---

# 45. STOP Conditions

STOP and return to CER if:

- official Miles would require changing the approved segmented waypoint definition;
- Change Plan cannot be correlated to a unique location waypoint;
- destination text/geocoding would be needed as mileage evidence;
- missing Change Plan waypoint would require silently skipping that waypoint;
- odometer or Haversine would be used as official fallback;
- a new Trip/Work Session/Activity state is required;
- a new role/capability is required;
- provider requires unapproved spend/contract/credentials;
- a privacy product decision is needed;
- retention duration would have to be invented;
- generic notifications would have to be rebuilt inside Route;
- OCR production would have to be implemented to complete RTE06;
- a certified RTE03/RTE04/RTE05 rule must be changed;
- RTE07+ scope becomes necessary.

---

# 46. Final STOP

After implementation and delivery of:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_REPORT_001.md`

**STOP.**

Do not begin RTE07 until CER reviews the report and explicitly certifies RTE06.
