# CER Route — Route Mileage Final Field Closure
## Shared-Environment Validation & Operational Closure
### Product Owner Instructions for Development Agent
### Revision 002

## 1. Context

The cross-surface mileage diagnostic established that the CER Route mileage pipeline is internally consistent:

- `TripMileage.total_meters` propagates correctly to Today / Live;
- the same value propagates correctly to Activity Explorer;
- pending mileage is not presented as final zero;
- no read-model, aggregation, unit-conversion or UI wiring defect was demonstrated;
- Reports is not yet implemented and remains outside this closure.

However, the diagnostic could not trace a **real affected Trip from the shared environment** because the accessible local database contained no operational Trips.

Therefore, the Route Mileage incident is **not yet field-closed**.

This instruction closes the remaining gap through the actual shared/deployed environment.

This work does **not reopen RTE06**. The certified mileage product semantics remain unchanged.

---

# 2. Objective

Close Route Mileage with evidence from the real shared environment by proving, end to end, that:

1. a real Trip has the required waypoint evidence;
2. the active routing provider is correctly available at runtime;
3. the mileage process reaches a truthful terminal state;
4. a valid Trip reaches `calculated`;
5. its Official Miles appear consistently in:
   - Today / Live;
   - Activity Explorer;
6. existing pending Trips are processed correctly by retry/sweeper;
7. no fabricated fallback mileage is introduced.

Final target:

`ROUTE MILEAGE — FIELD VALIDATED / CLOSED BY CER`

Development may only propose readiness. CER owns final closure.

---

# 3. Do Not Reopen Product Decisions

The following are already certified and must not change:

- Official Miles = routed road distance;
- authoritative waypoint chain uses the existing Start Trip / Change Plan / Arrived rules;
- Haversine / straight-line distance is never Official Miles;
- odometer delta is not Official Miles;
- destination text is not a routing endpoint;
- Pending is not final zero;
- partial segment totals are not published;
- `calculated` mileage is a historical fact;
- historical calculated values are not silently recalculated;
- Work Session / Trip / Activity lifecycle remains unchanged.

If field evidence exposes a conflict with one of these rules, STOP for CER instead of redefining mileage.

---

# 4. Shared Environment Is the Authority for This Closure

Do not use the local empty development database as the final evidence source.

The remaining closure must be executed against the environment where the field symptom was observed.

At minimum identify:

```text
environment
tenant/company
supervisor
session_date
work_session_id
trip_id
trip_mileage_id
runtime routing provider
```

Do not expose secrets in the report.

---

# 5. Mandatory Real-Trip Trace

Select at least:

- **Case A — one real affected existing Trip** where travel occurred but Miles are not currently visible;
- **Case B — one new controlled Trip** executed after the shared environment routing path is confirmed healthy.

For each case trace:

```text
Tenant
→ Supervisor
→ Work Session
→ Trip
→ Start Trip evidence
→ Change Plan waypoint(s), if applicable
→ Arrived evidence
→ TripMileage record
→ mileage state
→ attempts / retry metadata
→ provider
→ total_meters
→ Today / Live API
→ Today / Live UI
→ Activity API
→ Activity UI
```

Do not substitute synthetic data for these two field cases.

---

# 6. Case A — Existing Affected Trip

For the existing affected Trip, establish the actual current classification.

Inspect:

- Trip lifecycle state;
- required location evidence;
- `TripMileage.state`;
- `total_meters`;
- `attempt_count`;
- `next_attempt_at`;
- `last_error`;
- `terminal_reason`;
- `calculated_at`;
- provider/method/version;
- segment count.

Classify it as exactly one of:

### A1 — `calculated`

If:

`state = calculated AND total_meters > 0`

then trace the read path to Today / Live and Activity.

If the UI still does not display Miles, this is a real downstream product defect. Apply the minimum correction and prove before/after behavior.

### A2 — `pending_calculation`

Determine whether it is waiting on:

- waypoint evidence;
- routing provider;
- retry schedule;
- sweeper execution;
- other technical condition.

Do not accept indefinite Pending.

### A3 — `not_calculable`

Confirm the terminal reason corresponds truthfully to insufficient required evidence.

Do not fabricate Miles.

### A4 — `calculation_failed`

Confirm evidence was sufficient but routing exhausted the approved contingency.

Do not fabricate Miles.

### A5 — no mileage record

If no TripMileage record exists for a Trip that should have created one, treat as a product defect in trigger/persistence and correct it within existing semantics.

---

# 7. Runtime Routing Provider — Mandatory

Inspect the **actual runtime provider in the shared environment**.

Do not infer the provider from an older report or from the local environment.

CER has previously configured routing capabilities; therefore Development must determine what is active now rather than assume an unconfigured state.

Prove:

```text
provider/adapter selected
integration/config source
provider enabled?
secret/config present?
connectivity/reachability
one real route request
returned road distance
provider error, if any
```

Supported runtime paths may include the repository's existing platform integration and/or configured routing URL mechanisms.

Do not expose API keys or secrets.

If a provider is already configured but not being selected, diagnose adapter/configuration selection.

If the provider is selected but unreachable, classify separately:

`ENVIRONMENT / DEVOPS REACHABILITY`

If no provider is actually configured in the shared environment, classify:

`ENVIRONMENT CONFIGURATION`

and execute the approved operational configuration if Development has authority.

If Development lacks authority, provide the exact DevOps action and wait for that action before proposing final closure.

Do not call Route Mileage complete while the shared runtime has no working routing path.

---

# 8. Real Routing Validation

Once the runtime provider is available, execute at least one real routing calculation using real captured Trip endpoints.

Verify:

- correct waypoint order;
- routing request succeeds;
- road distance is plausible;
- result is persisted;
- provider/method/version provenance is stored;
- TripMileage becomes `calculated`;
- `total_meters > 0`.

Do not bypass plausibility validation merely to obtain a number.

---

# 9. Retry / Sweeper — Shared Environment

The final closure must prove that the automatic resolution path is actually operating in the deployed/shared environment.

Validate:

1. mileage job is registered;
2. scheduler is active;
3. leader/job execution occurs;
4. due pending records are detected;
5. `attempt_count` advances when appropriate;
6. successful retry moves to `calculated`;
7. unrecoverable cases reach truthful terminal states;
8. Pending does not remain indefinitely because the job is not running.

Where current logging is insufficient, use database state before/after the scheduled interval as evidence.

Do not require a product-code observability enhancement unless the shared-environment execution cannot otherwise be proven.

---

# 10. Backlog Behavior

After the routing provider is healthy, inspect existing pending mileage records for the affected tenant.

Determine:

- which are eligible to retry;
- which are waiting on evidence;
- which can resolve automatically;
- which should terminalize truthfully.

The product must not require a manual per-Trip database correction for normal provider recovery.

Prove that at least one eligible pre-existing pending Trip can advance through the supported automatic process.

If no eligible historical Trip exists, state that fact and prove the retry path with a controlled pending Trip in the shared environment.

---

# 11. Today / Live Field Validation

For a real `calculated` Trip, prove:

```text
TripMileage.total_meters
→ /api/live/today
→ supervisor official_miles
→ summary total_miles
→ rendered desktop/mobile value
```

Validate:

- correct Supervisor;
- correct business day;
- correct total;
- same value in row/detail where applicable;
- no cross-supervisor bleed;
- no cross-tenant bleed.

If more than one calculated Trip exists in the Work Session, prove the aggregate.

---

# 12. Activity Explorer Field Validation

For the same real `calculated` Trip, prove:

```text
TripMileage.total_meters
→ /api/activity-explorer
→ Day summary
→ Activity/stop presentation when applicable
→ Week / Month / Year aggregate
```

Important:

- a Trip can contribute Miles to the Day total even when no Activity block/card exists;
- that difference is valid and must not be treated as missing mileage.

Validate the appropriate real scenario.

---

# 13. Cross-Surface Consistency

For the same Trip / Work Session:

```text
Official Miles fact
      │
      ├── Today / Live
      └── Activity Explorer
```

must resolve to the same underlying Official Miles.

Differences are allowed only because of legitimate period aggregation.

No separate mileage formula may exist per surface.

Reports are excluded because they are not yet implemented.

---

# 14. Required Field Scenarios

Complete all applicable scenarios before proposing closure.

## FC-01 — Existing affected Trip

Real historical affected Trip classified and explained.

PASS required.

## FC-02 — New real Trip calculates

New controlled Trip with valid waypoint evidence reaches:

`calculated`

with a positive road-distance total.

PASS required.

## FC-03 — Today / Live displays it

Same new Trip's Miles appear correctly in Today / Live.

PASS required.

## FC-04 — Activity displays it

Same new Trip's Miles appear correctly in Activity Explorer.

PASS required.

## FC-05 — Pending recovery

An eligible pending Trip advances through the automatic retry/sweeper path after provider availability.

PASS required.

## FC-06 — Missing evidence remains truthful

A Trip lacking required authoritative waypoint evidence must not receive fabricated Miles.

PASS required.

## FC-07 — Multiple Trips aggregate

At least two calculated Trips within one applicable business period aggregate correctly.

PASS required.

## FC-08 — Business day

Mileage remains associated with authoritative `session_date`, including a cross-midnight case from automated regression if a real field case is unavailable.

PASS required.

## FC-09 — Tenant isolation

No mileage from another tenant is returned.

PASS required.

---

# 15. Correction Authorization

Development may apply the minimum correction required if field evidence proves a technical defect in:

- provider selection;
- configuration consumption;
- routing adapter wiring;
- mileage trigger;
- retry/sweeper execution;
- read model;
- API mapping;
- frontend binding.

Development must not change mileage business semantics.

If correction requires infrastructure/secret/deployment action rather than product code, classify it as such and execute through the authorized operational path.

CER functional certification does not require taking ownership of unrelated DevOps mechanics, but **the shared environment must be functionally working before Route Mileage can be field-closed**.

---

# 16. Tests / Regression

After any correction, execute affected regression for:

- mileage engine;
- routing adapter;
- retry/sweeper;
- Work Session;
- Trip;
- Change Plan;
- Today / Live;
- Activity Explorer;
- business-day aggregation;
- tenant isolation;
- typecheck/lint/build as applicable.

If no product code changes, state explicitly:

`NO PRODUCT CODE CHANGE — FIELD/ENVIRONMENT CLOSURE ONLY`

and still provide field evidence.

---

# 17. Acceptance Criteria

Route Mileage is ready for CER final closure only when:

1. one real affected Trip has been traced;
2. its actual cause/state is known;
3. shared-environment runtime provider is identified;
4. a real routing request succeeds;
5. a real Trip reaches `calculated`;
6. positive `total_meters` is persisted;
7. Today / Live displays the correct Miles;
8. Activity Explorer displays/aggregates the correct Miles;
9. both surfaces use the same mileage fact;
10. pending retry/sweeper works in the shared environment;
11. eligible backlog can advance automatically;
12. missing evidence does not fabricate Miles;
13. business-day semantics remain correct;
14. tenant isolation remains correct;
15. no odometer/Haversine fallback was introduced;
16. affected regression is green;
17. no unexplained Pending remains in the controlled closure cases;
18. no `PARTIAL`, `GAP`, `BLOCKED` or unresolved `DECISION REQUIRED` remains inside this closure scope.

---

# 18. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_MILEAGE_FINAL_FIELD_CLOSURE_REPORT_002.md`

Include:

1. Executive Closure Result
2. Shared Environment Identified
3. Existing Affected Trip Trace
4. Runtime Routing Provider
5. Real Routing Execution
6. TripMileage Persistence
7. Retry / Sweeper Evidence
8. Pending Backlog Behavior
9. Today / Live Field Evidence
10. Activity Explorer Field Evidence
11. Cross-Surface Consistency
12. Corrections Applied, if any
13. DevOps / Environment Actions, if any
14. Regression
15. Expected → Implemented → Evidence → Gap
16. Remaining Issues
17. Proposed Status

For each real Trip include:

`Trip → evidence → mileage state → provider → meters → API → UI → result`

Do not include secrets.

---

# 19. Status Rule

Only if all mandatory closure evidence is green may Development propose:

`ROUTE MILEAGE FIELD CLOSURE COMPLETE / READY FOR CER CERTIFICATION`

Development must not declare:

`ROUTE MILEAGE CLOSED`

CER owns final certification.

If a genuine new product decision is required:

`ROUTE MILEAGE CLOSURE BLOCKED — CER DECISION REQUIRED`

with:

`fact → impact → options → recommendation`

Do not leave the work as unexplained `PARTIAL`.

---

# 20. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_MILEAGE_FINAL_FIELD_CLOSURE_REPORT_002.md`

**STOP.**

Do not start RTE09.

Do not resume RTE10-A01.

Do not redesign Today / Live or Activity Explorer.

Wait for CER final review and certification.
