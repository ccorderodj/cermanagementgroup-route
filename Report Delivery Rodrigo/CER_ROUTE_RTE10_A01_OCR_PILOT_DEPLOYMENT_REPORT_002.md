# CER Route — RTE10-A01 OCR Pilot Deployment

**Report 002** · incremental over Report 001 · branch
`feature/rte10-a01-ocr-pilot-deployment` · 2026-10-05

Scope per `CER_ROUTE_RTE10_A01_OCR_PILOT_DEPLOYMENT_INSTRUCTIONS_001.md`.

---

## 1. Deployment Result

```text
BLOCKED — PILOT DEPLOYMENT ACCESS
```

**Not** `BLOCKED — PILOT ENVIRONMENT OCR DEPENDENCY`. The distinction matters and
it is in CER's favour: there is no missing dependency and nothing about the pilot
environment prevents OCR. The packages are declared in the supported mechanism
and will install on the next build. What is missing is the ability to **perform
the deployment**: this agent has no access to the DigitalOcean account —
verified, not assumed:

```text
doctl: command not found
credenciales de DO en el entorno: (ninguna)
config de doctl: sin config
```

Everything that does not require that access is **done and green**. The
deployment itself, and the three verification steps that can only run against a
live pilot, need someone with console access to the app. §8 of this report is the
exact sequence, written so it can be executed without interpretation.

The §1 pre-deployment gate — the only part of this task that was engineering
work — is closed. It included the one real change: aligning the stale browser
test, which CER authorized here and which is covered in §3.

**Nothing is declared green on evidence that was not produced.** Per the status
rule, `RTE10-A01 DEPLOYED TO PILOT / OCR ACTIVE / READY FOR CER FIELD
VALIDATION` is **not** claimed.

---

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
| `tesseract-ocr` declared | **done** | `Aptfile` on `dev` |
| `tesseract-ocr-eng` declared | **done** | `Aptfile` on `dev` |
| Supported mechanism | **yes** | `Aptfile` is what buildpacks read |
| Survives the next deployment | **yes** | it is in the repository, not a manual install |
| **Actually installed in pilot** | `NOT VERIFIED` | requires the deployment (§8) |

`Aptfile` contents on `dev`:

```
tesseract-ocr
tesseract-ocr-eng
```

No temporary manual install was performed, and none should be: §3 of the
instruction forbids it, and it would vanish on the next build while making the
environment look correct.

---

## 5. OCR Runtime Verification

All five checks of §4 are `NOT VERIFIED` — they require the live pilot. §8 gives
the commands. Two notes that will save the person running them a wrong
conclusion:

**The reader is registered in the uvicorn process, not in the image.** It is
wired by a startup event. Opening a fresh Python console in the container and
inspecting `get_odometer_reader()` returns `NoSuggestionReader`, because that
console is a different process that never ran the startup. That result would look
like a failed activation and would be meaningless. The authoritative signals are
the **startup log line** and the direct **adapter probe** in §8.4.

**`ODOMETER_OCR_ENABLED` defaults to `True`**, so OCR activates with no
environment variable at all. It should still be set explicitly in the App Spec
for the pilot: §4 asks to verify the flag is enabled and that it can disable OCR
without a code change, and a variable that is actually present is the only
version of that which is verifiable — and the only version a person under
pressure will find when they need the rollback switch.

Selection logic, for whoever audits the result:

```
ODOMETER_OCR_ENABLED false  →  NoSuggestionReader   (OCR off by choice)
binary not found            →  NoSuggestionReader   (OCR off by absence)
otherwise                   →  TesseractReader      (productive)
```

The middle row is the one that matters for honesty: a pilot whose build did not
install the package behaves exactly as it does today — correct flow, every
reading typed — and says so in the log. It does not fail, and it does not pretend
to have OCR.

---

## 6. Smoke Tests — START, END, Fallback, Durability

| § | Check | State |
| --- | --- | --- |
| 5 | START — capture, suggestion attempted, editable, explicit confirmation | `NOT RUN` |
| 5 | END — same behaviour | `NOT RUN` |
| 5 | OCR failure / no result does not block; manual entry available | `NOT RUN` on pilot |
| 5 | No automatic odometer exception from an absent suggestion | `NOT RUN` on pilot |
| 5 | Photo durably staged before upload | `NOT RUN` on pilot |
| 5 | Connectivity loss does not force an immediate retake | `NOT RUN` on pilot |
| 5 | Recovery resumes when connectivity returns | `NOT RUN` on pilot |

**`NOT RUN` on the pilot is not the same as untested.** Every one of these
behaviours has automated evidence against a real PostgreSQL and a real browser,
reported in Report 001 and re-run green here:

| Behaviour | Automated evidence |
| --- | --- |
| Suggestion never confirms by itself | `test_la_sugerencia_no_confirma_la_lectura_por_si_sola` |
| Wrong suggestion corrected by the supervisor | preflight: suggested `99120`, confirmed `99125` |
| OCR failure does not block, both ends | `test_un_ocr_que_revienta_no_cuesta_la_foto` |
| No automatic exception on OCR failure | same test: evidence stays `pending`, confirm succeeds as `photo` |
| Photo staged before upload | `test_la_foto_queda_guardada_cuando_la_subida_no_llega` |
| Connectivity loss, then recovery | same test plus the `online` event |
| END durability | `test_la_foto_de_cierre_tambien_sobrevive_y_se_sube_sola` |

What the pilot adds that no test here can is the only thing that matters now:
**a real Tesseract reading a real dashboard.** Everything else is already
demonstrated.

---

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

## 8. What Has To Happen Next, In Order

Everything below needs console or dashboard access to the pilot app.

### 8.1 — Confirm the pilot is building `dev`

In the App Platform dashboard, check the app's source branch is `dev` with
`deploy_on_push`. If it is, the merge of !43 already triggered a deployment and
the next steps verify it; if it is pinned to another branch, that is the blocker
to report back.

### 8.2 — Set the flag explicitly

Add to the app-level environment variables:

```
ODOMETER_OCR_ENABLED = true
```

Not because the default is wrong — it is `true` — but because §4 asks for a
verifiable flag and a findable rollback switch.

### 8.3 — Confirm the packages installed

In the app console:

```bash
tesseract --version
which tesseract
tesseract --list-langs
```

Expected: a version banner, a path, and `eng` in the language list. If
`tesseract` is not found, **stop here** and report it — that, and only that,
would be `BLOCKED — PILOT ENVIRONMENT OCR DEPENDENCY`.

### 8.4 — Probe the adapter end to end

Still in the console. This exercises the real adapter on a synthetic image with
digits, inside the pilot container:

```bash
python - <<'EOF'
import io
from PIL import Image, ImageDraw, ImageFont
from app.config import settings
from app.routers_api.odometer.ocr_tesseract import (
    TesseractReader, tesseract_disponible,
)

print("ODOMETER_OCR_ENABLED:", settings.ODOMETER_OCR_ENABLED)
print("binario:", settings.ODOMETER_OCR_BINARY,
      "disponible:", tesseract_disponible(settings.ODOMETER_OCR_BINARY))

imagen = Image.new("RGB", (640, 200), "white")
dibujo = ImageDraw.Draw(imagen)
dibujo.text((40, 50), "128437", fill="black",
            font=ImageFont.load_default(size=96))
buffer = io.BytesIO()
imagen.save(buffer, format="PNG")

lector = TesseractReader(
    binary=settings.ODOMETER_OCR_BINARY,
    timeout_seconds=settings.ODOMETER_OCR_TIMEOUT_SECONDS,
)
print("sugerencia:", lector.suggest(
    image=buffer.getvalue(), content_type="image/png"))
EOF
```

**Expected:** `True`, `True`, and `sugerencia: 128437.0`.

This is the decisive technical check: a reading printed here means the binary,
the language data, the preprocessing, the invocation and the interpretation all
work **in the pilot**, with no device and no vehicle involved.

> This probe could not be dry-run locally — Windows has no `apt` and the binary
> is not installed on the development machine. If it errors for a reason other
> than a missing binary, send the traceback rather than working around it.

### 8.5 — Confirm the reader the application selected

In the app's **runtime** logs (not the build logs), look for one of:

```
ODOMETER OCR | lector activo: tesseract (tesseract)
ODOMETER OCR | 'tesseract' no está instalado; sin sugerencias y el supervisor
               teclea la lectura, que es el camino normal
```

The first line is the goal. The second is a working pilot without OCR — correct,
but not what this deployment is for.

### 8.6 — Verify the rollback switch

Set `ODOMETER_OCR_ENABLED = false`, let it redeploy, and confirm the log shows no
active reader and that photo capture plus manual confirmation still work. Then
set it back to `true`. This proves §4's "the flag can still disable OCR without
code changes" on the environment where it would be used in anger.

### 8.7 — Smoke test on a device

With a phone against the pilot, the four blocks of §5: START, END, a no-result
case, and the durability pair (airplane mode after the photo, then signal back).
The ten-point list in Report 001 §12 is the fuller version for field validation.

---

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
BLOCKED — PILOT DEPLOYMENT ACCESS
```

| Part | State |
| --- | --- |
| §1 pre-deployment gate | **COMPLETE** — candidate confirmed, stale test aligned, regression 23/23 |
| §3 OCR dependencies declared in the supported mechanism | **COMPLETE** |
| §2 deploy to pilot | **BLOCKED** — access |
| §4 runtime verification | **PENDING** — §8.3–8.5 |
| §5 smoke tests | **PENDING** — §8.7 |
| §2 general production | **not touched**, as instructed |

`RTE10-A01 DEPLOYED TO PILOT / OCR ACTIVE / READY FOR CER FIELD VALIDATION` is
**not** declared: the binary's presence in the pilot, the selected reader and
both smoke tests have no evidence yet. `RTE10-A01 CLOSED` is not declared either
— field certification is CER's.

**Next step, not started:** §8, from 8.1. Paste the output of 8.3 and 8.4 and the
remaining verification can be completed and this report amended to its final
status.
