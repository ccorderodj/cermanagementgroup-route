# CER Route — RTE10-A01
## Odometer OCR Production Hardening & Mobile Capture Resilience
### Product Owner Instructions for Development Agent
### Revision 002

**Objective:** complete the production-ready odometer capture experience for START and END by adding assistive OCR, making a captured photo durable across mobile/browser interruptions, cleaning the reading-entry UX, and measuring/optimizing the mobile load where evidence justifies it.

**Architecture direction:** reuse the existing odometer domain, evidence model, capture flow, restoration behavior, permissions and audit. Preserve the current certified baseline.

---

# 1. Context

The current normal odometer flow is already functional:

```text
photo
→ manual reading
→ supervisor confirms
```

The repository already contains an OCR abstraction/runtime path, but productive OCR has not been active; prior validation used the no-suggestion behavior.

Field testing confirmed that Android/browser memory pressure can recreate the page. The current task-restoration flow is already part of the certified baseline; this checkpoint only addresses the remaining photo-durability and OCR experience:

> if the photo has been taken but has not yet been durably persisted/uploaded when the browser renderer is lost, the user may have to take the photo again.

This checkpoint must improve that experience without weakening the truthfulness of odometer evidence.

---

# 2. Objective

Deliver this target experience for both START and END:

```text
Take photo
→ photo is durably staged/persisted
→ OCR attempts to read odometer
→ OCR suggestion is shown when usable
→ Supervisor confirms or corrects the reading
→ confirmed reading becomes authoritative
```

If OCR cannot produce a usable suggestion:

```text
Take photo
→ no usable OCR suggestion
→ Supervisor enters reading manually
→ confirms
```

OCR is assistive only.

---

# 3. Confirmed Product Rules

## PR-01 — Supervisor confirmation remains authoritative

OCR must never independently finalize an odometer reading.

The authoritative reading is the value the Supervisor explicitly confirms.

```text
OCR suggestion ≠ confirmed reading
```

If the Supervisor edits the suggestion, the confirmed reading is the edited value.

## PR-02 — No OCR result must not block operations

Failure, timeout, low confidence, unreadable image or no detected reading must fall back cleanly to manual entry.

The user must not be forced into an exception merely because OCR failed.

## PR-03 — Normal photo evidence remains required

This checkpoint does not remove or weaken the existing normal photo + confirmed-reading flow.

The existing no-photo exception remains a distinct exception path.

Do not convert OCR failure into an odometer exception automatically.

## PR-04 — START and END use the same product semantics

The productive OCR/capture-resilience behavior must work for both START and END.

Do not create different business rules unless the existing domain already requires them.

## PR-05 — A captured photo should survive ordinary mobile interruption

Once the device has successfully produced the photo for the odometer task, the application should preserve it durably enough that an ordinary page reload, renderer recreation, temporary connectivity loss, or camera-return interruption does not unnecessarily require the Supervisor to take the same photo again.

The implementation must remain truthful:

- do not claim a server upload occurred until it actually occurred;
- do not fabricate a photo;
- do not show an old photo as belonging to a new capture;
- cleanup must occur after successful reconciliation or when the staged evidence is no longer valid.

---

# 4. Scope

RTE10-A01 includes:

1. productive OCR integration behind the existing odometer/OCR architecture;
2. OCR suggestion for both START and END;
3. explicit Supervisor confirmation/correction;
4. graceful manual fallback when OCR cannot provide a usable suggestion;
5. durable local staging/recovery of a newly captured odometer photo until server persistence is confirmed;
6. Retake behavior with correct replacement/reconciliation of photo and OCR suggestion;
7. reading-entry UX cleanup so an unconfirmed default such as `0` does not visually appear to be a detected/real reading;
8. measurement of current mobile bundle/load behavior;
9. scoped mobile performance optimization when measurements identify avoidable load relevant to the Supervisor experience;
10. automated regression and browser validation;
11. CER physical-field-validation handoff.

---

# 5. Out of Scope

Do not change:

- Work Session lifecycle;
- Trip lifecycle;
- Activity lifecycle;
- official mileage/routing rules;
- existing location-evidence and geolocation behavior;
- odometer exception business rules;
- `route.odometer.selfapprove` semantics or activation model;
- general Roles & Permissions architecture;
- tenant hierarchy;
- RTE07;
- global Location Permission Enforcement;
- unrelated Admin/Web functionality;
- broad frontend rewrite or framework migration.

Do not introduce a new external OCR/provider contract without assessing privacy, operating cost, licensing, replacement risk and infrastructure impact. If the best technical option materially changes those boundaries, stop and present the decision before committing to it.

---

# 6. Existing Components to Reuse

Before implementation, inspect and reuse the current implementation wherever appropriate, including:

- existing odometer evidence model and START/END flows;
- current photo upload/storage pipeline;
- current OCR abstraction/runtime path;
- existing `ocr_detected_reading` or equivalent suggestion field if present;
- current confirmed/manual reading field;
- current certified page/task restoration logic;
- existing offline/browser durable-storage mechanisms where suitable;
- existing authentication, tenant scope, audit and file-security controls.

Do not create parallel domain truth when an existing field/service already represents it.

---

# 7. Functional Requirements

## FR-01 — Productive OCR

After a valid odometer photo is captured/persisted sufficiently for processing, OCR should attempt to identify the odometer reading.

The implementation technique/provider is Development's decision within the architecture and security boundaries.

## FR-02 — OCR result is a suggestion

When OCR returns a usable reading:

- show/populate it as a suggestion in the reading workflow;
- make clear that the Supervisor still must confirm;
- allow the Supervisor to correct it before confirmation;
- preserve the distinction between OCR-detected value and confirmed value where the existing data model supports it.

No auto-submit.

## FR-03 — No-result/manual path

When OCR returns no usable reading, errors, times out or cannot interpret the image:

- keep the photo if it is valid evidence;
- allow manual reading entry immediately;
- do not create an exception automatically;
- do not display a fabricated numeric suggestion.

## FR-04 — Initial reading state

Before OCR/manual input exists, the reading field must not visually imply that a real reading has already been detected.

Use the smallest UX adjustment consistent with the existing component.

Do not redesign the screen.

## FR-05 — Retake

When the Supervisor retakes the photo:

- the new photo becomes the active evidence;
- OCR must run against the new photo;
- a suggestion from the previous photo must not overwrite or survive as if it belonged to the new one;
- stale asynchronous OCR results must be ignored/rejected;
- the confirmed value still requires Supervisor action.

## FR-06 — Durable photo staging

Once a new photo has been obtained from the device, preserve it durably until one of these terminal conditions occurs:

```text
server persistence confirmed
OR
Supervisor explicitly replaces/discards it
OR
the odometer task is no longer valid and cleanup is safe
```

The solution must tolerate, as applicable:

- page reload;
- browser renderer recreation;
- return from camera;
- temporary network interruption;
- retry after reopening the same operational experience.

Development chooses the storage/queue mechanism.

## FR-07 — Idempotent/reconciled upload

Recovery/retry must not create duplicate active evidence.

A staged photo that later reaches the server must reconcile with the same odometer task/evidence context.

Do not rely on frontend-only assumptions for domain truth.

## FR-08 — Truthful restoration

After recreation:

### Photo already persisted server-side
Restore the server-backed photo state.

### Photo staged locally but not yet persisted
Restore/resume the pending photo/upload state without claiming server persistence.

### No persisted/staged photo
Show the existing Take Photo state.

Never fabricate a successful capture/upload.

## FR-09 — Security and local cleanup

Any locally staged image must be scoped sufficiently to prevent accidental reuse across:

- tenant;
- user;
- Work Session;
- START/END evidence;
- replacement/Retake lifecycle.

Clean up temporary local image data after successful reconciliation or safe invalidation.

Do not weaken existing authorization or tenant isolation.

---

# 8. OCR Edge Cases

Validate at minimum:

1. clear odometer image;
2. angled image;
3. glare/reflection;
4. low light;
5. partial/obscured digits;
6. no readable odometer;
7. OCR returns an incorrect reading and Supervisor corrects it;
8. OCR produces no suggestion and manual entry succeeds;
9. Retake after an OCR suggestion;
10. page recreation while OCR is pending;
11. page recreation after photo capture but before server persistence;
12. network loss after capture;
13. recovery after network returns;
14. START;
15. END.

Do not invent business validation ranges beyond the existing odometer rules.

---

# 9. Mobile Performance / Memory

A previous Development observation measured a production bundle around `789 KB`. Re-measure the current build; do not assume that number is still current.

The purpose is to determine whether the Supervisor mobile experience loads avoidable code/resources that plausibly increase memory pressure or slow restoration.

Measure/document at least:

- current production bundle composition/size;
- what the Supervisor/My Route path loads initially;
- whether substantial Admin-only code is included in that path;
- page load/reload behavior relevant to camera return/restoration;
- any obvious avoidable resource retained in the mobile operational path.

## Optimization rule

If measurements identify a contained, low-risk optimization that clearly benefits the mobile Supervisor path, implement it within this checkpoint.

Examples may include route-level loading/splitting or removal of unnecessary mobile-path work, but **Development chooses the technique**.

Do not perform a broad frontend architecture rewrite merely to reduce the bundle.

If meaningful optimization would require a broad architectural change, document:

`measurement → bottleneck → options → expected impact → effort/risk`

and stop for CER decision on that expansion.

A measured conclusion that no scoped optimization is justified is acceptable only if supported by evidence.

---

# 10. Security / Privacy / Audit

OCR must not weaken existing security boundaries.

Confirm:

- tenant isolation;
- authorization remains server-side where domain writes occur;
- image access remains appropriately scoped;
- locally staged photos are not exposed to another tenant/user/task;
- confirmed reading remains attributable to the Supervisor;
- OCR suggestion is distinguishable from confirmed reading;
- Retake does not leave an old suggestion attached to the new photo.

If an external OCR service is proposed, assess before adoption:

- what image/data leaves CER infrastructure;
- retention by provider;
- secrets/API-key management;
- cost model;
- failure/timeout behavior;
- replacement/provider-neutrality impact.

Escalate if this materially changes product/security/infrastructure boundaries.

---

# 11. Development Autonomy

CER defines the required product outcomes, not the implementation.

Development owns:

- OCR engine/library/provider selection within approved boundaries;
- client vs server OCR placement;
- image preprocessing;
- confidence/usable-result technical thresholds;
- local binary-storage mechanism;
- queue/retry implementation;
- idempotency mechanism;
- component/state architecture;
- code splitting/performance technique;
- test harness and fixtures.

Prefer:

```text
reuse existing architecture
→ low coupling
→ deterministic truth
→ graceful fallback
→ recoverability
→ testability
→ measurable performance
```

Escalate only if the solution requires a material change to business rules, privacy, tenant boundaries, external cost/contracts or broader architecture.

---

# 12. Checkpoints

## CP1 — OCR Productive Path

Close:

- productive OCR path;
- START + END suggestion;
- Supervisor confirm/correct;
- no-result manual fallback;
- Retake correctness;
- initial reading-state cleanup;
- automated tests for OCR outcomes.

Do not proceed to CP2 with an ambiguous authoritative-reading model.

## CP2 — Photo Durability & Recovery

Close:

- durable staging after capture;
- recreation/reload recovery;
- temporary network-loss recovery;
- idempotent server reconciliation;
- cleanup;
- Retake replacement;
- START + END browser tests.

## CP3 — Mobile Performance & Final Hardening

Close:

- current bundle/load measurement;
- justified scoped optimizations, if evidence supports them;
- affected regression;
- browser/mobile lifecycle validation;
- CER field-validation checklist;
- final report.

The agent may execute CP1→CP3 continuously unless a decision requiring CER escalation is reached.

---

# 13. Acceptance Criteria

RTE10-A01 Development is complete only when all applicable items are green:

1. Productive OCR runs on the odometer photo path.
2. OCR never independently confirms/finalizes a reading.
3. Supervisor can confirm a correct OCR suggestion.
4. Supervisor can correct an incorrect OCR suggestion.
5. No OCR result falls back to manual entry without blocking.
6. START and END both work.
7. Retake uses only the new photo/new OCR result.
8. Stale OCR results cannot overwrite a later Retake.
9. A captured photo survives supported page/browser lifecycle interruption before upload.
10. Temporary connectivity loss after capture does not unnecessarily force a Retake.
11. Recovery does not fabricate server persistence.
12. Upload/retry does not create duplicate active evidence.
13. Temporary local photo data is correctly scoped and cleaned up.
14. The initial reading field does not present a fake detected reading.
15. Existing odometer exception behavior remains unchanged.
16. Existing START/END restoration behavior remains green.
17. Work Session/Trip behavior remains unchanged.
18. Mobile bundle/load is measured and documented.
19. Any scoped optimization claimed is supported by before/after evidence.
20. Relevant security/tenant isolation remains green.
21. Typecheck/lint/build and affected regression are green.
22. No `PARTIAL`, `GAP`, `BLOCKED` or unresolved `DECISION REQUIRED` remains in the authorized Development scope.

---

# 14. Tests Required

Use the smallest sufficient mix of unit/integration/browser tests, but provide executed evidence for:

### OCR
- correct suggestion;
- wrong suggestion + Supervisor correction;
- no suggestion + manual entry;
- Retake replaces prior suggestion;
- stale OCR result ignored;
- OCR failure/timeout does not block.

### Photo durability
- captured → page recreation before server persistence → recovered;
- captured → temporary offline → recovered/uploaded later;
- successful persistence → local staged copy cleaned;
- Retake → old staged photo cannot win;
- no duplicate active evidence.

### Lifecycle
- START;
- END;
- camera return;
- page reload/recreation;
- existing START/END restoration regression.

### Security
- tenant/user/task scoping of staged evidence;
- unauthorized access rejected where applicable.

### Performance
- reproducible before/after measurements for any optimization implemented.

Do not weaken or remove existing tests to obtain closure.

---

# 15. CER Physical Validation Handoff

Development must provide a short field checklist for CER covering at minimum:

1. START — clear photo → OCR suggestion → confirm;
2. START — wrong suggestion → correct → confirm;
3. START — no OCR result → manual;
4. END — same three paths;
5. Retake;
6. low-memory/page recreation after photo capture;
7. temporary loss of connectivity after photo capture;
8. return/recovery without unnecessary Retake;
9. normal device vs lower-memory device observation;
10. confirm no automatic finalization by OCR.

Development must not declare field certification on CER's behalf.

---

# 16. Required Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE10_A01_ODOMETER_OCR_PRODUCTION_HARDENING_REPORT_001.md`

Keep it evidence-driven and incremental.

Include:

1. Executive Result
2. As-Built Baseline
3. OCR Technical Choice & Boundary
4. Productive OCR Behavior
5. Photo Durability / Recovery
6. Retake / Stale Result Protection
7. Mobile Performance Measurement
8. Optimizations Performed or Evidence-Based Decision Not to Expand
9. Security / Tenant Isolation
10. Tests / Regression
11. Expected → Implemented → Evidence → Gap
12. CER Field Validation Checklist
13. Decisions / Risks, if any
14. Proposed Status

For meaningful technical choices record:

`problem → options considered → choice → reason → evidence/test → impact`

---

# 17. Do Not Change

Do not use this checkpoint to redesign or reopen:

- previously certified functionality outside this checkpoint;
- odometer exception approvals;
- Route RBAC generally;
- Work Session;
- Trip;
- Activity;
- routing/mileage;
- geolocation policy;
- hierarchy;
- RTE07;
- unrelated Web/Admin UX.

---

# 18. Status Rule

Development may propose:

`IMPLEMENTATION COMPLETE / READY FOR CER FIELD VALIDATION`

only when the authorized Development scope has no remaining Partial/Gap/Blocked/Decision.

Only CER can certify the field experience.

---

# 19. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE10_A01_ODOMETER_OCR_PRODUCTION_HARDENING_REPORT_001.md`

**STOP.**

Do not start RTE07 or any other checkpoint without CER authorization.
