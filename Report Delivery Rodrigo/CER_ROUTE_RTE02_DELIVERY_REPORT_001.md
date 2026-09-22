# CER Route — RTE02 Delivery Report

| | |
|---|---|
| **Checkpoint** | RTE02 — Application Foundation, Access Model, Navigation, Profiles, Vehicles & Configuration |
| **Delivery** | **001** |
| **Authoritative baseline** | `CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_001.md` (certified) |
| **Repository baseline** | `cermanagementgroup-route`, branch `dev` @ `c5f3acb` (CER Application Foundation + RTE01 deliverables) |
| **Implementation branch** | `feature/rte02-route-foundation` |
| **Date** | 2026-09-22 |
| **Proposed status** | **Completed — ready for CER certification** |

---

## 1. Summary of what was implemented

CER Route now exists as a product on top of the Foundation. The application
identifies itself as CER Route, has a server-enforced Route access model with
two tenant roles, a **mobile-only** Supervisor shell separate from the
responsive Admin shell, and three working configuration domains: vehicles,
supervisor↔vehicle assignment history, and the eight admin-managed value lists.

No Work Session, Trip, Activity, geolocation or mileage behaviour was built, and
none is simulated.

**Headline numbers:** 4 new tables, 1 migration (single head), 3 new
capabilities, 2 new roles, 16 new API endpoints, 5 new pages, 42 new tests,
**308 backend tests green**, frontend typecheck/lint/build clean.

---

## 2. Status by checkpoint

| Checkpoint | Deliverable | Status |
|---|---|---|
| **RTE02-C1** | Product identity, Route RBAC, Supervisor/Route Admin roles, navigation foundation | **Completed** |
| **RTE02-C2** | Mobile-only Supervisor shell, Admin Route navigation, page-key wiring, Configuration entry point | **Completed** |
| **RTE02-C3** | Supervisor profile, Vehicle master, assignment history, Admin API/UI, tenant/security/audit | **Completed** |
| **RTE02-C4** | `standard_value` domain, eight list codes, create/edit/reorder/deactivate/reactivate | **Completed** |
| **RTE02-C5** | Migration verification, regression suite, matrices, RTE03 readiness | **Completed** |

---

## 3. Files and components changed

### Backend — new

| Path | What |
|---|---|
| `app/routers_api/vehicles/models.py` | `Vehicle`, `SupervisorProfile`, `VehicleAssignment`, `FuelGrade` enum |
| `app/routers_api/vehicles/dao.py` | `VehiclesDAO`, `SupervisorProfilesDAO`, `VehicleAssignmentsDAO` |
| `app/routers_api/vehicles/schemas.py` | Create/Update/Read contracts, pagination params |
| `app/routers_api/vehicles/service.py` | Assignment rules, lifecycle, audit |
| `app/routers_api/vehicles/router.py` | 11 endpoints |
| `app/routers_api/standardvalues/models.py` | `StandardValue`, `StandardValueList` enum |
| `app/routers_api/standardvalues/dao.py` | `StandardValuesDAO` |
| `app/routers_api/standardvalues/schemas.py` | Contracts |
| `app/routers_api/standardvalues/service.py` | Create/update/reorder rules, audit |
| `app/routers_api/standardvalues/router.py` | 5 endpoints |
| `app/routers_pages/route/router.py` | 3 Supervisor page routes |
| `app/routers_pages/admin/route/router.py` | 2 Admin configuration page routes |
| `app/migrations/versions/0002_route_foundation.py` | Schema migration |

### Backend — modified

| Path | Change |
|---|---|
| `app/config.py` | `APP_NAME` / `APP_TITLE` → `CER Route` |
| `.env.example` | Same, in the template |
| `app/core/rbac/catalog.py` | 3 Route capabilities + `supervisor` and `route_admin` role templates |
| `app/routers_api/api.py` | Registers the 3 new routers (private surface only) |
| `app/routers_pages/admin/router.py`, `app/routers_pages/page.py` | Include the new page routers |

### Frontend — new

`widgets/RouteShell/` (mobile shell + `NotBuiltYet`), `entities/RouteVehicles/`,
`entities/RouteSupervisors/`, `entities/RouteStandardValues/` (all Zod-validated),
`features/RouteVehicles/` (2 panels), `features/RouteStandardValues/` (1 panel),
and 5 pages: `RouteMyRoutePage`, `RouteActivityPage`, `RouteMePage`,
`RouteVehiclesPage`, `RouteStandardValuesPage`. Templates under
`app/templates/route/` and `app/templates/admin/route/`.

### Frontend — modified

`maincontent.ts` (5 page keys), `mainContentConfig.tsx` (5 components),
`AppMainContent.tsx` (Supervisor pages excluded from the desktop shell),
`navigation.ts` (CER Route business group).

### Tests

| Path | Change |
|---|---|
| `tests/integration/test_route_foundation.py` | **New** — 37 tests |
| `tests/integration/conftest.py` | Route tables in cleanup order; `route_admin` and `supervisor` seeded users |
| `tests/test_page_wiring.py` | 5 new templates registered in `PAGE_TEMPLATES` |
| `tests/integration/test_pagination_and_transactions.py` | Generalised (see §11) |

---

## 4. Migration and Alembic heads

| | |
|---|---|
| Revision | `0002_route_foundation` (down_revision `0001_foundation`) |
| **Heads** | **`0002_route_foundation (head)` — exactly one** |
| Tables created | `vehicle`, `supervisor_profile`, `vehicle_assignment`, `standard_value` |
| Verified | `upgrade head` → `check` clean → `downgrade -1` → `upgrade head`, all against real PostgreSQL |

The autogenerated file was reviewed rather than trusted: the partial unique
index came out correct and was kept, and the docstring was rewritten to state
the three database-enforced guarantees.

---

## 5. Data model

| Table | Purpose | Key constraints |
|---|---|---|
| `vehicle` | Vehicle master | `ck_vehicle_fuel_grade` (enum CHECK), `uq_vehicle_company_unit`, `uq_vehicle_id_company` (composite-FK target), MPG > 0, year range |
| `supervisor_profile` | Thin Route extension of a Core user | `fk_supervisor_profile_membership` → `user_company(user_id, company_id)`, `uq_supervisor_profile_company_user` |
| `vehicle_assignment` | Effective-dated history | **`uq_vehicle_assignment_current`** — partial unique `WHERE effective_to IS NULL`; composite FKs to supervisor and vehicle; period CHECK |
| `standard_value` | Tenant-configurable list values | `ck_standard_value_list_code` (8 codes), `uq_standard_value_company_list_label` |

**Single source of truth for the current vehicle.** It is derived from the open
`vehicle_assignment` row; no copy is kept on `supervisor_profile`. Nothing can
drift because there is nothing to drift from.

**`supervisor_profile` is deliberately thin.** It holds no name, email or
authentication — those stay in `user`. It carries no field attributes because
none exist yet at this checkpoint; inventing columns nobody writes would imply
data that is not there.

---

## 6. APIs implemented

All under the authenticated private surface. **Nothing was added to the public
surface** — `tests/test_public_surface.py` is unchanged and green.

### Vehicles

| Method | Path | Capability |
|---|---|---|
| GET | `/api/vehicles` | `route.vehicles.read` |
| GET | `/api/vehicles/pagination` | `route.vehicles.read` |
| GET | `/api/vehicles/{id}` | `route.vehicles.read` |
| POST | `/api/vehicles` | `route.vehicles.manage` |
| PUT | `/api/vehicles/{id}` | `route.vehicles.manage` |
| POST | `/api/vehicles/{id}/deactivate` | `route.vehicles.manage` |
| POST | `/api/vehicles/{id}/activate` | `route.vehicles.manage` |

### Supervisors and assignments

| Method | Path | Capability |
|---|---|---|
| GET | `/api/supervisors` | `route.vehicles.read` |
| POST | `/api/supervisors` | `route.vehicles.manage` |
| **GET** | **`/api/supervisors/me`** | **Session only** — own data, see §10 |
| GET | `/api/supervisors/{id}/assignments` | `route.vehicles.read` |
| POST | `/api/supervisors/{id}/assignments` | `route.vehicles.manage` |
| POST | `/api/supervisors/assignments/{id}/end` | `route.vehicles.manage` |

### Standard values

| Method | Path | Capability |
|---|---|---|
| GET | `/api/standard-values/lists` | `route.standardvalues.manage` |
| GET | `/api/standard-values/{list_code}` (+ `include_inactive`) | `route.standardvalues.manage` |
| POST | `/api/standard-values` | `route.standardvalues.manage` |
| PUT | `/api/standard-values/{id}` | `route.standardvalues.manage` |
| POST | `/api/standard-values/{list_code}/reorder` | `route.standardvalues.manage` |

---

## 7. Roles and capabilities actually registered

**Three capabilities**, each enforced by real endpoints:

| Capability | Enforced at |
|---|---|
| `route.vehicles.read` | 6 API endpoints + `RouteVehiclesPage` |
| `route.vehicles.manage` | 8 API endpoints |
| `route.standardvalues.manage` | 5 API endpoints + `RouteStandardValuesPage` |

**Deferred, exactly as §4.2 allows** — the repository invariant rejects a
capability no endpoint requires (`test_permission_catalog.py`), so these enter
with the checkpoint that builds their protected surface:
`route.worksession.execute`, `route.live.read`, `route.activity.read`,
`route.reports.read`, `route.reports.export`, `route.fuelreference.manage`,
`route.records.adjust`. **The certified target list is unchanged.**

**Two roles**, seeded idempotently:

| Role | Capabilities | Note |
|---|---|---|
| `supervisor` | **none** | Field persona. Its capability (`route.worksession.execute`) arrives with the workday. The mobile shell requires a session, not a capability — same rule as `ProfilePage` |
| `route_admin` | `companies.read`, `regions.read`, `users.read`, the 3 `route.*` | Operational configuration administrator within the tenant |

`is_superuser` was **not** converted into a tenant role, and no Route capability
duplicates a Core one.

**Seeding verified against an existing tenant** (`uv run python -m app.db.scripts.bootstrap`):
3 capabilities created, `owner`/`admin` received them, `manager`/`viewer`
correctly received none, both Route roles created, **existing roles, users and
the admin password untouched**.

---

## 8. Web/Admin UI

- **Vehicles** (`/admin/route/vehicles`) — two tabs: the vehicle master
  (create/edit/retire/restore, MPG, fuel grade) and Assignments (assign, end,
  full history per supervisor, current vehicle derived).
- **Standardized Lists** (`/admin/route/standard-values`) — the eight lists with
  counts, add/retire/restore values, reorder, and a "Show retired values"
  toggle.
- **Navigation:** a `CER Route` group in `businessNavigation`, each item gated by
  the same capability its API requires. Today/Live, Activity and Reports are
  **not** wired — their modules do not exist, and a menu heading pointing at
  nothing is a dead link dressed as a section.

---

## 9. Supervisor Mobile shell

Mobile-only (D-03), at `/route`, `/route/activity`, `/route/me`. It does **not**
use the desktop sidebar: the three Supervisor page keys are excluded from the
Admin layout in `AppMainContent.tsx` and render inside `RouteMobileShell` —
compact header, full-viewport content, three-destination bottom bar sized for a
thumb.

**No fake business data.** My Route and Activity render a `NotBuiltYet` panel
naming the missing module and the checkpoint that delivers it. **Me** shows real
RTE02 data: the supervisor's identity and their currently assigned vehicle, or
an explicit "no vehicle assigned" — which is a normal state, not an error.

---

## 10. Security, tenant isolation and audit — evidence

| Control | Evidence |
|---|---|
| Tenant from subdomain, never from the client | Every endpoint uses `Depends(get_company_required)` |
| Cross-tenant access returns **404, not 403** | `test_a_vehicle_of_another_company_is_not_found` |
| Cross-tenant assignment impossible **in the database** | Composite FKs; `test_a_vehicle_cannot_be_assigned_across_tenants` |
| A non-member cannot become a supervisor | `fk_supervisor_profile_membership`; `test_a_user_of_another_company_cannot_become_a_supervisor` |
| Server-side authorization, not UI hiding | `test_a_supervisor_cannot_administer_vehicles`, `..._standard_values`, `test_a_viewer_without_the_capability_is_denied` |
| One current assignment per supervisor | Partial unique index; proven bypassing the API **and** with two concurrent requests |
| Optimistic concurrency | `test_a_stale_version_is_rejected_with_409` |
| Fuel grade constrained by the database | `test_the_database_rejects_a_fuel_grade_outside_the_enum` |
| Audit of vehicles, assignments and values | 3 audit tests asserting action, actor and `{old, new}` changes |
| CSRF | Exercised by the shared test client on every mutating call |

**One deliberate authorization decision, raised explicitly:**
`GET /api/supervisors/me` requires a **session only, no capability**. A
supervisor must be able to see which vehicle they drive; requiring
`route.vehicles.read` would mean granting the field role a vehicle-administration
permission to read their own record — the opposite of minimum privilege. It
returns only the caller's own profile, and it follows the existing
`/api/users/profile` precedent. Flagged here in case CER reads it differently.

---

## 11. Tests and exact commands

| Command | Result |
|---|---|
| `uv run python -c "import app.main"` | **OK** |
| `uv run alembic -c app/alembic.ini heads` | **`0002_route_foundation (head)`** — one head |
| `uv run alembic -c app/alembic.ini upgrade head` | OK |
| `uv run alembic -c app/alembic.ini check` | **No new upgrade operations detected** |
| `uv run alembic -c app/alembic.ini downgrade -1` then `upgrade head` | OK (roundtrip) |
| `uv run pytest` | **308 passed** in 381.73s |
| `uv run pytest tests/integration/test_route_foundation.py` | **37 passed** |
| `cd app && npm run typecheck` | **0 errors** |
| `cd app && npm run lint:ts` | **0 errors** |
| `cd app && npm run build:prod` | **compiled** (2 pre-existing bundle-size warnings) |
| `uv run python -m app.db.scripts.bootstrap` | Idempotent; see §7 |

**Baseline before RTE02 was 266 tests; it is now 308 (+42).**

**One pre-existing test was generalised, and it is worth stating plainly.**
`test_next_and_previous_reflect_the_position` hardcoded `page=2` as the last
page of roles — true only while there were exactly four default roles. Adding
the two Route roles broke it. The test's subject is that `next`/`previous`
reflect position, not how many roles the catalog has, so the last page is now
computed from the fixture (the same style the neighbouring assertion already
used). **No control was weakened to make a test pass.**

---

## 12. Expected vs Implemented

| RTE02 requirement | Implemented | Evidence |
|---|---|---|
| Product identity is CER Route | ✅ | `app/config.py`, `.env.example` |
| Existing tenant resolution and platform admin intact | ✅ | 308 tests green, including platform suites |
| Route capabilities in catalog, exercised by real surfaces | ✅ (3) | §7; `test_permission_catalog.py` |
| No orphan capability | ✅ | The invariant test enforces it |
| Supervisor and Route Admin roles | ✅ | §7 |
| Server-side enforcement proven | ✅ | §10 |
| Cross-tenant denied without existence leakage | ✅ | 404 tests |
| Supervisor mobile shell, no desktop sidebar | ✅ | §9 |
| Admin Route navigation, Configuration reachable | ✅ | §8 |
| No future feature represented as implemented | ✅ | `NotBuiltYet`; unbuilt routes not registered |
| Page/navigation wiring tests green | ✅ | 60 architecture tests |
| Profile does not duplicate Core identity | ✅ | §5 |
| Vehicle master tenant-scoped | ✅ | §5 |
| Assignment history effective-dated | ✅ | §5 |
| No overlapping current assignments | ✅ | Partial unique index + concurrency test |
| History retained after reassignment | ✅ | `test_reassignment_closes_the_previous_one_instead_of_overwriting` |
| No cross-tenant assignment | ✅ | Composite FKs |
| Vehicle changes auditable | ✅ | §10 |
| All eight list codes | ✅ | `test_all_eight_approved_lists_are_available` |
| Values tenant-specific | ✅ | Isolation tests |
| Outcome remains tenant data, not enum | ✅ | `test_outcomes_are_tenant_data_and_not_seeded_by_the_product` |
| Free-text fields not turned into catalogs | ✅ | Only the 8 codes exist; `client_destinations` rejected with 422 |
| Deactivate without destroying history | ✅ | `test_a_retired_value_remains_resolvable_for_history` |
| No configurable Activity Type / form builder | ✅ | Not implemented |
| Single Alembic head | ✅ | §4 |
| Constraints verified against PostgreSQL | ✅ | §4, §10 |
| Backend / frontend / architecture suites green | ✅ | §11 |
| No RTE03+ lifecycle implemented | ✅ | §14 |

---

## 13. Edge cases from §13 of the instructions

| # | Case | Handling |
|---|---|---|
| 1 | Vehicle of another tenant | 404 — tested |
| 2 | Assign another tenant's vehicle | Rejected by composite FK — tested |
| 3 | Supervisor with no assignment | Normal state, `current_vehicle: null` — tested |
| 4 | Vehicle change keeps history | Previous row closed, not overwritten — tested |
| 5 | Concurrent overlapping assignments | Partial unique index; exactly one current row — tested concurrently |
| 6 | Vehicle deactivated with history | Allowed once no current assignment; history intact — tested. Retiring a vehicle **in use** returns 409 |
| 7 | Value deactivated after historical use | Remains resolvable via `include_inactive` — tested |
| 8 | Same label in different tenants | Allowed — tested |
| 9 | Same label in different lists, one tenant | Allowed — tested |
| 10 | Concurrent admin edits | 409 with `X-Current-Version` — tested |
| 11 | Route Admin lacking a capability | Server denies — tested |
| 12 | Unimplemented route | Not registered; scaffolds declare themselves |

---

## 14. Confirmation: no RTE03+ scope was started

No Work Session, Start/End Work, Trip lifecycle, Change Plan, Activity
execution, multi-Activity block, geolocation, Recovery Window, Missing Location
Event, mileage, routing provider, sweeper, breadcrumbs, notifications, fuel
ingestion or estimate, Today/Live, Activity Explorer, reports, export,
corrections, retention jobs, odometer, maps, Supervisor Desktop or ERP
integration was implemented. No table for those domains was created.

**No certified RTE01 decision was changed.**

---

## 15. Technical decisions made by Development

1. **`vehicle_assignment` is not append-only.** Closing an assignment writes
   `effective_to`, which an append-only trigger would forbid. History is
   protected by never deleting rows and auditing every change.
2. **Vehicles and assignments share one module** (`routers_api/vehicles/`)
   because assignment is meaningless without the vehicle it references.
3. **One `standard_value` table keyed by a closed `list_code` enum**, rather
   than eight near-identical tables. The *list codes* are product (enum +
   CHECK); the *values* are tenant rows — which is precisely what keeps Outcome
   configurable.
4. **Reorder requires the exact set** of a list's values. Accepting a subset
   would leave the rest in an order that depends on which row the query met
   first.
5. **A vehicle in use cannot be retired** (409). The alternative — silently
   retiring a vehicle someone is driving — would leave the assignment pointing
   at a retired unit.
6. **`GET /supervisors/me` requires no capability** (§10).

## 16. Deviations

**None from the certified baseline or the RTE02 instructions.** The two items
worth CER's attention are the `/supervisors/me` authorization decision (§10) and
the generalised pagination test (§11); neither changes product behaviour.

---

## 17. Deferred to future checkpoints

- The seven remaining Route capabilities, with the surfaces that require them.
- Today/Live, Activity Explorer and Reports navigation, with their modules.
- Supervisor workday UI (My Route, Activity) — scaffolds today.
- `route.records.adjust` and the Admin correction surface (D-08.2).

## 18. New risks discovered

| Risk | Severity | Note |
|---|---|---|
| **Supervisor designation has no dedicated Admin screen** | Low | A supervisor profile is created through `POST /api/supervisors`; the Assignments tab lists existing ones but does not yet offer "add supervisor" as a form. Worth a small UI addition in the checkpoint that first needs it |
| **Frontend bundle is 785 KiB** | Low | Pre-existing, not caused by RTE02; will grow with Route modules. Worth code-splitting before RTE08 |
| **Dev-database drift** | Informational | The local dev database had `company.subdomain = 'cerroute'` while `.env` said `certime`, so `bootstrap` tried to insert a second company and failed on the name unique constraint. **Not caused by RTE02 and no data was modified to work around it** — the seeding was verified by pointing the script at the real subdomain. Worth aligning the two before the next environment setup |

---

## 19. V-1 parallel validation track

**`Pending Validation`.** No real iOS/Android hardware was available during
RTE02, so no device lifecycle or location behaviour was observed. Nothing about
device behaviour is self-certified here, and **D-03 remains a delegated
technical decision at exactly the status RTE01 certified** — the mobile-only
Supervisor shell is built as an installable-PWA-ready web client without
hardening that choice. V-4 was not run: the Route lifecycle and offline queue it
would exercise do not exist yet.

---

## 20. RTE03 readiness

**Ready.** The foundations RTE03 needs are in place and tested: tenant-scoped
Route domain with the DAO/service/audit pattern established, the Supervisor
shell with a place for the workday, `supervisor_profile` as the anchor for
session ownership, and the vehicle assignment that a Work Session will snapshot
its MPG from.

**Proposed status: `Completed — ready for CER certification`.** CER performs the
final validation.
