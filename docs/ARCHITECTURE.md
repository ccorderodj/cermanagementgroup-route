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
| Permission change control | Maker-checker in `rolepermissionsapprovals` (requester cannot approve their own request) |

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
- **No row-level data scope beyond the tenant.** It is not built in; a domain that needs it designs it explicitly ([DOMAIN_EXTENSION_GUIDE.md](DOMAIN_EXTENSION_GUIDE.md)).
