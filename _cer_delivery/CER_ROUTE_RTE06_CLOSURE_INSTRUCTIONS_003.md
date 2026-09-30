# CER Route — RTE06 Closure & Validation
## Agent Instructions — Revision 003

**Purpose:** close RTE06 completely before RTE07.  
**Baseline instruction:** `CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_INSTRUCTIONS_002.md`  
**Current delivery under review:** `Report Delivery Rodrigo/CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_REPORT_001.md`  
**CP0 report:** `CER_ROUTE_RTE06_CP0_EFFECTIVE_DATING_REPORT_001.md`

---

# 1. Context

RTE06 has a strong implementation candidate, but CER will not certify the sprint while any item remains `PARTIAL`, any productive integration remains only simulated, or any decision essential to RTE06 remains deferred.

This instruction is a **closure delta**, not a rewrite of RTE06.

Preserve the approved baseline:
- RTE06-CP0 Effective Dating is functionally closed unless regression proves otherwise.
- Official mileage remains road-routing distance.
- One Trip remains one Trip across Change Plan.
- Every Change Plan is an authoritative mileage waypoint.
- Missing required waypoint means `Not Calculable`.
- Haversine, breadcrumbs, odometer, destination text and inferred geocoding are never official mileage.
- `Pending Calculation` is transient.
- Calculated mileage is immutable.
- Provenance must remain auditable after raw location evidence is purged.
- OCR production remains outside RTE06.

RTE07 must not start before CER certifies this closure.

# 2. Objective

Close all remaining RTE06 implementation and validation gaps so that the final status can be proposed as:

`RTE06 — COMPLETED / READY FOR CER CERTIFICATION`

without:
- `PARTIAL`;
- `PENDING VALIDATION` inside RTE06 closure scope;
- provider integration left unmeasured;
- fallback documented but not exercised;
- offline location evidence that can be silently lost;
- provisional thresholds left unreviewed;
- unresolved Missing Location Event mutability.

# 3. CER Decision — Missing Location Event

## D-RTE06-MISSING-01 — Strict append-only fact

`MissingLocationEvent` is a historical fact and must be fully immutable after creation.

After insert:
- no business field may be updated;
- no generic `notes` field may remain mutable;
- no delete;
- no truncate;
- no reinterpretation of reason/evidence after the fact.

The Missing fact must contain only the event evidence required to explain what happened, including as applicable:
- tenant/company;
- supervisor;
- work session;
- trip;
- lifecycle action / subject;
- event kind;
- occurrence timestamp;
- reason code;
- permission/acquisition state;
- attempt evidence;
- rejected candidate age;
- rejected candidate accuracy;
- created timestamp.

Rejected candidate coordinates must not be stored merely because a rejected point existed.

## Notification state must be separate

Notification delivery state is **not part of the immutable Missing fact**.

Move notification lifecycle to a separate operational entity/contract.

Reuse existing Core/platform notification infrastructure if an appropriate reusable primitive already exists.

If no suitable reusable entity exists, create the minimum domain-neutral operational structure required to track delivery without mutating `MissingLocationEvent`.

The notification/delivery structure may contain, as applicable:
- `missing_location_event_id`;
- channel;
- status;
- attempt count;
- last attempt time;
- delivered time;
- failure code/reason;
- created/updated timestamps.

Do not create a Route-specific notification inbox in RTE06.

The design must remain compatible with future:
- in-platform notification;
- optional email;
- additional channels.

# 4. Closure Item A — Offline Location Evidence Durability

## Problem to verify

Current RTE06 behavior must prove that a useful location captured while the lifecycle action is offline is not silently lost merely because the network submission fails.

Do not assume fire-and-forget delivery is durable.

## Required behavior

For applicable lifecycle events:
- Start Work;
- Start Trip;
- Change Plan;
- Arrived;
- Complete Activity;
- Leave Activity;
- End Work;

if the device obtains a location while offline or while the evidence submission cannot reach the server:

1. preserve the evidence durably on the client/device;
2. preserve event kind, durable subject/action correlation, device capture timestamp, evidence level, coordinates, accuracy, and cached age/provenance where applicable;
3. retry/sync later;
4. preserve the original evidence classification;
5. bind to the exact lifecycle event after replay;
6. remain idempotent;
7. never bind by nearest timestamp;
8. never overwrite a first accepted authoritative point;
9. never reorder Change Plan waypoints by upload time.

CER does not prescribe the storage/queue mechanism. The required result is:

`captured offline → survives → syncs later → exact event correlation → no duplicate`

## Mandatory discriminating tests

At minimum prove:
- Start Trip queued offline + fresh location captured offline → both later sync correctly;
- Change Plan queued offline + location captured offline → correct purpose-change id after replay;
- multiple queued Change Plans preserve domain occurrence order;
- duplicate evidence replay writes one authoritative point;
- app/browser restart does not lose pending location evidence;
- reauthentication does not silently discard pending evidence;
- cached/degraded does not become Fresh after delayed upload;
- recovered evidence preserves actual capture timestamp;
- Missing is not created if valid durable evidence arrives within the allowed resolution path.

If current architecture already provides all of this, prove it with evidence rather than rewriting it.

# 5. Closure Item B — Routing Primary + Fallback Must Be Real

The technical selection of routing provider(s) remains Development's decision.

RTE06 cannot close on documentation alone.

## Required closure

The final implementation must prove:
1. a real primary routing engine can be reached through `RoadRouter`;
2. the adapter converts real coordinates correctly;
3. returned road distance is mapped correctly;
4. timeout / transient failure behavior is real, not only simulated;
5. permanent/no-route behavior is handled;
6. provenance records the provider actually used;
7. fallback is an implemented and exercised execution path, not only an architectural intention;
8. if primary fails and fallback succeeds, mileage can still reach `Calculated`;
9. if both fail after bounded contingency, result reaches `Calculation Failed`;
10. no Haversine result is promoted as official fallback.

## Required real integration evidence

Run live measurements against the selected primary.

If a fallback engine is part of the RTE06 design, run a real fallback path as well.

Minimum evidence:
- known coordinates;
- plausible road distance;
- provider/version recorded;
- one-segment Trip;
- multi-segment Trip;
- Change Plan route;
- primary failure → fallback success;
- primary + fallback failure → terminal failure.

Deterministic doubles remain required for automated failure coverage, but are not sufficient to certify productive routing integration.

# 6. Closure Item C — V-4 Offline Soak

The previous `PARTIAL` state is not acceptable for closure.

Design and run an extended soak sufficient to demonstrate stability of:
- durable operational queue;
- durable location evidence;
- reconnect;
- repeated network loss/restoration;
- duplicate replay;
- concurrency;
- reauthentication;
- multiple Trips;
- multiple Change Plans;
- lifecycle ordering;
- no duplicate mileage;
- no wrong-event correlation;
- no permanent Pending caused by replay behavior.

Development may choose the exact duration and automation strategy.

Document why the selected duration/load is technically meaningful.

The result must be `CONFIRMED`, or defects must be fixed and the soak rerun.

# 7. Closure Item D — Real Device Validation

Complete physical-device validation.

## iOS
- Safari on a physical iPhone;
- permission grant;
- permission denial;
- background transition;
- screen lock/background behavior where relevant;
- return to foreground;
- lifecycle event after return;
- End Work recovery boundary.

## Android
- Chrome on a physical Android device;
- same core scenarios.

Do not claim background location capability the browser does not provide.

Record:
- device/platform;
- browser version;
- scenario;
- observed evidence level;
- whether the lifecycle action was blocked;
- recovery behavior;
- resulting server state.

# 8. Closure Item E — Field Accuracy Sampling

Run a representative CER field sample sufficient to evaluate current location thresholds.

Measure at minimum:
- fresh acquisition latency;
- accuracy;
- cached point age;
- cached point accuracy;
- recovered frequency;
- missing frequency;
- obvious rejected-point cases.

Review at minimum:
- `fresh_timeout_seconds`;
- `cached_max_age_seconds`;
- `cached_max_accuracy_m`;
- `recovery_window_seconds`.

Use field evidence to retain or adjust values and document rationale.

Final thresholds must no longer be described merely as temporary/unvalidated defaults.

# 9. Closure Item F — Evidence-Level Distribution

Produce a controlled pilot/field distribution of:
- Fresh;
- Degraded Cached;
- Recovered;
- Missing.

Use it to detect pathological behavior such as:
- excessive Missing;
- cached evidence dominating normal use;
- recovery almost never succeeding;
- Fresh acquisition taking too long.

Do not fabricate percentages.

Document sample size and environment.

# 10. Missing Notification Refactor Requirements

Implement D-RTE06-MISSING-01.

## Required state after closure

`MissingLocationEvent`
- strict append-only;
- no notification status mutation;
- no generic mutable notes;
- historical fact only.

Notification/delivery state
- separate;
- references Missing event;
- independently mutable according to delivery lifecycle;
- auditable;
- compatible with future in-platform notification.

## Migration

If the current table contains notification columns:
- migrate without losing existing local/test state;
- do not silently rewrite historical Missing facts;
- keep upgrade/downgrade clean where applicable;
- keep schema roundtrip clean.

## Tests

Prove:
- Missing fact cannot update;
- Missing fact cannot delete;
- notification status can advance separately;
- notification update cannot modify Missing fact;
- tenant isolation;
- audit where applicable;
- compatibility with future notification delivery.

# 11. What Not to Reopen

Do not redesign:
- Work Session;
- Trip state machine;
- Activity execution;
- Change Plan semantics;
- odometer evidence;
- OCR;
- Route roles;
- Route permissions;
- standardized lists;
- Today/Live;
- Reports;
- Activity Explorer;
- Fuel;
- geocoding;
- maps;
- navigation;
- continuous GPS tracking;
- retention duration.

Do not introduce unrelated framework refactors.

# 12. Acceptance Criteria for RTE06 Closure

RTE06 closure may be proposed ready for CER certification only if all are true:

1. CP0 remains green.
2. Offline location evidence is durable and proven.
3. Exact action correlation survives offline replay.
4. App restart does not lose pending evidence.
5. Primary routing engine is live-tested.
6. Fallback path is implemented and live-tested if part of the selected design.
7. Primary failure → fallback success is proven.
8. Total routing failure → correct terminal state.
9. V-4 soak is `CONFIRMED`.
10. iOS physical-device validation is completed.
11. Android physical-device validation is completed.
12. Field accuracy sampling is completed.
13. Evidence-level distribution is measured.
14. Configurable thresholds are reviewed and finalized.
15. `MissingLocationEvent` is strictly immutable.
16. Notification state is separated.
17. No generic mutable Missing-event notes remain.
18. No partial mileage total is published.
19. No Missing waypoint is skipped.
20. Calculated mileage remains immutable.
21. Purge-safe provenance remains intact.
22. Tenant isolation remains green.
23. No new capability is introduced without approval.
24. RTE03/RTE04/RTE05 regression remains green.
25. Migration checks remain green.
26. Typecheck/lint/build remain green.
27. No RTE07+ scope is introduced.
28. No `PARTIAL`, `PENDING VALIDATION`, `NOT IMPLEMENTED / GAP` or `BLOCKED` remains inside RTE06 scope.

# 13. Tests Required

At minimum rerun and extend:
- Effective Dating / overlap;
- location evidence integration;
- mileage engine;
- silent capture browser journey;
- RTE05 journeys;
- offline queue;
- migration upgrade/downgrade/roundtrip;
- trigger diagnostics;
- tenant isolation;
- real routing integration;
- fallback integration;
- offline soak;
- physical-device validation evidence.

Do not weaken, skip or xfail a failing test to obtain closure.

A live integration test may remain environment-gated in the automated suite, but closure evidence must show that it was actually executed successfully in a configured environment.

# 14. Decision Authority

The agent/developer may decide technical implementation details that do not alter:
- approved business behavior;
- privacy model;
- permissions;
- tenant isolation;
- modular architecture;
- scope;
- significant cost/contract/licensing.

Do not escalate ordinary technical choices.

If several technical options satisfy the contract, evaluate them, choose one, document the reason, and proceed.

Escalate only when the decision changes a Product Owner concern.

# 15. Deliverable

Create a new incremental report:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_CLOSURE_REPORT_002.md`

Do not overwrite Report 001.

The report must contain at minimum:
1. Closure Scope
2. Starting Findings
3. Offline Location Durability
4. Offline Storage / Replay Architecture
5. Exact Correlation Evidence
6. Routing Primary Live Validation
7. Routing Fallback Live Validation
8. Routing Failure Matrix
9. Offline Soak Result
10. iOS Physical Validation
11. Android Physical Validation
12. Field Accuracy Sample
13. Evidence-Level Distribution
14. Final Thresholds
15. Missing Location Event Refactor
16. Notification State Separation
17. Migration Evidence
18. Security / Tenant Isolation
19. Historical Immutability
20. Purge-Safe Provenance
21. Regression
22. Browser Evidence
23. Typecheck / Lint / Build
24. Expected → Implemented → Evidence → Gap
25. Deviations / Technical Debt
26. Final Validation Inventory
27. Proposed Status

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

A proposal of `COMPLETED` is valid only when none of the unresolved classifications remains inside RTE06 scope.

# 16. STOP Conditions

STOP and return to CER only if closure requires:
- a new product state;
- changing official mileage semantics;
- changing Change Plan semantics;
- weakening tenant isolation;
- new Route capabilities;
- continuous/background GPS tracking beyond approved boundaries;
- a new external commercial commitment requiring CER approval;
- changing the privacy model;
- changing RTE03/RTE04/RTE05 certified business behavior.

Do not STOP for ordinary implementation choices.

# 17. Final STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_CLOSURE_REPORT_002.md`

**STOP.**

Do not start RTE07.

CER will review the closure and certify RTE06 explicitly.
