# RTE-MAIL-UNIFIED-01 — Email Test Send & Strategic Activity Reports

**Project:** CER Route — independent application  
**Version:** 1.1  
**Date:** 2026-10-16  
**Owner:** Product Owner / CER Development Copilot  
**Document purpose:** **One consolidated development instruction**, executed through controlled checkpoints.  
**Approval boundary:** Implement safe test sending for the provider and all four email templates, and the configurable strategic report with its secure, testable renderer. **Do not enable unattended production delivery** until the explicit GO gates in this document are closed.

**V1.1 change control (2026-10-16):** PO confirms the two strategic templates and explicitly requires a **Team Weekly Summary at the END of the strategic end-of-day email**, following all individual day/detail/week blocks. It consolidates week-to-date activity for the entire authorized subordinate scope, by category and overall totals, without counting anyone or any activity twice. **No other scope, architecture, permission, template cadence, or checkpoint is changed** from V1.0.

## 1. Context — baseline, not assumptions

Use the developer's `RTE-MAIL-TEST-01_EXISTING_MAIL_VALIDATION_REPORT.md` (2026-10-16) as the primary *reported* implementation evidence; verify against the target repository branch and deployed environment before editing.

| Component / decision | Evidence classification | Consequence |
| --- | --- | --- |
| `Platform > Integrations & Settings`, `Platform > Diagnostics`, and `CER Route Configuration > Activity Emails` exist; **no standalone Mail screen** was found | AS-BUILT (reported) | Extend existing email surfaces, no parallel Mail navigation or redesign. Product Owner's request to add reporting “within existing Mail” means the **existing mail capabilities**, not an invented menu. |
| M365 OAuth, SMTP, console and in-memory backends in `app/core/email/backends.py`; `send_email`, `get_email_backend` | AS-BUILT (reported) | Reuse the actual provider chain; distinguish physical sends from console/memory. |
| Platform `POST /api/platform/integrations/{key}/test-message` sends a generic test but accepts an arbitrary destination | AS-BUILT + TECHNICAL DEBT (reported) | Harden existing provider test; do not duplicate it. |
| Provider `Verify` calls `backend.check()` without sending | AS-BUILT (reported) | Keep `Verify` distinct from `Send Test Email`. |
| `Activity Emails` already stores two editable motivational templates and two recipient toggles; preview with fictitious values | AS-BUILT (reported) | Preserve the approved user-facing copy and existing stored preferences. |
| `GET /api/activity-emails/test-targets`, `POST /api/activity-emails/templates/{type}/test-send`, `Send test` dialog, `MAIL_TEST_RECIPIENTS`, anti-spam/audit rules were developed on `feature/rte-mail-test-01` | PARTIAL — reported locally | First verify merge, deployment and permissions; reuse if present instead of duplicating. |
| No real provider was configured in the examined local database; DigitalOcean environment was not verifiable; no real inbox reception | BLOCKED / PENDING VALIDATION | Owner/admin must configure keys using the secured UI and confirm inbox reception; developer cannot declare AC-05 completed based on mocks. |
| `app/core/platform/scheduler.py` uses APScheduler with PostgreSQL leader lock; no Activity Emails delivery job or delivery ledger | AS-BUILT + GAP | The test-send path must never pretend to be a scheduler. Scheduler is a *separate gated checkpoint*. |
| One historical unrelated test failure (RTE09 capability expectation) and a frontend source-tracking failure reportedly corrected after `git add` | PENDING REGRESSION VERIFICATION | Require rerun/evidence; do not claim full regression is green without it. |

**Existing approved references:**
- `RTE-NOT-01_ACTIVITY_EMAIL_TEMPLATES_RECIPIENTS_V1_0.md` — personal motivation defaults.
- `RTE-NOT-STR-01_STRATEGIC_ACTIVITY_REPORTS_V1_1.md` — strategic breakdown, security, hierarchy and scheduler rules.
- `RTE-MAIL-TEST-02_PROVIDER_TEST_UI_AC05_CLOSURE_V1_0.md` — scoped provider-test hardening.

This instruction **supersedes separate implementation handoffs** for those items; consult references only for additional rationale. Avoid coding features twice.

## 2. Objective and business separation

Deliver an end-to-end, explicitly invoked **demo email test** for **each** of five cases (provider + four templates), and prepare **Strategic Activity Reports** as a distinct, editable, per-manager hierarchical reporting capability using the existing email integration.

**Type A — motivational (already approved):** friendly, brief, individual activity reminders; deliberately omits detailed notes, routes, mileage, fuel and individual performance comparison.

**Type B — strategic (new):** management-level, each authorized subordinate shown separately with Activity Breakdown and daily activity details (including times and only email-approved notes), plus a per-person week-to-date section **and a separate Team Weekly Summary at the very end** of the closing report. No employee ranking, grading or unsupported inference.

**Essential distinction:** successful demo delivery **does not** mean automatic sending is configured, approved or running.

## 3. Scope / out of scope

**Implement in this instruction (through CP1–CP3):**

1. Confirm and reuse present UI, backend, auth, audit, provider, test targets and template components.
2. Secure/discover `Verify` and `Send Test Email` on the **existing provider integration** screen.
3. Retain/make accessible **Send test** for both motivational templates.
4. Add **two strategic templates** and per-manager, independent recipient preferences within the existing CER Route email configuration area, without recreating the provider UI.
5. Implement read-only, server-authorized **per-person strategic report aggregation/rendering** against existing operational contracts, with safe omissions of unauthorized note content.
6. Add **Preview** and **Send test** for **both** strategic templates, using deterministic **fictitious** hierarchy, notes and activity records only.
7. Validate all five tests and provide a safe deployment/real-inbox verification path; supply complete evidence and negative security tests.
8. Design/document the later automated schedule and its data contracts. It may be implemented in a **separately authorized CP4** after gates are closed; this MD is the authoritative scope for that future CP4 so no second broad specification is required.

**Out of scope without Product Owner authorization:**

- Activating any background email to real users or executives, or silently switching on subscriptions.
- New standalone `Mail` module, additional Admin navigation, mobile workday redesign or duplicative delivery/provider services.
- Changes to `Start Work`, `End Work`, approved overnight sessions, Activity execution, GPS, route map, official miles/fuel calculation, time-zone contracts or hierarchy assignments.
- Arbitrary bulk mail, free-text testing destinations, unsolicited sending to employees or customers, external CC/BCC, attachments.
- Publishing full unrestricted activity notes into external email before the note-disclosure policy is approved.
- AI-written messages, scoring, rankings, employee evaluations, disciplinary language or imagined events.

## 4. Reuse and UI placement

**Provider configuration and real test:** `Platform > Integrations & Settings`; preserve `Platform > Diagnostics` for connectivity. There is **no verified standalone Mail section**; do not fabricate one to comply with a conceptual label.

**Templates, recipients, preview and template tests:** extend existing `CER Route Configuration > Activity Emails` using its established UI patterns. Present two **clearly differentiated groups** on existing surfaces (e.g., tabs/cards within the existing page):

- **Motivational Emails** — current `MIDDAY_MOTIVATION`, `END_OF_DAY_RECOGNITION` unchanged.
- **Strategic Activity Reports** — `STRATEGIC_MIDDAY_REPORT`, `STRATEGIC_END_OF_DAY_REPORT` newly configurable.

Reuse existing user directory, permissions, tenant context, controls, test-target dialog, validation/audit patterns. Test UI on narrow screens. **No new top-level admin menu** or cosmetic redesign without explicit approval; if current page cannot reasonably accommodate both groups, report an option and request authorization before changing navigation.

Each template's visible actions: `Preview` (no email), `Save`, `Restore default`, `Send test` (explicit real external attempt if a real provider is configured). A test recipient is chosen from the allowed server-provided destinations; no general email field or “send to all”. Show delivery-state text separately from configuration state.

## 5. The five demo send cases — unified behavior

| ID | Test action / location | Subject / content | Data used |
| --- | --- | --- | --- |
| **T0** | Integration provider — `Verify` then **Send Test Email** | Fixed provider check message, `**[TEST] CER Route — Email integration**` | No operational data |
| **T1** | Motivational — **Midday Motivation → Send test** | Approved stored midday subject/body | Fictitious individual and completed-activity counts |
| **T2** | Motivational — **End of Day Recognition → Send test** | Approved stored end-of-day subject/body | Fictitious daily and week-to-date counts |
| **T3** | Strategic — **Midday Report → Send test** | Stored strategic midday subject/body with per-person block | Fictitious authorized management hierarchy, day-to-noon breakdown + activities/times/allowed notes |
| **T4** | Strategic — **End-of-Day Report → Send test** | Stored strategic closing subject/body with per-person blocks **followed by Team Weekly Summary** | Fictitious daily breakdown/details, week-to-date per person **and final de-duplicated whole-team weekly totals** |

For T1–T4: send the **saved template**, not a hardcoded copy which conceals template bugs; render through the **same safe template/report renderer** that production would use, but inject deterministic sample data. The strategic sample must demonstrate at least **two people separately**, category summaries, chronological activity rows, recorded times, safe sample notes, and distinct daily/weekly windows; for T4 add the **final whole-team weekly summary** reconciling with all included people, and show an in-progress row as such. Seed demo content only, no real customers/employee names, personnel records or sensitive notes.

For all five actual send attempts:

- The caller explicitly chooses **one approved test mailbox** (`MAIL_TEST_RECIPIENTS` and/or their own email, only where current policy permits) provided by the server. The server enforces allowlist, permitted actor, tenant/role and allowed template; arbitrary email, other tenant, CC/BCC, forged template ID or extra request fields => reject.
- Require authorized **platform admin** for T0. For T1–T4 use the existing tenant/Route template-management capability or a narrowly approved strategic-template permission; **having a manager role alone is not permission to send test emails**.
- Mark **subject** `[TEST]` (exactly once), prominent body banner `CORREO DE PRUEBA — datos ficticios`, header `X-CER-Route-Test`; do not falsely show the reported data as real. Clear display that tests do not enroll recipients.
- Reuse one shared durable anti-spam budget of **at most 5 sends per actor per 15 minutes** across applicable test paths unless existing platform policy is stricter; make it correct across replicas and race conditions. Denial uses `429`; do not create separate five-send budgets per template.
- Structured audit for *attempt*, selected template/provider, actor, scoped tenant, test destination, outcome and time. No secrets, note bodies, template contents, personal activity data or raw provider exceptions in audit and application logs. Consider recording denials without exposing guessed addresses.
- Tests must not change user preferences, work sessions, activity records, workday counts, job schedules, production delivery logs or idempotency/once-a-day quota.
- Outcomes distinguish `accepted_by_provider`, `not_sent_development_backend`, `captured_by_test_backend`, `not_configured`, `failed_auth`, `failed_unreachable` and denied/rate-limited. The UI **must never label `accepted_by_provider` as delivered**; actual delivery requires inbox confirmation.
- When testing a specifically selected provider/integration, do not silently count an unexpected fallback as success of that selected provider. Show the sanitized actual backend type used; console/memory never pass external delivery verification.
- Protect all rendering from HTML, template-expression, email-header and content injection. Disallow arbitrary URL or script token execution. If creating HTML emails, include a safe plain-text equivalent.

**Implementation constraint:** inspect whether existing `POST /api/platform/integrations/{key}/test-message`, `GET /api/activity-emails/test-targets`, `POST /api/activity-emails/templates/{type}/test-send` already meet these contracts, then extend/reuse them. Avoid parallel `test-send-v2` endpoints; if a new strategic route is necessary, keep it in the same activity-email subsystem with comparable authentication and anti-spam behavior.

## 6. Default template content — complete contract

### 6.1 Motivational: `MIDDAY_MOTIVATION` — **PO-APPROVED; preserve existing data**

**Subject:** `¡Buen trabajo! Sigamos adelante 💪`

```text
¡Vas haciendo un gran trabajo!

Hola, {{user_first_name}}:

Ya estamos a mitad del día y queremos recordarte que cada actividad cuenta.

{{midday_activity_block}}

Cada visita, cada conversación y cada esfuerzo contribuyen a nuestros objetivos.

¡Continúa con esa energía y que tengas una excelente tarde!

CER Management Group
```

### 6.2 Motivational: `END_OF_DAY_RECOGNITION` — **PO-APPROVED; preserve existing data**

**Subject:** `¡Jornada finalizada! Este es tu avance de hoy 🌟`

```text
¡Excelente esfuerzo hoy!

Hola, {{user_first_name}}:

Has finalizado una jornada más. Gracias por tu dedicación y compromiso.

{{day_activity_block}}

{{week_activity_block}}

El trabajo constante construye grandes resultados. Gracias por todo lo que aportas.

¡Descansa y recarga energías para tu próxima jornada!

CER Management Group
```

Allowed personal tokens: `{{user_first_name}}`, `{{midday_activity_block}}`, `{{day_activity_block}}`, `{{week_activity_block}}` according to template type. Required summary blocks cannot be deleted. The demo is not a substitute for actual scheduling and counting; never add notes, routes, GPS, mileage, sensitive names or fuel to motivational mail.

### 6.3 Strategic: `STRATEGIC_MIDDAY_REPORT` — **proposed editable initial copy**

**Subject:** `CER Route | Reporte operativo de mediodía — {{report_period_label}}`

```text
Hola, {{manager_first_name}}:

Compartimos el avance operativo registrado por las personas bajo tu supervisión hasta las 12:00 p. m. de hoy.

{{per_person_report}}

Este reporte refleja únicamente la actividad registrada en CER Route hasta el momento del corte. La información en curso o pendiente de cierre se identifica como tal.

CER Route
```

### 6.4 Strategic: `STRATEGIC_END_OF_DAY_REPORT` — **proposed editable initial copy**

**Subject:** `CER Route | Resumen del día y acumulado semanal — {{report_period_label}}`

```text
Hola, {{manager_first_name}}:

Compartimos el resumen de las actividades registradas hoy por las personas bajo tu supervisión, junto con su acumulado de la semana.

{{per_person_report}}

{{team_weekly_summary}}

Los datos corresponden a la información registrada y autorizada en CER Route al momento de generar el reporte. Las actividades pendientes de cierre o medición se indican expresamente.

CER Route
```

The PO has **approved retaining both strategic email variants and the V1.1 closing structure**, including the final team weekly block. Preserve both email purposes and the designated dynamic sections; any further meaning/content changes require review.

Strategic token allowlist: `{{manager_first_name}}`, `{{report_period_label}}`, `{{report_generated_at}}`, `{{per_person_report}}`, and, **only for the end-of-day report**, `{{team_weekly_summary}}` and where needed `{{week_period_label}}`. `{{per_person_report}}` is mandatory in both templates and `{{team_weekly_summary}}` is **mandatory and non-removable in the closing template**. Both are generated server-side from authorized records; do not allow them to be substituted by arbitrary user-controlled HTML, manager-ID strings or edits that silently remove required output.

## 7. Strategic reports — functional specification

### 7.1 Recipients and configurable scope

In the existing email administrative area, provide a dedicated **Strategic Activity Reports** configuration group:

| Existing eligible manager | Current organizational coverage (read-only) | Linked account email (read-only) | Midday | End of day |
| --- | --- | --- | --- | --- |
| User from existing CER Route directory | Derived from existing assignments/grants | Current validated recipient email | OFF/ON | OFF/ON |

- Toggles independent **of each other** and **of** motivational preferences; initial values OFF. No auto-enroll for existing executives. No manually typed manager recipient and no “enable all”.
- Do **not** equate role title with a universal right to read notes. Compute authorized **direct and indirect reports** within tenant and data scope using actual manager relationships, grants and replacements; fail closed on ambiguity/cycles. Manager's own work excluded from report by default. Report all eligible descendants individually; do not collapse into one aggregate.
- Approved organizational principle: exactly one tenant CEO; COO → assigned Regional Managers → assigned Supervisors/On-Site Managers; Sales reports to CEO and is **not included in COO's subtree** unless an approved organizational assignment changes this.
- Managers receive a report only when configured, active, associated with a valid/appropriately verified mailbox, and authorized at read/dispatch time. Transfers/revocations must be reflected immediately; old assignment should not continue disclosing notes.
- The administrator who can edit email settings must be separately authorized. Editing subscriptions must **not grant the receiving manager permissions** to see more operational data.
- Show coverage count only where authorized; saving must be persistent, tenant-scoped, audited (before/after, actor, target, time) and safe against concurrent changes.

### 7.2 Per-person section in both strategic variants

Repeat the following **for each eligible person**, sorted by a stable non-evaluative ordering (hierarchy/name, **never performance**):

1. **Person header:** display name and operational role (no SSN, email, personal phone, or confidential references).
2. **Activity Breakdown:** reuse existing CER Route server metric contracts used by the Activity breakdown screen. Columns `Activity`, `Miles`, `Time`, `Events`, `Estimated Cost`; present the supported categories such as Client Visit, Employee Visit, Recruiting, Check Delivery, Office, Other only when relevant to actual data and allowed. **Do not duplicate or reinterpret** official mile, time or fuel algorithms.
3. **Activity Details immediately below the breakdown:** chronological rows with category/type, operational day, recorded start/end time where reliable, duration, status (`Finalizada`, `En curso`, `Sin cierre registrado` as applicable), and **only notes permitted for external email by the final approved field policy**.
4. Where notes are empty use `Sin notas registradas`. If forbidden/uncertain: `Detalle no incluido en el correo` and a link into an existing authenticated authorized view only if such a route exists and has been audited; **never place a secret, token or direct note payload in the URL**.
5. Missing metrics display `No disponible`, not invented zero. Incomplete durations clearly labeled, and the meaning of the existing `+` time indicator must be verified before mirroring it.
6. No GPS traces, client/employee identifying details, attachments, maps, rankings, comments about employee performance or results inferred beyond recorded activities.

**Midday:** window ends **12:00 p.m.** recipient/reporting business time; day-to-cutoff breakdown and detailed activities per person. Report only observed work without implying inactivity is absence. The recipient does not have to be clocked in.

**Strategic end of day:** for each person, show **today's breakdown + today's detailed activity list** and then a **distinct individual week-to-date category summary** (event counts, miles, activity duration and estimated cost only when supported by current authoritative calculations). **After every individual block has been shown**, render the **mandatory Team Weekly Summary** defined in §7.4. Do not reproduce a whole week of note-by-note records by default. Local `session_date` (operational start date) governs legitimate overnight work; use timezone-aware timestamps and do not silently fall back to UTC as display time. Week start **Monday remains pending PO confirmation**.

**Email volume:** ensure 1, 0 and many subordinates render safely in desktop/mobile email clients. Long content must not be silently truncated. If actual report exceeds safe size, provide a documented mitigation proposal (e.g., authenticated in-app detail after authorization) for PO approval rather than sending incomplete unseen content.

### 7.3 Confidential notes — hard boundary

The PO requested a note-level managerial report; **that does not settle which free-form notes may lawfully or safely leave CER Route in email**. Email is forwardable and stored outside the application.

- For **demo previews/sends**, all notes must be **fictional**, pre-reviewed sample text.
- For **live aggregation**, implement separation between authorized source fields and email-approved output. Use **explicit field allowlist/data-classification and server-side permission**; no assumed magical PII detection and no automatic unrestricted full-note export.
- Until **DP-NOTES** is approved, production email **must omit real free-form notes**; implementing the renderer and demo is allowed. Where required by the acceptance contract, display the restricted indication. Full-note emails are **NO-GO** until PO/security/legal policy decision.

### 7.4 Mandatory final section — `Team Weekly Summary` (end-of-day ONLY, approved V1.1)

**Placement:** Insert exactly once at the **end of the strategic closing email**, **after the last individual person's daily Activity Breakdown, daily Activity Details, and individual Weekly Activity Summary**, and **before the final informational closing text**. Do **not** include this section in `STRATEGIC_MIDDAY_REPORT` or the individual motivational emails. This block must remain present even if the administrative editor adjusts the surrounding wording: it is a required, server-rendered section, not optional marketing copy.

**Visible content:**

1. Heading `Team Weekly Summary` and the explicitly labeled **week-to-date reporting period** (start date through the report's actual cutoff, not an entire completed week if it is still in progress).
2. **Overall metrics for the manager's authorized reporting team:** number of unique people *with recorded activity* (label this definition explicitly), total number of eligible events/activities, official recorded miles, total recorded activity time, and estimated cost **only if the existing Activity Breakdown contract supports it**. Keep counts/distance/duration/cost separate; **do not present time spent on activities as a person's full paid work shift**.
3. **Category breakdown** for the same weekly window. Minimum columns: `Activity` / `Week-to-date events`, with `Miles`, `Activity Time` and `Estimated Cost` only where the authoritative service provides valid values. An additional `Today events` comparison column may be shown using the same daily window, but must **not replace** week-to-date metrics or make daily values look weekly.
4. **Total** row reconciled with the individual weekly sections in this **same email**, using the *same eligible person set, reporting dates, scoping, metric definitions, rounding and availability rules*. If a metric cannot be derived reliably, show `No disponible` or appropriately indicate a partial total, **not zero** or a made-up sum.
5. This section contains **aggregated data only**. Do not repeat all individual notes, routes or detailed activities here; those remain in the per-person daily sections, subject to the notes-disclosure boundary in §7.3.

**Aggregation and controls:**

- Derive the unique authorized descendant-person set **once** for the manager within their tenant and server-side data scope. Reuse that same effective set in both the individual sections and the final team summary; include direct and indirect descendants only if authorized by current hierarchy/data grants. **Never automatically fold in the manager's own activity.**
- **De-duplicate on canonical activity/event identity** before weekly aggregation; if the same user appears through multiple hierarchical paths, their authorized activity must count **once**, never once per reporting level. Do not add a manager's personal team total to subordinate manager team totals if both already contain the same underlying activities.
- Match the existing official Activity Breakdown calculation/service for events, miles, activity time and estimated costs. Never independently calculate mileage, infer timestamps, reinterpret time zones or inflate unavailable metrics; preserve operational-date rules for sessions crossing midnight.
- When there are no eligible people or weekly events, show a clear `Sin actividades registradas para el período` / `Sin personas autorizadas para el reporte`, instead of a blank or fabricated card, without disclosing unauthorized users.
- The weekly reporting boundary remains **DP-WEEK** pending PO confirmation (the synthetic demo must label its explicit sample dates). This pending decision does not block implementation of deterministic demos or the template's required section, but **does block certification of live week-to-date numbers**.

**Demonstration / required example shape** (fictitious values only; not a mandate to hardcode metrics):

```text
Team Weekly Summary | Semana [inicio] - [corte]
Personas con actividad registrada: 2
Actividades registradas: 52 | Millas: 662.5 | Tiempo en actividades: 44h 45m

Actividad       Eventos semana    Millas    Tiempo
Client Visit    27                ...       ...
Recruiting       8                ...       ...
Office          14                ...       ...
Other            3                ...       ...
TOTAL           52               662.5     44h 45m
```

Use sample figures internally consistent with the **two or more individual demonstration profiles**; the illustrative table is a structure example, **not an expected fixed fixture dataset**.

## 8. Scheduling design — not enabled by CP1–CP3

Keep personalized and strategic scheduling separate despite shared provider infrastructure:

| Email | Scheduled behavior when independently approved |
| --- | --- |
| Motivational midday | 12:00 p.m. local for an enabled user on an applicable workday, with completed activities; no empty or invented report. |
| Motivational end of work | **20 minutes after valid `End Work`**; postpone/cancel pending send if work resumes, without changing workday state; daily/week counts based on existing authoritative records. |
| Strategic midday | **12:00 p.m. reporting timezone**, once per eligible manager's reporting day; no requirement that the manager start a work session. |
| Strategic end of day | **ONE consolidated email** per enabled manager / operational day: **20 minutes after reliably verified closure of their authorized active reporting team**, **OR** at an administratively configurable **maximum local reporting time**, **whichever comes first**. If team completion is uncertain, wait until cutoff rather than sending prematurely. |

**Approved:** existence of a configurable maximum time and one consolidated strategic closing email. **Not approved/known:** the **actual clock time**, authoritative reporting timezone, full note disclosure, Monday/week-boundary rule and details of reliable workforce-completion evidence. **Do not hardcode `7:00 p.m.` merely because it was proposed in conversation.** Implement a validated configuration field where appropriate, but do not silently default/activate production scheduling until the PO chooses and approves the value.

Design CP4 to reuse existing `PlatformScheduler`/leader coordination (or explain a documented alternative if needed), durable idempotency per tenant/recipient/template/local business date, retries, revocation/eligibility rechecks, delivery logging and explicit skipped reasons. Handle multiple sessions, overnight days, DST, later starts and workdays accidentally left open. **A report cutoff must never auto-close a legitimate or forgotten session.** Never send twice because two application replicas or replays claim the same due event. If recipient scope changed at dispatch time, regenerate authorization or skip; do not send a stale report cache.

## 9. Tests required (automated and controlled real-world)

### 9.1 Test matrix — all five send cases

| Case | Preview/test rendering | Real-provider acceptance test | Receipt evidence | Negative/security case |
| --- | --- | --- | --- | --- |
| T0 Provider | Generic fixed test only | Admin-selected provider, no hidden fallback | Test mailbox receipt | Non-admin forbidden; unapproved destination denied |
| T1 Motivational noon | Saved template + fictional midday counts | Explicit test send | Test mailbox receipt | Cannot change recipient preference or send real activity |
| T2 Motivational closing | Saved template + fictional daily/weekly totals | Explicit test send | Test mailbox receipt | No `End Work` mutation, no duplicate quota consumption |
| T3 Strategic noon | Two fake people, each breakdown and notes | Explicit test send | Test mailbox receipt | Cannot inject forged subordinates or real notes |
| T4 Strategic closing | Two fake people, daily details, individual weekly totals **and final team weekly summary** | Explicit test send | Test mailbox receipt | No leak across tenants; no note exposure; no double counting in team totals |

Automated test cases must cover: invalid/missing provider; M365/SMTP backends vs console/memory; tests working independently with provider mocked; fallback status honesty; 403/401/422/429; configured mailbox only; audit and anti-spam concurrency across multiple instances; X-CER-Route-Test header; template token injection; invalid UTF-8/HTML and safe note rendering; templates persisted and restored; preferences OFF/default and independent; responsive Web; sender does not mutate production state.

For hierarchy/report computations validate CEO including authorized CEO→Sales branch; COO **excluding** CEO→Sales and other branches; RM restricted to own subtree; OSM/Supervisor only if real descendants/grants; role changes/transfers, cross-tenant and cyclic assignments; records in progress, across midnight/DST, missing cost/time, zero activities, duplicate activities, long notes and large teams. Cross-check expected metrics against the **same authoritative logic** underlying the existing UI's Activity breakdown, not against screenshot-only values. **For T4 test final Team Weekly Summary presence/position, category totals and unique-person/event de-duplication; sums must reconcile with the individual weekly blocks for the same scope and window.** Include a hierarchy with a regional manager who also appears as a person in the CEO report to prove no duplicate aggregation. Confirm the midday template never includes team weekly totals.

CP4, if later authorized, additionally requires simulated clock tests for midday/local dates, +20 delays, team completion certainty, maximum cutoff, no auto-end, postponement, retries/idempotency, DST and revocations; do not claim completion based solely on timer unit tests.

### 9.2 Operational real-mail verification (CER-owned secret configuration)

1. Verify target branch/PR and deployed build include T0–T4 controls. If missing, report deployment blocker; **local tests alone are not deployment proof**.
2. An authorized platform administrator configures the existing integration (`email` or approved fallback) via `Platform > Integrations & Settings` in the proper environment. **Never place keys in MD, source, chat, logs or screenshots.**
3. Run `Verify`: authentication/connectivity only. Distinguish `healthy`, `auth_failed`, `unreachable`, `not_applicable`.
4. Set/select a company-controlled **test inbox** as allowed test target; run T0 and then T1–T4, subject to rate limiting (wait between batches rather than bypass controls).
5. Check the real inbox (and spam), verify five distinct messages/body structures and safe `[TEST]` banners, and record **sanitized recipient-side confirmation**. An accepted provider response alone remains `PENDING DELIVERY VALIDATION`.
6. Verify SPF/DKIM/DMARC and M365 sender authorization if applicable. Record results without disclosing sensitive infrastructure data.
7. Keep **all automatic motivational/strategic sends OFF** throughout demonstration. A manually clicked test send is the only allowed real send until explicit GO.

## 10. Security, data model and APIs — minimum requirements

- No new Core business semantics: use existing provider/email infrastructure as cross-cutting service and keep strategic reporting/aggregation in the CER Route activity/reporting domain.
- Do not duplicate the Activity Breakdown calculations, user hierarchy or tenant identity; use existing service contracts. A module must not directly traverse another module's private storage when a canonical domain interface exists.
- Evolve the tenant-scoped templates and preferences model with new strategic types. Existing motivational templates/preferences and data **must be preserved** on migration. Default all new strategic subscriptions OFF; include rollback/upgrade strategy, unique keys and data integrity constraints where needed.
- Canonical user/manager IDs and tenant come from authenticated server context; target test inbox only from allowlist; no client-supplied tenant scope or arbitrary subordinate list is trusted.
- Enforce authorization server-side on GET, configuration mutation, preview, report generation and test-send; separate *edit settings*, *receive summary* and *read detailed notes* permissions. Test views with synthetic data do not grant real note read access.
- Provider secrets remain in encrypted Platform Settings / authorized runtime secret store. No plain credentials in API, audit events, fixtures, exception bodies or test artifacts.
- Audit template edits, preference changes, demo send attempts/results and (when approved) real report generation/dispatch. Store metadata, not full note payloads or rendered report bodies.
- Apply CSRF/session protections consistent with the current platform, output escaping/HTML-safe rendering, recipient/header validation and rate limits. Use timezone-aware timestamps with documented operational date/time decisions.
- API shapes and database table names are the implementer's responsibility within existing conventions; **do not build unnecessary new APIs** if existing `activityemails` endpoints can be safely extended. Document every new/changed endpoint, permission, event, table/index and migration in the handoff.

## 11. Acceptance criteria — independently verifiable

- **AC-01:** Current surfaces and branch are confirmed. No duplicate Mail module/provider, no changed approved mobile navigation.
- **AC-02:** Provider `Verify` and **Send Test Email** are separate, visible and secure on the existing integration UI; platform generic test restricted to approved mailbox and rate limit.
- **AC-03:** Both existing motivational templates remain intact and their **Send test** features work using the saved templates, synthetic values and shared test target rules.
- **AC-04:** Two distinct strategic templates can be previewed, edited, saved, restored and tested; their required `{{per_person_report}}` block cannot be removed.
- **AC-05:** Strategic recipients are eligible authorized existing users, with independent noon/end preferences OFF by default and no changes to motivational settings.
- **AC-06:** Strategic hierarchical contract yields one separate breakdown and activity list per authorized descendant, with CEO/COO/Sales and cross-tenant/role-scope restrictions verified server-side.
- **AC-07:** Midday cutoff, daily vs weekly summary, supported category counts/miles/durations/cost, pending status, overnight time and unavailable fields are rendered correctly without inventing metrics.
- **AC-07A (V1.1):** The strategic **closing** template contains exactly one mandatory `{{team_weekly_summary}}` block **after all individual summaries**; the final display has a dated team week-to-date period, unique active-person count, overall activities/miles/time (and estimated cost where supported), category totals and no duplicate people/events. Figures reconcile to the individual weekly sections. The strategic midday template has **no** such weekly team block.
- **AC-08:** All five test messages use deterministic fictitious data and are clearly marked `[TEST]`; no actual notes/PII exported in test path.
- **AC-09:** Tests only target server-approved destinations, enforce 401/403/422/429 as appropriate, apply shared durable rate limit, log safe audit metadata and never modify production user/workday/delivery state.
- **AC-10:** UI differentiates provider acceptance, console/memory-only capture and **real confirmed inbox receipt**; each is evidenced, not conflated.
- **AC-11:** No real free-form note disclosure, new scheduled delivery or subscribed live recipient before explicit GO on pending policies/clock/zone; front end accurately marks feature availability.
- **AC-12:** Test suites (unit/integration/E2E, responsive, regression, auth/tenant, migrations) run with reproducible results; existing regression debt separately documented, never hidden.
- **AC-13:** Implementation handoff includes repository paths, APIs, migrations, access grants, test logs, screenshots, branch/commit, actual deployment state and outstanding blockers.

**Important:** AC-10's **confirmed external reception** is marked `BLOCKED EXTERNAL CONFIGURATION` / `PENDING VALIDATION` until the administrator uses real keys and physically verifies the target mailbox; do not use mock proof to mark it green.

## 12. Checkpoints, authorization boundaries and handoffs

**Single instruction; short control cycles. Do not execute all CPs as an undifferentiated bulk sprint.**

| CP | Deliverable / acceptance gate | Authorization |
| --- | --- | --- |
| **MAIL-U01 / CP1** | Baseline reconciliation; integration `Verify` / T0 test UI/API hardening; ensure existing T1/T2 tests are merged/deployable; targeted automated and security tests. Handoff with real-mail checklist. | **Release now.** Requires owner/admin keys only for external inbox test. |
| **MAIL-U01 / CP2** | Strategic templates, isolated recipient toggles, safe preview; per-person hierarchy and Activity Breakdown/Details renderer, **mandatory final Team Weekly Summary for the closing report with de-duplicated aggregation**; permission/notes filtering; deterministic demo fixtures. No live sending. | **Release after CP1 review**; no production notes. |
| **MAIL-U01 / CP3** | T3/T4 `Send test` using existing provider/test-target infrastructure; five-case test matrix **including end-of-day team-weekly block and reconciliation tests**; evidence of 5 received tests where provider configured; responsive/regression/tenant and data tests. | **Release after CP2 review**. Test sends only. |
| **MAIL-U01 / CP4** | Live schedule/orchestration for motivational and strategic emails, dedupe/retry/history, temporal behavior and deployment gate. | **NOT AUTHORIZED** by this handoff. Requires explicit PO GO and resolution of all blockers in §13. |

At completion of **each** CP, deliver **one developer Markdown report** with: `AS-BUILT/CONFIRMED`, `COMPLETED`, `PARTIAL`, `BLOCKED`, `NOT IMPLEMENTED/GAP`, `PENDING VALIDATION`, `DEVIATION`, `UNAUTHORIZED DECISION`, `TECHNICAL DEBT`, `DECISION REQUIRED` as appropriate. For each criterion use **Expected → Implemented → Evidence → Gap → Impact**, include exact commands and test results, DB/API/UI changes, screenshots, branch/commit and release readiness. If a CP is blocked, finish what can be verified without unsafe assumptions and propose the next smallest controlled action.

## 13. Pending Product Owner decisions and GO/NO-GO

| Code | Pending decision | Effect |
| --- | --- | --- |
| **DP-CUTOFF** | Exact maximum **local clock time** for the strategic end-of-day consolidated report (mechanism **approved**, numeric time **not selected**). | **Blocks CP4 strategic end-of-day activation**, not CP2/CP3 synthetic tests. |
| **DP-NOTES** | Define which recorded activity notes are permitted in externally sent managerial emails, including sensitivity classification, retention/forwarding considerations and per-field read grants. | **Blocks all real free-text-note email delivery**. Synthetic notes and safe restricted placeholders allowed. |
| **DP-TIMEZONE** | Authoritative tenant/recipient reporting timezone; operational date for multi-zone users and DST. | Blocks live scheduling and date-accurate recipient reports until verified. |
| **DP-WEEK** | Monday vs other week start and business weekly boundary. | Blocks certification of live week-to-date totals; synthetic tests can assume an explicitly labeled fixture week. |
| **DP-TEAM** | Authoritative evidence that all expected team members have closed their day; if impossible, wait until approved cutoff. | Blocks early automatic send, not a simulated cutoff demonstration. |
| **DP-SCOPE** | Confirm that all *authorized descendants* (not only direct reports) are included; omit manager's own work by default. | Implement as documented recommendation with explicit flag in delivery report if repository constraints/PO interpretation differ; never broaden data grants to make it work. |
| **DP-DEPLOY** | Approve/complete target branch merge, provider keys, test mailbox and actual inbox reception. | Blocks declaring external real email sending verified. |

**GO for CP1:** immediate, subject to normal repo permissions. **GO for CP2–CP3:** following certified prior checkpoints, with demo data and the restrictions above. **NO-GO for unattended production email:** until actual provider reception, PO choices, permissions, privacy and scheduler acceptance are separately certified.

## 14. Do not change

- Approved personal motivation wording, cadence, recipients or low-detail privacy contract.
- Current CER Route UX navigation and supervisor flows (`My Route`, Activity execution, `End Work`, `Keep working`).
- Existing time/mileage/fuel computation, timestamp storage, `session_date`, authorized overnight work.
- CER ERP / CER Time modules, Core boundaries, personnel hierarchy without approved organizational change.
- Email provider outside narrowly necessary reuse/hardening, password reset flow or any unrelated message family.

**Expected developer response to this handoff:** acknowledge CP1 scope, inspect repo and existing pending branch, implement only the next controllable CP, and return evidence for certification before proceeding.
