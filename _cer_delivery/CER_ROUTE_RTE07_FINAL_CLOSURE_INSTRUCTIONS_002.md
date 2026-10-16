# CER Route — RTE07 Final Closure
## Today / Live Operations
### CER Closure Instructions for Development Agent
### Revision 002

## 1. Context

RTE07 — Today / Live is functionally implemented and already aligned to the approved CER Route V0.7 baseline on desktop and mobile.

The current implementation already demonstrates:

- V0.7 Today / Live baseline located and used;
- desktop structure and detail panel aligned;
- mobile list-first behavior and full-screen detail aligned;
- server-side authorization with `route.live.read`;
- tenant isolation;
- authoritative Work Session / Trip / Activity state mapping;
- Official Miles semantics;
- no map / no continuous tracking;
- no hierarchy implementation;
- no new persistence;
- relevant regression green.

The only remaining work for Development is:

1. apply CER's decision on the `estimated fuel` visual deviation;
2. close the missing validation evidence for freshness/error behavior already implemented.

This is a **closure delta**, not a redesign and not a new feature sprint.

RTE10-A01 remains paused and is unrelated.

---

# 2. CER Decisions — Approved

## D-01 — Estimated Fuel

CER approves the current visual treatment.

The V0.7 `estimated fuel` slot must remain present in the supervisor detail and must show the neutral value:

`—`

until an authoritative fuel-price source exists.

### Required interpretation

- Preserve the approved V0.7 visual hierarchy.
- Do not remove the Estimated Fuel slot.
- Do not invent a price per gallon.
- Do not use a hard-coded/default fuel price.
- Do not build Fuel Reference inside RTE07.
- Do not expand this checkpoint to create a new fuel module.
- Do not alter mileage semantics.

This resolves the deviation reported in RTE07 Report 001.

For RTE07, the correct state is:

`Estimated Fuel slot preserved / no authoritative value available / neutral "—"`

This is **not** a remaining gap after this decision is recorded.

---

## D-02 — Today / Live Freshness

CER approves the already implemented freshness behavior:

- approximately 30-second refresh while Today / Live is visible;
- polling/refresh pauses while the browser tab is hidden;
- returning to the visible tab triggers an immediate refresh;
- no WebSocket requirement for RTE07.

Do not redesign or replace this mechanism merely to satisfy testing.

The pending item is **validation evidence**, not a product decision.

---

# 3. Objective

Close all remaining RTE07 evidence gaps and return the checkpoint to CER with no unresolved:

- `PARTIAL`;
- `GAP`;
- `BLOCKED`;
- `DECISION REQUIRED`;

inside RTE07 scope.

Target status:

`RTE07 IMPLEMENTATION COMPLETE / READY FOR CER FINAL CERTIFICATION`

Development must not declare `RTE07 CLOSED`; final certification belongs to CER.

---

# 4. Scope

Only perform the following:

1. Record CER D-01 as the final resolution of the Estimated Fuel deviation.
2. Add/complete executed evidence for the four freshness/error scenarios that Report 001 listed as implemented but not separately tested.
3. If any of those tests reveal a real RTE07 defect, apply the minimum correction necessary within the existing approved behavior.
4. Re-run the affected RTE07 regression.
5. Deliver an incremental closure report.

---

# 5. Freshness / Error Evidence Required

The following scenarios must have explicit executed evidence.

## FC-01 — Automatic refresh reflects a real state change

Prove:

1. Today / Live is already open with an initial server-backed state.
2. Underlying supervisor operational state changes.
3. No manual browser reload is performed.
4. The page refresh mechanism executes.
5. Today / Live shows the new truthful state within the approved Live window.

The test must validate observable product behavior, not only that a timer callback was invoked.

---

## FC-02 — Refresh failure preserves truthful last-known state

Prove:

1. Today / Live has successfully loaded real data.
2. A subsequent refresh/read fails.
3. Existing truthful data remains visible.
4. The failed refresh does not turn into:
   - `Not started`;
   - `0 miles`;
   - an empty list;
   - a fabricated status.
5. The existing recoverable refresh/error indication is presented as designed.
6. A later successful refresh can recover normally.

Do not redesign the error UX unless this test exposes an actual defect.

---

## FC-03 — Hidden tab stops unnecessary freshness work

Prove:

1. Today / Live is visible and freshness behavior is active.
2. The document/tab becomes hidden.
3. Periodic refresh work does not continue aggressively while hidden.

The test should validate the actual implementation behavior, not a mocked assertion disconnected from the page lifecycle.

---

## FC-04 — Returning to foreground performs immediate refresh

Prove:

1. Today / Live is loaded.
2. The tab becomes hidden.
3. Relevant underlying state changes while hidden.
4. The tab becomes visible again.
5. An immediate refresh occurs without waiting for the next 30-second interval.
6. The changed state becomes visible.

---

## FC-05 — Multiple supervisors remain internally consistent

Close Report 001 edge case 17.

Prove one Today / Live read where multiple supervisors have different current conditions, for example:

- one `Not started`;
- one `On Route`;
- one `In Activity`;
- one `Work Ended` or `Working`;

and confirm:

- each row receives its own correct state;
- summary counts match the rows;
- no state from one supervisor bleeds into another;
- mileage aggregation remains consistent with row-level facts.

This can be integration-level if browser coverage would add no meaningful product evidence.

---

# 6. No Product Expansion

Do not use this closure work to change:

- Today / Live layout;
- desktop/mobile UX;
- V0.7 hierarchy;
- status terminology;
- summary cards;
- supervisor table columns;
- detail panel structure;
- Official Miles semantics;
- Work Session rules;
- Trip rules;
- Activity rules;
- hierarchy/data-scope architecture;
- RBAC architecture;
- location behavior;
- odometer/OCR;
- fuel-reference domain;
- Activity Explorer;
- Reports;
- RTE08+.

---

# 7. Development Autonomy

Development chooses the technical test mechanism and any minimal implementation correction required if the new evidence exposes a real defect.

Technical implementation choices remain with Development.

However:

- do not replace the approved freshness behavior with another architecture without a demonstrated blocker;
- do not change visible product behavior merely to make a test easier;
- do not weaken an assertion to make the suite green;
- preserve user-observable truthfulness.

If a test fails, establish first whether the failure is:

`PRODUCT DEFECT`
or
`TEST/HARNESS DEFECT`

before changing product code.

---

# 8. Acceptance Criteria

RTE07 Development closure is complete when all of the following are true:

1. CER D-01 is recorded: Estimated Fuel slot remains and shows `—`.
2. No fuel price or fuel-reference functionality was invented.
3. FC-01 automatic state refresh is executed and green.
4. FC-02 failed refresh preserves last-known truthful state and is green.
5. FC-03 hidden-tab pause is executed and green.
6. FC-04 foreground immediate refresh is executed and green.
7. FC-05 multi-supervisor consistency is executed and green.
8. Existing desktop behavior remains unchanged.
9. Existing mobile behavior remains unchanged.
10. Existing V0.7 visual fidelity remains unchanged.
11. Authorization and tenant isolation remain green.
12. Official Miles semantics remain green.
13. Relevant Work Session / Trip / Activity regression remains green.
14. Typecheck/lint/build remain green as applicable.
15. No new RTE07 `PARTIAL`, `GAP`, `BLOCKED` or `DECISION REQUIRED` remains.

---

# 9. Evidence Required

The closure report must show, for each FC scenario:

`setup → action → observed result → assertion → PASS/FAIL`

Do not report only test names.

For any defect found and corrected:

`symptom → root cause → correction → before/after evidence → regression`

If no product code changes are required, say so explicitly.

No new screenshots are required if visible UI did not change, unless a browser test exposes and corrects a visible defect.

The existing Report 001 screenshots remain valid visual evidence if the UI remains unchanged.

---

# 10. Existing Test Harness Finding

The previously reported async fixture/harness fragility remains outside RTE07 scope if:

- it is reproducible without RTE07 code;
- the affected RTE07 suites can execute through the repository's supported test grouping;
- it does not hide a product regression.

Do not turn this closure delta into a general test-harness refactor.

Record it only as pre-existing technical debt if still relevant.

---

# 11. Deliverable

Create the incremental report:

`Report Delivery Rodrigo/CER_ROUTE_RTE07_FINAL_CLOSURE_REPORT_002.md`

Do not overwrite Report 001.

Use these sections:

1. Executive Closure Result
2. CER Decisions Applied
3. Freshness Validation
4. Error-Recovery Validation
5. Multi-Supervisor Consistency
6. Product Changes Made, if any
7. Regression
8. Expected → Implemented → Evidence → Gap
9. Remaining Issues
10. Proposed Status

The Expected → Implemented → Evidence → Gap table must explicitly close the Report 001 items that were previously only `IMPLEMENTED`.

---

# 12. Status Rule

If all acceptance criteria above are green, propose exactly:

`RTE07 IMPLEMENTATION COMPLETE / READY FOR CER FINAL CERTIFICATION`

If any required scenario fails and cannot be corrected within RTE07 without a new product decision:

`RTE07 CLOSURE BLOCKED — CER DECISION REQUIRED`

and state:

`fact → impact → options → recommendation`

Do not leave it as `PARTIAL`.

---

# 13. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE07_FINAL_CLOSURE_REPORT_002.md`

**STOP.**

Do not start RTE08.

Do not resume RTE10-A01.

Do not promote unrelated work.

Wait for CER certification.
