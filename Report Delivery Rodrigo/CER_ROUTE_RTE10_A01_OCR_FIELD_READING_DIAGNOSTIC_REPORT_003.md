# CER Route — RTE10-A01 OCR Field Reading Diagnostic & Correction

**Report 003** · branch `feature/rte10-a01-ocr-field-reading` · 2026-10-05

---

## Field symptom

The photo is captured and stored, Tesseract is deployed and active, and the
reading never reaches the mileage field. The supervisor sees an empty field and
types the number by hand. The manual path works throughout.

## Classification

```text
IMAGE PREPROCESSING  (Tesseract segmentation mode)
OCR INTERPRETATION / THRESHOLD  (candidate disambiguation, TSV parsing)
```

**Not `ENGINE LIMITATION`.** On a reproduced dashboard the engine reads the
odometer at **96% confidence**. Nothing was wrong with the recognition.

---

## How this was diagnosed without the field photos

The five real photos were in the pilot container and could not be reached from
here. Instead of waiting, Tesseract was installed locally (`scoop install
tesseract`, v5.5.3) and the field condition was **reproduced**: a phone-resolution
image with the structural property that matters — **more than one numeric group**,
which is what every dashboard has and what no synthetic probe had.

That reproduction found three defects, each sufficient on its own to produce the
symptom. Two of them are independent of the installation and therefore apply to
the pilot; the third is installation-dependent and is a latent fragility.

What this does **not** replace is stated in *Remaining limitation*.

---

## Root cause

### 1 — `--psm 7` finds nothing on a dashboard  ·  applies to the pilot

The adapter asked Tesseract for *"a single text line"*. A dashboard is not a
line: it is the odometer, the trip meter, the speed and whatever else the
manufacturer put there, scattered across the frame.

Measured on the same image, same preprocessing:

```text
psm=7   ->  []
psm=6   ->  [('128437', 96.3), ('241.6', 95.5)]
psm=11  ->  [('128437', 96.2), ('241.6', 96.6)]
psm=12  ->  [('128437', 96.2), ('241.6', 96.6)]
```

`psm 7` works for an image that *is* one line of digits — which is exactly the
shape of the synthetic probe used to verify the deployment. **That is why the
probe passed while every field photo produced nothing.** The verification
evidence was shaped like the assumption it was meant to test.

### 2 — The ambiguity rule discarded the correct reading  ·  applies to the pilot

With the segmentation fixed, there are two candidates: `128437` and `241.6`. The
adapter returned `None` for anything other than exactly one candidate.

That rule was deliberate and documented, and it was too strict. On a real
dashboard, two candidates is the normal case, not the ambiguous one — so the
rule guaranteed silence on exactly the photos the feature exists for.

### 3 — The TSV output silently degraded to plain text  ·  latent

Tesseract accepts `tsv` as the name of a **configuration file**. Where that file
is not installed, it warns on stderr, **returns 0**, and falls back to plain
text:

```text
STDERR: read_params_file: Can't open tsv
STDOUT: '128437\r\n'
```

The parser expects twelve tab-separated columns; plain text has one. Every line
was discarded, so the adapter returned `None` for **any** image, with no error
and a zero exit code.

The pilot's installation does ship the file — its probe returned a value — so
this is not what broke the field. It is a failure mode that produces exactly the
field symptom and announces itself nowhere, which is reason enough to remove it.

### 4 — A zero reading was audited as "no suggestion"  ·  minor

```python
"new": str(sugerencia) if sugerencia else None
```

`Decimal("0")` is falsy in Python, so a legitimate reading of zero was recorded
in the audit as an absent suggestion. §5 of the instruction asks for exactly
this check.

### What was ruled out, by measurement rather than opinion

| Hypothesis | Result |
| --- | --- |
| Resize makes digits too small | **No.** With the odometer at 8% of frame width, digits land at ~24 px after the reduction to 1600 px — above Tesseract's ~20 px floor |
| Illuminated dashboards (light digits on dark) break recognition | **No.** Both polarities read at ~96%; inverting changes nothing |
| Minimum confidence of 60 is too strict | **No.** Measured confidences are ~96 |
| Frontend discards the suggestion | **No.** `ocr_detected_reading` was `None` in all three field records, so there was nothing to discard. `readingAsNumber` handles `0` correctly |

---

## Correction

Four changes, all inside the current pipeline. No provider change, no business
rule, no architecture, no privacy boundary.

| # | Change | Why it is not "weakening a control" |
| --- | --- | --- |
| 1 | `--psm 7` → `--psm 11` (sparse text) | Matches what a dashboard is. Nothing is relaxed |
| 2 | Disambiguate by **strict digit majority** | The odometer accumulates and the trip meter resets, so the first has more digits for almost the whole life of the vehicle. Not size, not position, not "the biggest number" |
| 3 | TSV by parameter (`-c tessedit_create_tsv=1`), and a non-TSV output raises instead of returning `None` | Removes a dependency on a file that may not ship, and stops a broken installation from being indistinguishable from an unreadable photo |
| 4 | `if sugerencia is not None` in the audit | A zero is a reading |

**A tie is still ambiguous and still suggests nothing.** If two candidates have
the same digit count, the photo does not distinguish them and silence remains
the right answer. That is what keeps change 2 from becoming "pick one".

---

## Before / After

Reproduced dashboard, two numeric groups, phone resolution, both polarities:

| | Before | After |
| --- | --- | --- |
| Light dashboard, dark digits | `None` | **`128437.0`** |
| Illuminated dashboard, light digits | `None` | **`128437.0`** |
| Installation without the `tsv` config | `None`, silently | raises, logged, still no suggestion to the user |

The suggested value is the **odometer**, not the trip meter.

---

## Tests

| Suite | Result |
| --- | --- |
| `tests/test_odometer_ocr_reader.py` | **17/17 PASS** |
| Odometer + OCR + retention + media pipeline | **111/111 PASS** |

New tests fix the behaviour that was wrong and the behaviour that must not
regress: the digit-majority choice in both token orders, the tie that stays
silent, the non-TSV output that is declared unavailable, and the segmentation
mode itself — because returning to `7` reproduces the entire field failure.

The test that encoded the old rule (*two candidates are ambiguous*) was replaced
rather than deleted: its intent — do not guess — now lives in the tie test.

---

## Remaining limitation

**This was diagnosed on a reproduction, not on the field photographs.** The
pilot's five real photos could not be reached from here, and the dashboard type
was never reported.

What the reproduction cannot tell you:

- whether a **seven-segment LCD** reads at all — the known engine limitation,
  unchanged and still expected to produce no suggestion;
- how glare, angle and low light behave on real glass;
- whether a real odometer's font reads as cleanly as a rendered one.

So the acceptance criteria that require real photographs — items 1, 2, 5 and 6
of §Acceptance — are **`PENDING REAL-PHOTO VALIDATION`**. What is demonstrated is
that the pipeline, which previously could not produce a suggestion from *any*
multi-element image, now produces the correct one at 96% confidence.

**To close it:** take one photo per dashboard type in the pilot and run the
adapter against it. If a legible dashboard still yields nothing after this
correction, the cause is the engine and the next conversation is the external
provider — which remains CER's decision and is untouched here.

---

## STOP

Correction implemented and validated to the limit of the available evidence. No
other checkpoint started.
