# CER Route — RTE06 Field Corrections & Hardening
## Agent Implementation Instructions — Revision 001

**Purpose:** implement the corrections authorized by CER after physical Android field validation and the diagnostic findings.

**Mode:** implementation + validation + closure report.

**Do not start RTE07.**

---

# 1. Context

CER completed the first physical Android/Chrome field iteration for RTE06.

The diagnostic identified two independent findings:

1. **F-1 — Recovered geolocation accepts any accuracy**
   - `fresh` currently applies a maximum accuracy threshold of **100 m**.
   - `degraded_cached` currently applies **500 m + age** limits.
   - `recovered` currently has **no accuracy threshold**.
   - As a result, a point rejected earlier for poor accuracy can later be accepted as `recovered`, including values such as ~2,000 m.
   - `for_trip_waypoints()` consumes accepted `location_fix` rows and does not separately re-filter by `evidence_level` or `accuracy_m`, so an inaccurate accepted recovered point can become an authoritative routing waypoint.
   - This is classified by CER as **REGRESSION / blocking RTE06 final certification**.

2. **Odometer camera return loses the active odometer task**
   - On physical Android, after taking the odometer photo, the user can return to the main activity/workbench screen instead of remaining in the pending odometer flow.
   - Observed in both:
     - START odometer;
     - END odometer.
   - Diagnostic indicates `capturandoInicio` / `revisandoCierre` are volatile UI state and are not persisted.
   - The behavior is independent of OCR.
   - This is classified by CER as **NOT IMPLEMENTED / UX STATE-RESTORATION GAP**.

OCR remains separately planned under:

`RTE10-A01 — Odometer OCR Production Hardening & Validation`

Do not implement productive OCR in this delta.

---

# 2. CER Decisions

These decisions are final for this implementation.

## D-FIELD-01 — Recovered accuracy threshold

`recovered` must meet the same maximum accuracy requirement as `fresh`:

```text
accuracy_m <= 100
```

Prefer reusing the existing configurable Fresh accuracy threshold instead of creating a second independent Recovery threshold, unless the current architecture makes reuse technically unsafe or ambiguous.

Do not hard-code duplicate configuration if one authoritative threshold can serve both.

## D-FIELD-02 — Recovery candidate above threshold

If a Recovery acquisition returns a point with accuracy worse than the approved threshold:

```text
accuracy_m > 100
```

then:

1. do **not** create an authoritative `location_fix`;
2. record the attempt/rejection evidence using the existing privacy rules;
3. continue attempting recovery while the approved Recovery Window remains open;
4. if the window expires without an acceptable point, create `MissingLocationEvent`.

The rejected candidate's coordinates must **not** be stored merely because the candidate existed.

Preserve available diagnostic metadata such as:
- rejected accuracy;
- age/source age when applicable;
- attempt evidence;
- acquisition/permission state;
- timestamps already allowed by the model.

## D-FIELD-03 — Missing reason

Reuse an existing `MissingLocationEvent.reason_code` only if its meaning precisely represents:

> location was acquired but every candidate failed the approved accuracy requirement before the recovery window expired.

If no existing reason code expresses that fact accurately, CER authorizes adding a new specific reason code and the required database/catalog constraint update.

Do not overload an unrelated reason.

Technical naming is delegated to Development.

## D-FIELD-04 — Non-blocking behavior remains

Do **not** change the approved product rule:

```text
event-based + staged best-effort + non-blocking operational action
```

The operational action must still proceed when geolocation is unavailable, slow, denied or ultimately Missing.

This correction hardens **evidence acceptance**, not user blocking.

## D-FIELD-05 — Odometer camera return / state restoration

After returning from camera/photo selection, CER Route must restore the unresolved odometer task rather than leave the user on an unrelated screen.

### START expected behavior

```text
START odometer pending
→ Take photo
→ camera / file capture
→ return to CER Route
→ START odometer remains/resumes as the active task
→ show available photo/reading state
→ Supervisor confirms/corrects reading
→ START evidence resolves
→ first Trip may proceed
```

### END expected behavior

```text
END odometer task
→ Take photo
→ camera / file capture
→ return to CER Route
→ END odometer completion remains/resumes as the active task
→ show available photo/reading state
→ Supervisor confirms/corrects reading
→ END evidence resolves according to the already-approved END rules
```

If the browser/page was recreated before the file `onChange` completed and therefore no photo was persisted:

```text
return to CER Route
→ detect unresolved odometer task
→ reopen/resume that odometer task
→ request a new capture
```

Do not send the user to an unrelated activity/dashboard state and leave them to discover the pending odometer requirement manually.

## D-FIELD-06 — OCR remains out of scope

The current `NoSuggestionReader` / lack of productive OCR is **not** corrected here.

OCR remains assistive and belongs to `RTE10-A01`.

This delta must work correctly when OCR returns no suggestion.

---

# 3. Objective

Implement the smallest production-safe correction that:

1. prevents low-quality Recovery fixes from becoming authoritative location evidence;
2. preserves the staged Recovery process and non-blocking workflow;
3. produces truthful Missing evidence if no acceptable Recovery point is obtained;
4. restores the START and END odometer task after Android camera/browser focus or page recreation;
5. preserves all existing odometer evidence and guards;
6. does not introduce OCR production scope;
7. leaves RTE06 ready for physical revalidation and final CER certification.

---

# 4. Scope

## 4.1 Geolocation

Implement and validate:

- accuracy enforcement for `recovered`;
- reuse of the Fresh maximum accuracy policy where appropriate;
- rejected Recovery candidate handling;
- Recovery retries within the existing window;
- Missing creation after Recovery exhaustion;
- exact reason-code handling;
- preservation of privacy rules;
- routing waypoint safety;
- regression of Fresh and Degraded Cached behavior.

## 4.2 Odometer

Implement and validate:

- durable/restorable UI task state for START odometer;
- durable/restorable UI task state for END odometer;
- deterministic restoration after camera focus loss;
- deterministic restoration after browser/page recreation;
- correct state when the photo already persisted;
- correct state when the photo did not persist;
- Start Trip guard remains intact;
- END Option B / existing END semantics remain intact.

## 4.3 Tests and closure

- discriminating automated tests;
- relevant browser tests;
- regression of RTE03–RTE06 impacted surfaces;
- clear physical revalidation instructions for CER;
- final implementation report.

---

# 5. Out of Scope

Do not implement or redesign:

- productive OCR engine;
- OCR vendor/provider selection;
- continuous location tracking;
- background location tracking;
- geofence;
- visible GPS warning flow;
- maps/navigation;
- new routing provider;
- new mileage definition;
- new Work Session states;
- new Trip states;
- new Activity states;
- new odometer business rules;
- new roles or permissions;
- RTE07;
- hierarchy / roles sprint;
- unrelated UI redesign.

---

# 6. Geolocation Functional Requirements

## GEO-01 — Fresh remains unchanged

The existing Fresh acquisition behavior remains authoritative.

Confirm the actual configurable threshold used by Fresh.

Expected:

```text
fresh candidate
AND accuracy_m <= approved Fresh threshold
→ acceptable Fresh evidence
```

A newly acquired point above the Fresh accuracy limit must not become authoritative merely because it is current.

## GEO-02 — Cached remains unchanged

Existing Degraded Cached rules remain:

- age threshold;
- accuracy threshold;
- both must pass.

Do not loosen them.

## GEO-03 — Recovered uses approved accuracy threshold

Recovered is acceptable only if:

```text
recovery acquisition succeeds
AND accuracy_m <= approved Fresh accuracy threshold
```

A Recovery point above the threshold is a rejected candidate, not a `location_fix`.

## GEO-04 — Recovery continues after rejected candidate

A low-quality Recovery candidate must not automatically terminate the Recovery Window.

Continue attempts according to the existing bounded Recovery design while time remains.

Do not busy-loop or exceed the approved bounded behavior.

## GEO-05 — Recovery exhaustion

If the Recovery Window expires without any acceptable point:

```text
→ MissingLocationEvent
```

The event must truthfully indicate that acquisition occurred but candidates failed quality requirements if that was the actual cause.

## GEO-06 — No rejected coordinates

A rejected candidate may contribute approved diagnostic metadata but not persisted rejected coordinates.

Maintain the already-approved privacy boundary.

## GEO-07 — Authoritative waypoint safety

Verify that only accepted `location_fix` rows can enter official routing mileage waypoints.

At minimum prove:

- rejected Recovery candidate → never used as waypoint;
- Missing required waypoint → existing `Not Calculable` behavior;
- accepted Recovery <= threshold → may be used normally;
- Haversine, breadcrumbs and odometer remain non-authoritative.

## GEO-08 — Approximate Android permission

Do not invent platform detection that the browser does not expose.

If browser APIs do not distinguish Precise vs Approximate directly, continue relying on actual measured accuracy and the approved thresholds.

Document the as-built limitation.

---

# 7. Geolocation Tests Required

Create direct tests for at least:

### G1 — Recovered 50 m
- Recovery candidate accuracy = 50 m;
- accepted as `recovered`;
- authoritative `location_fix` exists.

### G2 — Recovered exactly at threshold
- candidate accuracy = configured threshold;
- accepted.

### G3 — Recovered above threshold
- candidate accuracy = threshold + 1;
- not accepted;
- no authoritative `location_fix` for that candidate.

### G4 — Recovered grossly inaccurate
- candidate accuracy ≈ 2,000 m;
- rejected;
- never enters `for_trip_waypoints()`.

### G5 — Bad candidate then good candidate
Within the same Recovery Window:

```text
candidate A > threshold → rejected
candidate B <= threshold → accepted
```

Result:
- one authoritative recovered point;
- correct actual capture timestamp;
- rejected candidate does not become authoritative.

### G6 — All Recovery candidates bad
- every candidate above threshold;
- window expires;
- one truthful `MissingLocationEvent`;
- no authoritative location fix.

### G7 — Missing reason
- exact expected reason code;
- reason is not an unrelated reused value.

### G8 — Privacy
- rejected candidate accuracy/attempt metadata may exist;
- rejected candidate coordinates do not.

### G9 — Fresh regression
- Fresh <= threshold accepted;
- Fresh > threshold not incorrectly accepted.

### G10 — Cached regression
- both age and accuracy constraints still enforced.

### G11 — Mileage
- rejected Recovery waypoint cannot yield official routed mileage;
- existing Missing waypoint terminal behavior remains correct.

---

# 8. Odometer Functional Requirements

## ODO-01 — Task state comes from durable/domain truth

Do not make correctness depend exclusively on transient React `useState` flags such as:

- `capturandoInicio`;
- `revisandoCierre`;

or equivalent volatile UI state.

The UI may use local state for presentation, but after reload/recreation it must be able to reconstruct the correct pending odometer task from authoritative/restorable state.

Choose the smallest architecture-compatible solution.

## ODO-02 — START restoration

If START odometer evidence is unresolved:

- returning from camera must resume START odometer;
- reload/recreation must resume START odometer;
- user must not be allowed to begin first Trip until START evidence is resolved;
- if photo exists, restore the correct photo-backed confirmation state;
- if photo does not exist, restore the pending capture state.

## ODO-03 — END restoration

If END odometer completion is unresolved:

- returning from camera must resume END odometer;
- reload/recreation must resume the pending END evidence task;
- do not reopen or mutate the ended Work Session;
- preserve approved END Option B semantics.

## ODO-04 — Photo already persisted

If `odometer_evidence.storage_key` or equivalent authoritative photo evidence exists:

- do not unnecessarily force a new photo;
- restore the corresponding pending confirmation state;
- preserve the correct reading/confirmation relationship.

## ODO-05 — Photo was not persisted

If Android/page recreation happened before the file callback completed:

- do not claim a photo exists;
- resume the odometer task;
- request another capture cleanly.

## ODO-06 — Manual reading remains normal photo-backed flow

When OCR provides no suggestion:

- the Supervisor may type the reading visible on the valid photo;
- confirm;
- evidence remains normal photo-backed evidence;
- no Admin exception is created merely because OCR returned nothing.

## ODO-07 — No-photo remains exception

Do not weaken the existing no-photo exception approval model.

## ODO-08 — No navigation ambiguity

After camera return, the unresolved odometer task must be visually obvious and immediately actionable.

Do not require the user to navigate through unrelated Activity screens to find it.

---

# 9. Odometer Tests Required

At minimum:

### O1 — START normal camera return
- START pending;
- photo captured;
- return;
- START odometer task visible;
- photo/reading state available.

### O2 — START page recreation after persisted photo
- photo has persisted;
- page recreated/reloaded;
- START task restored;
- same evidence restored;
- no duplicate evidence.

### O3 — START recreation before photo persistence
- no persisted photo;
- page recreated;
- START task restored in capture state;
- no fabricated evidence.

### O4 — START manual reading with no OCR suggestion
- valid photo;
- OCR returns none;
- manual reading confirmation works;
- PHOTO_CONFIRMED or approved equivalent reached;
- Start Trip unblocks only after resolution.

### O5 — START retake
- retake replaces/updates the intended pending evidence according to existing rules;
- no orphan/duplicate active evidence.

### O6 — END normal camera return
- END capture initiated;
- photo persists;
- return;
- END completion task restored.

### O7 — END page recreation
- Work Session remains ended if already ended;
- pending END odometer task restored;
- session is not reopened.

### O8 — END no OCR suggestion
- valid photo;
- manual confirmation succeeds;
- no exception solely because OCR returned none.

### O9 — END photo not persisted
- task restores to capture state;
- no fabricated photo/evidence.

### O10 — Existing no-photo exception regression
- approved exception path remains unchanged.

---

# 10. Mobile / Browser Validation

Automated browser tests are required, but the physical Android finding must also be revalidated by CER.

Development must provide a short physical revalidation checklist containing only the scenarios affected by this delta.

At minimum CER must repeat on Android:

1. START odometer → camera → return;
2. START odometer → camera → browser/page recreation if reproducible;
3. END odometer → camera → return;
4. END odometer → camera → browser/page recreation if reproducible;
5. Recovery with normal precise location;
6. one intentionally poor-location environment if practical, to observe that low-quality evidence is rejected/recovered/Missing rather than silently accepted.

Do not require CER to rerun the entire RTE06 field protocol unless regression evidence shows a broader impact.

---

# 11. Security / Audit

Revalidate:

- tenant isolation;
- Supervisor ownership of odometer evidence;
- no cross-session odometer restoration;
- no evidence from previous Work Session shown in a new session;
- no photo/evidence duplication on reload;
- no rejected geolocation coordinates persisted;
- no client-provided accuracy override trusted blindly;
- server remains authoritative for accepted evidence;
- Missing remains immutable;
- notification separation remains unchanged.

If a new Missing reason code is added:
- include it in the appropriate database/business constraint;
- migration must be safe;
- downgrade/roundtrip must remain valid;
- audit/diagnostics must remain truthful.

---

# 12. Compatibility Requirements

Must remain unchanged:

- RTE03 Work Session lifecycle;
- RTE04 Trip lifecycle;
- RTE04 odometer business rules;
- END Option B;
- RTE05 Activity flow;
- RTE06 exact offline correlation;
- RTE06 Missing immutability;
- RTE06 notification separation;
- RTE06 routing primary/fallback;
- official road-distance mileage;
- Change Plan waypoint semantics;
- no partial mileage;
- purge-safe provenance;
- tenant isolation;
- existing roles/capabilities.

---

# 13. Acceptance Criteria

This correction is complete only when:

1. Recovery no longer accepts arbitrary accuracy.
2. Recovered uses the approved 100 m / Fresh accuracy policy.
3. Recovery can continue after a rejected low-quality candidate.
4. Recovery exhaustion creates truthful Missing evidence.
5. Rejected coordinates are not persisted.
6. A 2,000 m Recovery candidate cannot become authoritative.
7. Rejected Recovery evidence cannot enter official routing waypoints.
8. Fresh behavior remains correct.
9. Cached behavior remains correct.
10. Missing required waypoint behavior remains correct.
11. START odometer resumes after camera return.
12. START odometer resumes after page recreation.
13. START photo state is restored if already persisted.
14. START capture state is restored if photo never persisted.
15. Start Trip remains blocked until START odometer resolves.
16. END odometer resumes after camera return.
17. END odometer resumes after page recreation.
18. END restoration never reopens an ended Work Session.
19. Valid photo + no OCR suggestion still supports manual confirmation.
20. No-photo exception behavior is unchanged.
21. No productive OCR implementation is introduced.
22. RTE03/RTE04/RTE05 regression remains green.
23. RTE06 offline correlation remains green.
24. RTE06 routing/mileage regression remains green.
25. tenant isolation remains green.
26. typecheck/lint/build remain green.
27. migrations/constraints remain green if changed.
28. no `PARTIAL`, `NOT IMPLEMENTED / GAP`, `BLOCKED` or unresolved `DECISION REQUIRED` remains inside this delta.

---

# 14. Tests / Regression Required

At minimum rerun:

- all new G1–G11 tests;
- all new O1–O10 tests;
- odometer integration tests;
- odometer browser flows;
- Work Session tests;
- Trip tests;
- Activity/workbench tests;
- RTE06 location evidence;
- RTE06 Missing immutability;
- exact offline correlation;
- mileage engine;
- routing waypoint construction;
- tenant isolation;
- migration tests if reason-code constraint changes;
- typecheck;
- lint;
- production build.

Do not weaken, skip or xfail tests to obtain closure.

---

# 15. Decision Authority

Development may choose:

- how to persist/restore odometer UI task state;
- whether to derive pending task from server state, persisted client state or a combination;
- component/router implementation details;
- exact technical name of a new Missing reason code if required;
- test structure;
- internal helper/refactor needed to avoid duplication.

Do not return ordinary technical choices to CER.

Return to CER only if the correction would require:

- changing the 100 m decision;
- blocking operational actions on GPS;
- changing privacy rules;
- changing odometer evidence business rules;
- changing Work Session/Trip/Activity state machines;
- introducing productive OCR now;
- adding meaningful external dependency/cost;
- changing tenant isolation or permissions.

---

# 16. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_FIELD_CORRECTIONS_CLOSURE_REPORT_004.md`

Include only:

1. Executive Result
2. F-1 Root Cause and Correction
3. Recovered Accuracy Rule — As Built
4. Rejected Recovery / Missing Behavior
5. Routing Waypoint Protection
6. Odometer START Restoration
7. Odometer END Restoration
8. Photo Persistence / Page Recreation Cases
9. OCR Scope Confirmation
10. Security / Privacy
11. Tests / Regression
12. Expected → Implemented → Evidence → Gap
13. Physical Revalidation Checklist for CER
14. Remaining Field Validation Items, if any
15. Proposed Status

Proposed status may be:

`IMPLEMENTATION COMPLETE / READY FOR CER PHYSICAL REVALIDATION`

only if every Development-side acceptance criterion above is confirmed.

Do not claim:

`RTE06 CERTIFIED`

CER will issue that status after physical revalidation.

---

# 17. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_FIELD_CORRECTIONS_CLOSURE_REPORT_004.md`

**STOP.**

Do not start RTE07.

Do not start RTE10-A01.

CER will perform the targeted physical revalidation and decide final RTE06 certification.
