# CER Route — Odometer / OCR Preflight

| | |
|---|---|
| **Request** | preflight verification before RTE06 |
| **Branch** | `feature/odometer-ocr-preflight`, cut from `dev` |
| **Date** | 2026-09-29 |
| **Nature** | **diagnostic**, plus one test-coverage correction. No domain change |
| **RTE06** | **Not started.** Geolocation / mileage not touched (step 10) |
| **STOP** | **Triggered by step 9** — no productive OCR engine is connected, and none was selected or activated |

---

## Verdict, in one table

| Area | Classification |
|---|---|
| Odometer required / pending / blocking, with a current assignment | **AS-BUILT / CONFIRMED** — works |
| Banner + capture rendering in `What's next?` | **AS-BUILT / CONFIRMED** — works |
| Photo → reading → confirmation → `PHOTO_CONFIRMED` → Trip unblocked | **AS-BUILT / CONFIRMED** — works |
| **OCR suggestion** | **AS-BUILT / OCR ASSISTIVE NOT ACTIVE** |
| "Banner does not appear" as reported | **CONFIGURATION / TEST DATA** in the most likely reading — see §3 |
| Anything RTE04 declared implemented but inoperative | **no GAP found** |

**There is no regression.** Every blocking and rendering condition behaves as RTE04 certified, measured rather than inferred. The only thing that does not exist is a productive OCR engine — and RTE04 never claimed one existed.

---

## 1. Reproduction (steps 1–2)

`tests/integration/test_odometer_ocr_preflight.py::test_with_a_current_assignment_the_start_reading_is_pending_and_blocks`

Supervisor with an **active profile** and a **current vehicle assignment**, `Start Work`, then read the authoritative state.

| Question asked | Measured answer |
|---|---|
| required / not required | **required** — `status = "pending"` |
| pending / resolved | **pending** — `confirmed_reading` is `NULL`, `evidence_method` is `NULL` |
| vehicle id / applicable assignment | **`vehicle_id` = the assigned vehicle**, and `work_session.mpg_snapshot` is set |
| does the server block `Start Trip`? | **yes — HTTP 409**, detail mentions the odometer |

Where the state comes from: `GET /api/odometer/sessions/{id}`. Note that `/worksessions/current` does **not** carry odometer state; the screen reads it from that second endpoint. Worth knowing before anyone looks for it in the wrong payload.

---

## 2. The exact condition that renders the banner (step 3)

`pages/RouteMyRoutePage`:

```
{faltaInicio && !capturandoInicio && preparando === null && inicio && (
    <OdometerPendingBanner status={inicio.status} … />
)}
```

with

```
inicio       = odometro?.start ?? null
faltaInicio  = inicio !== null && !isOdometerResolved(inicio.status)
```

So the banner appears when **all four** hold: the start evidence exists, its status is not resolved, the capture screen is not already open, and no pre-trip form is open. `ODOMETER_RESOLVED` is `photo_confirmed`, `manual_exception_confirmed`, `not_required`.

`OdometerPendingBanner` itself renders `null` for any status outside `pending`, `exception_requested`, `exception_approved` — so a resolved or `not_required` row produces nothing, by design and in two independent places.

**Verified in a browser, not only read:** `test_rte05_workbench_browser.py::test_the_odometer_banner_coexists_with_the_card_grid` signs in with a current assignment, reaches the workbench, and asserts the banner is present, sits above the cards without overlapping them, does not disturb the grid or the card/`End Work` order, and causes no horizontal overflow.

---

## 3. Why a banner can legitimately not appear — `CONFIGURATION / TEST DATA`

This is the part worth reading carefully, because it explains the reported symptom without any defect.

`WorkSessionService.start` snapshots a vehicle onto the Work Session **only if both** of these hold:

1. the user has a supervisor profile **and it is active**;
2. that profile has a **current** vehicle assignment.

If either is missing, `vehicle_id` stays `NULL`, and `OdometerService.ensure_row` then creates the evidence as **`NOT_REQUIRED`** — which is a resolved status. Consequence: **no banner, no capture, and `Start Trip` is not blocked.** That is RTE04 §6.1 behaving as certified: a supervisor without a vehicle has a perfectly valid workday and no reading is fabricated for them.

Measured, not asserted: `test_without_a_current_assignment_no_reading_is_required` — profile present, no assignment, and the result is `status = "not_required"`, `vehicle_id = null`, `Start Trip` → **200**.

### And what "current" means, precisely

`VehicleAssignmentsDAO.current_for_supervisor` treats as current **the assignment with no end date** (`effective_to IS NULL`). Nothing else.

`test_an_assignment_with_an_end_date_is_not_current` closes the assignment through the API and shows the next Work Session comes back `not_required`. That is correct behaviour, and it is also the most plausible route by which a supervisor who *looks* assigned in the admin screen ends up with a workday without a vehicle.

**Two observations, offered as information rather than as defects:**

| Observation | Why it matters |
|---|---|
| `effective_from` is **not** evaluated | an assignment dated in the future, with no end date, counts as current today. Whether that is desired is a product question, not something to change here |
| an inactive supervisor profile silently yields no vehicle | same mechanism; the day is valid and no reading is asked for |

**Recommended first check whenever someone reports "no odometer capture":** read `work_session.vehicle_id` for that session. If it is `NULL`, the product is behaving correctly and the question moves to the assignment data.

---

## 4. The full visible path (step 5)

`test_the_whole_capture_path_persists_photo_confirmed_and_unblocks` walks it and asserts what persists at each step.

| Step | As-built |
|---|---|
| capture / photo upload | `POST …/{start|end}/photo`. The storage key is **generated by the server**, never derived from the uploaded filename |
| preview / evidence | the key is stored and the row **stays `pending`** |
| reading | typed by the supervisor |
| OCR suggestion | `ocr_suggestion: null` with the wired reader — see §5 |
| confirmation / correction | `POST …/confirm` with the reading |
| persistence | `status = photo_confirmed`, `evidence_method = photo`, `confirmed_reading = 128437.0`, `vehicle_id` carried |
| return to the Trip being started | `Start Trip` → **200** afterwards |

### A correction to my own expectation, reported because it was mine

I first asserted the row becomes `photo_uploaded` after the upload. **That status does not exist**: the enum is `pending`, `photo_confirmed`, `exception_requested`, `exception_approved`, `manual_exception_confirmed`, `not_required`. The photo alone does not change the status, and that is coherent — a photo without a reading is not usable evidence, so the row keeps blocking until somebody confirms what they see. The test was corrected to the real behaviour, not the behaviour I assumed.

In the browser, the same path is covered by `test_trip_and_odometer_browser.py` (6 journeys, green in the 004 regression), including the exception route: request → admin approval → manual entry → `manual_exception_confirmed`.

---

## 5. OCR audit as-built (step 6)

| Question | Answer, with evidence |
|---|---|
| which `OdometerReader` / adapter exists? | **one**: `NoSuggestionReader`, in `app/routers_api/odometer/ocr.py`. It is the Protocol's default implementation and returns `None` |
| which implementation is wired at runtime? | `NoSuggestionReader`. `test_the_default_reader_is_the_one_wired_at_runtime` asserts the instance type and that it suggests nothing |
| does production still use it? | **yes.** `set_odometer_reader` is called from **tests only** — `grep` over `app/` returns no caller. Nothing in startup or configuration registers an adapter |
| is PaddleOCR integrated into the real flow, or only tested in isolation? | **neither integrated nor present.** The only occurrence of the string "paddle" in the entire repository is the **docstring** of `ocr.py`, which records the isolated evaluation. No adapter, no import, and `pyproject.toml` has no OCR dependency |
| what configuration enables/disables the suggestion? | **none exists.** There is no flag, no setting, no environment variable. The only lever is calling `set_odometer_reader` in process |
| evidence of real photo → OCR suggestion → confirmed value | **not available with a real engine**, because none is connected. What *is* proven is that the port works: see below |

### The port works — what is missing is an adapter, not the wiring

`test_the_port_works_when_an_adapter_is_plugged_in` registers a stub adapter and shows:

* the **real** upload path calls the port (the adapter is invoked exactly once);
* the suggestion reaches the response (`ocr_suggestion: "99120.0"`);
* the supervisor corrects it to `99125.0`, and the two are stored **separately** — `ocr_detected_reading = 99120.0`, `confirmed_reading = 99125.0`.

That separation is the reason the suggestion can never be mistaken for a fact: what the engine thought and what the person confirmed are different columns, and only the second one counts.

What the `ocr.py` docstring records about the isolated PaddleOCR evaluation, reproduced because it bears on any future decision: it read mechanical roller odometers and clean printed text, **detected nothing on a seven-segment display**, weighs ~760 MB installed, downloads models on first start, and needs `enable_mkldnn=False` on CPU. CER accepted leaving it off by default.

### Step 9 — STOP

The instruction is explicit: if the real OCR is not connected and only the port plus the `NoSuggestionReader` default exist, **STOP, and do not select or activate an engine without reporting first.**

That is exactly the situation. **I have not selected, installed, configured or enabled any engine.** Doing so would be an implementation decision with runtime and dependency consequences — a ~760 MB install, first-run model downloads, and a CPU flag — and it is CER's call, not mine.

**Classification: `AS-BUILT / OCR ASSISTIVE NOT ACTIVE`.** Capture works end to end; there is no productive OCR connected. This matches what RTE04 delivered and reported; it is not a gap against a claim.

---

## 6. Classification (step 7)

Using only the permitted labels:

| Finding | Classification |
|---|---|
| Odometer required/pending/blocking with a current assignment | **AS-BUILT / CONFIRMED** |
| Banner and capture rendering, including alongside the card grid | **AS-BUILT / CONFIRMED** |
| Full capture path and `PHOTO_CONFIRMED` persistence | **AS-BUILT / CONFIRMED** |
| No productive OCR connected | **AS-BUILT / OCR ASSISTIVE NOT ACTIVE** |
| A supervisor without a current assignment sees no capture | **CONFIGURATION / TEST DATA** |
| Anything RTE04 declared implemented but not operative | **none found** — no `GAP` |
| Wiring/UI regression against the certified baseline | **none found** — no `REGRESSION` |

Step 8 therefore does not apply: there is no regression to correct.

---

## 7. What I did change, and why

No domain code. Two test-side additions:

| File | Change |
|---|---|
| `tests/integration/test_odometer_ocr_preflight.py` | **new**, 6 tests. Records the as-built state in writing so this classification rests on measurements |
| `tests/e2e/test_rte05_workbench_browser.py` | **+1 journey** — the banner coexisting with the card grid |

### A coverage hole I closed, and it was mine

Checkpoint 004's VR-04 required proving "no overlap with the odometer banner". My journeys there ran **without a vehicle assignment**, so the banner was never on screen and that clause was asserted without evidence. It now has a journey with a current assignment that measures the banner's position against the cards and against `End Work`.

That is the second time in this engagement that a clause I reported as covered turned out to be covered only in appearance. Both times it was found by re-reading the instruction against the code rather than against my own summary.

---

## 8. Validation

| Suite | Result |
|---|---|
| `tests/integration/test_odometer_ocr_preflight.py` (6) | **0 failures, exit 0** |
| `test_rte05_workbench_browser.py::test_the_odometer_banner_coexists_with_the_card_grid` | **pass** |
| `npm run typecheck` / `lint:ts` | **NOT RUN** — no frontend source changed |
| Odometer + My Route regression | **PENDING** — see below |

**Declared honestly:** the full odometer + My Route regression has **not** been re-run for this preflight, because nothing in the product changed. The suites that cover it were green in the checkpoint-004 chain immediately before this work: `test_odometer.py` + `test_odometer_end_work.py` (48 tests, 0 failures), `test_trip_and_odometer_browser.py` (6, 0), `test_rte05_workbench_browser.py` (23, 0). Step 8 asks for that regression only if a correction was made; none was.

---

## 9. What I recommend CER decide

Nothing here requires a decision to keep the product working — the manual path is complete and certified. Two questions are open, and both are yours:

**1. Does CER want a productive OCR at all?** If yes, the decision has a cost that should be stated before anyone writes the adapter: which engine, who validates its accuracy on real fleet photographs, and who accepts the runtime footprint. The isolated PaddleOCR measurement already says it fails on seven-segment displays, which is a common dashboard.

**2. Should `effective_from` be evaluated when resolving the current assignment?** Today a future-dated assignment with no end date counts as current. Changing it is a product rule, not a bug fix.

---

## 10. Scope respected

- **Step 9 STOP honoured:** no engine selected, installed, configured or activated.
- **Step 10 honoured:** no geolocation or mileage work started.
- **RTE06 not started.**
- No domain, migration, capability, role or standardized value was touched.

# STOP
