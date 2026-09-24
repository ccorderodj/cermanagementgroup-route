# CER Route — RTE02 Addendum A01 Closure Delivery Report

| | |
|---|---|
| **Checkpoint** | RTE02 Addendum A01 — Final Admin UX Validation (closure) |
| **Delivery** | **002** |
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE02_ADDENDUM_A01_CLOSURE_INSTRUCTIONS_005.md` |
| **Baseline delivery** | `Report Delivery Rodrigo/CER_ROUTE_RTE02_ADDENDUM_A01_DELIVERY_REPORT_001.md` |
| **Source branch** | `feature/rte02-a01-closure-002` |
| **Base commit** | `58c1b92` (tip of `dev`) |
| **Candidate commit** | `[[CANDIDATE]]` |
| **Push / MR status** | `[[MR]]` |
| **Date** | 2026-09-24 |
| **Proposed status** | **RTE02-A01 — Completed / Ready for CER Certification** |

---

## 1. Did User Delete already exist in the UI?

**No.** A search across `features/SecurityUsers/` and `entities/UserManagement/` for any delete/remove affordance returned **zero matches**. Delivery 001 built and tested the backend flow (`DELETE /api/users/{id}` + `users.delete`), but no screen reached it.

So this closure added the **minimum integration**, reusing what already existed:

| Added | Where | Reuses |
|---|---|---|
| `deleteUserManagement` thunk | `entities/UserManagement/model/services/deleteUserManagement/` | exact shape of the existing `setUserAccess` thunk |
| `Remove from company` menu item | `features/SecurityUsers/ui/components/data-table-row-actions.tsx` | the existing contextual `DropdownMenu` |
| Destructive confirmation | same file | `ConfirmDestructiveDialog` from the Addendum |
| Capability-based visibility | same file | `useUser().hasUserPermission` — the mechanism the sidebar already uses |
| Row refresh after removal | `SecurityUsersPanel` | existing `fetchUserManagementPagination` |

**No backend change was required** — the endpoint and capability shipped in delivery 001.

No Route-specific user model, no duplicate user-management surface, no re-enrollment or reused-email logic. Core keeps ownership of identity.

Two guards in the UI, both mirroring rules the server already enforces:
- the action is hidden without `users.delete` — hiding is UX, the 403 is the control (invariant 8);
- the action is hidden on your own row, because removing yourself would drop you out of the screen you are working in.

---

## 2. Browser evidence

`tests/e2e/test_admin_lifecycle_browser.py` — **6 journeys, 6 passed**, driving the Microsoft Edge installed on the machine (`channel="msedge"`, no browser download) against a real `uvicorn` process on the test database.

Evidence is **resulting state, not clicks**: after every action the table is re-read, and where the property lives on the server (the Core user surviving, the membership tombstone) PostgreSQL is queried directly.

### Vehicles — `test_vehicle_lifecycle_in_the_browser`

| Step | Asserted result |
|---|---|
| Create from the page | row appears — no Postman, no API call |
| Active row menu | `Deactivate` and `Delete` visible; **`Reactivate` absent** |
| Deactivate | row leaves the table |
| Show inactive vehicles | row returns, badge reads **`Inactive`** (exact match) |
| Inactive row menu | `Reactivate` and `Delete` visible; **`Deactivate` absent** |
| Reactivate | badge reads **`Active`** (exact match) |
| Delete → Cancel | dialog closes and **the row is still there** — the confirmation is real |
| Delete → confirm | row gone **while "show inactive" is still checked** — this is Delete ≠ Deactivate, on screen |

### Vehicles, blocked delete — `test_a_vehicle_with_a_current_assignment_cannot_be_deleted_in_the_browser`

Vehicle with a current assignment → confirm Delete → dialog turns into **`Action unavailable`** and displays the server's own sentence, *"end the current vehicle assignment first"*. After closing, the vehicle is still listed: the block deleted nothing.

### Supervisor designations — `test_supervisor_designation_lifecycle_in_the_browser`

| Step | Asserted result |
|---|---|
| Active designation | `Remove designation` offered |
| Remove | row shows `Removed` |
| Inactive designation | `Restore designation` offered; **`Remove designation` absent** |
| Restore | `Removed` badge gone |
| Delete designation | confirmation required; afterwards the row no longer offers lifecycle actions |
| **Database** | `supervisor_profile.deleted_at` set · `user.is_active` still `True` · `user_company.deleted_at` still `NULL` |

The last row is the Addendum's central requirement for supervisors: **deleting the designation does not touch the person**.

### Standardized list values — `test_standard_value_lifecycle_in_the_browser`

| Step | Asserted result |
|---|---|
| Create + Edit (rename) | new label rendered |
| Deactivate | row leaves the normal view |
| Show inactive values | row returns |
| Inactive row menu | `Reactivate` offered, `Deactivate` absent |
| Reactivate | badge `Active` (exact) |
| Delete | confirmation required; row gone **with "show inactive" still checked** |
| **Operational selector** | `GET /api/standard-values/outcomes`, called from the browser with the Admin's own session, no longer returns the deleted label |

### Users — `test_user_delete_is_reachable_and_complete_from_the_admin_ui`

| Step | Asserted result |
|---|---|
| Authorized Route Admin | `Remove from company` visible in the row menu |
| Click | confirmation dialog appears |
| Cancel | user still listed |
| Confirm | row disappears from the tenant user list |
| **Database** | `user_company.deleted_at` set · `user` row still present and `is_active = True` |

### Users, unauthorized — `test_a_role_without_the_capability_never_sees_user_delete`

`manager` (has `users.update`, lacks `users.delete`) opens the same row menu: `Edit` is visible, `Remove from company` is **absent**. Paired with the existing integration test `test_removing_a_user_requires_the_delete_capability`, which proves the server returns 403 regardless of what the UI shows.

---

## 3. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Gap |
|---|---|---|---|
| User Delete executable from normal Admin UI | added (did not exist) | §1, `test_user_delete_is_reachable_and_complete_from_the_admin_ui` | — |
| Reuses Core user management, no duplicate domain | `SecurityUsersPanel` + `entities/UserManagement` | §1 | — |
| User Delete requires confirmation | `ConfirmDestructiveDialog` | Cancel step in the same test | — |
| Authorized server-side; unavailable without `users.delete` | 403 server-side, hidden in UI | `test_a_role_without_the_capability_never_sees_user_delete` + `test_removing_a_user_requires_the_delete_capability` | — |
| Removes only tenant membership, preserves platform identity | membership tombstone | DB assertions in the same test | — |
| Vehicle Deactivate/Reactivate/Delete in the browser | — | `test_vehicle_lifecycle_in_the_browser` | — |
| Supervisor Deactivate/Reactivate/Delete in the browser | — | `test_supervisor_designation_lifecycle_in_the_browser` | — |
| Standard value Deactivate/Reactivate/Delete in the browser | — | `test_standard_value_lifecycle_in_the_browser` | — |
| Rows expose only contextually valid actions | `LifecycleRowActions` | absence assertions in all three journeys | — |
| Blocked Delete shows a clear business reason | server message in the dialog | `test_a_vehicle_with_a_current_assignment_cannot_be_deleted_in_the_browser` | — |
| Deleted records do not leak into Admin lists or selectors | DAO filtering | delete steps asserted with "show inactive" checked; selector queried live | — |
| No RTE03 behavior changes | none | §6 | — |
| No RTE04 / odometer started | none | §6 | — |
| Changed code passes regression | see §5 | §5 | — |

---

## 4. Code changed by this closure

| File | Change |
|---|---|
| `entities/UserManagement/model/services/deleteUserManagement/deleteUserManagement.ts` | **new** — delete thunk |
| `entities/UserManagement/model/services/index.ts` | export the thunk |
| `features/SecurityUsers/ui/components/data-table-row-actions.tsx` | `Remove from company` item, confirmation, capability and self-row guards |
| `features/SecurityUsers/ui/SecurityUsersPanel.tsx` | `onDeleted` → refresh the page after removal |
| `tests/e2e/conftest.py` | shared browser harness (`live_server`, `lanzar_edge`, `abrir_sesion`), **function-scoped** — see §5 |
| `tests/e2e/test_admin_lifecycle_browser.py` | **new** — the six journeys |
| `tests/e2e/test_work_session_offline_browser.py` | duplicated harness removed; now uses the shared one. **No behavioral change** — see §5 |

**No backend file was modified by this closure.** No product behavior was changed; the only corrections were to the test harness.

---

## 5. Failures that occurred, and what they were

Reported because they happened, not only the final green.

### 5.1 — Fixed sleeps hid a moving target (test defect)

Three browser journeys failed at first. Diagnosis by instrumenting the browser rather than guessing:

**`CONFIRMED`** — `VehiclesPanel.cargar()` sets `loading = true`, and the panel **unmounts the whole table** while reloading (`{!loading && vehicles.length > 0 && <Table>}`). Fixed waits of 400–600 ms landed inside an in-flight reload, so the assertion read zero rows. In the standard-values journey the same root cause surfaced differently: acting on a half-finished reload sent a **stale `version`**, the server correctly answered 409, and nothing was deleted.

A second, quieter defect in the same tests: `text=Active` matches by substring, so **`Inactive` satisfied it**. That assertion could never have failed.

**Correction:** removed every `wait_for_timeout` from the journeys and replaced them with Playwright `expect(...)` assertions that retry until the real state holds, plus `get_by_text(..., exact=True)` for the status badges. **No product code was changed** — the product was behaving correctly throughout.

### 5.2 — A latent fragility in the RTE03 browser harness (test defect)

After the new module was added, `test_queued_start_work_survives_reload_and_reauthentication` began failing with a login `401` when the whole `tests/e2e/` directory ran, while passing in isolation.

**`CONFIRMED`** — that test's `live_server` was **module-scoped**. pytest instantiates higher-scoped fixtures first, so the server's readiness probe (`GET /login` with `Host: alpha.localhost`) ran **before** `seeded`, caching the *previous* module's `company_id` in the tenant resolver for 60 s. `seeded` then re-seeded with new ids, and the browser authenticated against a company that no longer existed. In isolation there was no previous seeding to cache, which is why it never surfaced before.

**Correction:** the duplicated harness was deleted from that module and both browser modules now share the **function-scoped** `live_server` in `tests/e2e/conftest.py`, which is requested *after* `seeded`. RTE03's assertions and product behavior are untouched; `tests/e2e/` now runs **7 passed**.

This was a pre-existing fragility exposed by adding a second browser module, not a defect introduced by this closure.

### 5.3 — New files not yet tracked by git (process defect)

The first full regression ended **465 passed, 1 failed**: `test_every_relative_import_resolves_to_a_versioned_file`.

**`CONFIRMED`** — `deleteUserManagement.ts` existed on disk and was imported from `services/index.ts`, but was not yet staged in git. A fresh clone would not have built. The same net caught the same class of mistake in delivery 001; this is the repository's architecture net doing exactly its job.

**Correction:** files staged, net re-run green (62 passed), full suite re-run to confirm an intact green rather than a fix verified only in isolation.

---

## 6. Regression

| Scope | Command | Result |
|---|---|---|
| Browser — Admin lifecycle (new) | `uv run pytest tests/e2e/test_admin_lifecycle_browser.py` | **6 passed** |
| Browser — all, incl. RTE03 | `uv run pytest tests/e2e/` | **7 passed** |
| Frontend typecheck | `npm run typecheck` | **0 errors** |
| Frontend lint | `npm run lint:ts` | **0 errors** |
| Production build | `npm run build:prod` | compiled; 2 pre-existing warnings (Sass legacy API, bundle size) |
| Architecture nets | `uv run pytest tests/test_permission_catalog.py tests/test_public_surface.py tests/test_page_wiring.py tests/test_navigation_wiring.py tests/test_frontend_source_completeness.py` | **62 passed** |
| Full backend suite | `uv run pytest` | **466 passed**, 0 failed, **exit code 0** (460 at delivery 001; +6 browser journeys) |

**Environment:** local development and test databases only. No shared or production environment was touched.

The RTE02-A01 backend regression from delivery 001 remains applicable unchanged, since no backend file was modified here.

---

## 7. Confirmation — scope not started

No backend file was modified. `git diff` against `app/routers_api/worksessions/` is empty; RTE03 Work Session lifecycle, Start/End Work, the vehicle/MPG snapshot and `route.worksession.execute` are untouched. The only RTE03 file changed is its browser **test harness** (§5.2), with no assertion or behavior altered.

Nothing was created for: identity re-enrollment, same-person matching, reused-email reassignment, a Redux/DataTable refactor, unrelated frontend debt, Work Session changes, Trip, Activity, odometer, camera, OCR, GPS/geolocation, routing mileage, fuel, Reports, Today/Live, or any RTE04 functionality.

The tombstone strategy, Delete vs Deactivate semantics, the Vehicle Assignment lifecycle, Core ownership of Users, the terminal User Delete behavior, the eight list codes, the 28 approved values and the provisioning rules are all unchanged.

No STOP condition was triggered.

---

## 8. Remaining PENDING VALIDATION

| Item | Status |
|---|---|
| Admin lifecycle UX on desktop Edge | **Validated** — §2 |
| Admin lifecycle UX on other desktop browsers (Firefox, Safari) | **PENDING VALIDATION** — not required by this closure |
| Admin UX on real mobile hardware | **PENDING VALIDATION** — the Admin is a desktop surface; Mobile-only applies to the Supervisor shell |
| Unit tests for the new React components | **NOT APPLICABLE** — the repository has no JS test runner; behavior is covered end-to-end by the browser journeys |

### Operational action, unchanged from delivery 001

Wherever this is deployed, and **not performed by the local work**:
- `alembic upgrade head` to apply `0004_admin_lifecycle`;
- `uv run python -m app.db.scripts.bootstrap` to seed `users.delete` and the 28 initial values. **Without it, the new Remove action stays hidden for every role**, because the capability would not exist in that database.

---

## 9. Proposed status

**RTE02-A01 — Completed / Ready for CER Certification.**

Both closure items are answered. User Delete did not exist in the UI and now does, reusing Core user management with confirmation and capability gating. The lifecycle surfaces are validated in a real browser, asserting resulting state rather than clicks, with server-side properties confirmed directly in PostgreSQL.

Two defects were found and fixed during validation; both were in test code, not in the product. The item from delivery 001 that needed CER attention — user delete being terminal under the deferred re-enrollment model — is unchanged and still stands as documented.

Work stops here. RTE04 and the odometer checkpoint were not started.
