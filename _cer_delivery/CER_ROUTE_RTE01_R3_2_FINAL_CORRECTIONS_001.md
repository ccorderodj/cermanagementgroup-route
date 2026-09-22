# CER Route — RTE01 R3.2 Final Documentary Corrections

**Purpose:** Apply the last three documentary consistency corrections identified by CER during the R3.1 certification review.  
**Current source reviewed:** `CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT 1.md` — Revision R3.1  
**Scope:** Documentation correction only.  
**Do not write product code. Do not start RTE02. Do not reopen approved CER decisions.**

---

## 1. Objective

Produce a corrected **R3.2** version of the RTE01 Technical Baseline report that resolves the three remaining consistency issues below.

These corrections do **not** reopen any `A-*` or `D-*` product decision.

The intent is to leave RTE01 in a state that CER can certify as:

`Completed / Certified`

provided the returned document contains no new contradiction.

---

# 2. Mandatory Output Numbering

Do **not** return another file using the same generic filename.

Every delivery or redelivery must use a **unique incremental delivery number** so CER can distinguish revisions without ambiguity.

Use this format:

`CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_001.md`

If another correction cycle is required, increment only the final delivery number:

- `CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_002.md`
- `CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_003.md`
- etc.

Do not overwrite or reuse a previous delivery filename.

Inside the document header also record:

- **Revision:** `R3.2`
- **Delivery:** `001` for the first R3.2 response

This incremental delivery-number rule should be followed for future CER Route checkpoint report returns as well, unless CER explicitly instructs otherwise.

---

# 3. Correction 1 — Return Home Trip must reach a terminal state

## Current issue

The R3.1 lifecycle defines the normal Trip flow as:

`IN_TRANSIT → ARRIVED → CLOSED`

when the arrival is followed by an Activity block.

However, the `Return Home` row currently ends at:

`IN_TRANSIT → ARRIVED`

and the next step is `End Work`.

That leaves the HOME Trip without an explicitly documented terminal transition.

## Required correction

Make the HOME Trip lifecycle explicit and internally consistent.

Approved interpretation:

> `Arrived Home` completes/closes the HOME Trip.  
> The Work Session remains `ACTIVE` until the Supervisor separately executes `End Work`.

Therefore:

- do not create an Activity block merely to close the HOME Trip;
- do not make `Arrived Home` end the Work Session;
- do not leave the HOME Trip in `ARRIVED` indefinitely;
- preserve the existing product rule that arriving home and ending work are two separate actions.

Update all affected sections consistently, including as applicable:

- lifecycle/state machine;
- §6.2 sequence mapping;
- transition tables;
- tests;
- state restoration;
- reporting assumptions;
- any diagram or prose that implies every `ARRIVED` Trip requires an Activity before closure.

If the implementation needs an explicit transition such as:

`IN_TRANSIT → ARRIVED → CLOSED`

for HOME without an Activity block, document it as a domain/lifecycle rule, not as a new Supervisor UX step.

---

# 4. Correction 2 — End Work location Recovery Window vs ACTIVE-session collection boundary

## Current issue

R3.1 correctly states both of the following:

1. Location acquisition also occurs at `End Work`, and an event may not become `Missing` until its approved Recovery Window is exhausted.
2. Location writes are accepted only while the Work Session is `ACTIVE`, and once work ends the product must stop normal location collection.

Without an explicit boundary, those two rules can conflict if the `End Work` location attempt is still inside its Recovery Window when the Work Session transitions to `ENDED`.

## Required correction

Document a narrow technical rule that preserves both requirements:

> The `End Work` location acquisition attempt belongs to the End Work lifecycle event and may complete its already-started bounded recovery process after the session-end action, solely for that event. This does not reopen general tracking after the Work Session ends.

The report must make clear that:

- `End Work` is never blocked waiting for a GPS lock;
- the Work Session may become `ENDED` immediately according to the approved lifecycle;
- an End Work location acquisition/recovery operation that was initiated as part of that lifecycle event may finish asynchronously within its bounded recovery window;
- any resulting Fresh/Degraded/Recovered evidence is associated only with the already-created End Work event/session closure;
- if the bounded recovery window expires without usable evidence, create the corresponding `Missing Location Event`;
- no new generic location capture, breadcrumbs, Trip tracking, or unrelated position collection is allowed after the Work Session is `ENDED`;
- this exception is event-scoped and bounded, not a relaxation of the privacy boundary.

The development team may determine the exact persistence/job mechanism, but the report must remove the apparent contradiction between:

- D-01 recovery requirements; and
- the post-End-Work collection boundary.

Update affected sections consistently, especially:

- §8.4;
- §8.6;
- §10.3;
- lifecycle/End Work handling;
- tests.

Add a named test that proves:

> End Work does not wait for location, the session ends normally, the event-scoped recovery may still resolve afterward, and no unrelated post-session location is accepted.

---

# 5. Correction 3 — Raw location retention must not break historical mileage provenance

## Current issue

R3.1 correctly establishes:

- raw location evidence has its own limited retention policy;
- historical `Miles` and other derived operational facts survive that purge;
- `mileage_result` currently references `departure_fix_id` and `arrival_fix_id`.

If the referenced raw `location_fix` rows are physically purged, those references and the historical audit provenance can become invalid or incomplete.

## Required correction

Define explicitly how historical mileage provenance survives raw-location retention.

The product requirement remains:

> Expiration of raw location evidence must never alter, orphan, invalidate, or make unauditable a consolidated historical `Miles` fact.

The development team may choose the implementation pattern, but the R3.2 report must specify the required outcome and the recommended model.

At minimum, a consolidated `mileage_result` must retain a durable historical snapshot/provenance sufficient to explain the calculation even if detailed raw fixes are later purged.

That retained historical calculation provenance should include, as applicable:

- departure coordinates used for the calculation;
- arrival coordinates used for the calculation;
- endpoint evidence level / condition;
- endpoint capture timestamps;
- accuracy values relevant to the calculation;
- routing provider;
- method/version;
- calculated distance;
- calculation timestamp;
- any anomaly/degraded indicators required to interpret the result.

The report may preserve `departure_fix_id` / `arrival_fix_id` while the raw rows exist, but the historical fact must not depend exclusively on those foreign-key references for long-term auditability.

The developer/agent should choose and document the technically clean approach, for example:

- immutable snapshot fields on `mileage_result`;
- a retained calculation-evidence record separate from purgeable raw telemetry;
- or another equivalent architecture that preserves the same guarantee.

Do **not** require CER to choose the storage implementation.

Update consistently:

- §7 data/domain model;
- §8.5.5 historical fact/provenance;
- §10.6 retention;
- retention tests;
- any FK/deletion assumptions.

Add a named test proving that:

> after raw location evidence eligible for purge is removed, the historical `Miles` record and the minimum calculation provenance required for audit remain intact and readable.

---

# 6. Do Not Reopen or Change

Do not change previously approved decisions, including:

- A-1 through A-8;
- D-01 through D-10;
- multi-Activity one-block model;
- no odometer in V1;
- no Haversine as official Miles;
- in-platform notification required / email optional;
- Mobile-only Supervisor;
- routing provider delegated;
- fuel source delegated;
- raw-location retention duration not fixed by RTE01;
- Admin-only post-close corrections;
- authentication/timezone implementation delegated;
- no new Supervisor Desktop experience;
- no new map requirement.

Do not introduce a new product decision to solve any of the three corrections above.

If a technical choice is required, classify it as:

`Technical Decision Delegated to Development`

or:

`Technical Recommendation`

as appropriate.

---

# 7. Validation Required Before Returning R3.2

Before returning the corrected report, verify and explicitly confirm:

1. Does every Trip type now have a documented path to a terminal state, including HOME?
2. Does `Arrived Home` close the HOME Trip without ending the Work Session?
3. Is `End Work` still independent from `Arrived Home`?
4. Can End Work complete without waiting for location acquisition?
5. Can the End Work event's already-started recovery process finish after session closure without allowing general post-session tracking?
6. Is any unrelated location capture after `ENDED` still rejected?
7. Can raw location evidence be purged without breaking the historical `Miles` fact?
8. Does historical mileage retain sufficient minimum provenance after raw telemetry expires?
9. Were any existing CER product decisions reopened or altered?
10. Was any product code modified?
11. Was any RTE02+ work started?
12. Is the report now internally consistent and ready for CER certification?

If any of items 1–8 is not clearly satisfied in the document, correct it before returning the file.

---

# 8. Required Deliverable

Return **one new file only**:

`CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_001.md`

For the first response.

Do not return the old R3.1 filename and do not overwrite an earlier report.

The document must show:

- **Revision:** R3.2
- **Delivery:** 001
- the three corrections incorporated into the relevant body sections;
- updated consistency/closure validation;
- confirmation that no source code was modified;
- confirmation that RTE02 was not started.

If CER requests another documentary correction after this delivery, return:

`CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_002.md`

and continue incrementally.

---

# 9. Expected Final Status

If the three corrections above are applied consistently and no new contradiction is introduced, the report may propose:

`RTE01 — Completed / Ready for CER Certification`

CER will make the final certification decision.
