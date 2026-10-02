# CER Route — RTE06 Final Development Closure
## Product Owner Instructions for Development Agent
### Revision 003

**Purpose:** close the single remaining Development-side gap identified in `CER_ROUTE_RTE06_FIELD_CORRECTIONS_FINAL_CLOSURE_REPORT_005.md` and hand RTE06 back to CER ready for final physical/field certification.

**Mode:** final closure only.  
**Do not reopen completed RTE06 scope.**  
**Do not start RTE07.**  
**Do not start RTE10-A01 OCR.**  
**Do not introduce Location Permission Enforcement.**

---

# 1. CER Review of Report 005

CER accepts the following as closed from Development, subject only to the final regression required by this instruction:

- Recovered location requires verifiable acceptable quality.
- Unknown accuracy is not accepted as authoritative evidence.
- The approved quality rule is enforced coherently across the affected acquisition path and on the authoritative side of the system.
- Grossly inaccurate or unverifiable location evidence cannot become an official mileage waypoint.
- Rejected evidence preserves the approved privacy boundary.
- `recovery_accuracy_rejected` remains the approved reason for rejected Recovery candidates; the specific distinction between known-bad accuracy and unknown accuracy may remain in immutable attempt evidence.
- START odometer task restoration is implemented.
- END odometer task restoration is implemented.
- Camera/page recreation no longer leaves the user on an unrelated screen with an unresolved odometer task.
- OCR remains out of scope and manual confirmation from a valid photo remains supported.
- The additional silent-evidence-loss findings discovered during Development were valid and the resulting hardening is accepted in principle.
- Location Permission Enforcement remains a future product-hardening item and is not part of RTE06 closure.

CER also accepts Development's decision to apply the location-quality rule consistently where necessary to make the product requirement true. This is not treated as unauthorized scope expansion.

---

# 2. Remaining Gap

Report 005 identifies one remaining Development-side acceptance gap:

> The client-side bounded behavior for queued location evidence has not been demonstrated end-to-end using the real browser/offline queue.

The implementation exists and the server-side truthful terminal behavior is already covered, but RTE06 cannot be returned as Development-complete until the complete behavior is demonstrated.

**Classification:** `PENDING VALIDATION`

This is the only Development item authorized by this instruction.

---

# 3. Objective

Demonstrate that queued location evidence cannot remain indefinitely in a retry state and that, once its valid processing window is exhausted, the system reaches a bounded and traceable outcome consistent with the approved RTE06 model.

Required product outcome:

```text
queued location evidence
→ temporary inability to complete
→ bounded processing/retry
→ valid processing window ends
→ entry no longer retries indefinitely
→ event reaches a truthful traceable final condition
```

There must be no unexplained long-lived state where an operational event has:

- no accepted location evidence;
- no truthful Missing/final resolution;
- and a queue entry retrying indefinitely.

---

# 4. Development Authority

CER is **not prescribing the technical implementation or test mechanism**.

Development must review the current architecture and determine the most reliable way to prove the required outcome.

Development owns:

- test design;
- browser/offline queue setup;
- timing/control strategy;
- fixture strategy;
- internal retry/expiry implementation details;
- helpers/refactors if genuinely required;
- observability needed to prove the result.

Prefer the smallest coherent solution that reuses the existing RTE06 architecture.

Do not return ordinary technical choices to CER.

---

# 5. Required Validation

The final evidence must demonstrate, end-to-end, at minimum:

## AC-FINAL-01 — Bounded queue behavior

A location-evidence queue entry that cannot be completed during its valid window does **not** retry indefinitely.

## AC-FINAL-02 — Truthful terminal outcome

After the valid window is exhausted, the corresponding operational event reaches a traceable terminal condition consistent with the existing RTE06 Missing/sweeper model.

## AC-FINAL-03 — No false success

The test must not pass merely because the queue entry disappears. It must prove that disappearance does not silently lose the operational fact.

## AC-FINAL-04 — Good path preserved

A valid queued location-evidence entry that becomes processable within its valid window must still complete normally.

## AC-FINAL-05 — Existing boundaries preserved

The closure must not alter:

- approved location-quality rules;
- Work Session / Trip / Activity states;
- exact offline correlation;
- Missing immutability;
- routing/mileage semantics;
- privacy boundaries;
- tenant isolation;
- odometer behavior;
- OCR scope.

---

# 6. Regression

If closing the remaining gap requires code changes, execute the directly affected regression.

At minimum confirm:

- location evidence;
- offline durability/correlation;
- Missing terminalization;
- routing/mileage impact;
- tenant isolation;
- typecheck/lint;
- production build.

If no production code changes are required and the work is purely validation, do not rerun unrelated suites without reason. Reuse the green evidence from Report 005 and add only the new closure evidence.

Do not weaken, remove, skip or xfail meaningful tests to obtain closure.

---

# 7. Acceptance Criteria

RTE06 Development closure is complete only when:

1. the real client/offline queue is demonstrated to be bounded;
2. an expired/unresolvable queued evidence item cannot retry indefinitely;
3. the related event reaches a truthful and traceable final condition;
4. no evidence is silently lost;
5. valid queued evidence still succeeds normally when the condition becomes resolvable in time;
6. relevant regression remains green;
7. no new `PARTIAL`, `GAP`, `BLOCKED` or `DECISION REQUIRED` exists in RTE06 Development scope.

No additional product decision is currently required from CER.

---

# 8. Required Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_FINAL_DEVELOPMENT_CLOSURE_REPORT_006.md`

Do not overwrite Report 005.

Keep the report concise and incremental.

Include:

1. Executive Result
2. Remaining Gap from Report 005
3. Final Behavior
4. End-to-End Evidence
5. Good-Path Evidence
6. Regression
7. Expected → Implemented → Evidence → Gap
8. Development Closure Inventory
9. CER Physical/Field Validation Handoff
10. Proposed Status

For the closure requirement use:

```text
Expected
→ Implemented
→ Evidence
→ Gap
```

Do not infer PASS from code presence alone.

---

# 9. Status Rule

Development may propose:

```text
IMPLEMENTATION COMPLETE / READY FOR CER FINAL FIELD CERTIFICATION
```

only if this final remaining gap is closed with executed evidence and no Development-side gap remains.

Development must not declare:

```text
RTE06 CERTIFIED
```

Certification belongs to CER after physical/field validation.

---

# 10. CER Handoff

The report must preserve the remaining CER-side validation items separately from Development closure.

CER will then execute/complete, as applicable:

- targeted physical revalidation of the odometer field correction;
- Android/Chrome and iPhone/Safari physical validation still required by the RTE06 field gate;
- field accuracy sampling;
- evidence-level distribution;
- final threshold calibration based on field evidence.

Do not convert those CER field items into Development gaps.

Do not require CER to repeat already validated scenarios unless the final Development change materially affects them.

---

# 11. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_FINAL_DEVELOPMENT_CLOSURE_REPORT_006.md`

**STOP.**

Do not start:

- RTE07;
- RTE10-A01;
- Location Permission Enforcement;
- any unrelated improvement.

CER will review Report 006 and proceed with the remaining physical/field validation before issuing final RTE06 certification.
