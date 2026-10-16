# CER Route — Product Baseline V0.7 Updated

## 1. Product definition

CER Route is an independent field-operations application focused on capturing the workday, trips, activities, mileage and operational history of field supervisors.

The product must remain intentionally focused. It is not a CRM, payroll system, fleet-management suite, route optimizer or ERP.

The primary product questions are:

- When did the supervisor start and end work?
- How many miles did the supervisor travel?
- What was the purpose of each trip?
- What activity was actually performed at each destination?
- How long did each activity take?
- What is the current / last activity of each supervisor?
- What did the supervisor do by day, week, month and year?
- What is the estimated fuel consumption/cost based on mileage, vehicle MPG and stored fuel reference price?

---

## 2. User experiences

### 2.1 Supervisor

The supervisor experience is **100% mobile-first**.

Design principles:

- minimal taps;
- one primary action at a time;
- avoid scrolling during the operational workflow where reasonably possible;
- do not require typing while the supervisor is driving;
- no visible messages such as “GPS captured” or similar implementation details;
- the application guides the user through the next logical action;
- free text is used only where CER has explicitly chosen not to maintain a catalog.

### 2.2 Administrator

The Admin experience is responsive and usable on desktop and mobile.

Primary areas:

- Today / Live
- Activity
- Reports
- Configuration

Admin Mobile should prioritize the supervisor list immediately instead of consuming screen space with large summary cards.

---

## 3. Core operational sequence

Conceptually:

`Start Work → Select Trip Purpose → Enter/Select Required Pre-Trip Data → Start Trip → On Route → Arrived → Define/Confirm Activity → Start Activity → Complete Activity → Next Task → ... → Return Home → End Work`

A trip and an activity are related but distinct concepts.

- **Trip Purpose** represents why the supervisor is moving.
- **Activity** represents what is actually executed after arrival.

This distinction is essential because a plan may change while in transit.

---

## 4. Work Session

- Supervisor explicitly starts work.
- Supervisor explicitly ends work.
- Arriving home does not automatically end work.
- A work session may cross midnight.
- If a work session begins on one calendar date and ends after midnight, it remains associated with the **Work Session Date on which it started**.

Example:

- Start: Friday 8:00 AM
- End: Saturday 12:41 AM
- Work Session Date: Friday

---

## 5. Trip lifecycle

Minimum logical states/actions:

- Start Trip
- On Route
- Change Plan
- Arrived

`Change Plan` must not destroy the original intent. The system must preserve traceability between:

- original trip purpose;
- revised trip purpose;
- final activity executed.

No visible implementation message about GPS capture is required in the supervisor UI.

---

## 6. Approved activity flows — V0.7 Updated

### 6.1 Client Visit

Before departure:

- Destination — **free text**

After arrival:

- Visit Activity — **Admin-managed selectable list**

Completion:

- Outcome — Admin-managed selectable list
- Note — optional free text

Important: the specific Visit Activity is selected **after arrival**, because the actual management performed may differ from the initial intention.

### 6.2 Recruiting

Before departure / activity setup:

- Area / Location — **free text**
- Recruiting Activity — **Admin-managed selectable list**

All other V0.7 Recruiting behavior remains unchanged.

### 6.3 Employee Visit

- Employee / Reference — **free text**
- Reason — **Admin-managed selectable list**
- Outcome — Admin-managed selectable list

All other V0.7 behavior remains unchanged.

### 6.4 Check Delivery

- Employee / Reference — **free text**
- Delivery Type — **Admin-managed selectable list**
- Received By — Admin-managed selectable list
- Result / Outcome — preserve V0.7 behavior

All other V0.7 behavior remains unchanged.

### 6.5 Office

- Office — **free text**
- Purpose — **Admin-managed selectable list**
- Outcome — preserve V0.7 behavior

All other V0.7 behavior remains unchanged.

### 6.6 Other

- Area / Location — **free text**
- Activity — **Admin-managed selectable list**
- Outcome — preserve V0.7 behavior

The Activity remains selectable specifically to standardize operational reporting.

### 6.7 Home

Home is a special destination used to support the return-home flow. Arriving home must still require an explicit `End Work` action to close the work session.

---

## 7. Admin-managed standardized values

CER intentionally reduced unnecessary reference catalogs.

Admin should maintain operational lists that standardize **what was done**, such as:

- Client Visit Activities
- Recruiting Activities
- Employee Visit Reasons
- Delivery Types
- Office Purposes
- Other Activities
- Outcomes
- Received By

Do **not** require catalogs for:

- Client destinations
- Recruiting areas/locations
- Employee references
- Offices
- Other areas/locations

Those fields are free text in the current approved baseline.

---

## 8. Today / Live

Primary Admin question:

> How many miles has each supervisor traveled today and what is each supervisor doing now?

The main list should emphasize:

- Supervisor
- Miles today
- Current / last activity
- Time / since when

Selecting a supervisor should show a concise summary of that supervisor's activities for the day and provide access to Activity detail.

On Admin Mobile, avoid large KPI cards that push the supervisor list below the fold.

---

## 9. Activity Explorer

Time exploration is hierarchical:

- Year → grouped by Month
- Month → grouped by Week
- Week → grouped by Day
- Day → detailed Activities

Each aggregate level must be exploratory and drill into the next level.

### Day detail

Activities must be clearly separated from one another.

Each activity/event block should expose a concise header including, as applicable:

- activity type;
- reference/destination;
- start/end time;
- duration;
- miles associated with the activity/trip.

The detailed body may show the activity-specific information captured by the approved flow.

---

## 10. Reports

Reports should be consolidated rather than fragmented into many small reports.

Primary filters:

- Period
- Supervisor (All or individual)

Primary aggregated information:

- total miles;
- total time;
- activity count;
- activity distribution / activity time;
- estimated fuel consumption;
- estimated fuel cost.

The report must support an Excel export containing detailed activity-level data for follow-up analysis.

---

## 11. Vehicle and fuel model

Each applicable supervisor can have a configured vehicle with operational data such as:

- Make
- Model
- Year
- Unit / Identifier
- Fuel Grade
- Operational MPG

Supported initial fuel grades:

- Regular
- Midgrade
- Premium
- Diesel

Fuel cost is an **estimate**, not an accounting record.

Conceptually:

`Estimated Gallons = Miles / Operational MPG`

`Estimated Fuel Cost = Estimated Gallons × Reference Fuel Price`

The application must preserve fuel reference history so historical estimates are not silently changed when a new reference price is entered.

The exact source/integration strategy for fuel reference pricing is a technical/product decision to be evaluated; the model must not become tightly coupled to a single data provider without CER approval.

---

## 12. Product boundaries / out of scope for current baseline

Do not turn CER Route into:

- CER ERP;
- CRM/client master;
- payroll/timecard system;
- route optimization engine;
- dispatch suite;
- full fleet maintenance system;
- fuel purchasing/accounting system;
- employee tracking platform outside the authorized work-session purpose;
- messaging platform;
- AI decision engine.

Future extensibility may be considered, but must not inflate V1.

---

## 13. Product governance

CER owns product intent, approved flows, expected behavior and acceptance.

The assigned developer and AI agent own the end-to-end technical implementation proposal and execution.

CER does not prescribe implementation details unless a decision affects product behavior, architecture governance, security, privacy, cost, compatibility or future extensibility.

Any material deviation from this baseline must be surfaced as a decision for CER before implementation.
