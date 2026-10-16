# CER Route — RTE10-A01 OCR Pilot Deployment
## Deployment & Pilot Validation Instructions
### Revision 001

## Context
RTE10-A01 is ready to be exercised in the CER Route pilot/test environment currently used by field users.

This is **not a general production release**. The purpose is to activate productive OCR in the pilot environment so CER can validate it with real devices and vehicles.

The deployment requires:
- `tesseract-ocr`
- `tesseract-ocr-eng`

Without those packages, the system must continue with the existing manual-reading flow.

## Objective
Deploy the RTE10-A01 candidate to the CER Route pilot/test environment, confirm that productive OCR is actually active, run a minimal technical smoke test, and hand the environment back to CER for field validation.

Target status:

`RTE10-A01 DEPLOYED TO PILOT / OCR ACTIVE / READY FOR CER FIELD VALIDATION`

## Scope

### 1. Pre-deployment gate
Before deployment:
- ensure the approved RTE10-A01 implementation is the candidate being deployed;
- align the previously identified stale browser test with current product behavior;
- do not modify product behavior merely to restore the old transient `Ending your day` expectation;
- run the directly affected regression and leave it green.

### 2. Deploy to pilot/test only
Deploy to the current CER Route pilot/test environment used by field users.

Do **not** promote this change to general production as part of this task.

### 3. Install OCR dependencies
Ensure the pilot deployment includes:
- `tesseract-ocr`
- `tesseract-ocr-eng`

Use the project's supported deployment mechanism (`Aptfile`, `Dockerfile`, or the environment's normal build process).

Do not perform a temporary manual install that disappears on the next deployment.

### 4. Verify OCR activation
After deployment, verify:
- Tesseract is present and executable;
- the application selects the productive OCR reader rather than `NoSuggestionReader`;
- `ODOMETER_OCR_ENABLED` is enabled for the pilot;
- the flag can still disable OCR without code changes;
- the application starts normally.

### 5. Minimal smoke test

#### START
- capture an odometer photo;
- confirm OCR attempts to produce a suggestion;
- if a suggestion appears, it remains editable and requires explicit Supervisor confirmation;
- if no suggestion appears, manual entry remains available.

#### END
Repeat the same behavior for END odometer.

#### OCR failure/no-result
Confirm:
- OCR failure/no-result does not block the Supervisor;
- manual entry remains available;
- no odometer exception is created automatically merely because OCR produced no suggestion.

#### Photo durability
Confirm:
- the captured photo is durably staged before upload;
- temporary connectivity loss does not force an immediate Retake;
- recovery resumes correctly when connectivity returns.

## Rollback / Safety
Do not remove the manual-reading path.

If productive OCR behaves incorrectly in pilot:
1. disable OCR using `ODOMETER_OCR_ENABLED`;
2. preserve the photo + manual confirmed-reading flow;
3. report evidence of the issue;
4. do not hot-fix unrelated functionality during this task.

## Out of Scope
Do not:
- promote to general production release;
- change Work Session, Trip or Activity behavior;
- alter odometer exception rules;
- change RBAC;
- modify geolocation or hierarchy;
- add an external OCR provider;
- redesign the capture UI;
- start another checkpoint;
- optimize unrelated frontend/admin areas.

## Evidence Required
Report:
1. pilot environment deployed;
2. deployed commit / MR;
3. `tesseract-ocr` installed;
4. `tesseract-ocr-eng` installed;
5. OCR provider selected at runtime;
6. `ODOMETER_OCR_ENABLED` status;
7. START smoke result;
8. END smoke result;
9. OCR failure/no-result fallback result;
10. photo durability/recovery result;
11. warnings or limitations.

If the pilot environment cannot install or expose the OCR binary, classify:

`BLOCKED — PILOT ENVIRONMENT OCR DEPENDENCY`

and report the exact dependency. Do not silently fall back and declare OCR ready.

## Deliverable
Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE10_A01_OCR_PILOT_DEPLOYMENT_REPORT_002.md`

Include:
- Deployment Result
- Environment
- Build / Dependency Installation
- OCR Runtime Verification
- START Smoke Test
- END Smoke Test
- Failure / Manual Fallback
- Photo Durability
- Rollback Verification
- Issues / Blockers
- Final Status

## Status Rule
Only report:

`RTE10-A01 DEPLOYED TO PILOT / OCR ACTIVE / READY FOR CER FIELD VALIDATION`

if:
- the OCR binary is actually available in pilot;
- the productive reader is actually selected;
- START and END smoke tests are green;
- manual fallback remains functional;
- no blocker remains.

Do not declare `RTE10-A01 CLOSED`. Final field certification belongs to CER.

## STOP
After deployment, smoke validation and the deployment report:

**STOP.**

Do not start another checkpoint and do not promote to general production without CER authorization.
