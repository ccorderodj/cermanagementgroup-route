# CER Route — RTE06 Final Field Correction

**Report 007** · incremental over Report 006 · branch
`feature/rte06-final-field-correction` · 2026-10-02

Scope: the END odometer defect CER reproduced in physical Android validation,
per `CER_ROUTE_RTE06_FINAL_FIELD_CORRECTION_INSTRUCTIONS_004.md`. Nothing in
§4's exclusion list was touched.

---

## 1. Executive Result

The defect is corrected and the field sequence is now reproduced as an automated
test — one that **fails against the previous code and passes against the new
one**, so the correction is demonstrated rather than asserted.

The cause was a single line that made two different facts indistinguishable:

```ts
const evidencia = await fetchSessionOdometer(sesion.id).catch(() => null);
```

That `null` meant both *"there is no odometer evidence"* and *"I could not
ask"*. The screen decides from it whether an END reading is pending, so a
momentary read failure ended up asserting that nothing was pending — and sent
the supervisor back to the workbench with the task still live on the server.
Pressing **End Work** a second time worked because the second read succeeded.

The correction separates the two. The read either returns what the server said
or throws; the caller is then forced to decide what to do with uncertainty, and
what it may not do is mistake it for an answer.

CER's rule is now structurally enforced in this path:

> An inability to read current state is not equivalent to an authoritative
> absence of state.

**No new user-facing message was added** (FR-06). Where the state is genuinely
unknown after a cold start, the screen that already existed for "could not be
loaded" is shown instead of a workbench that would silently claim nothing is
pending.

---

## 2. Field Defect Reproduced / Diagnostic

CER's observed sequence, and what each step was doing:

| Field step | What was happening |
|---|---|
End Work → Ending odometer | The END evidence row is created; the screen renders from it |
Take photo → camera | Android may recreate the renderer (the low-memory warning on one device) |
Return to CER Route | The page remounts and reconciles |
**Task disappears, user lands on workbench** | The odometer read failed; `.catch(() => null)` turned that into "no END evidence"; reconcile fell through to the workbench branch |
Press End Work again | A fresh read succeeded, the pending END evidence was found, and the screen returned — with the photo, because it had uploaded successfully |

CER's reading of the trigger is confirmed by this: memory pressure is a
**trigger**, not the defect. The second device reproduced the same class of
failure without the memory warning because any transient failure of that one
request produces it.

**Classification:** `CONFIRMED` — the mechanism is confirmed by code and by the
mutation run in §4.

---

## 3. Final Product Behavior

| Situation | Behaviour |
|---|---|
The read succeeds and an END reading is pending | The END screen is shown or restored, with its photo-backed state if the photo exists |
The read succeeds and nothing is pending | Normal flow continues — the workbench, or whatever the day's state is |
The read fails transiently | Retried up to three times within the same reconciliation, with a growing pause. A real blink resolves here and the supervisor sees nothing |
The read keeps failing and the user was already somewhere | They stay where they were. Not having been able to ask is not a reason to move them |
The read keeps failing on a cold start | The existing "Your workday could not be loaded / Try again" screen. It says what is true — the state is unknown — instead of a workbench that would assert nothing is pending |
The read recovers | The pending END task is restored automatically; no second **End Work** |

### Changed files

| File | Change |
|---|---|
`app/components/react/pages/RouteMyRoutePage/ui/RouteMyRoutePage.tsx` | New `leerOdometro`: reads the evidence, retries a transient failure a bounded number of times, and **throws** if it cannot. `reconcile` no longer computes any phase from a failed read. The End Work handler uses the same reader |

No change to Work Session, Trip or Activity models, to odometer business rules,
to OCR scope, to permissions or to tenant isolation. No migration. No backend
change.

### On the retry numbers

Three attempts, pauses of 400 ms and 800 ms. The failure being covered is the
first requests after a renderer recreation, which settles well under a second;
this covers a little over one second, which is enough for that case and short
enough that the screen does not feel stuck. It is not a general retry
mechanism — if the server is down it exhausts and says so.

---

## 4. END Restoration Evidence

`tests/e2e/test_rte06_end_restoration_browser.py`, real Edge, real `uvicorn`,
real page recreation. Only `GET /api/odometer/sessions/{id}` is intercepted and
answered 503 for the first three calls — the exact failure class the field
analysis identified. The rest of the application keeps answering, so what is
measured is the screen's decision when a read does not arrive.

### E3 — temporary read failure

`test_e3_a_temporary_read_failure_does_not_erase_the_pending_end_task`

The field sequence, with the failure where the analysis said it was:

1. a full day up to END pending, with the photo uploaded (`captured_at` asserted
   non-null in the database);
2. the read starts failing, and the tab is recreated;
3. **the workbench does not appear** — the assertion that matters, because that
   is where the supervisor used to land;
4. the interception is asserted to have actually fired, so the test cannot pass
   by having simulated nothing;
5. the read recovers; the same END task returns showing **Retake photo**;
6. the reading is confirmed **without a second End Work**, and the database
   shows `photo_confirmed` with the entered value.

### E4 — the hardening must not trap anyone

`test_e4_the_hardening_releases_when_the_answer_is_nothing_pending`

The other half, and the one that stops this correction from trading one defect
for a worse one. With no END reading pending, the read is failed three times:
the screen says the state could not be loaded — and as soon as the authoritative
answer arrives it obeys it and the workbench appears.

```
2 passed in 31.81s     exit 0
```

### The correction is verified by removing it

The previous semantics were restored — a failed read again collapsing into "no
evidence" — the production bundle rebuilt, and E3 re-run:

```
AssertionError: Locator expected to have count '1'
Actual value: 0
  waiting for get_by_text("Your workday could not be loaded")
  locator resolved to 0 elements

1 failed in 42.18s     exit 1
```

With the old semantics the uncertainty screen never appears, because the
application did exactly what CER saw in the field: it fell through to the
workbench. The fix was then restored, the bundle rebuilt, and the scenario
re-run green; `git diff` on that file shows only the intended change.

That is the discrimination this evidence needed: E3 reproduces the field defect
against the old behaviour and passes against the new one.

---

## 5. START Regression

`tests/e2e/test_rte06_odometer_lifecycle_browser.py` — journey A covers O1–O5
and Start Trip protection: camera return, tab recreation before the photo is
persisted, tab recreation with it persisted, manual confirmation with no OCR
suggestion, and Retake.

```
**4 passed, exit 0**, 54.6 s (E3, E4 and both odometer lifecycle journeys)
```

CER's field validation of START is therefore still backed by executed evidence,
and the correction did not touch the START path's own restoration sources.

---

## 6. Work Session Integrity

Asserted inside E3, against the database rather than the screen: after the
failure and the restoration, the Work Session **id** and **status** are
unchanged and the trip count is unchanged. Journey B asserts the same for the
ordinary restoration path.

Restoring the END screen decides which screen is shown; it writes nothing.

---

## 7. Tests / Regression

| Area | Result |
|---|---|
END restoration under read failure (E3, E4) | **2 passed, exit 0** |
START + END odometer lifecycle journeys (E1, E2, E5, E6, E7) | **4 passed, exit 0**, 54.6 s (E3, E4 and both odometer lifecycle journeys) |
Work Session END behaviour, no-photo exception, manual confirmation | **11 passed, exit 0**, 18.9 s (`test_odometer_end_work.py`) |
Typecheck + lint | **exit 0**, 0 errors |
Production build | **exit 0** |

Nothing was weakened, skipped, xfailed or removed. Broader regression was not
re-run: the change is confined to one component's reconciliation path, and
Report 006's full-suite evidence stands.

---

## 8. Expected → Implemented → Evidence → Gap

| AC | Expected | Implemented | Evidence | Gap |
|---|---|---|---|---|
1 | A temporary read failure cannot be read as authoritative absence | Yes — the read throws instead of returning a value that means both things | E3; and E3 **fails** when the old semantics are restored | — |
2 | The user is not returned to an unrelated workbench while END is pending | Yes | E3 asserts the workbench does **not** appear | — |
3 | END restores automatically after camera / page recreation | Yes | E3 after recovery; journey B for the ordinary case | — |
4 | No second End Work needed | Yes | E3 confirms the reading without pressing it again | — |
5 | Persisted photo remains available | Yes | E3 asserts `captured_at` and the **Retake photo** state | — |
6 | Non-persisted photo not fabricated | Yes, unchanged | Journey B asserts **Take photo** and `captured_at IS NULL` | — |
7 | Restoration does not reopen or duplicate the Work Session | Yes | E3 asserts same id, same status, same trip count | — |
8 | START restoration stays green | Yes | **4 passed, exit 0**, 54.6 s (E3, E4 and both odometer lifecycle journeys) | — |
9 | Manual confirmation without productive OCR unchanged | Yes, untouched | Journeys A and B assert `ocr_detected_reading` null | — |
10 | No new user-facing recovery message | Yes — none added | The uncertainty case reuses the pre-existing "could not be loaded" screen; no toast, banner or notification was introduced | — |
11 | Relevant regression green | Yes | §7 | — |
12 | No `PARTIAL` / `GAP` / `BLOCKED` / `DECISION REQUIRED` | Yes | — | — |

---

## 9. CER Physical Revalidation Checklist

Only the affected scenarios, as §14 asks.

1. **End Work → Take photo → normal return.** The END screen stays, with the
   photo and the reading field.
2. **End Work → Take photo → force the Android recreation** if it reproduces on
   that device. The END task must come back **by itself**.
3. **Confirm the photo is restored** — the button must read *Retake photo*, not
   *Take photo*.
4. **Confirm no second End Work is needed.** This is the field symptom; its
   absence is the acceptance.
5. **Confirm the day does not reopen** after the restoration.
6. **Quick START check**: open the reading from Start Trip, return from camera,
   confirm the task is still there.

If a device shows the "could not be loaded" screen after a recreation, that is
the correction working, not a failure: it means the state could not be read yet.
**Try again** must bring back the pending END task.

---

## 10. Proposed Status

```text
IMPLEMENTATION COMPLETE / READY FOR CER RTE06 FIELD CERTIFICATION
```

Not `RTE06 CERTIFIED` — certification is CER's after the targeted physical
revalidation above.
