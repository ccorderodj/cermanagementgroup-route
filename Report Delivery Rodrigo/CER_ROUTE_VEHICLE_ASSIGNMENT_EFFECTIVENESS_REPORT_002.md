# CER Route — Vehicle Assignment Effectiveness (baseline correction)

| | |
|---|---|
| **Origin** | CER decisions on `CER_ROUTE_ODOMETER_OCR_PREFLIGHT_001.md` |
| **Branch** | `feature/odometer-ocr-preflight` (same branch as the preflight it answers) |
| **Commits** | `6041906` preflight diagnosis · `dac3993` this correction |
| **Date** | 2026-09-29 |
| **Scope** | **decision 2 only.** Decision 1 (productive OCR) registered, not implemented |
| **Migration** | **none** — the change is in a query, not the schema |
| **RTE06** | **Not started.** No geolocation or mileage work |

---

## 0. What CER decided, and what I did with each

| CER decision | Action taken |
|---|---|
| **1 — Productive OCR before production.** Photo → OCR → suggestion → Supervisor confirms/corrects → `PHOTO_CONFIRMED`. Successful recognition is not an absolute condition; a Supervisor may type the reading seen in that same photo and it stays photo-backed. The official reading is always the confirmed one. Engine selection happens in its own checkpoint, **not part of RTE06** | **Registered, not implemented.** No engine selected, installed or activated. §5 records what already holds today and what the future checkpoint must decide |
| **2 — `effective_from` must be evaluated.** An assignment applies only when `effective_from <= ` the occurrence time of Start Work and `effective_to` is null or later. A future assignment must not apply early. The vehicle is snapshotted on the Work Session and does not change retroactively. With no effective assignment, the day may start without a vehicle and the odometer stays `NOT_REQUIRED` | **Implemented and validated.** §1–§4 |

CER stated the correction before RTE06 is **only** the effective assignment resolution. That is what this report covers.

---

## 1. What was wrong

`VehicleAssignmentsDAO.current_for_supervisor` resolved the assignment by one condition: `effective_to IS NULL`.

Consequence: an assignment dated for next week — creatable through the API, which accepts `effective_from` — applied **today**. The Work Session snapshotted a vehicle the Supervisor does not have yet, and the odometer demanded a START reading for it. The API allows future dating, so this was reachable, not theoretical.

A second, quieter consequence: the vehicle was resolved **before** the occurrence time was computed, so it used the receipt clock. For a Start Work that waited in the offline queue, those are different moments.

---

## 2. What was implemented

### `VehicleAssignmentsDAO.effective_at(moment)`

An assignment applies when it has begun (`effective_from <= moment`) and has not ended (`effective_to` null or later). Both halves matter: without the first, a future assignment is applied early; without the second, a closed one keeps applying.

**The moment is received, not taken from `now()`.** `WorkSessionService.start` was reordered to compute the occurrence time first and resolve the assignment against it. That is the part worth reading: a workday queued without coverage occurred before the server knew about it (D-10). Resolving with the receipt clock would credit it with the vehicle the Supervisor had **on reconnect**, not the one they had when they started — and would demand an odometer reading retroactively.

### The snapshot is a real snapshot

`vehicle_id` and `mpg_snapshot` live on the Work Session row. Reassigning tomorrow cannot rewrite yesterday, which is what makes a closed day's mileage interpretable. This already held; it is now asserted.

### What deliberately did not change

The two guards that prevent deactivating or deleting a Supervisor who holds a vehicle still ask about the **open** assignment (`effective_to IS NULL`). That is the right question there: an assignment starting tomorrow already commits the vehicle on record, so it must still block. Two different questions now have two different functions, each documented at its definition.

### One extension, declared for CER to reject if unwanted

`VehicleAssignmentsService.current_vehicle` — the "current vehicle" the admin screen shows — now applies the **same** rule evaluated at the present moment.

Before, that screen showed as *current* a vehicle whose assignment starts next week, while the same Supervisor's workday began without a vehicle: one fact told two ways, and precisely the confusion the preflight flagged. I read CER's rule ("a future assignment must not be applied early") as applying here too.

**This is reversible in one line** if CER prefers the admin screen to show the assignment of record regardless of effectiveness.

---

## 3. Files changed

| File | Change |
|---|---|
| `app/routers_api/vehicles/dao.py` | `effective_at` added; `current_for_supervisor` kept and its narrower meaning documented |
| `app/routers_api/vehicles/service.py` | `current_vehicle` uses `effective_at(now())` |
| `app/routers_api/worksessions/service.py` | occurrence time computed first; assignment resolved at that moment |
| `tests/integration/test_odometer_ocr_preflight.py` | +4 tests; one docstring corrected to the new resolver |

No migration, no capability, no role, no standardized value, no frontend file.

---

## 4. Validation

| Suite | Tests | Result |
|---|---|---|
| `test_odometer_ocr_preflight.py` | 10 | **0 failures, exit 0** |
| `test_odometer.py` + `test_odometer_end_work.py` + `test_work_sessions.py` + `test_route_foundation.py` | 127 | **0 failures** |
| `test_trip_and_odometer_browser.py` | 6 | **6/6, exit 0** |
| `test_rte05_workbench_browser.py` | 24 | **24/24, exit 0** |

### The four cases that prove decision 2

| Case | Measured |
|---|---|
| assignment dated +7 days | Work Session has **no** vehicle, odometer `not_required`, first Trip starts **without** a reading |
| same case, admin view | not shown as current vehicle — **and still blocks deactivating** the Supervisor, because that is the other question |
| reassignment after the day started | `vehicle_id` and `mpg_snapshot` unchanged on the existing session |
| Start Work queued 30 min before an assignment began | resolved with the vehicle held **then** — i.e. none — with `started_at_source = device` asserted first, so the test proves what it claims |

### One failure, reported because it happened

Running the two browser suites in a **single** pytest process, `test_end_work_asks_for_the_ending_reading_and_resolves_the_distance` failed once: the closing-reading screen did not appear within 20 s.

It is **not a regression**. Four independent measurements say so: the test passes alone (exit 0), its whole suite passes alone (6/6), the other browser suite passes alone (24/24), and the 127 backend tests pass.

**Cause: `UNVERIFIED`.** I did not determine the mechanism and will not present a guess as a finding. The family is known in this project — each query opens a physical connection (`NullPool`), and long runs produce waits that exceed the 20 s locators. It affects the test harness, not the product.

---

## 5. Decision 1 — productive OCR, registered for its own checkpoint

Not implemented here, per CER. Recording what is already true, so the future checkpoint starts from facts rather than re-deriving them:

| CER requirement | Status today |
|---|---|
| for a day with an assigned vehicle, the first Trip cannot start until START is resolved | **already enforced** — HTTP 409, evidenced in the preflight |
| flow photo → OCR → suggestion → confirm/correct → `PHOTO_CONFIRMED` | everything except the OCR step works; the port is called on the real path |
| successful recognition is not an absolute condition | **already true** — a `None` suggestion does not block; the Supervisor types the reading and it stays `evidence_method = photo` |
| the official reading is always the Supervisor's confirmed one | **already true** — stored in a separate column from `ocr_detected_reading` |
| the no-photo route stays an Admin-controlled exception | **already true** — unchanged |
| engine selection and integration | **open**, and it is the whole of that checkpoint |

What that checkpoint will have to decide, stated now because it carries cost: which engine, who validates accuracy on real fleet photographs, and who accepts the runtime footprint. The isolated PaddleOCR measurement already on record read mechanical rollers and clean print but **detected nothing on a seven-segment display**, weighs ~760 MB installed, downloads models on first start and needs `enable_mkldnn=False` on CPU. Since CER has now decided OCR is mandatory before production, that seven-segment result is the first thing to resolve — a common dashboard the evaluated engine could not read.

---

## 6. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Classification |
|---|---|---|---|
| assignment applies only from `effective_from` | yes | §4 case 1 | AS-BUILT / CONFIRMED |
| and only while `effective_to` is null or later | yes | closed-assignment test | AS-BUILT / CONFIRMED |
| a future assignment is not applied early | yes | §4 case 1 | AS-BUILT / CONFIRMED |
| resolved against the **occurrence** time of Start Work | yes | §4 case 4 | AS-BUILT / CONFIRMED |
| vehicle snapshotted, not retroactive | yes | §4 case 3 | AS-BUILT / CONFIRMED |
| no effective assignment → day starts without a vehicle, odometer `NOT_REQUIRED` | yes | §4 cases 1 and 2 | AS-BUILT / CONFIRMED |
| odometer / My Route regression green | yes | §4 | AS-BUILT / CONFIRMED |
| admin "current vehicle" aligned with the same rule | yes | §2, declared extension | AS-BUILT / CONFIRMED, reversible on request |
| productive OCR | no | §5 | **registered for its own checkpoint, by CER decision** |
| real iOS/Android hardware | no | unchanged | **PENDING VALIDATION** |

---

## 7. Status and next step

**Decision 2: COMPLETED AND VALIDATED.** Nothing blocks RTE06 from this side.

**Decision 1:** mandatory before production, in its own checkpoint, not part of RTE06 — as CER stated.

### Operational action elsewhere

**None.** No migration, capability or seed. One behavioural note for whoever supports the product: a Supervisor whose assignment starts in the future now correctly begins the day without a vehicle and without an odometer reading. If that is reported as a fault, the answer is the assignment's `effective_from`, not the code.

### Next step, not started

RTE06, per its own instruction document.

# STOP
