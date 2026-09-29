# CER Route — RTE05 Final Certification + UX Realignment

| | |
|---|---|
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE05_FINAL_CERTIFICATION_UX_REALIGNMENT_INSTRUCTIONS_003.md` |
| **Branch** | `feature/rte05-ux-realignment`, cut from `dev` |
| **Date** | 2026-09-29 |
| **Proposed status** | **RTE05 — Ready for CER Certification** |
| **Does not overwrite** | reports 001 and 002 |
| **RTE02-A02 / RTE03 / RTE04** | certified baseline, **business rules unchanged** |
| **RTE06+** | **Not started** |
| **STOP conditions** | **None triggered** |

---

## 0. Read first

**1. No business rule changed.** What changed is how many screens sit between the Supervisor and their work. The whole backend regression is green without a single production-code change to the Work Session, Trip or Activity domains — that is the evidence, not a claim.

**2. The `/route` guard closes the last open decision.** Report 002 left it as `DECISION REQUIRED`; PD-10 decided it, and it is implemented with the capability that already existed. **No new capability.** §12. AC-19 therefore holds.

**3. Two findings you should see, neither of which I could resolve alone:** `owner` and `admin` hold the operational capability by the certified role model, so the guard admits them (§13); and FR-01's "card/grid" wording may expect a presentation different from the one already shipped (§5).

**4. One real product defect was found by walking the UI, not by reading code** — I had reviewed that code and judged it correct. §17.

**5. Four of my own mistakes are reported with their cause.** Three were test expectations and one was a genuine race in the screen. §17.

---

## 1. Current Flow Before

Audited against the authoritative states, not the labels, as the instruction requires.

| Domain state | Screen before |
|---|---|
| no Work Session | `Ready to start your day?` + `Start Work` |
| ACTIVE, no Trip | `Working since` + a **`Where to next?` button**; the seven choices only appeared after pressing it |
| context capture | choices → form → **`Prepare trip`** → **summary screen** → **`Start Trip`** |
| `PLANNING` | its own screen repeating the destination, with `End Work` |
| `IN_TRANSIT` | On Route, with `End Work` |
| `ARRIVED` unresolved | Activity flow, with `End Work` |
| Activity terminal / Trip `CLOSED` | back to the `working` screen — one more press to see the choices |

Divergences from the approved baseline: an extra navigation step after `Start Work` (PD-04), a second confirmation screen before `Start Trip` (PD-05), `End Work` offered inside active travel/work flows (PD-03), and no return to the workbench after terminalization (PD-09).

---

## 2. Target Flow Implemented

```
Start Work
  └─▶ What's next?  ◀────────────────────────┐
        ├─ seven choices                      │
        │    └─▶ context form + Start Trip    │
        │          └─ Back ──────────────────▶│
        │                                     │
        ├─▶ On Route (Arrived · Change Plan)  │
        │      └─▶ Arrived                    │
        │            └─▶ Activity flow        │
        │                  └─ Complete/Leave ─┘
        └─ End Work  (the only exit)
```

---

## 3. Screen / state transition matrix (as-built)

| Domain state | Screen now | Evidence |
|---|---|---|
| no Work Session | `Start Work` | J1 |
| ACTIVE, no Trip | **`What's next?`** with the seven choices | J1, J2 |
| context capture (client-side only) | one form + `Start Trip` + `Back` | J3 |
| `PLANNING` (interrupted start only) | resume: destination + `Start Trip`, odometer capture if blocking | §8 |
| `IN_TRANSIT` | On Route: context, `Arrived`, `Change Plan` | J11, J12 |
| `ARRIVED` unresolved | context-specific Activity screen | J12, RTE05 J10 |
| Activity `IN_PROGRESS` | execution screen with both exits | J12 |
| Activity terminal / Trip `CLOSED` | **`What's next?`** | J4, J5, J12 |
| HOME Trip `CLOSED` | **`What's next?`** | J10 |
| zero-trip ACTIVE session ending | `End Work` from the workbench | J2 |

---

## 4. Screens removed / merged

| Removed or merged | Why |
|---|---|
| the `Working since / Where to next?` intermediate screen | PD-04. A press that revealed options instead of showing them |
| the `Prepare trip` → summary → `Start Trip` sequence | PD-05. Preparing a trip and starting it are one decision |
| `End Work` on the pre-trip screen | FR-11 |
| `End Work` on On Route | PD-03 |
| `End Work` on the unresolved arrival | PD-03, FR-07 |
| the "Change" step inside `Change Plan` | PD-07. It now opens on the choices it must reuse |

Nothing was added: no new dashboard, no second operational UI, no new state.

---

## 5. Workbench behaviour

`What's next?` is the canonical idle state of an ACTIVE session. Reached after `Start Work`, after `Complete`, after `Leave`, and after a HOME arrival — anywhere the session is active with no unresolved Trip or execution (PD-01).

It shows the seven approved choices: Client Visit, Recruiting, Employee Visit, Check Delivery, Office, Other, Return Home. `End Work` is present and visually secondary — a ghost button below the choices, not a peer of each destination (FR-02). The odometer banner still appears here when a reading is pending, and still does not block choosing a destination.

`Working since` is retained as context on the workbench, which PD-04 explicitly permits, and it creates no extra step.

### One presentation, shared — and a question for CER

The seven choices are a single component (`TripContextChoices`) used by the workbench and by `Change Plan`. They cannot diverge into a second taxonomy because there is only one list.

**`PARTIAL` / question:** FR-01 says *"Preserve the approved mobile-first card/grid presentation unless a responsive adjustment is necessary."* The presentation already shipped is **full-width stacked buttons**, and that is what was preserved — the literal reading of "preserve". If the approved mockup shows a card grid, this is a visual adjustment CER should confirm against V0.7; it is not a behavioural gap and no journey depends on it.

---

## 6. Start Work behaviour

`Start Work` → `What's next?`, with no screen in between. J1 asserts both halves: the seven choices are present, and the `Where to next?` button is absent (count 0). `grep` over the frontend confirms the string exists nowhere in the application.

---

## 7. End Work placement

| State | `End Work` | Clause |
|---|---|---|
| workbench (ACTIVE, no Trip) | **offered**, secondary | PD-02, FR-02, FR-10 |
| pre-trip context capture | absent | FR-11 |
| `IN_TRANSIT` | absent | PD-03 |
| `ARRIVED` unresolved | absent | PD-03, FR-07 |
| Activity `IN_PROGRESS` | absent | PD-03, FR-12 |

J12 walks all five states in one journey. There is exactly **one** `End Work` in the interface.

**Zero-trip sessions end normally** (A-1 preserved): J2 ends a workday that created no Trip and asserts **0 Trip rows**. No fake Home Trip is fabricated to close a day.

**No bypass was created.** The server guards are untouched and remain authoritative: D-07 for the in-transit Trip, the RTE05 guard for an unresolved arrival or a running execution, and the odometer rules. Removing the shortcut removes the *offer*, not the control.

### Consequence declared

With `End Work` off the On Route screen, the D-07 review is no longer reachable by pressing a button while driving. It remains reachable through the legitimate paths PD-03 names — a queued action or a second device — and the domain rule itself stays covered by `test_trips.py::test_end_work_anyway_interrupts_without_faking_an_arrival`. A Supervisor who must end a day mid-trip does so through the approved lifecycle: arrive, resolve the stop, end from the workbench. No dead end exists, because both exits of a stop are always present.

---

## 8. Per-context pre-trip behaviour

One screen per context, asking only its approved data, with `Start Trip` as the primary action and `Back` to the workbench.

| Context | Pre-trip fields | Evidence |
|---|---|---|
| Client Visit | Destination (free text) | J3, J4 |
| Recruiting | Area / Location (free text) | J5 |
| Employee Visit | Reference (free text) + Reason (standard value) | J7 |
| Check Delivery | Reference (free text) + Delivery Type (standard value) | J6 |
| Office | Office (free text) + Purpose (standard value) | J8 |
| Other | Area / Location (free text) | J9 |
| Home | certified HOME semantics, unchanged | J10 |

### Cancellation leaves nothing behind

**The Trip is not created until `Start Trip` is pressed.** That is what makes FR-04 trivially true rather than a cleanup problem: `Back` cannot leave a ghost `PLANNING` row because no row exists. J3 asserts **0 Trip rows** after filling a destination and going back.

When the start odometer reading is pending, it is requested **before** anything is created, and once resolved the Trip departs without asking the Supervisor to choose again — the interruption was the system's, not theirs.

The `PLANNING` screen still exists for one case only: a start interrupted by lost connectivity, where the plan reached the queue and the start could not follow. That is resuming an interrupted action, not a confirmation screen.

---

## 9. Change Plan behaviour

`Change Plan` → the same seven choices → the new context's fields → applied to **the same Trip** → back to On Route.

J11 asserts: the seven choices appear, the Trip count does not change, `status` stays `in_transit`, `current_purpose` becomes the new one, `original_purpose` still holds the first, and the screen shows `Originally:`. No replacement Trip, no closure, no post-arrival selectors, no second taxonomy. Append-only history preserved (PD-07, FR-06).

---

## 10. Arrived / Activity behaviour

`Arrived` on a non-HOME Trip enters the post-arrival flow immediately and does **not** return to the workbench while the Trip is unresolved (FR-07). RTE05 J10 asserts the workbench is absent in that state.

Everything PD-08 lists is preserved, and the RTE05 suites prove it unchanged: multi-select 1..N for Client Visit / Recruiting / Other, one execution block per stop, one start, one end, one duration, one Outcome, one optional Notes, `Complete` and `Leave`, the Check Delivery `Received By` rule from closure 002, Employee Visit and Office without a redundant selector, and HOME with no block. `Start Activity` is retained.

---

## 11. Complete / Leave return behaviour

After either terminal action succeeds and the Trip becomes `CLOSED`, the Work Session stays ACTIVE and the client lands on `What's next?` — no intermediate screen, no extra click (PD-09).

Evidence: J4 (Complete), J5 (Leave), J12 (Complete, then `End Work` available again), and every context journey in the RTE05 suite.

---

## 12. `/route` guard

The My Route shell — `/route`, `/route/activity`, `/route/me` — requires **`route.worksession.execute`**, the capability that already protects every operational endpoint. **No capability was added**; `git diff` on `app/core/rbac/catalog.py` is empty.

### Why not the Core page dependency

`require_page_permissions` returns early for a platform superuser. For administration screens that is correct — whoever operates the deployment must be able to diagnose. For the operational shell it is not: FR-13 says *"platform identity alone must not grant operational Route access."*

So the shell uses its own dependency, **stricter than the Core one and without modifying it**: changing `require_page_permissions` would affect every administration page in the product, which is outside this scope. It does not weaken endpoint authorization — it adds a page-level check where there was none.

---

## 13. Role / access evidence

Measured against the certified role model, not assumed:

| Role | Capabilities | `/route` | Correct? |
|---|---:|---|---|
| `supervisor` | 2 | **200** | yes — product role |
| `route_admin` | 12 | **200** | yes — product role |
| `owner` | `*` | **200** | yes — holds execute |
| `admin` | 23 (all but `roles.delete`) | **200** | yes — holds execute |
| `manager` | 6 | **403** | yes |
| `viewer` | 3 | **403** | yes |
| platform superuser (no Route role) | — | **403** | yes — FR-13 |

### Finding for CER — not a gap, and not mine to decide

`owner` holds `ALL_CAPABILITIES` and `admin` holds everything except `roles.delete`, so **both include `route.worksession.execute`**. The guard cannot deny what the role model grants. FR-13 phrases the requirement with exactly that condition — *"Core owner/admin/manager/viewer **without** Route execute: denied"* — so the implementation complies.

If CER intends `owner` and `admin` **not** to enter the operational shell, that is a change to the role model, which this instruction places out of scope ("Do not change: role capabilities; Users role model"). I did not touch it. Classification: **DECISION REQUIRED — outside RTE05 scope**, raised here so it is not discovered later.

Menu visibility reflects permissions and does not replace authorization: the sidebar item carries `requiredPermission`, and the 403 comes from the server.

---

## 14. Browser journey evidence J1–J15

Production bundle, Microsoft Edge, 390×844 (and 1280×900 where the sidebar is the subject).

| # | Journey | Test | Result |
|---|---|---|---|
| J1 | Start Work → workbench, seven choices, End Work secondary | `test_start_work_lands_directly_on_the_workbench` | **PASS** |
| J2 | Zero-trip End Work | `test_a_workday_without_any_trip_ends_from_the_workbench` | **PASS** |
| J3 | Client Visit pre-trip, one screen, Back | `test_the_pre_trip_screen_is_one_screen_and_back_returns_empty_handed` | **PASS** |
| J4 | Client Visit full flow → workbench | `test_client_visit_with_two_activities_completes_and_closes_the_trip` | **PASS** |
| J5 | Leave flow → workbench | `test_recruiting_with_several_activities_leaves_and_closes_the_trip` | **PASS** |
| J6 | Check Delivery pre-trip + Received By rule | closure-002 journeys 5 and 6 | **PASS** |
| J7 | Employee Visit, no duplicate selector | `...do_not_ask_again[employee-visit]` | **PASS** |
| J8 | Office, no duplicate selector | `...do_not_ask_again[office]` | **PASS** |
| J9 | Recruiting / Other multi-select | `..._leaves_and_closes_the_trip`, `test_other_completes_with_several_activities` | **PASS** |
| J10 | HOME | `test_going_home_never_reaches_the_activity_screen` | **PASS** |
| J11 | Change Plan reuses the choices | `test_change_plan_reuses_the_same_seven_choices` | **PASS** |
| J12 | End Work placement, five states | `test_end_work_is_offered_only_from_the_workbench` | **PASS** |
| J13 | Administrador reaches the same workbench | `test_the_administrator_reaches_the_same_workbench` | **PASS** |
| J14 | `/route` guard, 6 roles + platform identity | `test_the_route_shell_requires_the_execute_capability` ×6, `test_platform_identity_alone_does_not_open_the_route_shell` | **PASS** |
| J15 | Reload / reauth / second device | `test_reloading_resumes_the_running_execution`, `test_a_new_session_resolves_the_same_execution` | **PASS** |

J1, J2, J3, J11, J12, J13 and J14 are new (`tests/e2e/test_rte05_workbench_browser.py`, 13 tests). J4–J10 and J15 already existed and now walk the new flow.

---

## 15. Backend regression counts

Serial batches, one pytest process at a time.

| Batch | Scope | Failures | Exit |
|---|---|---|---|
| N1 | `test_rte05_workbench_browser.py` (13) | **0** | **0** |
| N2 | `test_activity_execution_browser.py` (15) | **0** | **0** |
| N3 | `test_rte05_closure_browser.py` (6) | **0** | **0** |
| N4 | `test_trip_and_odometer_browser.py` (6) | **0** | **0** |
| N5 | `test_rte04_closure_browser.py` (5) | **0** | **0** |
| N6 | `test_route_access_browser.py` | **0** | **0** |
| N7 | `test_work_session_offline_browser.py` | **0** | **0** |
| B1 | `test_activities.py` (37) | **0** | **0** |
| B2 | `test_work_sessions.py` (42) | **0** | **0** |
| B3 | `test_trips.py` (66) | **0** | **0** |
| B4 | `test_odometer.py` + `test_odometer_end_work.py` (48) | **0** | **0** |
| B5 | A02 access, product context, role authority (67) | **0** | **0** |
| B6 | tenant isolation + authorization matrix (62) | **0** | **0** |
| B7 | navigation / page wiring / capability catalog / public surface / source completeness (65) | **0** | **0** |

**All fourteen batches green, every one exit 0 — roughly 450 tests across browser and backend.** And the backend is green with **no production change** to the Work Session, Trip or Activity domains. That is the load-bearing evidence for "no business rule changed": the realignment is confined to screen routing and one page guard.

---

## 16. Frontend typecheck / lint / build

| Check | Result |
|---|---|
| `npm run typecheck` | **0 errors** |
| `npm run lint:ts` | **0 errors** |
| `npm run build:prod` | **exit 0** (2 pre-existing size warnings) |
| `uv run python -c "import app.main"` | **exit 0** |
| Migration | **none** — neither delta touches the schema |

The bundle was rebuilt before every browser batch reported here.

---

## 17. Changed tests and justification

No `skip`, no `xfail`, no test deleted. Every change follows `old expectation → approved decision → new expectation`.

| Test | Old expectation | Approved decision | New expectation |
|---|---|---|---|
| `_hasta_la_llegada` (shared helper) | press `Where to next?`, then `Prepare trip`, then `Start Trip` | PD-04, PD-05 | workbench is already there; one `Start Trip` |
| idle-state assertions across 5 files | `Where to next?` button present | PD-01 | `What's next?` is the idle screen |
| `test_start_work_odometer_start_trip_change_plan_and_arrived` | `PLANNING` created first, reading resolved on top of it, then `Start Trip`; `Change` inside Change Plan | PD-05, PD-07 | reading requested before anything is created (0 Trip rows at that point); Change Plan opens on the choices |
| `test_start_exception_blocks_the_trip_until_an_admin_approves_it` | after the approved reading, `Start Trip` on the planning screen | PD-05 | reload returns to the workbench (nothing was created), reading entered from the banner, then one `Start Trip` |
| `test_the_administrator_runs_the_whole_operational_journey` | `Change` step inside Change Plan | PD-07 | choices directly |
| `test_continue_working_leaves_the_trip_exactly_as_it_was` | press `End Work` on On Route, see D-07, choose Continue | PD-03 | `End Work` absent on On Route; the property that mattered — nothing moves — still asserted |
| `test_end_work_asks_for_the_ending_reading_and_resolves_the_distance` | reach the closing reading via D-07 from On Route | PD-03 | reached through the approved lifecycle (HOME closes on arrival → workbench → End Work) |
| `test_a_rejected_end_work_does_not_come_back_from_the_queue` (KD-04) | rejection provoked by End Work while in transit | PD-03 | same definitive rejection provoked from the workbench with the closing reading pending; what the test proves is unchanged |
| `test_end_work_is_blocked_from_an_unresolved_arrival` (RTE05 J10) | press End Work, read the 409 on screen | PD-03, FR-07 | button absent; the server guard stays covered by integration |
| `test_end_work_is_blocked_while_the_execution_runs` (RTE05 J11) | "arrived and not started offers End Work" | PD-03 | absent there too |
| `test_start_work_odometer_start_trip_change_plan_and_arrived` (arrival half) | the screen showed the `RTE05` placeholder saying the next step was not built | RTE05 built it; the placeholder went with it, and FR-07 confirms arrival enters that flow | the stop's own selector is present, the workbench is absent, `End Work` is absent |

### 17.1 My own mistakes, with cause

| # | Mistake | Cause | How it was caught |
|---|---|---|---|
| 1 | `faltaInicio` used before definition | ordering | lint |
| 2 | `queuePlanTrip` only enqueues — I read state before the queue was flushed, so the Trip never started | I assumed enqueue meant send | smoke test, not my reasoning |
| 3 | `Change Plan` seeded with the current purpose, so it skipped the choices PD-07 requires it to reuse | implementation | J11 |
| 4 | J14 asserted `owner` should be denied | false premise about the role model | J14 itself; corrected to the measured truth (§13) |
| 5 | two new components left **unversioned** | forgot to stage | `test_frontend_source_completeness` — the net that exists for exactly this, and it would have shipped a frontend that compiles nowhere else |
| 6 | an assertion still expecting the on-screen text `RTE05` | a stale placeholder assertion that outlived what it described | the final RTE04 browser batch |

### 17.2 A real product defect, found by walking the UI

`CONFIRMED`, fixed. On confirming an odometer reading, the capture screen closed **before** reconciling. The workbench then appeared with stale evidence, and the first press of `Start Trip` bounced the Supervisor back to the reading they had just completed.

This was not test flakiness: anyone pressing within about a second of confirming would have hit it. Fixed by reconciling first and closing the capture afterwards — while the state is being read, the Supervisor keeps seeing the capture, which is the truth.

**I had reviewed that code and judged it correct.** It took a browser journey to disprove me.

---

## 18. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Classification |
|---|---|---|---|
| Start Work lands directly on the workbench | yes | J1 | AS-BUILT / CONFIRMED |
| Workbench is the canonical idle state | yes | J1, J4, J5, J10, J12 | AS-BUILT / CONFIRMED |
| All seven approved choices | yes | J1, J11, J13 | AS-BUILT / CONFIRMED |
| End Work from workbench, incl. zero-trip | yes | J2 — 0 Trip rows | AS-BUILT / CONFIRMED |
| Context capture and Start Trip on one screen | yes | J3 | AS-BUILT / CONFIRMED |
| Back/Cancel before Start Trip | yes | J3 — 0 Trip rows | AS-BUILT / CONFIRMED |
| No redundant Prepare Trip / Start Trip screen | yes | J3 asserts `Prepare trip` count 0; grep finds the string nowhere | AS-BUILT / CONFIRMED |
| On Route intact | yes | J11, J12, §9 | AS-BUILT / CONFIRMED |
| Change Plan reuses the choices and the same Trip | yes | J11 | AS-BUILT / CONFIRMED |
| Arrived enters the post-arrival flow | yes | J12, RTE05 J10 | AS-BUILT / CONFIRMED |
| RTE05 multi-select / one-block intact | yes | B1, N2 | AS-BUILT / CONFIRMED |
| Complete/Leave return to the workbench | yes | J4, J5, J12 | AS-BUILT / CONFIRMED |
| End Work not exposed inappropriately | yes | J12, five states | AS-BUILT / CONFIRMED |
| `/route` requires `route.worksession.execute` | yes | J14, §12 | AS-BUILT / CONFIRMED |
| Admin and Supervisor share My Route | yes | J13, one `mainContentConfig` entry | AS-BUILT / CONFIRMED |
| Core-only users cannot enter `/route` | yes for `manager`/`viewer` and platform identity; `owner`/`admin` hold the capability | J14, §13 | AS-BUILT / CONFIRMED, with §13 raised |
| RTE03 / RTE04 / RTE05 regression green | yes | §15 | AS-BUILT / CONFIRMED |
| No RTE06+ functionality | yes | §20 | AS-BUILT / CONFIRMED |
| No remaining DECISION REQUIRED inside RTE05 scope | yes — the `/route` guard is decided and built | §12 | AS-BUILT / CONFIRMED |
| Approved card/grid presentation | preserved as shipped (stacked buttons), not converted to a grid | §5 | **PARTIAL** — confirm against V0.7 |
| `owner` / `admin` excluded from the operational shell | no — the role model grants them the capability | §13 | **DECISION REQUIRED — outside RTE05 scope** |
| Real iOS/Android hardware | no | §19 | **PENDING VALIDATION** |

---

## 19. Remaining PENDING VALIDATION

**Real iOS/Android hardware: not executed.** All browser evidence is Microsoft Edge on Windows 11 at 390×844, against the production bundle. It covers layout at phone width, touch-target sizing and the IndexedDB queue in a Chromium engine. It does **not** cover iOS Safari specifics, real network transitions, or platform storage eviction. Identical to RTE03, RTE04 and reports 001 and 002; the limit has not narrowed.

---

## 20. No RTE06+ work started

Confirmed. Nothing was built for GPS/location, routing mileage, fuel, Reports, Live tracking, the Activity Explorer, new roles or capabilities, new Standardized Values, new Work Session / Trip / Activity states, a new dashboard, or a duplicated My Route. `RouteActivityPage` still states openly that the Activity Explorer is RTE08 and does not exist yet.

---

## 21. Proposed certification status

**RTE05 — Ready for CER Certification.**

The flow matches the approved workbench model, the business rules are demonstrably untouched, and the last `DECISION REQUIRED` from report 002 is closed.

Three items are declared and **not** counted as passed:

1. **§5 / FR-01 presentation** — `PARTIAL`. The shipped presentation was preserved; if V0.7 shows a card grid, that is a visual adjustment to confirm.
2. **§13 `owner` / `admin`** — `DECISION REQUIRED`, outside RTE05 scope. Excluding them means changing the role model, which needs CER approval.
3. **§19 real-device validation** — `PENDING VALIDATION`.

Per the instruction, RTE05 is **not** called Completed merely because tests pass: items 1 and 2 are CER's calls, not mine.

### Operational action required elsewhere

**None.** No migration, no capability, no seed. Deploying the built assets is the only requirement.

### Next step, not started

RTE06, per its own instruction document. Nothing begins until CER reviews this report and explicitly certifies RTE05.
