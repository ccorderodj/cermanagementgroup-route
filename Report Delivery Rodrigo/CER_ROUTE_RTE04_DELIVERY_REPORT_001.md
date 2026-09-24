# CER Route — RTE04 Delivery Report

| | |
|---|---|
| **Checkpoint** | RTE04 — Trip Foundation + Odometer Evidence |
| **Delivery** | **001 — interim, decision request** |
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE04_DEVELOPMENT_INSTRUCTIONS_001.md` |
| **Source branch** | `feature/rte04-trip-odometer` |
| **Base commit** | `ee33ede` (tip of `dev`) |
| **Date** | 2026-09-24 |
| **Status** | **RTE04 — In Progress / CER Decision Required** |

---

## 0. What this delivery is, and what it is not

**This is not the RTE04 completion report.** Implementation is under way and nothing in it has been validated yet.

It exists because analysis of the instruction against the repository surfaced **two product decisions that only CER can make** and **three premises in the instruction that do not hold against the current codebase**. Holding those until a final report would mean building on assumptions CER has not confirmed, and would deliver the questions at the exact moment it is most expensive to answer them.

The final evidence-first delivery will be `CER_ROUTE_RTE04_DELIVERY_REPORT_002.md`.

---

## 1. DECISION REQUIRED — two items

### 1.1 — END odometer no-photo exception: terminal Work Session behavior

This one the instruction itself raises (§"DECISION REQUIRED") and forbids Development from inventing: *"Do not infer the answer from the START exception behavior."*

**Question.** A Supervisor invokes End Work, the session used the vehicle, they cannot obtain the END photo and submit a manual-entry exception request. Does the Work Session:

- **Option A** — stay `ACTIVE` until an Admin approves and the manual reading is entered?
- **Option B** — end with an explicit pending odometer exception?

**Status:** blocked. The shared request/approval model and the normal END photo path will be built either way; only the terminal behavior waits.

**Impact if unanswered at final delivery:** RTE04 is delivered as `Partial / CER Decision Required` for this specific reason, per the instruction's own guidance.

---

### 1.2 — Standardized Value timing for six of the seven Trip contexts

**This is the one CER may not be expecting**, and it is a STOP condition the instruction defines: *"If the repository baseline does not make the timing of a field determinable, STOP on that field and report the ambiguity rather than inventing a new flow."*

The certified RTE01 baseline contradicts itself on when a context's Standardized Value is chosen:

| Baseline location | What it says | Implies |
|---|---|---|
| §3.2 | *"**Admin-managed selectable lists** for what was **done**: Client Visit Activities, Recruiting Activities, Employee Visit Reasons, Delivery Types, Office Purposes, Other Activities, Outcomes, Received By"* | all eight are **post-arrival** |
| §6.2 flow table | *"Enter/Select pre-trip data — Trip fields set (**free text or standard value** per activity type)"* | at least one is **pre-trip** |

Only one field is unambiguous:

- §3.2: *"**Client Visit Activity is chosen after arrival** — this is a product rule about when the choice is made, and the data model must not force it earlier."* → **post-arrival, RTE05.**

The remaining six have no determinable timing:

| Context | Standardized Value | Timing per baseline |
|---|---|---|
| Client Visit | Client Visit Activities | **post-arrival** (explicit) |
| Recruiting | Recruiting Activities | **undetermined** |
| Employee Visit | Employee Visit Reasons | **undetermined** |
| Check Delivery | Delivery Types | **undetermined** |
| Check Delivery | Received By | **undetermined** |
| Office | Office Purposes | **undetermined** |
| Other | Other Activities | **undetermined** |

Intuition points different ways for different fields — *Delivery Type* (what you are carrying) is plausibly known before setting off, while *Received By* (who signed for it) can only be known on arrival — which is precisely why guessing is the wrong move.

**What is being built meanwhile.** The Trip carries the **purpose/context** and its **free-text reference field**, both of which the instruction states unambiguously. The Standardized Value is placed **nowhere** — not pre-trip, not post-arrival — until CER rules. No schema decision has been made that would have to be undone.

**Question for CER.** For each of the six fields above: chosen **before travel** (pre-trip, RTE04) or **after arrival** (Activity execution, RTE05)?

---

## 2. Premises in the instruction that do not hold

Reported because building on them silently would produce a delivery that claims reuse it did not perform.

### 2.1 — "Core Files" is not a reusable component yet

§"Current State" lists *"Core Files for private odometer photographs"* among components to reuse.

**Verified:** `app/core/storage/` contains a `StorageProvider` protocol with local and S3 implementations, media validation (`media.py`) and malware scanning (`scanning.py`) — but:

- **no upload endpoint exists anywhere** (`UploadFile` / multipart return zero matches across `app/routers_api/` and `app/routers_api_public/`);
- **no file registry table exists** (no `create_table('file'…)` in any migration);
- **no domain consumes the storage provider today.**

RTE04 is Core Files' **first consumer**. It must build the upload endpoint, the private authorized retrieval endpoint and the evidence record itself. This is additional work the instruction's scope statement does not account for.

**Design decision taken, within the delegated latitude** (*"Exact table/field layout is delegated to Development"*): storage metadata (`storage_key`, `content_hash`, byte size, content type) is stored **on the odometer evidence row**, rather than inventing a platform-wide file registry. A generic file registry is a Core/platform domain, and `AGENTS.md` places domains in the application that owns them. All stated requirements are still met: private storage, authorized retrieval, type/size validation, scanning, no public URL.

### 2.2 — `route.records.adjust` is absent from the catalog

Anticipated by the instruction (*"If it is not yet active in the catalog, activate the already-approved capability"*). Confirmed absent; the catalog comment already records why (a capability no endpoint enforces fails `test_permission_catalog.py` by design). It will be activated and bound to the Admin approval endpoints. **No semantic conflict found**, so no STOP is triggered here.

### 2.3 — Prerequisites are not certified

The instruction states *"Prerequisites: RTE03 — COMPLETED / CERTIFIED; RTE02-A01 — COMPLETED / CERTIFIED."*

Neither is certified. Both were delivered and merged into `dev`, and both are awaiting CER certification:

- RTE03 closure 002 — delivered, merged pre-certification;
- RTE02-A01 closure 002 — delivered, MR merged, certification pending.

Work proceeds on explicit developer instruction. Flagged so the record is accurate.

---

## 3. Scope judgement taken — offline odometer photo capture

§"Offline / Reconnect Requirements" makes this **conditional**: *"**If** supporting offline odometer capture…"*, and prescribes the fallback: *"If the application cannot safely preserve photo evidence offline with the current technical approach, STOP and report the limitation rather than letting Start Trip bypass the odometer guard."*

**Decision: offline photo capture will not be implemented in RTE04, and is reported as a documented limitation.**

Reasoning:
- The Start Trip guard is enforced **server-side**, so no offline path can bypass it — the integrity requirement holds regardless.
- Durably storing photo binaries in IndexedDB, ordering their upload ahead of dependent queued actions, and securely purging local copies after synchronization is a subsystem in its own right.
- The benefit is a narrow edge case: no connectivity **and** a need to begin travel before regaining it.

Non-photo Trip actions **will** use the existing RTE03 queue, as the instruction requires. No second queue implementation.

---

## 4. OCR — evaluated with measurements, not assumptions

The instruction delegates the OCR choice while requiring *"Avoid coupling the domain to a specific external OCR vendor."* PaddleOCR was evaluated in an isolated environment against three synthetic odometer images, all legible to a human, reading `128437`.

| Case | Read | Correct | Time |
|---|---|---|---|
| **Seven-segment LCD (digital dash)** | *(nothing detected)* | ❌ | 2.28 s |
| Mechanical roller, mid-roll digit | `128437` | ✅ | 2.81 s |
| Clean control | `128437` | ✅ | 2.75 s |

**2 of 3.** The failure is total non-detection on the seven-segment display — the known weakness of PP-OCR models, trained on scene and document text whose glyphs bear no resemblance to disconnected seven-segment strokes. **Modern vehicles predominantly use digital odometers, so the failing case is plausibly the majority case in a current fleet.**

Cost measured:

| Factor | Measurement |
|---|---|
| Installed size | **760 MB** (Windows). The Linux wheel is ~2× the Windows wheel (195 MB vs 105 MB), so the deployment target is larger |
| Cold start | 17.8 s import + **52.4 s** downloading models to `~/.paddlex` |
| Warm start | ~3 s import + ~3.5 s init |
| CPU inference | 2.3–2.8 s per image |
| Robustness | **Crashes** with a oneDNN/PIR `NotImplementedError` unless `enable_mkldnn=False` is passed |
| Models | Fetched at runtime → in a container, a cold-start network dependency unless baked into the image |

**Decision: OCR port with a pluggable adapter; PaddleOCR implemented but disabled by default.** The port is required regardless (the instruction forbids coupling the domain to a vendor). The domain is complete without OCR, because the product model already states OCR is assistive only and that *"OCR failure with a photo still allows normal manual confirmation"* with no Admin exception. Shipping 760 MB and a cold-start download for a suggestion that fails on digital dashboards is not a trade this checkpoint needs to make.

Automatic suggestion on digital odometers will be reported as `PENDING VALIDATION`.

---

## 5. Implementation status — honest

| Sub-checkpoint | Status |
|---|---|
| **C1 — Trip Domain Foundation** | **IN PROGRESS.** Model, DAO and state machine written; schemas, router, migration and tests **NOT STARTED** |
| C2 — Mobile Trip Lifecycle | **NOT STARTED** |
| C3 — Start Odometer Evidence | **NOT STARTED** (OCR decision resolved) |
| C4 — End Odometer | **NOT STARTED** (blocked on §1.1 for the terminal behavior only) |
| C5 — Validation / Delivery | **NOT STARTED** |

### Written so far

| File | Contents |
|---|---|
| `app/routers_api/trips/models.py` | `Trip` + `TripPurposeChange`; 7 system contexts and 5 states as `BusinessEnum` with CHECK constraints; partial unique index enforcing one non-terminal Trip per Work Session; composite FK to `work_session` for tenant safety; occurrence/receipt timestamps per RTE03 semantics; `original_*` immutable alongside `current_*` |
| `app/routers_api/trips/dao.py` | Tenant- and session-scoped queries; ownership resolved through the Work Session rather than a copied `user_id` |
| `app/routers_api/trips/service.py` | State machine: create, start, change plan (appends, never overwrites), arrive (HOME closes, operational stays `ARRIVED`), interrupt; idempotent replays; audit on every transition |

### Verification status

| Check | Result |
|---|---|
| Migration | **NOT RUN** — not yet written |
| Trip integration tests | **NOT RUN** — not yet written |
| Odometer tests | **NOT APPLICABLE** — domain not built |
| Browser validation | **NOT RUN** |
| Full backend suite | **NOT RUN** since RTE04 work began |
| Frontend typecheck / lint / build | **NOT RUN** — no frontend change yet |

Nothing above is claimed as working. The only thing verified is that the models import and their enums resolve.

---

## 6. Confirmation — scope not started

No Activity execution block, multi-select Activity, Activity timer, Outcome/Notes flow, GPS/geolocation, GPS permission UX, Recovery Window, Missing Location Event, breadcrumbs, routing provider, official Routing Mileage, Haversine, fuel reference, fuel estimate, Today/Live, Activity Explorer, Reports/export, Admin post-close corrections, maps, route optimization, client/employee master data, mid-session vehicle switching, or any RTE05+ functionality has been started.

No placeholder that resembles completed Activity, GPS or Mileage functionality has been created. The Trip state machine deliberately leaves an operational Trip in `ARRIVED` rather than closing it, which is the extension point RTE05 will use.

No Routing Mileage value is produced anywhere.

---

## 7. What CER is asked to decide

1. **END odometer no-photo exception** — Option A (session stays `ACTIVE`) or Option B (session ends with a pending exception)?
2. **Standardized Value timing** for Recruiting Activities, Employee Visit Reasons, Delivery Types, Received By, Office Purposes and Other Activities — pre-trip (RTE04) or post-arrival (RTE05), per field?

Both are answerable independently. Item 2 is the one that changes the Trip schema, so an early answer avoids rework; item 1 affects only the End Work terminal path.

---

## 8. Proposed delivery shape

Two tranches rather than one, recommended:

- **Tranche 1 — C1 + C2**: Trip domain, current-state contract, End Work review, mobile Trip lifecycle, offline queue extension, tests and browser evidence. Coherent and verifiable on its own; unaffected by decision §1.1.
- **Tranche 2 — C3 + C4**: odometer evidence, Core Files wiring, OCR port, Admin exception queue.

A single combined delivery is possible but maximises the work done before the first green, and risks rework against both pending decisions.

**Next step:** await the two CER decisions while Tranche 1 proceeds. RTE05 has not been started and will not be until CER reviews RTE04.
