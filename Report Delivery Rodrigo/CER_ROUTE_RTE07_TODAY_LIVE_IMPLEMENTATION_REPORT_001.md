# CER Route — RTE07 Today / Live

**Report 001** · branch `feature/rte07-today-live` · 2026-10-05

Scope per `CER_ROUTE_RTE07_TODAY_LIVE_INSTRUCTIONS_001.md`. Nothing in §5 or §21's
exclusion list was touched: Work Session, Trip, Activity, mileage rules, location
collection, odometer/OCR, tenant model, RBAC architecture and hierarchy are
unchanged. RTE10-A01 stayed paused.

---

## 1. Executive Result

Today / Live is implemented against the approved V0.7 baseline on desktop and
mobile, backed by the existing domain with **no new persistence**, authorized
server-side by a capability that this checkpoint declares because this is the
checkpoint that creates its protected surface.

One visible element of the baseline cannot be backed truthfully and is reported
as a deviation rather than invented: **estimated fuel**. Everything else maps to
an authoritative fact.

```text
RTE07 IMPLEMENTATION COMPLETE / READY FOR CER VALIDATION
```

---

## 2. V0.7 Baseline Located

`_cer_delivery/CER_ROUTE_RTE01_PACKAGE_V1_0/04_Mockup_Reference_V0_7/standalone.html`

The Today / Live experience lives in `adminToday()`, which branches on device and
composes `supervisorListRows()`, `supervisorDetail()`, `mobileTodayList()` and
`mobileSupervisorSummary()`. The visible states come from `statusMeta()`.

---

## 3. V0.7 → Implementation Mapping

### Visible states

`statusMeta()` defines four, and the API returns the code so the label stays in
the presentation layer:

| V0.7 | Approved label | Derived from |
| --- | --- | --- |
| `route` | **On Route** | Trip `IN_TRANSIT` |
| `activity` | **In Activity** | Activity `IN_PROGRESS` |
| `ended` | **Work Ended** | Work Session `ENDED` |
| *fallback* | **Working** | open session, no trip in transit, no activity |
| — | **Not started** | no Work Session for the business day |

`not_started` is **not a new workflow state**. V0.7 draws every authorized
supervisor, and FR-09 says explicitly not to hide one for having no session. A
supervisor who has not started cannot disappear from the list and cannot be shown
as "Working", so the server distinguishes the case and the screen gives it the
neutral label.

**The order of the branches is the rule**, and it is not arbitrary: an activity
happens *inside* a trip that already arrived. Asking about the trip first would
show "On Route" for someone working at the destination — and whoever reads the
panel would decide who to call on false information. A test fixes it.

### Fields

| V0.7 | Source | State |
| --- | --- | --- |
| name, initials | `user` | mapped |
| vehicle `"2024 Toyota Hilux · V-025"` | vehicle of the **session snapshot** | mapped |
| miles today | `TripMileage.total_meters`, `CALCULATED` only, per `session_date` | mapped |
| status | Work Session + Trip + Activity | mapped |
| current activity + reference | Trip `current_purpose` / `current_context_reference` | mapped |
| since | timestamp of the state in force | mapped |
| activities today | count of `ActivityExecution` | mapped |
| 4 summary cards | aggregates of the same read | mapped |
| **estimated fuel** | `miles / mpg × price` | **deviation — see §14** |

---

## 4. As-Built Data Contract

`GET /api/live/today` → `LiveToday`, one aggregate read for the whole page.

```text
session_date, generated_at
summary { supervisors_working, supervisors_total, total_miles, on_route, in_activity }
supervisors [ { supervisor_profile_id, user_id, name, initials,
                status, since, vehicle_label,
                activity_label, activity_reference,
                official_miles, mileage_pending,
                activities_today, operational_mpg, fuel_grade } ]
```

One call rather than several, deliberately: the page refreshes itself every
thirty seconds, and rebuilding it from five endpoints would multiply that traffic
and force the browser to reconstruct rules that belong to the domain — what "On
Route" means, which miles count, what day it is.

**No raw coordinates.** V0.7 does not require them and §10 forbids them.

### Business day

`session_date`, not UTC. The day is derived by applying the **device-reported UTC
offset** — the most recent one the company reported — to the current instant,
which is the same evidence the domain already trusts when it computes
`session_date` on `Start Work`.

Resolving it with `CURRENT_DATE` would move the day boundary four or five hours
early for an American fleet: at eight in the evening in Georgia it is already
tomorrow in UTC, and the page would empty itself every afternoon. FR-01 forbids
exactly that.

### No N+1

Six queries for the whole list — supervisors, current trip, current activity,
activity counts and mileage — none of them dependent on the number of rows.
Measured in the pilot harness at `query_count=5` for the endpoint.

It matters because the page polls: a per-supervisor pattern would not be a
start-up cost, it would be permanent load that grows with the payroll.

---

## 5. Today / Live Functional Behavior

| Behaviour | Implementation |
| --- | --- |
| Supervisor list is the primary surface | desktop table, mobile cards |
| Selection opens the approved detail | side panel / full-screen push |
| Official Miles only | `CALCULATED` sums; pending is flagged, never silently zero |
| Automatic freshness | 30 s poll, stopped while the tab is hidden |
| Loading | preserves the page structure |
| Empty | truthful message, no fabricated rows |
| Read failure | keeps the last known screen and says it could not refresh |

**A read failure is not a business state.** FR-10's example is worth keeping: an
API error is not "the supervisor is not working". When a refresh fails and there
is already data, the data stays and a quiet line says it could not refresh.
Turning uncertainty into an operational state would assert something nobody knows.

---

## 6. Desktop Fidelity — 1280 × 900

Verified in a real browser: the four cards with their approved labels and hints,
the `Supervisors` table with the five approved columns in order, and the detail
panel with the hero, the current-activity box and the two mini-stats. No
horizontal overflow.

Screenshot: `var/screenshots/rte07/01-desktop-list.png`,
`02-desktop-detail.png`.

---

## 7. Mobile Fidelity — 390 × 844

List-first, verified by measurement rather than by eye: the first supervisor card
is asserted to sit **inside the viewport**, so the summary cannot push the list
below the fold. The summary condenses — the numbers stay, the hints go — and the
detail is a full-screen push with a real back action that restores the list.

**The mobile detail is not the desktop panel squeezed.** The page *chooses*
between the two approved presentations rather than rendering one and letting CSS
compress it, and the test asserts the desktop panel is **absent** on mobile. §2.3
and §14 forbid the alternative.

Screenshot: `03-mobile-list.png`, `04-mobile-detail.png`.

---

## 8. Roles / Authorization / Tenant Isolation

`route.live.read`, declared in this checkpoint. The catalog had reserved it with
a note that says why it could not exist earlier:

> *they enter with the checkpoint that builds their protected surface, because
> `test_permission_catalog.py` rejects — on purpose — a capability no endpoint
> asks for.*

It is granted to the Route administration role, **not** to the supervisor role: a
supervisor runs their own workday, they do not watch everyone else's.

| Control | Evidence |
| --- | --- |
| Capability enforced server-side | supervisor gets `403` on the API |
| Page demands the same capability as its API | supervisor gets `403` on the page |
| Tenant scope from the subdomain | beta never sees alpha's supervisors |
| No client-provided company authority | `get_company_required` |

**No hierarchy was implemented**, as §8 requires. The authorized set is decided by
the read model; when an organizational hierarchy exists it will narrow that `where`
without the UI changing a line. The frontend never filters by role name: it could
not do so with authority, and guessing would be inventing a hierarchy nobody
approved.

---

## 9. Freshness

Polling every 30 s while the tab is visible, stopped when hidden, and an
immediate re-read on returning to the foreground so that looking at the screen
after a while shows something current rather than something stale.

No WebSockets. §5 discourages introducing them for this alone, and a poll that
stops by itself costs one request per half minute per administrator watching.

---

## 10. Official Mileage Semantics

Only `CALCULATED` trip mileage sums, converted from metres to miles, aggregated
for the business day.

**Pending is not zero.** A trip still being calculated contributes nothing to the
total *and* raises `mileage_pending`, which the screen shows as `+ pending`. A
total that presents an uncalculated trip as zero miles looks final and is not.
FR-05 forbids disguising it, and a test fixes it.

Odometer delta and straight-line distance are never used as Official Miles.

---

## 11. Edge Cases

| § | Case | State |
| --- | --- | --- |
| 1 | tenant with no supervisors | **tested** |
| 2 | supervisor has not started today | **tested** |
| 3 | work started, zero trips | **tested** |
| 4 | trip `IN_TRANSIT` | **tested** |
| 5 | trip `ARRIVED` | covered by the "Working" branch |
| 6 | activity `IN_PROGRESS` | **tested** |
| 7 | between trips | covered by the "Working" branch |
| 8 | HOME trip | same mapping; no special case |
| 9 | ended work session | **tested** |
| 10 | Official Mileage = 0 | **tested** |
| 11 | Official Mileage pending | **tested** |
| 12 | data changes with the page open | poll; not separately tested |
| 13 | temporary read failure | implemented; not separately tested |
| 14 | another tenant's supervisor | **tested** |
| 15 | mobile detail → back | **tested** |
| 16 | tab hidden then visible | implemented; not separately tested |
| 17 | several supervisors changing at once | not separately tested |

Cases 12, 13, 16 and 17 are implemented and reviewable but have no automated
evidence of their own. They are listed here rather than counted as green.

---

## 12. Tests / Regression

| Suite | Result |
| --- | --- |
| `tests/integration/test_live_today.py` (new) | **14/14 PASS** |
| `tests/e2e/test_rte07_today_live_browser.py` (new) | **5/5 PASS** |
| `tests/e2e/test_rte07_today_live_screenshots.py` (new) | **1/1 PASS**, 4 images |
| Wiring nets batch (page, navigation, catalog, public surface, frontend) | **64/64 PASS** |
| Domain batch (live, work sessions, trips, activities) | **159/159 PASS** |
| `npm run check` | **0 errors, 0 warnings** |

### Two mistakes of mine, reported because they happened

**A screenshot of the loading state.** The first run of the evidence test waited
for the page heading before capturing — and the heading also renders while
loading, so `01-desktop-list.png` came out showing *"Loading today's operational
state…"*. The test passed. It was caught by **looking at the image**, not by
trusting the green. It now waits for content that only exists once loaded.

**`data-testid` does not survive the production build.** The first version of the
browser tests located everything by test id and failed entirely: the build strips
them from `.tsx` in production (`isTsx && isProd` in `buildBabelLoader`). The rest
of the suite documents this in its own headers — *"Sin `data-testid`"* — and the
tests were rewritten to use roles and visible text, which is also what the user
sees. The attributes were removed from the components so nothing depends on
something the deployed bundle does not contain.

> This also **corrects two diagnoses from RTE10-A01**: a click timeout I
> attributed to a race, and a locator timeout I attributed to a remount, were
> both this. The delivered RTE10 tests pass on text locators and test the right
> things, but those stated causes were wrong.

### A pre-existing harness fragility, not caused by RTE07

Running the new integration file together with a particular mix of root-level and
integration files produces `fixture 'seeded' not found` in
`tests/integration/test_activities.py`.

It is **not** this checkpoint's doing, and that was established rather than
assumed: a throwaway file containing a single trivial test and none of RTE07's
code reproduces the failure identically, and removing RTE07's file from the mix
makes it pass. Some threshold in that particular combination breaks async fixture
resolution.

Reported as an incidental finding. The regression above was therefore run in the
two batches the suite is designed around, and both are green.

---

## 13. Expected → Implemented → Evidence → Gap

| # | Acceptance criterion | State | Evidence |
| --- | --- | --- | --- |
| 1 | V0.7 baseline located and used | VALIDATED | §2, §3 |
| 2 | Desktop structure and hierarchy preserved | VALIDATED | browser test, screenshots |
| 3 | Mobile list-first preserved | VALIDATED | measured card position |
| 4 | Mobile detail full-screen with back | VALIDATED | browser test |
| 5 | Desktop detail follows the panel behaviour | VALIDATED | browser test |
| 6 | Supervisors from server-authorized scope | VALIDATED | read model |
| 7 | Cross-tenant data unreadable | VALIDATED | integration test |
| 8 | State derived from authoritative domain | VALIDATED | 5 state tests |
| 9 | Current activity follows V0.7 semantics | VALIDATED | trip purpose + reference |
| 10 | Official Miles only | VALIDATED | 2 mileage tests |
| 11 | `session_date` semantics | VALIDATED | integration test |
| 12 | No map, no continuous tracking | VALIDATED | none added |
| 13 | No duplicate current-status persistence | VALIDATED | read model only |
| 14 | Automatic refresh within the Live target | IMPLEMENTED | 30 s poll; no automated timing test |
| 15 | Read failure is not a false business state | IMPLEMENTED | last-known screen kept |
| 16 | Empty/no-session/active/ended truthful | VALIDATED | §11 |
| 17 | Desktop validation green | VALIDATED | 5/5 |
| 18 | Mobile validation green | VALIDATED | 5/5 |
| 19 | No overflow, usable layout | VALIDATED | asserted at both sizes |
| 20 | Work Session / Trip / Activity unchanged | VALIDATED | 159/159 |
| 21 | Typecheck / lint / regression green | VALIDATED | §12 |
| 22 | No unauthorized hierarchy/RBAC redesign | VALIDATED | §8 |
| 23 | No PARTIAL / GAP / BLOCKED in scope | see §14 | — |

---

## 14. Deviations

```text
baseline      →  "estimated fuel" mini-stat in the supervisor detail
implemented   →  the slot is kept, showing the neutral "—"
reason        →  the price per gallon does not exist anywhere in the domain.
                 The RBAC catalog reserves `route.fuelreference.manage` as a
                 future capability, so the fact has no source. Inventing a
                 default price is forbidden by §2.4 and §14; removing the
                 mini-stat would alter the approved hierarchy.
CER approval  →  YES
```

The slot is preserved so that the day a fuel reference exists it is filled
without touching the approved layout.

No other visible element of V0.7 deviates.

---

## 15. CER Validation Checklist

**Desktop**, at a normal admin window:

1. The four cards read *Supervisors working*, *Total miles today*, *On route*,
   *In activity*, in that order.
2. The table has *Supervisor*, *Miles today*, *Status*, *Current / last
   activity*, *Since*.
3. Clicking a supervisor fills the right-hand panel.
4. A supervisor who has not started today is **in the list**, not hidden.
5. Leave the page open while a supervisor starts a trip: within about half a
   minute the row changes by itself.

**Mobile**, on a phone:

6. The supervisor list is visible without scrolling past big cards.
7. Tapping a supervisor opens a full screen, not a cramped side panel.
8. The back arrow returns to the list.
9. Nothing scrolls sideways.

**Truthfulness:**

10. A supervisor working at a destination shows **In Activity**, not *On Route*.
11. Miles shown are official road mileage; a trip still calculating shows
    `+ pending` rather than counting as zero.

---

## 16. Proposed Status

```text
RTE07 IMPLEMENTATION COMPLETE / READY FOR CER VALIDATION
```

`RTE07 CLOSED` is not declared: final certification belongs to CER.

**Open for CER:** the `estimated fuel` deviation in §14.

**Next step, not started:** CER validation per §15.
