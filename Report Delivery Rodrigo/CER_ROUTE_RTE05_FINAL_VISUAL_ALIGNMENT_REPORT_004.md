# CER Route — RTE05 Final Visual Alignment

| | |
|---|---|
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE05_FINAL_VISUAL_ALIGNMENT_CERTIFICATION_INSTRUCTIONS_004.md` |
| **Branch** | `feature/rte05-visual-alignment`, cut from `dev` |
| **Date** | 2026-09-29 |
| **Proposed status** | **RTE05 — Ready for CER Certification** |
| **Does not overwrite** | reports 001, 002, 003 |
| **RTE02-A02 / RTE03 / RTE04** | certified baseline, untouched |
| **RTE06+** | **Not started** |
| **STOP conditions** | **None triggered** — the V0.7 baseline was located and used |

---

## 0. Read first

**1. The V0.7 baseline exists in this repository and was used literally.** VR-05 is a hard gate — locate it or STOP. It did not have to be triggered: `04_Mockup_Reference_V0_7/standalone.html` contains the workbench as executable HTML/CSS. Nothing was inferred from preference. §1.

**2. Backend untouched.** Four frontend files changed and nothing else. That is the evidence for D-02, not a claim. §4.

**3. The grid is measured, not described.** The browser reports the container's computed `grid-template-columns`; a stacked layout would give one column. §5.

**4. One coverage gap of mine was found by re-reading the instruction** — V3 also requires proving My Route stays visually separate from Configuration, which no journey asserted. Closed. §16.

---

## 1. Visual baseline used

**`_cer_delivery/CER_ROUTE_RTE01_PACKAGE_V1_0/04_Mockup_Reference_V0_7/standalone.html`** — the approved integrated functional mockup V0.7 REFINED, shipped inside the RTE01 package. Its `README.md` names it the approved UX/interaction reference.

The workbench is defined there as executable code, so there was nothing to interpret:

```js
case 'working':
  `<div class="screen">
     <div class="screen-title">What's next?</div>
     <div class="screen-sub">Choose one activity to start a trip.</div>
     ${purposeGrid()}
   </div>`
```

```js
function purposeGrid(){ const a=[
  ['client','Client Visit','Client / site'],
  ['recruiting','Recruiting','Candidate activity'],
  ['employee','Employee Visit','Employee support'],
  ['check','Check Delivery','Delivery'],
  ['office','Office','Office task'],
  ['other','Other','Field task'],
  ['home','Home','End route']];
  return `<div class="purpose-grid">${a.map(x=>
    `<button class="purpose ..."><b>${x[1]}</b><small>${x[2]}</small></button>`)}</div>` }
```

```css
.purpose-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px }
.purpose      { min-height:72px; border:1px solid #e1e6ec; border-radius:14px;
                background:#fff; padding:10px; text-align:left }
.purpose b    { display:block; font-size:13px }
.purpose small{ display:block; font-size:10px; color:var(--muted); margin-top:4px }
.purpose.active { border-color:#1d63d7; background:#eef5ff }
```

The mockup also settles two things that were not mine to decide:

* the heading copy — **"What's next?"** with **"Choose one activity to start a trip."**;
* that `purposeGrid()` also renders the **`Change activity`** screen, which is why a single shared component is the mockup's own design and not an invention of report 003.

### The one adaptation, and why it is mandatory

The mockup expresses colour as fixed hex values. Those are expressed here as design-system tokens (`border-border`, `bg-card`, `text-muted-foreground`, `border-primary`, `bg-accent`). A hand-written `#e1e6ec` does not respond to the tenant's brand — the exact defect already corrected once in the sidebar, and prohibited by the repository's own rules. The **visual concept is unchanged**; only the colour source is.

`Home` keeps the shipped label **"Return Home"**, which VR-01 permits explicitly ("Home / Return Home").

---

## 2. Before vs after

| | Before (stacked) | After (V0.7 card grid) |
|---|---|---|
| Arrangement | one full-width button per row, 7 rows | **2-column grid of cards** (3 at `sm`, 4 at `lg`) |
| Card content | label only | **label + hint**, the mockup's second line |
| Card height | button height | **`min-h-72px`**, the mockup's measure and a comfortable touch target |
| Card shape | button radius | rounded card with border, `text-left` |
| Heading | bare `What's next?` | **title + subtitle**, as the mockup presents it |
| Selected state | none | `border-primary bg-accent`, the mockup's `.purpose.active` |
| `Home` | visually distinct (`secondary`) | **identical to the rest** — in the mockup all seven cards are equal; what differs is what happens on selection, not how it looks |
| `End Work` | ghost button below | unchanged: still below, still secondary |

---

## 3. Frontend files changed

| File | Change |
|---|---|
| `entities/RouteTrips/model/types/index.ts` | `TRIP_CONTEXTS` gains `hint` — the mockup's second line, one per context, in the single place the taxonomy already lives |
| `features/RouteTrip/ui/TripContextChoices.tsx` | rewritten as the card grid; gains an optional `selected` to render the mockup's active state |
| `features/RouteTrip/ui/TripContextPicker.tsx` | Change Plan heading aligned to the mockup (`Change activity` / `Select the new trip purpose.`) and the current purpose marked as selected |
| `pages/RouteMyRoutePage/ui/RouteMyRoutePage.tsx` | workbench heading + subtitle from the mockup |

**Four files. No new component, no second taxonomy, no duplicated list of contexts.** The seven options remain a single source of truth shared by the workbench and Change Plan, exactly as `purposeGrid()` is in the mockup.

---

## 4. No backend domain logic changed

`git diff` for this checkpoint touches **no** backend file: `app/routers_api/**`, `app/routers_pages/**`, `app/core/**` and `app/migrations/**` are all untouched. No migration. No capability. No standardized value.

That is what makes the D-02 claim checkable rather than rhetorical: a visual change that cannot reach the domain cannot regress it, and the full backend regression in §14 confirms it did not.

---

## 5. Mobile workbench evidence (V1)

`test_the_workbench_is_the_approved_card_grid[390x844]`.

| Assertion | How |
|---|---|
| `What's next?` reached directly after `Start Work` | click, no intermediate screen |
| the mockup's subtitle is present | `Choose one activity to start a trip.` |
| **it is a grid, not a stack** | the browser's computed `grid-template-columns` on the card container resolves to **≥ 2 columns**. A stacked layout resolves to 1 |
| all seven cards present, enabled | by role, one per context |
| each card carries its hint | the seven mockup sublabels asserted individually |
| no horizontal overflow | `scrollWidth ≤ clientWidth` |
| `End Work` below the cards | bounding boxes compared: `End Work.y > card.y` |

Measuring the computed style rather than reading the class is the difference between checking and assuming: the class could be right and the layout still collapse.

---

## 6. Desktop / tablet evidence (V3)

`test_the_workbench_is_the_approved_card_grid[1280x900]` runs the **same** assertions at `1280×900`: still a grid, never fewer columns than mobile, no overflow, same hierarchy. The grid expands to 3 and 4 columns responsively and remains recognisably the same workbench.

`test_my_route_stays_visually_separate_from_configuration` covers V3's second half: at desktop the sidebar shows **`CER Route`** and **`CER Route Configuration`** as two distinct groups, and My Route opens the operational shell from the first. Asserted by button role, not loose text — "CER Route" also appears as the application title and as a card description, so a text search returns three different things and none of them is the menu.

---

## 7. Seven-card navigation evidence (V4)

`test_every_card_opens_its_own_context_flow`, **parametrized over all seven** — the instruction says not to revalidate one representative card.

| Card | Opens | Asks for |
|---|---|---|
| Client Visit | pre-trip | `#trip-reference` (free text) |
| Recruiting | pre-trip | `#trip-reference` |
| Employee Visit | pre-trip | `#trip-standard-value` → `Attendance Issue` present |
| Check Delivery | pre-trip | `#trip-standard-value` → `Payroll Check` present |
| Office | pre-trip | `#trip-standard-value` → `Paperwork` present |
| Other | pre-trip | `#trip-reference` |
| Return Home | pre-trip | **neither field** |

Each also asserts `Start Trip` as the primary action, `End Work` absent, and `Back` returning to the workbench. After all seven: **0 Trip rows**. No intermediate confirmation step was introduced, and the fields required later are unchanged (VR-02).

---

## 8. End Work hierarchy evidence (V8, VR-03)

| Claim | Evidence |
|---|---|
| visible on the workbench | V1, J1 |
| visually secondary | V1 — bounding box below the cards; it is a ghost button, not a card |
| **not an eighth card** | the grid renders exactly `TRIP_PURPOSES`, seven entries; `End Work` is outside the grid container |
| not repeated inside each card | a card's only child elements are its label and hint |
| zero-trip session can end | J2 — **0 Trip rows**, session `ended` |
| absent from active flows | J12 walks pre-trip, `IN_TRANSIT`, unresolved `ARRIVED` and `IN_PROGRESS`; count 0 in all four |

---

## 9. Complete / Leave return evidence (V5)

`test_client_visit_with_two_activities_completes_and_closes_the_trip` (Complete) and `test_recruiting_with_several_activities_leaves_and_closes_the_trip` (Leave) both assert the return to `What's next?` — which is now the aligned card grid, since there is only one workbench. J12 adds a third Complete journey ending on the workbench with `End Work` available again.

---

## 10. Back / Cancel evidence (V6)

`test_the_pre_trip_screen_is_one_screen_and_back_returns_empty_handed` and the seven-way V4 journey. Both assert **0 Trip rows** afterwards. This stays trivially true because the Trip is not created until `Start Trip` is pressed — report 003's design, unchanged here.

---

## 11. Change Plan evidence (V7)

`test_change_plan_reuses_the_same_seven_choices`: the seven choices appear, a new context is chosen, the change applies to **the same Trip** — count unchanged, `status` still `in_transit`, `current_purpose` new, `original_purpose` preserved, `Originally:` shown — and the screen returns to On Route.

The visual reuse is appropriate to its context (FR-05): the shared grid is wrapped by the mockup's own Change Plan heading — `Change activity` / `Select the new trip purpose.` — and the current purpose renders in the mockup's active state. **Domain behaviour is untouched.**

---

## 12. `/route` guard regression (V9, FR-07)

Unchanged from report 003 and re-run here. The shell requires `route.worksession.execute` through the Route-local dependency, which is stricter than the Core page guard because a platform superuser must not gain operational access by identity alone.

---

## 13. Role / access regression

| Identity | `/route` | Same as report 003? |
|---|---|---|
| `supervisor` | 200 | yes |
| `route_admin` | 200 | yes |
| `owner` | 200 | yes — holds the capability |
| `admin` | 200 | yes — holds the capability |
| `manager` | 403 | yes |
| `viewer` | 403 | yes |
| platform superuser | 403 | yes |

**D-03 is satisfied without any change:** `owner` and `admin` hold `route.worksession.execute` under the certified role model, so their access remains valid. RTE02-A02 and the Core role capabilities were not modified. The item report 003 raised is **closed by CER decision**, not by code.

---

## 14. Regression results

Serial batches, one pytest process at a time.

| Batch | Scope | Failures | Exit |
|---|---|---|---|
| V1 | `test_rte05_workbench_browser.py` (23) | **0** | **0** |
| V2 | `test_activity_execution_browser.py` (15) | **0** | **0** |
| V3 | `test_rte05_closure_browser.py` (6) | **0** | **0** |
| V4 | `test_trip_and_odometer_browser.py` (6) | **0** | **0** |
| V5 | `test_rte04_closure_browser.py` (5) | **0** | **0** |
| V6 | `test_route_access_browser.py` | **0** | **0** |
| V7 | `test_work_session_offline_browser.py` | **0** | **0** |
| B1 | RTE05 Activity execution (37) | **0** | **0** |
| B2 | RTE03 Work Session (42) | **0** | **0** |
| B3 | RTE04 Trips + Change Plan (66) | **0** | **0** |
| B4 | RTE04 odometer + End Work (48) | **0** | **0** |
| B5 | RTE02-A02 access model (67) | **0** | **0** |
| B6 | tenant isolation + authorization (62) | **0** | **0** |
| B7 | navigation / page wiring / capability catalog / public surface / **source completeness** (65) | **0** | **0** |

**All fourteen batches green, every one exit 0 — roughly 440 tests across browser and backend.**

V2 and V3 first went red on **all 15** and **2 of 6** respectively, from a single
cause in my own locators (§16.2), and are green after the fix. Reported because
it happened, not only because it was corrected.

No test was weakened or removed to obtain green.

---

## 15. Typecheck / lint / build

| Check | Result |
|---|---|
| `npm run typecheck` | **0 errors** |
| `npm run lint:ts` | **0 errors** |
| `npm run build:prod` | **exit 0** (2 pre-existing size warnings) |
| `uv run python -c "import app.main"` | **exit 0** |
| Migration | **none** |

The bundle was rebuilt before the browser batches, so the evidence matches the committed source.

---

## 16. Changed-test justification

Only locators changed, and only because the card carries a second line.

| Change | `old visual expectation` | `V0.7 approved visual baseline` | `new expectation` |
|---|---|---|---|
| context locators in 4 browser files | `get_by_role("button", name="Client Visit", exact=True)` — the button's accessible name was the label alone | the card is `<b>label</b><small>hint</small>`, so its accessible name is `"Client Visit Client / site"` | substring match on the label, which is Playwright's default |

Seven literal call sites plus three loops. **No assertion was weakened**: matching a label inside a longer accessible name still identifies exactly one card, and the hints are separately asserted in V1.

### 16.1 A coverage gap of mine, closed

V3 requires verifying that **My Route remains visually distinct from Configuration**. No journey asserted it — mine from report 003 checked that the links exist, not that they sit in two separate groups. `test_my_route_stays_visually_separate_from_configuration` was added.

### 16.2 My own mistakes in this checkpoint

| # | Mistake | Caught by |
|---|---|---|
| 1 | relaxed the seven literal locators but left three `exact=True` inside loops | the first visual run — 3 of 22 red, all the same cause |
| 2 | asserted `get_by_text("CER Route", exact=True)` count 1; it appears **three** times on `/admin` (menu group, application title, card description) | the new test itself, on its first run |
| 3 | left `exact=True` on the **variable** form inside the shared arrival helper (`name=contexto_ui`) after relaxing the seven literal call sites | the regression — V2 red on all 15 journeys and V3 on 2 of 6, one cause. The same class of mistake as #1, twice in one checkpoint: a global replace that matched literals and missed the parameterised forms |

Both were test-side. Neither reached the product.

---

## 17. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Classification |
|---|---|---|---|
| `What's next?` uses the V0.7 card/grid presentation | yes | §1, §5, §6 | AS-BUILT / CONFIRMED |
| stacked-button workbench no longer canonical | yes | computed grid ≥ 2 columns in both viewports | AS-BUILT / CONFIRMED |
| all seven choices visible | yes | V1, V4, J13 | AS-BUILT / CONFIRMED |
| every card opens the correct flow | yes | V4, all seven | AS-BUILT / CONFIRMED |
| Start Work lands on the workbench | yes | J1, V1 | AS-BUILT / CONFIRMED |
| Complete returns to the workbench | yes | §9 | AS-BUILT / CONFIRMED |
| Leave returns to the workbench | yes | §9 | AS-BUILT / CONFIRMED |
| Back/Cancel returns without a ghost Trip | yes | §10 — 0 Trip rows | AS-BUILT / CONFIRMED |
| End Work secondary and available | yes | §8 | AS-BUILT / CONFIRMED |
| End Work not an inappropriate shortcut | yes | J12, four states | AS-BUILT / CONFIRMED |
| Change Plan uses the same taxonomy | yes | §11, one shared component | AS-BUILT / CONFIRMED |
| no Work Session / Trip / Activity rule change | yes | §4 — backend diff empty; §14 | AS-BUILT / CONFIRMED |
| `/route` guard unchanged | yes | §12 | AS-BUILT / CONFIRMED |
| owner/admin behaviour unchanged | yes | §13 | AS-BUILT / CONFIRMED |
| responsive mobile rendering | yes | §5 | AS-BUILT / CONFIRMED |
| desktop/tablet rendering | yes | §6 | AS-BUILT / CONFIRMED |
| no RTE06 functionality | yes | §19 | AS-BUILT / CONFIRMED |
| RTE03/RTE04/RTE05 regression green | yes | §14 | AS-BUILT / CONFIRMED |
| typecheck / lint / build green | yes | §15 | AS-BUILT / CONFIRMED |
| no remaining `PARTIAL` / `DECISION REQUIRED` in RTE05 scope | yes | the 003 `PARTIAL` is closed by §1–§6; the 003 `DECISION REQUIRED` is closed by D-03 | AS-BUILT / CONFIRMED |
| real iOS/Android hardware | no | §18 | **PENDING VALIDATION** |

**No remaining `PARTIAL`, `NOT IMPLEMENTED / GAP`, `DEVIATION`, `UNAUTHORIZED DECISION` or `DECISION REQUIRED` inside RTE05 scope.**

---

## 18. Remaining PENDING VALIDATION

**Real iOS/Android hardware: not executed.** All evidence is Microsoft Edge on Windows 11 at `390×844` and `1280×900`, against the production bundle. It covers grid layout at both widths, touch-target height, label legibility, absence of horizontal overflow and the IndexedDB queue in a Chromium engine. It does **not** cover iOS Safari specifics, real network transitions or platform storage eviction.

D-04 states this does not block certification given the responsive evidence above. The limit is identical to RTE03, RTE04 and reports 001–003, and has not narrowed.

---

## 19. RTE06+ not started

Confirmed. Nothing was built for GPS/location, routing mileage, fuel, Reports, Live tracking, the Activity Explorer, new dashboard concepts, new navigation architecture, new roles or capabilities, new standardized values, or any Work Session / Trip / Activity state change. `RouteActivityPage` still states openly that the Activity Explorer is RTE08 and does not exist yet.

---

## 20. Proposed final RTE05 certification status

**RTE05 — Ready for CER Certification.**

The workbench now matches the approved V0.7 card/grid presentation, taken literally from the mockup shipped in the RTE01 package rather than inferred. Behaviour certified in report 003 is preserved and re-evidenced. The two items report 003 left open are closed: the `PARTIAL` by this alignment, the `DECISION REQUIRED` by CER's D-03.

One item remains declared and **not** counted as passed: **real iOS/Android hardware** (`PENDING VALIDATION`, §18), which D-04 states does not block certification.

### Operational action required elsewhere

**None.** No migration, no capability, no seed. Deploying the built assets is the only requirement.

### Next step, not started

RTE06, per its own instruction document. Nothing begins until CER reviews this report and explicitly certifies RTE05.
