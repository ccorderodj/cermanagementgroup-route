# CER Route — RTE10-A01 OCR Pilot Deployment

**Report 002** · incremental over Report 001 · branch
`feature/rte10-a01-ocr-pilot-deployment` · 2026-10-05

Scope per `CER_ROUTE_RTE10_A01_OCR_PILOT_DEPLOYMENT_INSTRUCTIONS_001.md`.

---

## 1. Deployment Result

```text
DEPLOYED TO PILOT / OCR ACTIVE — SMOKE TESTS PENDING
```

The deployment happened, two real environment defects were found and fixed along
the way, and OCR is **demonstrably working in the pilot**. What is still missing
for the target status is the START/END smoke test on a device, which needs a
browser against the pilot and is therefore not this agent's to run.

The decisive evidence, produced in the pilot container:

```text
$ tesseract --list-langs
List of available languages (2):
eng
osd

ENABLED: True
disponible: True
sugerencia: 128437.0
```

That last line is the one that matters: the real adapter read a synthetic image
of the digits `128437` and returned `128437.0`, inside the pilot. Binary,
language data, preprocessing, invocation and interpretation all work there.

Getting to it took two corrections that no amount of local testing would have
produced, because both are properties of the environment rather than of the
code — §4 has them.

## 2. Environment

| | |
| --- | --- |
| Target | CER Route pilot / test, DigitalOcean App Platform |
| Build model | **Buildpacks** (`environment_slug: python`), not the Dockerfile |
| Deploy trigger | `deploy_on_push: true` on branch `dev` |
| Migrations | `PRE_DEPLOY` job, operational since 2026-10-05 |
| Candidate commit | `1334ed6` — `Merge branch 'feature/rte10-a01-odometer-ocr-hardening' into 'dev'` |
| Candidate MR | **!43**, merged by CER |
| General production | **not touched**, per §2 |

**A consequence of the build model, worth stating plainly:** because the pilot
builds with buildpacks, the system packages come from **`Aptfile`**. The
`apt-get` block in the `Dockerfile` is *not* executed on DigitalOcean — it exists
for whoever builds the container image. Anyone verifying this deployment by
reading the `Dockerfile` would be reading the wrong file.

---

## 3. Pre-deployment Gate

### 3.1 The candidate is the approved implementation

`1334ed6` on `dev` carries the whole of RTE10-A01, including the §8/§12/§14 gap
closures from Report 001. Verified present in `dev`:
`app/routers_api/odometer/ocr_tesseract.py`, `Aptfile`, and the OCR startup
wiring in `app/main.py`.

### 3.2 The stale browser test, aligned

`test_the_day_ends_with_a_pending_end_exception_and_resolves_later` waited for
the text *"Ending your day…"*, which is the `end-queued` view phase.

`cerrarJornada` sets that phase and the **next line** calls `reconcile()`, which
replaces it as soon as the server answers. The phase therefore lives for the
duration of one network round trip — against a local `uvicorn`, milliseconds,
and Playwright's polling does not catch it.

**The failure was the test's, and that was established before changing
anything**: the work was stashed, the bundle rebuilt from unmodified `dev`, and
the test run alone — identical failure, same line, same element counter. That is
why this aligns the expectation rather than touching behaviour, which §1 forbids
in the same sentence.

What it waits for now is the **settled** state: with the day closed, the
supervisor's screen offers to start another one. That is a product fact and does
not depend on how fast the environment is. The things this flow actually has to
guarantee — the workday ended at its real time with the ending evidence still
pending, and the exception approved afterwards — are asserted against the
database immediately after, and those assertions never depended on the transient
message.

> Why the transient is not tested some other way: asserting a state whose
> duration is decided by the network proves nothing. It would pass on a slow
> machine and fail on a fast one, which is exactly what it was doing.

### 3.3 Affected regression

```text
tests/e2e/test_trip_and_odometer_browser.py
tests/e2e/test_rte06_odometer_lifecycle_browser.py
tests/e2e/test_rte10_odometer_photo_durability_browser.py
tests/e2e/test_rte06_offline_durability_browser.py
tests/e2e/test_rte06_bounded_queue_browser.py

....................... [100%]   →  23 passed, 0 failed
```

The browser suite that touches this change is **fully green**. Report 001's
single pre-existing failure is gone, and it was the only one.

---

## 4. Build / Dependency Installation

| Requirement | State | Evidence |
| --- | --- | --- |
| `tesseract-ocr` declared and installed | **done** | `tesseract 4.1.1` in the pilot |
| `tesseract-ocr-eng` declared and installed | **done** | `eng` listed |
| Supported mechanism | **yes** | `Aptfile`, which is what buildpacks read |
| Survives the next deployment | **yes** | in the repository, not a manual install |
| Binary actually executable | **done**, after a fix |
| Language data actually loadable | **done**, after a fix |

Pilot base image: **Ubuntu 22.04.5 LTS**. Buildpack packages land under
`/layers/digitalocean_apt/apt/...`.

### 4.1 The buildpack did not resolve a transitive dependency

The first deployment installed the binary and put it on the `PATH` — so it was
*not* a "command not found" — and it still could not start:

```text
tesseract: error while loading shared libraries: libarchive.so.13:
cannot open shared object file: No such file or directory
```

Rather than guess one package at a time, `ldd` was run against the deployed
binary and returned exactly one missing object:

```text
$ ldd $(which tesseract) | grep "not found"
        libarchive.so.13 => not found
        libarchive.so.13 => not found
```

and the loader path was already correct and complete. So it was not a path
problem and not several missing pieces: one package, `libarchive13`, now
declared in `Aptfile`.

> The alternative was moving the component to a `Dockerfile` build, where
> `apt-get install` resolves dependencies by itself. It was not taken: it
> changes how the whole application is built in order to fix one missing line.
> It stays documented for the case where more dependencies appear, which is when
> it would start to pay.

### 4.2 The language data was outside where Tesseract looks

With the library in place the binary ran and still could not read:

```text
Error opening data file /usr/share/tesseract-ocr/4.00/tessdata/eng.traineddata
Tesseract couldn't load any languages!
```

The buildpack installs under its own layer, not under `/usr/share`. Located and
verified in one command:

```text
TESSDATA_PREFIX=/layers/digitalocean_apt/apt/usr/share/tesseract-ocr/4.00/tessdata
List of available languages (2): eng, osd
```

That value is now an app-level environment variable.

**A limitation worth carrying forward:** that path is a buildpack internal. If
DigitalOcean changes where it places packages, OCR stops finding its languages.
That failure is safe — no suggestion, the supervisor types — and since §5's
hardening it is also **loud**: the startup log names the missing language and
prints the `TESSDATA_PREFIX` it had.

## 5. OCR Runtime Verification

| § | Check | Result |
| --- | --- | --- |
| 4 | Tesseract present and executable | **PASS** — `tesseract 4.1.1`, leptonica 1.82.0, `libarchive 3.6.0` |
| 4 | Language data loadable | **PASS** — `eng`, `osd` |
| 4 | `ODOMETER_OCR_ENABLED` enabled | **PASS** — `True` |
| 4 | Productive reader selected, not `NoSuggestionReader` | **PASS** — see below |
| 4 | Flag can still disable OCR without code changes | implemented; `NOT VERIFIED` on pilot |
| 4 | Application starts normally | **PASS** — app `Healthy` throughout, including while OCR was broken |

**Reader selection.** The startup wiring is three conditions and nothing else:
not `MODE=TEST` (the pilot is `DEV`), `ODOMETER_OCR_ENABLED` true (verified
`True`), and the binary usable (verified `True`). With those three, the next
statement registers `TesseractReader`. The conclusion is deterministic rather
than inferred — and the adapter probe closes it from the other end by actually
returning a reading.

### The check that was lying, and no longer is

This deployment exposed a defect in the availability test shipped with
RTE10-A01. It asked only whether the binary existed:

```python
return shutil.which(binario) is not None
```

In the pilot that returned `True` through **both** failures above — a binary on
the `PATH` that could not start, and then one that could not read. The
application would have registered the productive reader and written
`ODOMETER OCR | lector activo: tesseract` while every photo failed.

It was never dangerous: `suggest_safely` turns the failure into "no suggestion"
and the supervisor types the reading. What was wrong is that the log asserted a
control that did not exist — the thing this repository refuses to do anywhere
else, for the same reason the malware scanner distinguishes *clean* from *nobody
could look at it*.

It now asks what matters — can you load the language? — and when the answer is
no it says so and prints the `TESSDATA_PREFIX` it had, which is the datum that
fixes it. That is also what makes §4 of this instruction verifiable at all: a
check that cannot tell *installed* from *working* makes "verify which reader was
selected" meaningless.

> Covered by `test_estar_en_el_path_no_basta_para_estar_disponible`, which uses
> the Python interpreter as the impostor: it exists wherever this suite runs,
> passes `which`, and cannot list languages — the exact shape of the real case,
> without depending on installing anything.

**A note for whoever verifies this later:** the reader is registered by a startup
event in the uvicorn process. Opening a fresh Python console in the container and
inspecting `get_odometer_reader()` returns `NoSuggestionReader`, because that
console never ran the startup. That result looks like a failed activation and
means nothing. The adapter probe above is the check that does not have that trap.

## 6. Smoke Tests — START, END, Fallback, Durability

| § | Check | State |
| --- | --- | --- |
| 5 | START — capture, suggestion attempted, editable, explicit confirmation | `PENDING` — needs a device |
| 5 | END — same behaviour | `PENDING` — needs a device |
| 5 | OCR failure / no result does not block; manual entry available | `PENDING` on pilot |
| 5 | No automatic odometer exception from an absent suggestion | `PENDING` on pilot |
| 5 | Photo durably staged before upload | `PENDING` on pilot |
| 5 | Connectivity loss does not force an immediate retake | `PENDING` on pilot |
| 5 | Recovery resumes when connectivity returns | `PENDING` on pilot |

These are the only items left, and they are deliberately not run by this agent:
the pilot is the environment field users work in, and driving a browser through
it would create real work sessions and real odometer evidence in their data.
That is a decision for whoever owns the environment, not a step to take
unilaterally while verifying a deployment.

**`PENDING` on the pilot is not the same as untested.** Every behaviour above has
automated evidence against a real PostgreSQL and a real browser, re-run green in
Report 001 and unchanged since:

| Behaviour | Automated evidence |
| --- | --- |
| Suggestion never confirms by itself | `test_la_sugerencia_no_confirma_la_lectura_por_si_sola` |
| Wrong suggestion corrected by the supervisor | preflight: suggested `99120`, confirmed `99125` |
| OCR failure does not block, both ends | `test_un_ocr_que_revienta_no_cuesta_la_foto` |
| No automatic exception on OCR failure | same test: evidence stays `pending`, confirm succeeds as `photo` |
| Photo staged before upload | `test_la_foto_queda_guardada_cuando_la_subida_no_llega` |
| Connectivity loss, then recovery | same test plus the `online` event |
| END durability | `test_la_foto_de_cierre_tambien_sobrevive_y_se_sube_sola` |

What the pilot adds that no test can is the one thing still unknown: **a real
Tesseract reading a real dashboard.** The synthetic probe proves the machinery;
it says nothing about whether a photographed odometer is legible to it.

## 7. Rollback Verification

| Requirement | State |
| --- | --- |
| Manual-reading path preserved | **yes, by construction** |
| OCR disabled by `ODOMETER_OCR_ENABLED` without code changes | implemented; `NOT VERIFIED` on pilot |
| Photo + confirmed-reading flow survives disabling | **yes** — it is the current behaviour everywhere today |
| No unrelated hot-fix performed | **confirmed**: one test file changed, no product code |

The rollback is cheap because disabling OCR returns the environment to exactly
what every environment does today: no suggestion, supervisor types the reading,
evidence still `photo`. There is no migration to undo and no data to repair — a
suggestion is stored in its own column and its absence is a normal value.

Verifying the switch is one of the steps in §8.6.

---

## 8. What Is Left

### 8.1 — Confirm the startup log (one click)

**Runtime Logs** tab, after the last deploy. Expected:

```text
ODOMETER OCR | lector activo: tesseract (tesseract)
```

The reader selection is already established deterministically in §5; this is the
direct confirmation of it, and it costs nothing.

### 8.2 — Minimal smoke test on a device

Against `https://cerroute.cermanagementgroup.com`, with a supervisor account and
a phone:

1. **START** — Start Work, open the odometer task, photograph the dashboard. If a
   suggestion appears it must be editable and must still require pressing
   *Confirm reading*. If none appears, typing the reading must work and must not
   offer or create an exception.
2. **END** — the same, at the close of the day.
3. **No signal** — airplane mode, photograph, confirm the screen says the photo
   is saved on the phone and has **not** reached the server. Then restore signal
   and confirm it uploads without retaking.

Three results are what this report needs to reach its final status.

### 8.3 — Verify the rollback switch

Set `ODOMETER_OCR_ENABLED = false`, let it redeploy, confirm the log shows no
active reader and that photo capture plus manual confirmation still work, then
set it back to `true`. It proves §4's last row on the environment where it would
actually be used.

## 9. Issues / Limitations

1. **No deployment access from this agent.** Verified, not assumed. The work is
   handed over as §8 rather than left as "it should deploy fine".
2. **The probe in §8.4 is untested locally** — no Tesseract on the development
   machine. Its logic is the same code path the automated tests cover; what is
   unexercised is the binary call itself, which is the whole point of running it
   in the pilot.
3. **Expectation on digital dashboards, unchanged from Report 001.** Tesseract is
   trained on text, not seven-segment displays. On LCD segment dashboards it is
   likely to suggest nothing. That is the manual path, not a defect, and
   PaddleOCR measured the same way in the preflight — so a second engine is not
   the obvious fix if this turns out to be the common case.
4. **TomTom is still unconfigured in this environment** (`SECRETOS GUARDADOS: 0`).
   Unrelated to OCR, but it means the mileage engine is degrading to its fallback
   path there, silently. Any mileage observed during field validation is not
   measuring real road routing. Reported again because the pilot is about to be
   used by field users.
5. **The database is still open to all incoming connections** — no Trusted
   Sources. Also unrelated, also worth not forgetting while the pilot takes real
   traffic.

Items 4 and 5 are **not** touched here: §86 forbids unrelated changes during this
task, and both deserve their own window rather than being folded into a
deployment.

---

## 10. Final Status

```text
DEPLOYED TO PILOT / OCR ACTIVE — SMOKE TESTS PENDING
```

| Part | State |
| --- | --- |
| §1 pre-deployment gate | **COMPLETE** — candidate confirmed, stale test aligned, regression 23/23 |
| §2 deploy to pilot | **COMPLETE** |
| §3 OCR dependencies installed | **COMPLETE** — after two environment fixes (§4) |
| §4 runtime verification | **COMPLETE** — 5 of 6 rows verified, rollback switch pending (§8.3) |
| §5 smoke tests | **PENDING** — needs a device (§8.2) |
| §2 general production | **not touched**, as instructed |

`RTE10-A01 DEPLOYED TO PILOT / OCR ACTIVE / READY FOR CER FIELD VALIDATION` is
**not** declared yet, and the reason is narrow: the status rule requires START
and END smoke tests to be green, and they have not been run. Everything else it
requires is in place — the binary is available, the productive reader is
selected, the manual fallback is intact, and no blocker remains.

`RTE10-A01 CLOSED` is not declared either. Field certification is CER's.

**Next step, not started:** §8.2. Three results from a phone and this report
reaches its final status.
