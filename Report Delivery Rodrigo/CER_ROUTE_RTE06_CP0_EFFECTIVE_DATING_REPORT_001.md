# CER Route — RTE06-CP0: Vehicle Effective Dating
## Delivery Report 001
## Checkpoint: `RTE06-CP0` (§41 of `CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_INSTRUCTIONS_002.md`)

**Status:** `COMPLETED` — CP0 scope only.
**Date:** 2026-09-29
**Branch:** `feature/rte06-geolocation-mileage`

> This report covers **CP0 alone**. The full RTE06 report
> (`CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_REPORT_001.md`, 38 sections) is
> delivered at CP4 and is not replaced by this one. CP0 gets its own report
> because §41 requires it to be complete and verifiable *before* CP1, and
> because closing it changed a database invariant that deserves to be read on
> its own.

---

## 0. Read first

**1. Four of the five CP0 requirements were already built and already proven.**
`effective_from`, `effective_to`, occurrence-time resolution and the immutable
vehicle snapshot were delivered earlier (MR !24) with named tests for E1–E4.
CP0 was at 90%; this checkpoint closes the remaining 10%. §2.

**2. The overlap hole was worse than previously reported, and simpler.** An
earlier report of mine described it as "creating an assignment with a past
`effective_from` inside an already-closed period". Measured, it needs no
concurrency and no past date: a *closed future* period plus a new assignment
starting before it was enough. §3.

**3. Two mistakes of mine are reported with their cause**, one of which made a
test pass for the wrong reason. §9.

---

## 1. What CP0 required (§41)

| Deliverable | Status |
|---|---|
| Current resolver audit | `AS-BUILT / CONFIRMED` — §2 |
| `effective_from` / `effective_to` correction | `AS-BUILT / CONFIRMED` — delivered in MR !24, re-verified §2 |
| Occurrence-time handling | `AS-BUILT / CONFIRMED` — MR !24, re-verified §2 |
| **Overlap protection** | `AS-BUILT / CONFIRMED` — **this delivery**, §4 |
| Regression of Work Session snapshot + odometer behaviour | `AS-BUILT / CONFIRMED` — §7 |
| STOP if a new CER product decision is required | **not triggered** — §10 |

---

## 2. Current resolver audit

Measured against the code, not against a summary.

| Requirement §8 | State | Where |
|---|---|---|
| `effective_from` on the model | exists | `app/routers_api/vehicles/models.py` |
| `effective_to` on the model | exists | id. |
| Applies when `from <= T` and (`to IS NULL` or `T < to`) | exists | `VehicleAssignmentsDAO.effective_at()` |
| Start Work uses the **occurrence** time, not receipt | exists | `worksessions/service.py` — the instant is computed first, then the assignment resolved at it |
| Snapshot historical and immutable | exists | `test_the_vehicle_snapshot_does_not_change_retroactively` |
| E1 future assignment does not apply | proven | `test_a_future_assignment_does_not_apply_yet` |
| E2 current assignment applies | proven | `test_with_a_current_assignment_the_start_reading_is_pending_and_blocks` |
| E3 ended assignment does not apply | proven | `test_an_assignment_with_an_end_date_is_not_current` |
| E4 offline delayed Start Work | proven | `test_a_queued_start_work_resolves_the_vehicle_it_had_then` |
| No applicable assignment → session still starts, `vehicle_id = null`, odometer `NOT_REQUIRED` | proven | `test_without_a_current_assignment_no_reading_is_required` |
| **E5 no overlap** | **was missing** | §3 |

---

## 3. The overlap hole, as measured

### What protected the invariant before

1. `uq_vehicle_assignment_current` — a **partial** unique index
   (`WHERE effective_to IS NULL`). Prevents two *open* assignments.
2. `VehicleAssignmentsDAO.overlaps_existing()` — Python, looked for a **closed**
   period containing the new `effective_from`.
3. A guard inside `assign()`: `desde < anterior.effective_from`.

### The case that passed all three

```
exists:   [Mar 1 → Apr 1)   closed
none:     no open assignment

assign(effective_from = Feb 1)
  → overlaps_existing(Feb 1) looked for  from <= Feb 1 AND to > Feb 1
    the March row starts Mar 1 > Feb 1   → not found
  → no open assignment, so guard 3 does not apply
  → inserted [Feb 1 → ∞), which overlaps [Mar 1 → Apr 1)
```

**Impact — `CONFIRMED`:** on March 15 two assignments were simultaneously
applicable, and `effective_at()` returned whichever the query plan produced
first. The vehicle a Work Session opened with stopped being deterministic — and
that is precisely the datum §8 requires settled before RTE06 builds anything on
top of it.

**Correction to my own earlier report.** I previously described this hole as
"creating an assignment with a past `effective_from` inside an already-closed
period". That is a *different*, narrower case — and it was the one protection 2
already caught. The real hole needs neither a past date nor concurrency. I had
reasoned about it instead of measuring it.

**Second defect, same code — `CONFIRMED`:** `overlaps_existing()` ran **outside**
`async with transaction()`, so it was a TOCTOU. Two concurrent requests with
different start dates both passed it.

---

## 4. Vehicle assignment rules as-built

### The invariant is now the database's

Migration `0009_assignment_no_overlap`:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE vehicle_assignment
ADD CONSTRAINT ex_vehicle_assignment_no_overlap
EXCLUDE USING gist (
    company_id WITH =,
    supervisor_profile_id WITH =,
    tstzrange(effective_from, effective_to, '[)') WITH &&
);
```

Verified in the database after `upgrade head`:

```
ex_vehicle_assignment_no_overlap
  EXCLUDE USING gist (company_id WITH =, supervisor_profile_id WITH =,
                      tstzrange(effective_from, effective_to, '[)'::text) WITH &&)
```

### Why `EXCLUDE` and not the house trigger pattern

This codebase's pattern for database invariants is a PL/pgSQL trigger
(`*_is_append_only`). It does not work here: two concurrent inserts do not see
each other, so a trigger would need explicit locking to be correct — hand-rolling
what `EXCLUDE` already does. `EXCLUDE` is correct by construction and atomic, so
it also removes the TOCTOU of §3 rather than relocating it.

### Why the interval is half-open

`[from, to)` is what keeps normal reassignment working. Reassigning closes the
previous row at `effective_to = desde` and opens the new one at
`effective_from = desde`; with `[)` those two intervals **touch without
overlapping**. With `[]` every reassignment in the product would have started
failing. Both borders are asserted — §6.

### A correction to my own recommendation, stated plainly

The execution recommendation said the extension question was why I had
originally preferred a trigger: *"`CREATE EXTENSION` requires superuser."* That
premise was wrong. Measured on this environment — PostgreSQL 16.4 — `btree_gist`
is a **trusted** extension (`pg_available_extensions.trusted = true`), so the
database owner installs it without superuser. I had asserted the constraint from
memory instead of querying it.

### `current_for_supervisor` renamed

§8.3 says not to retain a misleading definition of "current" that means only
`effective_to IS NULL`. The method meant exactly that, and the name invited the
confusion. It is now `open_for_supervisor`, with the docstring saying why it is
not the one that decides a Work Session's vehicle. Two call sites updated; both
are deactivation/delete guards, where "is a vehicle in this person's hands in the
register" is the right question — including when the assignment starts tomorrow.

### The docstring that was false

`VehicleAssignment`'s docstring claimed the partial index guaranteed that "a
supervisor cannot have two assignments effective at once". Given §3, that was
**false**. It now describes both constraints and which one is narrower, and says
what used to slip through. Documentation that lies is worse than none.

### What was removed

`overlaps_existing()` and its call site. The database guarantees it, so leaving
the Python check would be the dead code general rule 2 forbids — and it would
imply a protection whose real coverage was partial.

---

## 5. Error contract

`assign()` can now be rejected by two different constraints, and the person
assigning has to know which. The dispatch is by **PostgreSQL error code**:

| Code | Meaning | Message |
|---|---|---|
| `23P01` exclusion_violation | the period overlaps another | "That period overlaps another vehicle assignment for this supervisor. End the other one first, or pick a start date outside it." |
| `23505` unique_violation | an open assignment already exists | "This supervisor already has a current vehicle assignment. Reload and try again." |
| anything else | unknown integrity violation | generic 409, **cause not invented** |

**Not by text, and not by `constraint_name`.** Measured: SQLAlchemy's asyncpg
dialect wraps the original exception in its own `IntegrityError`, so
`constraint_name` never reaches `exc.orig` — only `sqlstate` survives. I wrote
the mapping on `constraint_name` first, and a test caught it: the overlap
returned the generic fallback message instead of naming the overlap. §9.2.

### On where the `IntegrityError` is caught

An earlier version of my recommendation said it must be caught **outside**
`async with transaction()`. That is too absolute, and I am correcting it rather
than restructuring working code. The real rule is: **do not swallow it and then
commit** — that leaves the session in rollback and `commit()` raises
`PendingRollbackError` → HTTP 500, which is what happened twice in this project.
Catching it inside and **re-raising** — which `assign()` already did — is
correct: the exception leaves the context manager, which rolls back and never
attempts a commit. Nothing was restructured here.

---

## 6. Scenario evidence — E5

`tests/integration/test_vehicle_assignment_overlap.py` — **8 tests, 0 failures,
exit 0.**

| Test | What it pins |
|---|---|
| `test_a_start_date_before_a_closed_period_is_rejected` | **the case of §3**: closed `[+30d, +60d)`, then open from `+10d` → **409**, message names the overlap, and **nothing is written** (one period remains) |
| `test_a_start_date_inside_a_closed_period_is_rejected` | what `overlaps_existing()` did catch is still caught, same status code — deleting it loosened nothing |
| `test_a_normal_reassignment_still_works` | the border `[)` permits: the close instant **equals** the open instant, two rows, first closed, second open |
| `test_consecutive_closed_periods_that_touch_are_allowed` | the same border with no open assignment, so the result does not depend on the partial index |
| `test_a_future_assignment_after_an_open_one_is_still_rejected` | an open `[t, ∞)` swallows any later period, so `assign()` closes the previous one at the new date instead of overlapping — constraint and service logic agree |
| `test_the_database_rejects_an_overlap_written_directly` | the invariant is the **database's**: a raw `INSERT` is rejected with `23P01`, so a script or a future module cannot write the overlap either (invariant 6) |
| `test_two_simultaneous_assignments_produce_one` | real concurrency via `asyncio.gather`: exactly one success, one period. The deleted check read outside the transaction; the constraint has no window |
| `test_the_constraint_is_scoped_per_company` | `company_id WITH =` is present: one tenant's assignment does not block another's |

**Why a specific case and not a generic one.** A generically-written overlap test
passes against the three old protections and proves nothing. The first test is
the one that went through them.

---

## 7. Regression

| Batch | Tests | Result | Exit |
|---|---|---|---|
| E5 (new), run standalone first | 8 | **0 failures** | 0 |
| Odometer, odometer End Work, odometer/OCR preflight, Route admin configuration, Route foundation, Trips | 62 | **0 failures** | 0 |
| Remaining integration suite (everything else under `tests/integration`, the 8 E5 tests included) | 424 | **0 failures** | 0 |

**Total: 486 integration tests, 0 failures, every batch exit 0.** The 8 E5 tests
appear in both the first and third batches; counted once, the distinct total is
486.

Batched deliberately: it isolates a failure and makes progress observable. No
test was weakened or removed. No `skip`, no `xfail`.

**Browser suites: `NOT RUN`.** CP0 changed no frontend file and no user-facing
flow, so no browser journey covers anything this delivery altered. They are
`NOT RUN`, not passed.

**Nothing depended on the removed messages** — verified by `grep` across `tests/`
and `app/` for both old strings. The frontend surfaces `detail` as a string and
decides by HTTP status, not by text (`SupervisorSetupPanel.tsx`), so the new
message displays with no frontend change.

---

## 8. Migration checks

| Check | Result |
|---|---|
| `import app.main` | **exit 0** |
| `npm run check` (typecheck + lint) | **`NOT APPLICABLE`** — no file under `app/components/react` was touched; `git status` confirms it |
| Production build | **`NOT APPLICABLE`** — same reason |
| `alembic upgrade head` | **exit 0** |
| Constraint present in the database | **verified** by `pg_get_constraintdef` — §4 |
| `btree_gist` installed | **verified** in `pg_extension` |
| `alembic downgrade -1` | **exit 0** |
| `alembic upgrade head` again | **exit 0** |
| `alembic heads` | **1 head** — `0009_assignment_no_overlap` |
| Autogenerate roundtrip | **0 operations** — the generated revision body was `pass`; probe revision deleted |

**Existing data is not interpreted.** The constraint is added against the data as
it stands. If some company already held an overlap created by the §3 hole,
`ALTER TABLE` **fails and the migration stops** — which is correct: an ambiguous
business datum is not silently corrected so a migration can finish. Deciding
which assignment wins is a per-company call, and not this migration's.

| Migration metric | Value |
|---|---|
| Records evaluated | all `vehicle_assignment` rows, implicitly, by `ALTER TABLE` |
| Records modified | **0** — the migration adds a constraint and transforms nothing |
| Records skipped | 0 |
| Records requiring human review | **0 in this environment** (the migration succeeded, so no overlap existed here) |

---

## 9. Findings, including my own errors

### 9.1 My earlier description of the hole was wrong — `CONFIRMED`, corrected

I reported the overlap as needing a past `effective_from` inside a closed period.
That case was already protected. The real one needs neither a past date nor
concurrency. **Cause:** I reasoned about the code instead of running it. The test
that now pins it is the measured case, not the one I had imagined.

### 9.2 I wrote the error mapping on an attribute that does not arrive — `CONFIRMED`, fixed

The first version dispatched on `exc.orig.constraint_name`. The overlap test
failed because the mapping fell through to the generic message: SQLAlchemy's
asyncpg dialect wraps the original exception, so that attribute is absent. Fixed
by dispatching on `sqlstate`, which is a documented PostgreSQL contract, after
**measuring** what the exception actually exposes.

### 9.3 A test of mine passed against the wrong constraint — `CONFIRMED`, fixed

`test_the_database_rejects_an_overlap_written_directly` first inserted a row with
`effective_to = NULL`. That hits `uq_vehicle_assignment_current` — the **old**
partial index — so the test would have passed without ever exercising the new
constraint. It now inserts a **closed** overlapping row and asserts `23P01`
explicitly. This is the failure mode worth naming: a green test that proves
something other than what it claims.

### 9.4 A blocked operation, reported rather than worked around

`git restore .` was refused by the environment's safety classifier as
irreversible local destruction. I did not work around it: the stale working tree
was parked with `git stash` instead, which is recoverable. That stash still
exists and holds only content already committed to `dev`; it can be dropped
without loss, but that is the user's call, not mine.

---

## 10. STOP conditions (§45)

Evaluated one by one against CP0's scope. **None triggered.**

| Condition | State |
|---|---|
| A certified RTE03/RTE04/RTE05 rule would have to change | **no** — the reassignment border is preserved and asserted (§6) |
| A new role or capability is required | **no** — no capability added or changed |
| A new Trip / Work Session / Activity state is required | **no** |
| A privacy product decision is needed | **not applicable to CP0** |
| A new CER product decision is required (§41 CP0 STOP) | **no** — §8.3 delegates the implementation of the invariant to Development, and this is that implementation |

The other nine conditions concern location evidence, mileage and the routing
provider, none of which CP0 touches.

---

## 11. Files changed

| File | Why |
|---|---|
| `app/migrations/versions/0009_vehicle_assignment_no_overlap.py` | new — the extension and the `EXCLUDE` constraint, with `downgrade` |
| `app/routers_api/vehicles/models.py` | the `ExcludeConstraint` declared on the model so metadata matches the schema; the false docstring corrected |
| `app/routers_api/vehicles/dao.py` | `current_for_supervisor` → `open_for_supervisor`; `overlaps_existing()` removed |
| `app/routers_api/vehicles/service.py` | the Python overlap check removed; `_conflicto_de_asignacion()` added, dispatching on `sqlstate`; two call sites renamed |
| `tests/integration/test_vehicle_assignment_overlap.py` | new — the 8 E5 tests of §6 |
| `_cer_delivery/CER_ROUTE_RTE06_EXECUTION_RECOMMENDATION_001.md` | the two corrections of §4 and §5 written where the next reader will find them |

---

## 12. Expected → Implemented → Evidence → Gap

| Expected (§39) | Implemented | Evidence | Classification |
|---|---|---|---|
| AC-1 `effective_from` respected at Start Work | yes | §2, MR !24 | AS-BUILT / CONFIRMED |
| AC-2 `effective_to` respected at Start Work | yes | §2, MR !24 | AS-BUILT / CONFIRMED |
| AC-3 snapshot uses occurrence time | yes | §2 — E4 proves it across the offline delay | AS-BUILT / CONFIRMED |
| **AC-4 overlapping assignments cannot produce two applicable vehicles** | yes | **§4, §6 — 8 tests** | AS-BUILT / CONFIRMED |
| AC-5 no-vehicle Work Session remains valid | yes | §2 | AS-BUILT / CONFIRMED |
| AC-6 existing odometer behaviour intact | yes | §7 — 62 tests | AS-BUILT / CONFIRMED |
| AC-7 OCR production not pulled into RTE06 | yes | untouched; `NoSuggestionReader` still the runtime reader | AS-BUILT / CONFIRMED |
| AC-39 migration checks green | yes | §8 | AS-BUILT / CONFIRMED |
| AC-40 no RTE07+ implemented | yes | nothing outside `vehicles/` and its tests | AS-BUILT / CONFIRMED |

No `PARTIAL`, `NOT IMPLEMENTED / GAP`, `DEVIATION`, `UNAUTHORIZED DECISION`,
`DECISION REQUIRED` or `BLOCKED` inside CP0 scope.

AC-8 through AC-38 belong to CP2–CP4 and are **`NOT STARTED`**, not passed.

---

## 13. Operational action required elsewhere

**One, and it is real.** The migration runs `CREATE EXTENSION IF NOT EXISTS
btree_gist`. In the shared environment the migrating role must have `CREATE` on
the database. On PostgreSQL 13+ `btree_gist` is *trusted*, so being the database
owner is enough and superuser is not required — but **this was verified locally,
and local is not shared.** Confirm it before deploying, because the migration
fails at its first statement otherwise.

No capability, no seed, no bootstrap, no configuration change.

---

## 14. Proposed status

**RTE06-CP0 — `COMPLETED`.** All five §41 deliverables are in place with named
evidence, and the STOP condition was evaluated and not triggered.

This is **not** a proposal to certify RTE06. CP1 through CP4 have not started,
and AC-8..AC-38 remain `NOT STARTED`.

### Next step

RTE06-CP1 — the written audit and technical decisions: lifecycle correlation,
location architecture, V-1..V-5 status, the closed routing provider decision,
threshold strategy, migration plan, waypoint/segment model, and confirmation that
production OCR stays out of scope. The substance is already drafted in
`_cer_delivery/CER_ROUTE_RTE06_EXECUTION_RECOMMENDATION_001.md`.

# STOP
