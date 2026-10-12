# CER Route — RTE09 Enhancement 01
## Historical Period Selection + Interactive Activity Breakdown
### Development Instructions
### Revision 001

## 1. Context

RTE09 Reports is already implemented and functionally aligned with the approved V0.7 baseline.

Current behavior confirmed by CER:

- Reports works on desktop and mobile.
- Supervisor filter works.
- Week / Month / Year works.
- KPIs work.
- `By day / By week / By month` grouping works.
- Activity Breakdown works.
- Official Miles are correct.
- Fuel Estimate remains prepared for future Fuel Reference data.

CER now requires a controlled UX improvement to make Reports more useful for historical review and drill-down.

This is a **delta over the existing RTE09 implementation**.

Do not redesign Reports.

Do not reopen the RTE09 reporting architecture.

---

# 2. Objective

Improve Reports in two coordinated ways:

1. Allow the user to choose **which Week, Month or Year** to review.
2. Make the lower-left temporal grouping interactive so selecting one group filters the **Activity Breakdown** on the right.

The page must preserve the V0.7 structure and visual language.

---

# 3. Confirmed UX Model

The reporting hierarchy becomes:

```text
Supervisor
    ↓
Period Type
Week / Month / Year
    ↓
Specific Period
Selected week / selected month / selected year
    ↓
Period KPIs
    ↓
Temporal Groups
Day / Week / Month
    ↓
Optional selected group
    ↓
Activity Breakdown
filtered to that group
```

The primary report period and the selected temporal subgroup are separate concepts.

---

# 4. Dynamic Specific-Period Selector

The existing:

```text
Week | Month | Year
```

control remains.

Add a dynamic selector for the **specific period instance**.

Behavior:

## Week

When `Week` is selected, the selector represents a specific week.

Display example:

```text
Oct 12–18, 2026
```

## Month

When `Month` is selected, the selector represents a specific month.

Display example:

```text
October 2026
```

## Year

When `Year` is selected, the selector represents a specific year.

Display example:

```text
2026
```

The selector must update its semantics automatically when the Period Type changes.

Do not use one generic label that makes the selected temporal scope ambiguous.

---

# 5. Default Period

On initial load, keep the existing behavior:

- Week → current business week.
- Month → current business month.
- Year → current business year.

The server remains authoritative for the effective business date/timezone.

Do not initialize historical reporting from browser-local `new Date()`.

This requirement exists specifically to avoid reintroducing the date-authority defect previously corrected in Activity Explorer.

---

# 6. Historical Period Navigation

The user must be able to choose a previous valid Week, Month or Year through the dynamic selector.

The implementation must not be limited to the current period.

Development may determine the most appropriate UI control consistent with the current CER Route design, such as a select/combobox.

Do not introduce previous/next arrows unless required by the chosen component; the product requirement is the **period selector**, not another navigation model.

The available values must be derived from authorized reportable data / valid report range rather than hardcoded dates.

Tenant and Supervisor scope remain server controlled.

---

# 7. Existing Period Tabs Remain the Primary Grain

Period Type continues to define the main report range:

```text
Week
→ report covers the selected week
→ left panel groups By day

Month
→ report covers the selected month
→ left panel groups By week

Year
→ report covers the selected year
→ left panel groups By month
```

Do not change these grouping semantics.

Reuse the same business-day and period logic already established in RTE09 / Activity Explorer.

---

# 8. Interactive Lower-Left Temporal Groups

The existing lower-left list becomes selectable.

Examples:

## Week

```text
By day

Mon Oct 12
Tue Oct 13
Wed Oct 14
...
```

Selecting:

```text
Mon Oct 12
```

filters the Activity Breakdown to that day.

## Month

```text
By week

Oct 1–4
Oct 5–11
Oct 12–18
...
```

Selecting one week filters the Activity Breakdown to that week.

## Year

```text
By month

January
February
March
...
```

Selecting one month filters the Activity Breakdown to that month.

---

# 9. Default Breakdown Scope

When no temporal subgroup is selected:

```text
Week  → Activity Breakdown = entire selected week
Month → Activity Breakdown = entire selected month
Year  → Activity Breakdown = entire selected year
```

This is the default state after:

- first load;
- changing Supervisor;
- changing Period Type;
- changing the specific Week / Month / Year.

Changing the primary report context must clear any previous subgroup selection.

Do not carry an old day/week/month selection into a different report period.

---

# 10. Selected Group State

When a user selects a temporal group:

- visually identify the selected row;
- keep the main report period visible;
- update the Activity Breakdown to the selected subgroup;
- make the selected subgroup context understandable to the user.

Example:

```text
Main period:
Oct 12–18, 2026

Selected group:
Mon Oct 12

Activity Breakdown:
Mon Oct 12 only
```

The exact highlight treatment must reuse existing CER Route / V0.7 visual patterns.

Do not introduce a visually unrelated component style.

---

# 11. Return to Full-Period Breakdown

The user must be able to return from a selected subgroup to the whole main period.

Required result:

```text
selected subgroup
→ clear selection
→ Activity Breakdown returns to entire Week / Month / Year
```

Development may choose the least intrusive V0.7-compatible interaction, for example:

- an `All` / whole-period row;
- a clear-selection action;
- equivalent established interaction.

Do not force the user to change the Period Type or reload the page just to return to the full report.

---

# 12. KPI Behavior

The four top KPIs remain associated with the **main selected period**, not with the lower subgroup.

Example:

```text
Week Oct 12–18
Total Miles      126.3
Activity Time    4h 15m
Activities       6
Est. Fuel Cost   $0.00
```

If the user selects:

```text
Mon Oct 12
```

the top KPIs **do not change**.

Only the Activity Breakdown changes to the selected day.

This preserves:

- period context at the top;
- drill/detail context at the bottom.

Do not turn the whole page into a day/week/month subreport after selecting a lower-left group.

---

# 13. Activity Breakdown Behavior

Activity Breakdown continues to use the approved RTE09/V0.7 Purpose rows:

- Client Visit
- Employee Visit
- Recruiting
- Check Delivery
- Office
- Other

When no subgroup is selected:

- values represent the full main period.

When a subgroup is selected:

- Miles;
- Time;
- Events;
- Est. Cost

must represent only that subgroup.

All existing anti-duplication rules remain:

- one TripMileage counted once;
- segments do not add extra miles;
- multi-selected Activities do not multiply miles/time;
- visit Purpose remains the visible breakdown dimension.

---

# 14. Reporting Data Contract

Do not create a second reporting model.

Extend/reuse the existing RTE09 server-side reporting contract.

The server must remain authoritative for:

- Supervisor scope;
- business dates;
- Week / Month / Year boundaries;
- subgroup boundaries;
- Official Miles;
- time;
- events;
- Est. Fuel;
- tenant isolation.

The frontend may hold selection state but must not recalculate report facts.

Development may choose whether subgroup data is:

- returned with the primary report payload; or
- requested through a scoped parameter/query.

Choose the approach that best fits the current repository and query cost.

---

# 15. Suggested API Semantics

This section defines required outcomes, not mandatory endpoint syntax.

The reporting contract must be able to express:

```text
Supervisor
Period Type
Specific Period / anchor
Optional subgroup
```

Conceptually:

```text
range = week | month | year
date = authoritative selected period anchor
supervisor_user_id = optional
group = optional selected day/week/month identifier
```

Do not use user-visible labels such as `Mon Oct 12` as authoritative query identifiers if a stable date/range representation already exists.

---

# 16. Period Options

The dynamic selector must not expose another tenant's data.

Period options must be generated within the same authorized reporting scope.

If a valid historical period has no activity:

- selecting it is allowed if it is within the supported report range;
- show the normal empty report state;
- do not fabricate values.

Development may use bounded period-option generation rather than loading an unbounded historical list.

Document the chosen range/strategy in the delivery report.

---

# 17. Supervisor Interaction

Changing Supervisor must:

1. keep the selected Period Type where reasonable;
2. refresh the available specific periods in the authorized scope;
3. clear the lower subgroup selection;
4. reload the KPIs and group list;
5. show Activity Breakdown for the entire selected main period by default.

Do not allow the frontend Supervisor selector to expand server scope.

---

# 18. Period-Type Interaction

Changing:

```text
Week → Month
Month → Year
Year → Week
```

must:

1. switch the specific-period selector to the correct semantic type;
2. choose the corresponding current/default valid period unless the implementation can preserve an equivalent historical anchor safely;
3. clear the lower subgroup selection;
4. reload period KPIs;
5. reload the correct temporal grouping;
6. reset Activity Breakdown to the full selected period.

No stale subgroup may survive a grain change.

---

# 19. Excel Export

This enhancement does **not** change the approved export scope.

Excel continues to export according to:

- selected Supervisor;
- selected main Week / Month / Year.

The temporary lower-left subgroup selection is an **Activity Breakdown exploration filter only**.

Do not silently change Excel to export only the selected day/week/month subgroup.

If future CER requirements need subgroup export, treat that as a separate delta.

---

# 20. Fuel Behavior

Do not change current RTE09 Fuel behavior in this enhancement.

Preserve:

- existing Fuel Estimate formula;
- `waiting_reference`;
- existing visible zero behavior currently approved for waiting Fuel Reference;
- State snapshot;
- Fuel Grade snapshot;
- Fuel Reference matching;
- historical provenance.

This enhancement is about temporal navigation and interactive breakdown only.

---

# 21. Responsive Requirements

## Desktop

Preserve the current RTE09/V0.7 layout.

The new specific-period selector must fit naturally into the existing Supervisor + Week/Month/Year control area.

Do not create unnecessary empty horizontal space or detach the selector from the period controls.

## Mobile

The controls must remain usable at the existing supported mobile width.

Required:

- Supervisor selector visible;
- Period Type visible;
- Specific Period selector visible;
- no horizontal overflow;
- temporal rows remain touch friendly;
- selected row state obvious;
- Activity Breakdown remains readable after selection.

Do not copy the desktop arrangement literally if stacking is required.

---

# 22. Accessibility / Interaction

The interactive lower-left rows must be operable by:

- pointer/touch;
- keyboard where the existing web component model supports it.

Selected state must not rely only on color.

Use correct interactive semantics rather than a visually clickable non-interactive `div` where avoidable.

---

# 23. Security

No authorization changes are required.

Continue using:

- `route.reports.read`;
- `route.reports.export` for Excel.

Subgroup selection must not introduce a new path to retrieve data outside:

- tenant;
- effective Supervisor scope;
- selected authorized period.

Server-side validation remains mandatory.

---

# 24. Edge Cases

Validate at minimum:

1. current Week;
2. previous Week;
3. Week spanning month boundary;
4. Month with partial first/last weeks;
5. previous Month;
6. previous Year;
7. year with months containing no data;
8. empty selected period;
9. All Supervisors;
10. one Supervisor;
11. switch Supervisor while subgroup selected;
12. switch Week → Month while subgroup selected;
13. switch Month → Year while subgroup selected;
14. select a day with activity;
15. select a day with zero activity;
16. select a week inside Month;
17. select a month inside Year;
18. clear subgroup back to full period;
19. multi-Activity execution;
20. pending/unresolved mileage;
21. waiting Fuel Reference;
22. mobile layout;
23. cross-tenant Supervisor identifier attempt;
24. browser reload with a valid selected main period.

---

# 25. Acceptance Criteria

This RTE09 enhancement is ready for CER validation only when:

1. Existing Reports remains visually consistent with V0.7.
2. Week / Month / Year remain present.
3. A specific-period selector exists.
4. Week selector identifies an actual week range.
5. Month selector identifies month + year.
6. Year selector identifies the year.
7. Historical periods can be selected.
8. Server business date/timezone remains authoritative.
9. Week shows By day.
10. Month shows By week.
11. Year shows By month.
12. Lower temporal rows are interactive.
13. Selecting a day filters Activity Breakdown to that day.
14. Selecting a week inside Month filters Activity Breakdown to that week.
15. Selecting a month inside Year filters Activity Breakdown to that month.
16. Default Activity Breakdown represents the whole selected main period.
17. User can return from subgroup to full-period breakdown.
18. Selected subgroup is visually evident.
19. Top KPIs remain for the main period.
20. Changing Supervisor clears subgroup selection.
21. Changing specific main period clears subgroup selection.
22. Changing Period Type clears subgroup selection.
23. Activity Breakdown continues to use Purpose.
24. Official Miles remain sourced from existing shared mileage logic.
25. No mileage/time/event duplication is introduced.
26. Fuel behavior remains unchanged.
27. Excel continues to export the main selected period, not the subgroup.
28. Tenant isolation remains intact.
29. Desktop passes.
30. Mobile passes.
31. No horizontal mobile overflow.
32. Existing RTE09 tests remain green.
33. New tests are discriminating.
34. No unexplained Partial / Gap / Blocked item remains inside this enhancement.

---

# 26. Tests Required

## Period selector

- default current Week;
- select previous Week;
- switch to Month and select another month;
- switch to Year and select another year;
- authoritative date comes from server/report semantics, not browser date.

## Interactive groups

- Week → select day;
- Month → select week;
- Year → select month;
- selected group filters only Activity Breakdown;
- KPIs do not change;
- clear subgroup returns full-period breakdown.

## State reset

- changing Supervisor clears subgroup;
- changing main period clears subgroup;
- changing Period Type clears subgroup.

## Data correctness

- subgroup Miles reconcile with source Trips;
- subgroup Time correct;
- subgroup Events correct;
- subgroup Fuel consistent with existing rule;
- multi-Activity does not duplicate;
- unresolved mileage remains truthful.

## Authorization

- tenant isolation;
- Supervisor scope;
- unauthorized Reports access unchanged.

## Export

- selected main historical period is exported;
- lower subgroup selection does not silently narrow export.

## Browser

- desktop;
- mobile;
- touch/click group selection;
- period selector;
- no overflow;
- selected-state visibility.

Mutation/discriminating coverage must prove that:

- removing subgroup filtering;
- allowing KPI recalculation from subgroup;
- preserving stale subgroup after period change;
- using browser-local date authority

causes tests to fail.

---

# 27. Do Not Change

Do not change:

- RTE09 report architecture;
- V0.7 visual structure beyond the approved controls/interactivity;
- Today / Live;
- Activity Explorer;
- Official Miles definition;
- Fuel Estimate domain;
- Operational State;
- Fuel Grade snapshot;
- Fuel Reference;
- RTE10-A02;
- My Route;
- routing/TomTom;
- odometer/OCR;
- offline/location recovery;
- roles/capabilities.

Do not add:

- charts;
- maps;
- new breakdown dimensions;
- subgroup-specific Excel export;
- new Reports permissions.

---

# 28. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE09_HISTORICAL_PERIOD_INTERACTIVE_BREAKDOWN_REPORT_001.md`

Include:

1. Executive Result
2. Previous vs New UX
3. Specific-Period Selector
4. Week Behavior
5. Month Behavior
6. Year Behavior
7. Interactive Temporal Groups
8. Full-Period vs Subgroup State
9. Activity Breakdown Filtering
10. KPI Preservation
11. Supervisor / Period State Reset
12. API / Read Model Changes
13. Desktop Evidence
14. Mobile Evidence
15. Export Regression
16. Security / Tenant Isolation
17. Tests / Regression
18. Expected → Implemented → Evidence → Gap
19. Remaining Issues
20. Proposed Status

Provide evidence for all three drill cases:

```text
Week → Day → Activity Breakdown
Month → Week → Activity Breakdown
Year → Month → Activity Breakdown
```

Also prove:

```text
subgroup selection changes Breakdown
BUT
top KPIs remain unchanged
AND
Excel still represents the main period
```

---

# 29. Proposed Status Rule

If all acceptance criteria are green:

`RTE09 HISTORICAL PERIOD + INTERACTIVE BREAKDOWN COMPLETE / READY FOR CER VALIDATION`

Development must not declare RTE09 closed.

CER owns final certification.

If a genuinely new product decision is discovered:

`RTE09 ENHANCEMENT BLOCKED — CER DECISION REQUIRED`

with:

`fact → impact → options → recommendation`

---

# 30. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE09_HISTORICAL_PERIOD_INTERACTIVE_BREAKDOWN_REPORT_001.md`

**STOP.**

Do not start another RTE checkpoint.

Wait for CER review and field validation.
