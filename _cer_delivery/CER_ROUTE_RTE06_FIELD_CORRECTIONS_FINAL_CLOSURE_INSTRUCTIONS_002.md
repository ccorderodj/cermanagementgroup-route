# CER Route — RTE06 Field Corrections Final Closure
## Product Owner Instructions for Development Agent
### Revision 002

**Purpose:** close the remaining Development-side gaps identified in `CER_ROUTE_RTE06_FIELD_CORRECTIONS_CLOSURE_REPORT_004.md` and return the field-correction delta ready for targeted CER physical revalidation.

**Operating principle:** CER defines the required product behavior, quality boundaries, evidence and acceptance criteria. Development reviews the complete repository/context and decides the best technical implementation plan within those boundaries.

**Do not start RTE07.**  
**Do not start RTE10-A01.**  
**Do not introduce Location Permission Enforcement in this closure.**

---

# 1. Context

Development implemented the two field corrections authorized by CER:

1. **F-1 — Recovered location quality hardening**
2. **Odometer START/END task restoration after camera/page lifecycle changes**

Report 004 also surfaced an additional reliability issue where valid location evidence could be lost silently under an internal timing/state condition.

The report correctly did **not** claim final readiness because:

- some geolocation scenarios remain unexecuted;
- odometer O1–O10 are not yet written/executed;
- clean regression is still pending;
- one remaining product-quality gap exists in the implemented Recovered acceptance rule.

This instruction is the **final Development closure delta** for those findings.

---

# 2. Current State — CER Assessment

## 2.1 Recovered location

The current implementation accepts a recovered candidate when:

```text
accuracy <= approved threshold
OR
accuracy is unknown
```

CER does **not** accept unknown accuracy as equivalent to verified acceptable accuracy.

A location point may become authoritative for mileage only when its quality can be evaluated and satisfies the approved rule.

**Classification:** `NOT IMPLEMENTED / GAP`

---

## 2.2 Silent loss of valid location evidence

Development identified a condition in which valid evidence could be rejected before the related operational state became ready and end up as neither:

- accepted location evidence;
- nor truthful Missing evidence.

Development already implemented a correction for the observed case, but the final solution must be evaluated against the full technical context rather than CER prescribing a specific HTTP/retry mechanism.

**Product requirement:** no valid location evidence may disappear silently because of an internal timing, ordering or transient state condition.

**Classification:** `IMPLEMENTED / REQUIRES COMPLETE VALIDATION`

---

## 2.3 Odometer START/END restoration

The implementation now attempts to restore the unresolved odometer task after camera return or page recreation.

The approach described in Report 004 is acceptable in principle, but CER will not certify it until Development demonstrates the required behaviors through automated evidence.

**Classification:** `IMPLEMENTED / PENDING VALIDATION`

---

## 2.4 OCR

Productive OCR remains outside this closure.

The active no-suggestion behavior is expected until:

`RTE10-A01 — Odometer OCR Production Hardening & Validation`

**Classification:** `OUT OF SCOPE / EXPECTED`

---

# 3. Objective

Complete the field-correction delta so that Development can truthfully propose:

```text
IMPLEMENTATION COMPLETE / READY FOR CER PHYSICAL REVALIDATION
```

The delta is complete only when:

1. recovered location evidence cannot become authoritative without verifiable acceptable quality;
2. valid location evidence cannot be lost silently because of internal timing/state conditions;
3. START and END odometer experiences recover correctly from the mobile camera/browser lifecycle;
4. no existing RTE03–RTE06 behavior is regressed;
5. all Development-side evidence required for closure is complete.

---

# 4. Product Requirements — Mandatory Outcomes

## FR-01 — Recovered evidence requires verifiable quality

A recovered point may become authoritative only when:

- its accuracy is known/measurable;
- and that accuracy satisfies the approved location-quality threshold.

The currently approved threshold remains the same policy used by Fresh:

```text
100 m default / current approved Fresh policy
```

A point with:

```text
accuracy unknown
```

must **not** silently become authoritative location evidence.

The existing staged location model remains:

```text
Fresh
→ Degraded Cached
→ Recovery
→ Missing
```

The exact technical handling of an unknown-accuracy candidate is delegated to Development, provided the result remains truthful and consistent with the existing staged model.

---

## FR-02 — Poor or unverifiable recovery must never become official mileage evidence

A candidate that does not satisfy the quality rule must not later appear as:

- accepted `location_fix`;
- official Trip waypoint;
- routed mileage input;
- calculated mileage provenance.

If no valid evidence is obtained through the existing approved acquisition paths, the existing Missing model must resolve the fact truthfully.

No coordinates may be fabricated.

---

## FR-03 — No silent evidence loss

For every location-capture attempt associated with an operational event, internal timing/order/state conditions must not cause valid evidence to disappear silently.

The final behavior must be deterministic and traceable.

A valid point that is temporarily unable to bind to its authoritative operational event must be handled safely according to Development's chosen architecture.

A condition that is genuinely final/invalid must not create an indefinite or misleading processing state.

CER is **not prescribing**:

- HTTP-status-specific logic;
- a retry algorithm;
- queue internals;
- helper structure;
- persistence mechanism.

Development must evaluate the full technical context and implement the most robust solution consistent with existing architecture and RTE06 semantics.

---

## FR-04 — START odometer experience must survive camera/browser lifecycle

When START odometer evidence remains unresolved:

- returning from camera must return the Supervisor to the START odometer task;
- page/browser recreation must restore the unresolved task;
- if a valid photo was actually persisted, it must be available for the pending confirmation flow;
- if the photo was never persisted, the UI must not pretend that it exists;
- Start Trip must remain protected until START odometer evidence is validly resolved;
- absence of OCR suggestion must not prevent manual confirmation from a valid photo.

The user must not be sent to an unrelated workbench state and forced to rediscover the pending task.

---

## FR-05 — END odometer experience must survive camera/browser lifecycle

When END odometer completion remains unresolved:

- returning from camera must restore the END odometer task;
- page/browser recreation must restore the unresolved END task;
- existing Work Session terminal state must remain truthful;
- restoring the END UI must not reopen the Work Session;
- photo persistence/non-persistence must be represented honestly;
- lack of OCR suggestion must not force an exception when a valid photo exists.

Existing approved END rules remain unchanged.

---

# 5. Existing Behavior That Must Not Change

Preserve:

- RTE03 Work Session lifecycle;
- RTE04 Trip lifecycle;
- RTE04 odometer business rules;
- END Option B behavior;
- RTE05 Activity execution;
- RTE06 staged location acquisition;
- RTE06 exact offline correlation;
- RTE06 Missing immutability;
- RTE06 privacy boundaries;
- RTE06 notification separation;
- official mileage as routed road distance;
- Change Plan waypoint semantics;
- no partial mileage;
- tenant isolation;
- existing permissions/capabilities;
- OCR remaining assistive/out of production scope;
- Location failures remaining best-effort/non-blocking under the currently approved RTE06 model.

---

# 6. Explicitly Out of Scope

Do not add or redesign:

- global Location Permission Gate;
- mandatory location permission at login;
- PC/Web location enforcement;
- continuous/background tracking;
- geofence;
- maps/navigation;
- routing-provider redesign;
- productive OCR;
- hierarchy/role changes;
- RTE07;
- RTE10-A01;
- unrelated UI redesign;
- new Work Session/Trip/Activity state machines.

The future question of **Operational Location Permission Enforcement** remains a separate product-hardening item and must not be mixed into this closure.

---

# 7. Technical Guidance — Non-Binding

The following are **technical observations, not implementation prescriptions**.

Development should use them to evaluate the best closure plan against the repository as a whole.

## TG-01 — Unknown accuracy

Report 004 shows that unknown accuracy is currently accepted during Recovery.

CER's required outcome is simply:

> unverifiable location quality cannot become authoritative.

Development decides the safest internal representation and processing path.

---

## TG-02 — Internal transient/final conditions

Report 004 found a timing/state condition where valid location evidence could be lost silently.

CER does **not** require a particular rule such as “retry every 409” or any other status-code recipe.

Development should evaluate:

- which conditions are genuinely transient;
- which are final;
- how existing queues/state synchronization already model those cases;
- how to avoid unnecessary retries;
- how to ensure a valid point does not disappear silently;
- how to preserve existing End Work recovery boundaries.

The implementation should be aligned with existing architecture rather than adding a local workaround that creates inconsistent behavior elsewhere.

---

## TG-03 — Odometer restoration

Report 004 describes an implementation based on domain evidence plus restorable UI intent.

CER accepts that direction if it satisfies the functional outcomes.

Development remains free to refine the internal approach if repository-wide context indicates a safer or simpler implementation.

Do not move transient UI state into domain persistence unless the architecture genuinely requires it.

---

# 8. Validation Required

Development must provide direct evidence for the unresolved scenarios from Report 004.

## 8.1 Geolocation

The behaviors represented by the following pending scenarios must be demonstrated:

- **G3** — candidate immediately above threshold is rejected;
- **G4** — grossly inaccurate recovered candidate (e.g. ~2,000 m) cannot become authoritative;
- **G6** — all Recovery candidates invalid → truthful Missing resolution;
- **G7** — Missing reason/fact correctly represents the condition;
- **G8** — rejected candidate privacy boundary remains intact.

Additionally add/adjust direct evidence for:

### G12 — Unknown accuracy
A recovered candidate whose accuracy cannot be verified:

- is not accepted as authoritative;
- cannot enter official routing mileage;
- resolves through the existing staged model truthfully.

The exact automated test organization is Development's decision.

If Development determines that equivalent or stronger tests better prove the same behavior, it may reorganize the suite, but the report must map the resulting evidence back to each required behavior above.

---

## 8.2 Odometer

The behaviors originally requested as O1–O10 must all be demonstrated.

Required behavioral coverage:

1. START normal camera return;
2. START page/browser recreation with persisted photo;
3. START recreation before photo persistence;
4. START valid photo + no OCR suggestion + manual confirmation;
5. START retake behavior;
6. END normal camera return;
7. END page/browser recreation;
8. END valid photo + no OCR suggestion;
9. END recreation where photo was not persisted;
10. existing no-photo exception remains unchanged.

Development may organize these tests differently if the same behavioral coverage is explicit and traceable.

---

## 8.3 Silent-loss finding

Add direct evidence showing that:

- a transient internal ordering/state condition does not permanently discard valid evidence;
- final invalid conditions remain bounded and truthful;
- no capture is left in an unexplained “neither evidence nor Missing” state after the system has reached its final resolution point.

This validation must exercise the actual mechanism selected by Development rather than merely assert implementation details.

---

# 9. Regression Required

Before proposing Development closure, run the relevant clean regression in isolation from conflicting test environments.

At minimum cover:

- Work Sessions;
- Trips;
- Activities / workbench;
- odometer;
- location evidence;
- staged Recovery;
- Missing events;
- exact offline correlation;
- routing/mileage;
- Change Plan;
- tenant isolation;
- migrations/constraints affected by the delta;
- typecheck;
- lint;
- production build.

Do not weaken, skip, xfail or remove existing meaningful tests to reach green status.

Any failure must be resolved or explicitly classified before closure.

---

# 10. Acceptance Criteria

Development closure requires all of the following:

1. Unknown/unverifiable Recovery accuracy cannot become authoritative.
2. Recovered acceptable evidence satisfies the approved quality rule.
3. A grossly inaccurate point cannot become official mileage evidence.
4. Invalid/unverifiable Recovery evidence resolves truthfully through the staged model.
5. Rejected coordinates are not fabricated or improperly persisted.
6. No valid evidence can be silently lost because of an internal transient condition.
7. Final invalid conditions remain bounded and traceable.
8. START odometer returns/restores to the correct unresolved task.
9. END odometer returns/restores to the correct unresolved task.
10. Persisted photo evidence is restored honestly.
11. Non-persisted photo state is not fabricated.
12. Start Trip remains correctly protected by START odometer requirements.
13. END restoration never reopens an ended Work Session.
14. Valid photo + no OCR suggestion continues to support manual confirmation.
15. Existing no-photo exception behavior remains unchanged.
16. Productive OCR is not introduced.
17. Location Permission Enforcement is not introduced.
18. RTE03–RTE06 relevant regression is green.
19. Tenant isolation remains green.
20. Migrations/constraints affected by this delta are validated.
21. Typecheck/lint/build are green.
22. No `PARTIAL`, `NOT IMPLEMENTED / GAP`, `BLOCKED`, or unresolved `DECISION REQUIRED` remains within this closure scope.

---

# 11. Development Authority

Development owns the technical plan.

Development may choose or revise:

- retry strategy;
- transient/final error classification mechanism;
- queue behavior within existing architecture;
- state restoration mechanism;
- helpers/refactors;
- test fixtures;
- test organization;
- internal APIs;
- data-access implementation details;
- UI state-management details.

Development should prefer:

```text
reuse existing architecture
→ low coupling
→ smallest coherent change
→ deterministic behavior
→ testability
→ observability
→ no hidden future debt
```

Do not ask CER to decide ordinary technical implementation details.

Escalate only if the required closure would force a change to:

- visible business behavior;
- approved location-quality rule;
- privacy model;
- tenant isolation;
- roles/permissions;
- Work Session/Trip/Activity states;
- official mileage definition;
- approved odometer business rules;
- production OCR scope;
- external infrastructure/cost with product impact.

---

# 12. Required Deliverable

Create a new incremental report:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_FIELD_CORRECTIONS_FINAL_CLOSURE_REPORT_005.md`

Do not overwrite Report 004.

Include only the information necessary to certify the delta:

1. Executive Result
2. Changes Since Report 004
3. Recovered Quality — Final Behavior
4. Unknown Accuracy — Final Behavior
5. Silent Evidence-Loss Finding — Final Resolution
6. Odometer START — Final Behavior
7. Odometer END — Final Behavior
8. Tests / Evidence
9. Regression
10. Security / Privacy / Tenant Isolation
11. Expected → Implemented → Evidence → Gap
12. Targeted Physical Revalidation Checklist for CER
13. Remaining Items, if any
14. Proposed Status

For each requirement use:

```text
Expected
→ Implemented
→ Evidence
→ Gap
```

If evidence is missing, classify it as pending. Do not infer PASS from code presence, build success or developer intent.

---

# 13. Status Rule

Development may propose:

```text
IMPLEMENTATION COMPLETE / READY FOR CER PHYSICAL REVALIDATION
```

only when every Development-side acceptance criterion in this instruction is confirmed with evidence.

Development must **not** declare:

```text
RTE06 CERTIFIED
```

Final certification belongs to CER after targeted physical validation.

---

# 14. Physical Revalidation Handoff

Once Development is genuinely ready, provide CER only the minimal physical-device scenarios needed to validate the changed behavior.

Do not require CER to repeat the entire RTE06 field protocol unless Development finds evidence of broader impact.

The handoff should be concise, operational and executable on the physical device.

---

# 15. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_FIELD_CORRECTIONS_FINAL_CLOSURE_REPORT_005.md`

**STOP.**

Do not start:

- RTE07;
- RTE10-A01;
- Location Permission Enforcement;
- any unrelated improvement.

CER will review the evidence and execute the targeted physical revalidation before issuing final RTE06 certification.
