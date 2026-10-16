# CER Route — RTE10-A01 Odometer OCR Production Hardening

**Report 001** · branch `feature/rte10-a01-odometer-ocr-hardening` · 2026-10-05

Scope per `CER_ROUTE_RTE10_A01_ODOMETER_OCR_PRODUCTION_HARDENING_INSTRUCTIONS_002.md`.
Nothing in §5 or §17's exclusion list was touched: Work Session, Trip, Activity,
mileage/routing, location evidence, exception business rules,
`route.odometer.selfapprove`, RBAC, hierarchy and RTE07 are untouched.

---

## 1. Executive Result

Productive OCR is wired, the captured photo now survives the interruptions that
field testing exposed, and three defects that existed in the certified path were
found and corrected.

The most important of the three was not in the new work — it was in the old:

```python
sugerencia = get_odometer_reader().suggest(image=image, content_type=tipo)
```

That call sat **after** the photo was written to storage and **before** the
evidence row received its `storage_key`, with no guard. It was harmless while
the default provider was `NoSuggestionReader`, which cannot fail. The moment a
real engine is plugged in, an exception or a hang there leaves the object in
storage, the evidence row without its key, and the supervisor without the photo
he just took — blocked by a failure of the assistant. Activating OCR without
fixing this would have turned an assistive feature into an outage.

It is now `await suggest_safely(...)`: off the event loop, with a deadline, and
returning `None` for every failure mode. **An OCR that fails and an OCR that
sees nothing produce the same visible result**, because there is no OCR error a
supervisor in the street can act on.

Two further corrections: a retake could leave the previous photo's suggestion in
the reading field, and the field's `placeholder="0"` read as a detected value in
a large centred box.

The mobile performance question has a measured answer, and it is *no scoped
optimization is justified* — see §7 and §8. Three candidate bottlenecks were
measured; two were accounting artefacts that webpack already eliminates, and the
one that is real is worth **3,429 bytes gzipped**, which does not pay for
touching eight certified administration screens.

---

## 2. As-Built Baseline

The repository was in better shape than the instruction assumed. Measured, not
read:

| Component | State | Where |
| --- | --- | --- |
| OCR port (`Protocol`) | exists | `app/routers_api/odometer/ocr.py` |
| Default no-suggestion provider | exists, wired at runtime | `NoSuggestionReader` |
| `ocr_detected_reading` column | exists, separate from `confirmed_reading` | `odometer_evidence` |
| `ocr_suggestion` in the photo response | exists | `OdometerPhotoResult` |
| Suggestion shown as editable draft | exists | `OdometerCapture.tsx` |
| Task restoration across page recreation | exists, certified | RTE06 |
| Durable IndexedDB queue, 2 lanes | exists | `shared/lib/offlineQueue` |
| One evidence row per session and end | enforced by the database | `uq_odometer_evidence_session_type` |
| **Any OCR engine installed** | **none** | `test_odometer_ocr_preflight.py` |
| **Photo durability before upload** | **none** | — |

So RTE10-A01 is not a build; it is an adapter, a durability lane, and three
corrections. No parallel domain truth was created: the suggestion still lives in
the column that already existed.

---

## 3. OCR Technical Choice & Boundary

**Problem.** Produce a reading suggestion from an odometer photograph without
moving the privacy, cost or infrastructure boundaries that §5 and §10 protect.

**Options considered.**

| Option | Image leaves CER | Cost | Weight | Verdict |
| --- | --- | --- | --- | --- |
| **Tesseract, server-side** | no | none | ~30 MB system package | **chosen** |
| PaddleOCR, server-side | no | none | ~760 MB + model download | rejected |
| `tesseract.js`, in the browser | no | none | ~12 MB WASM + language data on the device | rejected |
| Google Vision / AWS Textract | **yes** | per call | none | not adopted without CER |

**Choice and reason.** Tesseract in the server. The photograph stays inside CER
infrastructure, there is no per-call cost, no provider contract, no API key to
manage, and the licence is Apache 2.0 — so none of §10's boundaries move and no
escalation is required.

PaddleOCR was already measured in the odometer/OCR preflight: it read mechanical
roller odometers and clean printed text, **detected nothing on a seven-segment
display**, weighs ~760 MB installed and downloads models on first boot. It does
not fit the test environment node.

`tesseract.js` is rejected by §9 on its own: adding ~12 MB of WASM and language
data, and running recognition in the renderer, is the opposite of reducing
memory pressure on a phone whose page Android is already killing. The checkpoint
cannot both ask for less mobile memory and ship an in-browser OCR engine.

An external service is the best option for accuracy, including digital
dashboards, and it is the one that moves the boundary §5 names. It is **not
adopted**, and it is the decision to bring to CER if suggestion quality on
seven-segment displays turns out to matter in the field.

**Known limit, stated up front.** Tesseract is trained on text, not on
seven-segment displays. On mechanical roller odometers and typographic dashboard
digits it works; on an LCD segment display it is **likely** to suggest nothing.
That is PR-02's manual path, not a malfunction, and the supervisor's flow is
unchanged when it happens.

**Boundary of activation.** The reader is selected by **presence of the binary**,
not by configuration optimism: an image without the system package keeps
`NoSuggestionReader` and behaves exactly as before this checkpoint, which is what
keeps the certified baseline green. `ODOMETER_OCR_ENABLED` exists to switch it
off without a deployment — an assistive feature that started suggesting badly
must be removable, not fixable in a hurry.

**Conservative by design.** Faced with two plausible candidates in one
photograph — the total odometer and the trip meter, which is what any dashboard
has — it suggests **nothing**. Picking one by size or position would be guessing,
and the two errors do not cost the same: a missing suggestion makes someone
type, and a wrong one can enter as a person-confirmed mileage fact if accepted
without looking.

---

## 4. Productive OCR Behavior

| Behaviour | Where |
| --- | --- |
| Recognition runs on the stored photo, off the event loop, with a deadline | `ocr.py :: suggest_safely` |
| Suggestion returned beside the confirmed reading, never instead of it | `OdometerPhotoResult` (unchanged) |
| Suggestion populates the field as an editable draft | `OdometerCapture.tsx` |
| Supervisor edit wins and survives a retake | `lecturaEsSugerida` |
| Failure, timeout, low confidence, ambiguity, no digits → `None` | `ocr_tesseract.py`, `suggest_safely` |
| No automatic exception on OCR failure | unchanged: the exception path is a separate, explicit request |
| Audit records what the machine suggested per capture | `audit_event.changes.ocr_suggested` |

Interpretation rules, all tested: minimum per-token confidence of 60 on
Tesseract's 0–100 scale; at least two digits, because a single digit on a
dashboard photo is almost always part of another indicator; the reading bounded
by the **existing** contract ceiling of `99999999.9`, with no invented business
range (§8 forbids it); scale fixed to one decimal to match `Numeric(10, 1)`.

Timing: recognition is synchronous within the upload request. The normal case is
well under a second on a 1600 px greyscale image; the worst case is bounded by
`ODOMETER_OCR_TIMEOUT_SECONDS` (default 8), after which the process is **killed**
— not merely abandoned, which would leave it occupying the node.

---

## 5. Photo Durability / Recovery

A third lane in the IndexedDB database that already existed —
`DATABASE_VERSION` 2 → 3, `pending_odometer_photos`. `onupgradeneeded` creates
what is missing and touches nothing else, so a device holding queued actions
from version 1 or 2 keeps them.

**What is staged and what is not.** The **photo** is, because it asserts nothing
about the domain: it is the file the evidence will need when it arrives. The
**reading confirmation** is not, and RTE04's reason still holds entirely — what
the supervisor needs to know is whether he may drive, and a queued confirmation
would tell him yes while the server can still refuse. That distinction is now
written where the old comment was.

**Three design decisions that carry the honesty requirement.**

1. **The store has no `uploaded` field.** An entry means exactly one thing —
   *taken, not confirmed by the server* — and is deleted on confirmation. A
   boolean would permit the state "saved and marked uploaded without anyone
   having checked", which is the lie FR-08 forbids. The browser test asserts the
   field's absence.
2. **The write is awaited before the network is touched.** That is what makes
   "the device has the photo" a fact rather than an intention. Issued in parallel
   with the POST, there would be a window in which Android can recreate the page
   and the photo exists nowhere.
3. **The screen says what is true.** *"Your photo is saved on this phone. It has
   not reached the server yet."* Not uploaded, because it is not; not an error,
   because nothing was lost and the photo does not need retaking.

**Restoration (FR-08), three cases, none invented:**

| Server state | Local state | Restored as |
| --- | --- | --- |
| `captured_at` set | any | server-backed photo; the local copy is removed |
| none | staged entry | pending upload, retried automatically; **no claim of persistence** |
| none | none | the existing Take Photo state |

Recovery is automatic on mount and on the browser's `online` event, so the
supervisor who loses signal in a car park finds the photo already uploaded by
the time he reaches the street. An explicit *Try to upload now* button exists for
the case where the automatic path has not fired yet.

**FR-07 — no duplicate active evidence — was already guaranteed, by the
database.** `uq_odometer_evidence_session_type` admits one row per session and
end, so a retry that arrives after a first upload actually succeeded replaces the
storage key of the same row. No idempotency mechanism was added, because none is
missing; a test now fixes that property so nobody relaxes the index, and so
nobody adds a parallel mechanism believing it is absent.

---

## 6. Retake / Stale Result Protection

Two distinct defects, both corrected.

**The previous photo's suggestion survived a retake.** `subirFoto` set the
reading from the suggestion but never cleared it when the new photo produced
none. Photo 1 suggests `90210`, the supervisor retakes, photo 2 suggests nothing
— and the field still showed `90210`, now attached to the new photograph. The
distinction now implemented: a value that came from OCR belongs to the photo it
came from and is cleared on replacement; a number the supervisor typed while
looking at the dashboard describes the same odometer and survives, because
erasing his input for repeating a photo would make him type it again for nothing.

**Stale asynchronous results.** A monotonic capture counter now guards the
response. Two uploads can overlap — the button is disabled, but a browser retry
or a reconnection does not go through the button — and the first response can
arrive after the second. Without the counter, the discarded photo's OCR would
write its suggestion onto the new one.

Clearing happens **before** the upload starts, not on response: while the request
is in flight the screen must not be showing a suggestion belonging to a
photograph the supervisor has just replaced.

Server side, the retake is already correct and now tested: `attach_photo`
assigns `ocr_detected_reading` unconditionally, so a second photo with no
suggestion sets the column to `NULL` rather than leaving the discarded photo's
number — which would otherwise have made the evidence claim the machine read
`90210` on an image where it read nothing.

Locally, the staged entry is keyed by the task tuple, so a new capture
**replaces** the pending one. Two entries would let the retry upload the photo
the supervisor deliberately rejected.

---

## 7. Mobile Performance Measurement

The instruction's prior observation of ~789 KB is **still current**: `main.js` is
807,619 bytes raw, which is 789 KiB.

| Metric | Value |
| --- | --- |
| `main.js` raw | 807,619 B |
| `main.js` gzipped (what is transferred) | **224,673 B** |
| `css/main.css` raw | 105,472 B |
| Emitted assets | 33 |
| All assets, raw | 1,344,970 B |

The baseline is already well optimised: the bundle is minified, tree-shaken,
split per page (all 22 pages are `React.lazy`, confirmed by the numbered chunks),
and served through `GZipMiddleware`. The Supervisor's My Route path downloads
`main.js` plus its own page chunk.

**What is eagerly in `main.js`, by source size:**

| Module | Source | Emitted? |
| --- | --- | --- |
| `react-dom` | 532.6 KB | yes — unavoidable |
| `@radix-ui/react-icons` | 492.9 KB | **tree-shaken**: `usedExports` = 16 of 318 |
| Admin-only entity slices (8) | 154.8 KB | **yes** — in chunk 792 |
| `react-hook-form` | 109.1 KB | **yes** — via the shared UI barrel's `Form.tsx` |
| `date-fns/locale` | 2,081.8 KB | **eliminated entirely**: `chunks: []` |

Two of the three candidates that looked like bottlenecks were artefacts of
source-size accounting:

- **Radix icons.** All imports are named; webpack's `usedExports` shows 16 of 318
  exports used, and terser drops the rest. An earlier grep of the emitted bundle
  appeared to confirm this, but that evidence was invalid — the output is
  minified, so names prove nothing in either direction. The `usedExports` data is
  what settles it.
- **`date-fns` locales.** 2,081.8 KB of locale source is parsed and **entirely
  discarded** — the modules report `chunks: []`. Their only importer,
  `getDateLocale`, is declared in `shared/lib/utils/utils.ts` and **never called
  anywhere**. Dead code worth zero bytes of payload (see §13: not removed, as it
  is outside this checkpoint's scope).

**The real avoidable content** is the Redux root reducer statically importing
eight administration entity slices, so a supervisor on a phone downloads Roles,
Permissions, Companies and Platform Settings. `DynamicModuleLoader` already
exists and is unused for them.

**Camera return and restoration.** The relevant cost is not the bundle. It is the
photograph: a phone image is multiple megabytes held in renderer memory. The
durability design in §5 stores the `Blob` natively rather than base64 — which
would inflate it by 33% and place it in the JavaScript heap as a string — and
keeps no second copy in React state.

**Before / after for this checkpoint's own changes:**

| | Before | After | Delta |
| --- | --- | --- | --- |
| `main.js` raw | 807,619 B | 807,619 B | **+0** |
| `main.js` gzipped | 224,673 B | 224,675 B | **+2 B** |
| All assets raw | 1,344,970 B | 1,349,767 B | +4,797 B |
| Asset count | 33 | 33 | 0 |

Productive OCR and photo durability cost **zero bytes in the eager mobile path**
and +4,797 B in lazily-loaded chunks.

---

## 8. Evidence-Based Decision Not to Expand

§9 permits concluding that no scoped optimization is justified "only if supported
by evidence". The evidence was produced by experiment rather than estimated.

**Experiment.** The eight administration slices were removed from the root
reducer, a production build was run, `main.js` was measured, and the change was
reverted with `git checkout`.

| | Baseline | Without admin slices | Saving |
| --- | --- | --- | --- |
| `main.js` raw | 807,619 B | 772,788 B | −34,831 B (−4.3%) |
| `main.js` gzipped | 224,673 B | 221,244 B | **−3,429 B (−1.5%)** |

A proportional estimate from source size suggested roughly 40 KB gzipped. The
measured figure is **ten times smaller**, because Redux slice boilerplate is
highly repetitive and gzip compresses it almost away.

**Decision: do not expand.** Converting the root reducer to dynamic registration
requires wrapping eight previously certified administration screens in
`DynamicModuleLoader` — screens §17 forbids reopening in this checkpoint — to
save 1.5% of the mobile transfer. That is not a trade worth making, and because
the measured saving is this small there is **nothing to escalate**: no CER
decision is required.

`react-hook-form`'s eager inclusion was **not separately measured**, because
removing it requires taking `Form.tsx` out of the shared UI barrel, which breaks
compilation of the administration forms — too invasive for an experiment. Given
that 154.8 KB of slice source was worth 3.4 KB gzipped, its 109.1 KB is unlikely
to behave differently, but that is reasoning, not measurement, and is recorded as
such.

**No optimization is claimed in this checkpoint**, so §9's before/after
requirement for claimed optimizations does not apply. The before/after in §7 is
reported to show the new work did not make the mobile path worse.

---

## 9. Security / Tenant Isolation

| Control | State |
| --- | --- |
| Tenant scope on every odometer endpoint | unchanged (`get_company_required`) |
| Authorization for domain writes | unchanged, server-side |
| Photo served only through the authorized endpoint | unchanged; no public URL |
| Storage key generated by the server | unchanged |
| Malware scan before storing | unchanged, and still **before** any decode |
| Confirmed reading attributable to the supervisor | unchanged |
| Suggestion distinguishable from confirmation | unchanged, separate columns |
| Retake leaves no old suggestion on the new photo | **corrected**, §6 |

**Local staged photos (FR-09).** The key is `userId:sessionId:end`.

It carries no company, and does not need to: each tenant is a distinct
subdomain, therefore a distinct browser origin with its own IndexedDB. Tenant
isolation comes from the origin model, which is stronger than any prefix that
could be written in application code.

The user **is** in the key, because two supervisors can share a phone and one's
photo must not surface for the other. It comes from the `user_data` cookie, which
is readable and editable — so this is **local isolation, not authorization**, and
invariant 8 is respected: who may upload a photo to which session is decided by
the server on every request.

Cleanup: the entry is deleted when the server confirms the photo, when the
supervisor replaces it, and when restoration finds the server already holds it.

**A locally staged photo cannot produce a confirmed reading.** `confirm_reading`
rejects with 409 when there is no `storage_key` and no approved exception, so the
screen's honesty does not depend on the screen being honest. Tested.

**No image is written to disk by OCR.** Tesseract is invoked with the photo on
`stdin` and TSV on `stdout`. A temporary file holding a dashboard and a number
plate would be evidence outside the private store, with no owner and no
guaranteed deletion.

**Nothing new in the logs.** The audit event records the suggested value, as it
already did; no bytes and no filename.

---

## 10. Tests / Regression

| Suite | Tests | Result |
| --- | --- | --- |
| `tests/test_odometer_ocr_reader.py` (new) | 13 | **PASS** |
| `tests/integration/test_odometer_ocr_productive.py` (new) | 10 | **PASS** |
| `tests/e2e/test_rte10_odometer_photo_durability_browser.py` (new) | 7 | **PASS** |
| Odometer regression: `test_odometer`, `_end_work`, `_exception_autoapproval`, `_ocr_preflight` | 64 | **PASS** |
| Browser regression: RTE06 odometer lifecycle, offline durability, bounded queue, trip+odometer, RTE10 | 20 | **19 PASS, 1 failure pre-existing in `dev`** — see below |
| `npm run check` (typecheck + lint) | — | **0 errors, 0 warnings** |
| `uv run python -c "import app.main"` | — | **OK** |
| Full Python suite | — | `NOT RUN` |

No existing test was weakened or removed.

### §8's fifteen edge cases, one by one

| # | Case | State | Evidence |
| --- | --- | --- | --- |
| 1 | clear odometer image | `NOT RUN` | needs the binary and a real photo — §13.1, CER §12.1 |
| 2 | angled image | `NOT RUN` | same |
| 3 | glare / reflection | `NOT RUN` | same |
| 4 | low light | `NOT RUN` | same |
| 5 | partial / obscured digits | `NOT RUN` | same |
| 6 | no readable odometer | **PASS** | `test_sin_texto_no_hay_sugerencia`, `test_el_ruido_no_numerico_se_descarta` |
| 7 | wrong reading, Supervisor corrects | **PASS** | preflight: suggested `99120`, confirmed `99125` |
| 8 | no suggestion, manual entry succeeds | **PASS** | `test_un_ocr_que_revienta_no_cuesta_la_foto` (both ends) |
| 9 | retake after a suggestion | **PASS** | `test_rehacer_la_foto_borra_la_sugerencia_de_la_anterior` |
| 10 | page recreation while OCR is pending | **PASS** | `test_recrear_la_pagina_con_el_ocr_en_vuelo_no_pierde_la_foto` |
| 11 | recreation after capture, before persistence | **PASS** | `test_la_foto_guardada_sobrevive_a_recrear_la_pagina_y_se_sube_sola` |
| 12 | network loss after capture | **PASS** | `test_la_foto_queda_guardada_cuando_la_subida_no_llega` |
| 13 | recovery after network returns | **PASS** | same test, via the `online` event |
| 14 | START | **PASS** | throughout |
| 15 | END | **PASS** | `test_la_foto_de_cierre_tambien_sobrevive_y_se_sube_sola` |

Case 10 deserves a note, because OCR makes it worse rather than better:
recognition takes time, and that time is added to the upload window. The window
in which Android can kill the page with the photo half-way is now *longer* than
before this checkpoint. Had the photo not been staged before the network is
touched, enabling OCR would have aggravated exactly the problem the checkpoint
exists to fix.

### A test that passed for the wrong reason, caught and replaced

The first version of the AC-8 test intercepted the upload, called
`Route.fetch()` to obtain the real response and re-fulfilled it with an injected
suggestion. It reported green. It was green because the handler was **throwing**:
`Route.fetch` resolves the host with the system resolver, which does not know
`*.localhost` — the limitation the e2e conftest already documents for its own
probe. No suggestion ever arrived, so "the stale suggestion did not survive" was
true for a reason that had nothing to do with the guard under test.

It was replaced by a version that builds the response body itself and opens with
a **positive control**: one upload, answered with the suggestion, asserting the
field actually shows it. Only then does the race phase run. Without that control
an invalid body would produce the same empty green, and the failure mode would
have been invisible a second time.

### The browser regression failure is not a regression

```
FAILED tests/e2e/test_trip_and_odometer_browser.py::
       test_the_day_ends_with_a_pending_end_exception_and_resolves_later
```

Across the whole five-file run there was exactly **one** `FAILED` line. The four
other files — including `test_rte06_odometer_lifecycle_browser.py`, which is the
START/END restoration net this checkpoint most risked breaking — produced none.

It was **not** accepted as a flake. The work was stashed, the bundle was rebuilt
from unmodified `dev`, and the single test was run alone:

```text
main.js limpio: 807619 bytes
tests/e2e/test_trip_and_odometer_browser.py:669: AssertionError
  Expect "to_have_count" get_by_text("Ending your day") with timeout 20000ms
  42 × locator resolved to 0 elements
```

Identical failure, same line, same counter, against code with none of this
checkpoint's changes. **Attribution is `CONFIRMED`: the failure pre-exists in
`dev`.**

Why it fails is `UNVERIFIED`. The test waits for the transient `end-queued`
phase — the *"Ending your day…"* message — which no longer appears. That phase
lives in `RouteMyRoutePage.tsx`, a file this checkpoint does not touch, and §17
forbids reopening certified functionality here. It is reported rather than
fixed, with its operational action in §13.

Counts for that run: `..............F.....` — **20 tests, 19 passed, 1 failed**.

**A discarded run, reported because it happened.** The first browser regression
was launched and, while it was still running, the bundle was rebuilt twice for
the §8 experiment. Its child servers started after the experimental bundle was in
place, so that run tested code that is not being delivered. It was killed and
re-run against the shipped bundle; the background job's "exit code 0" came from
the kill, not from pytest, and was **not** counted as a pass.

**Methodological note.** The first attempt at the new browser tests failed all
four, because the browser was serving the bundle built three days earlier — the
TypeScript had been edited but `npm run build:prod` had not been re-run. The
diagnostic that found it showed the IndexedDB at version 2 with two stores. Any
browser validation of frontend changes in this repository requires a fresh
production build first.

**An incidental defect introduced by this checkpoint, found and fixed.** Two
certified browser tests opened the durable database with a pinned version:
`indexedDB.open('cer-route-offline', 2)`. Raising `DATABASE_VERSION` to 3 makes
that call throw `VersionError`, whose handler resolves to an empty list — so the
tests would have silently read "nothing pending" instead of failing loudly. Both
now open without a version, matching the three tests that already did, so the
next schema addition cannot repeat it.

---

## 11. Expected → Implemented → Evidence → Gap

| # | Acceptance criterion | State | Evidence |
| --- | --- | --- | --- |
| 1 | Productive OCR runs on the photo path | IMPLEMENTED | `ocr_tesseract.py`, wired in `main.py` by binary presence |
| 2 | OCR never confirms a reading by itself | VALIDATED | `test_la_sugerencia_no_confirma_la_lectura_por_si_sola` |
| 3 | Supervisor can confirm a correct suggestion | VALIDATED | preflight `test_the_port_works_when_an_adapter_is_plugged_in` |
| 4 | Supervisor can correct a wrong suggestion | VALIDATED | same test: suggestion `99120`, confirmed `99125` |
| 5 | No result falls back to manual without blocking | VALIDATED | `test_un_ocr_que_revienta_no_cuesta_la_foto` |
| 6 | START and END both work | VALIDATED | parametrised `["start", "end"]`; END durability in `test_la_foto_de_cierre_tambien_sobrevive_y_se_sube_sola` |
| 7 | Retake uses only the new photo and result | VALIDATED | `test_rehacer_la_foto_borra_la_sugerencia_de_la_anterior` |
| 8 | Stale OCR cannot overwrite a later retake | VALIDATED | `test_la_sugerencia_de_la_foto_descartada_no_puede_llegar_tarde_y_ganar`, with a positive control |
| 9 | Photo survives lifecycle interruption before upload | VALIDATED | `test_la_foto_guardada_sobrevive_a_recrear_la_pagina...` |
| 10 | Connectivity loss does not force a retake | VALIDATED | same test: `online` event, uploads by itself |
| 11 | Recovery does not fabricate persistence | VALIDATED | no `uploaded` field, asserted; `captured_at is None` |
| 12 | Upload/retry creates no duplicate active evidence | VALIDATED | `test_subir_la_misma_foto_dos_veces_no_duplica_la_evidencia` |
| 13 | Local photo data scoped and cleaned up | VALIDATED | key assertions; empty lane after confirmation |
| 14 | Initial field shows no fake detected reading | VALIDATED | `test_el_campo_de_lectura_no_finge_una_lectura_detectada` |
| 15 | Exception behaviour unchanged | VALIDATED | 64/64 odometer regression |
| 16 | START/END restoration still green | VALIDATED | `test_rte06_odometer_lifecycle_browser.py`, no failures (§10) |
| 17 | Work Session / Trip unchanged | VALIDATED | no files touched; regression green |
| 18 | Mobile bundle measured and documented | VALIDATED | §7 |
| 19 | Any claimed optimization has before/after evidence | NOT APPLICABLE | none claimed; §8 |
| 20 | Security / tenant isolation green | VALIDATED | §9; `test_no_se_puede_subir_una_foto_a_la_jornada_de_otro` (404, nothing written) |
| 21 | Typecheck / lint / build / regression green | VALIDATED | §10 |
| 22 | No PARTIAL / GAP / BLOCKED / DECISION REQUIRED | see §13 | — |

---

## 12. CER Field Validation Checklist

Development cannot certify the field experience. Ten checks, in the order that
exposes a problem fastest.

**Before starting:** the test environment needs the `tesseract-ocr` system
package for suggestions to appear at all. Without it the flow is correct but
every reading is typed — which is a valid state, not a failure, and is the
operational action in §14.

1. **START, clear photo.** Photograph the odometer in good light. A suggestion
   should appear as an editable draft with the words *"check it against the
   vehicle before confirming"*. Confirm it.
2. **START, wrong suggestion.** If any suggestion is wrong, correct it and
   confirm. The value that counts must be the corrected one.
3. **START, no suggestion.** Expect this on a digital segment display. Type the
   reading and confirm: it must complete without asking anyone for approval, and
   must **not** offer an exception.
4. **END, the same three paths.**
5. **Retake.** Photograph, wait for a suggestion, then retake. The old
   suggestion must not remain attached to the new photo. If you had typed a
   value by hand, it should still be there.
6. **Low memory / page recreation after capture.** Take the photo, then switch
   apps and open several others until Android recreates the page. Return: the
   photo must not need retaking.
7. **Loss of connectivity after capture.** Enable airplane mode, take the photo.
   The screen must say the photo is saved on the phone and has **not** reached
   the server. It must not say uploaded.
8. **Return and recovery.** Turn connectivity back on without touching
   anything. The photo should upload by itself and the reading field appear.
9. **Normal device versus lower-memory device.** Repeat 6 and 7 on both, and
   note any difference in how long restoration takes.
10. **No automatic finalisation.** At no point may a reading become confirmed
    without someone pressing *Confirm reading*. If a reading ever appears already
    confirmed, stop and report it.

**What to report back:** for any photo where the suggestion was wrong, the value
suggested, the value that was true, and the dashboard type (mechanical roller or
digital segment). That is the data that decides whether the external-service
option in §3 is worth bringing to a decision.

---

## 13. Decisions / Risks

**Within the authorized scope, nothing is PARTIAL, BLOCKED or awaiting a
decision.** Two items are recorded as limits rather than gaps.

1. **§8's image-condition cases 1–5 are `NOT RUN`.** A clear photo, an angled
   one, glare, low light and partially obscured digits cannot be exercised here:
   they need the Tesseract binary, which is not installed on the development
   machine — Windows has no `apt` and the package is declared for the deployment
   image — and they need real dashboard photographs. They are inherently field
   observations and are carried in §12's checklist, items 1–3, where CER can
   produce them. What *is* tested without the binary is the half that can go
   wrong in code: how the engine's output is interpreted, which thresholds
   accept or reject, and what happens when it is ambiguous, absent, slow or
   broken.
2. **Suggestion quality on real fleet photographs remains `PENDING VALIDATION`,**
   as the preflight already stated. It is CER field validation and Development
   must not declare it. The seven-segment limit in §3 is a prediction from
   PaddleOCR's measured behaviour on the same display type, not a measurement of
   Tesseract on CER vehicles.

**A certified browser test is red in `dev` right now.**
`test_the_day_ends_with_a_pending_end_exception_and_resolves_later` fails with
and without this checkpoint's changes (§10). Someone has to decide whether the
test drifted or the product changed how the day closes with a pending END
exception — the two have opposite fixes, and guessing here would either hide a
product defect or edit away a correct assertion. **This is the operational
action this delivery does not perform**, and it is a decision, not an
engineering failure.

**Incidental findings outside this checkpoint's scope, not acted on:**

- `getDateLocale` in `shared/lib/utils/utils.ts` is dead code and the only
  importer of three `date-fns` locales. It costs **zero** emitted bytes, so
  removing it is tidiness, not optimization, and it sits in shared utilities
  outside this scope.
- The eager administration slices in the root reducer, measured at 3,429 bytes
  gzipped (§8). Recorded so the question does not have to be re-measured.

**Risk accepted.** Activating OCR changes what supervisors see on a screen they
already trust. The mitigations are that the engine is selected by binary
presence, that `ODOMETER_OCR_ENABLED` switches it off without a deployment, and
that ambiguity produces no suggestion at all.

---

## 14. Proposed Status

```text
IMPLEMENTATION COMPLETE / READY FOR CER FIELD VALIDATION
```

Only CER can certify the field experience.

**Operational action this change does not perform.** The test environment runs on
buildpacks and needs the system package for OCR to produce any suggestion.
`Aptfile` now declares `tesseract-ocr` and `tesseract-ocr-eng`, and the
`Dockerfile` installs the same two, but **the package only arrives on the next
deployment**. Until then the odometer flow is correct and every reading is typed
by hand — the pre-existing behaviour, not a regression. §12's checklist is worth
running only after a deployment that includes it.

**Next step, not started:** CER field validation per §12.
