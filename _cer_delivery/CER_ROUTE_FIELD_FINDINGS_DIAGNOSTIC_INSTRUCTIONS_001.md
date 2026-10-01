# CER Route — Field Findings Diagnostic
## Agent Instructions — RTE06 Field Validation / Odometer + Geolocation
### Revision 001

**Mode:** Diagnostic only.  
**Do not implement fixes yet unless explicitly authorized after CER reviews the diagnosis.**  
**Do not start RTE07.**

---

# 1. Context

CER executed the first physical-field iteration on **Android / Chrome**.

The operational experiences were exercised successfully enough to continue the field review, but two findings were observed:

1. **Odometer photo flow / navigation**
   - When the Supervisor takes the odometer photo, the application leaves the odometer experience and returns to the main activity/workbench screen.
   - This was observed in both:
     - START odometer flow before travel;
     - END odometer flow when ending work.
   - The user can become disoriented because the odometer task is still unresolved but the UI context changes.

2. **Geolocation robustness**
   - The application allows the operational action to proceed while location acquisition is best-effort.
   - CER wants to verify that the capture itself is sufficiently robust and that low-quality/stale/ambiguous location evidence is not being treated as stronger evidence than it really is.

Field screenshots were captured from Android showing:
- the odometer capture/confirmation experience;
- Android/Chrome geolocation permission with **Precise** selected.

---

# 2. Important Product Baseline — Do Not Reinterpret

## 2.1 Odometer

Approved behavior remains:

- START odometer evidence is required before the first vehicle Trip when an applicable vehicle exists;
- photo + Supervisor-confirmed reading is the normal evidence path;
- OCR is assistive, never authoritative;
- if OCR fails but the photo is valid, the Supervisor may type the visible reading and confirm it;
- no-photo manual entry remains an Admin-approved exception;
- END odometer follows the approved END evidence / exception rules;
- odometer evidence is independent from routing mileage.

The odometer experience must not become ambiguous merely because the camera application/browser temporarily takes focus.

## 2.2 OCR

CER already has a separate planned production-hardening checkpoint for OCR:

`RTE10-A01 — Odometer OCR Production Hardening & Validation`

Therefore distinguish explicitly between:

**A. OCR recognition not yet production-integrated**  
and  
**B. the odometer photo/navigation flow losing or changing UI context after returning from camera capture.**

A missing/incomplete OCR engine can explain a missing automatic reading suggestion.

It does **not by itself** explain why the user is navigated away from the odometer task after taking the photo.

Do not merge these two findings without evidence.

## 2.3 Geolocation

The approved RTE06 model is:

`event-based + staged best-effort + non-blocking operational action`

The Supervisor's Work Session / Trip / Activity action must not be blocked solely because GPS is slow, unavailable, denied, backgrounded, or ultimately Missing.

Therefore:

> “The user can still mark/continue while GPS is not perfect” is not automatically a defect.

The diagnostic must instead determine whether CER is capturing, classifying, preserving and using location evidence with sufficient quality and truthfulness.

Do **not** introduce a hard GPS gate in this diagnostic.

---

# 3. Objective

Determine, from the repository and the Android field evidence:

1. the exact root cause of the odometer navigation/context-loss behavior;
2. whether it is:
   - an existing RTE04/RTE05 odometer UX defect/regression;
   - Android/Chrome camera lifecycle behavior not handled correctly;
   - state persistence/restoration failure;
   - an OCR-related issue;
   - another cause;
3. whether START and END share the same root cause/component;
4. whether any odometer evidence is lost or only the visual context changes;
5. whether the current geolocation pipeline is behaving according to RTE06;
6. whether real Android evidence reveals a quality weakness that should be hardened before final RTE06 certification;
7. what change, if any, is required;
8. estimated effort for the smallest compliant correction.

---

# 4. Diagnostic A — Odometer Photo / Navigation

Reproduce and trace both paths independently.

## A1 — START odometer

Trace:

```text
Start Work
→ START odometer pending
→ open camera
→ take photo
→ return to Chrome/CER Route
→ observed screen/state
```

Determine:

- route before opening camera;
- component/state before opening camera;
- whether the browser page is reloaded, resumed, recreated or merely refocused;
- whether `visibilitychange`, `pageshow`, `focus`, history/popstate, router restoration, component remount or another lifecycle event executes;
- what callback runs after the photo is selected/captured;
- whether photo evidence is uploaded/persisted;
- whether the odometer evidence state remains pending;
- whether the Workbench/main screen is being chosen by default because UI state was lost;
- whether the user can return to the unresolved odometer task;
- whether Start Trip remains correctly guarded until the START reading is resolved.

## A2 — END odometer

Trace:

```text
End Work flow
→ END odometer capture
→ open camera
→ take photo
→ return to Chrome/CER Route
→ observed screen/state
```

Determine the same items and whether:

- the Work Session has already ended;
- END evidence remains pending correctly;
- the UI has a deterministic way to return to the END odometer completion task;
- the behavior is caused by the same component/state-restoration path as START.

## A3 — Photo persistence

For START and END verify separately:

- image selected/captured;
- image upload/storage state;
- confirmed reading state;
- OCR suggestion state, if any;
- evidence row/state;
- whether retaking the photo replaces the correct pending evidence;
- whether browser/app restart loses or preserves the pending odometer task.

## A4 — OCR wiring

Inspect the actual runtime and report:

- which odometer reader implementation is active;
- whether a production OCR engine is currently wired;
- whether the current build still uses a no-suggestion / development implementation;
- whether OCR is invoked after a photo;
- whether a recognition failure changes navigation;
- whether the navigation problem exists even with OCR bypassed/manual confirmation.

**Do not implement RTE10-A01 as part of this diagnostic.**

If production OCR is not yet implemented, state that clearly and classify it against the already-planned `RTE10-A01`, not as an accidental RTE06 omission.

## A5 — Required reproduction matrix

At minimum:

| Case | START | END |
|---|---:|---:|
| Take photo and return normally | required | required |
| Retake photo | required | required |
| Photo with no OCR suggestion | required | required |
| Manual confirmed reading from valid photo | required | required |
| Browser loses focus during camera | required | required |

If Android physical hardware is not available to Development, reproduce as far as possible and identify exactly what CER must repeat on-device after a fix.

---

# 5. Diagnostic B — Geolocation Robustness

Do not diagnose “action continues without GPS” as a defect by itself.

Diagnose the **evidence quality pipeline**.

## B1 — Inspect the actual Android field rows

Using the timestamps / Supervisor / tenant from the field run, inspect the corresponding:

- `location_fix`;
- `missing_location_event`;
- acquisition attempts/evidence;
- event kind;
- `evidence_level`;
- `accuracy_m`;
- source age / cached age;
- `device_captured_at`;
- `server_received_at`;
- permission/acquisition state;
- recovery outcome.

If the exact field rows cannot be identified, state what identifier/timestamp CER must provide.

## B2 — Permission quality

The physical Android screenshot shows **Precise** selected.

Determine:

- whether the application can distinguish behavior produced by Android Precise vs Approximate permission from the evidence it receives;
- whether the browser/API exposes enough information directly or whether only measured `accuracy` can be relied upon;
- whether approximate/coarse results could currently be accepted as a stronger evidence level than their actual accuracy justifies.

Do not assume browser behavior. Measure/read the implementation.

## B3 — Fresh quality

Check whether `fresh` means only “new/current acquisition” or also enforces an acceptable accuracy threshold.

If a newly captured point is extremely inaccurate, determine what happens today:

- accepted as `fresh`;
- degraded;
- sent to recovery;
- rejected and eventually Missing.

State the exact current rule.

## B4 — Cached quality

Verify:

- maximum cached age;
- maximum cached accuracy;
- whether both must pass;
- whether stale but accurate evidence is rejected;
- whether recent but very inaccurate evidence is rejected;
- whether original timestamp/age is preserved after delayed upload.

## B5 — Recovery

Verify in the field path:

- when recovery starts;
- recovery window;
- whether a better point replaces only pending evidence, never an already accepted authoritative point;
- whether recovered evidence uses the actual recovery capture time;
- whether operational actions remain non-blocking.

## B6 — Missing truthfulness

Verify that Missing occurs when acquisition genuinely fails after the approved staged path and not because:

- evidence was lost client-side;
- exact correlation failed;
- the browser was briefly backgrounded and a valid later point arrived within the allowed recovery path.

## B7 — Routing consumption

Verify that routing mileage does not treat a rejected or Missing waypoint as a valid official point.

Confirm current behavior for:

- low-accuracy accepted location;
- rejected cached candidate;
- Missing required waypoint;
- snap-radius rejection;
- routing plausibility checks.

---

# 6. Hardening Analysis Required

If the current implementation is compliant but the Android field test shows that location quality can be improved, recommend hardening without changing the non-blocking product rule.

Evaluate only evidence-backed options such as:

- accuracy acceptance thresholds;
- different treatment of newly acquired but low-accuracy fixes;
- staged retry/recovery tuning;
- cached age/accuracy tuning;
- better diagnostics/telemetry;
- explicit handling of coarse/approximate evidence if technically detectable;
- field calibration of current thresholds.

For each recommendation provide:

```text
Current behavior
Observed weakness
Proposed hardening
User impact
Data/mileage impact
Security/privacy impact
Estimated effort
Requires CER decision? yes/no
```

Do **not** introduce:

- continuous tracking;
- background tracking claims;
- a GPS hard-block;
- new visible GPS-warning workflow;
- geofencing;
- a new provider;
- unrelated maps/navigation scope.

unless the diagnostic demonstrates that an approved requirement cannot be met without one, in which case STOP and present the decision to CER.

---

# 7. Classification Rules

Classify every finding as one of:

- `AS-BUILT / CONFIRMED`
- `REGRESSION`
- `NOT IMPLEMENTED / GAP`
- `PENDING FIELD EVIDENCE`
- `TECHNICAL DEBT`
- `EXPECTED / BY DESIGN`
- `DECISION REQUIRED`
- `BLOCKED`

Examples:

- operational action continues while GPS is unavailable → likely `EXPECTED / BY DESIGN`;
- valid location is accepted despite violating the approved quality rule → `REGRESSION` or `GAP`;
- camera returns user to unrelated screen while odometer task remains unresolved → likely UX/state `REGRESSION`, subject to diagnosis;
- productive OCR not wired yet → classify against planned `RTE10-A01`, not automatically as an RTE06 regression.

---

# 8. Impact Analysis

For each confirmed defect state whether it impacts:

- RTE04 Odometer;
- RTE05 Workbench;
- RTE06 Field Validation;
- RTE06 final certification;
- RTE10-A01 OCR;
- future RTE07;
- no other scope.

Explicitly answer:

### Q1
Can RTE06 be finally certified with the current odometer navigation behavior?

### Q2
Is the observed odometer behavior caused by unfinished OCR, independent of OCR, or mixed?

### Q3
Does the Android field evidence demonstrate a geolocation defect, or only the approved non-blocking behavior?

### Q4
What exact hardening, if any, is required before final RTE06 certification?

### Q5
Can the fix be completed as a small closure delta, or does it require reopening a larger checkpoint?

---

# 9. Estimation

For every recommended correction provide:

| Item | Minimum | Probable | High | Main uncertainty |
|---|---:|---:|---:|---|
| Odometer navigation/state | | | | |
| Geolocation hardening, if required | | | | |
| Tests/regression | | | | |
| Field revalidation required from CER | | | | |

Separate implementation time from CER physical-device revalidation.

Do not include Git/MR administrative time as product-development effort.

---

# 10. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_FIELD_FINDINGS_DIAGNOSTIC_REPORT_001.md`

Recommended sections:

1. Executive Result
2. Field Evidence Received
3. START Odometer Reproduction
4. END Odometer Reproduction
5. Root Cause
6. OCR Runtime Status
7. Odometer Evidence Integrity
8. Android Geolocation Evidence
9. Location Quality Rules — As Built
10. Robustness Findings
11. Routing / Mileage Impact
12. Security / Privacy Impact
13. Expected vs Implemented
14. Classification
15. Required Corrections
16. Effort Estimate
17. Impact on RTE06 / RTE10-A01 / RTE07
18. Decisions Required from CER
19. Recommendation

Keep the report focused on evidence and delta. Do not repeat the whole project history.

---

# 11. STOP

After delivering the diagnostic report:

**STOP.**

Do not implement the proposed fixes.

Do not start RTE07.

CER will decide from the evidence whether:
- RTE06 can be certified as-is;
- a small RTE06 field-finding closure delta is required;
- part of the finding belongs to `RTE10-A01`;
- geolocation thresholds need adjustment.
