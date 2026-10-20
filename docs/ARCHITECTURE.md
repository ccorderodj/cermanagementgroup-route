# Architecture

This foundation is the platform layer of a CER application: everything a bounded-domain application needs *except* the domain. It was extracted from the CER Staffing application, where every piece below ran in production.

The target landscape is **several small modular monoliths**, each owning one bounded domain. They integrate only through versioned REST APIs and signed webhooks in both directions ([INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)).

## 1. Runtime composition

`app/main.py` composes three ASGI applications:

```text
app (root)   CorrelationId → AuditRequestContext → SecurityHeaders → TrustedHost → CORS → GZip → CompanyResolver
 ├── /health, /health/ready     liveness/readiness, no tenant
 ├── /metrics                   Prometheus (ENABLE_METRICS), no tenant
 ├── /api                       JSON API        CSRF → Exception → query profiler
 │    ├── api_router            private: Depends(get_current_user) at router level
 │    ├── api_router_public     /public/*: explicit per-endpoint whitelist (login, logout, password reset)
 │    └── integration router    /v1/*: app-to-app contract, signature-authenticated
 └── /                          pages + /static    Auth → LoggedIn → App middleware
```

Mount order matters: `/api` is mounted before `/`, because `Mount("")` captures everything else.

## 2. Tenancy

- **Tenant resolution.** A tenant is a `company`, resolved from the request host `<subdomain>.<BASE_DOMAIN>` by `CompanyResolverMiddleware` (60 s cache). Without a valid subdomain every page and API returns 404, except `/health*` and `/metrics`.
- **Tenant-owned data.** Tenant tables carry `company_id`. Composite foreign keys `(id, company_id)` stop one tenant's row from pointing at another tenant's row.
- **Query filtering.** DAOs filter by `company_id` explicitly; there is no automatic filter and no row-level security. Every endpoint takes the company from `Depends(get_company_required)`, never from the request body.
- **Cross-tenant access** returns **404, not 403**. The existence of another tenant's record is never confirmed.
- **Global data.** The capability catalog and `region` (US states) are global. Roles, memberships and operating states belong to a tenant.

## 3. Identity, authentication and authorization

| Concept | Implementation |
|---|---|
| User | `user` (global identity, argon2id password, `is_superuser` platform flag) |
| Membership | `user_company` — one active role per user per company |
| Role | `role` per company, created from templates `owner`, `admin`, `manager`, `viewer` (`app/core/rbac/catalog.py`) |
| Capability | `permission` rows seeded from `CAPABILITIES` (`module.action`) |
| Session | JWT (HS256) in HttpOnly cookie `cer_access_token`; CSRF double submit with `cer_csrf_token` + `X-CSRF-Token` |
| Page authorization | `require_page_permissions([...])` on the page route |
| API authorization | `require_permissions([...])` / `has_permissions` — grants re-read from the database on every request |
| Platform boundary | `require_platform_admin` (`is_superuser`); never grantable by a tenant |
| Permission change control | Maker-checker in `rolepermissionsapprovals` (requester cannot approve their own request). The platform superadmin (`is_superuser`) is above it: their change applies immediately, recorded as an approved request plus an `audit_event` (`apply_direct`) |

Some rules are enforced by tests:

- **Catalog ↔ code** (`tests/test_permission_catalog.py`): every capability used in code is in the catalog, and every catalog entry is used.
- **Unauthenticated surface** (`tests/test_public_surface.py`): the set of endpoints and pages served without a session is a closed list.
- **Frontend permission checks** (`hasUserPermission`) are UX only. The backend is the gate.

## 4. Data layer

- **Database stack.** SQLAlchemy 2 async over asyncpg, and PostgreSQL 14+. SQLite is not supported: the schema relies on partial unique indexes, JSONB, composite foreign keys and `timestamptz`.
- **DAO per module.** Each module has a DAO. `BaseDAO.query()` plus `paginate()` implement pagination, which is 1-based on the server.
- **Transactions.** `transaction()` opens an ambient transaction. Nested DAO calls join it: their `commit()` becomes part of the outer unit of work.
- **Optimistic concurrency.** `VersionedMixin.version` plus `ensure_version()` answer **409** with `X-Current-Version` instead of overwriting.
- **Business states.** `BusinessEnum` generates the `CHECK` constraint from the Python enum, so the code and the database cannot disagree.
- **Append-only tables.** A trigger rejects `UPDATE`, `DELETE` and `TRUNCATE` on `audit_event`, `integration_event`, `platform_audit_event` and `platform_health_check_run`. `app/core/platform/integrity.py` verifies the triggers live from Diagnostics.
- **Migrations.** Alembic keeps a single linear history starting at `0001_foundation`, the clean baseline of this foundation. Domain applications add revisions on top.

## 5. Cross-cutting services (`app/core`)

| Package | Responsibility |
|---|---|
| `audit/` | `record_event()` into `audit_event` with request id, IP, user agent and actor role; joins the business transaction |
| `security/` | cookies, CSRF, in-process rate limiter |
| `middleware/` | tenant resolver, auth, security headers (strict CSP in PROD), exceptions, gzip, CORS |
| `exceptions/` | page error handlers (403/404 HTML) and API errors (`{detail, error_id}`) |
| `platform/` | encrypted secrets (AES-256-GCM, master key in env), integration settings, policies, diagnostics, production-readiness gates, scheduler with leader election |
| `storage/` | storage provider interface (local for development, S3-compatible), upload validation, malware scanner adapters (ClamAV, Cloudmersive) with fail-closed quarantine |
| `email/` | console/memory/SMTP/M365 backends with fallback |
| `integration/` | `/api/v1`, inbound/outbound webhooks, HMAC signatures, idempotency, integration event metadata |
| `identity.py` | project identity (`APP_*`) for templates and the frontend |

## 6. Frontend

**Page rendering.** There is no client-side router. Every page follows one chain:

```text
FastAPI route  name="SecurityUsersPage"
  → Jinja template  <div id="rc-currentPage" data-current-page="{{ url_name }}">
  → ComponentRoot enum value 'SecurityUsersPage'      (maincontent.ts)
  → RootComponents['SecurityUsersPage']               (mainContentConfig.tsx)
  → pages/SecurityUsersPage/ui/SecurityUsersPage.tsx
```

If any link in that chain disagrees, the page renders blank without an error. `tests/test_page_wiring.py` compares all four sources.

**Layers** (`app/components/react`):

| Layer | Contents |
|---|---|
| `app/` | providers: store, user and app context, main content, navigation |
| `entities/` | Zod schemas, types, Redux slices, thunks per business entity |
| `features/` | user-facing panels, forms and dialogs |
| `pages/` | one folder per page key, lazily loaded |
| `widgets/` | layout (`AppTopbar`), sidebar, page loader |
| `shared/` | Axios client (`shared/api`), `parseApi`/Zod validation, shadcn/Radix UI kit, hooks, utilities, design tokens |

**Data flow.**

- Panels never call endpoints. They dispatch thunks and read selectors.
- Thunks use the single Axios instance, which adds the CSRF header and redirects to `/login` on 401.
- Responses are validated with `parseApi(schema, data, label)`: a contract break fails at the call, not three screens later.

**Navigation.** `navigation.ts` declares two menus:

- `businessNavigation`, the sidebar. It is empty in the foundation; domain modules add their groups.
- `administrationNavigation`, the account menu: Organization, Access control, Platform.

Both menus are filtered by the same `useVisibleNavigation` hook. The authenticated landing page (`AdminPage`) builds its cards from `businessNavigation`.

**Identity and branding.**

- The `app_data` cookie (set by `AppMiddleware`) carries the tenant branding plus the project identity (`app_title`, `brand_label`, `logo_path`, `environment_label`, `default_path`).
- A tenant's own logo and colors from Company Profile override the project defaults.

## 7. Retained application surface

| Area | Pages | API |
|---|---|---|
| Access | Login, Password reset, Change password | `/api/public/auth/*` |
| Account | Admin landing, My Profile | `/api/auth/profile` |
| Organization | Company Profile, Operating States, Companies (platform) | `/api/companies/*`, `/api/regions/*` |
| Access control | Users, Roles & Permissions, Permissions, Permission Requests | `/api/users/*`, `/api/roles/*`, `/api/permissions/*`, `/api/rolepermissions*` |
| Platform | Integrations & Settings, Diagnostics | `/api/platform/*` |
| Integration | *(API only)* | `/api/integrations/*` (tenant admin), `/api/v1/*` (contract) |

## 8. What is deliberately absent

- **No business domain.** The Staffing domains (clients, CIR, OAP, job openings, recruitment, forms, onboarding, binder, I-9, E-Verify, workforce) were removed; see `EXTRACTION_REPORT.md`.
- **No messaging infrastructure.** There is no event bus, message broker, or generic integration platform. Webhooks plus REST are the integration contract.
- **One external origin, for map tiles only.** The Activity Admin route viewer (`View Route`) loads Leaflet on demand and draws raster tiles from `MAP_TILE_URL` (OpenStreetMap by default, best-effort; switchable to another provider by configuration). The CSP opens that origin in `img-src` and nowhere else. The viewer shows the **points used to calculate the mileage** (start, plan changes, arrival) as numbered markers, never a line: the mileage request asks TomTom for the distance only, so no road geometry exists. It requires `route.activity.read` + `route.activity.map.read`, an on-demand capability that no role template grants (`CAPACIDADES_A_DEMANDA`), and the trip must be in the viewer's hierarchy scope.
- **No email dispatch for activity emails (yet).** CER Route → Configuration → Activity Emails (RTE-NOT-01, `/api/activity-emails/*`) only **stores** configuration: the two approved templates (`midday_motivation`, `end_of_day_recognition`; approved text in `activityemails/content.py`, a row exists only once a tenant customizes one) and per-user eligibility (`activity_email_preference`, both switches off by default, composite FK to `user_company`). Recipients are members whose role grants `route.worksession.execute`, narrowed by the hierarchy delegation; the address always comes from the user account. Templates are plain text with an allowlist of `{{tokens}}`; HTML, links and unknown tokens are rejected. Everything requires `route.activityemails.manage`, an on-demand capability (`CAPACIDADES_A_DEMANDA`). The scheduler, aggregation and sending are RTE-NOT-02/03 and must re-check eligibility at send time, and must **not send** when the person has no completed activities (PO decision, 16-10-2026; `TemplateSpec.send_condition`). The only sends today are **controlled tests**, sharing one policy (`app/core/email/politica_de_prueba.py`, RTE-MAIL-UNIFIED-01 CP1): the provider test in Platform › Integrations & Settings (T0, platform admins, the selected provider only, never the fallback) and the template tests in Activity Emails (T1/T2, saved template with fictional data). Template tests go only to the actor's own address or `MAIL_TEST_RECIPIENTS`; the provider test (T0) lets a platform admin type one validated address (V1.2). All tests carry `[TEST]` once, a banner and the `X-CER-Route-Test` header, and draw on **one** budget of 5 per actor per 15 minutes, reserved before sending in `mail_test_send` under a per-actor PostgreSQL advisory lock (correct across replicas). Every conversation with the provider is bounded (25 s in total, 10 s for the Microsoft Entra token, 5 s per server address) and a failure names its step (`token_timeout`, `token_refused`, `smtp_timeout`, `smtp_auth_rejected`, `smtp_send_rejected`…) with a fixed message, never the provider's text. Results are `accepted_by_provider`, `not_sent_development_backend`, `captured_by_test_backend`, `not_configured`, `failed_auth` or `failed_unreachable`; never "delivered".
- **Strategic Activity Reports (configuration and test only).** Activity Emails also holds two manager reports (`strategic_midday_report`, `strategic_end_of_day_report`, RTE-MAIL-UNIFIED-01 V1.2) and per-manager switches (`strategic_*_enabled` on `activity_email_preference`, off by default, managers = CEO/COO/RM with a current position and a team). `activityemails/strategic.py` builds one block per authorized person (scope from `organization.scope.alcance_administrativo`, numbers from `reports.dao.hechos` / `reports.service._metricas`, the manager excluded) and, only in the closing report and after every person, one Team Weekly Summary that is the sum of the individual blocks. **Real activity notes are never emailed** (`nota_para_correo`) until DP-NOTES is approved; previews and tests use fixed fictional data. Day, cutoff and week start are passed by the caller (DP-TIMEZONE/DP-CUTOFF/DP-WEEK pending); nothing is scheduled.
- **Real activity-email sending (RTE-MAIL-CP4), off by default.** One dispatcher (`activityemails/delivery.py`) and one ledger (`activity_email_delivery`, unique per tenant/recipient/type/operational day) serve three triggers: the in-app `PlatformScheduler` every minute (precision), a DigitalOcean Scheduled Job every 15 min running `python -m app.routers_api.activityemails.jobs --once` (reconciliation), and the manual **Send now** in Activity Emails (`/api/activity-emails/reports/*`, capabilities `route.activityemails.preview` and `.send`, on demand; resending an email that already went out is **Resend**, gated only by `.resend` and numbered in `activity_email_resend`). `real_reports.generar` builds the four emails with real data and the saved templates (noon cutoff in the recipient's zone, end of day 20 min after the last close, strategic close when the whole team closed or at `MAIL_STRATEGIC_CUTOFF`). Nothing is sent unless `MAIL_REAL_SEND_TYPES` lists the type, the recipient's switch is on and, for automation, `MAIL_AUTOMATION_ENABLED=true` with `MAIL_AUTOMATION_DRY_RUN=false`. See `docs/MAIL_DISPATCH_RUNBOOK.md`.
- **No row-level data scope beyond the tenant.** It is not built in; a domain that needs it designs it explicitly ([DOMAIN_EXTENSION_GUIDE.md](DOMAIN_EXTENSION_GUIDE.md)).
  CER Route does, in `app/routers_api/organization/` (person → person `org_assignment`, history by period):
  - The hierarchy changes **only** through CER Route → Users (`/api/route/users`, `/api/route/organization`). The general contract (`/api/users`) answers **409** `managed_in_cer_route` to any role change of someone in the hierarchy, to a hierarchy role for anyone, and to `superior_user_id` (`contract_guard.py`).
  - **One current CEO per tenant**, guaranteed by the partial unique index `uq_org_assignment_one_ceo` (migration 0019).
  - CER Route role names are a contract (position and scope derive from them): Roles & Permissions answers 409 to renaming or deleting them.
  - Retire a manager (direct reports move up to their superior) and replace a manager (the successor takes position and team) are single-transaction operations restricted to `route_admin` (`succession.py`); suspension is a temporary absence and keeps the structure.
  - **CEO and COO change only through “Replace manager”**: editing their role or superior, or making someone CEO/COO from the role list, answers 409 `use_replace_manager`. Creating the first CEO or a new COO stays in the create form.
  - **History follows the position** (`scope.py`): a successor inherits what the predecessor saw (`org_assignment.replaces_user_id`, migration 0020); each person's first assignment covers their past (initial load); lateral moves (e.g. a supervisor between Regional Managers) stay by period, so no zone sees another's history.
  - **The CEO sees everything, without time** (V1.6): the whole hierarchy's history, including people who already left (up to their last assignment). Time + relation applies from COO down.
  - **A manager (CEO, COO, RM) is never emptied by hand**: moving their last direct report elsewhere (or out of the tree) answers 409 `manager_left_without_team`; the team changes leader through “Replace manager” and a position closes through “Retire manager”. Replacing can keep the outgoing person in the company with a lower role.
