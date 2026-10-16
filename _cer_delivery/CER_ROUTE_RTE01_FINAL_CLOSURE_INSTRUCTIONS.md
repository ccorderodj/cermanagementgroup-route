# CER Route — RTE01 Final Closure Decisions and Correction Instructions

**Document purpose:** Final CER decisions required to close **RTE01 — Technical Baseline + Target Alignment**.  
**Target report:** `CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT.md`  
**Current report revision reviewed by CER:** R2  
**Expected next revision:** R3  
**Authority:** CER Product / Architecture Governance  
**Scope:** Documentation closure only. **Do not write product code and do not start RTE02.**

---

## 1. Objective

Update the existing RTE01 report so that it reflects all CER decisions below consistently and contains **no remaining CER product ambiguity from RTE01**.

The report must remain a technical baseline and target-alignment document. Do not convert these decisions into premature implementation work.

After applying this document:

- all resolved `A-*` ambiguities listed below must be removed from the open-ambiguity list;
- all resolved `D-*` items must be recorded as approved CER requirements or as explicitly delegated technical decisions;
- recommendations superseded by CER decisions must be removed or rewritten;
- no obsolete alternative may remain elsewhere in the report as if it were still valid;
- no RTE02+ product code may be created;
- the final proposed checkpoint status may be:
  **`Completed — ready for CER certification`**.

CER retains final checkpoint certification authority.

---

# 2. Product Decisions Approved by CER

## A-1 — Start Work does not require an immediate Trip

**RESOLVED.**

A Supervisor may execute `Start Work` without creating or starting a Trip.

`Start Work` opens the Work Session. From that moment CER Route must record the applicable operational events and activity.

A Trip is created only when the Supervisor actually begins a displacement.

### Required rule

> Do not create an artificial Trip merely because the Work Session started.

---

## A-3 — Multiple Activities at one arrival

**RESOLVED.**

The existing V0.7 flow remains unchanged except for one surgical UX change:

> The existing Activity selector becomes **multi-select**.

Approved flow:

`Start Trip → On Route → Arrived → Select one or more Activities → Start Activity → Complete / Leave → Outcome → Notes → next approved flow action`

### Rules

1. `Arrived` ends the travel leg. It does **not** start the Activity automatically.
2. After `Arrived`, the Supervisor selects **one or more configured Activities from the Activity selector applicable to that existing V0.7 context**.
3. Do **not** turn this into cross-context selection of unrelated Activity Types.
4. At least one Activity must be selected before `Start Activity`.
5. `Start Activity` is executed once.
6. All selected Activities share:
   - one `started_at`;
   - one `completed_at`;
   - one duration;
   - one Outcome;
   - one Notes field.
7. No per-selected-Activity timer, start, completion, Outcome, or Notes is introduced.
8. The existing Outcome step remains in the same place in the flow.
9. Outcome values are **tenant/Admin-configured data**, not hardcoded system values and not a `BusinessEnum`.
10. Mockup Outcome labels are examples of configured data only.
11. Notes remain optional as defined by V0.7.
12. No additional completion-status field is introduced.
13. No new user-facing term such as `Activity Group`, `Stop Group`, or similar may be introduced.
14. Internal grouping entities are allowed if technically appropriate, but they are implementation details only.
15. A-3 does **not** change the approved semantics of Reason, Delivery Type, Purpose, Received By, or free-text reference fields.

### Activity restoration

When an Activity is `IN_PROGRESS`, the Supervisor remains in the Activity execution flow.

If the Supervisor leaves/closes the application and later returns, CER Route must restore that same active Activity state.

The Supervisor must use the approved Activity actions (`Complete` or `Leave`, as defined by the existing flow) and record the applicable Outcome before returning to the general flow.

`End Work` is not a normal action while an Activity remains `IN_PROGRESS`.

If the backend exceptionally receives an `End Work` request while an Activity is active, reject the invalid transition and return the authoritative active Activity state. Do not auto-close the Activity and do not invent an Outcome.

---

## A-4 — Change Plan

**RESOLVED.**

`Change Plan` is available only while the Trip is:

`On Route / IN_TRANSIT`

Its purpose is to handle an unexpected change while travelling.

After the Supervisor presses `Arrived`:

- the Trip has reached its destination;
- `Change Plan` no longer applies to that Trip;
- any later displacement requires a new Trip.

Do not extend `Change Plan` beyond `Arrived`.

---

## A-6 — Same Work Session across devices

**RESOLVED.**

A Supervisor may not have two active Work Sessions in parallel.

If the Supervisor opens CER Route on another mobile device while a Work Session is active:

- do not create another Work Session;
- do not duplicate Trips or Activities;
- treat the event as a **transfer/resume of the same active Work Session**;
- the same Work Session may move back and forth between devices;
- the server remains the authoritative state;
- any pending offline queues must reconcile safely without losing traceability.

The implementation details of device/session transfer belong to development.

---
# 3. Location Acquisition — D-01

## D-01 — Location acquisition and Missing Location handling

**RESOLVED / APPROVED.**

Location evidence is a high-priority requirement. CER Route must make a serious best-effort attempt to obtain and store location at every applicable lifecycle event.

The Supervisor's operational workflow must not stop because location acquisition failed.

### 3.1 Acquisition priority

The implementation must support a staged acquisition strategy.

Conceptually:

1. Attempt a **Fresh Point** at the lifecycle event.
2. Exhaust the normal/current-location acquisition paths defined by the implementation.
3. If current acquisition fails, a technically available last-known/cached point may be evaluated as fallback.
4. Cached/last-known evidence may be used only when it satisfies the applicable freshness and accuracy criteria.
5. If no valid endpoint exists at the event, CER Route may continue trying silently inside a short **Recovery Window**.
6. If recovery succeeds, persist the actual recovered point and its actual metadata.
7. Only after current acquisition, approved cached fallback, and recovery have been exhausted may the event become `Location Missing`.

The exact retry count, timings, browser APIs, cache implementation, freshness thresholds and recovery-window duration are technical decisions to be validated on real devices.

### 3.2 Four location evidence levels

Use these conceptual levels consistently:

1. **Fresh Point**
   - obtained for the lifecycle event normally.

2. **Degraded Cached Point**
   - last-known/cached evidence used only after normal acquisition paths were exhausted;
   - must satisfy the approved technical freshness/accuracy rules;
   - must remain explicitly Degraded.

3. **Recovered Point**
   - a valid point obtained shortly after the lifecycle event within the approved recovery window;
   - must preserve its true capture timestamp and provenance;
   - must never be represented as if it were captured exactly at the event.

4. **Missing**
   - no acceptable evidence after all approved acquisition/fallback/recovery paths were exhausted.

### 3.3 Provenance

Every stored fix must preserve the relevant evidence needed to understand its quality, including as applicable:

- latitude;
- longitude;
- accuracy;
- actual device capture timestamp;
- server received timestamp;
- source/provenance;
- age/staleness;
- Fresh / Degraded / Recovered condition;
- anomaly flags.

Never fabricate coordinates.

A cached or recovered point must never be represented as Fresh.

### 3.4 Supervisor UX

Location acquisition failures are **silent during normal operation**.

Do not show operational GPS diagnostics such as:

- `GPS failed`;
- `Missing Location`;
- timeout warnings;
- accuracy errors;
- retry diagnostics;
- repeated location warnings.

The browser/OS permission prompt itself is not bypassed.

### 3.5 Missing Location Event

If acquisition ultimately becomes `Missing`, persist an explicit Missing Location Event or equivalent traceable record.

It must identify as applicable:

- tenant/company;
- Supervisor;
- Work Session;
- Trip/event;
- lifecycle event kind;
- timestamp;
- honest reason code based on what the platform can actually determine;
- acquisition/fallback evidence;
- last-known evidence if relevant;
- notification status.

Do not invent a technical failure reason that the browser/device does not expose.

### 3.6 Back-office notification

A confirmed Missing Location Event must be eligible for configurable back-office notification.

Required channels:

- **in-platform notification**;
- **email as an optional channel**.

Tenant/Admin configuration must define recipients by the supported role/user model.

Rules:

- do not notify for each internal retry;
- notify only after the event is confirmed Missing;
- notification grouping/deduplication is allowed to prevent spam;
- grouping must never delete the underlying Missing Location Events.

### 3.7 Foundation gap

The Foundation currently provides email and scheduler capabilities but does not provide a complete in-platform notification capability.

Record the in-platform notification capability as **New / future implementation required**.

Do **not** state that email-only launch permanently satisfies the approved D-01 requirement.

No notification feature is to be implemented in RTE01.

---

# 4. Mileage — D-02

## D-02 — Mileage authority and lifecycle

**RESOLVED / APPROVED.**

### D-02.1 — Meaning of `Miles`

`Miles` means:

> **Road distance calculated between the Trip departure and arrival endpoints using a routing service.**

It does not mean:

- odometer mileage;
- continuous GPS trace mileage;
- straight-line distance.

### D-02.2 — Routing endpoints

The authoritative routing endpoints are:

- departure = coordinate associated with `Start Trip`;
- arrival = coordinate associated with `Arrived`.

Do not use free-text destination, inferred address, client master data, or unrelated events as routing endpoints.

### D-02.3 — Degraded endpoint eligibility

A Degraded/cache/last-known point may be used as a routing endpoint only when:

- all normal/current acquisition paths were exhausted first;
- it satisfies the approved technical freshness and accuracy rules.

Its degraded provenance must remain preserved.

### D-02.4 — Endpoint recovery

If a valid point is unavailable at `Start Trip` or `Arrived`, CER Route may continue trying silently during a short recovery window.

A Recovered Point must preserve:

- real timestamp;
- accuracy;
- provenance;
- recovered/degraded condition.

If a required endpoint remains Missing after acquisition, fallback and recovery are exhausted:

- do not fabricate an endpoint;
- do not infer it from destination text;
- do not borrow a point from the next Trip or unrelated event;
- the Trip cannot produce normal calculated mileage from that missing endpoint.

### D-02.5 — Breadcrumbs

Foreground/opportunistic GPS breadcrumbs are **supporting evidence only** in V1.

They may support:

- diagnostics;
- anomaly detection;
- validation;
- later administrative review.

They do **not** automatically modify, replace, or become the authoritative `Miles` value.

### D-02.6 — Routing provider failure

If valid endpoints exist but the routing service cannot provide a valid road-distance result:

- save the Trip normally;
- set mileage to `Pending Calculation`;
- retry through the approved backend contingency strategy.

Do **not** publish Haversine/straight-line distance as official `Miles`.

Haversine may only be used internally for diagnostics/plausibility if development finds it useful.

### D-02.7 — Odometer is out of V1

Remove odometer from the V1 product and RTE01 closure requirements.

Specifically:

- no odometer capture;
- no odometer OCR;
- no manual odometer reconciliation;
- no mileage tolerance defined against odometer;
- no requirement for V-3 to compare routing against odometer;
- odometer validation must not block RTE06.

If future CER scope adds odometer evidence, it will require a separate product decision.

### D-02.8 — Historical Miles are facts

Once a valid `Miles` value is calculated and consolidated:

> **It is a persisted historical fact and must not be automatically recalculated.**

Persist enough provenance to audit it, including as applicable:

- calculated value;
- routing provider;
- calculation method/version where relevant;
- endpoint references/provenance;
- calculation timestamp.

Future changes to provider, maps, algorithms or configuration must not silently alter historical Trips.

### D-02.9 — Plausibility validation

Before a routing result becomes the final historical `Miles` fact, the result must pass reasonable technical plausibility/validation controls.

If the result is anomalous, incoherent or technically suspicious:

- do not consolidate it as final Miles;
- use the approved retry/fallback/contingency strategy;
- keep the calculation unresolved until a valid result or terminal exception is reached.

Do not silently substitute a fabricated value or Haversine value.

The exact anomaly thresholds belong to development/validation.

### D-02.10 — Mileage calculation states

Approved conceptual states:

#### `Pending Calculation`
Transitory only.

The system still has a path to resolve the calculation automatically.

#### `Calculated`
Terminal successful state.

A valid road-distance result has been consolidated as the historical fact.

#### `Not Calculable`
Terminal exceptional state.

Required data/endpoints remain insufficient after acquisition, fallback and recovery were exhausted.

#### `Calculation Failed`
Terminal exceptional state.

Sufficient endpoints/data exist, but the routing calculation could not produce a valid result after the approved retry/fallback/contingency mechanisms were exhausted.

### Rules

- No Trip may remain in `Pending Calculation` indefinitely.
- Every Trip must eventually reach a terminal mileage state.
- Terminal exceptional states retain:
  - reason;
  - terminal/closure timestamp;
  - available evidence;
  - audit/traceability;
  - back-office notification when applicable.
- `Degraded` is quality/provenance metadata, **not** a fifth mileage state.

---
# 5. Supervisor Client Technology — D-03

## D-03 — Technical decision delegated to Development

**CER does not prescribe PWA, native, hybrid or another client technology.**

CER defines the product requirement:

1. The **Supervisor experience is Mobile-only in V1**.
2. No Supervisor Desktop experience is required or should be developed.
3. The selected technology must reliably satisfy the approved D-01/D-02 location requirements.
4. It must support the required mobile workflow, fallback/recovery, offline continuity and provenance.
5. It must preserve CER Route modularity, security and maintainability.

The developer, assisted by its agent, must evaluate the viable options and document the recommendation, including:

- option(s) evaluated;
- iOS/Android behavior and limitations;
- location acquisition reliability;
- offline behavior;
- operational reliability;
- implementation impact;
- maintenance/deployment impact;
- security implications;
- reason for the selected approach.

Do not leave D-03 as an unresolved CER product decision. Record it as an explicitly delegated technical decision.

---

# 6. Routing Provider — D-04

## D-04 — Technical decision delegated to Development

CER does not prescribe a specific routing provider.

Product requirement:

> Obtain **road distance** between the approved `Start Trip` and `Arrived` endpoints.

Technical constraints:

- routing calculation is backend-side;
- provider credentials must not be exposed to the Supervisor client;
- provider access must sit behind an adapter/port boundary;
- domain logic must not be coupled directly to a provider.

The developer/agent must evaluate and document:

- coverage and routing quality;
- reliability/availability;
- latency;
- cost and quotas;
- coordinate privacy;
- licensing;
- observability;
- vendor lock-in risk;
- provider replacement;
- retries/fallback;
- contingency for degradation/outage.

The contingency must integrate with the D-02 mileage state model.

Do not leave D-04 as an unresolved CER provider-selection decision.

---

# 7. Location Data Retention — D-05

## D-05 — Confirmed principle

CER distinguishes historical facts from raw location evidence.

### Historical operational facts

The retention policy for raw GPS evidence must not silently delete or change historical operational facts such as:

- Trip;
- lifecycle timestamps;
- final Miles;
- calculation provenance;
- Activities;
- Outcome;
- duration;
- fuel estimate;
- terminal calculation states/exceptions;
- audit history.

### Raw location evidence

Raw/detailed location evidence has its own limited retention policy, including as applicable:

- raw latitude/longitude fixes;
- breadcrumbs;
- cached/recovered points;
- accuracy;
- age/staleness;
- detailed acquisition evidence.

When raw evidence expires, derived historical facts remain unchanged.

Do not hardcode the RTE01 recommendation of **90 days** as an approved CER requirement unless an authoritative policy separately establishes that exact duration.

The exact retention duration belongs to the applicable policy/compliance/configuration decision, not an invented RTE01 product rule.

---

# 8. Fuel Reference / Estimated Fuel Cost — D-06

## D-06 — Fuel reference variability

**RESOLVED.**

Fuel price is not a single static tenant value.

The model must support the real variability of fuel by:

- location/geographic scope — state/city or other technically viable granularity;
- fuel grade;
- date/effective time.

CER Route must support a scheduled mechanism to keep reference fuel prices reasonably current for estimation.

### Technical decision delegated to Development

The developer/agent must evaluate the practical source and ingestion strategy, which may include:

- external provider/API;
- scheduled connection;
- CSV/import;
- combination of sources/fallbacks.

The technical proposal must consider:

- reliability;
- geographic coverage;
- update frequency;
- cost;
- licensing;
- provenance;
- fallback/contingency;
- data validation.

### Missing fuel price

If the applicable fuel price is not currently available:

> `Estimated Fuel Cost` remains `Pending Calculation`.

Do not invent or silently substitute a fuel price.

When a valid applicable price becomes available, the estimate may be completed.

### Historical integrity

Persist the reference/provenance required to preserve the historical estimate, including as applicable:

- source;
- geographic scope;
- effective date/time;
- fuel grade;
- price used;
- calculation timestamp.

Future price updates must not silently change historical facts.

---

# 9. End Work / Open Trip — D-07 / A-2

## D-07 — End Work while On Route

**RESOLVED.**

`End Work` is a finalization/review action, not an immediate destructive close.

If the Supervisor attempts End Work while a Trip remains `IN_TRANSIT`:

1. do not invent `Arrived`;
2. do not automatically close the Work Session;
3. present the existing end-of-work review/summary behavior;
4. provide **Continue Working** as the recovery path;
5. `Continue Working` restores the prior active operational state without losing traceability.

If the Supervisor explicitly confirms **End Work Anyway**:

- Work Session may become `ENDED`;
- the open Trip becomes `INTERRUPTED`;
- no artificial `Arrived` event is created;
- retained mileage/location evidence follows D-01/D-02 rules.

`Continue Working` is a recovery/fallback path, not a normal lifecycle step.

### Activity in progress

Do not mix End Work with the Activity execution screen.

While Activity is `IN_PROGRESS`:

- restore the Supervisor to the active Activity when the app is reopened;
- require the approved `Complete` or `Leave` path and Outcome;
- do not auto-close the Activity;
- do not invent an Outcome;
- backend must reject an invalid End Work transition while Activity remains active and return authoritative state.

Remove the prior R2 rule that automatically marked an active block internally incomplete on End Work.

---

# 10. Privacy Notice and Administrative Corrections — D-08

## D-08.1 — Location/privacy notice

**RESOLVED.**

Show one clear plain-language location/privacy notice:

- during onboarding or first activation;
- before the first device/browser location-permission request.

It should explain simply that CER Route uses location during the workday to record travel and calculate operational mileage.

Do not repeat this notice during normal operation.

Do not turn it into recurring operational friction.

---

## D-08.2 — Post-close correction / recalculation authority

**RESOLVED.**

Only **Admin** may initiate post-close corrections or recalculations of historical records.

Corrections must occur through controlled Web Admin actions and backend services/jobs.

Normal business operation must not rely on direct database editing.

Each correction/recalculation must preserve:

- original value/fact;
- corrected/current value;
- reason;
- initiating Admin;
- timestamps;
- complete audit trail;
- job/result status when relevant.

No automatic or silent historical recalculation is allowed.

Direct database intervention is reserved for exceptional technical recovery procedures, not normal Admin operation.

---

# 11. Mobile Authentication Continuity — D-09

## D-09 — Technical decision delegated to Development

CER does not prescribe access-token duration, refresh-token design, cookie lifetime or session-rotation implementation.

CER defines the requirement:

> An active Work Session must not lose operational continuity merely because authentication expires.

Also:

> A pending offline queue must be recoverable/synchronizable securely after reauthentication if reauthentication becomes necessary.

The developer/agent must determine and document the appropriate technical design, including as applicable:

- secure renewal;
- refresh/rotation;
- lifetime;
- revocation;
- session recovery;
- offline queue protection;
- mobile UX;
- security/minimum privilege.

Do not leave D-09 as an unresolved CER configuration decision.

---

# 12. Time Handling — D-10 / A-5

## D-10 — Technical decision delegated to Development

CER does not require a Supervisor timezone catalog or manual timezone assignment in V1.

Product requirements:

1. Every operational event must record the real date/time it occurred.
2. Timezone/offset context must be preserved sufficiently to reconstruct local chronology correctly.
3. A Work Session belongs to the local calendar date on which `Start Work` occurred, even if it crosses midnight.
4. Timezone handling must not block or interrupt:
   - Start Work;
   - Start Trip;
   - Arrived;
   - Activity;
   - location capture;
   - other lifecycle events.
5. Supervisor should not have to configure timezone to operate the product.

The developer/agent owns the technical strategy for:

- server time;
- device time;
- UTC storage;
- local offset/timezone capture;
- daylight-saving transitions;
- clock skew;
- synchronization.

Do not keep D-10/A-5 as open CER product ambiguity.

---
# 13. RTE01 Items That Must Be Removed or Corrected

When producing R3, search the entire report and correct all surviving statements that conflict with the approved decisions.

At minimum, remove or rewrite the following superseded statements/assumptions:

1. Any assumption of **one Activity only** per arrival.
2. Any implication that Activities from unrelated V0.7 contexts should be cross-selected.
3. Any hardcoded Outcome example treated as a system business rule.
4. Any rule that auto-closes an Activity on End Work or invents an Outcome.
5. Any statement that `Change Plan` remains available after `Arrived`.
6. Any statement allowing two active Work Sessions for the same Supervisor.
7. Any statement that automatically makes a new Work Session on the second device.
8. Any statement that location failure may block normal Supervisor work.
9. Any statement that cached/recovered location may be passed off as Fresh.
10. Any statement that email-only permanently satisfies the D-01 notification requirement.
11. Any statement that Haversine is an official mileage fallback.
12. Any statement that continuous GPS trace is the official V1 mileage source.
13. Any odometer/OCR/reconciliation requirement or odometer-based V-3 gate.
14. Any requirement to define an odometer error tolerance for RTE06.
15. Any implication that `Pending Calculation` may remain indefinitely open.
16. Any use of ambiguous `Unavailable` as the terminal mileage state if the approved `Not Calculable` terminology applies.
17. Any automatic historical mileage recalculation.
18. Any fixed routing provider prescribed by CER.
19. Any PWA/native/hybrid choice represented as a CER product decision.
20. Any fixed 90-day raw-location retention represented as CER-approved if no separate policy supports it.
21. Any single static tenant fuel price assumption.
22. Any fixed fuel provider/source represented as CER-selected.
23. Any direct-DB-editing workflow represented as normal Admin correction behavior.
24. Any token/session lifetime represented as a CER-selected technical configuration.
25. Any mandatory Supervisor timezone catalog/manual timezone setting.
26. Any statement that `End Work` immediately closes an open `IN_TRANSIT` Trip without the approved review/Continue Working path.
27. Any outdated cross-reference such as the prior multi-device reference to D-06 if it still survives.

---

# 14. Technical Recommendations vs Approved Requirements

R3 must clearly distinguish:

- **Confirmed Requirement / CER Decision**
- **Technical Decision Delegated to Development**
- **Technical Recommendation**
- **Validation Required**
- **Repository Finding**
- **Risk**

Do not promote a developer recommendation into a CER requirement.

Likewise, when CER has delegated a technical choice, do not keep presenting it as an unresolved product decision.

Examples of delegated technical decisions now include:

- D-03 client technology;
- D-04 routing provider/contingency implementation;
- exact D-01 retry/fallback algorithms and thresholds;
- fuel data source/ingestion implementation under D-06;
- D-09 authentication/session strategy;
- D-10 time/timezone implementation;
- detailed anomaly thresholds;
- exact recovery-window duration.

These items may remain implementation/validation work for future checkpoints, but they are **not open RTE01 product decisions**.

---

# 15. RTE01 Open-Item Closure

After applying this document, the RTE01 report must no longer present the following as unresolved CER product ambiguities:

- A-1;
- A-2 — resolved by D-07;
- A-3;
- A-4;
- A-5 — product requirement resolved; implementation delegated under D-10;
- A-6;
- A-7 — resolved by D-08.2;
- A-8 — resolved by D-06.

Likewise:

- D-01 — resolved;
- D-02 — resolved at product/model level;
- D-03 — technical decision delegated;
- D-04 — technical decision delegated;
- D-05 — confirmed retention principle;
- D-06 — resolved with source implementation delegated;
- D-07 — resolved;
- D-08 — resolved;
- D-09 — technical decision delegated;
- D-10 — technical decision delegated.

The report may still list **future technical validations or implementation work**, but these must not be described as unresolved CER RTE01 product decisions.

---

# 16. Required R3 Closure Matrix

Add/update the final closure matrix in the same RTE01 report.

At minimum include:

| Item | R2 State | CER Final Decision | Sections Updated | Final Classification |
|---|---|---|---|---|
| A-1 | Open | Start Work may exist without immediate Trip | ... | Resolved |
| A-2 / D-07 | Open / proposed | End Work review + Continue Working; explicit End Work Anyway may interrupt Trip | ... | Resolved |
| A-3 | R2 resolved | Multi-select in existing context; one execution block | ... | Resolved |
| A-4 | Open | Change Plan only On Route | ... | Resolved |
| A-5 / D-10 | Open | Product rule fixed; technical implementation delegated | ... | Delegated technical |
| A-6 | Open | Same active Work Session transfers/resumes across devices | ... | Resolved |
| A-7 / D-08.2 | Open | Admin-only controlled corrections/jobs | ... | Resolved |
| A-8 / D-06 | Open | Variable fuel reference + scheduled ingestion | ... | Resolved |
| D-01 | R2 resolved | Final approved location hierarchy/notification requirement | ... | Resolved |
| D-02 | Open | Final mileage authority/lifecycle | ... | Resolved |
| D-03 | Open | Mobile-only requirement; technology delegated | ... | Delegated technical |
| D-04 | Open | Backend routing contract; provider delegated | ... | Delegated technical |
| D-05 | Open | Historical facts retained; raw location separately limited | ... | Resolved principle |
| D-06 | Open | Location/date/grade-variable fuel references | ... | Resolved |
| D-07 | Open | End Work review/recovery rule | ... | Resolved |
| D-08 | Open | One-time privacy notice + Admin corrections | ... | Resolved |
| D-09 | Open | Continuity requirement; auth mechanism delegated | ... | Delegated technical |
| D-10 | Open | Time requirements fixed; implementation delegated | ... | Delegated technical |

---

# 17. Validation Required Before Returning R3

Before sending the revised report to CER, perform a document-level consistency pass.

Explicitly answer at the end of the report:

1. **Does any CER product ambiguity from RTE01 remain open?**
2. **Does any section contradict the final decisions in this document?**
3. **Does any section still present a delegated technical decision as if CER must choose the implementation?**
4. **Does any section contain a superseded odometer/OCR/Haversine-official-fallback requirement?**
5. **Does any section still auto-close an active Activity or invent Outcome?**
6. **Does the report still contain any single-static-fuel-price assumption?**
7. **Does the report treat Missing/Degraded/Recovered/Fresh location according to the approved model?**
8. **Does every mileage calculation have a path from transient `Pending Calculation` to a terminal state?**
9. **Was any product code modified?**
10. **Was any RTE02+ work started?**
11. **Can RTE01 now be proposed as `Completed — ready for CER certification`?**

If any answer to 1–8 indicates inconsistency, fix the report before returning it.

---

# 18. Do Not Change

Do not:

- write CER Route product code;
- start RTE02;
- create migrations;
- implement providers;
- implement notifications;
- implement routing;
- implement fuel ingestion;
- implement authentication changes;
- redesign the approved V0.7 flows beyond the decisions in this document;
- create additional product terminology;
- hardcode mockup example values as universal business rules;
- silently resolve new product questions not covered here.

If implementation consequences are discovered, document them as:

- `Technical Recommendation`;
- `Validation Required`;
- or `Future Checkpoint Input`.

Do not convert them into a new CER decision without authorization.

---

# 19. Deliverable

Return **one updated document only**:

`CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT.md`

Increment its revision from R2 to **R3**.

The R3 report must:

- incorporate all decisions above throughout the relevant sections, not only in an appendix;
- update the executive summary;
- update ambiguity/decision tables;
- update lifecycle/state model;
- update data/domain model where necessary;
- update geolocation/mileage assessment;
- update fuel model;
- update mobile strategy;
- update security/audit;
- update test strategy;
- update risks/dependencies;
- update RTE02 readiness;
- include the final closure matrix;
- remove obsolete recommendations/contradictions.

**Proposed final checkpoint status after successful application:**

`Completed — ready for CER certification`

No later checkpoint work is authorized by this document.
