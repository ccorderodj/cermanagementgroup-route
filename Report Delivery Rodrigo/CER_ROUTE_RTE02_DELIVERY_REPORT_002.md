# CER Route — RTE02 Delivery Report

| | |
|---|---|
| **Checkpoint** | RTE02 — Closure of Admin Configuration / CRUD Gap |
| **Delivery** | **002** |
| **Previous delivery** | `CER_ROUTE_RTE02_DELIVERY_REPORT_001.md` (status `Partial`) |
| **Instruction applied** | `CER_ROUTE_RTE02_CLOSURE_INSTRUCTIONS_001.md` |
| **Authoritative baseline** | `CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_001.md` (certified) |
| **Implementation branch** | `feature/rte02-route-foundation` |
| **Date** | 2026-09-22 |
| **Proposed status** | **RTE02 — Completed / Ready for CER Certification** |

---

## 1. RTE02 status by checkpoint

| Checkpoint | Status | Note |
|---|---|---|
| **RTE02-C1** — Identity + access | **Completed** | `route_admin` extended with the minimum Core user-management capabilities (§4) |
| **RTE02-C2** — Shells + navigation | **Completed** | Configuration now has Users, Supervisors, Vehicles, Standardized Lists |
| **RTE02-C3** — Supervisor profile + Vehicles | **Completed** | Supervisor designation is now a product action, not an API call |
| **RTE02-C4** — Standardized Lists | **Completed** | Value editing added; all eight lists proven by parameterized tests |
| **RTE02-C5** — Regression + closure | **Completed** | 352 backend tests green; frontend clean; environment drift resolved |

---

## 2. Gap-closure work performed

The gap was that RTE02 delivered working APIs but not a fully operable Admin
experience: designating a supervisor required calling the API by hand, there was
no user administration inside CER Route, and a standard value could not be
renamed from the UI.

| Gap | Closed by |
|---|---|
| No user administration in Route Configuration | New **Users** page reusing the Core `SecurityUsersPanel` verbatim |
| Supervisor designation was API-only | New **Supervisors** page: designate, remove/restore, assign, end, history |
| `route_admin` could not create/edit users | Granted the existing Core capabilities (§4) |
| Standard values could not be renamed from the UI | Inline **Edit** added to the values table |
| Reports scattered at repository root | `Report Delivery Rodrigo/` created; all reports moved there |
| Dev environment drift (`certime` vs `cerroute`) | `.env` aligned to the real CER Route tenant (§18) |
| **User administration was not audited at all** | Audit added to the Core user-management module (§14) — a genuine defect found by a test written for this closure |

---

## 3. User-management Core components reused

**No second user model, no second screen, no Route-specific user API.**

| Reused | What it provides |
|---|---|
| `app/routers_api/usermanagement/` | `GET /api/users/pagination`, `POST /api/users`, `PUT /api/users/{id}`, `PUT /api/users/{id}/access` |
| `Users` + `UserCompany` (Core models) | The authoritative identity and tenant membership |
| `features/SecurityUsers/SecurityUsersPanel` | The complete Admin users UI: DataTable, search, pagination, create/edit dialog, access toggle |
| `entities/UserManagement` | Zod-validated entity, thunks, slice, selectors |
| `entities/Roles` (`fetchRoles`) | The role dropdown in the user form |
| `app/core/audit/` | The audit primitive (`record_event`, `diff`) |

The Route Users page is 25 lines: a `PageHeader` plus `<SecurityUsersPanel />`.
Writing a second users screen would have created a second place to fix the same
bug.

---

## 4. Core capabilities reused, and the change to `route_admin`

**No `route.users.*` capability was invented.** The Core contract already exists
and duplicating it would mean two ways to authorize the same thing.

`route_admin` gained exactly four **existing Core** capabilities:

| Capability | Why it is required |
|---|---|
| `users.create` | `POST /api/users` — create the user, its membership and its role |
| `users.update` | `PUT /api/users/{id}` and `PUT /api/users/{id}/access` — edit and suspend/restore |
| `roles.read` | The create/edit form must list this company's roles to assign one |
| `users.read` | Already granted in delivery 001 |

Final `route_admin` grant (verified in the database):
`companies.read`, `regions.read`, `roles.read`, `users.read`, `users.create`,
`users.update`, `route.vehicles.read`, `route.vehicles.manage`,
`route.standardvalues.manage`.

### Privilege boundary — how it holds

| Control | Mechanism |
|---|---|
| Cannot grant platform superuser | `is_superuser` is **not in the Core input schemas**. Sending it returns **422**, not a silently-ignored field. Two tests assert this |
| Cannot fabricate a more powerful role | `roles.read` only. `roles.create/update/delete` were **not** granted — a test asserts `POST /api/roles` returns 403 |
| Cannot administer another tenant | Company comes from the subdomain; Core queries are company-scoped |
| Cannot bypass role-assignment safeguards | `fk_user_company_role_same_company` rejects a role from another company at the database level |

**No unresolved privilege-escalation ambiguity was found.** The Core contract
excludes `is_superuser` at the schema boundary, which is the strongest place to
exclude it, because it does not depend on anyone remembering to filter it.

---

## 5. User CRUD / lifecycle implemented

| Operation | Where | Capability |
|---|---|---|
| **Create** — user + membership + role, in one transaction | Users page → "Add user" | `users.create` |
| **Read** — list, search, paginate, open detail, see active state and role | Users page | `users.read` |
| **Update** — username, email, names, password, role | Users page → row action | `users.update` |
| **Deactivate / restore** — suspends membership in *this* company | Users page → row action | `users.update` |
| **Physical delete** | **Does not exist**, by design | — |

Suspension writes `UserCompany.is_active`, not `Users.is_active`: the identity
is platform-level (D7). A deactivated user remains fully resolvable — a test
asserts the row still exists after suspension.

**Is the user a Route Supervisor, and what do they drive?** That is answered on
the Supervisors page (§6), which shows every tenant user with their designation
and current vehicle in one row.

---

## 6. Supervisor designation UI

New page **Configuration → Supervisors** (`/admin/route/supervisors`), backed by
`GET /api/supervisors/candidates`. One table makes the whole chain visible and
operable:

`User (Core identity) → Route supervisor designation → Vehicle assignment`

| Column / action | Behaviour |
|---|---|
| User | Name, email, and an "Access suspended" badge when the membership is inactive |
| Tenant role | From `user_company` → `role` |
| Route supervisor | `No` / `Yes` / `Removed` |
| Current vehicle | Derived from the open assignment — never a stored copy |
| **Designate** | Shown only for users who are not yet supervisors |
| **Remove / Restore** | Deactivates or restores the designation. **Never deletes it** |
| **Assign / End / History** | The full assignment lifecycle, inline |

Rules enforced server-side and tested: a duplicate designation returns **409**; a
user of another tenant cannot be designated (**404**, blocked by
`fk_supervisor_profile_membership`); and a supervisor who still holds a vehicle
**cannot** be undesignated (**409**) — otherwise a vehicle would stay assigned to
someone who is no longer a supervisor.

`supervisor_profile` remains thin: no name, email, authentication, tenant or
role data was added to it. The candidates query resolves identity by join.

---

## 7. Vehicle CRUD / lifecycle status

Complete and unchanged from delivery 001, re-verified:

| Operation | Status |
|---|---|
| Create | ✅ |
| Read / list / search / detail | ✅ |
| Update (with optimistic concurrency) | ✅ |
| Retire (deactivate) | ✅ — preserves history |
| Restore (reactivate) | ✅ |
| Physical delete | Does not exist |

The accepted rule holds: a vehicle with a current assignment cannot be retired
(**409**). No odometer, maintenance, insurance, registration or telematics scope
was added.

The Vehicles page is now the vehicle master only; assignments moved to the
Supervisors page, where the `user → supervisor → vehicle` relationship actually
lives.

---

## 8. Vehicle Assignment administrative lifecycle

| Operation | Status |
|---|---|
| View current assignment | ✅ Derived from the open row |
| View history | ✅ Full, with vehicle details resolved by join |
| Create | ✅ |
| End | ✅ Writes `effective_to`; the row stays |
| Replace / reassign | ✅ Closes the previous, opens the new, in one transaction |
| Supervisor with no vehicle | ✅ A normal state, displayed as "None" |
| Destructive delete | Does not exist |

One current assignment per supervisor is enforced by the partial unique index
`WHERE effective_to IS NULL` — proven both by bypassing the API and by firing two
concurrent requests. **One-supervisor-per-vehicle exclusivity was not imposed**;
CER has not approved it.

---

## 9. Standardized Lists — status per list

**Parameterized across all eight list codes** (24 tests: lifecycle, reorder and
tenant isolation × 8). Testing one and assuming the rest is exactly the error
the instruction warned against.

| List code | Create | Read | Edit | Reorder | Retire | Restore | Show retired | Tenant-scoped |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `client_visit_activities` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `recruiting_activities` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `employee_visit_reasons` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `delivery_types` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `office_purposes` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `other_activities` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `outcomes` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `received_by` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

**Edit was the missing operation** and is now inline in the values table, sending
`version` for concurrency control.

Preserved: the eight `list_code` identifiers remain product-defined and are not
editable; a retired value stays resolvable via `include_inactive=true`; Outcome
remains tenant data — a test asserts a new company starts with **zero** outcome
values, because seeding "Completed" would be an enum wearing a costume; and none
of the five approved free-text fields became a catalog.

---

## 10. APIs changed / reused

### Reused unchanged (Core)

`GET /api/users/pagination`, `POST /api/users`, `PUT /api/users/{id}`,
`PUT /api/users/{id}/access`, `GET /api/roles`.

### New (Route)

| Method | Path | Authorization |
|---|---|---|
| `GET` | `/api/supervisors/candidates` | `users.read` **and** `route.vehicles.read` — it reads both Core identity and Route domain |
| `PUT` | `/api/supervisors/{id}` | `route.vehicles.manage` — designation lifecycle |

### Modified (Core, audit only)

`app/routers_api/usermanagement/router.py` — the three mutating endpoints now
call `record_event`. No behaviour or contract changed.

---

## 11. UI / pages / components

### New

| Path | What |
|---|---|
| `pages/RouteUsersPage/` | Wraps the Core users panel |
| `pages/RouteSupervisorsPage/` | Wraps the supervisor setup panel |
| `features/RouteVehicles/ui/SupervisorSetupPanel.tsx` | The `user → designation → vehicle` table |
| `templates/admin/route/users.html`, `supervisors.html` | Page templates |
| `routers_pages/admin/route/router.py` | Two new page routes |

### Modified

`features/RouteStandardValues/ui/StandardValuesPanel.tsx` (inline edit);
`pages/RouteVehiclesPage` (vehicle master only); `maincontent.ts`,
`mainContentConfig.tsx`, `navigation.ts`; `entities/RouteSupervisors` (candidate
schema + three services).

### Removed

`features/RouteVehicles/ui/SupervisorAssignmentsPanel.tsx` — superseded by
`SupervisorSetupPanel`. Deleted rather than left behind; the repository's
frontend-completeness test is what flagged it.

**Navigation:** `CER Route → Users | Supervisors | Vehicles | Standardized
Lists`. Users is gated by `users.read`, the rest by their Route capabilities. No
second Admin application was created.

---

## 12. Migrations

**None.** This closure added no table and no column, so the schema is unchanged
and **`0002_route_foundation` remains the single head**. `alembic check` reports
no pending operations.

---

## 13. Security and tenant isolation evidence

| Control | Test |
|---|---|
| A user created in A is invisible to B | `test_the_created_user_belongs_only_to_the_acting_tenant` |
| A cross-tenant user cannot be designated supervisor | `test_a_user_of_another_company_cannot_become_a_supervisor` (404) |
| Route Admin cannot grant platform superuser on create | `test_route_admin_cannot_grant_platform_superuser` (422, and no user is created) |
| Route Admin cannot escalate an existing user | `test_route_admin_cannot_escalate_an_existing_user_to_superuser` (422) |
| Route Admin cannot administer roles | `test_route_admin_cannot_administer_roles_themselves` (403) |
| Supervisor cannot administer users | `test_a_supervisor_cannot_administer_users` (403) |
| `users.read` alone does not allow creating | `test_a_viewer_cannot_create_users` (200 then 403) |
| The candidates endpoint requires both capabilities | `test_the_candidates_endpoint_requires_both_capabilities` |
| Deactivated user remains resolvable | `test_route_admin_can_update_and_suspend_a_user` |
| Lists never cross tenants | `test_every_list_is_tenant_scoped` × 8 |
| CSRF on every mutation | The shared test client sends the token on all mutating calls |

Tenant always derives from the subdomain. No endpoint accepts a company id from
the client.

---

## 14. Audit evidence — and a defect found

**A test written for this closure failed, and it was right to fail.** Core user
management performed no auditing at all: creating a user — which grants access
to a tenant — left no trace.

Per §13 ("do not create parallel audit mechanisms if Core audit already covers
User/Role operations"), Core did **not** cover it, so audit was added **to the
Core module using the existing primitive**, not a Route-specific mechanism:

| Operation | Action recorded | Changes captured |
|---|---|---|
| Create user | `create` | username, email, names, gender, role_id |
| Update user | `update` | `{old, new}` per changed field |
| Password change | included in `update` | `"(changed)"` — **the value is never recorded** |
| Suspend / restore access | `deactivate` / `activate` | `is_active` transition |

Every event carries actor, tenant, target, action, timestamp and request context
through `record_event`.

Route configuration audit from delivery 001 is unchanged and re-verified:
vehicles (create/update/retire/restore), assignments (create/end/replace),
standard values (create/update/reorder/retire/restore), plus the new supervisor
designation lifecycle (`create` / `deactivate` / `activate`).

---

## 15. Tests added

| File | Tests | Covers |
|---|---|---|
| `tests/integration/test_route_admin_configuration.py` | **42 new** | User CRUD via Core, privilege boundary, supervisor designation lifecycle, the eight lists parameterized (24), audit |
| `tests/integration/test_route_foundation.py` | 37, re-run | Vehicles, assignments, isolation, concurrency, audit |
| `tests/test_page_wiring.py` | Updated | Two new templates registered |

**Backend total: 352 (was 308 at delivery 001, 266 before RTE02).**

---

## 16. Exact commands and results

| Command | Result |
|---|---|
| `uv run python -c "import app.main"` | **OK** |
| `uv run pytest` | **352 passed** in 544.15s |
| `uv run pytest tests/integration/test_route_admin_configuration.py` | **42 passed** |
| `uv run pytest tests/test_page_wiring.py tests/test_navigation_wiring.py tests/test_permission_catalog.py tests/test_public_surface.py` | **60 passed** |
| `uv run alembic -c app/alembic.ini heads` | **`0002_route_foundation (head)`** — one head |
| `uv run alembic -c app/alembic.ini check` | **No new upgrade operations detected** |
| `cd app && npm run typecheck` | **0 errors** |
| `cd app && npm run lint:ts` | **0 errors** |
| `cd app && npm run build:prod` | **compiled** (2 pre-existing bundle-size warnings) |
| `uv run python -m app.db.scripts.bootstrap` | Ran twice: first added the 3 new capabilities to `route_admin`; second reported **no changes** — idempotent |

No migration roundtrip was repeated because **no migration changed**.

---

## 17. Expected vs Implemented — this closure

| Acceptance criterion | Status | Evidence |
|---|:-:|---|
| Route Admin Configuration exposes User administration | ✅ | §5, §11 |
| Admin can create a user | ✅ | `test_route_admin_can_create_a_tenant_user` |
| Admin can list/search/read | ✅ | Core panel; `users.read` |
| Admin can edit supported attributes | ✅ | `test_route_admin_can_update_and_suspend_a_user` |
| Admin can deactivate/restore per Core lifecycle | ✅ | Same test |
| User operations reuse Core identity and capabilities | ✅ | §3, §4 |
| No parallel Route user model | ✅ | `test_route_admin_uses_core_user_capabilities_not_route_ones` |
| Cross-tenant operations impossible | ✅ | §13 |
| Platform-superuser not exposed | ✅ | Two 422 tests |
| Existing user designable as Supervisor from UI | ✅ | §6 |
| Duplicate Supervisor profile prevented | ✅ | `test_a_duplicate_designation_is_rejected` (409) |
| Designation not confused with identity | ✅ | Separate pages, separate entities |
| Supervisor can exist without a vehicle | ✅ | `test_a_supervisor_without_an_assignment_has_no_vehicle` |
| Assignment follows naturally from setup | ✅ | Same row, inline |
| Vehicles: create/read/update/retire/restore | ✅ | §7 |
| Assignments: create/read/end/replace, no destructive delete | ✅ | §8 |
| Eight lists: create/read/edit/reorder/retire/restore/history | ✅ | §9, parameterized |
| Outcome remains tenant data | ✅ | `test_outcomes_are_tenant_data_and_not_seeded_by_the_product` |
| No free-text field turned into a catalog | ✅ | Only the eight codes exist; others rejected 422 |
| Server-side authorization verified | ✅ | §13 |
| Tenant isolation verified | ✅ | §13 |
| Audit verified | ✅ | §14 |
| No regression | ✅ | 352 passed |
| One Alembic head | ✅ | §12 |
| Backend + frontend green | ✅ | §16 |
| No RTE03+ started | ✅ | §20 |

---

## 18. Environment-drift resolution

**Cause.** `.env` carried `BOOTSTRAP_COMPANY_SUBDOMAIN=certime` — a value left
over from the CER Time project — while the CER Route tenant in the database is
`cerroute`. Bootstrap looks the company up by subdomain, found none, and tried to
insert a second company, failing on the name unique constraint.

**Fix.** One line of **configuration**, using the existing mechanism:
`BOOTSTRAP_COMPANY_SUBDOMAIN=certime` → `cerroute`. The configuration was wrong,
not the data.

**No business data was mutated**, no hardcoded workaround was added, and the
ad-hoc `BOOTSTRAP_COMPANY_SUBDOMAIN=cerroute` override used during delivery 001
is no longer needed.

**Verification.** `uv run python -m app.db.scripts.bootstrap` now runs clean with
no environment overrides, and a second consecutive run reports no changes at all
— idempotent, against the intended CER Route tenant.

**One cosmetic inconsistency remains, deliberately not fixed by me.** The company
row still has `domain = 'certime.localhost'` while its subdomain is `cerroute`.
That column is **not** used for tenant resolution (resolution is by `subdomain`
only) and it is editable by an Admin from **Company Profile** in the product. I
did not change it with SQL precisely because this closure's standard is that no
normal administration task should require direct database editing — correcting
it in the UI demonstrates the standard rather than violating it. It affects
nothing functionally.

---

## 19. Report storage

Confirmed. All CER Route delivery reports are now under `Report Delivery Rodrigo/`
and **no duplicates remain at the repository root**:

```
Report Delivery Rodrigo/
├── CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT.md        (R3.1, historical)
├── CER_ROUTE_RTE01_TECHNICAL_BASELINE_REPORT_R3_2_001.md (certified baseline)
├── CER_ROUTE_RTE02_DELIVERY_REPORT_001.md              (historical evidence)
└── CER_ROUTE_RTE02_DELIVERY_REPORT_002.md              (this report)
```

The earlier reports were moved with `git mv`, so their history is preserved. No
earlier report was overwritten. The RTE01 reports were moved too, since leaving
them at the root is what §18 asks to stop doing.

---

## 20. Confirmation: no RTE03+ functionality was started

No Work Session, Start/End Work, Trip lifecycle, Change Plan, Activity
execution, geolocation, Recovery Window, Missing Location Event, mileage,
routing provider, breadcrumbs, notifications, fuel ingestion or estimate,
Today/Live, Activity Explorer, reports, export, post-close corrections,
retention jobs, odometer, maps or Supervisor Desktop was implemented.

**All "Do Not Change" items in §17 of the instruction are preserved:** only
exercised Route capabilities are registered (still three); `GET
/api/supervisors/me` remains self-service with no capability; the current
vehicle still derives from the open assignment; one current assignment per
supervisor; `supervisor_profile` is still thin; one `standard_value` table with
eight closed codes; Outcome is tenant data; nothing is physically deleted as
normal operation; the Supervisor experience is still mobile-only.

---

## 21. Closure standard

> **No normal RTE02 administration task requires Postman, direct API execution,
> direct database editing, or developer intervention.**

| Task | Product path |
|---|---|
| Create / edit / suspend a user | Configuration → Users |
| Designate or remove a Route supervisor | Configuration → Supervisors |
| Assign, end or replace a vehicle | Configuration → Supervisors |
| Review assignment history | Configuration → Supervisors |
| Create / edit / retire / restore a vehicle | Configuration → Vehicles |
| Create / edit / reorder / retire / restore a list value | Configuration → Standardized Lists |
| View retired values | Same screen, "Show retired values" |

No remaining RTE02 administration task requires an API call.

---

## 22. New risk discovered

| Risk | Severity | Note |
|---|---|---|
| **Core user administration was unaudited** | **Resolved in this delivery** | Found by a test written for this closure. It affected the Foundation generally, not just Route: any CER application built on this base had unaudited user creation. Now audited via the existing primitive (§14) |
| Frontend bundle size | Low | Pre-existing, unchanged by this closure. Worth code-splitting before RTE08 |

---

**Proposed status: `RTE02 — Completed / Ready for CER Certification`.**
CER performs the final certification.
