# CER Route — RTE04-C1 Progress Report

| | |
|---|---|
| **Checkpoint** | RTE04 — Trip Foundation + Odometer Evidence |
| **Sub-checkpoint** | **C1 — Trip Domain Foundation** |
| **Report** | Progress 001 — **not** the RTE04 completion candidate |
| **Resolves** | `_cer_delivery/CER_ROUTE_RTE04_CER_DECISIONS_AND_CONTINUATION_002.md` §9, C1 |
| **Source branch** | `feature/rte04-c1-trip-foundation` |
| **Base commit** | `3064e09` (tip of `dev`) |
| **Candidate commit** | `613fcb6` |
| **MR** | [merge_requests/11](https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/11) — open, not merged |
| **Date** | 2026-09-24 |
| **Status** | **C1 — Complete and green.** RTE04 overall remains **IN PROGRESS** |

---

## 0. Scope of this report

CER's continuation instruction states: *"C1 must be green before treating the Trip foundation as complete."* This report evidences exactly that, and nothing more.

It is deliberately **not** named `CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`, because CER reserved that number for the evidence-first completion candidate covering C1–C5. C2, C3, C4 and C5 are not started.

---

## 1. CER decisions incorporated

### 1.1 — Standardized Value timing (§2 of the resolution)

Applied to the schema exactly as ruled. Three contexts carry a standardized value **before departure**; the rest describe execution at the stop and belong to RTE05.

| Context | Field | Timing | Implemented in RTE04 |
|---|---|---|---|
| Employee Visit | Employee Visit Reason | Pre-trip | **Yes** |
| Check Delivery | Delivery Type | Pre-trip | **Yes** |
| Office | Office Purpose | Pre-trip | **Yes** |
| Client Visit | Client Visit Activities | Post-arrival | No — RTE05 |
| Recruiting | Recruiting Activities | Post-arrival | No — RTE05 |
| Check Delivery | Received By | Post-arrival | No — RTE05 |
| Other | Other Activities | Post-arrival | No — RTE05 |

The mapping lives in `PRETRIP_STANDARD_LIST` (`app/routers_api/trips/models.py`) and the **server** enforces it:

- a context not in the map rejects any standardized value with **422**;
- a context in the map rejects a value belonging to a different list with **422**, because crossing contexts is what the baseline forbids;
- the value is **optional** where it is allowed — a Supervisor may leave it blank.

Free-text fields remain free text. No catalog was created for any of them.

### 1.2 — END odometer exception, Option B (§1 of the resolution)

Recorded and carried into the design. **Not implemented in C1** — it belongs to C4. No behavior was chosen that would contradict it.

---

## 2. Corrections accepted

CER issued two corrections to the interim report (Delivery 001). Both are accepted and will be reflected in the completion report.

**2.1 — Recruiting timing was already determinable.** Delivery 001 stated only Client Visit Activity had determinable post-arrival timing. That was wrong: the certified A-3 closure states explicitly *"a Recruiting stop offers Recruiting Activities"*. The section had been read; the connection was not made. No new product rule was invented for Recruiting — the baseline already covered it.

**2.2 — An unevidenced claim about fleet composition.** Delivery 001 described digital seven-segment odometers as *"plausibly the majority case in a current fleet"*. No evidence supports that. The claim is withdrawn and will not appear in the completion report. What the measurement does support is narrower and still sufficient: PaddleOCR detected nothing on a seven-segment image, which justifies not making it mandatory.

---

## 3. As-built Trip state model

```
PLANNING ──start──▶ IN_TRANSIT ──arrive──▶ ARRIVED          (operational: RTE05 closes it)
                         │
                         ├──arrive (HOME)──▶ CLOSED
                         └──interrupt──────▶ INTERRUPTED     (explicit End Work Anyway)
```

| Rule | How it is enforced |
|---|---|
| A Trip exists only inside an `ACTIVE` Work Session | Service checks the open session; 409 with an actionable message |
| At most one non-terminal Trip per Work Session | **Partial unique index** `uq_trip_one_non_terminal` on `(company_id, work_session_id) WHERE status NOT IN ('closed','interrupted')` |
| `ARRIVED` is **not** terminal | Deliberately excluded from `TERMINAL_STATUSES`: an operational Trip that arrived is still awaiting RTE05. Treating arrival as completion is what the instruction forbids |
| Operational arrival does not close or create Activity | `arrive()` sets `ARRIVED` and stops; `ended_at` stays `NULL` |
| HOME closes on arrival, Work Session stays `ACTIVE` | Same transition sets `CLOSED` + `ended_at`; the Work Session is never touched |
| Change Plan only while `IN_TRANSIT` | 409 before start and after arrival |
| Original plan immutable | `original_purpose` / `original_context_reference` / `original_standard_value_id` written once; no code path rewrites them |
| Every plan change appended | One `trip_purpose_change` row per change, never an update |
| Server is authoritative | Every rule above lives in the service, not the UI |

### Time semantics

Each transition stores **occurrence** and **receipt** separately, reusing `_resolve_occurrence` from the Work Session rather than reimplementing it — the rule about which time evidence is acceptable is one rule in the product, and having it twice would let the two drift.

---

## 4. Data / schema impact

Migration **`0005_trip_domain`** (revises `0004_admin_lifecycle`). Two new tables, no change to any existing one.

| Guarantee | Mechanism |
|---|---|
| One live Trip per Work Session | `uq_trip_one_non_terminal` — partial unique index |
| A Trip cannot hang off another tenant's session | `fk_trip_work_session_same_company` — **composite** FK `(work_session_id, company_id)` |
| A deleted standardized value cannot destroy the Trip that chose it | `fk_trip_*_standard_value_same_company` with **`RESTRICT`**. RTE02-A01 made those deletions tombstones, so the row survives and history resolves |
| Ordered sequence within the session | `uq_trip_session_sequence` + `CHECK sequence >= 1` |
| No arrival before departure | `CHECK arrived_at IS NULL OR started_at IS NULL OR arrived_at >= started_at` |
| Closed states live in code **and** in the database | `TripStatus` / `TripPurpose` as `BusinessEnum`, each deriving its `CHECK` |

**No data is reinterpreted** — both tables are new and empty.

| Command | Result |
|---|---|
| `alembic upgrade head` | PASS |
| `alembic check` | `No new upgrade operations detected.` |
| `alembic downgrade -1 && upgrade head` | PASS |
| `alembic heads` | `0005_trip_domain` — **1 head** |

---

## 5. API added

All endpoints require **`route.worksession.execute`**. No new capability was created: executing field work is one authorization, and a Trip is part of that work. Inventing `route.trip.*` would grant authority over something already covered.

| Endpoint | Purpose |
|---|---|
| `POST /trips` | Plan a Trip. Returns the **existing** live Trip if one exists, rather than failing — this is what makes it safe against an offline-queue replay and a second device |
| `POST /trips/{id}/start` | `PLANNING → IN_TRANSIT` |
| `POST /trips/{id}/change-plan` | Appends a change; never overwrites |
| `GET /trips/{id}/plan-changes` | The append-only history |
| `POST /trips/{id}/arrive` | `IN_TRANSIT → ARRIVED`, or `→ CLOSED` for HOME |

`Idempotency-Key` reuses `app/core/integration/idempotency.py` — the same mechanism as the Work Session. **No second queue or idempotency framework was created.**

Ownership is resolved through the Work Session, never from a client-supplied identity. A Trip belonging to another Supervisor or another tenant returns **404, not 403**: existence is not confirmed.

**Deliberately absent:** the Start Trip odometer guard. It belongs to C3 and will arrive with the odometer domain and its own tests, rather than leaving half a guard written.

---

## 6. Test evidence — 34 passed

`tests/integration/test_trips.py` — **34 passed in 3:40**, first run, no failures.

| Requirement (CER §9, C1) | Named test |
|---|---|
| Zero-Trip Work Session remains valid | `test_start_work_still_creates_no_trip`, `test_a_zero_trip_work_session_still_ends_normally` |
| Trip requires ACTIVE Work Session | `test_a_trip_requires_an_active_work_session` |
| Service prevents a second non-terminal Trip | `test_planning_twice_returns_the_same_trip` |
| **DB** prevents it, bypassing the service | `test_the_database_rejects_a_second_live_trip_directly` |
| Real concurrency cannot create two | `test_concurrent_planning_creates_only_one_trip` (`asyncio.gather`) |
| `ARRIVED` still blocks a new Trip | `test_an_arrived_operational_trip_still_blocks_a_new_one` |
| Repeated Start changes state once | `test_repeated_start_changes_state_once` |
| Repeated Arrive changes state once | `test_repeated_arrival_changes_state_once` |
| Second device resolves the same Trip | `test_a_second_device_resolves_the_same_trip` |
| Change Plan preserves original + two changes | `test_change_plan_preserves_the_original_across_two_changes` |
| Change Plan before start rejected | `test_change_plan_before_starting_is_rejected` |
| Change Plan after arrival rejected | `test_change_plan_after_arriving_is_rejected` |
| Operational Arrived stays ARRIVED, no Activity | `test_an_operational_arrival_does_not_close_the_trip` |
| HOME Arrived closes the Trip | `test_arriving_home_closes_the_trip` |
| Arrived Home leaves the session ACTIVE | `test_arriving_home_does_not_end_the_work_session` |
| A new Trip can follow a closed HOME Trip | `test_after_arriving_home_a_new_trip_can_start` |
| Pre-trip value accepted in its own context | `test_the_three_pretrip_contexts_accept_their_own_list` (parameterized ×3) |
| Value from another list rejected | `test_a_value_from_another_list_is_rejected` |
| Post-arrival contexts take no pre-trip value | `test_post_arrival_contexts_take_no_pretrip_value` (parameterized ×4) |
| Pre-trip value is optional | `test_the_pretrip_value_is_optional` |
| Another Supervisor's Trip does not leak | `test_a_trip_of_another_supervisor_returns_not_found` |
| Cross-tenant Trip does not leak | `test_a_trip_of_another_tenant_returns_not_found` |
| Capability enforced | `test_planning_a_trip_requires_the_capability` (`route_admin` → 403) |
| Idempotent replay plans one Trip | `test_replaying_the_same_idempotency_key_plans_one_trip` |
| Transitions audited | `test_trip_transitions_are_audited` |
| Invalid transitions rejected | `test_arriving_before_starting_is_rejected`, `test_starting_a_trip_that_never_planned_is_rejected` |

**Environment:** local development and test databases. No shared or production environment was touched.

---

## 7. Expected → Implemented → Evidence → Gap (C1 only)

| Expected (CER §9, C1) | Implemented | Evidence | Gap |
|---|---|---|---|
| Schemas / contracts | `trips/schemas.py` | §5 | — |
| API / router | `trips/router.py` | §5 | — |
| Migration | `0005_trip_domain` | §4 | — |
| Capability enforcement | `route.worksession.execute` on every endpoint | `test_planning_a_trip_requires_the_capability` | — |
| Trip integration tests | 34 passed | §6 | — |
| Tenant isolation | Composite FK + ownership through the session | 2 named tests | — |
| State-machine / invariant tests | Partial index proven at DB level and under real concurrency | 3 named tests | — |
| Change Plan append-only evidence | `trip_purpose_change`, one row per change | `test_change_plan_preserves_the_original_across_two_changes` | — |
| HOME arrival closure behavior | Closes Trip, leaves session ACTIVE | 3 named tests | — |
| **Current-state integration** | — | — | **PENDING — `GET /worksessions/current` not yet extended with the current Trip** |

One gap remains inside C1, stated plainly rather than rounded up.

---

## 8. Status of the rest of RTE04

| Sub-checkpoint | Status |
|---|---|
| **C1** | **Complete and green**, except current-state integration (§7) |
| C2 — Mobile Trip Lifecycle | NOT STARTED |
| C3 — START Odometer Evidence | NOT STARTED |
| C4 — END Odometer (Option B) | NOT STARTED |
| C5 — Validation / Final Delivery | NOT STARTED |

Verification not yet run for this checkpoint as a whole:

| Check | Status |
|---|---|
| Full backend suite | **NOT RUN** since RTE04 began |
| Browser-level validation | **NOT RUN** |
| Frontend typecheck / lint / build | **NOT APPLICABLE** — C1 changes no frontend |

---

## 9. Confirmation — scope not started

No Activity execution, GPS/geolocation, Routing Mileage, Haversine, fuel, Today/Live, Reports, route optimization, client/employee catalogs, mid-session vehicle switching, platform-wide file registry, or any RTE05+ functionality has been started.

**No Routing Mileage value is produced anywhere.** No Activity is fabricated at arrival: the state machine leaves an operational Trip in `ARRIVED`, which is precisely the extension point RTE05 will use.

RTE03 Work Session behavior is unchanged — `Start Work` still creates no Trip, proven by `test_start_work_still_creates_no_trip`.

---

## 10. Next step

Close the remaining C1 gap (`GET /worksessions/current` extended with the current Trip), then proceed to C2 — Mobile Trip Lifecycle.

The completion candidate for CER validation will be `CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`, covering C1–C5 with browser evidence and full regression. RTE05 has not been started.
