# Domain Extension Guide

How to build a bounded-domain CER application on top of this foundation without damaging it. The running example is a module `workorders` with entity `WorkOrder`; replace the names with your own.

## 0. Before writing code

1. **Name the domain and its owner.**
   - Which canonical records does this application own?
   - Which does it only reference, and from which other application?
   - Write this in the application README.
2. **Identify cross-application facts.**
   - What must other applications learn from you (outbound events)?
   - What must you learn from them (inbound events or API calls)?
   - These become your `/api/v1` and webhook contract ([INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)).
3. **Set the project identity** in `.env`: `APP_NAME`, `APP_TITLE`, `APP_BRAND_LABEL`, `APP_LOGO_PATH`, `DEFAULT_AUTHENTICATED_PATH`.
4. **Do not modify `app/core`** to add domain behaviour. If the platform is missing a generic primitive, add it as a generic primitive, with tests, and propose it back to the foundation.

## 1. Backend module

```text
app/routers_api/workorders/
    __init__.py
    models.py        SQLAlchemy models
    schemas.py       Pydantic input/output (extra="forbid" on writes)
    dao.py           data access, always filtered by company_id
    service.py       business rules and state transitions (when they exist)
    router.py        thin handlers
```

### Model

```python
class WorkOrderStatus(BusinessEnum):
    OPEN = "open"
    CLOSED = "closed"

class WorkOrder(TimeStampedModel, VersionedMixin):
    __tablename__ = "work_order"
    __table_args__ = (
        WorkOrderStatus.check("status", name="ck_work_order_status"),
        UniqueConstraint("id", "company_id", name="uq_work_order_id_company"),  # target for composite FKs
    )
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), nullable=False, server_default=WorkOrderStatus.OPEN.value)
```

- A child row that belongs to the same tenant uses a **composite** foreign key `(parent_id, company_id)`.
- Evidence tables are append-only by trigger (see §4).

### Router

```python
router = APIRouter(prefix="/workorders", tags=["Work orders"])

@router.post("")
async def create_work_order(
    payload: WorkOrderCreate,
    current_company: TenantContext = Depends(get_company_required),
    current_user: Users = Depends(get_current_user),
    _authz: None = Depends(require_permissions(["workorders.create"])),
) -> WorkOrderRead:
    async with transaction():
        orden = await WorkOrdersDAO.create(company_id=current_company.id, values=payload.model_dump())
        await record_event(company_id=current_company.id, entity_type="work_order", entity_id=orden.id,
                           action="create", actor_user_id=current_user.id, summary="Work order created")
    return WorkOrderRead.model_validate(orden)
```

Register the router in `app/routers_api/api.py` (private). Never include a domain router in `app/routers_api_public/api.py`: public endpoints are added one by one and listed in `tests/test_public_surface.py`.

### Capabilities

1. **Declare** in `app/core/rbac/catalog.py`:

   ```python
   _cap("workorders", "read", "View work orders"),
   _cap("workorders", "create", "Create work orders"),
   ```

2. **Grant** them in `DEFAULT_ROLES`. `owner` and `admin` receive everything automatically; decide explicitly for `manager` and `viewer`.
3. **Seed:** `uv run python -m app.db.scripts.bootstrap`. It is idempotent and never rewrites a role's existing grants.
4. **Check:** `uv run pytest tests/test_permission_catalog.py`. It fails for a capability no endpoint uses, and for one an endpoint uses but the catalog lacks.

### Migration

```bash
uv run alembic -c app/alembic.ini revision --autogenerate -m "work orders"
```

- **Review the file.** Add by hand what autogenerate cannot infer: triggers and functions.
- **Check** that `down_revision` points at the current head (initially `0001_foundation`).
- **Run** `upgrade head`, `check`, `downgrade -1` and `upgrade head` on a scratch database.
- **Tests:** if the module adds append-only tables, add them to `APPEND_ONLY_TABLES` in your migration and in `tests/integration/conftest.py`, and add their trigger names to `EXPECTED_TRIGGERS` in `app/core/platform/integrity.py`.
- **Clean-up between tests:** add every new table to `TABLES_IN_DELETE_ORDER` in `tests/integration/conftest.py`, children before parents.

## 2. Frontend module

### Page (the four-way chain)

1. **Route** in `app/routers_pages/admin/workorders/router.py`:

   ```python
   @router.get("/list", name="WorkOrdersPage",
               dependencies=[Depends(require_page_permissions(["workorders.read"]))])
   async def get_work_orders_page(request: Request):
       return templates.TemplateResponse(request=request, name="admin/workorders/list.html", context={})
   ```

   Include it from `app/routers_pages/admin/router.py`.
2. **Template** `app/templates/admin/workorders/list.html`:

   ```html
   {% extends "base.html" %}
   {% block page_title %}Work orders{% endblock page_title %}
   {% block content %}<div id="rc-currentPage" data-current-page="{{ url_name }}"></div>{% endblock %}
   ```

   Add it to `PAGE_TEMPLATES` in `tests/test_page_wiring.py`.
3. **Page key:** `WORKORDERS = 'WorkOrdersPage'` in `maincontent.ts` and `[ComponentRoot.WORKORDERS]: <WorkOrdersPage />` in `mainContentConfig.tsx`.
4. **Page folder:** `pages/WorkOrdersPage/` with `index.ts`, `ui/WorkOrdersPage.tsx` and `ui/WorkOrdersPage.async.tsx`.

### Entity and feature

- `entities/WorkOrders/model/types/index.ts`: the Zod schema is the source, and the type comes from `z.infer`.
- `entities/WorkOrders/model/services`: thunks via `extra.api`, validated with `parseApi`.
- `entities/WorkOrders/model/slice` and `selectors`. Register the reducer key in `StateSchema.ts` and `store.ts`.
- `features/WorkOrders/ui`: panels, forms and dialogs. They dispatch thunks and read selectors; they never call Axios directly.

### Navigation

Add a group to `businessNavigation` in `app/components/react/app/providers/maincontent/config/navigation.ts`:

```ts
{ title: 'Operations', url: '#', icon: ClipboardList, items: [
    { title: 'Work orders', url: '/admin/workorders/list', requiredPermission: 'workorders.read' },
] },
```

- The sidebar and the authenticated landing page pick it up automatically.
- Administration pages go in `administrationNavigation`, never in the sidebar. `tests/test_navigation_wiring.py` enforces this.

## 3. Platform extension points

| Need | Extension point |
|---|---|
| A production-readiness gate for your domain | Append an `async (session) -> Gate` factory to `app.core.platform.readiness.EXTRA_GATES` |
| A scheduled job | `platform_scheduler.register(name, job, trigger="interval", minutes=5)` before startup; runs on the leader instance only |
| An inbound event from another app | `@register_inbound_handler("otherapp.entity.action")` in your module |
| Tell other apps something happened | `await enqueue_outbound(company_id=..., event_type="myapp.entity.action", payload=...)` inside the business transaction |
| An idempotent write endpoint | `idempotency.claim(...)` / `idempotency.remember(...)` with the `Idempotency-Key` header |
| Stored files to migrate to S3 | Append a source to `app.core.storage.migrate_local_to_s3.STORED_OBJECT_SOURCES` |
| A platform policy editable in Settings | Add a `PolicyDefinition` to `app.core.platform.policies.POLICIES` |
| Pages served without a session | Add the path to `AuthMiddleware.PUBLIC_PATHS` / `PUBLIC_PATH_PREFIXES` **and** to `tests/test_public_surface.py` |

## 4. Evidence and history

- **Append-only tables.** When a record must never be rewritten (history, approvals, signed facts), create it append-only with the trigger pattern in `0001_foundation_baseline.py` (`{table}_is_append_only` plus two triggers). A correction is a new row referencing the previous one.
- **Audit.** Every mutation writes `record_event(...)` in the same transaction, with `changes={"field": {"old": ..., "new": ...}}` from `app.core.audit.diff`.

## 5. Definition of done for a domain module

- [ ] `uv run python -c "import app.main"`
- [ ] `alembic upgrade head` on an empty database, `alembic check` clean, downgrade/upgrade works
- [ ] `uv run pytest` green, with tests for authorization, tenant isolation and database-enforced rules
- [ ] `npm run typecheck`, `npm run lint:ts`, `npm run build:prod` green
- [ ] Browser check of the new pages at desktop width and at ~390 px
- [ ] No duplicate canonical persistence of another module's or application's data
- [ ] Implementation report with evidence ([DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) §7)
