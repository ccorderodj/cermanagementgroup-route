# CER Route — RTE05 Activity Execution + Outcome + Trip Closure

| | |
|---|---|
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE05_ACTIVITY_EXECUTION_AND_TRIP_CLOSURE_INSTRUCTIONS_001.md` |
| **Branch** | `feature/rte05-activity-execution` |
| **Date** | 2026-09-28 |
| **Proposed status** | **RTE05 — Completed / Ready for CER Certification** |
| **RTE02-A02** | **Unchanged** |
| **RTE03** | **Unchanged** |
| **RTE04** | **Unchanged before ARRIVED.** RTE05 owns what happens after it |
| **RTE06+** | **Not started** |
| **STOP conditions** | **None triggered** |

---

## 0. Read first

**1. One execution block per stop, not one timer per Activity.** PD-01 is enforced by the schema, not by convention: `uq_activity_execution_trip` makes a second block per trip impossible. Multi-selected Activities are labels of one block — one start, one end, one duration, one Outcome, one Notes.

**2. Nothing closes itself.** A Trip reaches `CLOSED` because somebody completed or left **and said how it went**. `End Work` never closes it, never invents an Outcome, and cannot be forced past an unresolved arrival — `end_anyway` covers the in-transit Trip of D-07 and nothing else.

**3. Every defect of my own is in §19 with its cause classification**, including a frontend module cycle that left a Zod schema half-built at load time, three redundant indexes Alembic autogenerate proposed and I initially accepted, and one **deviation from an explicit clause** — `End Work` left visible while a stop was running, against FR-14.

**4. One coverage gap the instruction asked for was missing from my own test set** and was added before delivery: occurrence time for the queued **terminal** command. Only the start extreme had been covered. §14.

**5. The regression found seven failing RTE04 tests, and they were right to fail.** Two RTE04 test expectations encoded the temporary lifecycle gap that RTE05 exists to close. The guard was not relaxed; the expectations were corrected to the certified behaviour. Full account in §19.8 — including that they failed, which matters as much as that they now pass.

**6. Real iOS/Android hardware remains `PENDING VALIDATION`.** All browser evidence is Microsoft Edge on Windows at a 390×844 mobile viewport, against the production bundle.

---

## 1. Exact scope implemented

| Checkpoint | Scope | Result |
|---|---|---|
| **C1** Activity domain + authoritative state | execution block model/invariants, selected-Activity association, current-state extension, tenant/security boundaries, no duplicate active execution | `AS-BUILT / CONFIRMED` |
| **C2** Context-specific arrival UX | Client Visit / Recruiting / Other multi-select; Employee Visit and Office without a duplicate selector; Check Delivery Received By; HOME bypass | `AS-BUILT / CONFIRMED` |
| **C3** Complete / Leave + Outcome | both require Outcome, both preserve the terminal action, both close the Trip, neither ends the Work Session | `AS-BUILT / CONFIRMED` |
| **C4** Trip closure + End Work integration | ARRIVED → CLOSED atomically with the terminal facts; End Work guard ordering | `AS-BUILT / CONFIRMED` |
| **C5** Offline + final validation | durable-queue reuse, replay, concurrency, browser journeys, regression | `AS-BUILT / CONFIRMED` |

**Not touched, by instruction:** GPS/location, routing mileage, fuel, Reports, Live tracking, org hierarchy, RM/OSM scopes, Activity Explorer (RTE08), the Core role model, the RTE04 pre-trip fields, the 28 approved Standardized Values, and the Change Plan timing rules.

---

## 2. Files, components, APIs and data changed

### New — backend

| File | LoC | Purpose |
|---|---|---|
| `app/routers_api/activities/models.py` | 277 | `ActivityExecution`, `ActivityExecutionActivity`, enums, the context matrix constants |
| `app/routers_api/activities/schemas.py` | 89 | `ActivityStart`, `ActivityTerminalize`, `ActivityExecutionRead`, `SelectedActivityRead` |
| `app/routers_api/activities/service.py` | 438 | the rules: start, terminalize, `has_unresolved_work`, value eligibility |
| `app/routers_api/activities/router.py` | 166 | four command endpoints under `/trips` |
| `app/migrations/versions/0008_activity_execution.py` | 120 | two tables, reviewed by hand |

### New — frontend

| File | LoC | Purpose |
|---|---|---|
| `entities/RouteActivities/model/types/index.ts` | 85 | Zod schemas, context matrix, `requiereActividades` / `requiereReceptor` |
| `entities/RouteActivities/model/services/activitiesService.ts` | 74 | the two commands, through the durable queue |
| `features/RouteActivity/ui/ActivityStop.tsx` | 348 | the arrival screen: selection, running state with elapsed time, both exits |
| `shared/lib/offlineQueue/sync.ts` | 43 | the single queue sender, extracted (see §19.1) |

### Modified

| File | Change |
|---|---|
| `app/routers_api/worksessions/schemas.py` | envelope carries `current_activity` and `post_arrival_pending` |
| `app/routers_api/worksessions/router.py` | builds the block into the envelope |
| `app/routers_api/worksessions/service.py` | End Work guard: in-transit Trip → **unresolved arrival** → odometer |
| `app/routers_api/standardvalues/dao.py` | `find_selectable` now filters `is_active` (see §19.3) |
| `app/routers_api/api.py` | registers the activities router in the CER Route block |
| `entities/RouteWorkSessions/model/types/index.ts` | envelope schema extended |
| `entities/RouteWorkSessions/model/services/workSessionService.ts` | delegates the flush to the shared sender |
| `shared/lib/offlineQueue/index.ts` | exports `flushPendingActions`, `submitAction` |
| `pages/RouteMyRoutePage/ui/RouteMyRoutePage.tsx` | `arrived` phase mounts the stop; 409 on unresolved arrival re-reads state instead of parsing error text |
| `tests/integration/conftest.py` | teardown order for the two new tables |

### APIs

| Method | Path | Capability |
|---|---|---|
| `GET` | `/api/trips/{trip_id}/activity` | `route.worksession.execute` |
| `POST` | `/api/trips/{trip_id}/activity/start` | `route.worksession.execute` |
| `POST` | `/api/trips/{trip_id}/activity/complete` | `route.worksession.execute` |
| `POST` | `/api/trips/{trip_id}/activity/leave` | `route.worksession.execute` |

Command semantics, not CRUD: there is no `PUT` or `PATCH` on the block, so a terminal fact cannot be edited afterwards by an ordinary user. **No new capability was introduced** and **no parallel Standardized Values API** was created — post-arrival lists are read through the existing `route.standardvalues.read` contract.

### Data

Two new tables. **No existing row was read, interpreted or modified.** Pre-RTE05 `ARRIVED` trips stay exactly as they are: fabricating an execution for them would be inventing a fact.

---

## 3. Execution state model as-built

```
        start
  (ARRIVED, non-HOME)
          │
          ▼
    ┌─────────────┐   complete + Outcome    ┌───────────┐
    │ IN_PROGRESS │ ──────────────────────▶ │ COMPLETED │
    └─────────────┘                         └───────────┘
          │            leave + Outcome      ┌───────────┐
          └───────────────────────────────▶ │   LEFT    │
                                            └───────────┘
```

Both terminal states close the Trip in the same transaction. There is no third exit and no path out of a terminal state.

| Invariant | Enforced by |
|---|---|
| one block per Trip | `uq_activity_execution_trip` |
| terminal requires end time **and** terminal action **and** Outcome | `ck_activity_execution_terminal_facts` |
| cannot end before it started | `ck_activity_execution_ends_after_start` |
| the same Activity is not selected twice | `uq_activity_execution_value` |
| Trip, Work Session and every value belong to this tenant | composite FKs on `(id, company_id)` |
| a configured value cannot vanish from under history | `RESTRICT` on `standard_value` |

A Python check protects only while nobody forgets to call it; these protect always.

---

## 4. Context matrix as-built

| Trip context | Pre-trip (RTE04, untouched) | RTE05 post-arrival input | Evidence |
|---|---|---|---|
| Client Visit | Destination = free text | **Client Visit Activities**, 1..N | J1, `test_one_activity_completes_the_stop_and_closes_the_trip` |
| Recruiting | Area/Location = free text | **Recruiting Activities**, 1..N | J2 |
| Employee Visit | Reference + Reason (pre-trip) | **none added** | J3, `test_contexts_that_already_asked_do_not_ask_again` |
| Check Delivery | Reference + Delivery Type (pre-trip) | **Received By**, single, mandatory | J4, `test_check_delivery_records_who_received_it` |
| Office | Office + Purpose (pre-trip) | **none added** | J5 |
| Other | Area/Location = free text | **Other Activities**, 1..N | J6, `test_other_context_completes_with_several_activities` |
| Home | RTE04 closes at arrival | **no Activity, no block** | J7, `test_going_home_records_no_activity` |

The matrix lives in one place — `POSTARRIVAL_ACTIVITY_LIST` in the backend model, mirrored by the frontend entity — and the server validates it independently of what the screen shows. A context with a list **rejects an empty selection**; a context without one **rejects any selection**. Both directions are tested.

No pre-trip field was moved to Arrived, and no selector was added to Employee Visit or Office to make every screen look alike.

---

## 5. Multi-select evidence

`test_several_activities_are_one_block_with_one_of_everything` — three Activities selected, then asserted: **1** execution row, **3** association rows, **1** `started_at`, **1** `ended_at`, **1** Outcome, **1** Notes.

Browser J1 selects two and J6 selects three; both assert the association labels in selection order and exactly one block.

---

## 6. One-block semantics evidence

| Claim | Evidence |
|---|---|
| no per-Activity timer exists | `activity_execution_activity` has no time or status column at all — it is `standard_value_id`, `label`, `sort_order` |
| no per-Activity Outcome exists | Outcome is a column of the block |
| retry does not create a second block | `test_repeating_start_produces_one_execution` |
| two devices at once create one | `test_two_devices_starting_at_once_produce_one_execution` — the unique index decides, not a prior read |
| a second start does not silently mutate the selection | `start` returns the existing block unchanged |

---

## 7. Complete evidence

`test_one_activity_completes_the_stop_and_closes_the_trip`, browser J1, J3, J5, J6, J15.

Asserted: `status = completed`, `terminal_action = complete`, `ended_at` present, `outcome_standard_value_id` + `outcome_label` present, Trip `closed`, Work Session still `active`.

---

## 8. Leave evidence

`test_leaving_is_a_controlled_exit_that_also_closes_the_trip`, browser J2, J11.

Asserted: `status = left`, `terminal_action = leave`, Outcome **required exactly as for Complete**, Trip `closed`, Work Session still `active`. Leave is a recorded decision, not an abandonment: there is no exit that skips the Outcome.

---

## 9. Outcome / Notes evidence

| Rule | Evidence |
|---|---|
| Outcome required on both paths | `test_terminalizing_without_an_outcome_is_rejected` (parametrized `complete` / `leave`) → 422 |
| Outcome is tenant-configured data (PD-02) | read from the `outcomes` list through `route.standardvalues.read`; no hardcoded enum anywhere |
| Outcome must belong to the `outcomes` list of **this** tenant and be selectable | `test_an_activity_from_the_wrong_list_is_rejected`, `test_a_value_from_another_tenant_is_rejected`, `test_an_inactive_or_deleted_activity_is_rejected` |
| Notes optional, never auto-filled | `test_notes_are_optional`; browser J2 asserts `notes IS NULL` after a Leave with no note |
| one Notes per block | it is a column of the block |
| Notes labelled `(optional)` in the UI | follows the V0.7 convention certified in RTE04: only Note-type fields carry the marker |

---

## 10. Check Delivery — Received By behaviour

| Rule | Evidence |
|---|---|
| asked **on arrival**, not at planning | it appears only in the completion form; `test_check_delivery_records_who_received_it` and browser J4 |
| mandatory for Check Delivery | omitted → 422 `Record who received the delivery before finishing.`; the browser asserts the confirm button is **disabled** until it is chosen |
| rejected for every other context | 422 `Only a check delivery records who received it.` |
| read from the `received_by` list | same read contract; no parallel API |
| label snapshot stored | `received_by_label` alongside the id |

---

## 11. Trip ARRIVED → CLOSED evidence

The Trip closes inside the **same transaction** as the terminal update:

1. conditional `UPDATE ... WHERE status = 'in_progress'` on the block — `rowcount == 0` means another device got there first, and the existing state is returned;
2. `UPDATE trip SET status = 'closed', ended_at = <occurrence>` in the same transaction.

A terminal block with an open Trip, or a closed Trip without the facts that justify it, cannot exist.

Evidence: `test_complete_and_leave_at_once_leave_one_terminal_result`, `test_after_terminalizing_the_session_stays_active_and_a_new_trip_can_start`, browser J12, J13, J14.

---

## 12. End Work guard evidence

Guard order in `WorkSessionService.end` — in-transit Trip (D-07) → **unresolved arrival (RTE05)** → odometer:

| Situation | Response | Evidence |
|---|---|---|
| operational Trip `ARRIVED`, no block | **409** `Finish the work at your current stop before ending your day.` | `test_end_work_is_blocked_while_the_arrival_is_unresolved`, browser J10 |
| block `IN_PROGRESS` | **409**, same message | `test_end_work_is_blocked_while_the_execution_is_running`, browser J11 |
| `end_anyway = true` with either of the above | **still 409** — the override covers the in-transit Trip only | read from the service; browser J10 asserts no "End Work Anyway" affordance is offered |
| HOME arrival | **not blocked** — its Trip closed at arrival and it executes nothing | `test_going_home_records_no_activity`, browser J7 |
| after the block is terminal | the existing RTE04 rules apply unchanged | browser J11 second half: End Work succeeds right after the Leave |

Why RTE05 goes **before** the odometer: asking for the closing reading and then sending the supervisor back to the stop would be the long way round. What they have to do now is resolve the stop.

No auto-close, no invented Outcome. The screen re-reads authoritative state on a 409 rather than parsing the error text, so improving a message cannot break the flow.

---

## 13. Current-state / resume evidence

`GET /api/worksessions/current` now answers **which screen to return to**:

```
work_session, current_trip, current_activity, post_arrival_pending
```

`post_arrival_pending` is computed on the server because deducing it on the client would mean crossing purpose, Trip status and block status in three places that can drift.

| Case | Evidence |
|---|---|
| reload resumes the same block | browser J8 — the selected Activity is still shown and the start time is **unchanged**, not reset to the reload |
| reauthentication resumes it | browser J9 — cookies cleared, login again, same block id |
| a second device resolves the same block | `test_a_second_device_resolves_the_same_execution`, browser J9 |
| the envelope is authoritative | `test_the_current_state_returns_the_running_execution` |

---

## 14. Offline / replay evidence

The **existing** durable queue (RTE03, IndexedDB) is reused. No second framework was created.

| Required check | Evidence | Result |
|---|---|---|
| queued Start preserves occurrence time | `test_a_queued_command_keeps_the_time_it_was_pressed` | `started_at < started_received_at`, source `device` |
| queued Complete/Leave preserves occurrence time | `test_a_queued_terminal_command_keeps_the_time_it_was_pressed` | `ended_at < ended_received_at`, source `device` — **added during this checkpoint**, see §19.4 |
| command order preserved | the queue stops at the first failure (RTE03 behaviour, unchanged) | `AS-BUILT` |
| replay idempotent | `test_repeating_start_produces_one_execution`, `test_replaying_complete_does_not_corrupt_the_terminal_facts` | `CONFIRMED` |
| permanent 4xx leaves the queue and returns the authoritative error | browser J17 — the rejection is shown on screen and the queue is empty afterwards | `CONFIRMED` |
| network/5xx may retry | browser J18 — the command stays queued, survives a reload, and applies once on reconnect | `CONFIRMED` |
| reauthentication does not discard valid pending commands | RTE03 browser test, unchanged; browser J9 for the execution | `CONFIRMED` |
| a stale queued action cannot close a different/current execution | `test_a_stale_command_cannot_terminalize_a_later_execution` | `CONFIRMED` |

One deliberate difference from RTE03's fire-and-forget: the two Activity commands **flush immediately and surface their own rejection**. Enqueueing silently would let a 422 from the context matrix disappear while the supervisor is looking at the screen. Without coverage there is no rejection to surface and the command simply waits in the queue, which is the reason the queue exists.

---

## 15. Concurrency / idempotency evidence

| Scenario | Mechanism | Evidence |
|---|---|---|
| two `start` at once | unique index; `IntegrityError` caught **outside** the transaction | `test_two_devices_starting_at_once_produce_one_execution` |
| `complete` and `leave` at once | conditional `UPDATE ... WHERE status = 'in_progress'`; `rowcount == 0` → return the existing state | `test_complete_and_leave_at_once_leave_one_terminal_result` |
| replayed `complete` | terminal block returns unchanged; the first result is the one that happened | `test_replaying_complete_does_not_corrupt_the_terminal_facts` |
| `Idempotency-Key` | every queued action carries its own id; the platform mechanism in `app/core/integration/idempotency.py` is reused | `AS-BUILT` |

The `IntegrityError` is caught outside `async with transaction()` on purpose. Catching it inside leaves the session with its transaction already rolled back, and the context manager's `commit()` then raises `PendingRollbackError` — an HTTP 500 in the supervisor's face. That exact misuse has occurred twice in this project; it is not a hypothetical.

---

## 16. Roles / permissions evidence

**No new capability.** RTE05 uses `route.worksession.execute`, the same one that runs the Work Session and the Trip, because this is the user's own operational work and no endpoint ever accepts another person's identity.

| Role | RTE05 | Evidence |
|---|---|---|
| Administrador de CER Route | executes (12 capabilities, unchanged) | browser J15 — full journey, and `activity_execution.user_id` is the Administrador's |
| Supervisor | executes; reads values; **manages nothing** | `test_the_supervisor_executes_but_never_manages` asserts the effective permission set is exactly Read + Execute |
| Supervisor → catalog management | denied | `test_route_access_browser.py::test_the_supervisor_sees_no_route_administration` (already covers `/admin/route/standard-values`; not duplicated here) |
| another Supervisor's execution | **404**, not 403 | `test_another_supervisors_execution_is_not_reachable` |

`tests/test_permission_catalog.py` stays green: nothing was added to the catalog, so nothing can diverge.

---

## 17. Tenant isolation

| Vector | Result | Evidence |
|---|---|---|
| a Trip from another tenant | **404**, existence not confirmed | `test_another_supervisors_execution_is_not_reachable` |
| a standard value from another tenant | **422**, indistinguishable from "does not exist" | `test_a_value_from_another_tenant_is_rejected` |
| referencing another tenant's Trip / Session / value at all | **impossible by construction** — composite FKs on `(id, company_id)` | migration `0008` |
| `company_id` from the request body | **never accepted** — it comes from the subdomain, via `Depends(get_company_required)` | `AS-BUILT` |
| who acts / when | from the authenticated session and the occurrence rules, never from the body | `AS-BUILT` |

---

## 18. Audit evidence

`test_the_lifecycle_is_audited` asserts, against `audit_event`:

- actions present: exactly `{start, complete}` for a completed stop;
- `actor_user_id` is the acting user on every row;
- `occurred_at` is set on every row.

Recorded changes include the Activity labels, the Outcome, Received By, the occurrence times and the `arrived → closed` Trip transition. `audit_event` is append-only and trigger-protected; nothing here edits or deletes a row.

---

## 19. Findings

### 19.1 Frontend module cycle — `CONFIRMED`, fixed

`RouteWorkSessions/types` imports the activities schema for the envelope, and the activities service needed the queue flush that lived inside `RouteWorkSessions`. The resulting barrel cycle left a Zod schema half-constructed at module-evaluation time.

Fixed by extracting the single queue sender to `shared/lib/offlineQueue/sync.ts` (`flushPendingActions`, `submitAction`); `syncPendingWorkSessionActions` now delegates to it. One queue, one sender, no cycle. Side effect, deliberate: Activity commands can now surface their own server rejection (§14).

### 19.2 Three redundant indexes — `CONFIRMED`, fixed

Alembic autogenerate proposed an index on `trip_id` (already indexed by `uq_activity_execution_trip`, which is unique) and **two identical** indexes on `activity_execution_id` (covered by the leading column of `uq_activity_execution_value`). I accepted them in the first pass. Removed from both the models and the migration, with the reason documented in the migration docstring; roundtrip re-verified.

### 19.3 `find_selectable` did not filter `is_active` — `CONFIRMED`, fixed

A deactivated standard value was still selectable, contradicting the RTE02-A01 baseline. Fixed in `app/routers_api/standardvalues/dao.py`. **This also affects the RTE04 pre-trip values**, which used the same helper: it is an incidental finding outside the planned change, reported here rather than buried.

### 19.4 Missing coverage in my own test set — `CONFIRMED`, fixed

The instruction requires occurrence-time validation for the queued **terminal** command. Only the start extreme was covered. `test_a_queued_terminal_command_keeps_the_time_it_was_pressed` was added: without it, a forty-minute stop closed two hours later on reconnect would have measured two hours forty, and duration is an operational figure.

### 19.5 Two test defects of my own — `CONFIRMED`, fixed

- an integration test reused a live Trip (planning twice returns the same one) and asserted device time before arrival, which is impossible evidence;
- a browser test asserted the terminal Work Session status was `completed`; the enum value is `ended`. It failed, was corrected, and the corrected test passes. Reported because it happened, not only because it was fixed.

### 19.6 Correction to an earlier progress note

An earlier progress message reported the activities integration suite as `31/31`. The real count was **30** (28 functions, two parametrized). With the test added in §19.4 it is now **31 collected**. The figures in §20 are the measured ones.

### 19.8 Seven RTE04 tests encoded the gap RTE05 closes — `CONFIRMED`, corrected

The batched regression failed in two batches. Reported here in full because a
green milestone that hides a red batch is half a delivery.

| Batch | Result | Failures |
|---|---|---|
| L4 `test_trips.py` | **exit 1** | 1 |
| L5 `test_odometer.py` + `test_odometer_end_work.py` | **exit 1** | 6 (all in `test_odometer_end_work.py`; `test_odometer.py` never failed) |

**One root cause, confirmed by re-running with the output captured:** every
failure was the RTE05 guard — `Finish the work at your current stop before
ending your day.` — arriving where the test expected either a 200 or the
odometer's own 409. The most telling assertion was
`assert 'odometer' in 'finish the work at your current stop before ending your day.'`:
the test looked for the odometer message and got the stop's, because that guard
now runs first by C4's ordering.

`find_selectable` (§19.3) was **not** implicated. No second cause exists.

**Why the tests were right to fail.**
`test_an_arrived_operational_trip_does_not_block_end_work` asserted that End Work
returns 200 with an operational Trip in `ARRIVED`. Its docstring said that
neither the closure nor the block was defined in the baseline — true when it was
written. PD-04 repeals it in as many words: *"RTE04 accepted ARRIVED Trips
surviving a Work Session only because Activity execution did not yet exist. That
is no longer the target normal behavior once RTE05 is active."*

**Corrections applied.**

| File | Change |
|---|---|
| `tests/integration/test_trips.py` | the test is inverted and renamed `test_an_arrived_operational_trip_blocks_end_work`. Its docstring now records that the expectation changed by **product decision**, so nobody reads it later as a test bent to go green. It keeps the half that did not change — the Trip stays `arrived` — and adds that the Work Session stays `active`: requesting End Work closes nothing behind the user's back |
| `tests/integration/test_odometer_end_work.py` | `_jornada_conduciendo(llegar=True)` now resolves the stop through a new `_resolver_la_parada`, which starts and completes the block. Nine tests share that helper, so the fix is one and not six |

**Coverage gained, not just restored.** Those nine tests now reach End Work from
the state a supervisor actually reaches under RTE05, which makes **FR-15**
evidenced in the integration suite — previously it was covered only by browser
journey 11.

**A dependency checked before touching the helper:** `count_vehicle_trips`
counts Trips by `started_at`, not by status, so closing the Trip does **not**
remove the need for the closing reading. Had it counted live Trips, this fix
would have broken the same tests in a subtler way.

**What was deliberately not done:** the guard was not relaxed, no `end_anyway`
escape was added, nothing was marked `skip` or `xfail`, and no test was deleted.
The guard **is** the C4 requirement.

**Verification after the correction:** `test_trips.py` + `test_odometer.py` +
`test_odometer_end_work.py` + `test_activities.py` re-run together —
**183 tests, 0 failures, exit 0.** `test_activities.py` was included because the
change touches a shared helper, and a fix that broke RTE05 would be worse than
the original failure.

### 19.9 Four clause-level gaps found by a line-by-line re-read — `CONFIRMED`, closed

After the first pass was believed complete, the instruction was re-read clause by
clause against the code rather than against my own summary. It found four gaps my
summary had recorded as covered. Listed because the method is the point: a
summary is a weaker instrument than a search.

| Clause | Gap | Correction |
|---|---|---|
| **FR-14 / PD-03** — *"End Work is unavailable in normal UX"* | `End Work` stayed visible while the block was `IN_PROGRESS`, relying on the server's 409. I had argued that hiding it creates a dead end | The argument was wrong: with the block running there are **two** doors, Complete and Leave, so hiding `End Work` traps nobody. It is no longer rendered while `IN_PROGRESS`. Arrived-but-not-started still offers it, which is what FR-13 asks. The server guard is unchanged — it remains the control. **This was a deviation from an explicit clause, not a coverage oversight** |
| **FR-01** — *"must not be dropped back into a generic 'Where to next?' state while the current Trip remains unresolved"* | The offline reconcile path collapsed to `{ phase: 'working' }`, which offers planning another Trip — one the server would reject, since only one Trip lives per session — and hid the work left at the stop | The last server-confirmed view is now retained. On a full reload the in-memory reference is gone with the page, so it states that the state could not be read; that is true and also does not offer "Where to next?". Both paths are tested separately in journey 19 |
| **Edge case 26** — *renamed / **deactivated** / deleted* | Only rename and tombstone were covered | The test now uses a two-Activity block: one is renamed, the other deactivated, the Outcome tombstoned, plus an assertion that all three rows still exist — the FK is `RESTRICT`, and a genuinely deleted row would leave history without its value |
| **Security/Audit** — *"audit for start, complete **and leave**"* | `leave` was audited but never asserted | The audit test is parametrized over both exits and now also asserts what makes the fact traceable: actor, company, block identity, Trip and timestamp |

A related as-built note worth recording: `delete` on a Standardized Value is a
**tombstone, not a `DELETE`**. Were it a real delete, the `RESTRICT` foreign key
would refuse it and the administrator would receive a 500. Edge case 26 is
therefore satisfiable, and the test asserts it explicitly.

### 19.10 Requires human review, not engineering

None. No ambiguous business data was encountered and nothing was interpreted silently to make a migration finish.

---

## 20. Backend test counts

| Suite | Tests | Result | Exit |
|---|---|---|---|
| `tests/integration/test_activities.py` | 32 | **0 fallos** | **0** |
| `tests/integration/test_route_product_context.py` (A02) | 25 | **0 fallos** | **0** |
| `tests/integration/test_route_access_model.py` + `test_route_role_authority.py` + `test_provisioning_alignment.py` (A02) | 53 | **0 fallos** | **0** |
| `tests/integration/test_work_sessions.py` (RTE03) | 42 | **0 fallos** | **0** |
| `tests/integration/test_trips.py` (RTE04) | 66 | **0 fallos** (tras la corrección de §19.8) | **0** |
| `tests/integration/test_odometer.py` + `test_odometer_end_work.py` (RTE04) | 48 | **0 fallos** (tras la corrección de §19.8) | **0** |
| `tests/integration/test_route_admin_configuration.py` + `test_route_foundation.py` + `tests/test_standard_value_catalog.py` (RTE02) | 94 | **0 fallos** | **0** |
| `tests/integration/test_authorization_matrix.py` + `test_tenant_isolation.py` + `test_db_constraints.py` (Foundation) | 78 | **0 fallos** | **0** |
| Architecture nets: `test_page_wiring` + `test_navigation_wiring` + `test_permission_catalog` + `test_public_surface` | 63 | **0 fallos** | **0** |

All runs serial, one pytest process at a time, against the test database.

---

## 21. Browser test counts

| Suite | Tests | Result | Exit |
|---|---|---|---|
| `tests/e2e/test_activity_execution_browser.py` (RTE05) | 15 | **0 fallos** | **0** |

Production bundle, Microsoft Edge, 390×844. Fifteen tests cover the eighteen
required journeys plus one added by the clause re-read: journeys 12, 13 and 14
are asserted inside 1 and 2 because they are the same walk, journey 16 is covered
by a pre-existing suite and not duplicated, and journey 19 is new (FR-01).

The bundle was rebuilt and the suite re-run from scratch after the last source
change, so the evidence matches the committed code. An earlier pass was stopped
at 11/15 for exactly that reason: evidence against a stale artefact is not
evidence.

### Journey map

| # | Journey | Test |
|---|---|---|
| 1 | Client Visit, two Activities, Complete + Outcome | `test_client_visit_with_two_activities_completes_and_closes_the_trip` |
| 2 | Recruiting, multiple Activities, Leave + Outcome | `test_recruiting_with_several_activities_leaves_and_closes_the_trip` |
| 3 | Employee Visit, no redundant selector, Complete | `test_the_contexts_that_already_asked_do_not_ask_again[employee-visit]` |
| 4 | Check Delivery, post-arrival Received By, Complete | `test_check_delivery_asks_who_received_it_only_on_arrival` |
| 5 | Office, no redundant selector, Complete | `test_the_contexts_that_already_asked_do_not_ask_again[office]` |
| 6 | Other, multiple Activities, Complete | `test_other_completes_with_several_activities` |
| 7 | HOME — no Activity | `test_going_home_never_reaches_the_activity_screen` |
| 8 | Reload active execution and resume | `test_reloading_resumes_the_running_execution` |
| 9 | Reauth / device continuity | `test_a_new_session_resolves_the_same_execution` |
| 10 | End Work blocked from unresolved ARRIVED | `test_end_work_is_blocked_from_an_unresolved_arrival` |
| 11 | End Work unavailable from IN_PROGRESS (FR-14) | `test_end_work_is_blocked_while_the_execution_runs` — asserts the button is **absent** while running, that both exits are present, and that it returns once the stop is resolved |
| 12 | Trip CLOSED after Complete | asserted in journey 1 |
| 13 | Trip CLOSED after Leave | asserted in journey 2 |
| 14 | Session remains ACTIVE after terminal execution | asserted in journeys 1 and 2 |
| 15 | Administrador executes an RTE05 journey | `test_the_administrator_runs_an_rte05_operational_journey` |
| 16 | Supervisor cannot access catalog management | `test_route_access_browser.py::test_the_supervisor_sees_no_route_administration` — **pre-existing, not duplicated** |
| 17 | Wrong/inactive value rejected through the UI path | `test_a_value_retired_mid_flight_is_rejected_on_the_screen` |
| 18 | Offline/reconnect execution command path | `test_an_execution_command_survives_a_disconnection` |
| 19 | **FR-01** — losing the network does not hide an unresolved stop | `test_losing_the_network_does_not_hide_the_unresolved_stop` — added in the clause re-read (§19.9); covers both the in-page reconcile and a full reload |

---

## 22. Typecheck / lint / build / migration

| Check | Command | Result |
|---|---|---|
| Import graph | `uv run python -c "import app.main"` | **exit 0** |
| Typecheck | `npm run typecheck` | **0 errors** |
| Lint | `npm run lint:ts` | **0 errors** |
| Production build | `npm run build:prod` | **exit 0** (2 pre-existing bundle-size warnings, unchanged) |
| Migration up | `alembic upgrade head` | **applied** |
| Migration down | `alembic downgrade -1` | **reversible, verified** |
| Schema drift | `alembic check` | **No new upgrade operations detected** |
| Heads | `alembic heads` | **1** — `0008_activity_execution` |

Records evaluated / modified / skipped / requiring human review: **0 / 0 / 0 / 0.** The migration creates two tables and reads nothing.

---

## 23. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Classification |
|---|---|---|---|
| non-HOME ARRIVED restores the post-arrival flow | yes | envelope + browser J8, J9 | AS-BUILT / CONFIRMED |
| HOME bypasses RTE05 | yes | J7, `test_going_home_records_no_activity` | AS-BUILT / CONFIRMED |
| context inputs match the approved matrix | yes | §4, J1–J7 | AS-BUILT / CONFIRMED |
| multi-select contexts require 1..N | yes | `test_a_multi_select_context_requires_at_least_one_activity` | AS-BUILT / CONFIRMED |
| exactly one execution block | yes | `uq_activity_execution_trip` + §6 | AS-BUILT / CONFIRMED |
| no duplicate from retry/concurrency | yes | §15 | AS-BUILT / CONFIRMED |
| one start / one terminal / one duration / one Outcome / one optional Notes | yes | §5, §6 | AS-BUILT / CONFIRMED |
| multi-selected Activities have no independent timers/outcomes | yes | the association table has no time or status column | AS-BUILT / CONFIRMED |
| Complete and Leave both require Outcome | yes | §9 | AS-BUILT / CONFIRMED |
| both preserve the terminal action | yes | `terminal_action` column, §7, §8 | AS-BUILT / CONFIRMED |
| both close the Trip | yes | §11 | AS-BUILT / CONFIRMED |
| neither ends the Work Session | yes | J1, J2 assert `active` | AS-BUILT / CONFIRMED |
| next-trip flow available after closure | yes | `test_after_terminalizing_...`, J11 | AS-BUILT / CONFIRMED |
| End Work: unresolved ARRIVED blocks | yes | §12 | AS-BUILT / CONFIRMED |
| End Work: IN_PROGRESS blocks | yes | §12 | AS-BUILT / CONFIRMED |
| no auto-close, no invented Outcome | yes | no code path closes a block without an Outcome; the DB check forbids it | AS-BUILT / CONFIRMED |
| after CLOSED, RTE04 End Work rules apply | yes | J11 second half | AS-BUILT / CONFIRMED |
| correct list per context | yes | §4 | AS-BUILT / CONFIRMED |
| active values only for new operation | yes | §19.3 + `test_an_inactive_or_deleted_activity_is_rejected` | AS-BUILT / CONFIRMED |
| wrong-list / cross-tenant / inactive / deleted direct API submissions rejected | yes | §9, §17 | AS-BUILT / CONFIRMED |
| Supervisor reads but does not manage | yes | §16 | AS-BUILT / CONFIRMED |
| historical labels remain readable | yes | `test_history_survives_renaming_and_retiring_the_catalog_value` | AS-BUILT / CONFIRMED |
| reload / reauth / second device resume | yes | §13 | AS-BUILT / CONFIRMED |
| current-state is authoritative | yes | §13 | AS-BUILT / CONFIRMED |
| offline queue/replay creates no duplicate or stale terminal action | yes | §14 | AS-BUILT / CONFIRMED |
| tenant isolation | yes | §17 | AS-BUILT / CONFIRMED |
| authorization server-side | yes | §16 | AS-BUILT / CONFIRMED |
| audit for the lifecycle | yes | §18 | AS-BUILT / CONFIRMED |
| terminal historical facts not ordinary-user editable | yes | no `PUT`/`PATCH` exists; a terminal block returns unchanged on replay | AS-BUILT / CONFIRMED |
| elapsed/duration presentation (FR-07) | yes | `ActivityStop` shows live elapsed plus the start time; J1 asserts it | AS-BUILT / CONFIRMED |
| End Work unavailable in UX while IN_PROGRESS (FR-14 / PD-03) | yes | not rendered while running; J11 asserts absence. Corrected during the clause re-read, §19.9 | AS-BUILT / CONFIRMED |
| no generic "Where to next?" while the Trip is unresolved (FR-01) | yes | J19, both the offline reconcile and the reload path. Corrected during the clause re-read, §19.9 | AS-BUILT / CONFIRMED |
| real iOS/Android device validation | **no** | Edge/Windows at mobile viewport only | **PENDING VALIDATION** |

---

## 24. Pending real-device / mobile validation

`PENDING VALIDATION`, stated plainly: **no test ran on real iOS or Android hardware.** All browser evidence is Microsoft Edge on Windows 11 at a 390×844 viewport, against the production bundle. That covers layout at mobile width, touch-target sizing and the IndexedDB queue in a Chromium engine. It does **not** cover iOS Safari specifics, real network transitions, or platform storage eviction under pressure. This limit is identical to RTE03 and RTE04 and has not narrowed.

---

## 25. RTE02-A02 / RTE03 / RTE04 remain intact

| Area | Statement | Evidence |
|---|---|---|
| RTE02-A02 role model | unchanged — no capability added, removed or reassigned | §16, regression in §20 |
| Product context rule | unchanged | `test_route_product_context.py` in §20 |
| RTE03 Work Session lifecycle | unchanged; `end` gained one guard **before** the odometer and after D-07 | §12, regression in §20 |
| RTE04 Trip lifecycle before ARRIVED | unchanged | regression in §20 |
| HOME direct close | unchanged | J7 |
| Change Plan timing | unchanged | not touched |
| Odometer rules, END Option B | unchanged | regression in §20 |
| The 28 approved Standardized Values | unchanged — none added, renamed or removed | `tests/test_standard_value_catalog.py` |
| Core / Foundation role model | unchanged | not touched |

### Two declarations, stated precisely rather than as "everything stays green"

**1. RTE04's rules are intact; two of its test expectations were not.** The
lifecycle before `ARRIVED`, HOME's direct close, the odometer rules, END Option
B, the Routing Mileage definition and the Change Plan timing are all unchanged
and evidenced by the regression in §20. What did change is that seven RTE04
tests encoded the temporary lifecycle gap PD-04 repeals: an operational Trip in
`ARRIVED` may no longer survive a Work Session. That is **the mandated change of
behaviour, not a regression**, and the corrections are itemised in §19.8. Calling
this "RTE04 unchanged" without the distinction would misinform certification.

**2. `find_selectable` now excludes inactive values** (§19.3). It makes the
system match the certified A01 baseline rather than departing from it, and it
affects the RTE04 pre-trip lists as well as the RTE05 ones. The regression
confirms no test depended on the old behaviour: it was **not** among the seven
failures.

---

## 26. No RTE06+ scope was started

Confirmed. Nothing was built for GPS/location, routing mileage, fuel, Reports, Live tracking, org hierarchy, RM/OSM scopes or the Activity Explorer. `RouteActivityPage` still states honestly that the Activity Explorer is RTE08 and is not built — an empty hierarchy there would have suggested a finished module without data, which is not the same thing as a module that does not exist yet.

---

## 27. Proposed status

**RTE05 — Completed / Ready for CER Certification.**

Implementation complete, validation complete, evidence named alongside every
claim. One item stands as `PENDING VALIDATION` and is not counted as passed:
real iOS/Android hardware (§24).

Reached honestly rather than smoothly, and the route matters for review: the
batched regression went red in two batches (§19.8) and a clause-by-clause
re-read found four gaps a summary had called covered (§19.9). Both are reported
as what happened, not only as what was finally true. Seven RTE04 tests failed
and now pass; four clauses were not met and now are.

### Operational action required elsewhere

| Action | Where | Why |
|---|---|---|
| `alembic upgrade head` | every shared environment | migration `0008_activity_execution` — local application does not migrate anything shared |
| none for capabilities | — | RTE05 adds no capability, so **no bootstrap re-run is needed** |
| verify the `outcomes` and `received_by` lists are provisioned per tenant | shared environments | they are part of the 28 approved values; a tenant without them cannot close a stop |

### Next step, not started

RTE06, per its own instruction document. Nothing was begun beyond this checkpoint.
