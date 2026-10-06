# CER Route — RTE10-A01 OCR Consensus Correction
## Product Owner Instructions for Development Agent
### Revision 004

**Purpose:** correct the remaining OCR no-suggestion defect observed after MR !54 on the CER reference odometer images, without weakening the conservative false-positive protections already established in RTE10-A01.

**Mode:** targeted consensus-strategy correction + real-image reproduction + regression evidence.

**Reference branch:** `dev`

**Previous implementation:** MR !54 — `OCR de campo: endurecer preprocesado y hacer real el acuerdo multiescala`

**Do not replace Tesseract in this checkpoint.**  
**Do not lower confidence thresholds merely to make the reference images pass.**  
**Do not reduce the required agreement to one observation.**  
**Do not change Supervisor confirmation semantics.**

---

# 1. Context

MR !54 correctly fixed two real defects:

1. the preprocessing now includes bounded sharpening;
2. the previous absolute-scale loop no longer counts the same effective image three times as independent evidence.

Those changes remain valid.

However, CER revalidated the productive API after the merge and the OCR still returned no suggestion.

Observed API result:

```json
{
  "evidence": {
    "id": 97,
    "work_session_id": 315,
    "vehicle_id": 15,
    "evidence_type": "end",
    "status": "pending",
    "evidence_method": null,
    "confirmed_reading": null,
    "ocr_detected_reading": null,
    "captured_at": "2026-10-06T04:08:04.599186Z",
    "confirmed_at": null,
    "confirmed_by": null,
    "scan_status": "not_configured",
    "version": 13
  },
  "ocr_suggestion": null
}
```

Endpoint:

```text
POST /api/odometer/sessions/315/end/photo
```

The request completed successfully with HTTP 200.

Therefore:

```text
photo upload succeeded
→ evidence row was updated
→ OCR path returned no accepted suggestion
```

This is not a photo-upload failure.

It is a decision/consensus failure inside the OCR path.

---

# 2. New Measured Finding

The important new result is:

> Tesseract now reads the correct value `151517` from the CER reference images, but the current variant set does not produce enough matching accepted observations for `suggest()` to return it.

The problem after MR !54 is no longer primarily:

```text
Tesseract cannot read the odometer
```

It is now:

```text
Tesseract can read the odometer
→ one variant gets the correct value
→ the other configured variants do not agree
→ COINCIDENCIAS_NECESARIAS = 2 is not reached
→ suggestion = None
```

The safety rule remains correct.

The variant strategy is what must be corrected.

---

# 3. Reference Evidence

The visible odometer value in both CER reference images is:

```text
151517
```

## E1 — Full dashboard image

Source dimensions:

```text
524 × 381
```

Measured current MR !54 behavior:

| Variant | Tesseract output | Confidence | Accepted by filter |
| --- | ---: | ---: | --- |
| native + sharpening | `151517` | ~81.13 | YES |
| native without sharpening | `1561517` | ~56.44 | NO (`< 60`) |
| ×2 + sharpening | `454517` | ~79.03 | YES, but wrong |

Effective accepted observations:

```text
151517
454517
```

They disagree.

Final result:

```text
None
```

This matches the API behavior.

## E2 — Tight odometer crop

Source dimensions:

```text
185 × 72
```

Measured current MR !54 behavior:

| Variant | Tesseract output | Confidence | Accepted by filter |
| --- | ---: | ---: | --- |
| native + sharpening | `151517` | ~73.56 | YES |
| native without sharpening | `151517` | ~14.26 | NO (`< 60`) |
| ×2 + sharpening | `161517` | ~51.56 | NO (`< 60`) |

Effective accepted observations:

```text
151517
```

Only one accepted observation exists.

Final result:

```text
None
```

Again, this is consistent with the productive API returning:

```json
"ocr_suggestion": null
```

---

# 4. Root Cause

The remaining defect is the composition of the current variant set:

```python
VARIANTES = (
    (1.0, True),
    (1.0, False),
    (2.0, True),
)
```

The native sharpened path is the strongest path for these images.

The other two variants do not provide useful independent confirmation:

- `1.0 / no sharpening` is often too weak to pass the confidence threshold;
- `2.0 / sharpening` is unstable and can alter the digit interpretation.

Measured examples:

```text
full dashboard:
native sharpened → 151517
2x sharpened     → 454517

tight crop:
native sharpened → 151517
2x sharpened     → 161517
```

This means that ×2 enlargement is not acting as a reliable confirmation channel for this reference image class.

The result is conservative but operationally unhelpful:

```text
correct reading exists
→ consensus strategy cannot confirm it
→ no suggestion
```

---

# 5. Important Constraint

Do **not** solve this by changing:

```python
MIN_CONFIANZA = 60.0
COINCIDENCIAS_NECESARIAS = 2
MIN_DIGITOS = 4
```

Those controls are doing useful work.

Examples:

- `1561517 @ 56.44` is correctly rejected by the current confidence floor;
- short dashboard values such as `60` remain correctly rejected;
- one observation alone is still not enough evidence to present a confident suggestion.

The objective is:

> improve the quality and stability of the evidence entering the consensus rule, not weaken the rule.

---

# 6. Objective

Replace the unstable current variant set with a measured preprocessing ensemble that can produce repeatable agreement for readable mechanical odometer digits while preserving the existing false-positive protections.

Target behavior for the CER reference images:

```text
reference image
→ several materially different bounded preprocessing variants
→ at least two accepted variants read 151517
→ suggestion = 151517
→ Supervisor still confirms/corrects
```

If the variants disagree:

```text
no consensus
→ no suggestion
→ manual entry remains available
```

---

# 7. Technical Direction — Non-Binding

The first implementation direction to evaluate is:

```text
native-size image
→ grayscale/autocontrast
→ several bounded sharpening configurations
→ Tesseract on each
→ require 2 matching accepted readings
```

Instead of relying on:

```text
native sharpened
native unsharpened
2x sharpened
```

evaluate a small native-resolution sharpening ensemble.

Measured experiments on the CER reference images indicate that moderate native-resolution sharpening is substantially more stable than enlargement.

Examples observed during reproduction:

## Full dashboard

```text
radius=1.0 / percent=180 → 151517
radius=1.2 / percent=180 → 151517
radius=1.5 / percent=180 → 151517
```

## Tight crop

```text
radius=1.0 / percent=180 → 151517
radius=1.2 / percent=180 → 151517
radius=1.5 / percent=180 → 151517
```

These values are **starting evidence, not mandated production constants**.

Development must determine whether these or nearby bounded values provide the best positive/negative behavior.

A possible representation is:

```python
PREPROCESSING_VARIANTS = (
    SharpenVariant(radius=1.0, percent=180, threshold=2),
    SharpenVariant(radius=1.2, percent=180, threshold=2),
    SharpenVariant(radius=1.5, percent=180, threshold=2),
)
```

Development owns the final internal structure.

---

# 8. What Counts as a Distinct Variant

Different variants may use the same source dimensions if their preprocessing is materially different and deterministic.

However, do not treat arbitrary tiny parameter changes as automatically meaningful independent evidence.

Development must demonstrate that the chosen variants:

- produce materially different processed pixel data;
- have measurably different OCR failure modes;
- do not merely repeat the same transformation under a different name;
- improve correct agreement without increasing unsafe agreement on negatives.

The previous rule remains:

> repeating the same effective evidence is not confidence.

---

# 9. Upscaling Rule

The current ×2 path must be explicitly re-evaluated.

Do not keep it merely because it was introduced in MR !54.

The measured reference behavior shows that enlargement can alter digit interpretation:

```text
151517 → 454517
151517 → 161517
```

Therefore:

- remove ×2 from the consensus set if the broader evidence shows it is harmful;
- or retain it only if Development demonstrates a clear positive role across a representative matrix.

Upscaling remains an OCR preprocessing option, not a required architecture rule.

Do not treat enlargement as additional source evidence.

---

# 10. Functional Requirements

## FR-01 — Correct reference-image consensus

For both CER reference image classes, a readable image should produce:

```text
151517
```

as the OCR suggestion.

The final suggestion must come from the existing agreement rule, not from special-casing the known value.

## FR-02 — Keep two-observation agreement

Keep:

```python
COINCIDENCIAS_NECESARIAS = 2
```

unless a separate CER-authorized checkpoint explicitly changes the trust model.

One accepted OCR result must not automatically become a suggestion.

## FR-03 — Keep the confidence floor

Keep:

```python
MIN_CONFIANZA = 60.0
```

unless executed positive/negative evidence demonstrates a safer alternative.

This correction should succeed because preprocessing becomes more stable, not because weaker output is admitted.

## FR-04 — Keep short-number protection

Continue rejecting dashboard numbers such as:

```text
60
120
```

as odometer readings.

Keep:

```python
MIN_DIGITOS = 4
```

unless existing business rules change separately.

## FR-05 — Preserve ambiguity behavior

If two plausible equal-length candidates remain unresolved:

```text
None
```

Do not invent a new tie-breaker in this checkpoint.

## FR-06 — Preserve disagreement behavior

If accepted preprocessing variants produce conflicting readings and no value reaches the required agreement:

```text
None
```

Do not select the “most confident” conflicting value merely to produce a result.

## FR-07 — Preserve manual fallback

A no-suggestion result must remain:

```text
photo valid
→ manual reading available
→ Supervisor confirms
```

OCR failure must not create an exception automatically.

## FR-08 — No hard-coded reference reading

Do not special-case:

```text
151517
```

or any known vehicle/session.

The correction must generalize to the image class.

---

# 11. Required Diagnostic Logging

The productive issue currently collapses to:

```json
"ocr_suggestion": null
```

which is safe but insufficient for field diagnosis.

Add bounded diagnostic logging sufficient to explain why consensus failed.

At debug/info level as appropriate, record per OCR attempt:

```text
variant identifier
effective dimensions
raw accepted OCR reading or None
agreement state
final decision
```

Example:

```text
ODOMETER OCR | variant sharp-r1.0 524x381 -> 151517.0
ODOMETER OCR | variant sharp-r1.2 524x381 -> 151517.0
ODOMETER OCR | agreement 2/2 -> 151517.0
```

or:

```text
ODOMETER OCR | variant A -> 151517.0
ODOMETER OCR | variant B -> 454517.0
ODOMETER OCR | no consensus -> no suggestion
```

Do not log:

- image bytes;
- full file content;
- unnecessary user/vehicle information;
- secrets.

---

# 12. Reference Validation Matrix

Validate at minimum:

## E1 — CER full dashboard

Expected:

```text
151517
```

Current MR !54 result:

```text
None
```

Target after correction:

```text
151517
```

## E2 — CER tight crop

Expected:

```text
151517
```

Current MR !54 result:

```text
None
```

Target:

```text
151517
```

## E3 — Existing high-resolution known-good case

Must remain green.

## E4 — Odometer not readable, speedometer visible

Example:

```text
60
```

Expected:

```text
None
```

## E5 — No readable numeric odometer

Expected:

```text
None
```

## E6 — Odometer + trip meter

Expected:

- existing digit-count selection rule remains in force;
- correct odometer can be suggested when consensus exists.

## E7 — Equal-length ambiguity

Expected:

```text
None
```

## E8 — Glare / blur / compression

Confirm that the new sharpening ensemble does not create stable but incorrect agreement.

## E9 — Deliberately conflicting preprocessing outputs

If variants produce:

```text
151517
151577
151577
```

the system may return `151577` only if those are genuinely distinct, accepted variants and the test image truth supports that result.

For a controlled negative fixture whose truth is `151517`, such a result is a failure.

The consensus mechanism is not correct merely because two values agree.

## E10 — One accepted observation only

Expected:

```text
None
```

---

# 13. Real-Image Validation Requirement

The exact CER reference images must be used during development/pilot validation if available to the Development agent.

Do not rely exclusively on the synthetic fixture introduced in MR !54.

The synthetic fixture remains useful for deterministic regression, but it does not reproduce:

- real dashboard glass;
- real manufacturer typeface;
- reflections;
- sensor noise;
- exact compression;
- exact focus;
- surrounding dashboard geometry.

The previous checkpoint itself documented this limitation.

Therefore closure requires two layers:

```text
synthetic deterministic fixture
+
actual CER reference-image execution
```

The raw CER images do not need to be committed to the repository.

If privacy/repository policy prevents committing them:

- execute them locally or in the pilot;
- record dimensions, variant outputs, confidence and final result in the report;
- keep only a non-sensitive regression fixture in Git.

---

# 14. Automated Tests Required

Add the smallest sufficient regression coverage.

At minimum:

### Consensus
- two distinct native preprocessing variants agreeing → suggestion;
- one accepted variant only → `None`;
- conflicting accepted variants without majority → `None`;
- three variants where two agree → agreed value;
- variant order does not change the final result.

### Preprocessing variants
- variants are deterministic;
- variants produce materially different processed bytes where they are intended to be distinct;
- duplicate configuration is deduplicated;
- no temporary files are written.

### Safety
- `60` rejected;
- `120` rejected;
- equal-length ambiguity rejected;
- no readable odometer → `None`;
- wrong stable consensus fixture must fail the test rather than be accepted as “successful OCR”.

### Tesseract integration
Where Tesseract is available:

- reference-class crop reads expected value;
- full-dashboard reference class reads expected value if represented by a safe fixture;
- false-positive fixture remains `None`.

If Tesseract is not present in CI, continue to make those tests explicit `skipif` cases and record real-binary execution separately.

---

# 15. Regression Required

Run at minimum:

```text
tests/test_odometer_ocr_reader.py
tests/integration/test_odometer_ocr_productive.py
affected odometer service/integration tests
START odometer browser path
END odometer browser path
```

If the change remains isolated to `ocr_tesseract.py`, do not expand into unrelated media behavior.

Run broader regression only if shared infrastructure is changed.

Do not weaken, remove, skip or xfail meaningful tests to obtain closure.

---

# 16. Acceptance Criteria

This correction is complete only when all applicable criteria are supported by executed evidence:

1. the productive `ocr_suggestion: null` behavior is reproduced or explained by per-variant evidence;
2. the exact/full CER reference image produces `151517`;
3. the exact/tight CER reference image produces `151517`;
4. at least two materially distinct accepted preprocessing variants agree on the accepted suggestion;
5. `MIN_CONFIANZA` remains 60 unless separately justified with positive/negative evidence;
6. `MIN_DIGITOS` remains 4;
7. `COINCIDENCIAS_NECESARIAS` remains 2;
8. ×2 enlargement is removed or retained based on measured evidence, not inertia;
9. short dashboard values remain rejected;
10. equal-length ambiguity remains rejected;
11. no-readable-odometer cases remain `None`;
12. the solution does not special-case `151517`;
13. manual fallback remains functional;
14. Supervisor confirmation remains authoritative;
15. no external OCR provider is added;
16. START/END semantics remain unchanged;
17. actual Tesseract is exercised and recorded;
18. affected regression is green;
19. no `PARTIAL`, `GAP`, `BLOCKED` or unresolved `DECISION REQUIRED` remains inside this authorized delta.

---

# 17. Development Workflow

Work from the current `dev` baseline containing MR !54.

Create a focused branch, for example:

```text
fix/ocr-native-consensus-variants
```

Suggested MR subject:

```text
OCR de campo: estabilizar el consenso sin ampliar la imagen
```

Keep the MR limited to:

- OCR preprocessing variant strategy;
- consensus diagnostics;
- OCR regression fixtures/tests;
- incremental report.

Do not mix unrelated product changes.

Commit messages should explain:

```text
current API symptom
→ per-variant measured output
→ why the old consensus cannot succeed
→ why the selected ensemble is safer
→ positive and negative evidence
```

---

# 18. Required Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE10_A01_OCR_CONSENSUS_CORRECTION_REPORT_005.md`

Do not overwrite Report 004.

Include:

1. Executive Result
2. Productive API Symptom
3. Exact CER Reference Images
4. MR !54 Per-Variant Reproduction
5. Root Cause
6. Variant Strategies Evaluated
7. Selected Consensus Ensemble
8. ×2 Upscaling Decision
9. Before / After Matrix
10. False-Positive Matrix
11. Diagnostic Logging
12. Tests / Regression
13. START / END Impact
14. Expected → Implemented → Evidence → Gap
15. Remaining OCR Limitations
16. CER Pilot Revalidation Checklist
17. Proposed Status

For each actual reference image, include:

```text
source dimensions
variant configuration
effective dimensions
raw token
confidence
accepted/rejected
per-variant reading
final consensus
```

Do not report only the final `151517`.

The evidence must show why it was accepted.

---

# 19. Status Rule

Development may propose:

```text
IMPLEMENTATION COMPLETE / READY FOR CER OCR PILOT REVALIDATION
```

only if the exact CER reference cases are successfully exercised and the negative matrix remains safe.

Do not declare:

```text
RTE10-A01 CERTIFIED
OCR PRODUCTION CERTIFIED
```

Final field certification belongs to CER.

If no bounded preprocessing ensemble can reliably read the reference images without increasing false positives, report that honestly.

Do not reduce safeguards until the samples pass.

---

# 20. CER Revalidation Handoff

CER should only need to repeat:

1. exact full-dashboard image → expect `151517`;
2. exact tight odometer image → expect `151517`;
3. normal START capture;
4. normal END capture;
5. unreadable odometer with visible speedometer → expect no suggestion;
6. glare/blur case → verify no confident wrong value;
7. manual fallback;
8. Supervisor correction/confirmation.

For any wrong suggestion, record:

```text
true reading
suggested reading
dashboard type
image dimensions
```

That evidence determines whether further Tesseract hardening remains justified or whether CER should reopen the external-provider decision.

---

# 21. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE10_A01_OCR_CONSENSUS_CORRECTION_REPORT_005.md`

**STOP.**

Do not:

- replace Tesseract;
- lower safeguards to force success;
- add an external OCR provider;
- redesign the capture UI;
- change odometer business rules;
- start another roadmap checkpoint;
- perform unrelated refactors.

CER will review the evidence and perform targeted pilot revalidation.
