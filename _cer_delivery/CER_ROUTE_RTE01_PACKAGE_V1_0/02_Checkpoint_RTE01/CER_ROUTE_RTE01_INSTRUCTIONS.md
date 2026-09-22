# CER Route — RTE01 Technical Baseline + Target Alignment

## Context

CER Route is beginning formal development using controlled checkpoints.

The approved product baseline is **CER Route V0.7 Updated**. The included V0.7 mockup is the UX/flow reference, subject only to the explicit surgical updates documented in the product baseline.

CER will also provide a separate MD containing lessons learned from another geolocation-based application. That document is technical context only and is not an implementation mandate.

RTE01 must establish a clean technical understanding before CER authorizes development of subsequent checkpoints.

---

## Objective

Produce the end-to-end technical baseline and target alignment required to build CER Route from the approved product definition, while identifying risks, dependencies, open decisions and repository implications.

The result must allow CER to answer:

1. Does the assigned developer/agent correctly understand the product?
2. Is the proposed technical direction capable of supporting the approved flows?
3. What already exists and can be reused, if anything?
4. What needs to be created, adapted, replaced or removed?
5. What material technical decisions require CER approval before implementation?
6. Are geolocation and mileage risks understood before they become embedded in the product?

---

## Scope

### 1. Product alignment

Map the approved product baseline to the technical capabilities that will be required.

At minimum consider:

- Supervisor mobile experience
- Admin responsive experience
- Authentication / identity
- Roles and authorization
- Work Session
- Trip lifecycle
- Change Plan
- Activities and activity-specific data
- Admin-configurable standardized lists
- Vehicle assignment and operational MPG
- Geolocation
- Mileage calculation
- Today / Live
- Activity Explorer
- Reports
- Excel export
- Fuel Reference and historical pricing
- Audit / operational traceability
- Error/recovery behavior
- Data retention considerations
- Testing
- Deployment / runtime considerations

Do not reinterpret or expand the product scope.

### 2. Existing-system / repository assessment

Inspect the repository or project baseline actually provided to you.

Classify relevant components as:

- Reuse
- Adapt
- Migrate
- Replace
- Remove
- New

If CER Route is effectively greenfield, state that explicitly rather than inventing reusable components.

Identify technical debt or inherited assumptions that could conflict with the approved product.

### 3. Proposed technical direction

Propose the technical approach you recommend for the product as a whole.

CER expects the developer and agent to determine the implementation approach. Explain the rationale and relevant tradeoffs, especially where the choice materially affects:

- mobile reliability;
- browser/app lifecycle;
- geolocation behavior;
- privacy;
- security;
- maintainability;
- hosting/runtime;
- operating cost;
- future extensibility.

Do not ask CER to design implementation details that belong to the development team.

### 4. Geolocation + mileage assessment

This is a critical RTE01 area.

Review the external geolocation experience MD supplied by CER and evaluate its lessons against CER Route.

Your report must identify:

- which findings are applicable;
- which findings are not applicable and why;
- which unresolved issues remain relevant;
- what geolocation model you recommend for CER Route;
- how the application should behave when permissions are denied or unavailable;
- expected foreground/background implications;
- browser/mobile OS limitations relevant to the proposed model;
- how location accuracy and anomalous points should be treated;
- how mileage should be derived and what tradeoffs exist;
- whether external routing/map services are needed and why;
- what data must be stored to support traceability without unnecessary tracking;
- privacy/battery/cost implications;
- what should be proven by prototype/technical validation before relying on the design.

Do not simply copy the approach used by the previous application.

### 5. State and lifecycle model

Confirm that the proposed technical model can represent the approved lifecycle, including:

- Start Work
- active work session
- trip purpose
- Start Trip
- On Route
- Change Plan
- Arrived
- activity start
- activity completion
- next task
- Return Home
- End Work
- work session crossing midnight

Identify invalid/ambiguous transitions and propose deterministic handling without changing product intent.

### 6. Data model impact

Identify the logical data domains/entities required to support the product.

This is an assessment, not a request for CER to dictate schema implementation.

At minimum address concepts such as:

- user/supervisor
- role/access
- vehicle
- work session
- trip / route leg
- trip-purpose changes
- activity
- activity type/configuration
- standardized selectable values
- location evidence required by the technical design
- mileage result/evidence
- fuel reference history
- calculated fuel estimate
- operational/audit history

Explain ownership and relationships sufficiently to validate the model.

### 7. Security / privacy / audit

Assess, at minimum:

- authentication;
- server-side authorization;
- Admin vs Supervisor access;
- minimum privilege;
- protection of location data;
- location collection boundaries tied to authorized work activity;
- input validation;
- session handling;
- secrets/configuration;
- auditability of relevant changes;
- tamper/consistency risks around mileage and activity logs;
- logging without unnecessary exposure of sensitive data.

### 8. Mobile and responsive strategy

Evaluate the best implementation approach for:

- supervisor mobile-first workflow;
- minimal interaction while in the field;
- avoiding typing while driving;
- application suspension/resume;
- connectivity loss and recovery;
- responsive Admin desktop/mobile;
- state restoration after browser/app interruption.

The included mockup demonstrates approved product behavior, not required production architecture.

### 9. Fuel reference assessment

Recommend how CER Route should support:

- Regular
- Midgrade
- Premium
- Diesel

Address how reference prices can be stored historically and how a future automated source could be integrated without coupling the core product to one provider.

Do not implement a provider integration in RTE01 unless CER separately authorizes it.

### 10. Testing strategy

Define the test strategy required for later checkpoints, including areas that need device/browser validation rather than only unit tests.

Highlight tests needed for:

- work session lifecycle;
- midnight crossover;
- Change Plan;
- geolocation permissions;
- connectivity loss/recovery;
- mileage calculation;
- responsive behavior;
- role authorization;
- historical aggregation;
- fuel calculations;
- export correctness.

---

## Out of Scope

RTE01 does **not** authorize:

- implementation of RTE02–RTE11;
- redesign of the approved product flows;
- addition of CRM/client catalog;
- route optimization;
- payroll/timecard features;
- fleet maintenance;
- additional unapproved catalogs;
- production fuel-price provider integration;
- silent architecture decisions that materially alter product behavior.

Small technical experiments may be described or performed only when needed to validate a critical feasibility assumption; clearly identify them as validation evidence, not product implementation.

---

## Do Not Change

Do not change the approved V0.7 Updated product decisions, including:

- CER Route remains independent from CER ERP.
- Supervisor is mobile-first.
- Admin supports desktop/mobile.
- Client Visit destination is free text.
- Client Visit Activity is selected after arrival.
- Recruiting Area/Location is free text.
- Employee Visit Employee/Reference is free text.
- Check Delivery Employee/Reference is free text.
- Office is free text.
- Other Area/Location is free text.
- Standardized operational activities/reasons/outcomes remain Admin-managed selections where specified.
- No visible GPS-captured messaging in Supervisor UX.
- Work sessions crossing midnight remain associated with their start-date Work Session.
- Today/Live prioritizes supervisor miles + current/last activity.
- Activity Explorer hierarchy remains Year → Month → Week → Day → Activity.
- Reports remain consolidated and include Supervisor filtering.
- Fuel cost remains an estimate using stored reference pricing/history.

---

## Acceptance Criteria

RTE01 can be considered ready for CER validation when the submitted report:

1. Demonstrates correct understanding of the approved V0.7 Updated product.
2. Documents the actual repository/baseline state without inventing existing capabilities.
3. Maps relevant components to Reuse / Adapt / Migrate / Replace / Remove / New.
4. Presents a coherent end-to-end technical direction and rationale.
5. Explicitly analyzes geolocation and mileage feasibility, limitations and risks.
6. Uses the external geolocation MD as context rather than as an implementation mandate.
7. Identifies security/privacy implications of location data.
8. Identifies the logical data model and lifecycle required by the product.
9. Identifies material decisions that require CER approval.
10. Separates confirmed requirements, findings, recommendations, assumptions and open decisions.
11. Does not start or claim completion of later checkpoints.
12. Provides enough evidence for CER to decide whether RTE01 is Completed / Partial / Blocked / Pending Validation.

---

## Deliverables

Primary deliverable:

`CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT.md`

Supporting evidence may be included when useful, but avoid producing unnecessary documents.

The final report must state one proposed checkpoint status:

- Completed
- Partial
- Blocked

CER will independently validate the status.
