# CER Route — RTE06 Final Development Closure

**Report 006** · incremental over Report 005 · branch
`feature/rte06-final-development-closure` · 2026-10-02

Scope: the single remaining Development gap named in Report 005, per
`CER_ROUTE_RTE06_FINAL_DEVELOPMENT_CLOSURE_INSTRUCTIONS_003.md`. RTE07,
RTE10-A01 and Location Permission Enforcement were not started, and no
completed RTE06 scope was reopened.

---

## 1. Executive Result

The gap is closed with executed end-to-end evidence, and closing it found one
more thing that had to be fixed for the required outcome to be true:

> The server-side sweeper — the third recovery path, the one that closes an
> event nobody ever reported — covered **three of the seven** location events.
> `start_work`, `end_work`, `activity_complete` and `activity_leave` had no
> terminal path at all.

That is not an incidental tidy-up. CER's §3 requires that no operational event
be left with no evidence, no truthful resolution, and a queue entry retrying
forever. Bounding the queue removes the third condition — but for those four
events it would have removed the *retry* and left the event with **no
resolution at all**, which is the same limbo through a different door.

Why it had gone unnoticed is the part worth recording: nothing bounded the
queue before this closure. The entry stayed in the device queue retrying
indefinitely, which kept the appearance that something was still handling the
event. Bounding the queue is what made the sweeper's blind spot observable.

Both halves are now demonstrated against the real browser, the real IndexedDB
queue and the real flush, and the bounded behaviour is verified by neutralising
it and watching the test fail.

---

## 2. Remaining Gap from Report 005

```text
The client-side bounded behavior for queued location evidence had not been
demonstrated end-to-end using the real browser/offline queue.
```

Report 005 had the implementation (`expiresAt` on each queued send, consumed by
`haCaducado`) and the server-side terminal behaviour under test, but not the
client bound itself. Classification then: `PENDING VALIDATION`.

---

## 3. Final Behavior

The required outcome, as it now runs:

| Step | What happens |
|---|---|
Evidence is captured | A point that passes the approved quality rule is queued with `expiresAt` |
`expiresAt` is derived, not invented | Company `recovery_window_seconds` + `sweeper_grace_seconds` — the same two values the server uses to decide it will close the fact itself |
The send fails transiently | 409 (evidence arrived before its session was `ACTIVE`): the entry stays and the attempt is recorded |
The window is exhausted | `haCaducado` is true, the entry is removed instead of retried |
The fact is still told | The sweeper closes the event with `no_client_report` — the observable fact, not a guess about the device |
The condition clears in time instead | The entry is sent normally and the point is written at the level it was measured |

### What changed in this delta

| File | Change |
|---|---|
`app/routers_api/location/service.py` | `sweep_unreported_windows` extended from three event kinds to all seven: adds `start_work`, `end_work` (subject `work_session`, `trip_id` left null because a session has no trip) and `activity_complete` / `activity_leave` (distinguished by `terminal_action`, the same source the client uses when capturing) |
`tests/e2e/test_rte06_bounded_queue_browser.py` | New: the two end-to-end scenarios |
`tests/integration/test_route_location_evidence.py` | New: work-session sweeping, plus a structural guard so no future event kind can escape the sweeper |

No frontend code changed in this delta. No migration was needed — the sweeper
is a query, and `missing_location_event.trip_id` was already nullable.

---

## 4. End-to-End Evidence

`tests/e2e/test_rte06_bounded_queue_browser.py::test_an_expired_queue_entry_stops_retrying_and_the_fact_is_still_told`

Real Edge, real `uvicorn`, real IndexedDB, real flush. Only
`POST /api/location/evidence` is intercepted and answered 409 — the rest of the
application runs normally, so the reload that re-triggers the flush is the real
one. The window is exhausted by rewriting the entry's `expiresAt` into the past
rather than waiting the real five minutes; the code exercised is the same and
only the clock is advanced.

What it asserts, in order:

1. the entry **stays** queued after the transient failure, with `attempts ≥ 1`
   and a non-empty `expiresAt`;
2. no `location_fix` row exists, because the server refused the send;
3. ageing touched exactly **one** entry — so the test cannot pass by having
   aged nothing;
4. after the next flush the queue is **empty**;
5. still no `location_fix` row — removing the entry did not sneak the point in;
6. the sweeper then produces exactly one `start_work` Missing with
   `no_client_report`;
7. and no coordinates were fabricated.

```
2 passed in 48.63s     exit 0
```

### The bound is verified by breaking it

AC-FINAL-03 warns against passing merely because the entry disappears. Rather
than argue that from the code, Development neutralised `haCaducado` — made it
always return false — rebuilt the production bundle and re-ran the scenario:

```
AssertionError: una entrada caducada no puede seguir en la cola reintentándose
assert [{'id': 'start_work:key:83b86515-…', 'endpoint': '/location/evidence',
         'evidence_level': 'fresh', …}] == []
  Left contains one more item

1 failed in 23.17s     exit 1
```

`haCaducado` was then restored, the bundle rebuilt, and the scenario re-run
green — the neutralisation left no residue (`git diff` on that file is empty).

That is the discrimination this test needed: with the bound removed, the entry
stays queued and the assertion that it is gone fails. The test cannot pass
against an unbounded queue.

### Server-side terminalisation

`tests/integration/test_route_location_evidence.py`:

- `test_the_sweep_closes_work_session_events_too` — `start_work` and `end_work`
  are closed with `no_client_report`, `subject_kind = work_session`, `trip_id`
  null, and no fabricated coordinates.
- `test_the_sweep_cannot_leave_an_event_kind_behind` — a structural guard: every
  value of `LocationEventKind` must appear in the sweeper. It does **not**
  prove each branch works; it makes adding an event without a terminal path fail
  the suite instead of passing unnoticed. It exists because the previous gap
  lasted exactly that way — four of seven events uncovered, with nothing saying
  so.
- `test_an_event_the_client_never_reported_is_closed_by_the_sweep` and
  `test_the_sweep_leaves_alone_what_already_has_an_answer` — from Report 005,
  still green.

```
4 passed in 8.88s      exit 0
```

---

## 5. Good-Path Evidence

`…::test_a_queued_entry_still_succeeds_when_the_condition_clears_in_time`

The same setup, with one difference: the transient condition is resolved
**inside** the window and `expiresAt` is left alone. The entry then disappears
because it was *sent*, not because it expired — and the two are distinguished by
whether the point arrived.

Asserts: the queue empties, exactly one `location_fix` exists for `start_work`
at level `fresh` (waiting in the queue does not change the level), and there is
**no** Missing for the same fact. Without this half, both scenarios would pass
against a queue that discarded everything, and "bounded" would be
indistinguishable from "broken".

---

## 6. Regression

Production code changed (one query), so the directly affected areas were
re-run.

| Area | Result |
|---|---|
Location evidence, Missing terminalisation, sweeper | **102 passed, 1 skipped, exit 0** (5 integration files, 1 min 44 s) |
Exact offline correlation | included above |
Missing immutability | included above |
Routing / mileage | included above |
Offline durability (browser) | **8 passed, exit 0** (browser, 2 min 59 s, with the two new ones) |
Bounded queue (browser, new) | **2 passed, exit 0** |
Tenant isolation | included above (`test_route_role_authority.py`) + **14 passed, exit 0** public surface |
Typecheck + lint | **exit 0**, 0 errors |
Production build | **exit 0** |

Nothing was weakened, skipped, xfailed or removed. The sweeper is called only
by the scheduled route job and by tests, so extending it changed no request
path.

Everything else in RTE06 was green in Report 005 and is not re-run here, per
§6: the full integration tier (735 passed, 15 skipped), the unit tier (132
passed), browser G1–G12 (11 passed) and the odometer lifecycle journeys (2
passed).

---

## 7. Expected → Implemented → Evidence → Gap

| AC | Expected | Implemented | Evidence | Gap |
|---|---|---|---|---|
AC-FINAL-01 | A queue entry that cannot complete in its window does not retry indefinitely | Yes — `expiresAt` per send, consumed by `haCaducado` | Browser scenario 1, **passed**; and **failed** with the bound neutralised | — |
AC-FINAL-02 | After the window, the event reaches a traceable terminal condition in the existing Missing/sweeper model | Yes — and the sweeper now covers all seven events, not three | `start_work` Missing with `no_client_report` in the same browser scenario; plus the two sweeper integration tests | — |
AC-FINAL-03 | No false success: disappearance must not silently lose the fact | Yes | Scenario 1 asserts the Missing **after** the queue empties, and asserts no point was written; the mutation run proves the test discriminates | — |
AC-FINAL-04 | A valid entry that becomes processable in time still completes | Yes | Browser scenario 2, **passed**: point written at level `fresh`, no Missing | — |
AC-FINAL-05 | No approved boundary altered | Yes | No change to quality rules, states, correlation, Missing immutability, routing semantics, privacy, tenant isolation, odometer or OCR scope; the only production change is one query that adds rows the model already defined | — |

---

## 8. Development Closure Inventory

Everything CER listed as accepted in §1 of the instruction remains as reported,
plus this delta:

| Item | State |
|---|---|
Recovered location requires verifiable acceptable quality | closed (005) |
Unknown accuracy not authoritative | closed (005) |
Quality rule enforced on the authoritative side | closed (005) |
Inaccurate/unverifiable evidence cannot become a mileage waypoint | closed (005) |
Privacy boundary for rejected evidence | closed (005) |
`recovery_accuracy_rejected` kept as the approved reason | closed (005) |
START / END odometer restoration | closed (005) |
Camera / page recreation | closed (005) |
OCR out of scope, manual confirmation supported | closed (005) |
Silent-evidence-loss hardening | **closed (006)** |
Bounded client queue, demonstrated end to end | **closed (006)** |
Truthful terminal condition for all seven events | **closed (006)** |

**No `PARTIAL`, `GAP`, `BLOCKED` or `DECISION REQUIRED` remains in RTE06
Development scope.**

---

## 9. CER Physical / Field Validation Handoff

These are **CER-side** items, not Development gaps.

1. Targeted physical revalidation of the odometer field correction — the six
   scenarios in §12 of Report 005. Nothing in this delta changes the odometer,
   so that list stands unchanged.
2. Android/Chrome and iPhone/Safari physical validation required by the RTE06
   field gate.
3. Field accuracy sampling.
4. Evidence-level distribution.
5. Final threshold calibration from field evidence.

One note relevant to item 5: since Report 005 the device reads the company's
configured thresholds instead of values compiled into the bundle, so a
calibration decided from field evidence now takes effect by changing the
platform policy. Before that fix it would not have.

Nothing in this delta requires CER to repeat an already validated scenario.

---

## 10. Proposed Status

```text
IMPLEMENTATION COMPLETE / READY FOR CER FINAL FIELD CERTIFICATION
```

Not `RTE06 CERTIFIED` — certification is CER's after physical and field
validation.

The basis for proposing readiness: the one remaining Development gap is closed
with executed end-to-end evidence; the bound is verified by breaking it rather
than by reading the code; the blind spot that closing it exposed is fixed and
guarded against recurrence; and the affected regression is green.
