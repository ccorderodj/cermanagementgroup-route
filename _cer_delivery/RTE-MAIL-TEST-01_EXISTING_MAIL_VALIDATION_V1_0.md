# RTE-MAIL-TEST-01 — Existing Mail Audit, Provider Integration and Controlled Tests

**Project:** CER Route
**Version:** 1.0
**Date:** 2026-10-16
**Status:** NEXT CONTROLLED DEVELOPER CHECKPOINT — audit and test only; production activation requires separate authorization
**Owner:** Product Owner, CER Route
**Related instructions:** RTE-NOT-01 (personal motivation); RTE-NOT-STR-01 v1.1 (strategic reports)

## Context and decisions

The Product Owner already has email-provider keys and confirms that **CER Route has a Mail area**. Its implementation, operational readiness, provider, sending contracts, background scheduler, and deployment wiring have **not been verified by this instruction**. Existing motivational templates and per-user enrollment are defined in RTE-NOT-01; strategic reporting is a subsequent extension of **the same Mail capability**, not a new standalone email system or navigation module.

**Confirmed:**
- Reuse the existing Mail area, provider integration, identity, tenant/permission/audit services and supported scheduler/queue if present.
- **Motivational midday:** 12:00 p.m. in applicable local timezone, user-enrolled; **motivational end:** own End Work +20 minutes, per its previously approved rules.
- **Strategic midday:** 12:00 p.m. for enrolled managers; manager need not have a personal workday.
- **Strategic end:** once per manager per operational day, **20 minutes after all known active eligible team workdays close, OR at a configurable maximum local reporting time, whichever occurs first**. The cutoff clock time is **not yet approved**. Do not send automatically until configured/approved and content disclosure policy resolved.
- Separate recipient preferences for motivational vs strategic reports; all off by default for new enrollment, no forced mass opt-in.
- No unapproved change to Web/Mobile baseline, Start Work, End Work, hierarchies, activity data, or official mileage/cost calculations.

**Priority:** test and stabilize existing Mail with controlled deliveries **before** expanding the strategic reporting system.

## Objective — checkpoint RTE-MAIL-TEST-01

Determine, with reproducible evidence, whether existing Mail can:
1. Read its secret provider configuration safely and connect to the intended provider.
2. Render a known safe test template and send it to a pre-approved test recipient.
3. Reliably report the distinction between queued, accepted by provider, delivered (only when evidence is available), bounced/rejected, failed or not attempted.
4. Support a controlled test for each approved motivational template, without disclosing actual user's operational data or altering production subscriptions.
5. Identify and document what remains to automate noon and End Work +20 min if scheduling is not yet implemented.

Deliver diagnostics and test evidence; do not silently authorize production mass sends or implement the full strategic renderer during this checkpoint.

## Current State — verify, do not assume

Inspect and list actual source paths/components/contracts for:
- Current **Mail** navigation and administration UI (including existing templates, recipients, configuration and history if any).
- Provider adapter/client and secrets configuration; provider type; sender/domain identity; available sandbox or testing mode.
- Email template rendering and placeholders, HTML/text escaping, preview, tenant-specific persistence and current recipient toggles.
- Background execution mechanism and durable delivery ledger/idempotency, if any; deployment mode in DigitalOcean (if relevant).
- Workday and End Work event/data contracts; timezone mapping and user email validation.
- Authorization (server-side tenant + scope), audit hooks and error handling.

Classify each as **AS-BUILT/CONFIRMED, PARTIAL, NOT IMPLEMENTED/GAP, BLOCKED, PENDING VALIDATION, DEVIATION or TECHNICAL DEBT**, with code/test evidence. Existing MD specs alone are not implementation proof.

## Scope — test implementation if needed

### A. Secrets / provider configuration

- Use the existing runtime secret manager or environment variables; do **not** paste keys into source, documents, screenshots, chat, migrations, UI payloads or logs.
- Validate only non-secret attributes for operators: provider identifier, configured sender/domain, sandbox/test-vs-live state, masked credential status and last connection/test outcome.
- Confirm provider-specific sender verification / SPF, DKIM or DMARC prerequisites as applicable; distinguish connection/accepted vs real inbox delivery.
- Do not rotate, create or expose provider credentials unless explicitly requested by the Product Owner.

### B. Controlled test surface

Prefer **existing Mail test/diagnostic controls**. If absent, add the smallest authorized admin-only diagnostic action within Mail, with minimal API/service support:

- **Check connection:** non-disruptive credential/configuration check (when supported by provider); report honest pass/partial/fail, no claim of delivered mail.
- **Send test email:** admin selects an allowlisted/verified test recipient and one approved template; use **synthetic fixtures** (not live personnel, notes or client names). Label test clearly in subject/header and event logs.
- **Preview:** mock values with zero provider calls.
- Keep test deliveries isolated from real production recipient preferences and normal once-per-day idempotency keys.
- No arbitrary bulk sends, BCC/CC or external recipient listing; rate-limit test action, audit actor/tenant/destination/time/result without logging sensitive contents.
- Production environments must have explicit safe-test allowlist, permissions and/or guardrail; no free-form unverified destinations.

### C. Scheduling verification (test/harness, not automatic go-live)

- If a durable scheduler exists, test due-time computation with an injectable clock in test/staging; otherwise identify the missing capability and propose a separate checkpoint. Do not add browser timers or put provider calls inside HTTP End Work transaction.
- Validate local noon, successful End Work +20, resumption before due time, duplicate End Work/retry, inactive user, revoked enrollment, missing email, timezone/DST and legitimate crossing-midnight workday.
- For a test worker/job, persist delivery state and enforce idempotency. Simulated sends should never reach non-test inboxes.
- Clearly separate unit/integration simulation from a single genuine controlled email delivered to a test mailbox.

## Out of Scope

- Publishing scheduled production sends to all users.
- Building the strategic per-person activity renderer or transmitting real subordinate notes.
- Unapproved schema changes to Activity/Workday, permission grants or menu/navigation redesign.
- Choosing strategic cutoff hour without Product Owner approval; using a server-default timezone silently.
- Auto-subscribing users or managers, or modifying the approved motivational copy.

## Security and privacy controls

- Verify server-side permission and tenant isolation on connection tests, previews, test send APIs and recipient resolution.
- Never allow a client-submitted tenant, manager or arbitrary destination to bypass server-derived scope.
- Do not use operational notes as test payloads. Where strategic notes contain sensitive personnel/customer information, block real mail disclosure pending policy decision.
- Log minimal delivery metadata and sanitized provider error codes; never credentials, full note contents, auth tokens or third-party secrets.
- Keep pre-production/staging tests isolated from production data and avoid sending from a nonverified identity.

## Acceptance criteria

| ID | Expected evidence |
| --- | --- |
| AC-01 | Inventory of real Mail files/services/settings/scheduler and gap matrix with repo paths and evidence. |
| AC-02 | Provider secrets are consumed from secure runtime configuration; no plaintext leakage to code, UI or logs. |
| AC-03 | At least one connection/configuration test produces an accurately classified result. |
| AC-04 | A test of both motivational templates renders approved demo text safely (preview and, if provider is functional, authorized test send). |
| AC-05 | One controlled actual send has traceable acceptance and test-mailbox receipt evidence (if mail delivery is available); provider acceptance is not incorrectly labeled delivered. |
| AC-06 | Failure/invalid sender/bad credentials/unauthorized actor/invalid recipient are surfaced without sensitive logs. |
| AC-07 | Noon and End Work +20 scheduling rules have automated simulated tests **if** execution infrastructure exists; otherwise marked GAP with recommendation, not Completed. |
| AC-08 | Test sends never enroll actual users or consume normal daily quota/idempotency, and never modify Workday/Activity records. |
| AC-09 | Tenant/RBAC negative cases, existing Mail regression, responsiveness of any added admin control and audit verified. |
| AC-10 | Developer handoff clearly separates confirmed operational sending from not implemented or pending activation. |

## Deliverables

1. Developer MD with **Expected → Implemented → Evidence → Gap → Impact**, per checkpoint **Completed / Partial / Blocked** and as-built paths/contracts.
2. Non-secret provider/runtime checklist (configured vs missing); do not include key values or unmasked token fragments.
3. Commands/test cases/results, sanitized provider/test-send log references, receipt screenshot (synthetic content), and failures.
4. Concrete next-step recommendation: (i) fix current Mail defects, (ii) implement motivational scheduled sending where missing, or (iii) progress to Strategic Mail configuration once current send base is validated.
5. Branch/commit, migrations if any, permissions/audit evidence, Web/Mobile regression statement.

## Subsequent checkpoints — **not authorized by this file**

- **MAIL-CP2 — Motivational scheduling/readiness:** only after verified provider tests, implement or certify noon/end scheduling, eligibility and monitoring with safe staged rollout.
- **MAIL-CP3 — Strategic config in existing Mail:** add two strategic templates and manager recipient toggles, reusing current Mail UI/engine; independent of motivation.
- **MAIL-CP4 — Hierarchical strategic renderer:** bounded per-person daily breakdown + detail, week aggregates; verify note confidentiality and scope.
- **MAIL-CP5 — Strategic scheduled sending:** noon plus approved team-close+20/max cutoff behavior, retry/idempotency, delivery auditing and rollout gate.

## Decisions pending (do not assume)

- **DP-01:** Exact configurable **maximum end-of-day strategic report time**, in recipient's business timezone. Max-time mechanism approved; clock value not yet selected.
- **DP-02:** Policy on sending full free-text subordinate notes to manager inboxes vs limiting restricted data to authenticated CER Route views. Real notes must not be emailed until this policy is approved.
- **DP-03:** Confirm local reporting timezone mapping / weekly boundary for multi-state teams. Do not convert legitimate overnight sessions into forced closures.

**Release instruction:** execute RTE-MAIL-TEST-01 first, return evidence MD for Product Owner validation, then request release of the next checkpoint. Do not expand into Strategic Activity Reports implementation in this checkpoint.
