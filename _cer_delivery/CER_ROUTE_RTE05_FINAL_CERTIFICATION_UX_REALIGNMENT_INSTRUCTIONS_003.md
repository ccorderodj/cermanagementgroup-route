# CER Route — RTE05 Final Certification + UX Realignment Instructions 003

## Context

RTE05 is not yet certified.

The functional Activity domain delivered in RTE05 is largely correct, but CER visual validation found that the **Mobile/My Route navigation flow diverged from the approved V0.7 baseline** and introduced unnecessary intermediate screens and extra exit points.

This instruction closes RTE05 correctly by combining:

1. the remaining `/route` access guard decision;
2. UX realignment of My Route against the approved workbench flow;
3. full regression of RTE03 + RTE04 + RTE05 after the UX simplification.

This is **not a redesign of the product** and is **not RTE06**.

RTE02-A02, RTE03 and RTE04 remain certified baseline.

Do not begin RTE06.

---

# Objective

Restore the approved operational flow so that **My Route behaves as one continuous work experience**, with the `What's next?` screen acting as the central workbench.

Target navigation:

`Start Work`
→ `What's next?`
→ select destination/work context
→ capture only the data required for that context
→ `Start Trip`
→ `On Route`
→ `Arrived`
→ post-arrival Activity flow
→ `Complete / Leave + Outcome`
→ `What's next?`

The implementation must remove unnecessary intermediate screens without changing certified business rules.

---

# Confirmed Product Decisions

## PD-01 — The workbench is the central operational screen

The approved `What's next?` screen is the Supervisor's workbench.

It must be reached:

- immediately after successful `Start Work`;
- after successful `Complete`;
- after successful `Leave`;
- whenever the current Work Session is ACTIVE and there is no unresolved Trip or Activity execution.

The workbench must show the approved choices:

- Client Visit
- Recruiting
- Employee Visit
- Check Delivery
- Office
- Other
- Home

Do not replace this with another intermediate "working" screen.

---

## PD-02 — End Work is available from the workbench

`End Work` must be available from the workbench because a Supervisor may:

- Start Work;
- perform non-travel work;
- never create a Trip;
- still need to end the Work Session.

The system must **not** force a fake Home Trip simply to end a zero-trip Work Session.

This preserves A-1.

---

## PD-03 — End Work must not become a shortcut inside active travel/work flows

Do not expose End Work as a normal shortcut while the user is:

- entering/preparing a Trip;
- in `IN_TRANSIT`;
- selecting/starting post-arrival Activities;
- executing an Activity block.

Existing server-side guards remain authoritative.

For `IN_TRANSIT`, preserve the certified D-07 review / Continue Working / End Work Anyway behavior when End Work is legitimately invoked through the approved lifecycle.

Do not create new bypasses.

---

## PD-04 — Start Work must go directly to the workbench

Current agentic implementation inserted an extra screen:

`Start Work → Working since / Where to next? → work choices`

That extra screen is not required.

Target:

`Start Work → What's next?`

The working-since information may be retained as contextual information if useful, but it must not create an extra navigation step.

---

## PD-05 — Trip preparation must not be split into unnecessary screens

Current implementation introduced:

`select context → Prepare trip → summary screen → Start Trip`

CER does not approve this additional step sequence.

For a Trip context:

1. user selects the context from `What's next?`;
2. the product asks only for the pre-trip fields required for that context;
3. the same screen offers the primary action **Start Trip**;
4. `Back` or `Cancel` returns to the workbench without creating/starting a Trip.

Do not create a second confirmation screen merely to repeat the destination and ask for Start Trip again.

---

## PD-06 — On Route remains a distinct operational state

After `Start Trip`, show the existing On Route state.

It must preserve:

- current Trip context;
- destination/reference as applicable;
- departed/start information;
- Arrived;
- Change Plan.

Do not remove the On Route state.

---

## PD-07 — Change Plan reuses the workbench choices

Change Plan remains valid only while `IN_TRANSIT`.

When invoked:

- show the same approved destination/context choices used by the workbench;
- collect the relevant fields for the newly chosen plan;
- preserve the existing append-only Change Plan/history semantics;
- do not create a parallel taxonomy or a different set of options.

Change Plan does not return the user to a new Work Session state and does not create a new Trip.

---

## PD-08 — Post-arrival Activity behavior remains as delivered

Preserve RTE05 improvements:

- Client Visit / Recruiting / Other: multi-select 1..N;
- one execution block per stop;
- one start;
- one end;
- one duration;
- one Outcome;
- one optional Notes;
- Complete and Leave;
- Check Delivery `Received By` rule from closure 002;
- Employee Visit / Office without redundant Activity selector;
- HOME with no Activity block.

`Start Activity` remains acceptable.

---

## PD-09 — After Activity terminalization, return to the workbench

After `Complete` or `Leave` succeeds and the Trip becomes `CLOSED`:

- Work Session remains ACTIVE;
- client returns to `What's next?`;
- do not return to an obsolete/intermediate `working` screen;
- do not require an extra click to get back to the workbench.

---

## PD-10 — `/route` requires operational capability

The My Route page itself must require:

`route.worksession.execute`

Expected:

- Administrador → allowed;
- Supervisor → allowed;
- Core-only authenticated user without the capability → denied before entering the operational shell.

Do not add a new capability.

---

# Required Flow Audit Before Modification

Before changing code, inspect the current implementation and document the current state-to-screen mapping.

At minimum map:

| Domain State | Current Screen | Target Screen |
|---|---|---|
| no active Work Session | Start Work | Start Work |
| ACTIVE session, no unresolved Trip | current implementation | `What's next?` |
| Trip pre-start/context capture | current implementation | single context form + `Start Trip` + Back/Cancel |
| IN_TRANSIT | current implementation | On Route |
| ARRIVED unresolved | current implementation | context-specific post-arrival Activity screen |
| Activity IN_PROGRESS | current implementation | Activity execution |
| Activity terminalized / Trip CLOSED | current implementation | `What's next?` |
| HOME Trip CLOSED | current implementation | return to active-session workbench / approved End Work path |
| no-trip ACTIVE session ending | current implementation | End Work from workbench |

Do not infer the flow from UI labels alone. Verify the authoritative Work Session / Trip / Activity states behind each screen.

If the current code cannot be aligned without changing certified state semantics, STOP and report the incompatibility.

---

# Workbench UX Requirements

## FR-01 — Workbench contents

The `What's next?` screen is the canonical active-session idle state.

Display the seven approved choices:

- Client Visit
- Recruiting
- Employee Visit
- Check Delivery
- Office
- Other
- Home

Preserve the approved mobile-first card/grid presentation unless a responsive adjustment is necessary.

Do not introduce a second "Where to next?" screen with a different presentation.

---

## FR-02 — End Work on workbench

End Work must be reachable from the workbench without requiring a Trip.

It should be visually secondary to starting the next task/trip.

Do not place it as a competing primary action beside each destination.

Server-side Work Session / Trip / Activity guards remain authoritative.

---

# Context Capture + Start Trip

## FR-03 — One pre-trip screen per selected context

After selecting a workbench option, request only its approved pre-trip data.

### Client Visit
- Destination = free text
- primary action = `Start Trip`
- Back/Cancel = workbench

### Recruiting
- Area / Location = free text
- primary action = `Start Trip`
- Back/Cancel = workbench

### Employee Visit
- Employee / Reference = free text
- Employee Visit Reason = approved Standardized Value
- primary action = `Start Trip`
- Back/Cancel = workbench

### Check Delivery
- Employee / Reference = free text
- Delivery Type = approved Standardized Value
- primary action = `Start Trip`
- Back/Cancel = workbench

### Office
- Office = free text
- Office Purpose = approved Standardized Value
- primary action = `Start Trip`
- Back/Cancel = workbench

### Other
- Area / Location = free text
- primary action = `Start Trip`
- Back/Cancel = workbench

### Home
Preserve the certified HOME behavior and required pre-trip semantics already implemented.

Do not add redundant confirmation screens.

---

## FR-04 — Cancel/back semantics

Before Start Trip:

- Back/Cancel must return to the workbench;
- no Trip may become IN_TRANSIT;
- no Activity may be created;
- no false history may be written.

If a PLANNING record already exists as an implementation detail, cancellation must leave the authoritative domain in a valid approved state and must not produce a ghost current Trip.

Use existing domain conventions; do not invent destructive cleanup without evidence.

---

# On Route + Change Plan

## FR-05 — On Route screen

After Start Trip:

- show the current context/destination;
- show Arrived;
- show Change Plan;
- do not add an unnecessary workbench intermediary.

Preserve certified RTE04 state behavior.

---

## FR-06 — Change Plan

From IN_TRANSIT:

`Change Plan`
→ same workbench choice set
→ relevant context fields
→ apply change to current Trip
→ return to On Route

Do not:

- close the Trip;
- create a replacement Trip;
- expose post-arrival Activity selectors;
- create a second taxonomy.

---

# Arrived + Activity

## FR-07 — Arrival

After Arrived on non-HOME Trip:

- enter the correct RTE05 post-arrival flow immediately;
- do not return to the workbench while the Trip is unresolved.

---

## FR-08 — Multi-Activity

Preserve the current RTE05 multi-select implementation for:

- Client Visit;
- Recruiting;
- Other.

One execution block only.

No per-Activity timers/outcomes.

---

## FR-09 — Activity completion

Preserve:

- Start Activity;
- Complete;
- Leave;
- Outcome;
- optional Notes;
- Received By semantics;
- atomic Trip closure.

After terminalization:

`Trip CLOSED + Work Session ACTIVE`
→ `What's next?`

---

# End Work Rules

## FR-10 — Workbench End Work

If Work Session is ACTIVE and no unresolved Trip/Activity exists:

- End Work may be selected from the workbench;
- zero-trip Work Session may end normally;
- existing RTE04 odometer/END evidence rules still apply when vehicle travel occurred.

---

## FR-11 — No End Work shortcut during pre-trip preparation

On a context-capture screen before Start Trip:

- do not show End Work;
- user may Back/Cancel to workbench and End Work there.

This prevents premature/ambiguous exit and keeps one canonical ending location.

---

## FR-12 — No ordinary End Work shortcut while Activity is active

Preserve D-07 / RTE05:

- IN_PROGRESS Activity → End Work unavailable;
- server rejects invalid direct invocation;
- Complete or Leave + Outcome is required.

---

# `/route` Access Guard

## FR-13 — Page protection

Protect the My Route page/shell with:

`route.worksession.execute`

Validate both client routing/navigation and server/page guard behavior consistent with the existing architecture.

Required outcomes:

- Administrador: allowed;
- Supervisor: allowed;
- Core owner/admin/manager/viewer without Route execute: denied;
- platform identity alone must not grant operational Route access.

Do not weaken endpoint authorization.

---

# Scope

## In Scope

- My Route screen/state routing.
- removal of redundant intermediate UX screens.
- workbench as canonical idle state.
- Start Work → workbench.
- Complete/Leave → workbench.
- pre-trip form simplification.
- Back/Cancel.
- End Work placement.
- Change Plan UX reuse.
- `/route` capability guard.
- browser validation of complete operational flow.
- regression of RTE03/RTE04/RTE05.

## Out of Scope

Do not implement:

- RTE06;
- GPS/location;
- routing mileage;
- fuel;
- Reports;
- Live;
- Activity Explorer;
- new roles/capabilities;
- new Standardized Values;
- domain redesign;
- new Work Session states;
- new Trip states;
- new Activity states;
- new dashboard;
- duplicated My Route experience.

---

# Do Not Change

Do not change without CER approval:

- RTE02-A02 role model;
- RTE03 single Work Session behavior;
- RTE04 Trip state machine;
- HOME direct Trip close;
- Change Plan domain semantics;
- odometer evidence rules;
- END Option B;
- Activity one-block semantics;
- Outcome tenant configuration;
- Check Delivery Received By Complete/Leave rule;
- 28 approved Standardized Values;
- occurrence-time semantics;
- tenant isolation;
- audit requirements.

---

# Required Browser Journeys

Validate against the production frontend bundle using normal navigation.

## J1 — Start Work → workbench
- sign in as Supervisor;
- Start Work;
- next screen is `What's next?`;
- no extra `Working since / Where to next?` navigation step;
- seven approved choices visible;
- End Work available as secondary workbench action.

## J2 — Zero-trip End Work
- Start Work;
- create no Trip;
- End Work from workbench;
- Work Session ends successfully.

## J3 — Client Visit pre-trip
- workbench → Client Visit;
- enter destination;
- primary action is Start Trip;
- no Prepare Trip → second Start Trip screen;
- Back/Cancel returns to workbench.

## J4 — Client Visit full flow
- workbench;
- Client Visit;
- Start Trip;
- On Route;
- Arrived;
- select multiple Activities;
- Start Activity;
- Complete + Outcome;
- Trip CLOSED;
- return directly to workbench.

## J5 — Leave flow
- operational context;
- Start Activity;
- Leave + Outcome;
- Trip CLOSED;
- return directly to workbench.

## J6 — Check Delivery
- validate pre-trip Delivery Type;
- post-arrival Received By rule:
  - Complete requires it;
  - Leave does not.

## J7 — Employee Visit
- Reason asked before Trip only;
- no duplicate Activity selector after Arrived;
- terminalization returns to workbench.

## J8 — Office
- Purpose asked before Trip only;
- no duplicate Activity selector after Arrived;
- terminalization returns to workbench.

## J9 — Recruiting / Other
- correct post-arrival multi-select;
- terminalization returns to workbench.

## J10 — HOME
- select Home from workbench;
- preserve certified HOME Trip behavior;
- no Activity block;
- verify resulting session UX is coherent with End Work/workbench rules.

## J11 — Change Plan
- while IN_TRANSIT select Change Plan;
- see same seven workbench context choices;
- choose new context;
- capture correct context fields;
- apply to same Trip;
- return to On Route;
- original plan history preserved.

## J12 — End Work placement
Assert End Work:
- visible on workbench;
- absent from pre-trip context capture;
- absent while Activity IN_PROGRESS;
- does not create a bypass.

## J13 — Administrador
- visible My Route navigation;
- Start Work;
- reaches same workbench;
- follows same operational component.

## J14 — `/route` guard
- Supervisor with execute → allowed;
- Administrador with execute → allowed;
- Core-only authenticated user without execute → denied via direct `/route`.

## J15 — Reload / reauth / second device
For unresolved Trip or active execution, preserve authoritative recovery and do not incorrectly send the user to workbench.

---

# Backend / Integration Regression

At minimum re-run and evidence:

- RTE02-A02 role/access tests relevant to My Route;
- RTE03 Work Session lifecycle;
- RTE03 offline queue;
- RTE04 Trips;
- RTE04 Change Plan;
- RTE04 Odometer + End Work;
- RTE05 Activity execution;
- RTE05 End Work guards;
- RTE05 Check Delivery;
- tenant isolation;
- permission catalog/navigation wiring;
- idempotency/concurrency;
- audit.

Do not modify tests merely to reflect the new UX unless the old assertion explicitly encoded one of the now-rejected intermediate screens.

For every changed existing test, explain:

`old expectation → approved decision that supersedes it → new expectation`

No skip/xfail to obtain green.

---

# Acceptance Criteria

RTE05 can be proposed for certification only if:

1. Start Work lands directly on `What's next?`.
2. `What's next?` is the canonical active-session workbench.
3. Workbench shows all seven approved choices.
4. End Work is available from workbench, including zero-trip sessions.
5. Context capture and Start Trip occur on one screen.
6. Back/Cancel works before Start Trip.
7. No redundant Prepare Trip / Start Trip confirmation screen remains.
8. On Route remains intact.
9. Change Plan reuses workbench choices and current Trip.
10. Arrived enters the correct post-arrival flow.
11. RTE05 multi-select/one-block behavior remains intact.
12. Complete/Leave returns directly to workbench.
13. End Work is not exposed as an inappropriate shortcut.
14. `/route` requires `route.worksession.execute`.
15. Admin and Supervisor use the same My Route experience.
16. Core-only users cannot enter `/route`.
17. RTE03/RTE04/RTE05 regression is green.
18. No RTE06+ functionality is introduced.
19. No remaining `DECISION REQUIRED` exists inside RTE05 scope.

Real iOS/Android hardware may remain `PENDING VALIDATION` if not executed, but must be declared.

---

# Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE05_FINAL_CERTIFICATION_REPORT_003.md`

Do not overwrite reports 001 or 002.

The report must include:

1. Current Flow Before;
2. Target Flow Implemented;
3. screen/state transition matrix;
4. exact screens removed/merged;
5. workbench behavior;
6. Start Work behavior;
7. End Work placement;
8. per-context pre-trip behavior;
9. Change Plan behavior;
10. Arrived/Activity behavior;
11. Complete/Leave return behavior;
12. `/route` guard;
13. role/access evidence;
14. browser journey evidence J1–J15;
15. backend regression counts;
16. frontend typecheck/lint/build;
17. changed tests and justification;
18. Expected → Implemented → Evidence → Gap;
19. remaining PENDING VALIDATION items;
20. confirmation RTE06+ not started;
21. proposed certification status.

Use unique incremental filenames for any additional report.

---

# Classification

Use only:

- AS-BUILT / CONFIRMED
- PARTIAL
- PENDING VALIDATION
- NOT IMPLEMENTED / GAP
- DEVIATION
- UNAUTHORIZED DECISION
- TECHNICAL DEBT
- DECISION REQUIRED

Do not call RTE05 Completed solely because tests pass.

---

# STOP Conditions

STOP and return to CER if:

- realignment requires changing a certified Work Session / Trip / Activity state rule;
- a context requires data not defined in the approved matrix;
- Change Plan cannot reuse the approved context choices without domain redesign;
- End Work placement requires a new business rule;
- a new capability or role appears necessary;
- `/route` cannot be protected with the existing execute capability;
- historical data would need rewriting;
- RTE06 functionality becomes necessary;
- any new product decision is required.

After implementation, validation and delivery report:

# STOP

Do not begin RTE06 until CER reviews this report and explicitly certifies RTE05.
