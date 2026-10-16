# RTE-MAIL-UNIFIED-01 - Corrective UI Review and Strategic Reports (V1.2)

**To:** CER Route developer and coding agent  
**Authority:** Product Owner corrective instruction, 2026-10-16  
**Baseline:** `RTE-MAIL-UNIFIED-01_TEST_SEND_AND_STRATEGIC_REPORTS_V1_1.md` and `RTE-MAIL-UNIFIED-01_CP1_REPORT.md`  
**Purpose:** Reconcile what is actually deployed, restore the requested provider-test UX safely, and deliver the already-scoped Strategic Activity Reports in the existing Activity Emails interface. This document supersedes only conflicting CP1 test-recipient UX requirements; all other V1.1 requirements remain in force.

## 1. Current state: distinguish gaps from defects

Evidence: the attached screenshots show (a) CER Route Configuration > Activity Emails > Templates with only `Midday Motivation` and `End of Day Recognition`, and (b) Platform > Outbound email > Verify with `Verified` status and a single preselected test mailbox.

The CP1 report says CP2/CP3 had **NOT STARTED**. Therefore missing strategic templates are **NOT IMPLEMENTED / PENDING CP2**, not proof that a completed feature broke. CP1 intentionally replaced a free-address provider test with a server allowlist. This conflicts with the PO's now-confirmed requirement to enter a destination manually for **platform-provider testing**, but the security controls added in CP1 must be retained. `Verified` checks authentication; it does **not** confirm actual inbox delivery.

Before editing, inspect actual `dev`/feature branches, current migrations, current DigitalOcean build/version (where accessible), the provider guide and Activity Emails pages. Deliver a short Expected > Implemented > Evidence > Gap matrix. Do not guess that a change is deployed simply because it exists locally.

## 2. Objective A - Restore editable recipient in the provider test (T0)

In the **existing** Platform > Integrations & Settings > Outbound email > Verify step, keep `Verify` (connection-only) separate from `Send Test Email` (real outbound attempt). Replace the radio-only recipient restriction for **platform administrators** with a clearly labeled editable email field. Prefill it with the current admin address if available, and optionally offer configured test addresses as suggestions; the field must allow a platform admin to type a different syntactically valid email address instead of requiring a deployment change to `MAIL_TEST_RECIPIENTS`.

- This exception applies to **T0, provider integration testing by platform administrators only**. Do not silently grant arbitrary-recipient sending to tenant/Route admins using T1-T4. Preserve the existing server-approved destination policy for template tests unless the PO separately approves widening that permission.
- Validate the destination server-side (format, length, no header injection), reject `cc`/`bcc` and unexpected fields (`422`), require platform-admin authorization (`403` when unauthorized), and require explicit user action to send.
- Reuse the shared CP1 quota and durable reservation: **5 total test sends per actor per 15 minutes**, counting provider and template tests together, enforcing concurrency and cross-replica correctness. Return `429` when exhausted. Do not create a bypass endpoint or another independent quota.
- Preserve `[TEST]` exactly once in the subject, a visible fake-data/test banner, and `X-CER-Route-Test`. The T0 message must be generic, with no real Activity, employee, client or operational data.
- Preserve structured audit of actor, actual destination, time, provider/backend, outcome and rate-limit/security decisions; **never** log credentials, message body, real notes or raw provider exceptions.
- T0 must exercise the **selected provider**, not an implicit fallback. Distinguish `accepted_by_provider`, `not_configured`, `failed_auth`, `failed_unreachable`, and non-sending console/memory outcomes. Never label provider acceptance as delivered; actual receipt is verified manually.
- Keep secrets in the current encrypted Platform Settings/environment mechanism. Never ask the PO to send keys in chat or commit secrets.
- If existing API currently rejects non-allowlisted T0 addresses, change the **same endpoint's** validated contract and related frontend; do not create a duplicate test endpoint. Update and version the API contract and regression tests.

**T0 acceptance examples:** a platform admin can enter an external syntactically valid test mailbox and click Send Test Email; unsupported input fails safely; a tenant admin cannot do so; five test attempts exhaust the shared budget; the shown backend and outcome are truthful. An arbitrary entered address is allowed only under this explicit platform-admin test flow and protections.

## 3. Objective B - Add the two missing strategic templates (CP2)

Extend **CER Route Configuration > Activity Emails**, preserving the existing baseline and navigation. Organize the Templates area into two clearly labeled groups, without creating a new standalone Mail module:

1. **Motivational Emails (existing):** `MIDDAY_MOTIVATION` and `END_OF_DAY_RECOGNITION`. Keep existing approved Spanish defaults, subjects, variables, saved values, recipient switches, previews and tests untouched except for necessary shared infrastructure compatibility.
2. **Strategic Activity Reports (new):** `STRATEGIC_MIDDAY_REPORT` and `STRATEGIC_END_OF_DAY_REPORT`. Both must be visible and editable in the same existing area; each needs Subject, Body, Preview, Save, Restore default, and eventually Send test (CP3). Seed the approved V1.1 strategic default text, without replacing it with motivational copy.

The Recipients area must provide separate, **OFF by default**, per-manager strategic midday/end-of-day switches, without changing the motivational recipient preferences. Restrict editing to authorized admins within the correct tenant. Recipient inclusion must be resolved server-side against the actual hierarchy, roles and grants, not merely UI filters. A CEO sees authorized descendants including the Sales branch; a COO does not inherit CEO-only Sales users; RMs see only their subtree. Never duplicate people through indirect paths or mix tenants. A supervisor without authorized descendants does not gain new visibility just by having a manager-like label.

### Strategic report contract

**Midday (12:00 p.m. reporting cut):** separate block for each authorized subordinate: Activity Breakdown by category (events, miles, time, estimated fuel cost when authoritative data exist), followed by today's recorded activity details, timestamp/duration, and **only email-approved notes**. Mark in-progress/incomplete values honestly. No weekly total block in midday.

**Closing report:** for each authorized subordinate, provide (1) today's breakdown, (2) chronological today's activity details, and (3) the **individual week-to-date** totals by category. **AFTER all person sections**, append **exactly one mandatory `Team Weekly Summary`**, including clearly labeled week-to-date boundaries, unique people, activities, miles, time, category totals and cost only if supported. No duplicate activities/people. Totals must reconcile with the included per-person weekly blocks. The manager's own activity is excluded unless separately approved.

Use existing authoritative Activity/WorkSession/breakdown calculations and original recorded timestamps; preserve the session's correct operational date for overnight work, and do not fabricate zero cost, zero duration or totals when measurements are incomplete. Do not change official mileage, activity states, `End Work`, the Activity UI or timezone-storage behavior to implement email reports.

### Tokens, preview, security

Support the **approved V1.1 placeholders** including `{{manager_first_name}}`, `{{per_person_report}}` and the mandatory closing `{{team_weekly_summary}}`. Required generated blocks cannot be deleted by editing the surrounding prose. Allow controlled template edits, persisted per tenant with defaults/restoration and audit. Preview must use a fixed, entirely **fictional** hierarchy with at least two people, representative notes, timestamps, multiple categories and reconciled week totals. Preview never triggers an email or queries private real-user notes.

Real free-form activity notes are **not approved for email transmission yet (DP-NOTES)**. Build a safe redaction/approved-notes boundary: real outbound messages must omit/redact unapproved notes until the PO approves explicit policy. The synthetic demo may show safe fictional notes. Protect template rendering and displayed notes against injection and unsafe HTML.

## 4. Objective C - Test all five email cases (CP3)

Reuse the CP1 send-test infrastructure, idempotent budget, audit, and real backend selection. **No new mail provider configuration module**.

| Case | Entry point | Expected test content |
|---|---|---|
| T0 | Platform > Outbound email > Send Test Email | Generic `[TEST]` integration message; recipient manually entered by platform admin |
| T1 | Motivational Midday > Send test | Stored midday template, fictitious activity totals |
| T2 | Motivational Closing > Send test | Stored closing template, fictitious daily and weekly totals |
| T3 | Strategic Midday > Send test | Stored strategic midday template, two fictional subordinate reports, activity details |
| T4 | Strategic Closing > Send test | Stored strategic closing template, individual daily/week blocks, final de-duplicated `Team Weekly Summary` |

For T1-T4 preserve approved test-target permissions and use saved templates plus the **same controlled renderer** that their respective production paths would use, supplying only deterministic fictional data. All tests use one actual test destination, not distribution to real recipients; sending a test must not alter work sessions, activity records, subscriptions, real message quota or schedules.

Show clear user feedback for authenticated/verified, provider accepted, captured in development, failed and delivered **only if separately confirmed by receipt**. Include T0-T4 responsive UI and negative permission tests. For a real-provider test, CER will configure credentials in the Platform UI, run `Verify`, then send explicitly and check the inbox (including spam). Do not assert success based only on automated mocked tests.

## 5. Authorization and sequencing

Work in short controlled checkpoints:

- **A - Reconciliation and T0 correction:** inspect deployed vs local state; restore safe editable provider-test recipient; tests and regression. If the live build is missing CP1, diagnose deployment first rather than rewriting CP1.
- **B - CP2 strategic configuration and renderer:** create editable strategic templates, recipient controls, safe preview and weekly team block; tests. Report completion separately.
- **C - CP3 strategic test sends:** T3/T4 and complete T0-T4 five-case test matrix; tests, screenshots and receipt evidence when a live provider is available.

**Do not activate automatic delivery or implement the scheduled-email CP4 as part of this instruction.** The maximum local closing-report cutoff mechanism was approved, but the numeric time is still a PO decision. DP-NOTES, DP-WEEK, DP-TIMEZONE, DP-TEAM and scope-policy verification still gate real strategic dispatch and production certification. Do not silently select these values or send real management notes.

## 6. Required tests / acceptance evidence

1. Actual deployed screen/version reconciled with the expected V1.1 baseline. Screenshot the revised Provider Verify screen showing an editable valid recipient and preserve the separately functioning Verify action.
2. T0 entered address accepted for a platform admin; syntactically invalid/extra fields forbidden; 401/403/422/429 and shared concurrent quota tested. Existing M365/SMTP/console/memory semantics preserved.
3. All four saved templates displayed, persisted, previewed and restored; edits to strategic content do not change motivational defaults and vice versa; migrations are safe for existing data.
4. Independent recipient toggles stay OFF by default, scoped by tenant/roles/hierarchy, and are audited. Include cross-tenant and CEO/COO/Sales negative tests.
5. T3/T4 previews include two people; T4's single final `Team Weekly Summary` matches the individual week totals and appears **after** them; no week summary in T3.
6. Tests demonstrate no transmission of real activity data or unapproved notes. Actual test messages show `[TEST]` and fictional data.
7. Backend tests, API/integration tests, E2E desktop/mobile, migration-head checks, frontend typecheck/build, focused regression and any outstanding baseline failure reported as such.
8. Distinguish `Completed`, `Partial`, `Blocked`, `Pending validation` and `Not implemented`. Report Expected > Implemented > Evidence > Gap > Impact. Provide commit/branch, migration identifiers, files touched, screenshots, test commands/results, and explicit deployment/receipt evidence (or blocker).

**Definition of Done:** A is ready only once the corrected provider UI/API/security work is demonstrated. B is ready only when both strategic templates and their independent recipients/renderers actually exist. C is ready only when all five explicit test paths have passed code/E2E checks; external real-email receipt is a separate validation gate. A healthy provider indicator alone does not close that gate.

## 7. Do not change

Do not redesign CER Route navigation; add independent Mail modules; loosen tenant security; turn on subscriptions by default; alter motivational copy, operational calculations, WorkSession behavior, End Work, approved mobile baseline, mail backend selection/fallback logic outside the requested test path, or production dispatch schedules. Prefer shared current components and surgical changes. Ask for a PO decision only when blocked by a genuine product choice, not for implementation details already determined by the accepted V1.1 specification.
