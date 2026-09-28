# CER Route — RTE04 Final Closure & Validation

| | |
|---|---|
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE04_FINAL_CLOSURE_AND_VALIDATION_INSTRUCTIONS_004.md` |
| **Branch** | `feature/rte04-final-closure` |
| **Date** | 2026-09-28 |
| **Proposed status** | **RTE04 — Completed / Ready for CER Certification** |
| **Supersedes** | `CER_ROUTE_RTE04_DELIVERY_REPORT_002.md` (not overwritten) |
| **RTE03** | **Unchanged** |
| **RTE05** | **Not started** |
| **STOP conditions** | **None triggered.** DR-01 and DR-02 validated as-built; neither required a behavior change |

---

## 0. Read first

**1. Nothing was rebuilt.** This checkpoint validates the existing RTE04 implementation against the now-certified RTE02-A02 baseline. No RTE04 area was reconstructed, because validation proved no defect in them.

**2. The Administrador's operational journey had never been run.** When RTE04 was first validated, that role could not execute field work — A02 changed it. RV-01 required proving it in a browser rather than inferring it from a capability table, and it passes end to end: Start Work → read values → plan → odometer → Start Trip → Change Plan → Arrive.

**3. DR-01 and DR-02 were measured, not assumed.** Both behave exactly as the previous report described, neither produces an invalid persistent state, and neither needed changing. Exact as-built evidence in §9 and §10.

---

## 1. Scope actually validated

| Checkpoint | Result |
|---|---|
| **FC1** Baseline reconciliation | `AS-BUILT / CONFIRMED` |
| **FC2** Trip Foundation regression | `AS-BUILT / CONFIRMED` |
| **FC3** START odometer regression | `AS-BUILT / CONFIRMED` |
| **FC4** END odometer / End Work regression | `AS-BUILT / CONFIRMED` |
| **FC5** Security, browser & closure evidence | `AS-BUILT / CONFIRMED` |

Out of scope and not touched: RTE05 Activities, post-arrival multi-select, Outcomes, Received By, GPS, routing mileage, fuel, Reports, Live tracking, org hierarchy, RM/OSM scopes, offline binary photo capture, Core role changes, the Core `manager → owner` remediation.

---

## 2. FC1 — RTE02-A02 compatibility

| Check | Result |
|---|---|
| Certified A02 present in the working baseline | **yes** — branch cut from `dev` at `d5703e9`, byte-identical to the certified content |
| Administrador capabilities | **12**, exactly as certified |
| Supervisor capabilities | **2** — `route.worksession.execute` + `route.standardvalues.read` |
| `route.standardvalues.read` exists and is required by the read endpoint | **yes** |
| `route.worksession.execute` as generic catalog-read shortcut | **absent** — grep over the endpoint returns nothing |
| 8 lists / 28 approved values provisioned | **yes** |
| Stale pre-A02 assumptions in RTE04 tests | **none** — searched for `route_admin` paired with denial assertions; zero hits |

The two RTE04 tests that carried pre-A02 assumptions were already corrected during A02 (`test_planning_a_trip_requires_the_capability`, `test_a_supervisor_cannot_administer_standard_values`) and are green here.

---

## 3. RV-01 — Administrador operational execution

Proven **by browser and by API**, as the instruction requires.

| Step | Evidence |
|---|---|
| Enter My Route | page loads, Start Work offered |
| Start Work | session `active` in PostgreSQL, owned by the Administrador |
| Odometer pending affordance shown, not blocking | notice present **and** "Where to next?" enabled |
| Read required Standardized Values | Employee Visit Reason options load and are selectable |
| Plan a Trip | trip in `planning` with the chosen value |
| Resolve START odometer | photo + confirmed reading |
| Start Trip | `in_transit` |
| Change Plan | same trip — count unchanged; "Originally:" shown |
| Arrive | `arrived` |

`tests/e2e/test_rte04_closure_browser.py::test_the_administrator_runs_the_whole_operational_journey` — **PASS**.

---

## 4. RV-02 — Supervisor operational execution, and its limits

Executes the same flow (browser journeys in `test_trip_and_odometer_browser.py`, plus `test_route_access_browser.py`), and is denied everything else:

| Denied | Result |
|---|---|
| Standardized Values management (create, edit, delete, reorder, list groups, see retired) | **403**, all six |
| Vehicles management | **403** |
| Users management, both contracts | **403** |
| Odometer exception approval / rejection | **403** |
| Admin pages (Users, Vehicles, Lists, Odometer Exceptions) | **401/403/404** — server refuses, not just the menu |

Supervisor holds exactly two capabilities; a test asserts set equality, so anything manage-shaped added to that role fails the suite.

---

## 5. RV-03 — Pre-trip Standardized Values

Browser-validated for all three contexts. Employee Visit was already covered; Check Delivery and Office are new here.

| Context | Options load | Selection persists | Start Trip accepts |
|---|---|---|---|
| Employee Visit → Reason | yes | yes | yes |
| **Check Delivery → Delivery Type** | yes | yes | yes |
| **Office → Office Purpose** | yes | yes | yes |

Each asserts the chosen value is stored on the trip (`current_standard_value_id` resolves to the expected label) and that the trip reaches `in_transit`.

**No Route workflow depends on Admin/Manage permissions to read these values.** The Supervisor performs all three journeys holding only Read + Execute.

---

## 6. Trip lifecycle evidence

| Rule | Evidence |
|---|---|
| Trip only inside an ACTIVE Work Session | backend `test_trips.py` |
| Start Work creates no Trip | backend |
| `PLANNING → IN_TRANSIT → ARRIVED` | browser journeys A and Administrador |
| HOME: `PLANNING → IN_TRANSIT → CLOSED`, session stays ACTIVE | browser journey B |
| End Work Anyway: `IN_TRANSIT → INTERRUPTED`, no fake ARRIVED | browser journey D, asserted in PostgreSQL |
| **Continue Working leaves everything untouched** | **new** — trip id, status, version and session status byte-identical before and after; no second trip; nothing left queued |
| Change Plan only while IN_TRANSIT; original preserved; append-only | backend + browser (trip count unchanged, `trip_purpose_change` row added) |
| Authoritative current state returns session + trip | backend + browser reload and second device |
| No duplicate Trip from replay or concurrency | idempotency key test; second-device test counts rows in PostgreSQL |
| Reauthentication resolves the same Trip | backend |
| Tenant isolation, and same-tenant supervisor isolation | backend |

---

## 7. START odometer evidence

| Rule | Evidence |
|---|---|
| Pending after Start Work when a vehicle applies; not forced | notice shown, "Where to next?" enabled |
| Pending state visible and recoverable | banner survives reload |
| Start Trip blocked while unresolved | **409**, server-side |
| Photo + confirmed reading → `PHOTO_CONFIRMED` | browser + backend |
| OCR assistive only; suggestion stored separately from the confirmed value | backend — both columns asserted distinct |
| OCR silence does **not** create an exception | backend — manual typing from a valid photo stays photo-backed |
| No-photo exception: `PENDING → EXCEPTION_REQUESTED → EXCEPTION_APPROVED → MANUAL_EXCEPTION_CONFIRMED` | browser journey C |
| Approval one-time and scoped to session + end | backend — a START approval cannot authorize END; one session's cannot authorize another; consumed cannot be reused |
| Supervisor may continue non-driving work while pending | browser |
| Rejected exception leaves the trip blocked | backend |

---

## 8. END odometer / Option B evidence

| Rule | Evidence |
|---|---|
| Asked at End Work, not at Arrived Home | backend + browser journey B |
| Trip blockers resolved first | backend — trip 409 precedes odometer 409 |
| `END >= START` | **422** on a lower reading; no silent correction |
| Odometer Distance = END − START; `null` while incomplete, never `0` | backend + browser |
| Option B: session may end with the exception still unreviewed | browser journey E |
| `ended_at` immutable across later resolution | read before and after; identical |
| Later resolution does not reopen the session | status still `ended` |
| Later resolution creates no Trip | trip count unchanged |
| No-photo evidence permanently distinguishable | `evidence_method = manual_no_photo` |
| Odometer never writes Routing Mileage | no such field exists in RTE04; asserted absent from the trip contract |

---

## 9. DR-01 — End Work from an operational ARRIVED Trip

**Measured, not assumed.** Exact as-built sequence:

| Moment | Work Session | Trip | current-state |
|---|---|---|---|
| After Arrive | `active` | `arrived` | returns both |
| End Work attempt | — | — | **409**: the END odometer is required first (the session drove) |
| After END odometer + End Work | **`ended`**, `ended_at` set | **stays `arrived`** | `work_session: null`, `current_trip: null` |
| Afterwards | a new Work Session opens normally (**200**) | — | — |

**Classification: `AS-BUILT / CONFIRMED`.**

The operational Trip is **not** closed and **not** fabricated into any other state — it stays `arrived`, exactly as the approved baseline intends, because RTE05 owns Activity execution and operational Trip completion.

Is the persistent state invalid or impossible? **No.**

- The partial unique index `uq_trip_one_non_terminal` is scoped per Work Session, so a non-terminal Trip on an ended session blocks nothing: the next session gets its own Trip.
- The current-state endpoint returns `null` for both, because there is no active session — the Supervisor sees no stale Trip and cannot resume one.
- Historically the row is coherent and readable: it arrived, the day ended, completion awaits RTE05.

**One fact CER should know:** these Trips accumulate as permanently non-terminal until RTE05 gives them a completion path. That is a consequence of the approved design, not a defect, and nothing in RTE04 can close them without fabricating an Activity outcome — which the instruction forbids. We did not change it.

---

## 10. DR-02 — Photo after the session ended under an END exception

**Measured.** Exact as-built:

| Step | Result |
|---|---|
| Request END exception, End Work | **200** — session `ended`, evidence `exception_requested` |
| Upload a new END photo afterwards | **409** — *"Your workday is already closed. The ending reading can only be completed through the approved manual entry."* |
| Admin approves, Supervisor enters the reading | **200** — `manual_exception_confirmed`, `evidence_method = manual_no_photo` |

**Classification: `AS-BUILT / CONFIRMED`.** Behavior validated exactly; not broadened.

### `captured_at` vs `uploaded_at`

The instruction asks us to distinguish them if both exist. **Only `captured_at` exists** on `odometer_evidence` (alongside `confirmed_at`, `created_at`, `updated_at`). It is set from the server clock at upload.

Because offline binary photo capture is not implemented in RTE04, capture and upload are the same instant today, and the distinction has no observable consequence. **If offline photo capture is ever authorized, the two concepts separate and this rule needs revisiting** — a photo genuinely taken before the day ended but uploaded after would currently be refused. We flag it rather than pre-building for it.

---

## 11. Known defects — proven still closed

| | Regression proof |
|---|---|
| **KD-01** Standardized Values 403 | Supervisor reads all three pre-trip lists with Read only; `test_route_foundation.py` asserts read 200 and all six manage operations 403 |
| **KD-02** Concurrent odometer row creation | two concurrent state reads → both 200, exactly one evidence row |
| **KD-03** Concurrent Admin decision | approve + reject in parallel → `[200, 409]`, a single terminal status |
| **KD-04** Permanently rejected queued commands | **new browser test**: a 409'd End Work leaves the queue, survives reload, and the session stays open |
| **KD-05** Occurrence timestamp | a device time 90 minutes old is stored as `started_at`, distinct from `started_received_at`; a future time is not believed |
| **KD-06** Malware scanning | rejected → nothing stored, trip still blocked; unavailable → stored as `unavailable`, never `clean`; not configured → says so |
| **KD-07** Query/connection churn | `session_state` reads each row once; two queries where there were five |

---

## 12. Concurrency, offline queue, scanning, security

**Concurrency / idempotency.** Same idempotency key plans one Trip; concurrent planning creates one Trip; concurrent exception requests open one door; replayed confirmation writes one reading; second device resolves the same Trip without creating another.

**Offline queue.** Queued Trip actions carry device occurrence time. Order preserved; a 4xx leaves the queue and is handed back; network errors and 5xx still wait. Reauthentication does not discard pending actions. **Offline binary photo capture remains `PENDING VALIDATION / MOBILE HARDENING`** — Start Trip cannot bypass unresolved START evidence, no photo is fabricated, and queued non-photo actions stay consistent, so per the instruction it is not a closure blocker.

**Security / audit.** Tenant isolation intact; cross-tenant evidence and photo access return 404 without disclosure; another Supervisor in the same tenant cannot read a photo; photos have no public or permanent URL and every download re-checks ownership; content type resolved from bytes, size capped at 12 MB; the audit trail records exception request, approval and reading confirmation, and never stores photo bytes or the storage key.

---

## 13. Test results

All runs **serial**, against controlled test databases. No discarded or concurrent run is counted.

### Backend, by batch

| Batch | Tests | Exit |
|---|---:|---|
| Unit + architecture nets + catalog | 111 | `0` |
| A02 access model, product context, provisioning | 78 | `0` |
| Auth / CSRF / authorization matrix | 83 | `0` |
| Route configuration + admin lifecycle | 143 | `0` |
| Data: constraints, pagination, tenant isolation | 47 | `0` |
| **Work Sessions + Trips (RTE03 + RTE04)** | **108** | `0` |
| **Odometer (START + END)** | **48** | `0` |
| Platform + integration + maker-checker | 49 | `0` |
| **Total** | **667** | **0 failures** |

### Browser

| Suite | Tests | Exit |
|---|---:|---|
| **RTE04 closure journeys** (Administrador, Check Delivery, Office, Continue Working, rejected queue) | **5** | `0` |
| Trip + odometer (13 RTE04 flows) | 6 | `0` |
| Route access (selector, both roles Mobile, FR-03) | 9 | `0` |
| Admin UX (Vehicles, Lists) | 2 | `0` |
| Standardized Values rendering + isolation | 2 | `0` |
| Admin lifecycle (RTE02-A01) | 6 | `0` |
| Work Session offline queue (RTE03) | 1 | `0` |
| **Total** | **31** | **0 failures** |

### Frontend

`npm run typecheck` **0 errors** · `npm run lint:ts` **0 errors** · `npm run build:prod` **exit 0** (2 pre-existing bundle-size warnings).

### The 15 required browser journeys

| # | Journey | Where |
|---|---|---|
| 1 | Supervisor full RTE04 journey | trip+odometer A |
| 2 | **Administrador full journey** | **closure, new** |
| 3 | Employee Visit pre-trip value | trip+odometer A |
| 4 | **Check Delivery pre-trip value** | **closure, new** |
| 5 | **Office pre-trip value** | **closure, new** |
| 6 | START photo / confirmation | trip+odometer A |
| 7 | START no-photo exception | trip+odometer C |
| 8 | Admin approval path | trip+odometer C |
| 9 | END photo flow | trip+odometer D |
| 10 | END Option B | trip+odometer E |
| 11 | **End Work → Continue Working** | **closure, new** |
| 12 | End Work Anyway → INTERRUPTED | trip+odometer D |
| 13 | State recovery / reopen | trip+odometer B |
| 14 | Offline / reconnect queue | RTE03 offline |
| 15 | **Rejected queued action does not replay** | **closure, new** |

---

## 14. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Classification |
|---|---|---|---|
| Trip only under ACTIVE Work Session | yes | backend | `AS-BUILT / CONFIRMED` |
| No duplicate Trip from replay/concurrency | yes | idempotency + second device | `AS-BUILT / CONFIRMED` |
| PLANNING → IN_TRANSIT → ARRIVED | yes | browser ×2 | `AS-BUILT / CONFIRMED` |
| HOME closes directly, session stays ACTIVE | yes | browser B | `AS-BUILT / CONFIRMED` |
| End Work Anyway → INTERRUPTED, no fake arrival | yes | browser D | `AS-BUILT / CONFIRMED` |
| Continue Working changes nothing | yes | browser, new | `AS-BUILT / CONFIRMED` |
| Change Plan only IN_TRANSIT, append-only | yes | backend + browser | `AS-BUILT / CONFIRMED` |
| Authoritative current state | yes | backend + browser | `AS-BUILT / CONFIRMED` |
| Employee Visit / Check Delivery / Office pre-trip values | yes | browser ×3 | `AS-BUILT / CONFIRMED` |
| Both roles read values; only Administrador manages | yes | backend + browser | `AS-BUILT / CONFIRMED` |
| No execute-as-read shortcut | yes | source-level test | `AS-BUILT / CONFIRMED` |
| START pending, visible, non-blocking | yes | browser ×2 | `AS-BUILT / CONFIRMED` |
| Start Trip blocked while START unresolved | yes | backend 409 | `AS-BUILT / CONFIRMED` |
| Photo path, OCR assistive, manual-from-photo | yes | backend + browser | `AS-BUILT / CONFIRMED` |
| No-photo exception, scoped one-time approval | yes | backend + browser C | `AS-BUILT / CONFIRMED` |
| END photo, END ≥ START, Option B | yes | backend + browser D/E | `AS-BUILT / CONFIRMED` |
| `ended_at` immutable; no reopen; no new Trip | yes | before/after comparison | `AS-BUILT / CONFIRMED` |
| Odometer Distance pending until valid END | yes | `null`, never `0` | `AS-BUILT / CONFIRMED` |
| Administrador executes the operational flow | yes | **browser, RV-01** | `AS-BUILT / CONFIRMED` |
| Supervisor Read + Execute only | yes | backend + browser | `AS-BUILT / CONFIRMED` |
| Tenant isolation, private evidence, audit | yes | backend | `AS-BUILT / CONFIRMED` |
| Malware scan truthful | yes | three verdicts tested | `AS-BUILT / CONFIRMED` |
| Occurrence time preserved | yes | backend | `AS-BUILT / CONFIRMED` |
| Queue rejection / no replay | yes | browser, new | `AS-BUILT / CONFIRMED` |
| **DR-01** End Work from ARRIVED Trip | as previously reported | §9 | `AS-BUILT / CONFIRMED` |
| **DR-02** Post-close END photo | as previously reported | §10 | `AS-BUILT / CONFIRMED` |
| Offline binary photo capture | **not implemented**, by instruction | §12 | `PENDING VALIDATION` |
| Real iOS / Android hardware | **not tested** | §15 | `PENDING VALIDATION` |
| Representative real-fleet OCR quality | **not measured** | §15 | `PENDING VALIDATION` |
| Core `manager → owner` exposure | **not fixed**, out of scope | A02 report §11 | out of scope |

No item is classified `PARTIAL`, `NOT IMPLEMENTED`, `DEVIATION`, `UNAUTHORIZED DECISION`, `TECHNICAL DEBT` or `DECISION REQUIRED`.

---

## 15. Still pending validation

Carried forward explicitly. None authorizes bypassing any odometer integrity rule.

1. **Real iOS / Android hardware.** All browser validation is desktop Edge at a 390×844 viewport. Camera capture, `capture="environment"`, IndexedDB under iOS storage pressure and real network transitions are **not** validated.
2. **Offline binary odometer photo capture.** Not implemented in RTE04, per the instruction's Offline Boundary. The declared limits hold: Start Trip cannot bypass unresolved START evidence, no photo is fabricated, and queued non-photo actions remain consistent and recoverable.
3. **Representative real-fleet OCR quality.** The port is in place with a no-suggestion default. PaddleOCR was measured in isolation: correct on mechanical roller odometers and clean print, **total non-detection on a seven-segment display**. Quality on real fleet photographs remains unmeasured.
4. **`captured_at` vs `uploaded_at`** — currently the same instant. If offline photo capture is authorized, DR-02's rule needs revisiting (§10).

---

## 16. Scope confirmation

RTE03 Work Session lifecycle and time semantics: **unchanged**. D-07 End Work rules: **unchanged**. D-10 occurrence-time semantics: **unchanged**. RTE02-A02 role model: **unchanged and not reopened**. Routing Mileage definition, Trip endpoint-coordinate rules, Outcome model, free-text decisions, the 28 Standardized Values, the Odometer/Routing Mileage separation, END Option B semantics and the Core/Foundation role model: **all unchanged**.

**RTE05 was not started.** No Activity execution, multi-select, timers, Outcome, Notes, GPS, routing provider, fuel calculation, Today/Live or Reports exists in this branch.

---

## 17. Proposed closure status

**RTE04 — Completed / Ready for CER Certification.**

No STOP condition was triggered. DR-01 and DR-02 were validated exactly as-built and neither required a product decision to close. The three `PENDING VALIDATION` items in §15 are carried forward as declared limits, not as gaps.

Development stops here and does not begin RTE05 until CER reviews this report and explicitly certifies RTE04.
