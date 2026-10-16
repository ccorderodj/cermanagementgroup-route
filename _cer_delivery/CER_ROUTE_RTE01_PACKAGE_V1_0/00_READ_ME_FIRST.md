# CER Route — RTE01 Package V1.0

## Purpose

This package is the official product input for **RTE01 — Technical Baseline + Target Alignment** of CER Route.

CER Route is an independent product. It is not a CER ERP module and must not depend on CER ERP to operate.

RTE01 is an **alignment and technical assessment checkpoint**. Its purpose is to translate the approved product baseline into an end-to-end technical proposal and identify decisions, risks and dependencies before implementation proceeds.

**RTE01 does not authorize RTE02 or subsequent implementation work.**

---

## Authority hierarchy

When interpreting the project, use the following order of authority:

1. **`01_Product_Baseline/CER_ROUTE_PRODUCT_BASELINE_V0_7_UPDATED.md`** — authoritative functional baseline.
2. **`02_Checkpoint_RTE01/CER_ROUTE_RTE01_INSTRUCTIONS.md`** — executable scope for this checkpoint.
3. **`04_Mockup_Reference_V0_7/`** — approved UX/flow reference.
4. **`03_Roadmap/CER_ROUTE_MASTER_ROADMAP.md`** — visibility of the complete development path; it is not authorization to execute later checkpoints.
5. **External Geolocation Technical Experience MD** supplied separately by CER — technical experience reference only, non-binding.
6. Repository findings and the assigned developer/agent technical assessment.

If two sources appear to conflict, do not silently choose one. Use the hierarchy above and document the issue in the RTE01 report.

---

## Important mockup rule

The included mockup is **V0.7 REFINED** and remains the visual/interaction reference.

After that mockup was produced, CER approved a small set of surgical product updates. Those updates are documented in the authoritative baseline and **override the mockup only for the explicitly listed fields**.

Do not redesign the approved flows because of those deltas.

---

## Companion geolocation document

CER will provide a separate MD created from experience gained on another geolocation-based application.

Treat it as:

> **Technical Experience Reference — Context Only / Non-Binding**

Its purpose is to provide lessons learned, technologies evaluated, challenges encountered, workarounds and unresolved issues.

It must **not** be interpreted as:

- required architecture;
- required libraries;
- mandatory vendors;
- approved CER Route implementation decisions;
- product requirements.

The assigned CER Route developer and agent must evaluate what is applicable to CER Route and explain their own technical proposal.

---

## Expected output

Return one principal file:

`CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT.md`

Use the structure provided under `05_Deliverable_Expected/` as guidance.

The report must clearly distinguish:

- Confirmed requirement
- Repository / baseline finding
- Technical recommendation
- Assumption
- Risk
- Decision required from CER

Do not begin RTE02 until CER explicitly validates RTE01.
