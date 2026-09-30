# CER Route — RTE06 Final Development Closure
## Delivery Report 003 (incremental — does not replace Reports 001 or 002)
## Instruction: `CER_ROUTE_RTE06_FINAL_CLOSURE_INSTRUCTIONS_004.md` (Revision 004)

**Proposed status:** `IMPLEMENTATION COMPLETE / READY FOR CER FIELD VALIDATION`
**Date:** 2026-09-30
**Branch:** `feature/rte06-final-closure`

---

## 1. Starting CER Findings

CER's review of Report 002 identified three items. All three are closed here.

| # | Finding | Status |
|---|---|---|
| 1 | Exact offline correlation incomplete for multiple lifecycle actions performed offline | **AS-BUILT / CONFIRMED** — §2–§9 |
| 2 | Migration safety for pre-existing `missing_location_event.notes` not acceptable | **AS-BUILT / CONFIRMED** — §12, §13 |
| 3 | Acceptance-count/status matrix internally inconsistent | **AS-BUILT / CONFIRMED** — §16, and the arithmetic error is named below |

**The counting error, stated plainly.** Report 002 wrote "23 of 28 met" while
its own row-by-row matrix showed 22 `AS-BUILT / CONFIRMED`, 5
`PENDING VALIDATION`, and criterion 28 itself `NOT MET` — which is 22 + 5 + 1 =
28, not 23 + 5. CER was right to reject the figure. This report separates
Development scope from CER field-validation scope so the arithmetic cannot drift
again (§16, §17, §18).

CER's accepted-as-closed list from §1 of the instruction was **not rebuilt**.
Regression re-proves it rather than re-implementing it (§15).

---

## 2. Exact Offline Correlation — Previous Gap

The correlation key of §14 is an **id created by the server**. So evidence
captured while the lifecycle action is still queued has nothing to point at.

Report 002's answer was to store the evidence with a *deferred subject* and
resolve it after reconnect — **and to refuse to bind when two pending actions of
the same kind made the mapping unprovable**:

```
Offline:  Start Trip A → Point A
          Start Trip B → Point B
Reconnect: two pending start_trip points, two new server ids
Result:    mapping unprovable → neither bound → both may become Missing
```

Truthful, and not sufficient. A valid measured point must not become Missing
because Development cannot tell which event it belonged to. CER classified it
`NOT IMPLEMENTED / GAP` and that classification was correct.

---

## 3. Correlation Architecture Selected

**The client's durable action key is persisted on the domain row that the action
creates.** The chain is then complete end to end:

```
client action id          already existed: PendingAction.id in IndexedDB
  → Idempotency-Key       already existed: the header these endpoints take
  → client_action_key     NEW: the created row keeps it
  → location_fix.subject_id
```

### Why this one

Three mechanisms were viable. This is the smallest.

| Option | Why not / why yes |
|---|---|
| Promote `IdempotencyRecord` into the correlation contract | **rejected**: the scheduler purges it hourly (`IDEMPOTENCY_TTL_HOURS`), and this evidence must outlive it by years |
| A new correlation table mapping client keys to domain rows | **rejected**: a second place where the same fact lives (invariant 9), and it would need its own lifecycle, cleanup and tenant scoping |
| **Persist the key on the row the action creates** | **selected**: three nullable columns. No new table, no new mechanism, no second state machine. The client already generated the key and already sent it — the row simply keeps it |

### Why it is not authority — §12

The server resolves the row by `(company_id, client_action_key)` and **then**
applies the same ownership resolution it already applied to a client-supplied
id: the subject must belong to the authenticated supervisor's work session.

A forged or borrowed key yields exactly what a forged id yields — **404**. The
`WHERE company_id` is in all three lookups, so a key from another tenant is
indistinguishable from one that does not exist, which is the correct answer:
existence is not confirmed. Asserted in §14.

### What the deferred mechanism became

**Deleted.** `subjectPending`, the flush-time `resolverSujeto` and the
"refuse when ambiguous" branch are gone. With the key there is nothing to
deduce, so the code that deduced is not needed — and the behaviour CER rejected
cannot recur because the path no longer exists.

---

## 4. Contract / Data Changes

### Migration `0013_client_action_key`

| Table | Column | Index |
|---|---|---|
| `work_session` | `client_action_key VARCHAR(64) NULL` | `uq_work_session_client_action_key` unique **partial** `WHERE ... IS NOT NULL` |
| `trip` | id. | id. |
| `trip_purpose_change` | id. | id. |

**Partial on purpose.** Rows created before 0013 have no key and one cannot be
invented for them, so they stay `NULL`; a full unique would collide them with
each other. And the partial unique is what makes a replay unable to create a
second row with the same key — §5.9 guaranteed by the database rather than by
code.

**`activity_execution` is deliberately absent**, and this is a scope statement,
not an omission: it is created by `activity/start`, which is **not queueable
offline**. If the action cannot happen offline, its evidence cannot either, so
there is nothing to correlate. The mechanism extends with one more column the
day that action becomes queueable. This is not a `GAP` because the precondition
does not exist.

### API contract

`LocationEvidenceIn` and `MissingLocationIn` accept **exactly one** of
`subject_id` or `client_action_key`. Neither, or both, is a 422.

Both would let a client send one row's id and another row's key, and the server
would have to decide which it believes. That decision must not exist. Asserted
in §14.

### Change Plan became a queued action

It was the **only** lifecycle action called directly, with no queue and no key.
That blocked two things the closure requires: surviving a network loss like
every other action, and binding its point to *that* change rather than another
in the same trip.

`queueChangePlan` was added and the endpoint now takes `Idempotency-Key` with
the same `claim`/`remember` pattern as its siblings. **No lifecycle rule
changed** — the visible flow is identical (`Change Plan → choose context →
fields → back to On Route`), it is only durable now. §5.13 respected.

The client no longer reads `/plan-changes` to learn what to bind to; the key
identifies the change directly. One fewer round trip.

---

## 5. Start Work Offline Evidence — O1

`tests/integration/test_route_exact_correlation.py`

| Assertion | Result |
|---|---|
| The session is created with the key, and the row **keeps** it | `client_action_key` read back from `work_session` |
| The point identifies its subject by that key | 201 |
| It binds to **that** session | `subject_kind = work_session`, `subject_id` = the created id |
| One authoritative row | exactly 1 `location_fix` |

This is the case that could not work before: when the point is measured, the
session has no `id`.

---

## 6. Start Trip Offline Evidence — O2

**A real Start Trip scenario**, as §6 requires — not a Start Work substitute.

The key that identifies the trip is the one from the action that **creates** it
(the plan), not from starting it: the trip row carries the column, and the
departure waypoint belongs to the trip.

| Assertion | Result |
|---|---|
| Trip created with the key | 201 |
| Departure point binds by key | 201 |
| `subject_kind = trip`, `subject_id` = that trip | verified |

---

## 7. Multiple Offline Actions Evidence — O3

**The case that previously could not be resolved.**

The lifecycle does not permit two live trips at once, so the strongest valid
multi-action scenario the product allows is sequential: create, start, arrive,
finish the stop, create the next. No invalid lifecycle was invented (§6 O3
forbids it).

Both trips exist with their own keys. Their points arrive **afterwards and out
of order** — the second trip's first — which is what a queue draining after a
long outage produces.

| Assertion | Result |
|---|---|
| Two distinct trips | verified |
| `Point A → Event A`, `Point B → Event B` | the bound `subject_id`s match the two trips |
| No guessing | neither point needed resolution at flush time |
| **No Missing caused by ambiguity** | zero `missing_location_event` rows for `start_trip` |

The last row is the acceptance condition of §6 O3 and of AC-10.

---

## 8. Change Plan Offline Evidence — O4

| Assertion | Result |
|---|---|
| `trip_purpose_change` created with the key | `client_action_key` read back |
| The point binds to **that** change row | `subject_kind = trip_purpose_change`, exact id |

Before this delta the client had to read the history to learn what to bind to,
and offline that history did not exist yet.

---

## 9. Multiple Change Plans Evidence — O5

Two changes, two keys, two points — and the points are submitted **in reverse**,
with capture times that do not follow upload order.

| Assertion | Result |
|---|---|
| Each point binds to its own change row | keys map 1:1 to rows |
| **Ordering is domain ordering** | ordered by `changed_at`, the points come out in the same order as the change rows — not in upload order |

§5.4 and §5.6 satisfied, and measured against reversed input rather than
assumed.

---

## 10. Restart / Reauth / Replay

### Restart — O6 and Reauthentication — O7

Covered by the browser journeys delivered in Report 002 and re-run here
(§15): pending evidence survives closing and reopening the page in the same
context, and survives a fresh login, because the store is per-origin and not
per-session.

**The correlation now survives with them**, which is the new part: the entry
carries the action key, so what comes back after a restart is not "a point
needing a subject" but a point that already names its event.

### Replay — O8

| Assertion | Result |
|---|---|
| Same action replayed → one domain event | 1 `work_session` |
| Same point replayed → one authoritative row | 1 `location_fix` |
| **An accepted point is not replaced by a later replay** (§5.10) | a replay with *different* coordinates returns `replayed: true` and the **first** point's latitude remains |

Two separate guarantees and both are needed: the action's idempotency comes from
`Idempotency-Key`, the point's from the correlation unique index.

Concurrency over the same key was also asserted: two simultaneous submissions →
both 201, one row.

### One defect of mine found here — `CONFIRMED`, fixed

The idempotency re-read used `payload.subject_id`, which is **`None`** on the
key path. So the pre-check found nothing, the insert hit the unique index, and
the re-read after `IntegrityError` also searched for `None` and re-raised — a
**409 for a replay that had done everything right**.

Fixed by using the **resolved** subject id in both lookups. Found by the O8 and
concurrency tests, not by reading the code.

---

## 11. Missing Truthfulness — O10

Both halves are asserted, because one without the other proves little:

- a valid captured point is accepted and **nothing** converts it to Missing —
  zero `missing_location_event` rows;
- for a different event whose acquisition genuinely failed, the Missing path
  still works — 201 with `reason_code = permission_denied`.

The first is what this delta fixes: there is no ambiguity left that could lose a
point. AC-10 met.

---

## 12. Historical Notes Migration Safety

### The decision implemented

`MissingLocationEvent` stays strictly immutable. Mutable notes are **not**
restored. Notification state stays separate. Migration `0011` now **fails
safely** rather than counting and dropping.

### Behaviour, precisely

| Case | What happens |
|---|---|
| **count = 0** | the migration proceeds: notification state moves, the three columns drop, the trigger becomes the generic one. Log: `0011 \| missing_location_event -> notification: N migradas, M con estado desconocido migradas como pending` |
| **count > 0** | `RuntimeError` **before any schema change**. Alembic runs in a transaction, so nothing is applied: no new table, no dropped columns, no changed trigger, and the notes untouched |

The preflight runs before the first write, which is what makes "no partially
migrated state" true rather than hoped for.

### How the operator identifies the affected rows

The error message carries the query, so it does not have to be looked up:

```sql
SELECT id, company_id, event_kind, subject_id, occurred_at, notes
FROM missing_location_event
WHERE notes IS NOT NULL AND btrim(notes) <> ''
ORDER BY company_id, occurred_at;
```

### How it avoids data loss, and how it resumes

Nothing is transformed and nothing is dropped. The operator decides what that
text is worth — export it, record it in `audit_event`, or discard it knowingly —
empties the column, and re-runs. Once no note has content, the path is the
`count = 0` path. **There is nothing to undo, because nothing was applied.**

`btrim` is used on purpose: a column holding only spaces is not content, and
blocking a deploy for it would be a false positive that forces intervention
with nothing to preserve. Asserted.

### What was explicitly not done

No editable-notes feature was invented to save the old field, and the text is
**not** written into the notification table's `failure_detail`. That would be
turning historical free text into a field with a different meaning, which §7.3
forbids.

---

## 13. Migration Evidence

`tests/integration/test_route_notes_migration_safety.py` — **7 tests, 0
failures, exit 0.**

| # | Case | Result |
|---|---|---|
| **M1** | no historical notes | migration completes; notification state **moved** with its `delivered_at`; the fact is strictly immutable afterwards (an `UPDATE` raises `append-only`) |
| **M2** | one non-empty note | migration **stops**; the message names the count and carries the query; the 0010 schema is intact; **the note survives word for word** |
| M2b | whitespace-only note | does **not** block |
| M2c | resume after remediation | note emptied → re-run → completes |
| **M3** | unknown notification status | migrates as `pending`, **counted and logged**; the row does not disappear |
| **M4** | upgrade / downgrade / upgrade | clean, and the downgrade returns the state to the column **before** dropping the table |
| **M5** | schema roundtrip | **0 operations** |

### Two defects found by these tests — both `CONFIRMED`, both fixed

**1. `0011`'s downgrade could not run.** It dropped the composite unique on
`missing_location_event(id, company_id)` **before** dropping the notification
table whose foreign key depends on it → `DependentObjectsStillExistError`.
Autogenerate ordered it wrong, mirroring the upgrade ordering bug already fixed
in Report 002. The constraint now drops last.

**2. I had reported that roundtrip as passing when it had failed.** Report 002's
migration section claimed the 0011 down/up roundtrip was green. I had verified
it with `grep -c "Running downgrade"` — **counting log lines instead of checking
the exit code**. The lines appear whether the migration succeeds or throws.
Every migration check in this report is verified by exit code.

**3. A third, smaller one:** `0011` dropped `ck_missing_location_notification`
with `op.drop_constraint`, which fails if the constraint is already absent. It
now uses `DROP CONSTRAINT IF EXISTS` — a migration that falls over because
something it was going to delete is already gone is fragile for no gain; what
matters is that it does not exist afterwards.

| Check | Result |
|---|---|
| `alembic upgrade head` | **exit 0** |
| `alembic downgrade 0010` → `upgrade head` | **exit 0** both directions, verified by exit code |
| `alembic heads` | **1** — `0013_client_action_key` |
| Autogenerate roundtrip | **0 operations** |

---

## 14. Security / Tenant Isolation

Revalidated after the correlation change, as §12 requires.

| Requirement | Evidence |
|---|---|
| Tenant isolation | a key from another tenant resolves to **nothing → 404**, and nothing is written. The `WHERE company_id` is in all three key lookups |
| Authenticated supervisor ownership | unchanged: the resolved subject still has to belong to the supervisor's authoritative session |
| Exact event/action identity | §5–§9 |
| Replay idempotency | §10 |
| No client-selected tenant | the tenant still comes from the subdomain |
| No arbitrary subject id injection | an unknown key → 404; a foreign id → 404, as before |
| No cross-user evidence binding | the session boundary is unchanged |
| **An accepted point cannot be mutated through replay** | asserted with different coordinates: the first point stands |
| No raw coordinates in logs or audit | unchanged; the key is not a coordinate |
| No weakening of authorization | no capability added or changed; `route.worksession.execute` throughout |
| **The key is an identifier, not authority** | §3 — resolution by key ends in the same ownership check |

Also asserted: identifying the subject **neither** way, or **both** ways, is a
422.

---

## 15. Regression

| Batch | Tests | Result | Exit |
|---|---|---|---|
| RTE06 core: exact correlation, migration safety, location evidence, Missing immutability, mileage engine, CP0 overlap, platform diagnostics | **101** | **0 failures** | 0 |
| RTE03/RTE04/RTE05: odometer ×3, trips, activities, Route foundation, Route access | **227** | **0 failures** | 0 |
| Browser: RTE06 offline durability, RTE06 silent capture, RTE05 workbench, RTE03 work-session offline | **33** | **0 failures** | 0 |

**Total: 328 tests and browser journeys re-run for this delta, 0 failures, every
batch exit 0.**

Batched by file because the harness stops a background run at 30 minutes —
measured in Report 002, unchanged here. A stopped run is not reported as a pass.

The browser batch matters most for this delta: the capture module, the queue and
the workbench were all touched by the correlation change, and the RTE05 workbench
journeys staying green is the evidence that §36's "no extra step, no blocking
spinner" survived it.

**No test was weakened, skipped or xfailed.** Two tests changed for the approved
delta in Report 002 remain as documented there; this delta changed no existing
test's expectation.

The environment-gated live routing tests stay gated. **The routing code was not
changed by this delta**, so §13 of the instruction keeps Report 002's executed
live evidence valid: OSRM 2,061.60 m, Valhalla 2,059.00 m, divergence 1.001×,
primary-down → fallback 2,059.00 m with `provider=valhalla`.

| Check | Result |
|---|---|
| `npm run typecheck` | **0 errors** |
| `npm run lint:ts` | **0 errors** |
| `npm run build:prod` | **exit 0**, 2 pre-existing webpack size hints |

---

## 16. Expected → Implemented → Evidence → Gap

§14's 27 Development-closure criteria.

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | durable location evidence remains implemented | AS-BUILT / CONFIRMED | Report 002 §3, re-run §15 |
| 2 | exact offline correlation for Start Work | AS-BUILT / CONFIRMED | §5 (O1) |
| 3 | exact offline correlation for Start Trip | AS-BUILT / CONFIRMED | §6 (O2) |
| 4 | exact offline correlation for Change Plan | AS-BUILT / CONFIRMED | §8 (O4) |
| 5 | multiple pending server-generated events individually identifiable | AS-BUILT / CONFIRMED | §7 (O3) |
| 6 | multiple Change Plans individually identifiable | AS-BUILT / CONFIRMED | §9 (O5) |
| 7 | restart preserves correlation | AS-BUILT / CONFIRMED | §10 (O6) |
| 8 | reauthentication preserves correlation | AS-BUILT / CONFIRMED | §10 (O7) |
| 9 | replay creates no duplicate | AS-BUILT / CONFIRMED | §10 (O8) |
| 10 | valid evidence not converted to Missing by ambiguity | AS-BUILT / CONFIRMED | §7, §11 (O10) |
| 11 | original evidence level preserved | AS-BUILT / CONFIRMED | §13 of Report 002 + O9 |
| 12 | original capture timestamp preserved | AS-BUILT / CONFIRMED | O9 |
| 13 | tenant isolation intact | AS-BUILT / CONFIRMED | §14 |
| 14 | historical Missing facts strictly immutable | AS-BUILT / CONFIRMED | §13 (M1) |
| 15 | notification state separate | AS-BUILT / CONFIRMED | Report 002 §16, re-run §15 |
| 16 | migration does not silently destroy notes | AS-BUILT / CONFIRMED | §12, §13 (M2) |
| 17 | migration behaviour with existing notes tested | AS-BUILT / CONFIRMED | §13 (M2, M2b, M2c) |
| 18 | CP0 remains green | AS-BUILT / CONFIRMED | §15 |
| 19 | RTE03/04/05 regression green | AS-BUILT / CONFIRMED | §15.1 |
| 20 | mileage behaviour unchanged | AS-BUILT / CONFIRMED | §15 — mileage engine in the 101 |
| 21 | real routing/fallback behaviour intact | AS-BUILT / CONFIRMED | §15 — routing code untouched |
| 22 | V-4 remains confirmed | AS-BUILT / CONFIRMED | Report 002 §9 |
| 23 | migration checks green | AS-BUILT / CONFIRMED | §13 |
| 24 | typecheck / lint / build green | AS-BUILT / CONFIRMED | §15 |
| 25 | field validation protocol delivered to CER | AS-BUILT / CONFIRMED | §18 |
| 26 | no RTE07+ scope introduced | AS-BUILT / CONFIRMED | §17 |
| 27 | no `PARTIAL`, `NOT IMPLEMENTED / GAP`, `BLOCKED` or unresolved `DECISION REQUIRED` in Development scope | AS-BUILT / CONFIRMED | §17 |

**27 of 27 Development criteria met.** The arithmetic: 27 rows, 27
`AS-BUILT / CONFIRMED`, 0 anything else.

---

## 17. Development Closure Inventory

| Classification | Count | Items |
|---|---|---|
| `AS-BUILT / CONFIRMED` | **27** | all of §16 |
| `PARTIAL` | **0** | — |
| `NOT IMPLEMENTED / GAP` | **0** | the correlation gap of Report 002 is closed — §3–§9 |
| `DEVIATION` | **0** | — |
| `UNAUTHORIZED DECISION` | **0** | — |
| `DECISION REQUIRED` | **0** | — |
| `BLOCKED` | **0** | — |
| `TECHNICAL DEBT` | **1** | below |

### The one item of technical debt, and why it is debt and not a gap

**`activity_execution` has no `client_action_key`.** `activity/start` is not
queueable offline, so there is no offline activity evidence to correlate. The
approved product behaviour is fully satisfied — §16 of the instruction is the
test, and it is: nothing in O1–O10 or AC-1..27 concerns activity offline
correlation, because the precondition does not exist.

It is recorded as debt rather than hidden because the day `activity/start`
becomes queueable, this column is what that work needs, and whoever does it
should find the note rather than rediscover the design.

**Nothing else is deferred.** No functional gap is filed under
`TECHNICAL DEBT`.

### RTE07 confirmation

No RTE07+ scope. No page, route, menu entry or `ComponentRoot` key added. The
preserved behaviour list of §11 is untouched: official mileage definition,
segmented calculation, same-Trip Change Plan semantics, `Not Calculable` on a
missing waypoint, Haversine and breadcrumbs never official, odometer
independent, terminal states, bounded retry and sweeper, historical
immutability, purge-safe provenance, OSRM primary, Valhalla fallback, routing
provenance, snap-radius protection, strict Missing fact, separated notification
state, tenant isolation, no new capability, OCR outside RTE06.

**The event-based best-effort privacy model is unchanged.** No continuous or
background tracking was introduced.

---

## 18. CER Field Validation Items Remaining

These are **CER validation responsibilities**, not Development implementation
gaps, and they are not converted to PASS.

| Item | Classification | What it needs |
|---|---|---|
| Physical iPhone / Safari | `PENDING CER FIELD VALIDATION` | a physical device |
| Physical Android / Chrome | `PENDING CER FIELD VALIDATION` | a physical device |
| Field accuracy sampling | `PENDING CER FIELD VALIDATION` | a run through CER's operating area |
| Evidence-level distribution | `PENDING CER FIELD VALIDATION` | a pilot sample |
| Final threshold calibration | `PENDING CER FIELD VALIDATION` | depends on the sampling above |

### The protocol artifact, delivered

`_cer_delivery/CER_ROUTE_RTE06_FIELD_VALIDATION_PROTOCOLS.md` ships with this
report. It covers everything §10 of the instruction lists: both platforms,
permission grant and deny, background and foreground transitions, screen-lock
behaviour as observable, permission revocation, recovery, the field accuracy
sample with its minimum size and the reason for it, the evidence-level
distribution with its query, the threshold review, a recording template, and the
extraction steps.

Including the rule §10 requires in writing: **background geolocation capability
must not be falsely claimed.** Neither Safari nor Chrome grants geolocation to a
backgrounded tab or a locked screen, and the protocol records what actually
happens rather than what would be convenient.

One addition since Report 002: `snap_radius_m` is now listed as a fifth
threshold to review, because it was introduced by measuring a real engine and
its default is defensible rather than measured.

---

## 19. Proposed Status

**`IMPLEMENTATION COMPLETE / READY FOR CER FIELD VALIDATION`.**

Development scope: **27 of 27 criteria `AS-BUILT / CONFIRMED`**, no `PARTIAL`,
no `GAP`, no `BLOCKED`, no open decision. One item of declared technical debt
that does not affect approved behaviour.

**This is not `COMPLETED` and not `CERTIFIED`**, and it will not be claimed as
either while CER's field validation is open. That gate is CER's to execute, and
the protocol to execute it is in this package.

### Operational action required elsewhere

| Action | Why |
|---|---|
| **Run migrations 0011, 0012 and 0013** | notification separation, the zero-length assignment fix, and the correlation column. **If 0011 aborts, that environment has historical notes** — §12 says exactly what to do, and nothing will have been applied |
| Provision OSRM and Valhalla | proven locally; without them mileage stays pending and terminalises by bounded retry |
| **Execute the field validation gate** | §18 |

No capability, no seed, no bootstrap.

### Next step

CER's review of this Development closure, then the field-validation gate, then
explicit RTE06 certification. **RTE07 has not begun and will not begin before
that certification.**

# STOP
