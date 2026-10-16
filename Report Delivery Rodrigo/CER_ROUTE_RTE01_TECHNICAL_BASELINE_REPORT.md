# CER Route — RTE01 Technical Baseline + Target Alignment Report

| | |
|---|---|
| **Checkpoint** | RTE01 — Technical Baseline + Target Alignment |
| **Product baseline** | CER Route V0.7 Updated |
| **Repository** | `cermanagementgroup-route`, branch `dev`, commit `1d7c5cc` |
| **Date** | 2026-09-21 |
| **Revision** | **R3.1** — R3 incorporated `CER_ROUTE_RTE01_FINAL_CLOSURE_INSTRUCTIONS.md` (A-1 … A-8, D-01 … D-10); R3.1 applies CER's five documentary corrections (§18.4) |
| **Proposed status** | **Completed — ready for CER certification** |

### Classification labels

Used consistently throughout, and deliberately distinguished so that no
developer recommendation reads as a CER requirement and no delegated choice
reads as an open product question:

| Label | Meaning |
|---|---|
| **Confirmed Requirement / CER Decision** | Approved product rule. Not negotiable by the development team |
| **Technical Decision Delegated to Development** | CER has fixed the *requirement* and handed the *implementation choice* to the team. **Not an open CER decision** |
| **Technical Recommendation** | The development team's proposal. Carries no product authority |
| **Validation Required** | Must be measured on real devices/data before it is relied upon |
| **Repository Finding** | Observed in the repository and verified by execution |
| **Risk** | Something that can go wrong, with severity and mitigation |

> **Revision R3.** CER has closed **every** RTE01 product ambiguity. All eight
> `A-*` items and all ten `D-*` items are now either an approved requirement or
> an explicitly delegated technical decision. **No CER product decision from
> RTE01 remains open.** The decisions are incorporated throughout the document
> rather than appended; the closure matrix is in §18.1 and the required
> consistency answers in §18.2.
>
> **Revision R3.1** applies five documentary corrections requested by CER at
> review: the Recovery Window is now explicit in §8.4 before any event may be
> declared Missing; the notification rule reads *in-platform required, email
> optional additional channel* everywhere; §7.1 persists the Fresh / Degraded
> Cached / Recovered condition explicitly rather than by inference; A-1 is
> scoped so it no longer implies an Activity may attach to a Work Session; and
> absolute durability claims are replaced by a verifiable objective with stated
> boundaries. **No decision was reopened and no code was touched** (§18.4).
>
> Superseded R1/R2 material has been **removed, not annotated**: odometer
> comparison and tolerance, Haversine as an official mileage fallback, the
> email-only notification fallback, the fixed 90-day retention rule, the single
> static tenant fuel price, and the R2 rule that auto-closed an active Activity
> on End Work are all gone from the body of the report.

---

## 1. Executive Summary

### Proposed RTE01 status: Completed — ready for CER certification

The product baseline has been mapped end to end to a technical proposal, the
repository has been inspected and verified by execution, and the geolocation and
mileage problem has been analysed to the point where its real constraints — not
its hoped-for ones — are on the table. No later checkpoint has been started and
no product code has been written.

With CER's final closure decisions applied, **nothing in RTE01 is waiting on
CER**. What remains is implementation and validation work owned by the
development team, scheduled into later checkpoints — which is a different thing
from an unresolved product decision, and is labelled as such throughout.

### Major findings

1. **The repository is a production-proven platform foundation with zero
   business domain.** It provides multi-tenancy, authentication, server-side
   authorization, append-only audit, migrations, pagination, a React/Jinja
   frontend shell and a green test suite. Every CER Route concept — work
   session, trip, activity, vehicle, mileage, fuel — is **New**. This is
   *greenfield domain on a non-greenfield platform*, and that distinction is
   worth roughly two checkpoints of work that do not have to be spent.

2. **The single most consequential technical fact in this checkpoint: a mobile
   web browser cannot track location in the background.** When the screen locks
   or the supervisor switches apps — which is exactly what happens while
   driving — iOS Safari suspends JavaScript timers and geolocation callbacks,
   and Android throttles them. No amount of engineering inside the page changes
   this. Any mileage design that assumes a continuously running GPS trace in a
   web application will fail in the field, quietly, and the failure will look
   like under-reported miles.

3. **The approved UX does not require continuous tracking, and does not require
   a map.** The V0.7 mockup attributes mileage *per leg, at the moment of
   arrival* (`supAction`: miles increase on `start-trip`, `arrive` and
   `arrive-home`, never in between), and contains no cartographic map anywhere —
   all 26 occurrences of "map" in its script are `Array.map`. The product asks
   "how many miles did the supervisor travel", not "draw me the path".
   **CER has since confirmed this as the definition of Miles** (D-02): road
   distance between the `Start Trip` and `Arrived` endpoints, computed by a
   routing service. The technical analysis and the product decision agree.

4. **Offline capture is a design decision, not a later feature.** Field
   supervisors routinely have GPS and no usable data connection. If the
   supervisor's actions are not queued locally and synchronised, the product
   loses work sessions in warehouses and rural industrial parks. This must be
   built into RTE02/RTE03, not appended at RTE11.

5. **The external geolocation document is useful mainly as a list of things
   already paid for once.** Its central lesson — that discarding GPS `accuracy`
   makes every later question about position quality unanswerable — is adopted.
   Its architecture, stack, providers and route-optimization features are not
   applicable and are not carried over.

### Major risks (detail in §13)

| ID | Risk | Severity |
|---|---|---|
| R-01 | Background location is impossible in a mobile browser; the mileage model must not depend on it | **High** |
| R-02 | **Endpoint quality governs mileage quality.** A Degraded or Missing endpoint degrades or prevents the Miles calculation | **High** |
| R-03 | Field connectivity loss causes lost sessions unless offline capture is built in | **High** |
| R-08 | Employee location data carries legal/privacy obligations | **High** |
| R-13 | **In-platform notification does not exist in the Foundation** and is required by D-01 | Medium |
| R-05 | Routing-provider cost, quota, availability and vendor coupling | Medium |
| R-06 | Location spoofing cannot be prevented by any web application | Medium |
| R-14 | **Trips stuck in `Pending Calculation`** if the contingency path is incomplete | Medium |

### CER decisions — all closed

**No CER product decision from RTE01 remains open.** The eighteen items split
three ways (full matrix in §18.1):

| Outcome | Items | Meaning |
|---|---|---|
| **Approved requirement** | A-1, A-2, A-3, A-4, A-6, A-7, A-8, D-01, D-02, D-05, D-06, D-07, D-08 | Fixed product rules, applied throughout this report |
| **Delegated to development** | A-5/D-10, D-03, D-04, D-09 | CER fixed the requirement; the team owns and documents the implementation choice — recorded in §14.2, not as open questions |
| **Superseded and removed** | odometer, Haversine-as-official-fallback, email-only notification, fixed 90-day retention, static fuel price | Deleted from the body of the report, not merely annotated |

The four decisions with the largest engineering consequence:

- **D-02 defines `Miles`** as road distance between the `Start Trip` and
  `Arrived` endpoints via a routing service — not odometer, not GPS trace, not
  straight-line — and gives mileage a four-state lifecycle
  (`Pending Calculation` → `Calculated` / `Not Calculable` / `Calculation
  Failed`) in which a consolidated value is a **historical fact that is never
  silently recalculated**.
- **D-01 defines four evidence levels** — Fresh, Degraded Cached, Recovered,
  Missing — with a silent recovery window, and requires an **in-platform**
  notification channel that the Foundation does not yet have (§8.6.3).
- **D-03 makes the Supervisor experience mobile-only in V1** and delegates the
  client technology to the team.
- **D-07 makes `End Work` a review action**, not a destructive close, and
  **forbids auto-closing an active Activity or inventing an Outcome**.

### Recommendation

**Release RTE02.** Nothing in RTE02 — foundation, access model, navigation,
profiles, vehicles, configuration — depends on any remaining item. The
validations in §8.11 and the delegated technical evaluations in §14.2 run in
parallel, so RTE06 begins with measured facts rather than assumptions.

---

## 2. Sources Reviewed

| Source | Status |
|---|---|
| `00_READ_ME_FIRST.md` | Read first, as instructed |
| `01_Product_Baseline/CER_ROUTE_PRODUCT_BASELINE_V0_7_UPDATED.md` | Read in full — authoritative |
| `02_Checkpoint_RTE01/CER_ROUTE_RTE01_INSTRUCTIONS.md` | Read in full — executable scope |
| `04_Mockup_Reference_V0_7/standalone.html` | Read in full, including the behavioural script |
| `04_Mockup_Reference_V0_7/00_BASELINE_OVERRIDE_NOTICE.md` | Read — surgical field overrides applied |
| `03_Roadmap/CER_ROUTE_MASTER_ROADMAP.md` | Read for direction only; no later checkpoint executed |
| `05_Deliverable_Expected/` (structure + usage rule) | Read and followed |
| `CER_ROUTE_GEOLOCATION_TECHNICAL_CONTEXT.md` (external) | Read **after** the package, as instructed; treated as non-binding context |
| Repository `cermanagementgroup-route` @ `1d7c5cc` | Inspected and **executed** (§16) |
| `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/DOMAIN_EXTENSION_GUIDE.md` | Read — binding engineering invariants for this repository |
| `ARCHITECTURE_BEST_PRACTICES.md` (CER Staffing) | Read — layering and dependency rules adopted |

**Repository Finding — one documentation conflict.** The task prompt names the
deliverable `CER_ROUTE_RTE01_IMPLEMENTATION_REPORT.md`; both
`00_READ_ME_FIRST.md` and the RTE01 instructions name it
`CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT.md`. Per the package's own authority
hierarchy the package wins, so this report carries the package name. Flagged
rather than silently resolved, as the hierarchy requires. No second copy was
produced under the other name, since the package asks to avoid unnecessary
documents.

---

## 3. Product Understanding / Target Alignment

### 3.1 What CER Route is

An independent field-operations application that records **what a field
supervisor did during a workday, where, for how long, and how far they drove** —
and turns that into operational history, live visibility and an estimated fuel
cost.

It answers eight questions (baseline §1), and the technical design is judged by
whether it can answer them, nothing more.

### 3.2 Confirmed Requirements

These are treated as fixed and are not reinterpreted anywhere in this report:

- **Independence.** CER Route does not depend on CER ERP to operate.
- **Supervisor is 100% mobile-first**; minimal taps, one primary action at a
  time, no typing while driving, and **no implementation messaging** such as
  "GPS captured" in the supervisor UI.
- **Admin is responsive**, desktop and mobile; on Admin Mobile the supervisor
  list comes before KPI cards.
- **Trip Purpose ≠ Activity.** Purpose is why the supervisor moves; Activity is
  what was executed on arrival. The plan may change in transit.
- **Change Plan preserves traceability** between original purpose, revised
  purpose and final activity. It does not overwrite intent.
- **Work Session is explicit at both ends.** Arriving home does not end work.
- **A session crossing midnight belongs to its start date.** Friday 08:00 →
  Saturday 00:41 is a *Friday* Work Session.
- **Client Visit Activity is chosen after arrival** — this is a product rule
  about when the choice is made, and the data model must not force it earlier.
- **Free text where CER removed catalogs**: Client destination, Recruiting
  area/location, Employee reference, Office, Other area/location.
- **Admin-managed selectable lists** for what was *done*: Client Visit
  Activities, Recruiting Activities, Employee Visit Reasons, Delivery Types,
  Office Purposes, Other Activities, Outcomes, Received By.
- **Activity Explorer hierarchy**: Year → Month → Week → Day → Activity.
- **Reports are consolidated**, filtered by period and supervisor, with an
  activity-level Excel export.
- **Fuel cost is an estimate**, `Miles / MPG × reference price`, and **fuel
  reference history is preserved** so past estimates do not silently change.

### 3.3 Boundaries honoured

CER Route will not become a CRM, payroll/timecard system, route optimizer,
dispatch suite, fleet-maintenance system, fuel accounting system or messaging
platform. Two specific temptations are refused explicitly in this report:

- **No route optimization.** The external document describes a nearest-neighbour
  planner with a traffic-aware matrix API. CER Route orders nothing and plans
  nothing; a supervisor decides where to go. Not applicable.
- **No client/employee master data.** Destinations and references are free text
  by CER's decision. Nothing in this design turns them into catalogs, and the
  free-text values are deliberately *not* promoted to entities.

### 3.4 Ambiguities raised in RTE01 — all closed by CER

RTE01 surfaced eight genuine gaps in the approved baseline rather than resolving
them silently. **CER has now closed all eight.** None is an open product
question; each is either an approved rule or a fixed requirement whose
implementation is delegated.

| # | Ambiguity as raised | CER's decision | Where it is applied |
|---|---|---|---|
| **A-1** | May a work session start without a trip? | **Yes.** `Start Work` opens the session; a Trip is created only when a displacement actually begins. **No artificial Trip is created just because work started** | §6.2, §6.3 |
| **A-2** | What happens to an in-progress trip when work ends while On Route? | Resolved by **D-07**: End Work is a review action with a `Continue Working` path; only an explicit *End Work Anyway* interrupts the Trip | §6.6 |
| **A-3** | Can several Activities occur at one arrival? | **Yes** — multi-select within the same V0.7 context, executed as one block | §3.5 |
| **A-4** | Is Change Plan available after Arrived? | **No.** Change Plan applies only while `IN_TRANSIT`. After `Arrived` the Trip has reached its destination and any further displacement is a new Trip | §6.4 |
| **A-5** | Which timezone defines the Work Session Date? | Product rule fixed (session belongs to the **local calendar date of `Start Work`**); the time/timezone implementation is **delegated** under D-10 | §6.5, §14.2 |
| **A-6** | May a supervisor have an active session on two devices? | **No.** A second device **transfers/resumes the same active Work Session** — it never creates a second one | §6.6 |
| **A-7** | May an Admin correct a record after the fact? | Resolved by **D-08.2**: Admin-only, through controlled Web Admin actions and backend jobs, fully audited, never silent, never by direct DB editing | §10.6 |
| **A-8** | What is the fuel reference scope? | Resolved by **D-06**: fuel reference varies by **geographic scope, grade and effective date**, with scheduled ingestion. A single static tenant price is explicitly rejected | §11 |

### 3.5 A-3 — Multiple Activities at an arrival (RESOLVED BY CER)

**Confirmed Requirement.** CER has resolved A-3. The approved rule, which
governs every other section of this report:

> One arrival may contain **multiple selected Activities executed within one
> activity execution block**. They share one start time, one completion time,
> one duration, one Outcome and one Notes field. The existing V0.7 workflow
> remains otherwise unchanged.

The approved supervisor flow is:

`Start Trip → On Route → Arrived → Select one or more Activities → Start Activity → Complete / Leave → Outcome → Notes → next approved flow action`

Rules carried into the technical model:

1. `Arrived` ends the travel leg and does **not** auto-start the Activity.
2. After `Arrived` the supervisor selects one **or more** configured Activities
   **from the Activity selector applicable to that existing V0.7 context**. At
   least one is required before `Start Activity`.
3. **Selection never crosses contexts.** A Client Visit offers Client Visit
   Activities; a Recruiting stop offers Recruiting Activities. Multi-select
   widens the choice *within* the context the Trip already established — it does
   not turn the selector into a catalogue of unrelated Activity Types. The
   server validates this and rejects a selection whose values do not belong to
   the Trip's context.
4. `Start Activity` is pressed **once**; the block is closed **once**, through
   the approved `Complete` or `Leave` path.
5. There is exactly one start time and one completion time for the block, and
   duration derives from that single interval.
6. **No per-Activity timer, start action, completion action, Outcome or Notes.**
7. The Outcome step keeps its V0.7 terminology and **its position in the flow**.
8. Notes remain optional, as V0.7 defines them.
9. No additional completion-status field is introduced.

#### Activity restoration (CER decision)

While an Activity block is `IN_PROGRESS` the supervisor **remains in the
Activity execution flow**, and this survives the application being closed:

- Reopening the app **restores the same active Activity state** — this is the
  `GET /worksessions/current` reconciliation of §6.7, and it must land the
  supervisor back on the Activity screen, not on a generic home screen.
- Leaving the Activity requires the approved `Complete` or `Leave` action with
  its Outcome. There is no other exit.
- **`End Work` is not a normal action while an Activity is `IN_PROGRESS`.** If
  the backend exceptionally receives one, it **rejects the invalid transition**
  and returns the authoritative active-Activity state (§6.6).
- The system **never auto-closes the Activity and never invents an Outcome.**

**UX scope is deliberately minimal**: the existing Activity selector changes
from single-select to multi-select. Nothing else in the supervisor experience
changes.

**Terminology constraint.** No new visible concept — no "Activity Group", "Stop
Group" or "Task Group" — enters the supervisor UX. Where this report names an
internal grouping construct (§7.2), it is an engineering detail and carries no
product language.

**Outcome values are tenant-configurable data, not code.** Values such as
"Completed" or "Follow-up Required" appear in the mockup as examples of
configured tenant data and are **never** hardcoded as a business enum (§7.3).
No second completion-status field is introduced.

---

## 4. Existing Baseline / Repository Assessment

### 4.1 What this repository actually is

**Repository Finding.** `cermanagementgroup-route` at commit `1d7c5cc` is a
clean copy of the **CER Application Foundation** — a reusable multi-tenant
FastAPI + PostgreSQL + React monolith base that, in its own words, "brings no
business domain at all". One Alembic migration exists
(`0001_foundation_baseline`), a single head. The fourteen React pages are all
platform administration (login, users, roles, permissions, company profile,
platform diagnostics). There is no work session, no trip, no activity, no
vehicle, no fuel and no geolocation code of any kind.

**So: the CER Route product domain is greenfield. The platform underneath it is
not.** No reusable CER Route component was found or invented.

It is also worth stating for the record that the foundation is *not* CER ERP and
does not link to it. Building on it does not compromise the independence
requirement — it reuses a chassis, not a product.

### 4.2 Component classification

| Component / capability | Current state | Classification | Evidence / note |
|---|---|---|---|
| Multi-tenancy by subdomain, company scoping | Existing | **Reuse** | `get_company_required`; tenant never from client (AGENTS invariant 2) |
| Cookie auth (HttpOnly) + double-submit CSRF | Existing | **Adapt** | `app/core/security/cookies.py:38-55`; 24h token, no refresh — see D-09 |
| Capability catalog + server-side authorization | Existing | **Adapt** | `app/core/rbac/catalog.py` — add `route.*` capabilities |
| Platform-admin boundary (`is_superuser`) | Existing | **Reuse** | Never a tenant permission (invariant 3) |
| `BaseDAO` + uniform `paginate()` | Existing | **Reuse** | `app/core/dao/base.py:113` |
| Optimistic concurrency (`ensure_version` → 409) | Existing | **Reuse** | `app/core/dao/concurrency.py` |
| `BusinessEnum` → enum + DB `CHECK` | Existing | **Reuse** | `app/core/enums.py`; states derive their constraint |
| Append-only audit (`audit_event`, trigger-protected) | Existing | **Reuse** | `app/core/audit/` |
| Transaction boundary (`async with transaction()`) | Existing | **Reuse** | `app/core/db/session.py` |
| Alembic migrations, single head | Existing | **Reuse** | `0001_foundation` |
| `/api/v1` contract, signed webhooks, idempotency | Existing | **Adapt** | `app/core/integration/` — idempotency keys reusable for the offline queue |
| File storage + scanning boundary | Existing | **Reuse** | For generated Excel exports |
| Health, metrics, structured logging, correlation id | Existing | **Reuse** | `app/core/monitoring/` |
| React 19 + Jinja `route → template → page-key` shell | Existing | **Reuse** | No frontend router (invariant 7) |
| Redux Toolkit, Axios, Zod validation, DataTable | Existing | **Reuse** | Admin screens build directly on these |
| Admin sidebar navigation | Existing | **Adapt** | Replace platform menu with Today / Activity / Reports / Configuration |
| Project identity (`APP_*`) | Existing, unset for Route | **Adapt** | Still `"CER Application"` in `app/config.py:91` |
| **Work session / trip / activity / vehicle / fuel domain** | **Absent** | **New** | Entire product domain |
| **Geolocation capture and evidence** | **Absent** | **New** | Zero matches for `geolocation`/`latitude` in the repo |
| **Mileage engine** | **Absent** | **New** | — |
| **Offline capture queue / PWA** | **Absent** | **New** | No service worker, no manifest |
| **Supervisor mobile shell** | **Absent** | **New** | The existing shell is a desktop admin sidebar |
| **Excel export** | **Absent** | **New** | No `openpyxl`/`xlsx` dependency in `pyproject.toml` |
| **Map rendering / tiles** | **Absent** | **Not required for V1** | The approved mockup contains no map (§16) |
| CER ERP coupling | **Absent** | — | Confirms the independence requirement is satisfiable |

Nothing is classified **Migrate**, **Replace** or **Remove**: there is no prior
CER Route system to migrate from, and nothing in the foundation conflicts with
the product.

### 4.3 Inherited assumptions that could conflict with the product

**Repository Finding / Risk.** Four inherited traits of the foundation were
built for a desktop back-office application and meet a mobile field product for
the first time here:

1. **Session lifetime.** `ACCESS_TOKEN_EXPIRE_MINUTES = 1440` with no refresh
   token (`app/config.py:73`). A supervisor who starts at 07:00 Friday and ends
   at 00:41 Saturday is inside the window — but a 24-hour cookie on a phone that
   was last authenticated the previous morning is not. Re-authenticating a
   driver mid-shift is both a UX failure and a data-loss risk. See **D-09**.
2. **Subdomain-mandatory routing.** The app returns 404 without a company
   subdomain. This is correct and should stay, but it constrains how a supervisor
   installs and opens the mobile app (the install must carry the tenant host).
3. **CSRF double-submit + `SameSite=Lax` cookies.** Fine for a same-origin PWA;
   it does become a constraint if CER ever chooses a native wrapper on a
   different origin (see D-03).
4. **Desktop-first frontend shell.** The sidebar layout, `DataTable` and
   pagination primitives serve Admin well and serve the Supervisor not at all.
   The supervisor experience needs its own shell inside the same bundle — not a
   second application, and explicitly not a second frontend framework.

None of these is technical debt in the pejorative sense; they are correct
decisions for the base that need an explicit adaptation for this product.

---

## 5. Proposed Technical Direction

### 5.1 The recommendation in one paragraph

**Technical Recommendation.** Build CER Route as a single modular monolith on
the CER Application Foundation already in this repository: FastAPI + PostgreSQL
+ SQLAlchemy 2 async behind, React 19 + TypeScript served by Jinja in front,
using the existing `route → template → page-key` pattern. Add **two shells in
one bundle** — a mobile-first Supervisor shell and the responsive Admin shell —
and give the Supervisor shell an **offline action queue**. The Supervisor
experience is **mobile-only in V1** (D-03) and its client technology is a
delegated technical decision (§14.2), with an installable PWA as the current
recommendation. Capture location at lifecycle transitions only (never
continuously in the background, which is not possible), and derive `Miles` from
a **routing provider behind an adapter port** — with a routing failure
producing `Pending Calculation` and a bounded retry, **never** a published
straight-line distance (D-02.6).

### 5.2 Why this and not something else

| Alternative | Why not |
|---|---|
| Separate mobile app + separate admin app | Two deployments, two auth surfaces, duplicated domain logic, for one product with one database. The domain is small; the split would cost more than it returns |
| Microservices / event bus | Explicitly prohibited by `AGENTS.md` and unjustified at this size. REST + signed webhooks cover any future integration |
| Native app (Swift/Kotlin) or React Native | Buys background location — the one thing a browser cannot do. Costs an app-store pipeline, device provisioning, a second codebase and a much longer path to V1. The approved mileage model (D-02) does not require background capture, so this buys capability the product does not use |
| Capacitor wrapper around the same React code | A genuine middle option, deferred rather than dismissed: one codebase, with background location available later. Retained as the **escape hatch** if V-1 shows the web platform cannot meet the D-01 acquisition requirements. The choice among these is delegated to development (§14.2) |
| Adding a frontend router / second state manager | Prohibited by repository invariants 7 and the frontend rules; the page-key pattern already works |

### 5.3 Layering

The layering follows `ARCHITECTURE_BEST_PRACTICES.md` exactly, with one
deliberate emphasis: **CER Route has real business rules**, so the Service layer
is not optional here as it is for a CRUD module.

```
Router (thin: request → schema → service → response)
  → Service (work-session rules, trip lifecycle, mileage, fuel estimation)
    → DAO (persistence only, company-scoped)
      → PostgreSQL (constraints, CHECKs, partial unique indexes)
```

Rules enforced: routers never touch SQLAlchemy, DAOs never raise
`HTTPException` and never import FastAPI, cross-table operations run inside
`async with transaction()`, and every business state is a `BusinessEnum` whose
`CHECK` the database derives. Domain DAOs compose; they do not inherit from each
other.

### 5.4 Module layout (backend)

```
app/routers_api/worksessions/     work session lifecycle
app/routers_api/trips/            trips, purpose changes, arrivals
app/routers_api/activities/       activity execution and completion
app/routers_api/vehicles/         vehicle + assignment history
app/routers_api/standardvalues/   admin-managed selectable lists
app/routers_api/fuelreference/    reference prices and history
app/routers_api/tracking/         location evidence intake (write-mostly)
app/routers_api/reporting/        Today/Live, Explorer aggregates, export
```

Each module keeps the prescribed `router.py / schemas.py / models.py / dao.py /
service.py`. `tracking` and `reporting` are the two that will earn their
`service.py` immediately; the rest start thin.

### 5.5 Frontend layout

One bundle, two shells, selected by the page key already carried in
`data-current-page`:

- **Supervisor shell** — full-viewport, single-action screens, bottom nav (My
  Route / Activity / Me), no tables, no sidebar. Mirrors the approved mockup.
- **Admin shell** — the existing sidebar shell, with Today/Live, Activity,
  Reports and Configuration.

Shared: the Axios client, Zod response validation, Redux Toolkit store, and the
existing token-based theming. The supervisor screens are driven by a **client
state machine mirroring the server's** (§6), so the next action is always
computed, never guessed.

### 5.6 Runtime and deployment

**Technical Recommendation.** Keep the existing containerised deployment
(`Dockerfile`, `docker-compose.yml`, GitLab CI already present and configured).
Two runtime requirements are new and non-negotiable:

1. **HTTPS everywhere, no exceptions.** The Geolocation API, service workers and
   PWA installation all require a secure context. A plain-HTTP environment is not
   a degraded environment; it is a non-functional one.
2. **Accurate server time (NTP).** Server time is the audit authority for every
   session and activity boundary (§10).

Backups and point-in-time recovery matter more here than in a back-office app:
mileage history is the product, and it cannot be reconstructed after the fact.

---

## 6. State / Lifecycle Model

### 6.1 Three cooperating state machines

The approved sequence is not one flat machine. Modelling it as one is how
products of this kind acquire impossible states. Three nested machines, each
owning its own transitions:

**Work Session**

```
none ──Start Work──▶ ACTIVE ──End Work──▶ ENDED
```
`ACTIVE` is unique per supervisor (enforced by a **partial unique index**, not by
application logic — repository invariant 6).

**Trip** (only inside an `ACTIVE` session)

```
              Start Trip
PLANNING ─────────────────▶ IN_TRANSIT ──Arrived──▶ ARRIVED ──block completed──▶ CLOSED
   ▲                            │
   └────── Change Plan ─────────┘        (explicit "End Work Anyway" while IN_TRANSIT → INTERRUPTED; see §6.6)
```

**Activity execution block** (one per arrival, inside an `ARRIVED` trip)

```
DEFINED ──Start Activity──▶ IN_PROGRESS ──Complete Activity──▶ COMPLETED
```

Per CER's A-3 decision (§3.5), the block carries **one or more selected
Activities**. The state machine is the block's, not each Activity's: one start,
one completion, one duration, one Outcome, one Notes. Selecting three
Activities does not create three state machines — it creates one block holding
three selections.

### 6.2 Mapping to the approved sequence

| Baseline step | Technical event | State result |
|---|---|---|
| Start Work | `POST /worksessions` | Session `ACTIVE`, vehicle snapshot taken, origin fix attempted. **No Trip is created** (A-1) |
| Select Trip Purpose | Trip created — only when a displacement is actually beginning | Trip `PLANNING` |
| Enter/Select pre-trip data | Trip fields set (free text or standard value per activity type) | Trip `PLANNING` |
| Start Trip | `POST /trips/{id}/start` | Trip `IN_TRANSIT`, departure fix captured |
| On Route | — (a state, not an event) | Trip `IN_TRANSIT` |
| **Change Plan** | `POST /trips/{id}/purpose-changes` | Trip stays `IN_TRANSIT`; **a new `trip_purpose_change` row is appended**; the original purpose is never overwritten |
| Arrived | `POST /trips/{id}/arrive` | Trip `ARRIVED`, arrival endpoint acquired, **mileage calculation enters `Pending Calculation`** (§8.5). Change Plan is no longer available for this Trip (A-4) |
| Define/Confirm Activity | Execution block created with **one or more** selected Activities (Visit Activity chosen *now*, per baseline §6.1; multi-select per A-3) | Block `DEFINED` |
| Start Activity | `POST /activity-blocks/{id}/start` — pressed once | Block `IN_PROGRESS` |
| Complete / Leave | `POST /activity-blocks/{id}/close` — pressed once, with the single Outcome and optional Notes shared by the block | Block `COMPLETED`, trip `CLOSED`, duration derived from the one interval |
| Next Task | New trip | Session still `ACTIVE` |
| Return Home | Trip with purpose `HOME` | Trip `IN_TRANSIT` → `ARRIVED` |
| End Work | `POST /worksessions/{id}/end` | **A review action, not a destructive close** (D-07, §6.6). Rejected outright while an Activity is `IN_PROGRESS` |

This matches the mockup's own machine (`idle → working → pretrip →
route/home-route → arrived → activity → complete → working → home → ended`, with
`change` returning to purpose selection), which is the strongest available
evidence that the model represents the approved product rather than a
reinterpretation of it.

The **only** divergence from the mockup is the one CER approved in A-3: the
mockup's Activity selector is single-select, and the approved behaviour is
multi-select feeding one execution block. The state sequence itself is
unchanged — `arrived → activity → complete` still holds, because the block, not
the individual Activity, owns the states.

### 6.3 A-1 — A Work Session does not require a Trip

**Confirmed Requirement (A-1).** `Start Work` opens the Work Session and
nothing else. A Trip exists only when the supervisor actually begins a
displacement.

> **Do not create an artificial Trip merely because the Work Session started.**

Consequences carried into the model:

- `work_session` has **no mandatory trip**. A session with zero trips is a
  valid, complete record.
- Mileage is a property of Trips. A session without Trips reports zero miles
  because none were driven, not because data is missing — and the two must not
  look alike in reporting.
- Session-level lifecycle events — `Start Work`, `End Work` and their location
  evidence — belong to the session and need no Trip to exist.

**Scope of A-1, stated precisely.** A-1 permits a **Work Session without a
Trip**. It does **not** change the approved Activity lifecycle in any way. The
V0.7 lifecycle is unchanged: an Activity block belongs to an `ARRIVED` Trip
(§6.1, §6.2), and this report does not introduce any path by which an Activity
is recorded directly against a Work Session. A supervisor who never travels
produces a session with no Trips and therefore no Activity blocks — which is a
consequence of the approved lifecycle, not a new one.

This also settles what the origin fix at `Start Work` is *for*: it is session
evidence, **not** a Trip departure endpoint. A Trip's departure endpoint is
acquired at `Start Trip` (D-02.2).

### 6.4 Change Plan: traceability without destruction, and its boundary

**Confirmed Requirement**, and the one place where a naive implementation would
silently break the product. `Change Plan` must **not** be an `UPDATE` of
`trip.purpose`.

```
trip.original_purpose        set once at creation, immutable
trip_purpose_change[]        append-only: (from, to, changed_at, fix)
trip.current_purpose         derived = last change, or original
activity_block.selections    what was actually executed
```

Reporting can then answer all three questions the baseline asks for — what was
intended, what it became, and what was actually done — and a supervisor who
changes plan twice in one leg is recorded honestly. An append-only child table
also means the audit protection the foundation already provides applies
naturally.

**Boundary (A-4).** `Change Plan` exists to handle an unexpected change **while
travelling**, and is therefore available **only while the Trip is
`IN_TRANSIT`**. Once the supervisor presses `Arrived`:

- the Trip has reached its destination;
- `Change Plan` no longer applies to that Trip;
- any further displacement requires a **new Trip**.

The server enforces this: a purpose-change request against a Trip that is not
`IN_TRANSIT` returns `409`. Note this is a different question from *what was
executed on arrival* — that is the Activity, chosen after `Arrived` by design
(baseline §6.1), and it needs no Change Plan to differ from the purpose.

### 6.5 Midnight crossover and time handling

**Confirmed Requirement (D-10).** Every operational event records the real
date/time it occurred, with enough timezone/offset context to reconstruct local
chronology correctly. **A Work Session belongs to the local calendar date on
which `Start Work` occurred**, even when it crosses midnight.

Two further product rules from D-10 that constrain any implementation:

- **Time handling must never block or interrupt** `Start Work`, `Start Trip`,
  `Arrived`, Activity actions or location capture.
- **The supervisor never configures a timezone.** There is no supervisor
  timezone catalogue and no manual timezone assignment in V1.

**Technical Decision Delegated to Development (D-10).** The strategy for server
time, device time, UTC storage, local offset capture, daylight-saving
transitions, clock skew and synchronisation is the team's to design and
document. It is **not** an open CER decision.

**Technical Recommendation** (the team's current design, not a CER rule): store
all timestamps as `timestamptz`; capture the device's UTC offset alongside each
lifecycle event so local chronology is reconstructible; and persist
`work_session.session_date` as an explicit `DATE` computed **once at Start
Work** and never recomputed. Every aggregate — Today/Live, Explorer, Reports —
groups by that column and never by `date(started_at)` in UTC, which is exactly
the bug the rule exists to prevent: a 20:00 EST start is already the next day in
UTC. **Validation Required:** daylight-saving boundaries and a device with a
skewed clock (§12.2).

### 6.6 Invalid and ambiguous transitions

All handling below is now **approved**, not proposed: CER resolved A-2, A-6 and
D-07 in the final closure.

| Situation | Handling |
|---|---|
| Start Work with a session already `ACTIVE` | `409 Conflict`, returning the active session so the client re-syncs. Enforced by a partial unique index |
| Any trip/activity action without an `ACTIVE` session | `409`, never an implicit session creation |
| **Second device opened while a session is `ACTIVE` (A-6)** | **Transfer/resume of the same Work Session.** Never a second session, never duplicated Trips or Activities. The server stays authoritative; the session may move back and forth between devices; pending offline queues from either device reconcile by idempotency key without losing traceability |
| **End Work while a Trip is `IN_TRANSIT` (A-2 / D-07)** | **Not a destructive close.** Present the existing end-of-work review/summary, offering **Continue Working** as the recovery path, which restores the prior active state with full traceability. Only an explicit **End Work Anyway** ends the session: the Trip becomes `INTERRUPTED`, **no artificial `Arrived` is created**, and retained evidence follows D-01/D-02 |
| **End Work while an Activity block is `IN_PROGRESS`** | **Rejected as an invalid transition.** The backend returns the authoritative active-Activity state. The system does **not** auto-close the block and does **not** invent an Outcome. The supervisor closes it through the approved `Complete` or `Leave` path with its Outcome |
| Change Plan after `Arrived` (A-4) | `409` — the Trip is no longer `IN_TRANSIT`; a further displacement is a new Trip |
| Arrive on a trip that is not `IN_TRANSIT` | `409` |
| Duplicate action replayed from the offline queue | **Idempotent**: same idempotency key ⇒ same result, no second state change (reuses `app/core/integration/idempotency.py`) |
| Actions arriving out of order after reconnect | The server orders by the client-supplied monotonic sequence within a session and rejects an event contradicting current state, returning the authoritative state |
| Clock skew on the device | Device timestamp stored as evidence but never trusted for ordering; server timestamp is authoritative |

**On `Continue Working`.** It is a recovery/fallback path, not a normal
lifecycle step, and the model should treat it that way: it restores state rather
than creating any new record, and it is not something the flow ever steers a
supervisor toward.

### 6.7 State restoration

**Technical Recommendation.** The client never owns the truth. On every app
open, resume from suspension, reconnect, **or device transfer (A-6)**, the
supervisor client calls a single `GET /worksessions/current` that returns the
full current state — session, open trip, open activity block and its
selections, and the next legal actions. The UI renders from that. Local state
exists only to survive being offline and is reconciled against this endpoint the
moment connectivity returns.

Two approved behaviours depend on this endpoint being the single source of
truth:

- **Activity restoration (A-3).** If an Activity block is `IN_PROGRESS`, the
  supervisor is returned to the Activity execution screen, not to a generic
  home screen, and can leave it only through `Complete` or `Leave`.
- **Device transfer (A-6).** A second device calling this endpoint receives the
  same active session and resumes it, which is what makes "transfer, never
  duplicate" true in practice rather than merely intended.

This is what makes "the application guides the user through the next logical
action" (baseline §2.1) true after an interruption, not just on a happy path.

---

## 7. Data / Domain Model

### 7.1 Logical entities

All entities are company-scoped (`company_id`), per repository invariant 2.

| Entity | Owns | Key fields | Notes |
|---|---|---|---|
| `users` (existing) | Identity | — | Supervisor = a user with the supervisor role. **No parallel person table** (invariant 9) |
| `supervisor_profile` | Field-work attributes | `user_id`, active vehicle | Thin extension, not a copy of the user |
| `vehicle` | Vehicle master | make, model, year, unit, `fuel_grade`, `operational_mpg`, `version` | MPG is *operational*, an input to an estimate |
| `vehicle_assignment` | Who drove what, when | `vehicle_id`, `user_id`, `effective_from/to` | History, so a past session resolves to the vehicle actually used |
| `work_session` | The workday | `session_date` (DATE), `started_at`, `ended_at` (tz-aware), `status`, `vehicle_id`, **`mpg_snapshot`**, `utc_offset` | `session_date` never recomputed (§6.5). **Zero trips is valid** (A-1) |
| `trip` | One leg | `work_session_id`, `original_purpose`, `current_purpose`, free-text reference, `status`, `started_at`, `arrived_at`, `departure_fix_id`, `arrival_fix_id` | Purpose is a `BusinessEnum` with a DB `CHECK`. **Distance lives on `mileage_result`, not here** — a Trip may exist before its mileage is resolved |
| `trip_purpose_change` | Change Plan trace | `trip_id`, `from_purpose`, `to_purpose`, `changed_at` | **Append-only** |
| `activity_block` | One execution block per arrival | `trip_id`, `type`, `started_at`, `completed_at`, `outcome_value_id`, `note` | **One** start, completion, duration, Outcome and Notes — per A-3 (§3.5). Duration derived, not stored twice. Internal name only; never surfaced in the supervisor UX |
| `activity_selection` | The Activities chosen for that block | `activity_block_id`, `standard_value_id`, `sort_order` | **One or more rows per block.** This is what makes multi-select work without duplicating timing or Outcome |
| `activity_detail` | Type-specific fields | `activity_block_id`, `field_code`, `text_value` \| `standard_value_id` | See §7.2 |
| `standard_value` | Admin-managed lists | `list_code`, `label`, `sort_order`, `is_active`, `version` | See §7.3 |
| `location_fix` | Location evidence | `work_session_id`, `trip_id`, `event_kind`, `latitude`, `longitude`, **`accuracy_meters`**, **`evidence_level`**, `device_captured_at`, `server_received_at`, `source`, `age_seconds`, `recovered_after_seconds`, `is_anomalous` | **Append-only**, §8. **`evidence_level` is persisted, never inferred** — see the note below |
| `missing_location_event` | Confirmed absence of location evidence | `work_session_id`, `trip_id`, `event_kind`, `occurred_at`, `reason_code`, `attempt_evidence`, `last_known_fix_id`, `notification_status` | **Append-only**, per D-01 (§8.6.2). Grouping for notification never deletes a row |
| `mileage_result` | The `Miles` fact and its provenance | `trip_id`, `state`, `meters`, `provider`, `method_version`, `departure_fix_id`, `arrival_fix_id`, `calculated_at`, `terminal_reason`, `terminal_at` | **The four-state lifecycle of D-02.10 lives here** (§8.5). Once `Calculated`, it is a **historical fact and is never automatically recalculated** (D-02.8) |
| `fuel_reference_price` | Price history | `fuel_grade`, `price_per_gallon`, `effective_from`, `geographic_scope`, `source`, `ingested_at` | **Never updated in place**; varies by scope, grade and date (D-06), §11 |
| `fuel_estimate` | The estimate and what produced it | `work_session_id` or `trip_id`, `state`, `gallons`, `cost`, `fuel_reference_price_id`, `mpg_used`, `calculated_at` | `Pending Calculation` when no applicable price exists (D-06). Provenance persisted so a later price change cannot alter history |
| `record_correction` | Admin post-close corrections | `target_type`, `target_id`, `original_value`, `corrected_value`, `reason`, `admin_user_id`, `requested_at`, `job_status` | **Append-only**, per D-08.2 (§10.6). No silent or automatic historical change |
| `audit_event` (existing) | Change history | — | Reused as-is, trigger-protected |

#### Persisting the evidence level (D-01, aligned with §8.6.1)

**Confirmed Requirement.** The Fresh / Degraded Cached / Recovered condition of
a fix is **stored explicitly at write time**, as a first-class column, and is
**never reconstructed later by inference**.

| Column | Type | Purpose |
|---|---|---|
| **`evidence_level`** | `BusinessEnum` with a DB `CHECK` — `fresh`, `degraded_cached`, `recovered` | **The authoritative condition.** Set by the acquisition stage that produced the fix (§8.4), and immutable thereafter |
| `source` | text | Provenance: which mechanism produced the coordinate |
| `age_seconds` | int, null for `fresh` | Staleness of a cached point at the moment it was used |
| `recovered_after_seconds` | int, null unless `recovered` | Gap between the lifecycle event and the actual capture, so a Recovered Point never appears to have been captured at the event |
| `device_captured_at` | `timestamptz` | The **true** capture time — never restamped to the event |
| `server_received_at` | `timestamptz` | When the server received it |

Why this is a requirement and not a modelling preference: inferring the level
afterwards from `age_seconds` or timestamps would mean re-deriving a judgement
that was made under acquisition-time conditions the database no longer has —
which thresholds were configured, which paths had been exhausted, whether the
recovery window was still open. A later change to any of those would silently
reclassify historical evidence. Writing the level once, at the moment the
decision is actually made, is the only way "a cached or recovered point is
never represented as Fresh" (§8.6.1) stays true for the life of the record.

`Missing` is **not** a value of `evidence_level`. Missing means no fix exists,
so it is represented by the absence of a `location_fix` together with the
presence of a `missing_location_event` row (§8.6.2) — which is also why
`evidence_level` is non-nullable: every stored fix has a known condition.

The `mileage_result` rows that consume these endpoints carry the endpoint
references (`departure_fix_id`, `arrival_fix_id`), so the provenance of a
`Miles` figure — including whether it was computed from a Degraded or Recovered
endpoint — remains auditable without recomputing anything (D-02.3, D-02.8).

### 7.2 Activity-specific fields: one decision worth explaining

Six activity types each capture a different pair of fields. Two viable shapes:

- **(a) A table per activity type** — explicit columns, trivially queryable,
  six near-identical modules, and a migration every time CER adjusts a field.
- **(b) One `activity_block` + a narrow `activity_detail` key/value child** —
  one module, no migration to adjust a field, at the cost of slightly heavier
  reporting queries and validation moved into the service layer.

**Technical Recommendation: (b), with the field set declared in code.** Each
activity type declares its fields (code, free-text vs standard list, required)
in a single Python declaration — the same "one source of truth" discipline the
repository already applies to the capability catalog. The service validates
against that declaration, the database holds a `CHECK` on the type, and the
Excel export reads the declaration to build its columns. This keeps the *product
rule* ("Visit Activity is a list, destination is free text") in one readable
place rather than spread across six schemas, and it keeps the six approved flows
from turning into six copies of the same code.

This is an implementation choice, not a product change: the approved fields,
their types and their timing are exactly as the baseline specifies.

### 7.3 Standardized lists

**Technical Recommendation.** One `standard_value` table keyed by a `list_code`
enum holding the eight approved lists (Client Visit Activities, Recruiting
Activities, Employee Visit Reasons, Delivery Types, Office Purposes, Other
Activities, Outcomes, Received By). The list codes are closed and live in code;
the *values* are company-owned data an Admin edits.

Two properties the product needs:

- **Retiring a value must not rewrite history.** Values are deactivated
  (`is_active = false`), never deleted; an activity keeps its `standard_value_id`
  forever. A report from March must still say what it said in March.
- **No catalog is created for the free-text fields.** The five fields CER
  deliberately freed (destination, recruiting area, employee reference, office,
  other area) are stored as text on `activity_detail` and are **not** promoted to
  rows in `standard_value`, no matter how repetitive they look. Doing so would
  reintroduce exactly the catalogs CER removed.
- **Outcome is tenant data, never a business enum.** Per CER's A-3 closure
  (§3.5), values like "Completed" or "Follow-up Required" are *examples of
  configured tenant data* visible in the mockup. They are rows in
  `standard_value`, never members of a `BusinessEnum` and never seeded as
  universal product values. This is the one place in the model where the
  otherwise-standard "closed states live in code" rule is deliberately **not**
  applied, because CER has defined these as configurable.
- **Activity values are broad operational classifications**, not detailed tasks
  or independent workflows. The six V0.7 activity contexts remain
  system-defined: no new configurable Activity Types and **no dynamic form
  builder** (explicitly out of scope per CER's closure §2.4).
- **A-3 changes nothing else.** Reason, Delivery Type, Purpose, Received By and
  the free-text references keep their approved single-value semantics. Only the
  fields the baseline defines as an *Activity selector* become multi-select.

### 7.4 Ownership and relationships

```
company
 └── user ──── supervisor_profile ──── vehicle_assignment ──── vehicle
       └── work_session (1 active max)
             ├── trip (n, ordered)
             │     ├── trip_purpose_change (n, append-only)
             │     ├── activity_block (0..1 per arrival — one block)
             │     │     ├── activity_selection (1..n)  ◀── A-3: multi-select
             │     │     └── activity_detail (n)
             │     ├── location_fix (n, append-only)
             │     └── mileage_result (1 — the Miles fact + its state)
             ├── location_fix (session-level: start/end)
             ├── missing_location_event (n, per D-01)
             └── fuel_estimate (derived; Pending until a price applies)
company
 ├── standard_value (n)
 ├── fuel_reference_price (n — by scope × grade × effective date)
 └── record_correction (n, append-only, Admin-initiated)
```

**On A-3 cardinality:** there is at most one *execution block* per arrival, and
that block holds **one or more** selected Activities. The multiplicity CER
approved lives on `activity_selection`, which is precisely what keeps one start
time, one completion, one Outcome and one Notes intact while allowing several
Activities to be recorded for the stop.

**On the fuel estimate (revised in R3).** In R1/R2 this report treated the
estimate as purely derived at read time. CER's D-06 decision changes that: the
estimate has a **state** (`Pending Calculation` when no applicable price
exists) and must **persist the provenance** of the price actually used, so a
later price update cannot alter a historical estimate. It is therefore a thin
persisted record of *what was computed and from what*, not a second copy of the
inputs — which keeps invariant 9 intact while satisfying D-06's historical
integrity requirement (§11).

### 7.5 Indexing, driven by the actual queries

| Query the product asks | Index |
|---|---|
| Today/Live: all supervisors' miles + current activity, today | `(company_id, session_date, status)` on `work_session` |
| Explorer: a supervisor's year/month/week/day | `(company_id, user_id, session_date)` |
| One active session per supervisor | **Partial unique** on `(company_id, user_id) WHERE status = 'active'` |
| Fuel price effective on a date | `(company_id, fuel_grade, effective_from DESC)` |
| Evidence for a trip | `(trip_id, device_captured_at)` on `location_fix` |

The partial unique index is the one that matters most: it is the difference
between "we check for a duplicate session in Python" and "a duplicate session
cannot exist" (invariant 6).

---

## 8. Geolocation + Mileage Assessment

This is the section RTE01 exists for. It is also where CER Route is most likely
to make an expensive, irreversible mistake, because the wrong mileage model does
not fail loudly — it under-reports for months.

### 8.1 Lessons applied from the external experience document

| Lesson | Why it applies to CER Route | How it is applied |
|---|---|---|
| **`accuracy` was requested and never stored**, making every later quality question unanswerable (ext. §5, §19.2) | CER Route's positions are *evidence for mileage*, so their quality is a first-class concern | `accuracy_meters` stored on **every** fix from day one, with a rejection/flagging threshold |
| **Degrade instead of break** — the source app's Haversine fallback behind its routing API (§21) | The *principle* applies — a field app that stops dead when an API is down is worse than one that copes. The *mechanism* does not | **Adopted in spirit, rejected in form.** CER's D-02.6 forbids publishing straight-line distance as official `Miles`. Instead the workflow degrades (the Trip saves normally, mileage goes to `Pending Calculation` and retries) while the *number* refuses to degrade. Haversine survives only as an internal plausibility check |
| **Identity, tenant and timestamps from the server, never from the request** (§12) | Identical to this repository's invariant 2 | Already enforced by the foundation |
| **No offline capture is the gap most likely to hurt a field application** (§14) | Warehouses and rural industrial parks are CER Route's normal working environment | Offline queue in scope from RTE03, not deferred |
| **Per-tenant quotas with 80%/100% warnings for paid APIs** (§21) | A routing provider bills per call; a bug can drain a quota overnight | Quota + alerting around the routing adapter |
| **A diagnostics screen showing provider configuration and reachability** (§21) | Silent degradation is the enemy; a missing API key must be visible, not inferred | Extends the existing platform diagnostics page |
| **Capture both device and server timestamps** (§21) | Offline-queued actions arrive late by design; without both, a delayed sync is indistinguishable from a late action | Both stored on every fix and every queued action |
| **Never transport coordinates as locale-formatted strings** (§12) | The same bug class exists in JS/JSON (`41,40338`) | Coordinates travel as JSON numbers, stored `numeric`, never parsed from a localized string |
| **Separate acquisition from visualization** (§2) | Keeps the provider swappable | Adapter port; nothing else knows the provider's name |
| **A web app cannot verify a real position** (§15) | CER must not be told otherwise | Stated plainly in §10.4 |

### 8.2 Lessons NOT applicable, and why

| Lesson / element | Why it does not carry over |
|---|---|
| Route optimization, nearest-neighbour ordering, matrix API (§9) | CER Route is explicitly **not** a route optimizer (baseline §12). The supervisor decides where to go |
| TomTom Search / Google Places / Nominatim / Overpass discovery (§2) | These serve lead generation and CRM enrichment. CER Route has no client master and no lead concept |
| Leaflet, OSM tiles, marker icons (§10) | **CER Route V1 needs no map.** The approved mockup contains none (§16). Tile usage policies and CDN fragility are simply out of scope |
| ASP.NET Web Forms / `__doPostBack` constraints (§19.15) | Different stack; the constraint does not exist here |
| **Location optional by default** (§3, §21) | Defensible when position merely decorates a sales visit. In CER Route, position *is* the mileage. **CER resolved this in D-01**: acquisition is high-priority best-effort with fallback, failure never blocks the supervisor, and every failure is recorded and notifiable — the opposite of the source app, where a lost position was simply a `NULL` nobody saw |
| **One-shot capture as sufficient** (§21) | Sufficient for a check-in stamp; insufficient alone to answer "how many miles". CER Route needs endpoint capture **plus** a distance derivation (§8.5) |
| Reverse geocoding (§11) | Built and never called in the source app. CER Route's destinations are free text and no screen displays a resolved address. Not building it is the lesson |

### 8.3 The platform constraint that drives every other decision

**Confirmed technical constraint — not an opinion.** In a mobile web browser:

| Situation | What actually happens |
|---|---|
| Foreground, screen on | `getCurrentPosition` and `watchPosition` work |
| Screen locked | **iOS Safari suspends the page.** Callbacks stop. No fixes |
| Switched to another app (navigation, phone call) | Backgrounded; iOS suspends, Android throttles heavily |
| Browser closed | Nothing runs |
| Service worker installed | Service workers **cannot** access the Geolocation API. They enable offline caching and background *sync*, not background *location* |
| PWA installed to home screen | Improves lifecycle and storage durability. **Does not** grant background location |

A supervisor who is driving has the phone locked, pocketed, or running
navigation. **That is precisely when a browser cannot capture location.** Any
design assuming otherwise will report a fraction of real miles and will be
discovered late, in production, by a supervisor disputing their mileage.

### 8.4 Recommended geolocation model

**Confirmed Requirement (D-01, resolved by CER).** The governing rule, which
this whole section implements:

> Location capture is a high-priority best-effort requirement. CER Route
> attempts current location first, may use technically valid
> last-known/cached fallback evidence when available and acceptable, and
> continues trying silently inside a short **recovery window** before any event
> is declared Missing. If usable location still cannot be obtained, the
> supervisor workflow continues silently and the system records the
> reason/evidence as a **Missing Location Event**. Configured back-office
> recipients are notified through **in-platform notification — the required
> channel — with email as an optional additional channel**. Missing or degraded
> evidence is never fabricated or silently treated as authoritative mileage
> evidence.

**Technical Recommendation — "evidence at transitions, not surveillance".**

1. **One-shot capture at lifecycle transitions only**: Start Work, Start Trip,
   Arrived, Complete Activity, End Work. These are moments when the supervisor
   is stopped, holding the phone, app in foreground — exactly the conditions
   under which browser geolocation is reliable.
2. **Opportunistic foreground breadcrumbs** while a trip is `IN_TRANSIT` *and*
   the page is visible: low-frequency `watchPosition` (≈60 s / 250 m
   displacement filter). **Corroboration, never the primary mileage source** —
   precisely because their availability is unpredictable.
3. **Silent to the user.** No "GPS captured" messaging (baseline §2.1, §5).
   Capture is a side effect of an action the supervisor already took, so it
   never adds a tap.
4. **Never outside an active work session.** The server rejects any fix not
   belonging to an `ACTIVE` session (§10.3) — a hard privacy boundary enforced
   where the supervisor does not have to trust the client.
5. **Every fix stores its full provenance** — latitude, longitude,
   `accuracy_meters`, `device_captured_at`, `server_received_at`, `event_kind`,
   `source`, `age_seconds` when the fix is cached/last-known, and its
   degraded/anomalous status. A cached fix is **never** represented as a fresh
   one, and coordinates are **never** fabricated.

#### Staged acquisition (D-01)

The design must support a staged, best-effort strategy, and **all** of its
stages must be exhausted before an event may be classified as `Missing`:

1. **Fresh Point** — attempt to obtain a current usable location for the
   lifecycle event.
2. Exhaust the normal/current-location acquisition paths defined by the
   implementation.
3. **Degraded Cached Point** — if current acquisition fails, a technically
   available last-known/cached position may be evaluated as fallback, and used
   **only** when it satisfies the applicable freshness and accuracy criteria.
   It is stored with its real age and provenance.
4. **Recovery Window** — if no valid endpoint exists at the event, CER Route
   **may continue trying silently inside a short recovery window**. This stage
   is mandatory in the model, not optional: an event may not be declared
   `Missing` while the recovery window is still open.
5. **Recovered Point** — if recovery succeeds, persist the point actually
   recovered with its **actual** capture timestamp and metadata. It is never
   restamped to the lifecycle event and never presented as Fresh.
6. **Missing** — only after current acquisition, approved cached fallback
   **and** recovery have all been exhausted does the event become `Missing`:
   **the operational action still proceeds**, and a confirmed **Missing
   Location Event** is recorded (§8.6.2).

These six stages produce exactly the four evidence levels of §8.6.1 — Fresh
(stage 1-2), Degraded Cached (stage 3), Recovered (stages 4-5) and Missing
(stage 6) — and the level reached is persisted explicitly on the fix (§7.1),
never inferred afterwards.

**The exact retry algorithm, API choices, retry count, timings, freshness
thresholds, cache implementation and the recovery-window duration are
deliberately left to implementation and technical validation** (V-1, V-2), per
CER's instruction not to hardcode an algorithm at RTE01. What RTE01 fixes is
the *behaviour and its constraints*: try hard, exhaust recovery before
declaring Missing, degrade honestly, never block the supervisor, never invent a
coordinate.

Indicative starting parameters for that validation — not a specification:
`enableHighAccuracy: true`, a bounded timeout, and `maximumAge` used
deliberately rather than by accident, with a fast coarse fix accepted
immediately so the UI is never blocked and upgraded if a better one arrives.
**A supervisor must never wait on a GPS lock to start the day.**

### 8.5 Mileage — the approved model (D-02)

**Confirmed Requirement (D-02.1).** `Miles` means:

> **Road distance calculated between the Trip departure and arrival endpoints
> using a routing service.**

It explicitly does **not** mean odometer mileage, continuous GPS-trace mileage,
or straight-line distance.

This closes what R1/R2 left open. The alternatives that report previously
compared — a continuous GPS trace, a straight-line fallback, and odometer
reconciliation — are **no longer candidates** and have been removed rather than
annotated. The remaining analysis is about making the approved definition work
reliably.

#### 8.5.1 Endpoints (D-02.2, D-02.3, D-02.4)

| Rule | Detail |
|---|---|
| **Authoritative endpoints** | departure = the coordinate associated with `Start Trip`; arrival = the coordinate associated with `Arrived` |
| **Never used as endpoints** | free-text destination, inferred address, client master data, or any unrelated event |
| **Degraded endpoints** | A Degraded/cached/last-known point may serve as an endpoint **only** after all normal acquisition paths were exhausted **and** it meets the approved freshness and accuracy rules. Its degraded provenance is preserved on the result |
| **Recovery** | If no valid point exists at `Start Trip` or `Arrived`, CER Route may keep trying **silently** within a short recovery window; a Recovered Point keeps its real timestamp, accuracy and provenance and is never presented as captured at the event |
| **Exhausted** | If a required endpoint is still Missing: **do not fabricate it**, do not infer it from destination text, and do not borrow a point from the next Trip or an unrelated event. The Trip cannot produce normal calculated mileage from that missing endpoint |

The last row is the one that keeps the number honest. A fabricated endpoint
would produce a plausible-looking mileage figure that is simply untrue, and it
would be indistinguishable from a real one afterwards.

#### 8.5.2 Breadcrumbs are supporting evidence only (D-02.5)

Foreground/opportunistic breadcrumbs (§8.4) support diagnostics, anomaly
detection, validation and later administrative review. They **do not
automatically modify, replace or become** the authoritative `Miles` value in
V1. Where R2 proposed that breadcrumbs reconcile or adjust the routed distance,
that is superseded.

#### 8.5.3 Routing failure and plausibility (D-02.6, D-02.9)

**Straight-line/Haversine distance is never published as official `Miles`.** If
valid endpoints exist but the routing service cannot return a valid road
distance, the Trip is **saved normally**, mileage is set to `Pending
Calculation`, and the approved backend contingency strategy retries. Haversine
may be used **internally only**, for diagnostics or plausibility checks, if
development finds it useful.

Before any routing result is consolidated as the historical fact, it must pass
plausibility validation. If the result is anomalous, incoherent or technically
suspicious, it is **not** consolidated: the retry/fallback/contingency path
continues until a valid result or a terminal exception is reached, and no
fabricated or straight-line value is substituted. **Validation Required** —
exact anomaly thresholds belong to development and device/data validation.

#### 8.5.4 Mileage calculation lifecycle (D-02.10)

```
                 ┌─────────────────────► Calculated        (terminal, success)
                 │
Pending Calculation ──────────────────► Not Calculable     (terminal, exception)
  (transitory only)│
                 └─────────────────────► Calculation Failed (terminal, exception)
```

| State | Meaning |
|---|---|
| **`Pending Calculation`** | **Transitory only.** The system still has an automatic path to resolve the calculation |
| **`Calculated`** | Terminal success. A valid road distance has been consolidated as the historical fact |
| **`Not Calculable`** | Terminal exception. Required endpoints/data remain insufficient after acquisition, fallback and recovery were exhausted |
| **`Calculation Failed`** | Terminal exception. Endpoints were sufficient, but routing could not produce a valid result after the approved retry/fallback/contingency mechanisms were exhausted |

Rules that constrain the implementation:

- **No Trip may remain in `Pending Calculation` indefinitely.** Every Trip must
  reach a terminal state. This needs a bounded contingency policy and a sweeper
  — the existing `PlatformScheduler` (§16) is the natural home for it — and it
  is tracked as **R-14** because an incomplete contingency path is exactly how
  "pending forever" happens in practice.
- Terminal exceptional states retain the reason, the terminal/closure
  timestamp, the available evidence, full audit traceability, and back-office
  notification where applicable.
- **`Degraded` is quality/provenance metadata, not a fifth state.** A
  `Calculated` result computed from a Degraded endpoint is still `Calculated`;
  its degraded provenance travels with it on `mileage_result`.
- The terminology is exactly as approved: **`Not Calculable`**, never a vaguer
  "Unavailable".

#### 8.5.5 A calculated value is a historical fact (D-02.8)

Once consolidated, `Miles` **must not be automatically recalculated**. The
result persists its value, routing provider, calculation method/version,
endpoint references and provenance, and calculation timestamp — enough to audit
it years later.

A later change of provider, map data, algorithm or configuration must **not**
silently alter historical Trips. The only route to changing a consolidated
value is an explicit, audited Admin correction under **D-08.2** (§10.6).

**Repository Finding — this is already how the base thinks.** Append-only audit
and trigger-protected history tables exist (`app/core/audit/`), so "corrections
add rows, they never edit them" is the established pattern here rather than a
new discipline to invent.

### 8.6 Accuracy and anomaly handling

**Technical Recommendation** — thresholds to be confirmed by the §8.11
measurements rather than assumed:

| Condition | Handling |
|---|---|
| `accuracy <= 50 m` | Accept as a normal fix |
| `50 m < accuracy <= 200 m` | Accept, **flag low confidence**; mileage marked reduced-confidence |
| `accuracy > 200 m` | Store as evidence, **exclude from mileage**, flag the leg |
| Coordinates out of valid range, or far outside the company's operating region | **Reject at the API boundary** (the source app stored anything it was sent — ext. §15) |
| Implied speed between consecutive fixes > 200 km/h | Store, mark `is_anomalous`, exclude from distance |
| Cached / last-known fix used as fallback | Store **with its real age and provenance** as a **Degraded Cached Point** (§8.6.1); endpoint eligibility per D-02.3 |
| Valid fix obtained inside the recovery window | Store as a **Recovered Point** with its **true** capture timestamp — never restamped to the event (§8.6.1) |
| No usable fix after acquisition, fallback **and** recovery are exhausted | **The action still succeeds.** Record a **Missing Location Event** (§8.6.2); the affected endpoint yields no normal mileage (§8.5.1) |

#### 8.6.1 The four evidence levels (D-01)

**Confirmed Requirement.** CER approved a four-level model, used consistently
throughout this report. It supersedes the simpler two-condition model of R2.

| Level | What it is | Stored | Eligible as a mileage endpoint? | Alerts? |
|---|---|---|---|---|
| **1. Fresh Point** | Obtained normally for the lifecycle event | Full fix + provenance | **Yes** | No |
| **2. Degraded Cached Point** | Last-known/cached evidence used **only after** normal acquisition paths were exhausted, and only when it meets the approved freshness/accuracy rules | Full fix, explicitly marked **Degraded**, with real age and provenance | **Only** under D-02.3 (paths exhausted first, rules satisfied); degraded provenance preserved | No automatic alert |
| **3. Recovered Point** | A valid point obtained shortly **after** the event, inside the approved recovery window | Full fix with its **true** capture timestamp and provenance | Yes, per D-02.4, carrying its recovered condition | No automatic alert |
| **4. Missing** | No acceptable evidence after acquisition, fallback **and** recovery were all exhausted | No coordinates — **never fabricated**. A `missing_location_event` instead | No — the Trip cannot produce normal calculated mileage from this endpoint | **Yes** — eligible for back-office notification |

Three rules bind all four levels:

- **A cached or recovered point is never represented as Fresh.** The level is
  **persisted explicitly** on the fix as `evidence_level` at the moment of
  acquisition (§7.1) — never re-derived afterwards — and it travels with the
  fix into every downstream use.
- **A Recovered Point never claims to have been captured at the event.** Its
  real capture time is preserved, and the gap between event and capture is
  visible.
- **Coordinates are never fabricated**, at any level, for any reason.

`Degraded` is **quality/provenance metadata** — on the fix and, when it
propagates, on the mileage result. It is never a mileage state (§8.5.4).

#### 8.6.2 Missing Location Event

**Confirmed Requirement.** When location is definitively missing, CER Route
retains a back-office record sufficient to understand what happened, able to
identify as applicable: tenant/company; supervisor; Work Session; the Trip
and/or lifecycle event affected; the event kind (`Start Work`, `Start Trip`,
`Arrived`, …); the event timestamp; a failure/reason code **based only on what
the platform can actually determine**; the technical evidence from the
acquisition attempts; last-known/degraded fix information where relevant; and
notification status.

**No failure cause is invented.** Browsers expose a coarse error model
(permission denied / position unavailable / timeout) and cannot distinguish,
for example, "GPS hardware off" from "no satellite fix indoors". The reason code
records what was actually observable and says "undetermined" when that is the
truth — the alternative is a back-office report full of confident fiction.

The exact persistence shape belongs to a later checkpoint. What RTE01 fixes is
the requirement and the traceability expectation.

The rule that matters most operationally: **the supervisor's work is never
blocked by a location failure**, and the back office always learns about it.

#### 8.6.3 Back-office notification of missing location

**Confirmed Requirement.** A confirmed Missing Location Event is eligible for
configurable back-office notification. The required channels are:

- **in-platform notification** — required;
- **email** — an optional additional channel.

Tenant/Admin configuration defines recipients using the supported role/user
model.

Anti-spam rules, which are part of the requirement rather than a refinement:

- **Do not notify on internal retries.** Notification happens only once an event
  is classified as a *confirmed* missing-location condition.
- **Grouping is allowed; deletion is not.** Repeated or consecutive failures may
  be grouped or deduplicated for notification purposes, but **every underlying
  Missing Location Event is preserved** in the audit/tracking record. The
  notification layer summarises; it never becomes the system of record.

**Repository Finding — what the Foundation actually provides.** Checked rather
than assumed:

| Capability needed | Present in the Foundation? | Evidence |
|---|---|---|
| **Email delivery** | **Yes — reuse it** | `app/core/email/backends.py:310` `send_email`, with SMTP, Microsoft 365 OAuth, console and memory backends, selected from platform configuration with a fallback |
| **Scheduled/grouped dispatch** | **Yes — reuse it** | `PlatformScheduler` (`app/core/platform/scheduler.py:33`), APScheduler with leader-elected interval and cron jobs — suitable for grouped digests without duplicate sends across instances |
| **In-platform notification (inbox, read state, per-user delivery)** | **No — does not exist** | No notification model or table anywhere in `app/core/models/` or `app/core/platform/models.py`; the only "notification" matches are UI `Alert` components and platform health checks |

**Foundation gap (D-01 §3.7), recorded as required.** The Foundation provides
email and scheduling but **does not provide a complete in-platform notification
capability**. That capability is therefore classified **New / future
implementation required** — a tenant-scoped notification store, per-recipient
read state, recipient configuration by role/user, and surfacing in the Admin
shell.

**This is not satisfied by email alone.** In-platform notification is a
required channel of the approved D-01 requirement; email is the optional
additional one. An email-only launch would leave D-01 partially unimplemented,
and this report does not present it as a permanent alternative.

**Technical Recommendation.** Reuse `send_email` and `PlatformScheduler` rather
than rebuilding them, and scope the in-platform notification capability into
whichever checkpoint delivers Admin notifications. **Nothing is implemented in
RTE01** — this is a documented gap and a future work item, not a task started
here.

### 8.7 Permission behaviour

| Permission state | Supervisor sees | System does |
|---|---|---|
| Not yet asked | A one-time plain-language explanation **before** the browser prompt, at onboarding — never mid-drive | Requests permission at first Start Work |
| Granted | Nothing. Capture is silent | Captures at transitions |
| **Denied** | **Nothing during the operational flow.** The action proceeds silently | Staged fallback attempted; if nothing usable, a Missing Location Event is recorded and the back office notified per configuration |
| Revoked mid-session | Nothing during the operational flow | Session continues; affected events recorded as Degraded or Missing |
| Unavailable / timeout | Nothing visible; the action proceeds | Fallback attempted, then Degraded or Missing per §8.6 |

The Permissions API (`navigator.permissions.query`) **is** used to distinguish
"never asked" from "blocked earlier" — but as **diagnostic evidence for the
Missing Location Event and the back office**, not as a prompt to the supervisor.
The external app could not distinguish them at all, so its users received the
same useless message forever (ext. §4, §19.11).

**Supervisor UI silence is a hard requirement (D-01).** CER Route must never
show the supervisor "GPS failed", "missing location", "timeout", "accuracy
error", retry diagnostics, or repeated location warnings during normal
operation. If every acquisition attempt fails, the requested action still
succeeds and the workflow continues.

Two boundaries on that silence, so it is not misread:

- **The browser/OS permission model is not bypassed.** Any permission prompt the
  platform itself requires still happens with the platform's own behaviour. What
  CER Route suppresses is *its own* technical messaging after the outcome is
  known.
- **Onboarding is not "normal operation".** A single plain-language explanation
  before the first permission request is appropriate and is not a technical
  interruption. What is prohibited is nagging a working supervisor.

### 8.8 Offline behaviour

**Technical Recommendation.** The Supervisor client is offline-capable for the
*workflow*, not merely for reading:

- Every supervisor action is written to a **local durable queue** (IndexedDB)
  with a client UUID idempotency key, a monotonic sequence number and the
  device timestamp, **committed locally before the UI reports the action as
  taken**, then optimistically applied to local state.
- A service worker with **Background Sync** (where available) plus a foreground
  flush drains the queue when connectivity returns.
- The server applies actions **idempotently** (§6.5), reusing
  `app/core/integration/idempotency.py`, and returns the authoritative state.
- Conflicts resolve server-side; the client re-renders from the server.

#### Durability objective (verifiable, not absolute)

This report does not claim that nothing can ever be lost. It states a testable
objective and the conditions under which it holds:

| Property | Objective | How it is verified |
|---|---|---|
| **Durability** | An action accepted by the UI has been committed to the local durable queue **before** it is shown as taken, so it survives app suspension, app termination and device restart | V-4 soak test: kill the app and reboot the device at each lifecycle step; every accepted action is still queued |
| **Recovery** | On reconnect, resume, reauthentication (D-09) or device transfer (A-6), the queue drains and the client reconciles against `GET /worksessions/current`, which remains authoritative | V-4, plus the offline-ordering and device-transfer tests in §12.2 |
| **Idempotency** | A replayed or duplicated action changes server state at most once, keyed by its client UUID | §12.2: the same queued action replayed five times changes state once |
| **Ordering** | Out-of-order arrival after reconnect does not corrupt the state machine; contradictory events are rejected and the authoritative state returned | §12.2, §6.6 |

**Known boundaries, stated rather than glossed.** The objective does not hold
against: browser storage eviction under device storage pressure, a user
clearing site data, uninstalling the client, or device loss or destruction.
These are real and largely outside the application's control; the mitigation is
to drain the queue at the earliest opportunity and to keep the window in which
unsynchronised work exists as short as possible — **and V-4 should measure that
window**, not assume it is small.

Without an offline queue at all, the external document's §14 becomes CER
Route's: capture and submission collapse into one gesture, and a supervisor in
a warehouse loses the work outright.

### 8.9 External services: what is and is not needed

| Service | Needed for V1? | Why |
|---|---|---|
| **Routing / road-distance API** | **Yes** | The only way to turn two endpoints into the road distance D-02 defines as `Miles`. The one external dependency the product genuinely requires |
| Map tiles / rendering | **No** | The approved UX contains no map. Adding one adds cost, CDN fragility and scope |
| Geocoding (address → coordinates) | **No** | Destinations are free text by CER's decision, and D-02.2 forbids using destination text as a routing endpoint |
| Reverse geocoding | **No** | No screen shows a captured address |
| Places / enrichment | **No** | No client master |

#### Routing provider — Technical Decision Delegated to Development (D-04)

**CER does not prescribe a provider.** The product requirement is fixed:
*obtain road distance between the approved `Start Trip` and `Arrived`
endpoints*. The selection is the team's, and the full evaluation is recorded in
§14.2 rather than left as an open CER question.

Technical constraints set by CER, which bind whatever provider is chosen:

- routing calculation is **backend-side**;
- **provider credentials are never exposed to the Supervisor client**;
- provider access sits behind an **adapter/port boundary**;
- **domain logic is never coupled directly to a provider**;
- the contingency path **integrates with the D-02 mileage state model** — a
  provider outage produces `Pending Calculation` and retries, never a
  substituted straight-line number, and eventually a terminal state.

### 8.10 Privacy, battery and cost

- **Privacy.** Positions are captured only at lifecycle transitions, only
  during an active session, and the supervisor controls when the session ends.
  This is the narrowest collection that still answers the product's questions
  (§10.3). Note that a routing provider necessarily receives endpoint
  coordinates — a privacy consideration explicitly on the D-04 evaluation list.
- **Battery.** Transition-only capture is negligible. Foreground breadcrumbs at
  a low frequency with a displacement filter are modest and stop with the
  session. A continuous high-accuracy trace would be the expensive option, and
  it is not part of the approved model.
- **Cost.** One or two routing calls per Trip leg, plus retries under the
  contingency path. Six legs/day × 22 days ≈ 130 calls/month/supervisor: small,
  but it must be capped per tenant and monitored (lesson adopted from ext.
  §21), and retry storms during a provider outage are the case to bound.

### 8.11 Technical validations required before RTE06

**Validation Required — these must be measured, not believed.** The external
document is explicit that none of this was ever recorded in the source project;
CER Route should not inherit that silence.

These are **development/validation work items, not open CER product
decisions**.

| # | Validation | Question it answers | Effort |
|---|---|---|---|
| **V-1** | Client lifecycle probe on real iOS Safari and Chrome Android, across the candidate client technologies (D-03) | When exactly does capture stop on lock/background? Does an installed client behave differently? Feeds the D-03 recommendation |  2-3 days |
| **V-2** | Accuracy and acquisition-time sampling in CER's real environments (warehouses, industrial parks, parking structures) | Are the §8.6 thresholds, the freshness rules and the recovery-window duration real or guessed? | 3-5 days, needs site access |
| **V-3** | **Routing provider evaluation** (D-04): coverage, routing quality, latency, availability, cost/quota behaviour, and outage/contingency behaviour against the D-02 state model | Which provider, and does the contingency path actually reach a terminal state? | ~1 week |
| **V-4** | Offline queue soak test (airplane mode through a full simulated day), including device transfer mid-session (A-6) | Does anything get lost, duplicated or misordered? Does a session transfer cleanly? | 2-3 days |
| **V-5** | Endpoint-acquisition reliability across a realistic day: how often is each endpoint Fresh / Degraded / Recovered / Missing | The real-world frequency of degraded and missing endpoints — which determines how much `Not Calculable` the back office should expect | Runs alongside V-2 |

**Note on scope (D-02.7).** V-3 is a *provider* evaluation. It is **not** an
odometer comparison: odometer capture, OCR, manual reconciliation and any
odometer-based error tolerance are **out of V1 scope** by CER decision, and **no
odometer validation gates RTE06**.

### 8.12 Unresolved feasibility risks

1. If V-1 shows that transition capture is unreliable on some platform/version,
   the client technology decision (D-03, delegated) must account for it — which
   is precisely why D-03 is resolved after V-1 rather than before.
2. If V-5 shows endpoints are Missing more often than the back office can
   absorb, the consequence is operational load from `Not Calculable` Trips and
   missing-location notifications, not a redefinition of `Miles`. Reducing that
   rate is an acquisition-strategy problem (§8.4), and the recovery window is
   the main lever.
3. **R-14:** an incomplete contingency path leaves Trips in `Pending
   Calculation`, which D-02.10 forbids. The bounded sweeper must be designed
   and tested, not assumed.
4. Position spoofing remains impossible to prevent (§10.4).

---

## 9. Mobile / Responsive Strategy

### 9.1 Supervisor: mobile-only, one shell, one action per screen

**Confirmed Requirement (D-03).** The Supervisor experience is **Mobile-only in
V1**. No Supervisor Desktop experience is required, and none should be built.
This is a product decision, and it simplifies the work: the supervisor shell is
designed for one form factor rather than degraded gracefully across several.

**Technical Decision Delegated to Development (D-03).** CER does **not**
prescribe PWA, native or hybrid. The team selects the client technology against
CER's stated requirements — that it reliably satisfies the D-01/D-02 location
requirements, supports the mobile workflow, fallback/recovery, offline
continuity and provenance, and preserves CER Route's modularity, security and
maintainability. The evaluation and the recommendation are recorded in **§14.2**
and depend on **V-1**.

**Technical Recommendation** (the team's current position, pending V-1): an
installable PWA inside the same React bundle, selected by page key, for three
concrete reasons — a durable storage quota for the offline queue, a
full-viewport lifecycle without browser chrome, and Background Sync where
supported — with a Capacitor wrapper retained as a designed-for escape hatch if
V-1 shows the web platform cannot meet the D-01 acquisition requirements.

Design rules taken directly from baseline §2.1 and enforced as engineering
constraints, not suggestions:

- **One primary action per screen**, sized for a thumb, reachable one-handed.
- **The next action is computed from server state**, never inferred by the
  client — which is what makes the flow resumable after any interruption.
- **No typing while driving.** Free-text fields (destination, area, reference)
  appear only *before* Start Trip or *after* Arrived, never in the `IN_TRANSIT`
  screen. The `IN_TRANSIT` screen offers exactly: Arrived, Change Plan.
- **No implementation messaging.** No GPS toasts, no sync spinners, no
  "uploading" states. Sync status appears only as a single discreet indicator
  when something is actually pending.
- **Selectable lists are large tap targets**, not native `<select>` dropdowns,
  for the Admin-managed values. Per A-3, the **Activity selector is
  multi-select** — tap to toggle several, with `Start Activity` enabled once at
  least one is chosen. This is the only visible UX change from the V0.7 mockup,
  and it introduces no new visible concept or terminology (§3.5).
- **No location diagnostics, ever** (D-01). The supervisor never sees "GPS
  failed", a timeout, an accuracy warning or retry diagnostics during normal
  operation. Location problems are a back-office concern (§8.6.3), not a
  driver's.
- **An active Activity owns the screen** (A-3). While a block is
  `IN_PROGRESS`, reopening the app returns the supervisor to that Activity, and
  the only exits are `Complete` and `Leave`, each with its Outcome. `End Work`
  is not offered there (§6.6).
- **`End Work` is a review, not a trapdoor** (D-07). If a Trip is still
  `IN_TRANSIT`, End Work shows the end-of-work review with **Continue
  Working** as the recovery path; ending anyway takes an explicit second
  confirmation.

### 9.2 Suspension, resume and interruption

| Event | Behaviour |
|---|---|
| App backgrounded / screen locked | Local state persists in IndexedDB; no capture occurs (§8.3) — by design, not by accident |
| App resumed | `visibilitychange` triggers `GET /worksessions/current`; the UI re-renders from the server; the queue flushes |
| Browser/PWA killed and reopened | Same path. Nothing is held only in memory |
| Phone reboots mid-session | Session is server-side and still `ACTIVE`; the supervisor resumes exactly where they were |
| Connectivity lost | Actions queue locally; the workflow continues without interruption |
| Connectivity restored | Queue drains idempotently; server state wins on conflict |
| Device transfer mid-session (A-6) | The second device resumes **the same** Work Session via `GET /worksessions/current`; no second session, no duplicated Trips or Activities |
| Authentication expires mid-shift | **An active Work Session must not lose operational continuity** (D-09). Re-authentication returns to the same state and the pending offline queue remains recoverable and synchronizable. The mechanism is delegated to development (§14.2) |

**The objective:** an action the UI has accepted is durably queued before it is
shown as taken, and is recovered and applied idempotently after any of the
lifecycle events above — rather than an absolute guarantee that nothing can
ever be lost. The property, its verification and its known boundaries (storage
eviction, cleared site data, device loss) are set out in §8.8, and §12.2 tests
them.

### 9.3 Admin: responsive, list-first

The existing sidebar shell serves desktop. For Admin Mobile the baseline is
explicit (§2.2, §8): **the supervisor list comes first; large KPI cards must not
push it below the fold.** Implementation: the summary strip collapses to a
single compact line on narrow viewports, and the supervisor list renders
immediately beneath it. Selecting a supervisor opens a detail panel (side panel
on desktop, full-screen push with a back action on mobile — the mockup's
`adminMobileDetail` pattern).

`DataTable` + `DataTablePagination` from `features/Common` are reused for every
Admin table. No second table implementation (repository frontend rule 9).

### 9.4 Today/Live freshness

**Technical Recommendation.** Polling on a visible-tab interval (≈30 s), not
WebSockets. "Live" in this product means "current within half a minute", the
data changes a few times per hour per supervisor, and polling costs nothing to
operate. WebSockets would add a persistent-connection infrastructure for no
product gain — and can be introduced later behind the same selectors if CER ever
needs true push.

---

## 10. Security / Privacy / Audit

### 10.1 Reused from the foundation, unchanged

Authentication by HttpOnly cookie with double-submit CSRF; company resolved from
the subdomain and **never** from the request body; server-side capability checks
on every endpoint; platform-admin privilege strictly separate from tenant
permissions; append-only, trigger-protected audit; homogeneous error codes (401
/ 403 / 404 / 409 / 422), where another company's resource returns **404, not
403**. These are repository invariants and this product does not relax any of
them.

### 10.2 New capabilities

New `route.*` capabilities declared in `app/core/rbac/catalog.py` (invariant 4),
each with at least one endpoint requiring it:

```
route.worksession.execute     start/end own work session, trips, activities
route.live.read               Today / Live
route.activity.read           Activity Explorer (all supervisors)
route.reports.read            consolidated reports
route.reports.export          Excel export
route.vehicles.read/manage    vehicle master and assignment
route.standardvalues.manage   admin-managed selectable lists
route.fuelreference.manage    reference prices
route.records.adjust          post-hoc correction of an activity (see A-7 / D-08)
```

Two default roles: **Supervisor** (execute own work only) and **Route Admin**
(read across supervisors, manage configuration). A supervisor has **no**
capability to read another supervisor's data — enforced server-side, since the
`user_data` cookie is readable and editable in the browser and is therefore UX
only (invariant 8).

### 10.3 Location data: collection boundary

**Technical Recommendation, and the core privacy control.** Location may be
written **only** when it belongs to an `ACTIVE` work session owned by the
authenticated user. The intake endpoint rejects everything else. Consequences,
all deliberate:

- No position can exist for a supervisor who is off the clock.
- A supervisor who ends work stops being locatable by the product, immediately.
- A compromised or modified client cannot cause tracking outside working hours,
  because the boundary is enforced on the server.

Supporting measures: the one-time privacy notice of §10.5; the retention split
of §10.6; location visible only to the owning supervisor and to Admins of the
same company; and coordinates excluded from application logs, which carry
identifiers only.

### 10.4 Integrity, and one honest limitation

| Control | Status in the proposed design |
|---|---|
| Identity, company and timestamps from the server | **Yes** — inherited invariant |
| Coordinate range validation at the boundary | **Yes** — the external app had none (ext. §15) |
| Implausible-speed detection between fixes | **Yes** — flagged, excluded from mileage |
| Server-computed mileage (never client-supplied) | **Yes** — the client never sends a distance |
| Append-only location and purpose-change history | **Yes** |
| Audit of every Admin correction | **Yes** — corrections add rows, never edit them |
| **GPS spoofing prevention** | **No — and not achievable.** |

**Stated plainly, because CER should hear it from the developer and not from an
incident:** no web application can guarantee that a reported position is real.
Developer tools, emulators and mock-location apps can override
`navigator.geolocation` invisibly. What this design does is make a false
position **inconvenient and detectable after the fact** — accuracy recorded,
impossible travel flagged, both timestamps kept, everything audited. CER Route
must never claim "verified location". If a stronger guarantee is ever required,
that is a native-app and device-management conversation, not a web one.

### 10.5 Privacy notice (D-08.1)

**Confirmed Requirement.** One clear, plain-language location/privacy notice is
shown:

- during onboarding or first activation;
- **before** the first device/browser location-permission request.

It explains simply that CER Route uses location during the workday to record
travel and calculate operational mileage.

It is **not repeated during normal operation** and must not become recurring
operational friction. This is the single, deliberate exception to the "no
location messaging" rule of D-01 §3.4 — it happens once, before work begins,
and never again.

### 10.6 Retention, and Admin corrections

#### Retention (D-05) — historical facts and raw evidence are separate

**Confirmed Requirement.** CER distinguishes historical operational facts from
raw location evidence, and they do **not** share a retention policy.

| Category | Contents | Retention |
|---|---|---|
| **Historical operational facts** | Trip, lifecycle timestamps, final `Miles`, calculation provenance, Activities, Outcome, duration, fuel estimate, terminal calculation states/exceptions, audit history | **Must not be silently deleted or changed** by any raw-evidence retention policy |
| **Raw location evidence** | Raw lat/lon fixes, breadcrumbs, cached/recovered points, accuracy, age/staleness, detailed acquisition evidence | Its **own limited** retention policy |

**When raw evidence expires, the derived historical facts remain unchanged.**
This is what makes a limited retention period safe: purging a year-old
breadcrumb must not alter the `Miles` figure a report already published.

**The exact retention duration is not set by this report.** R1/R2 recommended
90 days; **that recommendation is withdrawn** and must not be read as a
CER-approved requirement. The duration belongs to the applicable
policy/compliance/configuration decision, not to an invented RTE01 product
rule. The model simply has to make any chosen duration implementable — which
the fact/evidence split above is precisely what achieves.

#### Post-close corrections (D-08.2)

**Confirmed Requirement**, and the only sanctioned way a consolidated
historical value ever changes (§8.5.5):

- **Only Admin** may initiate post-close corrections or recalculations.
- Corrections happen through **controlled Web Admin actions and backend
  services/jobs** — never by direct database editing. Direct DB intervention is
  reserved for exceptional technical recovery, not normal Admin operation.
- **No automatic or silent historical recalculation is allowed**, anywhere.
- Every correction preserves: the original value/fact, the corrected value, the
  reason, the initiating Admin, timestamps, a complete audit trail, and the
  job/result status where relevant.

This is the `record_correction` entity (§7.1) plus the existing append-only
`audit_event`. The capability `route.records.adjust` (§10.2) gates it, and it
is deliberately **not** granted to the Supervisor role.

### 10.7 Secrets and configuration

The routing provider's credentials are a secret: stored encrypted via
`app/core/platform/secrets.py`, never in Git, never in the frontend bundle.
**No routing call is ever made from the browser** (D-04) — all provider calls
are server-side, which keeps credentials private and prevents a client from
fabricating distances.

---

## 11. Fuel Reference / Estimated Cost Model

### 11.1 The model

```
Estimated Gallons   = Miles / Operational MPG
Estimated Fuel Cost = Estimated Gallons × Reference Price(grade, geographic scope, effective date)
```

**Confirmed Requirement**: this is an *estimate*, not an accounting record, and
history must not silently change.

### 11.2 Fuel price is variable, not a single tenant value (D-06)

**Confirmed Requirement.** CER has rejected the notion of one static price per
tenant. The model must support the real variability of fuel by:

- **geographic scope** — state/city or another technically viable granularity;
- **fuel grade**;
- **date/effective time**.

This supersedes the R1/R2 recommendation of "one set of prices per company for
V1", which is withdrawn.

`fuel_reference_price` rows are **immutable and effective-dated**:

| Field | Purpose |
|---|---|
| `fuel_grade` | Regular, Midgrade, Premium, Diesel — a `BusinessEnum` with a DB `CHECK` |
| `price_per_gallon` | `numeric(8,4)` — the mockup's prices carry four decimals (`4.0947`) |
| `effective_from` | When the price starts applying |
| `geographic_scope` | The area the price applies to (the mockup's "Georgia" is a state-scoped example) |
| `source` | Provenance — e.g. a named provider, a scheduled feed, or an import |
| `ingested_at` | When the row arrived, distinct from when it takes effect |

Entering a price **inserts a row**; it never updates one. Adding a price cannot
rewrite history, because there is nothing to overwrite.

**Confirmed Requirement.** CER Route must support a **scheduled mechanism** to
keep reference prices reasonably current for estimation.

**Repository Finding.** The scheduling capability already exists —
`PlatformScheduler` (`app/core/platform/scheduler.py:33`), APScheduler with
leader-elected cron/interval jobs — so the recurring-ingestion half of this
requirement reuses platform machinery rather than adding any.

### 11.3 Source and ingestion — Technical Decision Delegated to Development (D-06)

**CER does not select a fuel data source.** The team evaluates the practical
source and ingestion strategy — external provider/API, scheduled connection,
CSV/import, or a combination with fallbacks — against reliability, geographic
coverage, update frequency, cost, licensing, provenance, fallback/contingency
and data validation. The evaluation is recorded in §14.2.

The architecture makes the choice reversible and keeps it out of the domain:
the product reads prices **only** from `fuel_reference_price`, so how a row
arrives is an input mechanism, never a dependency. **No ingestion is
implemented in RTE01.**

### 11.4 Missing price: `Pending Calculation`, never a substitute (D-06)

**Confirmed Requirement.** If the applicable fuel price is not currently
available:

> `Estimated Fuel Cost` remains **`Pending Calculation`**.

The system does **not** invent a price, does not silently substitute a
neighbouring region's price, and does not fall back to the most recent
unrelated value. When a valid applicable price becomes available, the estimate
may be completed.

This mirrors the mileage lifecycle of §8.5.4, and for the same reason: a
plausible fabricated number is worse than an honest "not yet", because nobody
can tell afterwards which figures were real.

### 11.5 Historical integrity

**Confirmed Requirement.** Persist the reference and provenance required to
preserve a historical estimate: source, geographic scope, effective date/time,
fuel grade, the price actually used, and the calculation timestamp. **Future
price updates must not silently change historical facts.**

**The subtlety that would otherwise be missed.** Price history alone is not
sufficient — **MPG is the other input**, and `operational_mpg` is mutable
master data. If an Admin corrects a vehicle from 27 to 24 MPG, every historical
estimate for that vehicle would silently change, which is exactly the failure
the requirement forbids for prices.

Therefore **`mpg_snapshot` is captured on the work session at Start Work**, and
estimates use the snapshot rather than the current vehicle row. Same reasoning,
same protection, one column. The `fuel_estimate` record (§7.1) stores both the
`mpg_used` and the `fuel_reference_price_id` actually applied, so any
historical figure can be audited back to its two inputs.

Changing a consolidated estimate afterwards is possible only through an
audited Admin correction (D-08.2, §10.6) — never automatically.

---

## 12. Test Strategy

### 12.1 Layers

Following `ARCHITECTURE_BEST_PRACTICES.md` and the repository's own discipline
(**PostgreSQL only — never SQLite**, since the schema depends on partial unique
indexes, JSONB, composite FKs and `timestamptz`):

| Layer | Focus | Tooling |
|---|---|---|
| Unit — Services | Lifecycle rules, mileage arithmetic, fuel estimation, aggregation | pytest, no DB |
| Integration — DAOs | Company scoping, partial unique indexes, CHECK constraints, append-only triggers | pytest + real PostgreSQL |
| HTTP — Routers | Status codes, authorization, validation, idempotency | pytest + httpx |
| Architecture nets | The existing `test_page_wiring`, `test_navigation_wiring`, `test_permission_catalog`, `test_public_surface` extended to the new pages and capabilities | pytest |
| Frontend | State machine reducers, Zod schemas, offline queue | `tsc` + lint today; a unit runner to be added |
| **Device / browser** | The things no unit test can answer (§12.3) | Real iOS and Android hardware |

### 12.2 Scenarios that must have named tests

| Area | Test |
|---|---|
| Work session | One active session per supervisor enforced **by the database**, not by a check |
| **Midnight crossover** | Start Fri 20:00, end Sat 00:41 ⇒ `session_date` = **Friday**, in every aggregate. `time-machine` is already a dev dependency |
| Timezone (D-10) | A session near midnight lands on the correct **local** date, not the UTC date; a daylight-saving boundary and a skewed device clock do not corrupt it |
| **A-1** | A Work Session with **zero Trips** is valid and complete; no artificial Trip is ever created at `Start Work` |
| **Change Plan** | Original purpose survives two consecutive changes; the executed activity differs from both; all three are reportable |
| **Change Plan boundary (A-4)** | A purpose change after `Arrived` is rejected with `409` |
| **End Work review (D-07)** | End Work while `IN_TRANSIT` does **not** close anything by itself; `Continue Working` restores the prior state; only an explicit *End Work Anyway* ends the session, marking the Trip `INTERRUPTED` with **no** artificial `Arrived` |
| **Active Activity blocks End Work (A-3/D-07)** | End Work while a block is `IN_PROGRESS` is **rejected**, returns the authoritative state, and neither auto-closes the block nor writes an Outcome |
| **Activity restoration (A-3)** | Reopening the app mid-Activity returns to the Activity screen with its selections intact |
| **Device transfer (A-6)** | Opening a second device resumes the same session; no second session, no duplicated Trips or Activities; queued actions from both devices reconcile without loss |
| Geolocation permission | Denied / unavailable / timeout each proceed silently, never block the action, and produce Degraded or Missing per §8.6 |
| Accuracy | Fixes above threshold are excluded from mileage but retained as evidence |
| Anomaly | An implausible-speed pair is flagged and excluded |
| **Staged acquisition (D-01)** | A cached/last-known fallback is stored with its real age and provenance and is **never** presented as a fresh fix |
| **Missing Location Event (D-01)** | Exhausted acquisition records a traceable event with an honest reason code; the operational action still succeeds |
| **Notification anti-spam (D-01)** | Internal retries never notify; grouped notifications never delete an underlying event record |
| **No fabricated coordinates (D-01)** | No code path can persist a coordinate the device did not supply |
| **Recovered Point (D-01)** | A fix obtained inside the recovery window keeps its **true** capture timestamp and is never restamped to the event |
| **Multi-Activity block (A-3)** | Selecting three Activities produces **one** start, one completion, one duration, one Outcome, one Notes — not three |
| **A-3 minimum** | `Start Activity` is rejected when zero Activities are selected |
| **A-3 context (A-3.2)** | A selection containing a value from a different V0.7 context is rejected |
| **Outcome is tenant data (A-3)** | No Outcome value is seeded or hardcoded as a business enum; a tenant with different values behaves correctly |
| **Idempotency** | The same queued action replayed five times changes state once |
| **Durability (§8.8)** | An action the UI accepted is present in the local durable queue after app termination and after device restart — i.e. it was committed before being shown as taken |
| **Recovery (§8.8)** | The queue drains and reconciles against `GET /worksessions/current` after reconnect, resume, reauthentication and device transfer |
| Offline ordering | Out-of-order arrival after reconnect never corrupts the state machine |
| **Mileage endpoints (D-02.2)** | Known coordinate pairs produce known road distances; destination text is **never** used as an endpoint |
| **Mileage lifecycle (D-02.10)** | Every Trip reaches a terminal state; no Trip can remain in `Pending Calculation` past the contingency bound; `Not Calculable` and `Calculation Failed` are distinguished correctly |
| **No Haversine as Miles (D-02.6)** | A routing outage yields `Pending Calculation` then a terminal state — **never** a published straight-line distance |
| **Plausibility gate (D-02.9)** | An anomalous routing result is not consolidated; the contingency path continues |
| **Miles are historical facts (D-02.8)** | Changing provider, algorithm or configuration does not alter an already-`Calculated` Trip |
| **Admin correction (D-08.2)** | A correction preserves the original value, reason, admin and timestamps, and is fully audited; no silent recalculation path exists |
| **Fuel variability (D-06)** | The applicable price resolves by grade **and** geographic scope **and** effective date |
| **Fuel pending (D-06)** | With no applicable price, the estimate is `Pending Calculation` — never an invented or substituted price |
| **Fuel history** | A price added today does not alter last month's estimate; an MPG correction does not alter past sessions |
| **Retention split (D-05)** | Purging expired raw location evidence leaves `Miles`, timestamps, Outcomes and audit history unchanged |
| Authorization | A supervisor cannot read another supervisor's session (404, not 403); a cross-company id returns 404 |
| Aggregation | Year/month/week/day totals equal the sum of their day-level activities |
| **Export** | The Excel export matches the on-screen report row for row and value for value |

### 12.3 What device testing must cover that unit tests cannot

Explicitly called out because the external document shows what happens when it
is skipped — nothing was recorded, so nothing could be answered afterwards:

- iOS Safari and Chrome Android behaviour on lock, background and resume;
- installed-PWA versus in-browser behaviour;
- permission prompt flows, including "Allow once" and post-grant revocation;
- time to first fix indoors, outdoors and in a moving vehicle;
- accuracy in CER's actual working environments;
- offline-to-online transitions with a queue that has real contents;
- battery cost across a realistic workday.

A small, fixed device matrix should be agreed with CER and used for every
checkpoint from RTE03 onward, so regressions are found on hardware rather than
in the field.

---

## 13. Risks / Dependencies / Technical Debt

| ID | Risk | Sev. | Impact | Mitigation |
|---|---|---|---|---|
| **R-01** | Background location is impossible in a mobile browser | **High** | A design assuming continuous tracking silently under-reports miles | Transition-based model (§8.4); validated by V-1; client technology chosen with this in mind (D-03) |
| **R-02** | **Endpoint quality governs mileage quality.** Degraded or Missing endpoints degrade or prevent the `Miles` calculation | **High** | `Not Calculable` Trips and back-office load; gaps in the product's central number | Staged acquisition + recovery window (§8.4); measure real frequency (V-5); honest terminal states rather than fabricated values (§8.5.4) |
| **R-03** | Field connectivity loss | **High** | Lost sessions and lost work if not designed for | Offline queue from RTE03 (§8.8); soak-tested including device transfer (V-4) |
| **R-08** | Employee location data carries legal/privacy obligations | **High** | Compliance and labour-relations exposure | Collection bounded to active sessions (§10.3); one-time notice (§10.5); fact/evidence retention split (§10.6) |
| **R-13** | **In-platform notification does not exist in the Foundation**, and D-01 requires it | Medium | D-01 only partially implementable until it is built; email alone does not satisfy the requirement | Recorded as New / future implementation required (§8.6.3); scope into the checkpoint delivering Admin notifications |
| **R-14** | **Trips stuck in `Pending Calculation`** if the contingency path is incomplete | Medium | Violates D-02.10; reports show perpetually unresolved mileage | Bounded contingency policy + sweeper on the existing `PlatformScheduler`; explicit test that every Trip reaches a terminal state (§12.2) |
| **R-04** | GPS accuracy in warehouses and industrial parks is unmeasured | Medium | Wrong thresholds accept bad fixes or reject good ones; wrong recovery window | Measure on site (V-2); store `accuracy` and level from day one |
| **R-05** | Routing provider cost, quota, availability and coupling | Medium | Surprise bills; retry storms during an outage; migration cost if terms change | Adapter port (D-04); per-tenant quotas with 80%/100% alerts; bounded retries feeding the D-02 state model |
| **R-06** | Position spoofing is undetectable in principle | Medium | Fabricated mileage | Detect after the fact (§10.4); never claim verified location |
| **R-07** | **Authentication expiry during a long shift** | Medium | Re-authentication mid-drive; queued offline work stuck behind a login | D-09 requirement: continuity must not break, and the queue must survive reauthentication. Mechanism delegated (§14.2); addressed before RTE03 |
| **R-09** | Battery drain if capture frequency is raised later | Medium | Supervisors disable the app | Keep breadcrumbs opportunistic and infrequent; they are supporting evidence only (D-02.5); measure |
| **R-10** | Scope creep toward fleet management / route optimization | Medium | V1 inflation, the exact outcome baseline §12 forbids | Every new entity justified against the eight product questions |
| **R-11** | Year-scale Excel export memory and time | Low | Slow or failed exports | Stream the workbook; generate server-side into existing storage; cap or paginate ranges |
| **R-12** | Project identity still reads "CER Application" | Low | Foundation branding leaking into a delivered product | Set `APP_*` during RTE02 (§17.1) |

### Dependencies

**No dependency on CER remains for an RTE01 product decision.** What is listed
is operational access and infrastructure needed to run the delegated technical
evaluations and validations.

| Dependency | On whom | Needed by |
|---|---|---|
| Real devices (iOS + Android) for V-1 / V-4 | CER / team | Before the D-03 recommendation is finalised |
| Site access for accuracy and acquisition sampling (V-2, V-5) | **CER** (operational access) | Before RTE06 |
| Routing provider evaluation and budget approval (V-3, under delegated D-04) | Team proposes; CER approves spend | Before RTE06 |
| Retention duration from the applicable policy/compliance decision (D-05) | **CER policy owner** | Before production |
| Fuel data source selection and any licensing/cost (delegated D-06) | Team proposes; CER approves spend | Before RTE09 |
| HTTPS in every environment | Infrastructure | From RTE02 |

**Technical debt.** None inherited from a prior CER Route system — there is
none. The four inherited-assumption items in §4.3 are the only adaptations
required, and each is small if handled early.

---

## 14. Decision Register

**No decision in this section is awaiting CER.** Every item is either an
approved CER requirement (§14.1) or a technical decision CER has explicitly
delegated to development (§14.2). Decision IDs are kept stable rather than
renumbered so that earlier cross-references, and CER's own references, continue
to resolve.

### 14.1 Approved CER requirements

Each is applied in the body of the report; the section references are where the
rule actually governs the design, not where it is merely mentioned.

| ID | Approved decision | Where applied |
|---|---|---|
| **A-1** | `Start Work` opens a Work Session without a Trip. **No artificial Trip** is created because work started; a Trip exists only when a displacement begins | §6.3, §7.1 |
| **A-2 / D-07** | `End Work` is a **finalization/review action, not a destructive close**. While a Trip is `IN_TRANSIT` it presents the end-of-work review with **Continue Working** as the recovery path. An explicit **End Work Anyway** ends the session and marks the Trip `INTERRUPTED`, with **no artificial `Arrived`**. While an Activity is `IN_PROGRESS`, End Work is **rejected** — no auto-close, no invented Outcome | §6.6, §9.1, §9.2 |
| **A-3** | One arrival may contain **multiple Activities selected within that same V0.7 context**, executed as one block with one start, one completion, one duration, one Outcome and one Notes. Selector becomes multi-select; at least one required. Outcome values are tenant-configured data, never a `BusinessEnum`. No new user-facing terminology. Active Activities are restored on reopening | §3.5, §6.1, §6.2, §7.1, §7.3, §9.1 |
| **A-4** | `Change Plan` is available **only while `IN_TRANSIT`**. After `Arrived` the Trip has reached its destination and any further displacement is a new Trip | §6.4, §6.6 |
| **A-6** | A supervisor may not have two active Work Sessions. A second device **transfers/resumes the same session** — never duplicates it. The server stays authoritative; offline queues reconcile without losing traceability | §6.6, §6.7, §9.2 |
| **A-7 / D-08.2** | **Admin-only** post-close corrections, through controlled Web Admin actions and backend jobs, fully audited, preserving original and corrected values, reason, admin and timestamps. **No automatic or silent recalculation.** Direct DB editing is not normal operation | §10.6, §8.5.5, §7.1 |
| **A-8 / D-06** | Fuel reference varies by **geographic scope, grade and effective date**, with a **scheduled mechanism** to keep prices current. A single static tenant price is rejected. A missing price leaves the estimate `Pending Calculation` — never invented | §11 |
| **D-01** | Location is a **high-priority best-effort** requirement with four evidence levels (**Fresh / Degraded Cached / Recovered / Missing**), a silent recovery window, silent operational continuation, a traceable **Missing Location Event**, and configurable back-office notification with **in-platform required** and email optional. Coordinates are never fabricated; cached or recovered evidence is never presented as Fresh | §8.4, §8.6, §8.7, §7.1 |
| **D-02** | **`Miles` = road distance between the `Start Trip` and `Arrived` endpoints via a routing service.** Not odometer, not GPS trace, not straight-line. Four-state lifecycle (`Pending Calculation` → `Calculated` / `Not Calculable` / `Calculation Failed`), plausibility-gated, with a consolidated value being a **historical fact never automatically recalculated**. Breadcrumbs are supporting evidence only. Odometer is **out of V1** | §8.5 (all), §7.1, §12.2 |
| **D-05** | Historical operational facts and raw location evidence have **separate** retention. Expiring raw evidence must not alter derived facts. **No specific duration is set by this report** | §10.6 |
| **D-08.1** | **One** plain-language privacy notice, at onboarding/first activation and before the first permission request. Never repeated in normal operation | §10.5 |

### 14.2 Technical decisions delegated to development

CER has fixed the requirement and handed the implementation choice to the team.
**These are not open CER product decisions.** Each is recorded here with its
requirement, the evaluation CER asked for, and the team's current position —
which is a recommendation, not an approved rule, and in three cases depends on
a validation that has not yet run.

#### D-03 — Supervisor client technology

- **CER's requirement.** The Supervisor experience is **Mobile-only in V1**; no
  Supervisor Desktop experience is to be developed. The chosen technology must
  reliably satisfy D-01/D-02, support the mobile workflow, fallback/recovery,
  offline continuity and provenance, and preserve modularity, security and
  maintainability.
- **Options evaluated.** (a) Installable PWA in the existing React bundle;
  (b) Capacitor wrapper around the same React code; (c) fully native.
- **iOS/Android behaviour.** The decisive constraint is §8.3: no mobile browser
  captures location in the background — iOS Safari suspends the page on lock,
  Android throttles heavily, and service workers cannot reach the Geolocation
  API. (a) therefore supports transition capture and foreground breadcrumbs
  only. (b) and (c) can capture in the background, at the cost of store
  distribution, device management and a heavier release pipeline.
- **Why the approved model tolerates (a).** D-02 defines `Miles` from two
  endpoints captured at moments when the supervisor is stopped with the app in
  the foreground. The approved product does **not** require background capture.
- **Offline, reliability, maintenance, security.** (a) keeps one codebase, one
  auth surface and same-origin cookies, and covers offline through IndexedDB +
  Background Sync. (b) inherits all of that and adds native capability where
  the web platform falls short. (c) duplicates the codebase for capability the
  approved flows do not need.
- **Team recommendation: (a), with (b) as a designed-for escape hatch**, decided
  on the evidence of **V-1**. Building for (a) does not foreclose (b), because
  the same React code runs in both — which is the main reason to prefer it now.

#### D-04 — Routing provider and contingency

- **CER's requirement.** Obtain road distance between the approved endpoints.
  Backend-side only; credentials never exposed to the client; access behind an
  adapter/port; domain logic never coupled to a provider; contingency integrated
  with the D-02 state model.
- **Options.** Commercial APIs (Google Routes, Mapbox, HERE, TomTom) versus
  self-hosted OSRM/Valhalla on OpenStreetMap data.
- **Evaluation axes, as CER specified.** Coverage and routing quality;
  reliability/availability; latency; cost and quotas; **coordinate privacy**
  (endpoints leave the system with a commercial provider, not with self-hosting);
  licensing; observability; vendor lock-in; replacement cost; retries/fallback;
  and outage contingency.
- **Contingency design.** A provider outage must yield `Pending Calculation`
  with bounded retries and then a terminal `Calculation Failed`, never a
  substituted straight-line value (D-02.6) and never an indefinitely pending
  Trip (R-14).
- **Team position:** start with a commercial provider behind the adapter for
  speed of delivery, and keep self-hosting as a live option if volume or
  coordinate privacy justify it. **Decided on the evidence of V-3**; the adapter
  makes it reversible, which is why it does not delay RTE02.

#### D-06 (source) — Fuel data source and ingestion

- **CER's requirement.** Support fuel prices varying by scope, grade and date,
  kept reasonably current by a scheduled mechanism.
- **Options.** External provider/API; scheduled connection; CSV/import; or a
  combination with fallbacks.
- **Evaluation axes.** Reliability, geographic coverage, update frequency, cost,
  licensing, provenance, fallback/contingency and data validation.
- **Team position.** Design the ingestion as an adapter writing into
  `fuel_reference_price`, so the source is replaceable and the domain never
  knows it, reusing `PlatformScheduler` for recurrence. Source selection follows
  a coverage and licensing comparison. **Nothing is implemented in RTE01.**

#### D-09 — Authentication continuity on mobile

- **CER's requirement.** An active Work Session must not lose operational
  continuity merely because authentication expires, and a pending offline queue
  must remain recoverable and synchronizable securely after reauthentication.
- **Repository Finding.** `ACCESS_TOKEN_EXPIRE_MINUTES = 1440` with no refresh
  token (`app/config.py:73`) — a back-office default meeting a field product
  for the first time (R-07).
- **Design axes.** Secure renewal, refresh/rotation, lifetime, revocation,
  session recovery, offline-queue protection, mobile UX, and minimum privilege.
- **Team position.** Silent refresh with rotation, so a supervisor is never
  interrupted mid-shift, and an offline queue that survives reauthentication
  and is protected at rest on the device. Addressed before RTE03, since RTE03
  is where long sessions first become real.

#### D-10 / A-5 — Time and timezone handling

- **CER's requirement.** Every event records the real date/time it occurred with
  enough timezone context to reconstruct local chronology; a Work Session
  belongs to the **local calendar date of `Start Work`**, even across midnight;
  time handling never blocks a lifecycle event; and **the supervisor never
  configures a timezone** — no catalogue, no manual assignment.
- **Design axes.** Server time, device time, UTC storage, local offset capture,
  daylight-saving transitions, clock skew, synchronisation.
- **Team position.** `timestamptz` storage, device UTC offset captured per
  lifecycle event, and `session_date` computed once at `Start Work` and never
  recomputed (§6.5). Server time remains authoritative for ordering; device time
  is evidence. **Validation Required** for daylight-saving boundaries and skewed
  device clocks (§12.2).

### 14.3 Items explicitly removed from scope

| Removed | Authority |
|---|---|
| Odometer capture, OCR, manual reconciliation, odometer-based tolerance, and any odometer gate on RTE06 | D-02.7 |
| Haversine/straight-line distance as official `Miles` | D-02.6 — internal diagnostics only |
| Email-only satisfaction of the D-01 notification requirement | D-01 §3.7 |
| A fixed 90-day raw-location retention presented as CER-approved | D-05 |
| A single static tenant fuel price | D-06 |
| Auto-closing an active Activity or inventing an Outcome on End Work | D-07, A-3 |
| Supervisor Desktop experience | D-03 |
| Supervisor timezone catalogue or manual timezone setting | D-10 |

---

## 15. Deviations

**No deviation from the approved product baseline is proposed.** Every approved
flow, field type, hierarchy and rule in V0.7 Updated is preserved, including all
sixteen "Do Not Change" items.

Three items are recorded for transparency, none of which changes product
behaviour:

1. **Deliverable filename.** This report uses the package's name
   (`CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT.md`) rather than the task
   prompt's (`..._IMPLEMENTATION_REPORT.md`), resolved via the package's own
   authority hierarchy (§2).
2. **Activity-specific fields are modelled generically** (§7.2) rather than as
   six separate tables. The approved fields, their free-text/selectable types
   and their timing are unchanged; only the storage shape is an engineering
   choice.
3. **No map is proposed for V1** (§8.9), on the evidence that the approved
   mockup contains none. If CER expects a map, that is a product addition to
   raise now rather than an omission to discover at RTE07.

**R3 note — CER-approved changes are not deviations.** The A-3 multi-select
behaviour (§3.5) and every other decision in
`CER_ROUTE_RTE01_FINAL_CLOSURE_INSTRUCTIONS.md` are approved product changes,
not deviations proposed by the development team. Where they supersede the V0.7
mockup — the Activity selector becoming multi-select, and `End Work` becoming a
review action — the mockup is the superseded artefact.

**Internal names carry no product language.** `activity_block`,
`activity_selection`, `mileage_result`, `missing_location_event` and
`record_correction` (§7.1) are engineering constructs. Per CER's instruction
they introduce **no** visible concept and appear nowhere in the supervisor UX;
no "Activity Group", "Stop Group" or similar term exists in the product.

**No new product decision was introduced by the development team in R3.** Where
CER delegated a choice — client technology, routing provider, fuel source,
authentication mechanism, time handling, retry algorithms, freshness
thresholds, anomaly thresholds and the recovery-window duration — this report
records a *recommendation* with its rationale and the validation it depends on,
clearly labelled as delegated technical work (§14.2). Where CER left a
duration or threshold to policy (D-05 retention), the report declines to invent
one.

---

## 16. Evidence

All statements about the repository below were produced by running the commands,
not by inspection alone. Commands and real results:

| Check | Command | Result |
|---|---|---|
| Application composes and imports | `uv run python -c "import app.main"` | **OK** — `mode=DEV base_domain=localhost` |
| Invariant nets (wiring, permissions, public surface) | `uv run pytest tests/test_permission_catalog.py tests/test_public_surface.py tests/test_page_wiring.py tests/test_navigation_wiring.py` | **53 passed** in 12.8 s |
| Full backend suite, including integration against real PostgreSQL | `uv run pytest` | **266 passed** in 6 m 20 s |
| Frontend typecheck + lint | `cd app && npm run check` | **Clean** — `tsc` 0 errors, ESLint 0 findings |
| Migration heads | `uv run alembic -c app/alembic.ini heads` | `0001_foundation (head)` — single head, foundation only |

Repository findings and their evidence:

| Finding | Evidence |
|---|---|
| No business domain exists | `app/routers_api/` holds only companies, permissions, platform, regions, roles, rolepermissions(+approvals), usermanagement, users |
| All 14 React pages are platform administration | `app/components/react/pages/` |
| No geolocation code anywhere | Repo-wide search for `geolocation`/`latitude`/`Leaflet` returns only `node_modules` type definitions |
| No PWA, service worker or manifest | Repo-wide search for `serviceWorker`/`workbox`/`manifest.json` returns only `node_modules` |
| No Excel capability | No `openpyxl`/`xlsx` dependency in `pyproject.toml` |
| **The approved mockup has no map** | All 26 occurrences of "map" in `standalone.html` are `Array.map`; the 6 occurrences of "Location" are the *Area / Location* text field |
| **Mileage is attributed per leg at arrival in the approved UX** | `supAction()` in `standalone.html`: miles increase on `start-trip`, `arrive` (+8.2) and `arrive-home` (+14.4) — never continuously |
| The mockup's state machine matches §6.1 | `state.supState` values: `idle, working, pretrip, route, home-route, arrived, activity, complete, change, home, ended` |
| The mockup's fuel prices carry 4 decimals and a named source | `demo.fuel`: `{source:'AAA Georgia Avg.', scope:'Georgia', prices:{regular:4.0947,…}}` — informs §11.2 and D-06 |
| Session token is 24h with no refresh | `app/config.py:73` — `ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)` |
| Project identity still reads "CER Application" | `app/config.py:91` |
| **Uploaded photos already have EXIF GPS stripped** | `app/core/storage/media.py:19-20` and `tests/test_media_pipeline.py:8-9` — a reusable privacy control, should CER ever attach photos to activities (not in the current baseline) |
| **Email delivery exists and is reusable** (R2, for D-01 notifications) | `app/core/email/backends.py:310` `send_email`, with SMTP, M365 OAuth, console and memory backends selected from platform configuration |
| **A leader-elected scheduler exists** (R2) | `app/core/platform/scheduler.py:33` `PlatformScheduler` — APScheduler interval/cron jobs, suitable for grouped notification digests without duplicate sends |
| **In-platform notification does NOT exist** (R2) | No notification model or table in `app/core/models/` or `app/core/platform/models.py`; "notification" matches only UI `Alert` components and platform health checks. Recorded as a future implementation need, not invented (§8.6.3) |

**R3 verification — no product code was changed while applying CER's final
closure decisions.** Re-run after the R3 edits:

| Check | Command | Result |
|---|---|---|
| No source file modified | `find app tests \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.html" -o -name "*.scss" \) -mtime -2` (excluding `node_modules`, `__pycache__`, build output) | **0 files** |
| Application still composes | `uv run python -c "import app.main"` | **OK** |
| Invariant nets still green | `uv run pytest tests/test_permission_catalog.py tests/test_public_surface.py tests/test_page_wiring.py tests/test_navigation_wiring.py` | **53 passed** in 5.96 s |
| Working tree | `git status --short -- app tests` | No modifications; the only new file added by this work is this report |

The full 266-test suite and the frontend `npm run check` were run during the
original assessment and are recorded above; they were not repeated for a
documentation-only revision in which no source file changed.

**Note on what was and was not built.** No product code was written. The work
performed was inspection and verification of the existing environment, which the
RTE01 instructions permit. Nothing from RTE02–RTE11 has been started.

---

## 17. RTE02 Readiness

### 17.1 What is ready

- **The development environment runs and is verified**: 266 backend tests green
  against real PostgreSQL, frontend typecheck and lint clean, application
  imports, single migration head.
- **The platform foundation is in place and understood**: multi-tenancy,
  authentication, server-side authorization, audit, migrations, pagination,
  React/Jinja shell, CI.
- **The product is mapped end to end** to a technical proposal: lifecycle (§6),
  data model (§7), geolocation and mileage (§8), mobile strategy (§9), security
  and privacy (§10), fuel (§11), testing (§12).
- **The RTE02 work is unblocked and well-defined**: set `APP_*` identity,
  declare `route.*` capabilities, create the Supervisor and Route Admin roles,
  add the supervisor mobile shell alongside the admin shell, and build vehicles
  and the standardized lists.

### 17.2 What remains — and what it is not

**No CER product decision from RTE01 remains open.** What is listed below is
development work, not pending input:

| Remaining item | Type | Needed by |
|---|---|---|
| Client technology recommendation finalised (D-03) | Delegated technical, pending **V-1** | Before the supervisor shell hardens, RTE03 |
| Routing provider selected (D-04) | Delegated technical, pending **V-3** | Before RTE06 |
| Fuel source and ingestion selected (D-06 source) | Delegated technical | Before RTE09 |
| Authentication continuity design (D-09) | Delegated technical | Before RTE03 |
| Time/timezone implementation (D-10) | Delegated technical | Before RTE03 |
| Acquisition thresholds, recovery-window duration, anomaly thresholds | **Validation Required** — V-2, V-5 | Before RTE06 |
| Raw-location retention duration (D-05) | **CER policy/compliance**, not an RTE01 product decision | Before production |
| **In-platform notification capability** | **New platform work** (R-13) — the Foundation lacks it and D-01 requires it | With Admin notifications |
| Bounded contingency + sweeper so no Trip stays `Pending Calculation` | Engineering (R-14) | RTE06 |

### 17.3 Recommendation

**Release RTE02.** Nothing RTE02 delivers — foundation, access model,
navigation, profiles, vehicles, configuration — depends on any remaining item.
Every open thread is development or validation work that runs in parallel.

Suggested sequencing:

1. **Now** — begin RTE02; set `APP_*` identity and declare the `route.*`
   capabilities.
2. **During RTE02/RTE03** — run **V-1** and **V-4**; finalise D-03, D-09 and
   D-10.
3. **Before RTE06** — run **V-2**, **V-3** and **V-5**; finalise D-04 and the
   acquisition thresholds; design and test the mileage contingency sweeper.
4. **Before production** — obtain the D-05 retention duration from the
   applicable policy, and scope the in-platform notification capability.

**Proposed RTE01 status: Completed — ready for CER certification.** CER makes
the final checkpoint decision.

---

## 18. RTE01 Closure Validation (Revision R3.1)

Applying `CER_ROUTE_RTE01_FINAL_CLOSURE_INSTRUCTIONS.md` (R3) and CER's five
review corrections (R3.1, §18.4).

### 18.1 Closure matrix

| Item | R2 State | CER Final Decision | Sections Updated | Final Classification |
|---|---|---|---|---|
| **A-1** | Open ambiguity | `Start Work` may exist without an immediate Trip; no artificial Trip is created | §3.4, **§6.3** (new), §6.2, §7.1, §12.2 | **Resolved** |
| **A-2 / D-07** | Open / proposed auto-close | End Work is a review action with **Continue Working**; explicit *End Work Anyway* interrupts the Trip with no artificial `Arrived`; no auto-close of an Activity and no invented Outcome | §3.4, **§6.6**, §9.1, §9.2, §12.2, §14.1 | **Resolved** |
| **A-3** | R2 resolved | Multi-select **within the existing V0.7 context**; one execution block; Activity restoration on reopen; End Work rejected while Activity active | **§3.5**, §6.1, §6.2, §6.6, §6.7, §7.1, §7.3, §9.1, §12.2 | **Resolved** |
| **A-4** | Open ambiguity | `Change Plan` only while `IN_TRANSIT`; after `Arrived` a further displacement is a new Trip | §3.4, **§6.4**, §6.6, §12.2 | **Resolved** |
| **A-5 / D-10** | Open ambiguity | Product rule fixed (session = local date of `Start Work`; no supervisor timezone setting); implementation delegated | §3.4, **§6.5**, §7.1, §12.2, **§14.2** | **Delegated technical** |
| **A-6** | Open / proposed takeover | Same active Work Session **transfers/resumes** across devices; never a second session | §3.4, **§6.6**, §6.7, §9.2, §12.2 | **Resolved** |
| **A-7 / D-08.2** | Open ambiguity | Admin-only controlled corrections via Web Admin actions and backend jobs, fully audited; no silent recalculation; no direct DB editing | §3.4, **§10.6**, §8.5.5, §7.1, §12.2 | **Resolved** |
| **A-8 / D-06** | Open ambiguity | Fuel reference varies by scope × grade × date, with scheduled ingestion | §3.4, **§11** (rewritten), §7.1, §12.2 | **Resolved** |
| **D-01** | R2 resolved | Final hierarchy: **Fresh / Degraded Cached / Recovered / Missing**, recovery window, silent UX, Missing Location Event, **in-platform notification required** + optional email | §8.4, **§8.6.1** (four levels), §8.6.2, **§8.6.3**, §8.7, §7.1, §12.2 | **Resolved** |
| **D-02** | Open (was "blocks RTE06") | `Miles` = routed road distance between `Start Trip` and `Arrived`; four-state lifecycle; plausibility gate; historical fact, never auto-recalculated; breadcrumbs supporting only; **odometer out of V1**; **no Haversine as official Miles** | **§8.5** (rewritten), §7.1, §8.11, §12.2, §13, §14.1 | **Resolved** |
| **D-03** | Open product decision | **Mobile-only in V1**; client technology delegated | **§9.1**, §5.2, **§14.2**, §8.11 (V-1) | **Delegated technical** |
| **D-04** | Open product decision | Backend routing contract and constraints fixed; provider delegated | **§8.9**, §10.7, **§14.2**, §8.11 (V-3) | **Delegated technical** |
| **D-05** | Open / 90-day recommendation | Historical facts retained; raw location evidence separately limited; **no duration set here** | **§10.6**, §12.2, §14.1 | **Resolved principle** |
| **D-06** | Open product decision | Location/date/grade-variable fuel references + scheduled mechanism; missing price ⇒ `Pending Calculation`; source delegated | **§11** (rewritten), §7.1, **§14.2** | **Resolved** (source delegated) |
| **D-07** | Open product decision | End Work review/recovery rule (see A-2) | **§6.6**, §9.1, §14.1 | **Resolved** |
| **D-08** | Open product decision | One-time privacy notice (§10.5) + Admin-only corrections (§10.6) | **§10.5**, **§10.6**, §7.1, §14.1 | **Resolved** |
| **D-09** | Open product decision | Continuity requirement fixed; auth mechanism delegated | §4.3, §9.2, §13 (R-07), **§14.2** | **Delegated technical** |
| **D-10** | Open product decision | Time requirements fixed; implementation delegated (see A-5) | **§6.5**, **§14.2**, §12.2 | **Delegated technical** |

### 18.2 Required consistency answers

**1. Does any CER product ambiguity from RTE01 remain open?**
**No.** All eight `A-*` items and all ten `D-*` items are classified in §18.1
as Resolved, Resolved principle, or Delegated technical. §3.4 now presents the
ambiguities as closed with CER's decision against each, and §14 is a decision
*register*, not a request list.

**2. Does any section contradict the final decisions in this document?**
**No.** Superseded material was removed rather than annotated, and the document
was searched for each superseded assumption: one-Activity-per-arrival,
cross-context selection, hardcoded Outcome values, auto-close on End Work,
Change Plan after `Arrived`, dual active sessions, location failure blocking
work, cached evidence passed off as Fresh, email-only notification, Haversine as
official Miles, continuous GPS trace as the V1 source, odometer in any form,
indefinite `Pending Calculation`, the term "Unavailable" as a terminal mileage
state, automatic historical recalculation, a CER-prescribed routing provider, a
CER-chosen client technology, fixed 90-day retention, a static tenant fuel
price, direct-DB editing as normal operation, a CER-selected token lifetime, and
a supervisor timezone catalogue. The surviving mentions of odometer, Haversine
and 90 days are **explicit exclusion statements** (§14.3, §8.5, §8.11, §10.6),
which is what CER asked for.

**3. Does any section still present a delegated technical decision as if CER
must choose the implementation?**
**No.** D-03, D-04, D-09, D-10 and the D-06 source question are consolidated in
**§14.2** under "Technical decisions delegated to development", each with its
CER-fixed requirement, the evaluation axes CER specified, and the team's
recommendation. The §13 dependency table states explicitly that no CER product
decision remains, listing only operational access, spend approval and the
policy-owned retention duration.

**4. Does any section contain a superseded odometer/OCR/Haversine-official-
fallback requirement?**
**No.** Odometer capture, OCR, manual reconciliation, odometer tolerance and
the odometer-based V-3 gate are removed; V-3 is now a routing-provider
evaluation (§8.11). Haversine appears only as an internal diagnostic and as an
explicit prohibition on publishing it as `Miles` (§8.5.3).

**5. Does any section still auto-close an active Activity or invent an
Outcome?**
**No.** The R2 rule that marked an active block internally incomplete on End
Work has been **removed**. §6.6 now rejects the transition and returns the
authoritative active-Activity state; §3.5 and §9.1 state that the only exits are
`Complete` and `Leave` with their Outcome; §12.2 tests it.

**6. Does the report still contain any single-static-fuel-price assumption?**
**No.** §11 is rewritten around variability by geographic scope, grade and
effective date, with scheduled ingestion, and it records explicitly that the
earlier "one set of prices per company for V1" recommendation is withdrawn.

**7. Does the report treat Missing / Degraded / Recovered / Fresh location
according to the approved model?**
**Yes.** §8.6.1 defines all four levels with their storage, endpoint
eligibility and alerting, plus the three binding rules — never presented as
Fresh, never restamped to the event, never fabricated. `Degraded` is stated as
provenance metadata, **not** a fifth mileage state (§8.5.4).

**8. Does every mileage calculation have a path from transient `Pending
Calculation` to a terminal state?**
**Yes**, and it is treated as a real engineering obligation rather than a
diagram: §8.5.4 defines `Calculated`, `Not Calculable` and `Calculation Failed`
with their retention of reason, timestamp, evidence and audit; the rule that no
Trip may remain pending indefinitely is carried into a bounded contingency plus
a sweeper; it is tracked as **R-14**; and §12.2 requires a test that every Trip
reaches a terminal state.

**9. Was any product code modified?**
**No.** Verified by execution (§16): zero source files under `app/` or `tests/`
were modified, and the only new file in the working tree is this report.

**10. Was any RTE02+ work started?**
**No.** No product code, no migrations, no providers, no notifications, no
routing, no fuel ingestion, no authentication changes. Implementation
consequences discovered while applying these decisions are recorded as
Technical Recommendation, Validation Required, or future-checkpoint input —
never as new CER decisions.

**11. Can RTE01 now be proposed as `Completed — ready for CER certification`?**
**Yes.** That is the proposed status. All CER decisions are incorporated
throughout the body of the report; all prior findings and evidence remain
valid; no CER product ambiguity remains; and the recommendation to release
RTE02 is unchanged.

### 18.3 One item CER should be aware of, not a blocker

**R-13 — the in-platform notification capability does not exist in the
Foundation**, and D-01 requires it (§8.6.3, verified in §16). It is recorded as
**New / future implementation required**, and this report does **not** present
email-only as a permanent substitute. It needs scoping into whichever
checkpoint delivers Admin notifications; it does not affect RTE02 and does not
change any decision above.

### 18.4 R3.1 — CER review corrections

Five documentary corrections requested at CER's R3 review. **No decision was
reopened, no new product decision was introduced, and no code was modified.**

| # | CER's correction | What changed | Sections |
|---|---|---|---|
| **1** | §8.4 must state the **Recovery Window** explicitly before declaring Missing, consistent with §8.6.1 | The staged strategy is now six explicit stages — Fresh → exhaust current paths → Degraded Cached → **Recovery Window** → Recovered → Missing — with the rule that *an event may not be declared `Missing` while the recovery window is still open*, and an explicit mapping from the six stages onto the four evidence levels of §8.6.1. The governing D-01 quote also now names the recovery window | **§8.4**, §8.6.1 |
| **2** | Replace "in-platform and/or email" with the approved rule | The single remaining "and/or" (in the D-01 governing quote) now reads **in-platform notification — the required channel — with email as an optional additional channel**. Verified: the phrasing survives nowhere in the body of the report — the only remaining occurrences are in this row and in the R3.1 header note, where they name what was removed. All other mentions (§8.6.3, §13 R-13, §14.1, §17.2, §18.1) already carried the approved rule | **§8.4**, verified across §8.6.3, §13, §14.1, §17.2, §18.1 |
| **3** | §7.1 must align with §8.6.1 on how Fresh / Degraded / Recovered is persisted; **no later inference** | `location_fix` now carries **`evidence_level`** as a non-nullable `BusinessEnum` with a DB `CHECK`, set at acquisition time and immutable, plus `age_seconds` and `recovered_after_seconds`. A new subsection explains why inference is unsafe (thresholds and exhausted paths are not reconstructable later, so a config change would silently reclassify history) and records that `Missing` is **not** an `evidence_level` value — it is the absence of a fix plus a `missing_location_event` | **§7.1** (+ new subsection), §8.6.1 cross-reference |
| **4** | A-1 must not state that an Activity without a Trip is recorded against the Work Session | That bullet is **removed**. §6.3 now adds *Scope of A-1, stated precisely*: A-1 permits a Work Session without a Trip and **does not change the approved Activity lifecycle** — an Activity block still belongs to an `ARRIVED` Trip, and no path records an Activity directly against a session | **§6.3** |
| **5** | Replace absolute guarantees with a verifiable durability objective | "lose nothing" and "no supervisor action is ever lost" are **removed** from the body (they survive only in this row, naming what was removed). §8.8 now states a four-property objective — **durability, recovery, idempotency, ordering** — each with how it is verified, plus **known boundaries stated rather than glossed** (storage eviction, cleared site data, uninstall, device loss), and asks V-4 to *measure* the unsynchronised window rather than assume it is small. §9.2 points to it | **§8.8** (new objective table), §9.2, §12.2 (two new tests) |

**Consistency after R3.1.** The eleven answers in §18.2 are unchanged and remain
accurate: no CER product ambiguity is open, no section contradicts a final
decision, no delegated decision is presented as an open product question, and
the four evidence levels, mileage lifecycle and notification rule are stated
consistently throughout.

**Verification re-run after the R3.1 edits** (documentation only):

| Check | Command | Result |
|---|---|---|
| No source file modified | `find app tests \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.html" -o -name "*.scss" \) -mtime -2`, excluding `node_modules`, `__pycache__`, build output | **0 files** |
| Application still composes | `uv run python -c "import app.main"` | **OK** |
| Invariant nets still green | `uv run pytest tests/test_permission_catalog.py tests/test_public_surface.py tests/test_page_wiring.py tests/test_navigation_wiring.py` | **53 passed** |
| Working tree | `git status --short -- app tests` | No modifications; this report is the only file this work added |

**Proposed status is unchanged: `Completed — ready for CER certification`.**
