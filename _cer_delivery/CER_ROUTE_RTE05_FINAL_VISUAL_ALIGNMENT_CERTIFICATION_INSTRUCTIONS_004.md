# CER Route — RTE05 Final Visual Alignment + Certification Instructions 004

## Context

RTE05 functional behavior and UX flow were realigned in `CER_ROUTE_RTE05_FINAL_CERTIFICATION_REPORT_003.md`.

CER review accepts the functional flow implemented in that report:

- `Start Work` → `What's next?`
- one pre-trip screen per context
- `Start Trip` without redundant confirmation
- `On Route`
- `Arrived`
- Activity execution
- `Complete / Leave`
- return to `What's next?`
- `End Work` only from the workbench as the normal visible exit
- `Change Plan` reusing the same destination/context choices
- `/route` protected by `route.worksession.execute`

The remaining RTE05 closure item is **visual alignment of the `What's next?` workbench with the approved V0.7 mockup**.

The current implementation uses full-width stacked buttons. CER has confirmed that this is not the approved presentation.

The approved V0.7 mockup is the visual source of truth for the workbench.

This instruction is the final RTE05 closure iteration.

Do not begin RTE06.

---

## Current State

From report 003:

- Functional workbench behavior is correct.
- All seven approved choices are present.
- Start Work lands directly on the workbench.
- Complete/Leave return directly to the workbench.
- Change Plan shares the same choice component.
- End Work is available from the workbench.
- The workbench presentation is still the previously shipped stacked-button layout.
- Report 003 classified the approved card/grid presentation as `PARTIAL`.

RTE05 must not be certified until this visual divergence is resolved.

---

## Confirmed CER Decisions

### D-01 — Workbench presentation

`What's next?` must follow the approved V0.7 **card/grid workbench presentation**.

Do not preserve the existing full-width stacked-button presentation simply because it already exists in production.

The approved mockup is authoritative for:

- visual hierarchy;
- card/grid composition;
- grouping of the seven work options;
- relative prominence of work choices versus End Work;
- mobile-first structure.

Responsive adaptation is allowed where needed, but the visual concept must remain the approved card/grid workbench.

---

### D-02 — Functional behavior does not change

This iteration is visual/interaction alignment only.

Do not change:

- Work Session rules;
- Trip rules;
- Activity rules;
- Activity multi-select;
- Check Delivery Received By rules;
- End Work business rules;
- Change Plan domain behavior;
- role/capability model;
- `/route` guard;
- standardized values;
- odometer behavior;
- tenant isolation;
- audit;
- offline behavior.

---

### D-03 — Core owner/admin access

No change is required.

If `owner` or `admin` already holds `route.worksession.execute`, access to `/route` remains valid under the certified role/capability model.

Do not modify RTE02-A02 or Core role capabilities in this closure.

This item is considered resolved for RTE05.

---

### D-04 — Real hardware validation

Real iOS/Android hardware remains `PENDING VALIDATION`.

It does not block RTE05 certification if the responsive/browser evidence required below is green.

---

# Objective

Align the `What's next?` workbench visually with the approved V0.7 mockup while preserving all behavior certified in report 003.

After implementation, RTE05 should have no remaining:

- `PARTIAL`
- `NOT IMPLEMENTED / GAP`
- `DEVIATION`
- `UNAUTHORIZED DECISION`
- `DECISION REQUIRED`

inside RTE05 scope.

Real-device validation may remain `PENDING VALIDATION`.

---

# Scope

## In Scope

- visual structure of the `What's next?` workbench;
- card/grid layout for the seven approved options;
- responsive behavior of that layout;
- visual hierarchy of `End Work`;
- reuse of the same context-choice component where appropriate;
- validation that visual changes do not alter navigation or state behavior;
- final RTE05 regression;
- final certification report.

## Out of Scope

Do not implement or redesign:

- RTE06;
- GPS/location;
- routing mileage;
- fuel;
- Reports;
- Live;
- Activity Explorer;
- new dashboard concepts;
- new navigation architecture;
- new roles/capabilities;
- new standardized values;
- Work Session state changes;
- Trip state changes;
- Activity state changes;
- backend domain behavior;
- Core access model.

---

# Existing Components to Reuse

Reuse the existing workbench and context-choice implementation created in report 003.

The existing shared choice component used by:

- `What's next?`
- `Change Plan`

should remain a single source of truth unless the approved mockup requires a presentation wrapper specific to one context.

Do not duplicate the seven-option taxonomy.

Do not create a second independent list of contexts.

---

# Visual Requirements

## VR-01 — Approved workbench structure

The workbench must present these seven choices:

- Client Visit
- Recruiting
- Employee Visit
- Check Delivery
- Office
- Other
- Home / Return Home

The visual arrangement must follow the approved V0.7 mockup's card/grid concept rather than full-width stacked buttons.

---

## VR-02 — Card behavior

Each card must:

- be clearly tappable/clickable;
- map to exactly one approved work context;
- preserve the current navigation behavior;
- not introduce an intermediate confirmation step;
- not alter the destination/context fields required later.

Do not encode business logic in the card presentation.

---

## VR-03 — End Work hierarchy

`End Work` remains available from the workbench.

It must remain visually secondary to the seven work choices.

Do not convert End Work into:

- an eighth work card;
- a peer primary action;
- an action repeated inside each card.

The workbench should visually communicate:

**choose next work context first; end the workday as a separate secondary action.**

---

## VR-04 — Responsive behavior

Validate at minimum:

- mobile viewport around `390×844`;
- desktop/tablet viewport around `1280×900`.

The mobile layout must preserve:

- readable labels;
- adequate touch targets;
- no clipped card content;
- no horizontal overflow;
- no overlap with the odometer banner;
- no overlap with End Work;
- no accidental reordering of work contexts.

Desktop may expand the grid responsively, but must remain recognizably the same workbench.

---

## VR-05 — Approved visual source

Compare the implementation against the approved V0.7 mockup.

Do not infer a new visual system from personal preference.

If the approved mockup asset/reference cannot be located with enough fidelity to implement the card/grid correctly, STOP and report exactly what source is missing.

Do not guess.

---

# Functional Requirements to Preserve

## FR-01 — Start Work

`Start Work`
→ directly to `What's next?`

No intermediate screen.

---

## FR-02 — Workbench navigation

Selecting a card:

→ opens the correct single pre-trip/context screen.

No extra `Where to next?`.

No `Prepare Trip` summary step.

---

## FR-03 — Back/Cancel

Before `Start Trip`:

→ returns to the workbench.

No ghost Trip.

---

## FR-04 — Complete/Leave

After terminalization:

→ return directly to the same workbench.

---

## FR-05 — Change Plan

Change Plan continues to reuse the same approved context taxonomy.

If the shared component is visually reused there, it must remain appropriate to the Change Plan context.

Do not change Change Plan domain behavior.

---

## FR-06 — End Work

End Work remains:

- visible from the workbench;
- absent as a normal shortcut in pre-trip, IN_TRANSIT, unresolved ARRIVED and Activity IN_PROGRESS states.

---

## FR-07 — `/route` guard

Preserve:

`route.worksession.execute`

Do not change access semantics accepted in report 003.

---

# Acceptance Criteria

RTE05 can be certified only if all of the following are evidenced:

1. `What's next?` uses the approved V0.7 card/grid workbench presentation.
2. The previous full-width stacked-button workbench is no longer the canonical presentation.
3. All seven approved choices are visible.
4. Every card opens the correct existing flow.
5. Start Work still lands directly on the workbench.
6. Complete still returns directly to the workbench.
7. Leave still returns directly to the workbench.
8. Back/Cancel still returns to the workbench without creating a ghost Trip.
9. End Work remains visually secondary and functionally available from the workbench.
10. End Work does not reappear as an inappropriate shortcut elsewhere.
11. Change Plan still uses the same context taxonomy.
12. No Work Session, Trip or Activity business rule changes.
13. `/route` access guard remains unchanged.
14. Owner/admin capability behavior remains unchanged.
15. Responsive mobile rendering is correct.
16. Desktop/tablet rendering is correct.
17. No new RTE06 functionality exists.
18. RTE03/RTE04/RTE05 relevant regression remains green.
19. Frontend typecheck/lint/build remain green.
20. No remaining `PARTIAL` or `DECISION REQUIRED` exists within RTE05 scope.

---

# Required Browser Validation

Use the production bundle and normal navigation.

## V1 — Supervisor mobile workbench

At approximately `390×844`:

- sign in as Supervisor;
- Start Work;
- verify immediate arrival at `What's next?`;
- verify card/grid presentation;
- verify all seven options;
- verify End Work is secondary;
- verify no old stacked workbench remains as the canonical layout.

---

## V2 — Administrador mobile workbench

At approximately `390×844`:

- sign in as Administrador;
- open My Route;
- verify same operational workbench component;
- verify same seven cards;
- verify no duplicated Admin-specific operational UI.

---

## V3 — Desktop/tablet responsive workbench

At approximately `1280×900`:

- verify the same workbench;
- verify responsive expansion/alignment;
- verify no overflow or broken spacing;
- verify My Route remains visually distinct from Configuration.

---

## V4 — Card navigation coverage

From the workbench, verify each option opens its correct existing context flow:

- Client Visit
- Recruiting
- Employee Visit
- Check Delivery
- Office
- Other
- Home

Do not revalidate only one representative card.

---

## V5 — Return to workbench

Complete at least:

- one `Complete` journey;
- one `Leave` journey;

and verify both return to the aligned card/grid workbench.

---

## V6 — Back/Cancel

Enter at least one pre-trip context and use Back/Cancel.

Verify:

- return to card/grid workbench;
- no Trip created;
- visual state remains coherent.

---

## V7 — Change Plan

From `IN_TRANSIT`:

- open Change Plan;
- verify the approved context taxonomy remains the same;
- verify visual reuse does not change domain behavior;
- apply a change;
- return to On Route.

---

## V8 — End Work

Verify:

- visible on workbench;
- visually secondary;
- zero-trip Work Session can end;
- absent from inappropriate active-flow screens.

---

## V9 — Access guard regression

Verify:

- Supervisor → `/route` allowed;
- route_admin → `/route` allowed;
- manager/viewer without execute → denied;
- platform identity alone without execute → denied;
- owner/admin behavior remains as report 003.

---

# Regression Required

Re-run and report the suites necessary to demonstrate that this visual alignment did not regress:

- RTE05 workbench/browser journeys;
- RTE05 Activity execution;
- RTE05 closure / Received By;
- RTE04 Trip + Change Plan;
- RTE04 odometer/End Work;
- RTE03 Work Session/offline recovery;
- RTE02-A02 access model;
- tenant isolation / authorization;
- navigation/page wiring;
- frontend source completeness;
- typecheck;
- lint;
- production build.

Do not weaken or remove tests to obtain green.

If an existing browser assertion changes only because it encoded the stacked-button presentation, document:

`old visual expectation → V0.7 approved visual baseline → new expectation`

---

# Do Not Change

Do not change:

- Work Session domain;
- Trip domain;
- Activity domain;
- Activity one-block semantics;
- multi-select rules;
- Check Delivery Received By rules;
- Outcome rules;
- Standardized Values;
- role/capability assignments;
- `/route` guard semantics;
- odometer rules;
- offline occurrence-time behavior;
- tenant isolation;
- audit behavior;
- navigation separation between My Route and Configuration.

---

# Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE05_FINAL_VISUAL_ALIGNMENT_REPORT_004.md`

Do not overwrite reports 001, 002 or 003.

The report must include:

1. visual baseline used;
2. before vs after workbench presentation;
3. exact frontend files/components changed;
4. confirmation that no backend domain logic changed;
5. mobile workbench evidence;
6. desktop/tablet evidence;
7. seven-card navigation evidence;
8. End Work hierarchy evidence;
9. Complete/Leave return evidence;
10. Back/Cancel evidence;
11. Change Plan evidence;
12. `/route` guard regression;
13. role/access regression;
14. regression results;
15. typecheck/lint/build;
16. changed-test justification;
17. Expected → Implemented → Evidence → Gap;
18. remaining `PENDING VALIDATION`;
19. explicit confirmation RTE06+ not started;
20. proposed final RTE05 certification status.

---

# Expected Final Classification

If all acceptance criteria are satisfied:

- card/grid alignment → `AS-BUILT / CONFIRMED`
- functional flow → `AS-BUILT / CONFIRMED`
- access model → `AS-BUILT / CONFIRMED`
- RTE03/RTE04/RTE05 regression → `AS-BUILT / CONFIRMED`
- real iOS/Android hardware → `PENDING VALIDATION` only

There should be no remaining RTE05:

- `PARTIAL`
- `NOT IMPLEMENTED / GAP`
- `DEVIATION`
- `UNAUTHORIZED DECISION`
- `DECISION REQUIRED`

---

# STOP Conditions

STOP and return to CER if:

- the V0.7 visual baseline cannot be located or interpreted reliably;
- matching the workbench requires changing domain behavior;
- a new role/capability appears necessary;
- Change Plan requires a separate taxonomy;
- the visual alignment requires a new dashboard/navigation model;
- any RTE06 functionality becomes necessary;
- any new product decision is required.

After implementation, validation and report delivery:

# STOP

Do not begin RTE06 until CER reviews report 004 and explicitly certifies RTE05.
