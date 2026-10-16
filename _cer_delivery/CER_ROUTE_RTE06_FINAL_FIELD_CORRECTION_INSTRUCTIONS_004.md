# CER Route — RTE06 Final Field Correction
## Product Owner Instructions for Development Agent
### Revision 004

**Purpose:** close the final field defect found during CER physical validation after Report 006, without reopening unrelated RTE06 scope.

**Mode:** targeted field correction + validation + final closure report.

**Do not start RTE07.**
**Do not start RTE10-A01.**
**Do not introduce Location Permission Enforcement.**

---

# 1. Context

RTE06 Development was delivered in Report 006 as:

`IMPLEMENTATION COMPLETE / READY FOR CER FINAL FIELD CERTIFICATION`

During subsequent CER physical Android validation, START odometer behavior showed clear improvement:

- returning from camera restored the pending START odometer task;
- Retake behaved correctly;
- the pending odometer task remained visible.

However, CER reproduced a remaining defect in the **END Work / Ending Odometer** flow.

Observed field behavior:

```text
End Work
→ Ending odometer
→ Take photo
→ camera
→ return to CER Route
→ Ending odometer task disappears
→ user returns to My Route/workbench
→ user presses End Work again
→ Ending odometer reappears
→ previously uploaded photo is present
→ reading can then be confirmed
```

On one Android device Chrome also displayed:

`Unable to complete previous operation due to low memory`

A second device did not reproduce the memory warning.

CER therefore treats memory pressure / renderer recreation as a possible trigger, not as the product defect itself.

The product defect is:

> a temporary inability to read/reconcile the pending END odometer state must not be interpreted as proof that no END task exists.

Development's analysis identified a likely mechanism consistent with the field behavior: a failed evidence read can currently collapse into the same branch as “no pending END evidence.” CER accepts this as a strong diagnostic finding, but Development retains responsibility for the final technical solution.

---

# 2. Objective

Ensure that the END odometer task survives temporary reconciliation/read failures after camera/browser lifecycle interruptions.

Required product outcome:

```text
END odometer pending
→ camera
→ browser/tab may be recreated or temporarily unable to reconcile
→ CER Route must not collapse to unrelated workbench state
→ pending END task remains/restores correctly
→ if photo already exists, it remains available
→ user can continue to reading confirmation
```

---

# 3. Scope

This delta includes only:

1. correction of the END odometer restoration behavior when reconciliation/read temporarily fails;
2. direct automated evidence for that failure-and-recovery scenario;
3. regression of START and END odometer restoration;
4. targeted physical revalidation handoff for CER;
5. final incremental closure report.

---

# 4. Out of Scope

Do **not** add or modify in this delta:

- productive OCR;
- OCR suggestion quality;
- the initial `0` reading presentation;
- offline/local durability of photo binary data before upload;
- mobile bundle-size optimization;
- memory/bundle performance refactor;
- global recovery notifications/messages;
- Location Permission Enforcement;
- Work Session, Trip or Activity state models;
- odometer business rules;
- routing/mileage;
- RTE07.

The following are explicitly moved to:

`RTE10-A01 — Odometer OCR Production Hardening & Validation`

- productive OCR;
- final UX of the suggested/empty reading field;
- photo durability between camera capture and server upload;
- measurement and potential optimization of mobile memory/bundle footprint.

---

# 5. Functional Requirements

## FR-01 — Read failure is not absence

If CER Route cannot temporarily determine the current END odometer evidence state, it must not interpret that condition as:

```text
no pending END odometer task
```

and must not silently send the user back to an unrelated workbench state.

A temporary reconciliation failure must remain distinguishable from an authoritative “nothing pending” result.

## FR-02 — Preserve END task continuity

When END odometer completion is unresolved, the user must remain in or be restored to the END odometer experience after:

- returning from camera;
- page/tab recreation;
- temporary read/reconciliation failure;
- recovery from that failure.

The user must not need to press **End Work** a second time merely to rediscover an already-pending END odometer task.

## FR-03 — Persisted photo remains truthful

If the photo was successfully persisted before the interruption:

- the restored END task must show the existing photo-backed state;
- Retake may remain available according to the existing flow;
- the user may continue to reading confirmation.

If the photo was not persisted:

- CER Route must not pretend it exists;
- the existing capture state remains truthful.

## FR-04 — Work Session truth remains unchanged

Restoring the END odometer task must not:

- reopen an ended Work Session;
- create a second Work Session;
- create a duplicate Trip;
- change END business rules.

UI restoration and domain state must remain separate concerns.

## FR-05 — START behavior must not regress

The START odometer restoration that worked in field validation must remain intact.

The fix must not regress:

- Start Trip protection;
- START camera return;
- START page recreation;
- START Retake;
- manual confirmation without OCR.

## FR-06 — No new recovery message required

CER does **not** require a new message such as:

`We recovered your pending odometer reading`

for this closure.

If the correct pending task is restored automatically, the restored screen itself is sufficient feedback.

Avoid adding new notifications, toast messages or banners unless Development can demonstrate they are required to satisfy the behavior.

---

# 6. Product Rule

This delta formalizes the following rule:

> **An inability to read current state is not equivalent to an authoritative absence of state.**

For END odometer restoration, CER Route must preserve a safe and truthful user experience until the authoritative pending/non-pending state can be reconciled.

Development may generalize this principle internally where appropriate, but must not expand scope into unrelated workflows without evidence.

---

# 7. Technical Guidance — Non-Binding

Development's field diagnosis indicates that the current END reconciliation path may convert an evidence-read failure into the same outcome as “no END evidence.”

CER does **not** prescribe:

- a specific `catch` behavior;
- retry count;
- state container;
- router behavior;
- cache mechanism;
- API change;
- React implementation.

Development should review the complete flow and choose the smallest architecture-compatible solution that:

- preserves the pending END task during temporary uncertainty;
- resolves cleanly once authoritative evidence becomes available;
- does not simulate domain facts;
- does not duplicate interface state unnecessarily.

---

# 8. Validation Required

Development must provide direct evidence for at least the following behaviors.

## E1 — Normal END flow

```text
End Work
→ Take photo
→ return
→ END task remains visible
→ confirm reading
```

Expected: normal flow unchanged.

## E2 — END page recreation with persisted photo

```text
END pending
→ photo persisted
→ page/tab recreated
→ END task restored automatically
→ existing photo-backed state shown
```

Expected: no second End Work action required.

## E3 — END temporary evidence-read failure

Simulate the real failure class identified during field analysis:

```text
END pending
→ camera / recreation
→ first reconciliation/read fails temporarily
→ application does not collapse to workbench
→ later reconciliation succeeds
→ same END task restored
```

Expected: the user remains in a safe pending state and can continue.

## E4 — Failure followed by authoritative no-pending result

Prove that the hardening does not trap the user forever when the authoritative result truly indicates that no END odometer task remains pending.

## E5 — Persisted photo truthfulness

After restoration:

- persisted photo → photo-backed state;
- non-persisted photo → capture state;
- no fabricated evidence.

## E6 — Work Session integrity

After restoration:

- same Work Session;
- no reopening;
- no duplicate Work Session;
- no duplicate Trip.

## E7 — START regression

Re-run the directly relevant START restoration journey and confirm it remains green.

---

# 9. Regression

If production code changes, run the directly affected regression.

At minimum cover:

- START odometer restoration;
- END odometer restoration;
- Work Session END behavior;
- no-photo exception;
- manual reading confirmation without OCR;
- typecheck/lint;
- production build.

Use broader regression only if the chosen implementation affects broader shared behavior.

Do not weaken, remove, skip or xfail meaningful tests to obtain closure.

---

# 10. Acceptance Criteria

This field correction is complete only when:

1. a temporary END evidence-read/reconciliation failure cannot be interpreted as authoritative absence;
2. the user is not returned to an unrelated workbench while END odometer remains pending;
3. END odometer automatically restores after camera/page recreation;
4. a second press of End Work is not required to recover the task;
5. persisted photo state remains available when it truly exists;
6. non-persisted photo state is not fabricated;
7. END restoration does not reopen or duplicate the Work Session;
8. START restoration remains green;
9. manual confirmation without productive OCR remains unchanged;
10. no new user-facing recovery message is required;
11. relevant regression is green;
12. no `PARTIAL`, `GAP`, `BLOCKED` or unresolved `DECISION REQUIRED` remains in this delta.

---

# 11. Development Authority

Development owns the technical implementation plan.

Development may choose:

- reconciliation strategy;
- temporary-error handling;
- UI state preservation;
- test structure;
- helper/refactor strategy;
- retry mechanics if required;
- observability necessary to demonstrate the behavior.

Prefer:

```text
existing architecture
→ smallest coherent correction
→ truthful state
→ deterministic restoration
→ low coupling
→ testability
```

Do not return ordinary technical implementation decisions to CER.

Escalate only if closure would require changing:

- visible END business behavior;
- Work Session lifecycle;
- odometer evidence rules;
- OCR scope;
- permissions;
- tenant isolation;
- external infrastructure/cost.

---

# 12. Required Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_FINAL_FIELD_CORRECTION_REPORT_007.md`

Do not overwrite Report 006.

Keep the report incremental and concise.

Include:

1. Executive Result
2. Field Defect Reproduced / Diagnostic
3. Final Product Behavior
4. END Restoration Evidence
5. START Regression
6. Work Session Integrity
7. Tests / Regression
8. Expected → Implemented → Evidence → Gap
9. CER Physical Revalidation Checklist
10. Proposed Status

For each requirement use:

```text
Expected
→ Implemented
→ Evidence
→ Gap
```

---

# 13. Status Rule

Development may propose:

`IMPLEMENTATION COMPLETE / READY FOR CER RTE06 FIELD CERTIFICATION`

only if every Development-side criterion above is confirmed with executed evidence.

Development must not declare:

`RTE06 CERTIFIED`

Final certification belongs to CER after targeted physical revalidation.

---

# 14. CER Physical Revalidation Handoff

After Development closure, CER should only need to repeat the affected field scenarios:

1. END Work → Take photo → normal return;
2. END Work → Take photo → Android/browser recreation if reproducible;
3. confirm previously persisted photo is restored automatically;
4. confirm no second End Work action is required;
5. confirm the Work Session does not reopen;
6. START odometer quick regression check.

Do not require CER to repeat unrelated RTE06 field scenarios because of this delta.

---

# 15. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_FINAL_FIELD_CORRECTION_REPORT_007.md`

**STOP.**

Do not start:

- RTE07;
- RTE10-A01;
- Location Permission Enforcement;
- photo binary/offline durability;
- mobile bundle optimization;
- any unrelated improvement.

CER will perform the targeted physical revalidation and then decide final RTE06 certification.
