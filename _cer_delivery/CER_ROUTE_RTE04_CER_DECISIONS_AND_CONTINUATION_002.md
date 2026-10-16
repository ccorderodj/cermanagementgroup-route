# CER Route — RTE04 CER Decisions and Continuation Instructions 002
## Resolution of Interim Decision Request + Controlled Continuation

**Applies to:** `CER_ROUTE_RTE04_DELIVERY_REPORT_001.md`  
**Checkpoint:** RTE04 — Trip Foundation + Odometer Evidence  
**Status:** RTE04 remains **IN PROGRESS**. This document resolves the product decisions raised by Delivery 001 and authorizes continuation.  
**Expected final delivery:** `Report Delivery Rodrigo/CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`

---

## 1. CER Decision — END Odometer Exception

### Decision: OPTION B

If the Supervisor reaches `End Work`, vehicle use occurred, the END odometer photo cannot be obtained, and the Supervisor submits the approved manual-entry exception request:

**The Work Session may end with an explicit pending END odometer exception.**

Do **not** keep the Work Session artificially `ACTIVE` while waiting for Admin availability.

### Required semantics

- `End Work` may transition the Work Session to `ENDED` once all other approved Work Session/Trip blockers have been resolved.
- The END odometer evidence remains explicitly unresolved, for example:
  - `EXCEPTION_REQUESTED`;
  - later `EXCEPTION_APPROVED` or rejected according to the approved exception flow.
- `ended_at` remains the actual End Work occurrence and must not later move because the odometer evidence was resolved after the session ended.
- `Odometer Distance` remains `PENDING` until a valid END reading exists.
- Never infer, fabricate or substitute an END reading.
- Admin approval remains one-time and scoped to:
  - tenant;
  - Supervisor;
  - Work Session;
  - Vehicle;
  - `END`;
  - the specific exception request.
- After approval, the Supervisor may complete the authorized manual END reading through a bounded pending-evidence completion flow associated with the already-ended Work Session.
- Completing END odometer evidence after the Work Session ended:
  - does **not** reopen the Work Session;
  - does **not** change `ended_at`;
  - does **not** permit a new Trip under that session;
  - does **not** make the manual evidence appear to be photo evidence.
- If the Admin rejects the request or requires a photo, the evidence remains unresolved until the permitted evidence path is completed. Do not invent a reading to close the exception.
- All request, approval/rejection and final confirmation actions remain audited.

### Important

This decision does **not** bypass the already-approved End Work rules.

If another blocker exists, such as an `IN_TRANSIT` Trip requiring the D-07 review flow, that blocker is handled first. The odometer exception only resolves the question of whether waiting for Admin approval keeps the Work Session active.

---

## 2. CER Decision — Timing of Context-Specific Standardized Values

The standardized fields are divided between **Trip planning data** and **post-arrival operational evidence**.

### Final timing matrix

| Context | Field | Timing | Checkpoint ownership | Cardinality |
|---|---|---|---|---|
| Client Visit | Client Visit Activities | **Post-arrival** | RTE05 | Activity selector / multi-select under A-3 |
| Recruiting | Recruiting Activities | **Post-arrival** | RTE05 | Activity selector / multi-select under A-3 |
| Employee Visit | Employee Visit Reason | **Pre-trip** | RTE04 | Single value |
| Check Delivery | Delivery Type | **Pre-trip** | RTE04 | Single value |
| Check Delivery | Received By | **Post-arrival** | RTE05 | Single value |
| Office | Office Purpose | **Pre-trip** | RTE04 | Single value |
| Other | Other Activities | **Post-arrival** | RTE05 | Activity selector / multi-select under A-3 |

### Rationale / product boundary

The top-level Trip context answers **why the Supervisor is moving**. Pre-trip fields further qualify the plan where they are naturally known before departure.

Post-arrival Activity selectors record **what was actually executed at the stop**.

Therefore:

- `Employee Visit Reason` belongs to planning: the Supervisor is traveling for that reason.
- `Delivery Type` belongs to planning: it identifies what is being taken for delivery.
- `Office Purpose` belongs to planning: it qualifies why the Supervisor is going to the office.
- `Received By` can only represent the actual recipient after arrival.
- `Client Visit Activities`, `Recruiting Activities` and `Other Activities` describe execution at the stop and remain post-arrival.

### Existing free-text fields

Keep the already-approved free-text model. These are not catalogs:

- Client Visit destination;
- Recruiting Area / Location;
- Employee / Reference;
- Check Delivery Employee / Reference;
- Office;
- Other Area / Location.

These values may be collected as applicable to the pre-trip planning flow.

---

## 3. Correction to the Interim Report

Delivery 001 states that only Client Visit Activity had determinable post-arrival timing.

That is not fully correct.

The certified RTE01 A-3 closure already states that, **after `Arrived`**, the Supervisor selects configured Activities from the applicable context and explicitly gives:

> a Recruiting stop offers Recruiting Activities.

Therefore:

- `Recruiting Activities = post-arrival` was already supported by the certified baseline;
- no new RTE04 product rule is being invented for Recruiting;
- the other timing questions are resolved by CER in §2 above.

Update the final RTE04 report so the record does not continue to describe Recruiting timing as unresolved.

---

## 4. Storage / “Core Files” Clarification

CER accepts the repository finding from Delivery 001:

The repository currently provides **storage primitives**, validation and scanning support, but not a complete reusable Core Files domain with upload/retrieval endpoints and a generic file registry.

The RTE04 instruction used “Core Files” too broadly.

### Approved direction

For RTE04:

- reuse the existing storage abstraction/provider;
- reuse media validation and malware scanning capabilities where applicable;
- keep the odometer photograph private;
- expose upload/retrieval only through authorized RTE04/domain contracts;
- do not create a public permanent URL;
- keep the evidence metadata required by RTE04 with the odometer evidence if that is the cleanest domain implementation;
- do **not** create a new platform-wide generic file registry solely for RTE04.

A future reusable Files capability may generalize this later if multiple domains require it.

This is a technical implementation clarification, not a new product feature.

---

## 5. `route.records.adjust`

Proceed with activating the already-approved `route.records.adjust` capability when the RTE04 Admin exception endpoints exist and actually enforce it.

Do not create the capability as an orphan merely to populate the catalog.

No new CER decision is required here.

---

## 6. OCR Decision

CER accepts the architecture direction:

- OCR is an assistive port/interface;
- the odometer domain must not depend directly on a specific OCR vendor;
- PaddleOCR may remain **disabled by default**;
- OCR failure must not convert a valid photograph into an exception;
- Supervisor manual confirmation from the photograph remains a normal valid path;
- no OCR result may autonomously establish the official reading.

The three-image experiment is sufficient to justify **not making PaddleOCR mandatory for RTE04**, but it is not sufficient to establish general real-fleet OCR accuracy.

Therefore:

`OCR quality on representative real odometer photographs = PENDING VALIDATION`

Do not state in the final report that any specific display technology represents the majority of the fleet unless evidence exists for that claim.

---

## 7. Offline Odometer Photo Limitation

CER accepts the RTE04 implementation boundary that offline photo-binary preservation is not being added in this checkpoint, provided the following remain true:

- the server-side Start Trip guard cannot be bypassed;
- a Start Trip cannot proceed without resolved START odometer evidence when odometer is required;
- no fake or text-only normal path is introduced to compensate for lack of connectivity;
- the Supervisor receives a clear operational message when connectivity is required to complete the evidence;
- pending state survives normal reload/reconciliation as far as the implemented state permits.

Classify this as:

`PENDING VALIDATION / MOBILE HARDENING — offline odometer photo capture`

It does not block continuing RTE04 under the current instruction, but it must remain visible before production readiness is assessed.

---

## 8. Prerequisite Status Correction

For the final RTE04 report, use the current CER status:

- `RTE03 — COMPLETED / CERTIFIED`
- `RTE02-A01 — COMPLETED / CERTIFIED`

Do not continue carrying the interim report statement that these checkpoints are awaiting CER certification.

Git/MR timing is outside this functional correction unless it creates a product-impacting issue.

---

## 9. Continuation Authorization

The two product decisions raised by Delivery 001 are now resolved.

Development may continue RTE04.

### Controlled sequence

#### RTE04-C1 — Complete Trip Domain Foundation
Complete:

- schemas/contracts;
- API/router;
- migration;
- capability enforcement as applicable;
- Trip integration tests;
- tenant isolation;
- state-machine/invariant tests;
- Change Plan append-only evidence;
- HOME arrival closure behavior;
- current-state integration.

C1 must be green before treating the Trip foundation as complete.

#### RTE04-C2 — Mobile Trip Lifecycle
Complete:

- mobile Trip planning UX;
- pre-trip fields according to §2;
- Start Trip;
- On Route;
- Change Plan only while `IN_TRANSIT`;
- Arrived;
- HOME / Arrived Home;
- recovery after reload/reconnect/reauth/second device;
- reuse the existing offline action queue for supported non-photo Trip actions;
- End Work review behavior required by the approved baseline.

Do not implement RTE05 Activity execution.

#### RTE04-C3 — START Odometer Evidence
Complete:

- persistent `Odometer pending` state after Start Work when applicable;
- non-blocking banner/prompt before travel selection;
- contextual capture when first travel action is selected;
- hard server-side guard before Start Trip;
- photo evidence;
- Supervisor-confirmed reading;
- optional OCR suggestion;
- photo-with-manual-confirmation normal path;
- no-photo exception request;
- Admin approval/rejection;
- one-time manual authorization;
- audit/security/private retrieval.

#### RTE04-C4 — END Odometer
Complete using §1 of this document:

- END capture at End Work;
- photo + confirmed reading normal path;
- no-photo exception request;
- Work Session may end with pending END exception;
- later bounded evidence completion without reopening the session;
- `End Reading >= Start Reading`;
- derived `Odometer Distance = End - Start`;
- Odometer Distance remains independent from Routing Mileage.

#### RTE04-C5 — Validation / Final Delivery
Validate:

- backend/integration tests;
- permission/tenant tests;
- browser-level mobile flow;
- offline/reconnect behavior within the supported boundary;
- private photo access;
- odometer exception lifecycle;
- regression against certified RTE03 and RTE02-A01;
- frontend typecheck/lint/build;
- migration/schema integrity.

---

## 10. Do Not Change

Do not change or introduce:

- RTE03 Work Session occurrence-time semantics;
- one active Work Session per Supervisor;
- official Routing Mileage authority;
- Haversine as official mileage;
- Activity execution before RTE05;
- GPS/geolocation before its checkpoint;
- fuel calculation;
- Reports/Today-Live;
- route optimization;
- client/employee master catalogs;
- mid-session vehicle switching;
- a generic platform file registry solely for this checkpoint;
- OCR as authoritative evidence;
- a permanent permission to enter odometer manually;
- automatic use of odometer distance as Routing Mileage.

---

## 11. Final Deliverable

The next CER-facing report should be:

`Report Delivery Rodrigo/CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`

It must be the evidence-first completion candidate and include:

- actual implementation by C1-C5;
- Expected → Implemented → Evidence → Gap;
- state/invariant evidence;
- API/data/UI components changed;
- browser evidence;
- permissions/security/audit;
- odometer photo and exception evidence;
- supported offline behavior and explicit limitations;
- test/regression results;
- remaining `PENDING VALIDATION`;
- confirmation that RTE05 was not started.

Do not label RTE04 completed merely because implementation exists. The report must provide the evidence required for CER certification.

---

## 12. STOP Conditions

STOP and return to CER if implementation would require:

- changing any decision in §§1-2;
- making a post-arrival field pre-trip or vice versa;
- reopening an ended Work Session merely to finish END odometer evidence;
- weakening the Start Trip odometer guard;
- making OCR authoritative;
- using odometer distance as official Routing Mileage;
- introducing Activity execution/RTE05;
- introducing GPS/routing mileage/fuel/reporting scope early;
- creating a new platform-wide file domain or other major architectural expansion not required by RTE04;
- any new product decision not already resolved by the approved baseline or this document.

After producing `CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`, **STOP** for CER validation.
