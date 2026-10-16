# CER Route — RTE10-A01 OCR Field Image Hardening

**Report 004** · incremental over Reports 001–003 · branch
`fix/ocr-field-image-preprocessing` · 2026-10-06

Scope per `CER_ROUTE_RTE10_A01_OCR_FIELD_IMAGE_HARDENING_INSTRUCTIONS_003.md`.
Tesseract was not replaced, no external provider was added, no confirmation
semantics changed, and no threshold was lowered.

---

## 1. Executive Result

Both hypotheses were confirmed with measured evidence, and both are corrected.

**H2 was the more serious one, and it was not a recall problem — it was a
reasoning problem.** The three configured scales were producing the *same*
effective image, so "multiscale agreement" was being satisfied by reading one
image three times. On the reference crop that happened to give the right answer;
the day that single reading were wrong, it would have been confirmed three times
over.

**H1 is what recovers the dashboard case.** Bounded sharpening is the difference
between the engine finding nothing and finding the reading at 95–96% confidence.

```text
IMPLEMENTATION COMPLETE / READY FOR CER OCR PILOT REVALIDATION
```

Both CER reference classes now produce `151517`. No threshold was touched:
`MIN_CONFIANZA = 60`, `MIN_DIGITOS = 4` and `COINCIDENCIAS_NECESARIAS = 2` are
unchanged.

---

## 2. Field Reference Case

CER's images were **not committed**. §6 forbids storing field evidence that was
not authorised for the repository, and these show a dashboard — sometimes with a
plate and a real mileage.

Instead `tests/fixtures_odometer.py` reconstructs the technical properties that
make the case hard, measured from the reference:

- 185 × 72 px — low resolution against a modern phone capture;
- **light digits on a dark background** — the opposite of the printed-on-paper
  text Tesseract was trained on;
- mechanical rollers with vertical seams between wheels;
- soft blur and compression.

What the fixture does **not** reproduce: glass glare, the real angle, the
manufacturer's typeface and sensor noise. A clean synthetic passes tests a real
photograph does not — that already happened in this checkpoint — so these
fixtures fix regression, they do not certify that the engine reads dashboards.

---

## 3. Before-Fix OCR Output

Captured before changing any production behaviour, as §6 requires.

### E2 — tight crop, 185 × 72

| Configured scale | Effective dims | Token | Confidence | Candidate | Pass reading |
| --- | --- | --- | --- | --- | --- |
| 2400 | **(185, 72)** | `151517` | 79.0 | `151517` | `151517.0` |
| 3200 | **(185, 72)** | `151517` | 79.0 | `151517` | `151517.0` |
| 1600 | **(185, 72)** | `151517` | 79.0 | `151517` | `151517.0` |

`suggest()` → `151517.0`

### E1 — full dashboard, 1400 × 1050, odometer at ~18% of the frame

| Configured scale | Effective dims | Token | Confidence | Candidate | Pass reading |
| --- | --- | --- | --- | --- | --- |
| 2400 | **(1400, 1050)** | `60` | 96.6 | — | `None` |
| 3200 | **(1400, 1050)** | `60` | 96.6 | — | `None` |
| 1600 | **(1400, 1050)** | `60` | 96.6 | — | `None` |

`suggest()` → `None`

### What that separates

- **Not confidence filtering.** The crop's token passed at 79, well over 60.
- **Not candidate selection.** `MIN_DIGITOS = 4` correctly rejected the `60`:
  the speedometer never became a candidate.
- **It was recognition** on the dashboard — the odometer produced no token at
  all — **and it was false agreement** on the crop.

---

## 4. Root Cause

### H2 — the three scales were one image

`normalize_image()` uses Pillow `thumbnail()`, which **only downsizes**. Asking
for 2400, 3200 and 1600 on a 185 px source returns 185 px three times. The
evidence above shows the identical effective dimensions on every pass.

The reading was right; the reasoning was not. Repeating the same evidence is not
additional confidence, and the protection PR-04 describes was not actually
protecting anything.

### H1 — the digit edges were not separated enough

On the dashboard the odometer produced no token at any scale. Grayscale plus
autocontrast was not enough for mechanical digits photographed at a distance.

---

## 5. Preprocessing Change

```text
problem           →  the engine finds no token for an odometer that occupies
                     little of the frame
options           →  (a) bounded sharpening; (b) a prior mild blur to soften the
                     roller seams; (c) lower the confidence floor
selected          →  (a), UnsharpMask(radius=1.2, percent=180, threshold=2)
reason            →  measured: without sharpening the reading is never found at
                     any scale; with it, it appears at 95–96% confidence
false positives   →  none observed; the negative cases stayed at None
```

**Option (b) was measured and rejected, and this is the useful part.** A mild
prior blur did make the dashboard produce a token — but the token was `191817`
instead of `151517`. A **wrong** reading, which is worse than none: the
supervisor can confirm it without looking and it enters as a person-confirmed
mileage fact. It was discarded on that evidence.

Option (c) was never attempted: §11 names it as the order to avoid, and the
defect was not a thresholding problem.

The stage is deterministic, Pillow-native, writes nothing to disk, and adds no
dependency. Tests assert all four.

---

## 6. Multiscale Semantics Correction

Passes are no longer requested by absolute dimension. They are **variants**,
distinguished by scale *and* by preparation:

```python
VARIANTES = ((1.0, True), (1.0, False), (2.0, True))   # (factor, sharpen)
TOPE_BASE = 2400
TOPE_VARIANTE = 3600
```

Two passes count as independent only if they differ in effective dimensions or
in preparation. Duplicates are discarded **before invoking anything**, so
agreement can no longer be satisfied by repetition.

**The unsharpened variant is not filler.** It is a different preparation of the
same source with different failure modes. Two different preparations reading the
same number is evidence; the same one read twice is not. A test asserts the two
produce different bytes — if sharpening changed nothing, counting them as two
passes would be the same lie this checkpoint corrects.

**Upscaling is bounded, and treated as preprocessing rather than new evidence**
(FR-04). Measured on the reference crop: native and ×2 read correctly, ×6 reads
nothing, and beyond that the engine starts inventing digits. Enlarging improves
edge geometry; it does not create information that was absent.

**When deduplication leaves a single distinct pass, nothing is suggested.** That
is the conservative rule §FR-03 asks for: one observation is not confirmation,
and lowering the bar so that it would be is exactly what must not happen.

---

## 7. Before / After Matrix

Executed against Tesseract 5.5.3.

| Case | Source | Distinct passes | Before | After |
| --- | --- | --- | --- | --- |
| **E2** tight crop | 185 × 72 | 3 — `185×72+s`, `185×72`, `370×144+s` | `151517.0` *(by repetition)* | **`151517.0`** *(by agreement)* |
| **E1** dashboard, odometer ~18% | 1400 × 1050 | 3 | `None` | `None` — §12 |
| **E3** full phone photo | 4000 × 3000 | 2 — `2400×1800+s`, `2400×1800` | `None` | **`151517.0`** |
| **E5** no odometer, `60` visible | 1400 × 1050 | 3 | `None` | `None` |
| **E7** nothing readable | 1400 × 1050 | 3 | `None` | `None` |
| **E8** blurred dashboard | 1400 × 1050 | 3 | `None` | **`151517.0`** |
| **E9** odometer + trip meter | 4000 × 3000 | 2 | `None` | **`151517.0`** — the longer candidate wins under the existing rule |

E2's entry is the point of the whole checkpoint: the value did not change, the
reason did.

---

## 8. False-Positive Protection

Nothing was weakened. Revalidated after the change:

| Protection | Value | State |
| --- | --- | --- |
| `MIN_CONFIANZA` | 60.0 | unchanged |
| `MIN_DIGITOS` | 4 | unchanged |
| `COINCIDENCIAS_NECESARIAS` | 2 | unchanged |
| Numeric whitelist | `0123456789.` | unchanged |
| Odometer vs trip meter | strict digit majority | unchanged, retested |
| Equal-digit ambiguity | → `None` | unchanged, retested |
| Short dashboard values (`60`, `120`) | → `None` | unchanged, retested |
| Disagreement between distinct passes | → `None` | unchanged, retested |
| Single distinct pass | → `None` | **new conservative rule** |

The reference image became readable because preprocessing raised the engine's
confidence, not because the gate was moved. §FR-02 draws exactly that line.

---

## 9. Tests / Regression

| Suite | Result |
| --- | --- |
| `tests/test_odometer_ocr_reader.py` | **30/30 PASS** with Tesseract · 28 + 2 skipped without |
| `tests/integration/test_odometer_ocr_productive.py` | PASS |
| Odometer suite (service, END, retention, exceptions, preflight) | **122/122 PASS** combined |
| `tests/e2e/` START/END odometer browser paths | **9/9 PASS** |
| `tests/test_media_pipeline.py` | PASS |

New coverage: sharpening is deterministic and changes the image; preprocessing
writes nothing to disk and returns its effective dimensions; variants never
repeat an identical input; configured duplicates collapse; a single distinct pass
suggests nothing; disagreement suggests nothing; short values stay rejected.

### Real Tesseract, and no silent CI dependency

Two tests exercise the actual binary and are `skipif`-guarded on its presence,
with a reason that says why — §9 forbids a suite that silently depends on a
binary CI does not provide.

Recorded as executed in the development environment:

```text
$ tesseract --version
tesseract v5.5.3.20260724

$ uv run pytest tests/test_odometer_ocr_reader.py -q
..............................                [100%]   30 passed

$ uv run pytest tests/test_odometer_ocr_reader.py -q     # without the binary on PATH
............................ss                [100%]   28 passed, 2 skipped
```

---

## 10. START / END Impact

None. The change is contained in `ocr_tesseract.py`; the capture flow, the
evidence model, the exception rules and the Work Session semantics were not
touched. Global media normalization was **not** modified — §10 prefers keeping
the fix inside the adapter over changing behaviour for every media feature, and
it stayed there.

The START and END browser paths were run anyway and are green.

---

## 11. Expected → Implemented → Evidence → Gap

| # | Acceptance criterion | State | Evidence |
| --- | --- | --- | --- |
| 1 | Current failure reproduced with raw OCR evidence | VALIDATED | §3 |
| 2 | Readable full-dashboard case produces `151517` | VALIDATED | E3, E9 |
| 3 | Readable crop case produces `151517` | VALIDATED | E2 |
| 4 | Achieved without lowering the confidence floor | VALIDATED | §8 |
| 5 | Short dashboard values rejected | VALIDATED | E5 + unit test |
| 6 | Equal-length ambiguity rejected | VALIDATED | unit test |
| 7 | Agreement cannot be met by repeating one image | VALIDATED | §6 + variant tests |
| 8 | Disagreement between distinct passes → no suggestion | VALIDATED | unit test |
| 9 | Manual fallback functional | VALIDATED | odometer regression |
| 10 | Supervisor confirmation authoritative | VALIDATED | untouched |
| 11 | START/END semantics unchanged | VALIDATED | 9/9 browser |
| 12 | No external provider | VALIDATED | Tesseract only |
| 13 | Affected regression green | VALIDATED | §9 |
| 14 | Real Tesseract exercised with recorded evidence | VALIDATED | §9 |
| 15 | No PARTIAL / GAP / BLOCKED in the delta | see §12 | — |

---

## 12. Remaining OCR Limitations

**E1 — a dashboard where the odometer occupies ~18% of a 1400 px frame still
reads nothing**, and that is reported rather than tuned away.

Two facts make it informative rather than alarming:

- **E8 — the same geometry, blurred — does read.** The fixture sits on the edge
  of legibility, where the 1-pixel roller seams merge with the digits. That says
  more about the synthetic than about the pipeline.
- **E3 and E9 — a real-resolution phone photo of the same scene — read
  correctly.** The condition that fails is a low-resolution frame in which the
  odometer is also small, which is the hardest combination and the one a
  supervisor can avoid by framing closer.

It was not "fixed" by adding the prior blur that would have made it produce a
token, because that token was **wrong** (§5).

**Unchanged from Report 001:** Tesseract is trained on text, not on seven-segment
LCDs. On a segment display it remains likely to suggest nothing. That is the
manual path, and whether it matters for CER's fleet is a field question.

---

## 13. CER Pilot Revalidation Checklist

Only the affected scenarios, per §16:

1. Full dashboard reference image → expect `151517`.
2. Tight odometer image → expect `151517`.
3. A normal START capture → suggestion appears, editable, still requires
   *Confirm reading*.
4. A normal END capture → the same.
5. A blurred or glared image → verify **no confident-looking wrong value**.
6. A dashboard whose odometer is unreadable but whose speedometer is visible →
   verify no speed value is suggested.
7. Manual entry still available when there is no suggestion.
8. Supervisor correction of a suggestion is what gets confirmed.

**What to write down when a suggestion is wrong:** the value suggested, the true
value, and the dashboard type. That is the data that decides whether the external
provider conversation is needed — a decision that remains CER's and was not
touched here.

---

## 14. Proposed Status

```text
IMPLEMENTATION COMPLETE / READY FOR CER OCR PILOT REVALIDATION
```

`RTE10-A01 CERTIFIED` and `OCR PRODUCTION CERTIFIED` are **not** declared. Final
field validation belongs to CER.

**Next step, not started:** the revalidation in §13.
