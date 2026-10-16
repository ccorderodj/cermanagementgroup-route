# CER Route — RTE01 CER Decisions for Closure

**Purpose:** Incorporate the CER decisions below into the existing `CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT.md` and return RTE01 ready for final CER certification.

**Checkpoint:** RTE01 — Technical Baseline + Target Alignment  
**Authoritative product baseline:** CER Route V0.7 Updated  
**Instruction type:** Targeted correction / closure  
**Important:** Do **not** start RTE02 or write product code as part of this task.

---

## 1. Context

CER reviewed the RTE01 Technical Baseline Report and is providing the decisions required to remove the specific ambiguities identified during validation.

The existing RTE01 analysis remains valid unless explicitly changed by this document.

This is **not** a redesign of CER Route and must not be used to introduce new workflows, new terminology, new business objects visible to the user, or additional product scope.

The objective is to update the existing RTE01 report so that the approved V0.7 flow and the technical analysis are consistent and RTE01 can be closed without carrying these items forward as unresolved decisions.

---

# 2. CER Decision A-3 — Multiple Activities at an Arrival

## 2.1 Decision status

**A-3 — RESOLVED / APPROVED BY CER**

CER confirms that, after `Arrived`, the supervisor may select **one or multiple configured Activities** before pressing `Start Activity`.

This is a surgical change to the existing V0.7 interaction. The rest of the approved flow remains unchanged.

---

## 2.2 Approved supervisor flow

The supervisor flow remains:

`Start Trip → On Route → Arrived → Select Activity/Activities → Start Activity → Complete Activity → Outcome → Notes → Next Trip / Return Home`

Rules:

1. `Arrived` ends the travel leg. It does **not** automatically start the activity.
2. After `Arrived`, the supervisor selects one or more configured Activities in the existing Activity selector.
3. At least one Activity must be selected before `Start Activity` can proceed.
4. The supervisor presses `Start Activity` only once.
5. All selected Activities belong to the same execution block for that stop.
6. There is one activity start time and one activity completion time for the block.
7. Duration is derived from that single start/completion interval.
8. The supervisor presses `Complete Activity` once.
9. After `Complete Activity`, the **existing V0.7 Outcome step remains unchanged**.
10. Notes remain as currently defined in V0.7.
11. After completion, the normal V0.7 next-trip / return-home flow continues.

Do not create a separate timer, start action, completion action, Outcome, or Notes field for every selected Activity.

---

## 2.3 Outcome rule — do not change terminology or workflow

`Outcome` is the existing V0.7 concept and must remain exactly that.

**CER decision:** Outcome values are **tenant-configurable and managed by Admin**.

Therefore:

- Do not hardcode values such as `Completed`, `Follow-up Required`, `Escalated`, `No Contact`, or any other mockup value as a universal business enum.
- Values displayed in the mockup are examples of configured tenant data.
- Do not introduce a second completion-status field such as `Partially Completed`, `Not Completed`, or similar unless CER approves it in a future checkpoint.
- The selected Activities in the execution block share the same Outcome and Notes.

---

## 2.4 Activity configuration

Preserve the current V0.7 catalog simplification.

Where V0.7 defines an Admin-managed Activity list, its values remain tenant-configurable and should represent **broad operational classifications**, not detailed tasks or independent workflows.

Examples may be used for explanation, but they must not become hardcoded product values.

The system-defined V0.7 activity contexts/flows remain unchanged. Do not create new configurable Activity Types or a dynamic form builder as part of RTE01.

**Important:** Do not generalize this decision into changing unrelated V0.7 fields. Existing fields such as Reason, Delivery Type, Purpose, Received By, free-text references, etc. retain their approved semantics unless the baseline explicitly defines them as an Activity selector.

---

## 2.5 UX scope

The visible UX change is intentionally minimal:

**Before:** existing Activity selector = single select.  
**After:** existing Activity selector = multi-select.

Everything after `Start Activity` follows the already approved V0.7 flow.

Do not introduce a new visible concept called `Activity Group`, `Stop Group`, `Task Group`, or similar into the supervisor UX.

If an internal implementation needs a grouping construct, it is an engineering detail and must not redefine the approved product language.

---

## 2.6 Required RTE01 corrections for A-3

Update all RTE01 sections that currently assume:

- `activity (0..1 per arrival)`;
- completing one Activity automatically closes the Trip;
- one Arrival can only contain one selected Activity.

The revised report must consistently represent the approved rule:

> One arrival may contain multiple selected Activities executed within one activity execution block. They share one start time, completion time, duration, Outcome and Notes. The existing V0.7 workflow remains otherwise unchanged.

Do not use this correction to redesign Trip lifecycle beyond what is necessary to remove the previous one-activity assumption.

---

# 3. CER Decision D-01 — Location Acquisition and Missing Location Handling

## 3.1 Decision status

**D-01 — RESOLVED / APPROVED BY CER**

CER Route's priority is to obtain and store location evidence at every lifecycle event where location capture applies.

The application must make a best-effort attempt to obtain usable location evidence before classifying an event as missing location.

However, a location failure must **not stop the supervisor's operational workflow**.

---

## 3.2 Approved acquisition principle

The technical design must support a staged/fallback acquisition strategy.

Conceptually:

1. Attempt to obtain a current usable location.
2. If a current usable location cannot be obtained, attempt technically valid fallback mechanisms.
3. A last-known/cached position may be used as fallback when the platform/browser makes it available and when it satisfies the applicable quality/freshness rules.
4. If no usable location can ultimately be obtained, continue the operational action and record a confirmed missing-location event.

The exact retry algorithm, browser APIs, retry count, timing and implementation details belong to the development team and must be validated technically. RTE01 should define the behavior and constraints, not prematurely hardcode an implementation algorithm.

---

## 3.3 Location provenance and quality

Every stored location must preserve enough evidence to determine what was actually obtained.

Where applicable, retain:

- source/provenance;
- latitude/longitude;
- accuracy;
- device capture timestamp;
- server received timestamp;
- age/staleness when the location is cached/last-known;
- degraded/anomalous status when applicable.

A cached or degraded location must never be represented as a fresh location.

The system must never fabricate coordinates.

A cached/degraded location may be stored as evidence but is **not automatically authoritative for mileage**. Mileage eligibility depends on the later mileage rules, including location freshness, accuracy and D-02.

---

## 3.4 Supervisor UX when location fails

CER decision: location capture problems must not interrupt the normal supervisor flow.

The Supervisor UI must not show technical messages such as:

- GPS failed;
- missing location;
- timeout;
- accuracy error;
- retry diagnostics;
- repetitive browser/location warnings generated by CER Route during normal operation.

If all acquisition attempts fail, the requested operational action still succeeds and the workflow continues.

This requirement does not mean CER Route should bypass the browser/OS permission model. Any permission request required by the platform still follows the platform's own security behavior. The product itself should not add unnecessary technical interruption after the outcome is known.

---

## 3.5 Distinguish Degraded Location from Missing Location

The revised RTE01 must distinguish at least these two conditions conceptually:

### Location Degraded

A location was obtained and stored, but its provenance, age, accuracy or other quality characteristic means it may not be suitable for every downstream purpose.

A degraded fix is retained with its real quality/provenance metadata.

A degraded location does not automatically require an operational alert and does not automatically qualify for mileage.

### Location Missing

The applicable acquisition/fallback strategy was exhausted and no usable location evidence was obtained for the event.

This condition requires explicit back-office traceability and is eligible for notification according to tenant configuration.

---

## 3.6 Missing Location Event

When a location is definitively missing, CER Route must retain a back-office record sufficient to understand what happened.

The conceptual record must be able to identify, as applicable:

- tenant/company;
- supervisor;
- Work Session;
- Trip and/or lifecycle event affected;
- event kind (`Start Work`, `Start Trip`, `Arrived`, etc.);
- event timestamp;
- failure/reason code based on what the platform can actually determine;
- technical evidence available from the acquisition attempts;
- last-known/degraded fix information when relevant;
- notification status where needed.

Do not invent a failure cause that the browser/device cannot actually distinguish.

The exact persistence shape is an implementation decision for a later checkpoint; RTE01 must define the requirement and traceability expectation.

---

## 3.7 Back-office notifications

CER Route must support configurable notifications for confirmed missing-location events.

The design must allow tenant configuration of:

- notification recipients;
- supported back-office roles and/or specific users as recipients;
- in-platform notification;
- optional email notification.

Use existing Foundation/Core notification capability if it exists and is appropriate; do not duplicate a platform capability unnecessarily. If the current Foundation does not provide the required notification mechanism, document that as a future implementation need rather than inventing it in RTE01.

Notification behavior must avoid operational spam:

- do not notify for every internal retry;
- notify after the event is classified as a confirmed missing-location condition;
- preserve every underlying Missing Location Event even if the notification layer groups or deduplicates alerts;
- repeated/consecutive failures may be grouped for notification purposes without deleting the individual audit/tracking records.

---

## 3.8 Required RTE01 corrections for D-01

Update the RTE01 report anywhere it currently presents D-01 as unresolved or states a conflicting product rule.

The revised report must consistently state:

> Location capture is a high-priority best-effort requirement. CER Route attempts current location first and may use technically valid last-known/cached fallback evidence when available and acceptable. If usable location still cannot be obtained, the supervisor workflow continues silently, the system records the reason/evidence as a Missing Location Event, and configured back-office recipients may be notified through in-platform and/or email channels. Missing or degraded evidence is never fabricated or silently treated as authoritative mileage evidence.

Remove D-01 from the list of CER decisions still pending.

---

# 4. Items That Must Not Be Changed by This Closure

This instruction does **not** authorize changes to:

- CER Route independence from CER ERP;
- V0.7 Trip Purpose vs Activity distinction;
- Change Plan traceability;
- explicit Start Work / End Work behavior;
- Work Session midnight rule;
- approved free-text fields;
- existing Admin-configurable catalogs other than the multi-select behavior described above;
- the existing Outcome step or terminology;
- mileage authority/tolerance decision D-02;
- provider selection D-04;
- fuel model decisions not explicitly addressed here;
- Web/PWA/native decision except where already documented as technical context;
- any later RTE checkpoint.

Do not start product implementation while applying this closure instruction.

---

# 5. Required Agent Actions

Using the existing `CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT.md` as the document to correct:

1. Incorporate **A-3** exactly as approved above.
2. Incorporate **D-01** exactly as approved above.
3. Correct every section, table, state/lifecycle description, relationship diagram, risk entry and decision list that contradicts these decisions.
4. Preserve all RTE01 findings and evidence that remain valid.
5. Do not silently introduce additional CER decisions.
6. Do not reinterpret mockup example values as hardcoded business rules.
7. Do not start RTE02 or any product implementation.
8. Re-run only the repository checks necessary to confirm that no product code was changed; there is no need to repeat discovery work that is unaffected by these corrections.
9. Return the revised RTE01 report as a **single updated file**, not a second competing baseline report.

---

# 6. Closure Validation Required from the Agent

At the end of the revised RTE01 report, provide a concise closure matrix containing:

| Item | Previous State | CER Decision Applied | Report Sections Updated | Final State |
|---|---|---|---|---|
| A-3 | Open ambiguity | Multiple Activity selection within one execution block; V0.7 flow otherwise unchanged | list sections | Resolved |
| D-01 | Decision Required | Best-effort location + fallback + silent operational continuation + Missing Location Event + configurable back-office notification | list sections | Resolved |

Also state explicitly:

- whether any contradiction remains inside RTE01 regarding A-3 or D-01;
- whether any new product decision was introduced by the agent;
- whether any product code was changed;
- whether RTE01 can now be classified as `Completed — ready for CER certification`.

If the agent identifies a genuine contradiction that prevents applying either CER decision, it must flag the exact section and reason rather than choosing a different behavior on CER's behalf.

---

# 7. Expected Deliverable

Return the corrected:

`CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT.md`

The revised report must incorporate the CER decisions above and must not create a new competing technical baseline.

**Target status after correction:**

`RTE01 — Completed — ready for CER certification`

CER will perform the final certification before authorizing the next checkpoint.
