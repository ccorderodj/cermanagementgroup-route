# Development Workflow

This is the working discipline carried over from the CER Staffing project. Following it is part of using this foundation: it is what kept a multi-tenant system with sensitive data auditable while it changed every day.

## 1. Source authority

1. **The code is the source of truth.** Documents, plans, closure reports and earlier summaries are pointers. When a document and the code disagree, the code wins and the document gets fixed in the same change.
2. **Requirements come from the business owner in writing.** Implement the instruction as written. When it is ambiguous or conflicts with the approved target, stop and ask; do not silently reinterpret it. When a decision is needed, record it as a question with the evidence behind it.
3. **Evidence over assertion.** "It works" means a command was run and its real output was observed. "Not verified" is always said explicitly. A report never claims a test, build or browser result that was not produced.
4. **One branch per delivery.**
   - Each delivery gets a single branch, up to date with the integration branch (`dev`), and a single merge request.
   - No intermediate or stacked branches.
   - The integration branch is merged by its owner.
5. **Clean checkout builds.**
   - Anything a build or test needs must be tracked in git: code, lockfiles, migrations, templates.
   - A change is not done until it works from a fresh clone: `uv sync --frozen`, `npm ci`, `alembic upgrade head` on an empty database, `pytest`, `typecheck`, `lint:ts`, `build:prod`.
   - `tests/test_frontend_source_completeness.py` fails when a relative import resolves to an untracked file.
   - Review `git status` in full before committing, not only the folder you worked in.

## 2. Architecture conventions

- **Modular monolith, API-first, integration-ready.** Modules talk through their public services and DAOs inside one application. Applications talk through `/api/v1` and webhooks.
- **Domain ownership.**
  - Every canonical record has exactly one owning module (inside an app) and one owning application (across apps).
  - Other modules and applications **reference** it by id or **consume** it through the API or an event.
- **No duplicate canonical persistence.**
  - A second table holding the same fact as another is not a cache; it is a second truth that will drift.
  - If a screen needs a value that another module owns, read it from its owner.
  - Frozen **snapshots** (evidence of what was seen at a moment) are allowed only when they are explicitly immutable and named as snapshots.
- **Evidence is append-only.** History, audit and signed or approved facts are never updated in place. A correction is a new row that references the old one, and the database enforces it with triggers.
- **Server decides.** Tenant, actor, time, permissions and derived states are computed on the server. The frontend shows them; it never supplies them.

## 3. Backend conventions

- **Module layout.** A module lives in `app/routers_api/<module>/` with `router.py`, `schemas.py`, `models.py`, `dao.py`, and `service.py` or `dependencies.py` when needed.
- **Handlers.** Keep handlers thin (request → schema → service/DAO → response). Declare explicit input and output schemas, with `extra="forbid"` on write payloads.
- **Every endpoint declares** its tenant (`Depends(get_company_required)`) and its authorization (`require_permissions([...])` or `require_platform_admin`).
- **Transactions.** Writes that touch more than one table run inside `async with transaction():`. The audit event is written in the same transaction.
- **Status codes.**

  | Code | Meaning |
  |---|---|
  | 401 | No session |
  | 403 | Missing capability |
  | 404 | Missing, or belongs to another tenant |
  | 409 | Conflict: stale version, state that forbids the action, duplicate |
  | 422 | Validation or business objection. Return every objection at once, with the field it belongs to. |

- **Business states.** Use `BusinessEnum` with a `CHECK` constraint. Transitions are explicit maps, and actions that need preconditions are dedicated endpoints, never a generic status change.
- **Capabilities.** Declare the capability in `app/core/rbac/catalog.py`, grant it in `DEFAULT_ROLES`, seed it with `python -m app.db.scripts.bootstrap`, and keep `tests/test_permission_catalog.py` green.

## 4. Frontend conventions

- **Page-key chain.** Route `name=` = `ComponentRoot` value = `RootComponents` key = `pages/<Key>` folder. Run `tests/test_page_wiring.py` after adding a page.
- **Redux.** The store holds the state of entities; panels dispatch thunks and read selectors. Thunks live in `entities/<Entity>/model/services`, and the three pagination thunks share one file.
- **Axios.** There is exactly one HTTP client (`shared/api`). Do not add RTK Query or `fetch`.
- **Zod.**
  - Every response is parsed with `parseApi(schema, response.data, 'thunkName')`.
  - Types come from `z.infer` of that schema.
  - `api.get<T>()` is not validation.
- **UI.** Use shadcn primitives from `shared/ui/shadcn/new-york` and the design tokens (never raw `slate-*` or hex). Tables use `features/Common` `DataTable` with a mobile card variant where the page is used on phones. The frontend has no dark mode.
- **Permissions in the UI** only hide what the server would refuse anyway.
- **Builds.** Browser verification uses `npm run build:dev`, which keeps `data-testid` attributes. Release uses `npm run build:prod`.

## 5. Migration discipline

1. **Every schema change is an Alembic revision.** Generate it with `revision --autogenerate`, then **review it**. Autogenerate does not infer triggers or functions and can get partial or composite constructs wrong.
2. **Single head.** `alembic heads` returns one revision. `alembic check` must report "No new upgrade operations detected".
3. **Downgrade.** Implement `downgrade` whenever the change is reasonably reversible.
4. **Transforming existing data** is part of the migration:
   - document the mapping in the migration docstring;
   - preserve what cannot be converted, for example as an evidence note or a kept column;
   - validate against synthetic legacy rows before merging.
5. **Destructive steps** (dropping columns or tables with data) go in a later revision after a compatibility period, never in the same change that introduces the replacement.
6. **No `DROP SCHEMA`** in migrations, and no manual schema edits in any environment.
7. **Before deploying**, the migration runs before the new code serves traffic. The deploy notes say so when old and new code cannot share a schema.

## 6. Testing discipline

- **Real database.** Integration tests run against real PostgreSQL. The suite rebuilds the schema through `alembic upgrade head` (not `create_all`), so a broken migration fails the suite.
- **Test database.** Set `MODE=TEST` with a `TEST_DATABASE_URL` distinct from the development database; startup refuses the same URL.
- **One process at a time.** Never run two `pytest` processes against the same test database: they drop each other's schema.
- **What to test.**
  - Every rule enforced by the database has a test proving the database rejects the bad write, not only that Python validates.
  - Every endpoint that changes state has authorization tests (allowed role, denied role, other tenant).
- **Scope while iterating.** Run the tests of the files you touched. Run the full suite before the delivery report.
- **Browser verification** is required for UI deliveries: the real flow at desktop width and around 390 px, with screenshots kept as evidence and the checks listed in the report. Emulated widths are not physical devices; say which was used.

## 7. Delivery and implementation reports

Every delivery ends with a Markdown report addressed to the business owner. It contains:

1. **Classification of the request** before any code is changed: defect, requirement gap, new scope or needs decision, with the cause found in the code.
2. **Implementation summary:** what changed, the components reused, the files and domains affected, and migrations.
3. **Resulting flow:** the end-to-end behaviour now implemented.
4. **Technical decisions,** separated into *required by the business* and *technical choice*.
5. **Data treatment:** legacy data mapping and migration results.
6. **Validation evidence:**
   - exact commands;
   - real results, meaning pass counts and failures;
   - migration validation;
   - browser checks with screenshot names;
   - anything **not** run.
7. **Deviations and pending validation:** each acceptance criterion classified *Completed / Partial / Blocked / Pending Validation*, with the reason.
8. **Deploy notes:** migrations, configuration and ordering.

The next checkpoint is never started automatically: the report goes back for validation first.
