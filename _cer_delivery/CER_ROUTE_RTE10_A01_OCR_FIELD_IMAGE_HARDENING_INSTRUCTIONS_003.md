# CER Route — RTE10-A01 OCR Field Image Hardening
## Product Owner Instructions for Development Agent
### Revision 003

**Purpose:** correct the remaining OCR failure observed on real/representative odometer images without weakening the false-positive protections already added to RTE10-A01.

**Mode:** targeted OCR preprocessing hardening + multiscale validity correction + regression evidence.

**Reference branch:** `dev`

**Do not replace Tesseract in this checkpoint.**  
**Do not lower confidence thresholds merely to make a sample pass.**  
**Do not change Supervisor confirmation semantics.**

---

# 1. Context

The current `dev` baseline already contains the productive server-side Tesseract OCR path for odometer capture.

The relevant current behavior includes:

```text
Tesseract on server
→ grayscale + autocontrast preprocessing
→ --psm 11
→ numeric whitelist
→ MIN_CONFIANZA = 60
→ MIN_DIGITOS = 4
→ read at multiple configured scales
→ require agreement before suggesting
→ Supervisor confirms/corrects
```

The current multiscale configuration is:

```python
ESCALAS = (2400, 3200, 1600)
COINCIDENCIAS_NECESARIAS = 2
```

CER has now provided representative odometer images for which the visible odometer reading is:

```text
151517
```

and the current OCR path does not reliably surface that reading.

The observed image class includes:

- a full dashboard image where the odometer occupies a relatively small area;
- a tight odometer crop;
- low native resolution compared with normal modern phone captures;
- white mechanical digits on a dark background;
- moderate blur/softness and compression.

Two technical hypotheses must be investigated and closed with evidence.

## H1 — Current preprocessing is not strong enough for this digit edge profile

The current preprocessing ends effectively at:

```python
gris = ImageOps.autocontrast(imagen.convert("L"))
```

A bounded sharpening step after grayscale/autocontrast is expected to improve character-edge separation without requiring a lower confidence threshold.

A reasonable initial experiment is:

```python
ImageFilter.UnsharpMask(
    radius=1.2,
    percent=180,
    threshold=2,
)
```

This is **technical guidance, not a mandated final parameter set**. Development must measure and choose the smallest preprocessing adjustment that works reliably without increasing false positives.

## H2 — The current “multiscale agreement” is not always truly multiscale

`normalize_image()` currently uses Pillow `thumbnail()`.

`thumbnail()` downsizes but does not upscale.

Therefore, when an input image is already smaller than all configured target dimensions, passes requested at:

```text
2400
3200
1600
```

may all process the same effective pixel dimensions.

If the same effective image is passed to Tesseract multiple times, repeated identical output must not be treated as independent multiscale agreement.

The safety rule remains valid:

> independent evidence that agrees is useful; repeating the same evidence is not additional confidence.

---

# 2. Objective

Deliver a targeted hardening of `ocr_tesseract.py` so that readable low-resolution odometer images such as the CER reference case can produce a correct assistive suggestion while preserving the conservative behavior already established.

Required target behavior:

```text
readable odometer image
→ preprocessing improves digit legibility
→ OCR identifies plausible reading
→ independent processing passes agree when applicable
→ suggestion = 151517
→ Supervisor still confirms/corrects
```

If the image remains ambiguous:

```text
image
→ OCR outputs conflict / confidence is insufficient
→ no suggestion
→ manual reading remains available
```

A missing suggestion is still preferable to a confident-looking wrong value.

---

# 3. Confirmed Product Rules

## PR-01 — Supervisor confirmation remains authoritative

OCR remains assistive only.

```text
OCR suggestion ≠ confirmed reading
```

Do not auto-confirm, auto-submit or make OCR authoritative.

## PR-02 — False-positive protection must not be weakened to improve recall

Do not solve this defect by simply reducing:

```python
MIN_CONFIANZA
MIN_DIGITOS
COINCIDENCIAS_NECESARIAS
```

unless executed evidence demonstrates that a threshold change is safer than the current value across positive and negative cases.

The expected first path is better image preparation and truthful multiscale semantics.

## PR-03 — No OCR result must not block operations

Failure, timeout, disagreement, low confidence or unreadable image must continue to fall back to manual entry.

## PR-04 — Agreement must represent independent evidence

Two identical effective preprocessing passes must not be counted as two independent confirmations merely because they were invoked with two different configured maximum dimensions.

## PR-05 — No external OCR provider in this delta

Do not introduce Google Vision, Textract, Azure Vision, PaddleOCR or any other provider as part of this correction.

The checkpoint is to harden the existing Tesseract implementation.

---

# 4. Scope

This delta includes only:

1. reproduce and characterize the current failure using the CER reference image class;
2. measure current Tesseract output before modifying behavior;
3. improve preprocessing for low-resolution/mechanical odometer digits;
4. correct the semantics of multiscale processing for images smaller than the configured target dimensions;
5. preserve the current conservative candidate-selection rules;
6. add regression coverage for both correct reads and false-positive protection;
7. execute affected odometer/OCR regression;
8. produce an incremental evidence report.

---

# 5. Out of Scope

Do not use this task to:

- replace Tesseract;
- add an external OCR provider;
- redesign the odometer capture UI;
- implement automatic odometer confirmation;
- change Work Session lifecycle;
- change START/END business rules;
- change odometer exception behavior;
- change RBAC;
- change tenant hierarchy;
- change routing/mileage;
- change photo-retention policy;
- broadly refactor the media pipeline;
- introduce a manual cropping UX unless a later CER decision explicitly requests it;
- perform unrelated frontend/backend cleanup.

---

# 6. Baseline Evidence Required Before the Fix

Before changing production behavior, capture the current result for the reference case.

For each reference image or equivalent controlled fixture, record:

```text
original dimensions
effective dimensions at each configured scale
Tesseract token(s)
confidence per token
candidate after filtering
final reading per pass
final suggest() result
```

The purpose is to distinguish:

```text
recognition failure
vs
confidence filtering
vs
candidate selection
vs
multiscale agreement failure
```

Do not diagnose from the final `None` alone.

If the raw CER images cannot appropriately be committed to the repository, use them for local/pilot evidence and create a non-sensitive fixture that reproduces the same technical characteristics for automated regression.

Do not silently commit field evidence containing information CER did not authorize for repository storage.

---

# 7. Functional Requirements

## FR-01 — Improve preprocessing without lowering the safety bar

Evaluate a bounded sharpening stage after grayscale/autocontrast.

A recommended starting experiment is:

```python
from PIL import ImageFilter

gris = ImageOps.autocontrast(imagen.convert("L"))
procesada = gris.filter(
    ImageFilter.UnsharpMask(
        radius=1.2,
        percent=180,
        threshold=2,
    )
)
```

Development owns the final parameters and may choose another small Pillow-native sharpening technique if the evidence is better.

Required properties:

- deterministic;
- inexpensive;
- no external dependency;
- no temporary image written to disk;
- suitable for normal phone images as well as low-resolution images;
- does not create a material new false-positive class.

Do not add a large image-processing framework for this.

## FR-02 — Preserve current confidence protection

The current confidence floor is a deliberate false-positive control.

Keep:

```python
MIN_CONFIANZA = 60.0
```

unless comparative evidence across positive and negative fixtures justifies a change.

A reference image becoming readable because preprocessing improved confidence is acceptable.

A reference image becoming “accepted” only because the threshold was lowered is not sufficient closure.

## FR-03 — Make multiscale processing actually distinct

Development must inspect what dimensions each pass truly sends to Tesseract.

When the source is smaller than the configured maximum dimensions, choose the smallest architecture-compatible strategy that preserves the intent of multiscale agreement.

Valid implementation directions include, but are not limited to:

### Option A — Intentional upscale variants

Generate genuinely different OCR inputs for small images using high-quality resampling, then process those distinct variants.

### Option B — Distinct preprocessing variants

Use scale/preprocessing combinations that create materially distinct OCR inputs without pretending that `max_dimension` alone changed the source.

### Option C — Deduplicate identical effective passes

Detect when multiple configured scales resolve to the same effective image/dimensions and do not count those duplicate passes as independent agreement.

If this option reduces the available number of independent passes, define a conservative decision rule rather than automatically weakening the required confidence.

Development chooses the technique based on measured behavior.

## FR-04 — Do not turn upscaling into invented detail

If upscaling is used, treat it as an OCR preprocessing technique, not as new evidence.

Upscaling may improve edge geometry for the recognizer but does not create information that was absent in the source.

The final decision rule must remain conservative.

## FR-05 — Preserve odometer-vs-dashboard protections

The current safeguards against reading another dashboard number as the odometer must remain effective.

At minimum preserve/revalidate:

- `MIN_DIGITOS = 4`;
- numeric whitelist;
- candidate validation;
- odometer vs trip-meter selection behavior;
- equal-digit ambiguity behavior;
- multiscale disagreement → no suggestion;
- speedometer-like short values such as `60` or `120` → no suggestion.

## FR-06 — Maintain graceful fallback

For any image where OCR is uncertain:

```text
no suggestion
→ manual entry
→ Supervisor confirms
```

No exception path should be created merely because OCR did not produce a value.

## FR-07 — Useful observability without leaking image data

Where helpful for diagnosis, log bounded metadata such as:

```text
effective preprocessing dimension
scale/variant identifier
accepted reading
disagreement
no-candidate result
```

Do not log raw image bytes.

Do not log unnecessary sensitive metadata.

---

# 8. Reference Validation Cases

Validate at minimum:

## E1 — CER full-dashboard reference class

Expected visible odometer:

```text
151517
```

Target:

```text
final OCR suggestion = 151517
```

provided the image is objectively readable by the chosen pipeline.

## E2 — CER tight odometer crop class

Expected visible odometer:

```text
151517
```

Target:

```text
final OCR suggestion = 151517
```

## E3 — Normal high-resolution phone image

Existing known-good behavior must remain green.

## E4 — Small image / duplicate-scale condition

Use an input smaller than every configured scale.

Prove that:

```text
2400 / 3200 / 1600
```

do not silently become three votes from one identical effective image.

## E5 — Speedometer false-positive case

A dashboard where the odometer is not readable but a short speed value such as:

```text
60
120
```

is visible must not become an odometer suggestion.

## E6 — Conflicting OCR passes

Example:

```text
151517
151577
151517
```

may be accepted only if the two agreeing observations are produced by genuinely distinct processing passes.

If all three effective inputs are identical, the repetition is not independent confirmation.

## E7 — No readable odometer

Expected:

```text
None
```

Manual flow remains available.

## E8 — Blur / glare / low contrast

Confirm that sharpening does not turn noise into a plausible accepted odometer.

## E9 — Trip meter + odometer

Confirm the longer valid odometer candidate still wins only under the existing deterministic rule.

## E10 — Equal-length ambiguity

Two plausible equal-length candidates must still produce:

```text
None
```

---

# 9. Automated Tests Required

Add the smallest sufficient tests to prevent regression.

At minimum cover:

### Preprocessing
- preprocessing remains decodable;
- sharpening is deterministic;
- image orientation behavior remains unchanged;
- processing does not write a temporary image to disk.

### Effective-scale semantics
- small image does not count identical effective passes as independent votes;
- normal large image still exercises the intended distinct passes;
- early exit after legitimate agreement remains correct if retained.

### Decision rules
- two genuinely distinct agreeing passes → suggestion;
- disagreement → no suggestion;
- one valid pass only → no suggestion unless Development introduces and justifies a safer equivalent rule;
- short dashboard values remain rejected;
- equal-digit ambiguity remains rejected.

### Regression fixture
Where repository/privacy constraints permit, include a safe image fixture reproducing the low-resolution mechanical-digit case and assert the expected reading.

If CI does not install Tesseract, keep deterministic Python-level tests in CI and execute the actual Tesseract fixture test in the development/pilot environment, recording the command and result in the report.

Do not make the test suite depend silently on a binary that CI does not provide.

---

# 10. Regression

Run the directly affected regression.

At minimum:

- `tests/test_odometer_ocr_reader.py`;
- productive OCR integration tests;
- odometer service/integration tests affected by OCR suggestion;
- START odometer browser path if production behavior touched shared capture flow;
- END odometer browser path if production behavior touched shared capture flow;
- typecheck/lint/build only where the chosen implementation affects those layers.

Use broader regression if shared media normalization is modified.

If the solution can remain isolated inside `ocr_tesseract.py`, prefer that over changing global image normalization behavior for every media feature.

Do not weaken, delete, skip or xfail meaningful tests to obtain closure.

---

# 11. Technical Guidance — Non-Binding

Prefer the smallest correction in this order:

```text
measure current OCR
→ improve OCR-specific preprocessing
→ make effective passes genuinely distinct
→ preserve conservative decision rules
→ add regression evidence
```

Avoid this order:

```text
lower confidence threshold
→ accept more output
→ declare success from one sample
```

The first improves evidence quality.

The second weakens the gate.

Development retains authority over:

- exact sharpening parameters;
- resampling algorithm;
- whether controlled upscaling is appropriate;
- scale set;
- internal helper structure;
- logging details;
- fixture design.

For meaningful choices record:

```text
problem
→ options considered
→ selected approach
→ reason
→ before/after evidence
→ false-positive impact
```

---

# 12. Acceptance Criteria

This correction is complete only when all applicable items are green:

1. the current failure is reproduced or otherwise characterized with raw OCR evidence;
2. the readable CER reference full-dashboard case can produce the expected `151517` suggestion;
3. the readable CER odometer-crop case can produce the expected `151517` suggestion;
4. the result is achieved without blindly lowering the confidence floor;
5. short dashboard values remain rejected;
6. ambiguous equal-length candidates remain rejected;
7. multiscale agreement cannot be satisfied merely by invoking Tesseract repeatedly on an identical effective image;
8. disagreement between genuinely distinct passes still returns no suggestion;
9. manual fallback remains functional;
10. Supervisor confirmation remains authoritative;
11. START/END business semantics remain unchanged;
12. no external OCR provider is introduced;
13. affected regression is green;
14. actual Tesseract behavior is exercised somewhere with recorded evidence;
15. no `PARTIAL`, `GAP`, `BLOCKED` or unresolved `DECISION REQUIRED` remains inside this authorized delta.

---

# 13. Development Workflow

Work from the current `dev` baseline.

Use a focused branch, for example:

```text
fix/ocr-field-image-preprocessing
```

Keep the MR scoped to this OCR hardening.

Do not mix:

- unrelated cleanup;
- broad media refactors;
- UI redesign;
- provider experimentation;
- other roadmap checkpoints.

A suitable MR subject is:

```text
OCR de campo: endurecer preprocesado y hacer real el acuerdo multiescala
```

Commits should explain the measured failure and why the chosen correction is safer than lowering the acceptance threshold.

---

# 14. Required Deliverable

Create a new incremental report:

`Report Delivery Rodrigo/CER_ROUTE_RTE10_A01_OCR_FIELD_IMAGE_HARDENING_REPORT_004.md`

Do not overwrite Reports 001–003.

Keep it evidence-driven.

Include:

1. Executive Result
2. Field Reference Case
3. Before-Fix OCR Output
4. Root Cause
5. Preprocessing Change
6. Multiscale Semantics Correction
7. Before / After Matrix
8. False-Positive Protection
9. Tests / Regression
10. START / END Impact
11. Expected → Implemented → Evidence → Gap
12. Remaining OCR Limitations
13. CER Pilot Revalidation Checklist
14. Proposed Status

For the before/after matrix include, where available:

```text
image
source dimensions
effective pass dimensions
recognized token
confidence
candidate
per-pass reading
final suggestion
```

Do not claim improvements that were not executed against Tesseract.

---

# 15. Status Rule

Development may propose:

`IMPLEMENTATION COMPLETE / READY FOR CER OCR PILOT REVALIDATION`

only if the acceptance criteria are supported by executed evidence.

Do not declare:

`RTE10-A01 CERTIFIED`

or:

`OCR PRODUCTION CERTIFIED`

Final field validation belongs to CER.

If the reference images still cannot be read reliably after bounded preprocessing work, report the exact evidence and classify the limitation honestly rather than lowering safeguards until they pass.

---

# 16. CER Revalidation Handoff

CER should only need to repeat the affected scenarios:

1. full dashboard reference image → expected suggestion `151517`;
2. tight odometer image → expected suggestion `151517`;
3. normal START capture;
4. normal END capture;
5. blurred/glare image → verify no unsafe confident suggestion;
6. unreadable odometer with speedometer visible → verify no speed value is suggested;
7. manual fallback;
8. Supervisor correction/confirmation.

Do not require CER to repeat unrelated RTE10-A01 scenarios because of this delta unless regression evidence identifies broader impact.

---

# 17. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE10_A01_OCR_FIELD_IMAGE_HARDENING_REPORT_004.md`

**STOP.**

Do not:

- replace Tesseract;
- add an external OCR provider;
- broaden RTE10-A01;
- start another roadmap checkpoint;
- redesign capture UX;
- modify unrelated product behavior.

CER will review the report and perform the targeted OCR pilot revalidation.
