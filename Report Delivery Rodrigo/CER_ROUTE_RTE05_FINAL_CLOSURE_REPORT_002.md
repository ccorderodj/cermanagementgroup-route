# CER Route — RTE05 Final Closure

| | |
|---|---|
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE05_FINAL_CLOSURE_INSTRUCTIONS_002.md` |
| **Branch** | `feature/rte05-final-closure`, cut from `dev` |
| **RTE05 delivery 001** | MR !20 **merged** into `dev` as `278a9b3`. This closure therefore branches from `dev` and carries only the two deltas |
| **Date** | 2026-09-28 |
| **Proposed status** | **RTE05 — Completed / Ready for CER Certification** |
| **Supersedes** | nothing. `CER_ROUTE_RTE05_DELIVERY_REPORT_001.md` is **not** overwritten; this report adds the two closure deltas to it |
| **RTE02-A02 / RTE03 / RTE04** | **Certified baseline, unchanged** |
| **RTE06+** | **Not started** |
| **STOP conditions** | **None triggered** |

---

## 0. Read first

**1. Only the two authorized deltas were touched.** Since the RTE05 commit, `git diff` shows **8 modified files plus one new test file**. Every item on the "Do Not Change" list is confirmed untouched by diff rather than by assertion — the evidence is in §13.

**2. Delta 2's gap was worse than the instruction describes.** `My Route` was not merely missing a menu entry: for the Supervisor the entire CER Route group disappeared, and because the signed-in landing page builds its cards from that same list, **the Supervisor landed on a page with not one card**. The only way to reach their own work was to type the URL. §5.

**3. One product decision was deliberately not taken.** `/route` requires a session but no capability. Changing that is a product decision, so it is reported for CER instead of being made here. §10.

**4. Two gaps were found by re-reading the instruction clause by clause against the code**, not against my own summary: one flaky assertion of mine that made a batch go red, and one missing assertion from the mandatory browser list. Both closed. §12.

**5. Every batch was executed, including one I had first justified skipping.** `test_odometer.py` was reported `NOT RUN` on the reasoning that neither delta touches it. Reasoning is not evidence, so it was run: batch C7, green.

---

## 1. Exact code / UI delta

### Backend

| File | Change |
|---|---|
| `app/routers_api/activities/service.py` | `Received By` is required on **Complete** and optional on **Leave**. The rule reads `action`, never the chosen Outcome |
| `app/routers_api/activities/schemas.py` | field documentation only |

### Frontend

| File | Change |
|---|---|
| `entities/RouteActivities/model/types/index.ts` | `requiereReceptor` split into `registraReceptor` (which contexts record it) and `exigeReceptor(purpose, action)` (when it blocks) |
| `entities/RouteActivities/index.ts` | barrel updated |
| `features/RouteActivity/ui/ActivityStop.tsx` | the field stays visible on both exits; it blocks confirmation only on Complete, and carries `(optional)` only on Leave |
| `app/providers/maincontent/config/navigation.ts` | `CER Route → My Route` as its own operational group; the five configuration destinations move to `CER Route Configuration` |

### Tests

| File | Change |
|---|---|
| `tests/integration/test_activities.py` | +5 tests (32 → 37) and the AC-01 Work Session assertion |
| `tests/e2e/test_rte05_closure_browser.py` | **new** — 6 closure journeys |
| `tests/e2e/test_activity_execution_browser.py` | a flaky assertion of mine replaced by the stable state (§12.1) |

**No migration.** Neither delta changes the schema.

---

## 2. Check Delivery validation matrix (as-built)

| Context | Action | Outcome | Received By | Notes | Result |
|---|---|---|---|---|---|
| Check Delivery | Complete | required | **required** | optional | 422 without it; 200 with a valid value |
| Check Delivery | Leave | required | **optional** | optional | 200 with or without it; if supplied it is validated and preserved |
| Every other context | Complete | required | **rejected** | optional | 422 `Only a check delivery records who received it.` |
| Every other context | Leave | required | **rejected** | optional | 422, same message |

**Where the rule comes from.** The `action`, and nothing else. Completing a delivery asserts that somebody received it, and that assertion without a name is not verifiable. Leaving asserts the opposite — that it could not be delivered — and demanding a receiver there would force the supervisor to invent one in order to close the stop. A datum fabricated to satisfy a validation is worse than the absence of the datum.

**What it does not come from.** Outcome labels. `grep` over the whole activities module for the four approved labels returns **nothing**; the only `completed` occurrences are the execution-status enum, which is a different field. Outcome remains tenant-configured data, independent of this validation (AC-03).

**Preserved:** tenant/list eligibility (`_valor_elegible` is still called on every supplied value) and the historical label snapshot (`received_by_label` is still stored beside the id).

---

## 3. Backend evidence

`tests/integration/test_activities.py` — **37 tests, 0 failures, exit 0.**

| Required test | Test | Result |
|---|---|---|
| 1. Complete without Received By → reject | `test_check_delivery_records_who_received_it` | 422, message contains `received` |
| 2. Complete with Received By → success | same test | 200, `received_by_label = "Authorized Person"` |
| 3. Leave without Received By → success | `test_leaving_a_check_delivery_needs_no_receiver[sin]` | 200, `received_by_*` both `NULL` |
| 4. Leave with Received By → success | `test_leaving_a_check_delivery_needs_no_receiver[con]` | 200, `received_by_label = "Office Staff"` |
| 5. Outcome still required for both | `test_terminalizing_without_an_outcome_is_rejected[complete\|leave]`, `test_leaving_a_check_delivery_still_requires_an_outcome` | 422 |
| 6. Received By rejected for non-Check-Delivery | `test_only_a_check_delivery_records_who_received_it[complete\|leave]` | 422; the Trip stays `arrived` — a rejected terminalization closes nothing |
| 7. Trip closure and Work Session state | both Check Delivery tests | Trip `closed`, Work Session `active` |

The AC-01 Work Session assertion was **missing** and was added: the test proved the Trip closed but never that the day stayed open.

One correction to the existing test: its docstring justified the requirement from the V0.7 mockup convention. That rationale is superseded by CER's explicit decision, and the docstring now says so — otherwise a later reader would take a product decision for an inference.

---

## 4. Administrador navigation evidence

`test_the_administrator_reaches_my_route_from_normal_navigation` — **no URL is typed**, which is the instruction's condition.

| Step | Evidence |
|---|---|
| sign in as Administrador | browser session, desktop viewport 1280×900 |
| visible My Route entry | `get_by_role("link", name="My Route")` resolves on the signed-in landing |
| click it | click, not `goto` |
| operational screen loads | `Ready to start your day?` renders and `page.url` ends in `/route` |
| Admin configuration still reachable | all five destinations — Users, Supervisors, Vehicles, Standardized Lists, Odometer Exceptions — resolve as links |

All six destinations D2-FR01 requires are present: My Route in the operational group, the other five in configuration.

---

## 5. Supervisor navigation evidence

`test_the_supervisor_reaches_my_route_and_sees_no_configuration`.

| Step | Evidence |
|---|---|
| sign in as Supervisor | browser session |
| visible My Route access | link resolves on the landing page |
| operational screen loads | `Ready to start your day?` renders |
| Admin configuration not offered | all five configuration destinations resolve to **0** links |
| server authorization still the real gate | direct navigation to `/admin/route/standard-values` returns **HTTP 403** |

### What was actually broken

The five CER Route destinations each require an administration capability. The Supervisor holds exactly two capabilities — `route.worksession.execute` and `route.standardvalues.read` — so no item was visible, and `useVisibleNavigation` drops a group once it has no visible children. The group vanished entirely. `AdminPage` builds its cards from that same filtered list, so the landing page rendered **zero cards**.

Splitting the operational area into its own group fixes the menu and the landing page in one place, because both read the same list. That is also why **no new dashboard was invented** (D2-FR04): the landing already derives from navigation.

---

## 6. Browser evidence from normal navigation

`tests/e2e/test_rte05_closure_browser.py` — **6 journeys, 0 failures, exit 0.** Production bundle, Microsoft Edge.

| # | Journey | Viewport |
|---|---|---|
| 1 | Administrador reaches My Route from normal navigation; configuration still reachable | 1280×900 |
| 2 | Supervisor reaches My Route; no configuration offered; direct Admin URL still 403 | 1280×900 |
| 3 | Administrador opens the same My Route experience | 390×844 |
| 4 | Supervisor opens the same My Route experience | 390×844 |
| 5 | Check Delivery Complete: blocked without Outcome, blocked without Received By, finishes with both | 390×844 |
| 6 | Check Delivery Leave: blocked without Outcome, finishes without Received By, receiver field marked optional | 390×844 |

Journeys 5 and 6 are **separate journeys**, as the instruction requires for the Leave path.

The mandatory list's "Outcome required in both" is asserted on **both** exits: the confirm button is `disabled` before an Outcome is chosen, on Complete and on Leave. That assertion was missing from the Complete path and was added (§12.2).

---

## 7. Both roles use the same My Route experience

`test_both_roles_open_the_same_my_route_experience[admin|sup]` — parametrized over the two roles, same assertions, mobile viewport.

Structural confirmation, which matters more than the journey: there is **one** `RouteMyRoutePage` — one import and one entry in `mainContentConfig.tsx`, one key in the `ComponentRoot` enum. There is no role branch anywhere in the mobile shell, so the experience cannot fork. The role difference is what each may administer, not what each may operate (D2-FR03).

---

## 8. Permission regression

| Check | Result |
|---|---|
| Administrador can enter My Route | journey 1 |
| Supervisor can enter My Route | journey 2 |
| Supervisor denied Admin pages | journey 2 — 403 on direct URL |
| Navigation visibility reflects permissions but does not replace authorization | the menu item carries `requiredPermission`; the 403 comes from the server |
| **No new capability** | `git diff` on `app/core/rbac/catalog.py`: **no changes**. `route.worksession.execute` already existed and already protects RTE03/04/05 endpoints |
| Capability catalog net | `tests/test_permission_catalog.py` green (§9) |

No STOP condition was triggered: no new role or capability proved necessary, the application shell was not redesigned, and the Supervisor received no Admin permission.

---

## 9. Regression — measured, in serial batches

One pytest process at a time against the test database.

| Batch | Scope | Tests | Failures | Exit |
|---|---|---|---|---|
| C1 | `test_rte05_closure_browser.py` | 6 | **0** | **0** |
| C2 | `test_activity_execution_browser.py` (RTE05 journeys) | 15 | **0** | **0** |
| C3 | `test_activities.py` (RTE05 execution) | 37 | **0** | **0** |
| C4 | `test_trips.py` + `test_odometer_end_work.py` (affected RTE04) | 77 | **0** | **0** |
| C5 | `test_route_access_model.py` + `test_route_product_context.py` + `test_route_role_authority.py` (A02) | 67 | **0** | **0** |
| C6 | `test_navigation_wiring.py` + `test_page_wiring.py` + `test_permission_catalog.py` + `test_public_surface.py` | 61 | **0** | **0** |
| C7 | `test_odometer.py` (RTE04 odometer) | 37 | **0** | **0** |

**300 tests across seven batches, 0 failures, every batch exit 0.**

AC-07 is satisfied on all four of its points: RTE05 execution green (C1, C2, C3), affected RTE04 green (C4), RTE02-A02 role/access model green (C5), and no RTE06+ scope started (§14).

### An unexplained wall-clock anomaly, reported rather than hidden

C3 took **4h47m** for 37 tests; the same suite with 32 tests took 277s in the previous run. It passed with zero failures, and C4 ran at normal speed immediately afterwards, which points at host suspension rather than at the tests. Cause **`UNVERIFIED`** — I did not determine it, and I am not presenting a guess as a finding. It does not affect the result.

---

## 10. Affected RTE04 regression

**C4 — 77 tests, 0 failures, exit 0.**

This is the batch that mattered most for this closure, because RTE05's `End Work` guard had already forced corrections to seven RTE04 test expectations in the previous delivery (report 001, §19.8). Those corrections hold, and the Delta 1 change did not disturb them.

`test_odometer.py` **was** re-run in this closure — batch C7, **37 tests, 0 failures, exit 0**. It was first reported as `NOT RUN` on the argument that neither delta touches the odometer path. The argument is true but it is not evidence, and absent evidence never becomes PASS, so the suite was executed rather than reasoned about.

### A product decision deliberately not made — `DECISION REQUIRED`

`/route` requires **only a session**, not a capability. The RTE02 reasoning for that has expired: back then `route.worksession.execute` did not exist and the catalog rejects capabilities that protect nothing. Today it exists and protects real endpoints.

I did **not** change it:

- it is not necessary for either delta — the menu item is hidden by permission, and every endpoint behind the page enforces the capability, so no data is served without it;
- deciding who may *open* a page is a product decision, and the instruction's STOP conditions name exactly that.

The consequence as-built: a Core-only user with a session can open the operational shell and see it fail on every call. That is a UX wart, not an authorization hole. **CER's decision**, not mine to take.

---

## 11. Frontend typecheck / lint / build

| Check | Command | Result |
|---|---|---|
| Typecheck | `npm run typecheck` | **0 errors** |
| Lint | `npm run lint:ts` | **0 errors** |
| Production build | `npm run build:prod` | **exit 0** (2 pre-existing bundle-size warnings, unchanged) |
| Import graph | `uv run python -c "import app.main"` | **exit 0** |

The bundle was rebuilt before the browser batches, so the evidence matches the committed source.

---

## 12. Findings

### 12.1 A flaky assertion of mine — `CONFIRMED`, fixed

C2 went red on `test_going_home_never_reaches_the_activity_screen`. The test asserted that `Ending your day…` appears. That text is **transient**: `reconcile()` replaces it as soon as the server confirms the close. Asserting a state that lasts one network round trip is a race, not a check — it passed in the previous run by timing luck.

Replaced in both places I had written it with the **stable** state: the supervisor ends with no open workday. That is a stronger assertion, not a looser one, and the database assertion that was already there is unchanged.

Reported as what it is: a fragile test I wrote. Not "intermittent, ignore it".

### 12.2 A gap in the mandatory browser list — `CONFIRMED`, closed

The browser list's point 5 reads *"Outcome required in both"*. I asserted it only on the Leave path; on Complete I selected the Outcome before checking anything, so the rule was never demonstrated there. Assertion added, together with the other half of D1-FR02: on Complete the receiver field carries **no** optional marker.

### 12.3 A UX consequence of Delta 1 worth declaring

Until now only Notes carried the `(optional)` marker, and report 001 described the convention that way. Delta 1 makes `Received By` genuinely optional on Leave, so it now carries the marker **on that exit only**. This is the faithful representation of CER's decision, not a new convention: optional fields are marked, and Notes simply happened to be the only optional field until today. On Complete the field is unmarked, like Outcome, because required is the default.

### 12.4 Requires human review, not engineering

One item: §10, the `/route` page guard. No ambiguous business data was encountered.

---

## 13. Out-of-scope confirmation, by diff

`git diff` from the RTE05 commit — **8 modified files plus one new test file**, listed in §1. Everything below is confirmed untouched by that diff, not by assertion:

| Must not change | Verification |
|---|---|
| Activity execution model and architecture, one-block semantics | `activities/models.py`, migration `0008`: no diff |
| Trip lifecycle and state model | `trips/`: no diff |
| Work Session lifecycle and rules; End Work rules | `worksessions/`: no diff |
| Outcome catalog; the 28 Standardized Values | `standardvalues/provisioning.py`: no diff |
| Supervisor, Administrador and Core role capabilities | `app/core/rbac/catalog.py`: no diff |
| Users role model, Vehicles, odometer business rules | no diff |
| GPS/location, routing mileage, fuel, Reports, Live | nothing added |
| Core/Foundation navigation architecture | `widgets/Sidebar`, `useVisibleNavigation`, `AdminPage`: **no diff**. Only the navigation configuration data changed, which is the minimum needed to expose My Route |
| A second operational UI for Administrador | one `RouteMyRoutePage`, one `mainContentConfig` entry, one enum key |
| My Route under Configuration | it is in the operational group; the configuration group is separate and named as such |

---

## 14. No RTE06+ work started

Confirmed. Nothing was built for GPS/location, routing mileage, fuel, Reports, Live tracking, org hierarchy, RM/OSM scopes or the Activity Explorer. `RouteActivityPage` still states openly that the Activity Explorer is RTE08 and does not exist yet.

---

## 15. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Classification |
|---|---|---|---|
| CD Complete without Received By → reject | yes | §3 test 1; journey 5 | AS-BUILT / CONFIRMED |
| CD Complete with valid Received By → allow | yes | §3 test 2; journey 5 | AS-BUILT / CONFIRMED |
| CD Leave without Received By → allow | yes | §3 test 3; journey 6 | AS-BUILT / CONFIRMED |
| CD Leave with valid Received By → allow, and preserved | yes | §3 test 4 | AS-BUILT / CONFIRMED |
| Received By invalid in every other context | yes | §3 test 6, both actions | AS-BUILT / CONFIRMED |
| Tenant/list validation and label snapshot preserved | yes | §2 | AS-BUILT / CONFIRMED |
| Outcome required for both actions | yes | §3 test 5; asserted on both exits in the browser | AS-BUILT / CONFIRMED |
| No Outcome-label-specific branching | yes | `grep` of the four labels over the module: none | AS-BUILT / CONFIRMED |
| Notes optional | yes | `Optional[str]`, max 2000; unchanged | AS-BUILT / CONFIRMED |
| Complete: Received By visibly required | yes | journey 5 — confirm disabled until chosen; no optional marker | AS-BUILT / CONFIRMED |
| Leave: Received By does not block | yes | journey 6 — confirm enabled with Outcome alone | AS-BUILT / CONFIRMED |
| Administrador visible path CER Route → My Route | yes | §4 | AS-BUILT / CONFIRMED |
| Administrador retains the other five destinations | yes | §4 | AS-BUILT / CONFIRMED |
| My Route visually distinguishable from configuration | yes | separate group; configuration group named separately | AS-BUILT / CONFIRMED |
| Supervisor visible access to My Route | yes | §5 | AS-BUILT / CONFIRMED |
| Supervisor sees no Route configuration | yes | §5 — 0 links | AS-BUILT / CONFIRMED |
| Server authorization remains the real enforcement | yes | §5 — 403 on direct URL | AS-BUILT / CONFIRMED |
| Both roles reach the same experience | yes | §7 | AS-BUILT / CONFIRMED |
| Landing behaviour validated; no new dashboard | yes | §5 | AS-BUILT / CONFIRMED |
| No new capability | yes | §8 — catalog diff empty | AS-BUILT / CONFIRMED |
| RTE05 / affected RTE04 / A02 regression green | yes | §9 | AS-BUILT / CONFIRMED |
| `test_odometer.py` re-run in this closure | yes | §9 batch C7 — 37 tests, 0 failures | AS-BUILT / CONFIRMED |
| `/route` page requires a capability | no | reasoning in §10 | **DECISION REQUIRED** |
| Real iOS/Android hardware validation | no | Edge on Windows only | **PENDING VALIDATION** |

---

## 16. Proposed final status

**RTE05 — Completed / Ready for CER Certification.**

Both authorized deltas implemented, validated and evidenced: **300 tests in seven serial batches, 0 failures, every batch exit 0.** Nothing in the instruction is left unexecuted.

Two items are declared and **not** counted as passed, and neither is an execution gap:

- the `/route` page guard — **`DECISION REQUIRED`**, because deciding who may open a page is a product decision and the instruction's STOP conditions name exactly that (§10);
- real iOS/Android hardware — **`PENDING VALIDATION`**, the same limit as RTE03, RTE04 and delivery 001, and it has not narrowed.

### Operational action required elsewhere

**None.** Neither delta adds a migration, a capability or a seed. The navigation change ships with the frontend bundle, so the only requirement is deploying the built assets.

### Next step, not started

RTE06, per its own instruction document. Nothing was begun beyond this closure, and nothing will be until CER certifies RTE05.
