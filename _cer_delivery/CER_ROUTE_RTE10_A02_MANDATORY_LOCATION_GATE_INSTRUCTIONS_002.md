# CER Route — RTE10-A02 · Mandatory Location Permission Gate
## Development Instructions
### Revision 002 — Permission-First / Silent Signal Recovery

## 1. Context

CER Route already has a location architecture designed to continue operating when GPS/location signal is temporarily unavailable, using the existing fallback, cached evidence, recovery and offline mechanisms.

The product change in this checkpoint is **not** to redesign that technical recovery model.

The new requirement is narrower and explicit:

> **A Supervisor may operate CER Route only while location permission remains granted.**

The system must distinguish:

- **Permission state** — whether the user allows CER Route to access location.
- **Signal/evidence availability** — whether the device can currently return a usable coordinate.

These are different conditions and must not be treated as the same problem.

This checkpoint supersedes the previous tolerant policy only with respect to **permission denial/revocation**.

It does not reopen RTE06 mileage semantics, location fallback/recovery, offline behavior, or routing rules.

---

# 2. Confirmed Product Decision

## 2.1 Hard requirement

Location permission must remain:

`GRANTED`

for the Supervisor to start or continue into any **new operational action** in My Route.

If permission is:

- `PROMPT`
- `DENIED`
- `REVOKED`
- or equivalent browser/device state where CER Route does not have location access

the operational experience must be blocked by the mandatory location gate.

## 2.2 Signal loss does not block operation

If permission remains `GRANTED` but the device cannot currently provide a usable coordinate:

- do **not** block the Supervisor;
- do **not** show a new warning/message solely because of signal loss;
- keep using the already-approved backend/client location strategy;
- preserve Fresh / Cached / Recovery / Missing behavior;
- preserve offline behavior;
- preserve truthful evidence provenance;
- do not fabricate a coordinate.

The user-facing gate is about **permission**, not GPS quality.

---

# 3. Objective

Implement a mandatory location-permission gate for the Supervisor operational experience so that:

1. location permission is checked before CER Route allows operational use;
2. the user is clearly told that location is required;
3. the primary message/action is **Enable Location**;
4. if permission is denied or revoked, new operational actions cannot be executed;
5. permission is re-evaluated throughout the operational lifecycle so a user cannot grant access once and then revoke it without CER Route detecting it;
6. temporary signal loss with permission still granted continues under the existing silent fallback/recovery model;
7. open operational records can still be closed truthfully if permission is lost mid-operation;
8. once permission is granted again, CER Route automatically returns to the normal operational experience without requiring logout or a manual “Check Again” action.

---

# 4. Scope

Applies only to the **Supervisor / My Route / Execute** operational experience.

It does not gate:

- Login
- Today / Live
- Activity Explorer
- Reports
- Configuration
- Users
- Roles
- Vehicles
- Catalogs
- Other administrative surfaces

This is an operational permission gate, not an application-wide location requirement.

---

# 5. UX — Mandatory Location Gate

## 5.1 Full operational gate

When location permission is not `GRANTED`, the Supervisor must not see an actionable normal My Route state.

Instead, show a blocking operational screen/state centered on:

**Location Required**

CER Route requires location access to use My Route.

**[ Enable Location ]**

The exact visual treatment may follow the existing CER Route mobile design language.

The important behavior is:

- the gate cannot be dismissed;
- there is no “Continue without location”;
- there is no bypass;
- there is no “Check Again” action;
- normal operational actions are unavailable behind the gate.

## 5.2 Enable Location

`Enable Location` is the single primary action.

Development must implement the correct browser/device behavior according to the actual permission state and supported APIs.

Examples:

- if the browser can still present the native permission request, invoke it;
- if the browser has already placed the site in a denied/revoked state and cannot re-prompt, keep the user inside the same mandatory gate and provide the minimum contextual guidance necessary to enable location from browser/site/device settings.

Do not add a separate manual `Check Again` flow.

CER Route must re-evaluate permission automatically when technically possible.

---

# 6. Permission State Is the Gate

The product rule is:

```text
permission = GRANTED
    → operational experience available
    → location acquisition continues using existing best-effort logic

permission != GRANTED
    → mandatory Location Required gate
    → no new operational action
```

Do not make `LOCATION_READY` depend on receiving a Fresh GPS coordinate.

For this checkpoint:

`LOCATION_PERMISSION_READY = permission is GRANTED`

That is the hard prerequisite.

Coordinate quality remains governed by the existing location domain.

---

# 7. When Permission Must Be Re-Evaluated

CER defines the required outcome, not the exact browser implementation.

Development must determine the technically correct combination of browser/device events, permission APIs and operational preflight checks.

The system must be able to detect permission loss/revocation without depending only on the first Start Work request.

At minimum, the implementation must ensure re-evaluation around the following moments:

- entering My Route;
- before Start Work;
- before starting a new Trip / Depart;
- before Change Plan;
- before starting a new Activity;
- before any other transition that opens a new operational state;
- when the app/page returns from background;
- after page reload/resume;
- when the browser exposes a permission-state change event.

Development may optimize the exact timing/mechanism, but the user must not be able to continue starting new operational work after permission is revoked.

Do not repeatedly show native permission prompts while the state remains granted.

---

# 8. Existing Open Operation — Closure Exception

CER confirms the existing exception:

> If permission is lost after an operation has already started, the user must be able to close the current operational record truthfully.

Examples:

- Arrived / Trip completion
- Arrive Home
- Activity completion
- Outcome / Notes completion
- End Work
- existing approved interruption/closure flows

After the current operation is closed:

- if permission is still not `GRANTED`, return immediately to the mandatory Location Required gate;
- no next operational action can begin.

This exception exists only to avoid trapping open operational records.

It is not a bypass for starting new work.

---

# 9. Signal Loss / Rural / Indoor Operations

No new visible warning is required solely because GPS/location signal is temporarily unavailable while permission remains granted.

The existing design remains authoritative:

```text
Fresh
  ↓
Cached / degraded evidence where valid
  ↓
Recovery
  ↓
Missing
```

CER Route must continue to:

- attempt location acquisition;
- preserve evidence quality/provenance;
- recover when signal returns;
- work with the existing offline queue;
- avoid fabricated coordinates;
- keep missing/recovered evidence truthful.

The Supervisor should not be blocked merely because the environment prevents a usable GPS fix for minutes or hours.

This is especially important for:

- rural areas;
- industrial plants;
- warehouses;
- buildings with weak satellite reception;
- temporary network loss.

---

# 10. Offline Behavior

Offline operation remains supported.

The system must not confuse:

`no Internet`

with:

`location permission denied`

Examples:

```text
Permission GRANTED + offline + location available/unavailable
    → operate under existing offline/recovery rules

Permission DENIED/REVOKED
    → block new operational actions regardless of network state
```

Do not change the current offline queue architecture in this checkpoint.

---

# 11. Server-Side Enforcement

Frontend blocking alone is insufficient.

Development must inspect the existing command/API architecture and enforce the strongest technically valid server-side invariant available without inventing guarantees the browser cannot prove.

Required outcome:

> A new operational transition must not be accepted when the client has not satisfied the mandatory location-permission precondition defined by this checkpoint.

The implementation must remain compatible with:

- offline queue/replay;
- existing location evidence correlation;
- Work Session recovery/resume;
- multi-device behavior.

If the server cannot independently know the browser's OS permission state, document the trust boundary clearly and implement a technically defensible preflight/evidence contract rather than pretending the server can see something it cannot.

Do not weaken the frontend gate because of that limitation.

---

# 12. Audit / Evidence

Record enough operational evidence to distinguish:

- permission request initiated;
- permission granted;
- permission denied;
- permission revoked where detectable;
- permission restored;
- blocked attempt to start a new operational action;
- closure of an already-open operation while permission was unavailable.

Do not add raw coordinates to audit logs unnecessarily.

Signal loss itself continues to use the existing location evidence/recovery model and does not need a new user-facing compliance event merely because no fix was available.

---

# 13. Reload / Foreground / Multi-Device

## Reload

On reload:

- re-evaluate permission;
- if not granted → show Location Required gate;
- if granted → restore the correct operational state;
- do not rely on a stale in-memory permission value.

## Background / Foreground

When returning to foreground:

- re-evaluate permission before enabling the next new operational action.

## Multi-device

Permission is device/browser specific.

A second device must satisfy its own location-permission gate.

It cannot inherit the first device's granted state.

Existing Work Session uniqueness/resume rules remain unchanged.

---

# 14. Operational Action Matrix

Development must inspect the current state machine and produce a complete matrix.

At minimum:

| Action | New operational state? | Requires permission GRANTED? | Allowed if permission lost mid-operation? |
|---|---:|---:|---:|
| Enter My Route | operational entry | Yes | N/A |
| Start Work | Yes | Yes | No |
| Depart / Start Trip | Yes | Yes | No |
| Change Plan | Yes | Yes | No |
| Start Activity | Yes | Yes | No |
| Arrived / close active Trip | No — closes current | No, if already open | Yes |
| Complete Activity | No — closes current | No, if already open | Yes |
| Arrive Home | No — closes current Trip | No, if already open | Yes |
| End Work | No — closes current session | No, if already active | Yes |

Development must validate the actual command/state model and add any missing transitions.

Do not rely only on button names.

---

# 15. Acceptance Criteria

The checkpoint is ready for CER certification only when:

1. My Route is blocked when location permission is not granted.
2. The gate clearly states that location is required.
3. The primary action is `Enable Location`.
4. There is no dismiss/continue-without-location option.
5. There is no `Check Again` button.
6. When permission becomes granted, CER Route automatically restores operational access.
7. Start Work requires granted permission.
8. Every new operational state transition requires granted permission.
9. Revoking permission during the workday prevents the next new operational action.
10. An already-open Trip can still be closed.
11. An already-open Activity can still be completed.
12. An active Work Session can still be ended.
13. After closure, denied/revoked permission returns the user to the gate.
14. Permission is re-evaluated on reload/resume/foreground and at appropriate operational preflight points.
15. Permission `GRANTED` + no GPS fix does **not** block operation.
16. No new signal-loss warning is required for the Supervisor.
17. Existing Fresh/Cached/Recovery/Missing behavior remains intact.
18. Existing offline behavior remains intact.
19. No fabricated location is introduced.
20. No continuous off-work/background tracking is introduced.
21. Admin/non-operational surfaces remain unaffected.
22. Server/API bypass risk is addressed with the strongest valid enforcement supported by the architecture.
23. Existing Work Session / Trip / Activity / location / mileage regressions remain green.
24. No unexplained Partial / Gap / Blocked item remains inside this checkpoint.

---

# 16. Tests Required

## Permission states

- initial permission undecided → Location Required gate;
- Enable Location → permission granted → operational experience;
- explicit denied → gate persists;
- revoked after previously granted → gate applied before next new action;
- permission restored externally → application detects recovery and removes gate automatically.

## New actions

Verify denied/revoked permission blocks:

- Start Work;
- Start Trip / Depart;
- Change Plan;
- Start Activity;
- every other command identified as opening a new operational state.

## Closure exception

- active Trip + permission revoked → Arrived remains possible;
- active Activity + permission revoked → completion remains possible;
- active Work Session + permission revoked → End Work remains possible;
- after closure → next action blocked until permission returns.

## Signal loss

With permission still `GRANTED`:

- no Fresh location;
- cached/recovery path;
- prolonged missing fix;
- offline state.

Verify the workflow remains operational according to the existing location design and no new blocking gate is triggered.

## Resume

- reload while granted;
- reload while denied;
- background → revoke → foreground;
- second device with independent permission state.

## Regression

Run affected suites for:

- Work Session;
- Trip;
- Change Plan;
- Activity;
- HOME;
- End Work;
- offline/replay;
- location evidence/recovery;
- mileage;
- tenant isolation;
- mobile browser.

Tests must be discriminating: removing the permission gate must cause the new tests to fail.

---

# 17. Do Not Change

Do not change:

- Official Miles definition;
- TomTom/routing behavior;
- fallback/cache/recovery semantics;
- offline queue design;
- odometer/OCR behavior;
- Today / Live;
- Activity Explorer reporting;
- Reports;
- role/capability architecture;
- hierarchy;
- vehicle rules;
- Work Session uniqueness;
- privacy boundary outside active work;
- location retention rules.

Do not resume RTE10-A01 as part of this checkpoint.

---

# 18. Development Autonomy

Development owns the technical implementation details, including:

- browser permission API usage;
- when/how native permission requests can legally/technically be triggered;
- permission-change listeners;
- focus/visibility/reload hooks;
- operational preflight implementation;
- server-side enforcement mechanism;
- mobile-browser differences.

CER defines the required behavior:

> Permission must remain granted for My Route operational use.

Do not hardcode a timing strategy in product behavior if the browser platform requires a different technically correct implementation.

---

# 19. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE10_A02_MANDATORY_LOCATION_GATE_REPORT_001.md`

Include:

1. Executive Result
2. Previous vs New Permission Policy
3. Permission State Model
4. Location Gate UX
5. Enable Location Behavior
6. Permission Re-Evaluation Strategy
7. Operational Action Matrix
8. Mid-Operation Revocation / Closure Exception
9. Signal Loss / Recovery Preservation
10. Offline Behavior
11. Server-Side Enforcement / Trust Boundary
12. Reload / Foreground / Multi-Device
13. Audit
14. Tests / Regression
15. Expected → Implemented → Evidence → Gap
16. Remaining Issues
17. Proposed Status

---

# 20. Proposed Status Rule

If all acceptance criteria are green:

`RTE10-A02 MANDATORY LOCATION PERMISSION GATE COMPLETE / READY FOR CER VALIDATION`

Development must not declare it closed.

CER owns final certification.

If a genuine product decision is discovered:

`RTE10-A02 BLOCKED — CER DECISION REQUIRED`

with:

`fact → impact → options → recommendation`

---

# 21. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE10_A02_MANDATORY_LOCATION_GATE_REPORT_001.md`

**STOP.**

Do not start Reports.

Do not start RTE09.

Do not resume RTE10-A01.

Do not modify Today / Live or Activity Explorer.

Wait for CER review and field validation.
