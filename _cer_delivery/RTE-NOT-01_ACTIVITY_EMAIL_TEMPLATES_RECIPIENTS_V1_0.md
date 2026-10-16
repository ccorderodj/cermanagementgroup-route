# RTE-NOT-01 - Activity Email Configuration: Templates & Recipients

**Project:** CER Route  
**Version:** 1.0  
**Date:** 2026-10-15  
**Status:** Ready for developer assessment and implementation under the stated checkpoint scope  
**Owner:** CER Route Product Owner  
**Developer deliverable:** Implementation evidence in Markdown, plus screenshots/tests  

## 1. Context and approved decisions

CER Route will add two lightweight motivational emails addressed to selected application users. Their purpose is to recognize everyday effort and gently remind each person of the activities performed, **not** to grade performance, monitor movements, or expose everything recorded by the app.

**Confirmed by Product Owner:**

1. **Midday Motivation:** a motivational email at **12:00 p.m.** with a simple summary of the activities performed so far.
2. **End of Day Recognition:** an email **20 minutes after End Work** summarizing the completed day and the cumulative activity for the current week.
3. The message style and substance shown in section 6 of this document are approved as the default copy for both cases.
4. Delivery must be selectable **per CER Route user**; do not turn it on for every user by default.
5. Avoid message overload, rankings, judgmental language, detailed locations, travel history, mileage, fuel cost, sensitive operational details, and identifying customers/employees.
6. Preserve the existing `Start Work`, activity execution and `End Work` flows; do not change their behavior in this checkpoint.

**Proposed UI decision for this checkpoint (to implement unless existing navigation makes an equivalent location preferable):** a single admin area **Settings > Notifications > Activity Emails**, containing two tabs: **Templates** and **Recipients**. If a reusable Settings/Notifications location already exists, extend it rather than making a parallel navigation path. Any change to the meaning or breadth of these controls needs Product Owner approval.

**Not yet verified:** current menu architecture, notification/email provider, existing permission conventions, storage models and scheduling infrastructure. Perform a focused repository audit; do not assert that uninspected components exist or rebuild components already available.

## 2. Objective and functional boundary

Deliver an administrable, persisted configuration for: 

- Editing the **subject and body** of the two approved email templates.
- Previewing each template with **synthetic demo values** before saving.
- Restoring each template to its approved default text.
- Selecting which **existing CER Route users** are eligible for either/both emails.
- Maintaining tenant separation, server-side authorization and an auditable record of sensitive changes.

**This checkpoint is configuration only.** Real email dispatch, noon scheduler, delayed `End Work + 20 min` queue, live aggregation, email-provider integration and retry/deduplication are **out of scope** and must be delivered through a later explicitly authorized checkpoint, **RTE-NOT-02/03**. Do not claim this functionality is actively emailing people until the delivery engine has been built and validated.

## 3. Placement and interaction design

### 3.1 Navigation

Preferred administrative location:

`CER Route > Settings > Notifications > Activity Emails`

In this screen use two tabs, or the closest existing pattern:

| Tab | Purpose | Actions |
| --- | --- | --- |
| **Templates** | Maintain Midday Motivation and End of Day Recognition | Open template, edit subject/body, preview, save, restore default |
| **Recipients** | Select user recipients | Search/filter existing users, enable/disable Midday and End of Day independently |

Do **not** create an additional standalone business module, add a new mass-email tool, or duplicate the existing user directory. Reuse existing layout, responsive components, forms, toasts and user/tenant search.

### 3.2 Templates tab

Display two template cards/sections:

1. **Midday Motivation** - scheduled for 12:00 p.m. (future engine).
2. **End of Day Recognition** - scheduled for `End Work + 20 minutes` (future engine).

For each template:

- Clear editable **Subject** input and **Body** multiline field.
- Human-readable token help showing supported dynamic placeholders (section 5).
- **Preview** button using demo data only; distinguish demo from a real delivery.
- **Save changes** with success/error feedback, unsaved-changes warning and server validation.
- **Restore default** with an explicit confirmation before discarding customized text.
- Show who last modified the template and when, if the existing UI has a compatible metadata pattern.
- Copy remains in Spanish initially; no translation editor or WYSIWYG/HTML authoring requirement in V1.
- Prevent unintended edits to the second template when saving the first.

If the delivery engine is not yet active, show unobtrusive status text: **"Configuración guardada. Envío automático pendiente de habilitación."** Never label a saved template as "sent".

### 3.3 Recipients tab

Reuse the existing CER Route user directory or its supported user-selection component, with a row per eligible user:

| User | Email (read-only) | Midday | End of Day |
| --- | --- | --- | --- |
| Existing user | Email already maintained in their account | On/Off | On/Off |

Required behavior:

- Search/filter users by their existing identity fields; show only users the current administrator is authorized to manage.
- Toggle **Midday** and **End of Day** separately per user; default both to **OFF** until intentionally activated.
- Do not ask the admin to type a recipient email address; reuse the verified email associated with the existing user.
- If no valid/verified email is available, do not allow enablement; display a neutral reason and route the admin to the existing user-management workflow to correct it. Do not edit identity data from this screen.
- Handle inactive/disabled/deleted users according to the existing account rules: fail closed, no eligibility for future deliveries; retain appropriate audit records.
- Show empty/loading/error/saving states, and reliably reflect the persisted state after refresh.
- Any user-detail link/shortcut, if desired, must lead to **the same persisted settings**, not a duplicated set of toggles.
- No bulk enable-all action in this checkpoint.
- Display a concise explanation that this page configures future eligibility, not immediate email delivery.

### 3.4 Mobile and accessibility

Administrative setup may be optimized for Web, but must remain usable responsively: use stacked user cards rather than a horizontally overflowing table on narrow screens. Provide labeled switches, keyboard interaction, focus visibility, accessible errors and readable previews. Do not modify the supervisor's mobile workday flow.

## 4. Functional rules

**BR-01 - Two distinct templates.** Template types are `MIDDAY_MOTIVATION` and `END_OF_DAY_RECOGNITION`; labels are human readable. No arbitrary additional categories in this checkpoint.

**BR-02 - Tenant isolation.** Templates and recipient preferences belong to the authenticated tenant and must never appear across tenants, regardless of client-supplied identifiers.

**BR-03 - One canonical setting.** Each user has at most one recipient-preference record per tenant, with two independent booleans. No settings duplication across screens or modules.

**BR-04 - Explicit opt-in by admin.** For every existing and newly provisioned user, both switches start `false`; migrations must not inadvertently subscribe current users.

**BR-05 - Verified recipient identity.** Recipient email is derived from the user record, not persisted as a new editable free-text destination. At future send time the engine must re-check eligibility and the current approved address.

**BR-06 - Controlled content.** Allow editing the message text and its supported variables, but no GPS, route map, customer/employee name, employee identifiers, detailed timestamps, miles, MPG, fuel cost, rankings, scores, productivity KPIs or Outcome details as automatic template variables. Text entered by an administrator is subject to normal content review/governance, not a promise that all free text can be mechanically classified.

**BR-07 - Core summary presence.** Midday text must retain the `{{midday_activity_block}}` placeholder; End of Day text must retain `{{day_activity_block}}` and `{{week_activity_block}}`. Reject an update removing the required blocks with a clear field-level message. Other supported token(s) are optional.

**BR-08 - Reliable persistence.** Template edits and switch changes persist in the backend; no local-only or hardcoded frontend settings. Changes apply only to the same tenant.

**BR-09 - Restore is explicit.** Restoring a default updates only the selected tenant/template and is auditable; it does not reset recipient preferences.

**BR-10 - Schedule is informational in this checkpoint.** Fixed labels: noon and +20 minutes. Do not implement local browser timers or attach email sending to an API request handler.

**BR-11 - Future engine contract.** When implemented separately: one midday email per user per local working day when a workday exists; one end-of-day email after a valid End Work +20 minutes, deferring if work resumes before due time; no email on a day without an applicable workday; daily/weekly counts based on completed non-duplicated activities. Week begins Monday (working assumption requiring PO confirmation prior to the send engine). This rule does not authorize the engine now.

**BR-12 - No deceptive delivery state.** Saved/Enabled/Configured means only the settings are stored, not that a mail was sent or scheduled by this checkpoint.

## 5. Dynamic variables (allowlist)

The editor supports exactly the following allowlisted tokens for V1; later the sender/summary service will resolve them server-side:

| Token | Meaning | Availability |
| --- | --- | --- |
| `{{user_first_name}}` | Recipient's display first name (safe fallback: `colega`) | Both |
| `{{midday_activity_block}}` | Brief completed-activity breakdown up to midday; if none, a friendly no-count sentence | Midday only |
| `{{day_activity_block}}` | Brief completed-activity breakdown for the closed workday; if none, a neutral sentence | End of Day only |
| `{{week_activity_block}}` | Weekly cumulative count of completed activities, with brief general category wording | End of Day only |

- Use semantic category labels already supported by CER Route (e.g. client visit, recruiting, employee visit, operational tasks), not sensitive free-text destination or reference fields.
- Reject unknown variables, malformed token syntax, unsupported token/template combinations and attempts to insert executable HTML/script. Render escaping/sanitization server-side when mail sending is built; implement compatible validation now.
- Support UTF-8 characters and approved emojis without corrupting subject/body.
- Preview should show realistic **fictional** values, clearly marked `Ejemplo / Vista previa`.
- Do not use AI generation to produce or rewrite the messages in this checkpoint.

## 6. Approved default email copy (Spanish)

Use the following as editable **seed defaults**, not immutable hardcoded frontend text. Preserve the approved positive tone even as it becomes customizable. The sample metrics shown in earlier discussions have been replaced by safe dynamic placeholders.

### 6.1 MIDDAY_MOTIVATION

**Default subject:** `¡Buen trabajo! Sigamos adelante 💪`

**Default body:**

```text
¡Vas haciendo un gran trabajo!

Hola, {{user_first_name}}:

Ya estamos a mitad del día y queremos recordarte que cada actividad cuenta.

{{midday_activity_block}}

Cada visita, cada conversación y cada esfuerzo contribuyen a nuestros objetivos.

¡Continúa con esa energía y que tengas una excelente tarde!

CER Management Group
```

**Example rendered activity block when data exists:**

```text
Hasta ahora has realizado:
- 2 visitas a clientes.
- 1 actividad de reclutamiento.
- 1 gestión de seguimiento.
```

If no completed activities exist, do not fabricate accomplishments. Show a brief motivational alternative without numeric statistics.

### 6.2 END_OF_DAY_RECOGNITION

**Default subject:** `¡Jornada finalizada! Este es tu avance de hoy 🌟`

**Default body:**

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

**Example rendered blocks (demo data only):**

```text
Tu día en resumen:
- 3 visitas.
- 2 gestiones.
- 1 actividad de reclutamiento.

Tu semana hasta hoy:
18 actividades realizadas durante la semana en visitas, reclutamiento y gestiones operativas.
```

These samples must be explicitly identified as examples. Never show demo counts as real user data.

## 7. Use cases and exception handling

**UC-01 - Edit midday or end-of-day message**

1. Authorized administrator opens Settings > Notifications > Activity Emails > Templates.
2. Opens one template, edits subject/body and requests a preview with fictional data.
3. Client and server validate content, including its required block(s).
4. Administrator saves; the tenant-specific template is persisted and a change audit is recorded.
5. A refresh or a different authorized admin session sees the saved version.

**Exceptions:** invalid placeholder, missing required block, blank subject/body, concurrent modification, permission denied, save failure. Do not silently overwrite a more recent edit: apply the repository's existing concurrency convention or an equivalent conflict check.

**UC-02 - Restore original template**

1. Administrator clicks Restore default for one template.
2. Confirmation identifies the template affected.
3. Only that template is restored and auditable; unrelated template/recipient settings remain intact.

**UC-03 - Enable one recipient**

1. Administrator opens Recipients, searches an existing user within their management scope.
2. Enables Midday and/or End of Day.
3. Server verifies permissions, tenant, user status and email eligibility.
4. Setting persists and appears correctly after reloading.
5. Interface states that delivery automation belongs to a subsequent checkpoint.

**Exceptions:** user belongs to another tenant, outside management scope, disabled, email missing/unverified, stale state, network failure, unauthorized update.

**UC-04 - Disable one recipient**

- Administrator switches off one or both message types; preserve the unaffected setting.
- A disable change is audited. The future send engine must re-check eligibility before dispatch, so disablement wins over a pending message.

## 8. Security, roles and audit

- Reuse existing CER Route identity, RBAC, tenant and hierarchical user scope. **Do not assign permission by role name alone**, and do not assume every supervisor may view/edit these settings.
- Evaluate/reuse existing manage-notification/configuration permission. If unavailable, propose one narrowly scoped capability and document its mapping; do not broaden current roles without authorization.
- Enforce all permissions and recipient-management scope **server-side** on read, create, update, preview and reset endpoints. Avoid trusting filtered frontend lists or arbitrary `tenant_id` values.
- Protect data at rest and in transit according to the app's existing practices. Do not expose other tenants' users, email addresses or templates in errors or search.
- Audit: actor, tenant, target user/template, operation, timestamp, old/new values or safe diffs as appropriate, and outcome. Keep access to audit records permission-controlled; avoid logging full email bodies or personal information in regular application logs.
- Avoid HTML injection, email header injection, arbitrary web links and unsafe template evaluation. Only safe, explicit token substitution is allowed.
- New records, queries, unique constraints and migrations must respect multi-tenancy, referential integrity and deletion/account-deactivation policy.

## 9. Data and API contracts (behavioral, not prescriptive implementation)

**Configuration entities / persistence needs:**

- **Tenant message template**: tenant reference, template type, subject, body, version/concurrency marker, timestamps and editor identity. Uniqueness per `(tenant, template_type)`.
- **Per-user activity email preference**: tenant reference, user reference, `midday_enabled`, `end_of_day_enabled`, timestamps and editor identity. Uniqueness per `(tenant, user)`. Defaults both `false`.
- Reuse existing audit mechanism rather than introducing a second audit subsystem.

**Required application contracts** (reuse existing endpoints/service naming patterns):

1. Read both templates for current tenant.
2. Update a single template, validating mandatory tokens and permission.
3. Restore a single template's approved default.
4. Preview a template with synthetic data and no mail send.
5. List eligible/manageable users and current two-switch preferences, with pagination/search if appropriate.
6. Change one user's notification preferences without touching their account profile or the other user's preferences.

Do not expose unrestricted list/update endpoints across all tenants. The exact table names, endpoint paths, request schema and migration tooling are implementation choices to be documented after assessing the repository.

## 10. Scope boundaries / do not change

- Do not implement **real sending, scheduling, time-zone automation, workday listeners, live aggregation or retry queues** in this checkpoint.
- Do not change `End Work`, activity state machine, route capture, GPS, official mileage, fuel calculation or workday restoration.
- Do not add client/customer catalogs, employee-identity details, arbitrary recipient emails, third-party mailing-list integration, AI writing, promotional campaigns or analytics dashboards.
- Do not copy CER ERP notification logic or introduce cross-app coupling; CER Route remains deployable independently.
- Do not introduce a provider-specific dependency if CER Route already has a reusable mail abstraction.
- Do not silently enable users during migration or seed install.

## 11. Acceptance criteria

| ID | Criterion | Evidence expected |
| --- | --- | --- |
| AC-01 | Authorized admin sees an Activity Emails area with Templates and Recipients | Web screenshots, navigation test |
| AC-02 | Both editable templates are initialized with the approved default subjects/bodies | Database/API assertion, screenshots |
| AC-03 | Edits persist and remain tenant-specific after refresh | API/DB tests |
| AC-04 | Preview is clearly sample-only, resolves permitted tokens and never sends a message | UI + service test |
| AC-05 | Invalid/unknown tokens and missing required activity blocks are rejected | Validation tests |
| AC-06 | Restore default requires confirmation and affects only selected template | UI + audit test |
| AC-07 | Eligible users appear only within actor's authorized tenant/scope | Authorization tests |
| AC-08 | Midday and End of Day toggles are independent; both are off by default | Persistence/migration tests |
| AC-09 | User without valid email cannot be enabled; disabled users cannot receive future eligibility | Negative tests |
| AC-10 | Every template/preference update is audited; unauthorized access denied by backend | Audit + HTTP tests |
| AC-11 | Mobile/responsive screen and accessibility basics pass | Responsive screenshots / smoke tests |
| AC-12 | Existing workday/end-work flows are not changed; no real email is dispatched by this checkpoint | Regression tests and diff |
| AC-13 | Concurrent edits are handled without silent data loss | Conflict test |
| AC-14 | UI communicates configuration-only status until dispatch infrastructure exists | Screenshots |

## 12. Tests required

- Unit: template validation, allowlist, mandatory blocks, restore defaults, default-off preference logic.
- Integration: tenant-specific CRUD, user scope, persistence, no cross-tenant leakage, existing-account email eligibility, update isolation, audit events, conflict handling.
- Negative/security: cross-tenant reads/updates, scope bypass, forged tenant/user IDs, XSS/script/template injection, unsupported variables, unauthorized preview/reset, inactive users.
- UI: edit-save-refresh, preview with demo values, restore confirmation, search recipients, independent toggles, no-email disabled state, empty/error/loading states and mobile layout.
- Regression: existing user management, permission resolution, `Start Work`, Activity and `End Work` unaffected.
- Verify migration/seed idempotence and that all pre-existing users remain unsubscribed.

## 13. Developer checkpoints and required handoff

**CP-01 - Reuse audit and contract mapping**

- Identify actual Settings/Notifications navigation, user listing, permissions, email verification behavior, backend audit service, migration conventions and any notification/email abstractions.
- State exact components being reused and any conflict with this proposed placement. Do not expand scope silently.

**CP-02 - Templates configuration**

- Implement tenant-specific template persistence, approved seeds, UI editor, token validation, safe preview, restore and audit.

**CP-03 - Recipient configuration**

- Implement user selection/search and two independent persisted toggles, permission/scope controls and negative states.

**CP-04 - Validation and handoff**

- Complete tests, responsive screenshots, migration checks and regression review. Submit technical MD with evidence and actual implementation details.

**Required handoff MD:**

1. Implemented scope and **Completed / Partial / Blocked** per checkpoint.
2. Files/components changed, actual API contracts, data model/migrations, permissions and audits.
3. Expected vs implemented vs evidence vs gaps; screenshots of Templates and Recipients.
4. Tests executed with commands, counts and results (and any failures/limitations).
5. Commit SHA, branch/PR, known debt, deviations, unauthorized decisions (if any).
6. Explicit statement that email dispatch is **not yet implemented** in this checkpoint unless separately authorized and evidenced.
7. Technical prerequisites and recommendation for the subsequent email-sending checkpoint.

## 14. Pending Product Owner decisions (do not infer silently)

- **DP-01 - Exact administrative location:** preferred Settings > Notifications > Activity Emails; if the current IA differs, use the most coherent existing equivalent and show the resulting placement in the handoff.
- **DP-02 - Time-zone source:** resolve before shipping the send engine; fixed 12:00 p.m. means the intended user's applicable local time, not the web server clock.
- **DP-03 - Week boundary:** Monday is a working assumption for the future week-to-date summary; confirm before implementing accumulation.
- **DP-04 - End-user opt-out/self-service:** this checkpoint requires administrator-controlled enrollment only. Any end-user preference feature should be separately reviewed rather than assumed.

**Release boundary:** The two screens and their persisted settings can be certified as configuration-ready. The overall motivational email feature **cannot** be certified as operational until scheduled dispatch, aggregation, eligibility re-check, duplicate prevention, safety tests and real delivery evidence pass in subsequent checkpoints.
