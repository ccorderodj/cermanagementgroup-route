# CER Route — RTE02 Addendum A01 Delivery Report

| | |
|---|---|
| **Checkpoint** | RTE02 Addendum A01 — Admin UX Lifecycle + Initial Standardized Values |
| **Delivery** | **001** |
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE02_ADDENDUM_A01_DEVELOPMENT_INSTRUCTIONS_004.md` |
| **Source branch** | `feature/rte02-a01-admin-lifecycle` |
| **Base commit** | `30f875f` (tip of `dev`) |
| **Candidate commit** | `1237556` (plus this metadata follow-up) |
| **Push / MR status** | Pushed. [merge_requests/8](https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/8) **open, not merged** — awaiting CER validation |
| **Date** | 2026-09-24 |
| **Proposed status** | **RTE02-A01 — Completed / Ready for CER Validation** |

---

## 1. Precondition note

The instruction states *"Applies after: RTE03 — COMPLETED / CERTIFIED"*.

At the time this work started, RTE03 was **delivered but not certified**: closure delivery 002 is open with two pending CER decisions (the pre-certification merges to `dev`, and the two time-tolerance constants). Work proceeded on explicit instruction from the developer.

Nothing in this Addendum changes RTE03 behavior — see §12.

---

## 2. The central decision: tombstone, not physical delete

The Addendum requires Delete to be genuinely different from Deactivate, while keeping historical integrity, and explicitly permits *"a safe physical delete or a tombstone/retained-reference strategy"*.

**Physical delete was not an available option.** The database already forbids it:

| Reference | Constraint | Consequence of a physical delete |
|---|---|---|
| `work_session.vehicle_id` → `vehicle` | `RESTRICT` | PostgreSQL rejects deleting a vehicle with any work session |
| `vehicle_assignment.vehicle_id` → `vehicle` | `RESTRICT` | Same for any assignment, current or historical |
| `vehicle_assignment.supervisor_profile_id` → `supervisor_profile` | `CASCADE` | Would silently destroy the person's entire vehicle history |
| `supervisor_profile.(user_id, company_id)` → `user_company` | `CASCADE` | Deleting a membership would destroy their Route designation and, through it, their assignment history |
| `standard_value.id` | referenced by RTE04/RTE05 activities | Would orphan future historical records |

So: a `deleted_at timestamptz NULL` tombstone (`app/core/models/SoftDelete.py`), and **every normal query filters `deleted_at IS NULL`**. The Addendum's requirement that *"the internal persistence strategy must not leak tombstones back into normal Admin UX"* is met by filtering at the DAO layer, not by remembering to filter at each call site.

### The consequence that had to be solved

Three unique constraints would have made delete irreversible in a way the Admin could not understand — a conflict against a row they can no longer see. They became **partial unique indexes** (`WHERE deleted_at IS NULL`):

| Index | Without the change |
|---|---|
| `uq_vehicle_company_unit` | Deleting "V-014" would block ever creating another "V-014" |
| `uq_standard_value_company_list_label` | Deleting "Escalated" would block recreating it |
| `uq_supervisor_profile_company_user` | Deleting a designation would block re-designating that person |

`uq_standard_value_company_seed_key` is deliberately **not** partial — see §5.

---

## 3. Lifecycle by entity

| Entity | Create | Read | Edit | Deactivate | Reactivate | Delete | Delete blocked when |
|---|---|---|---|---|---|---|---|
| **Vehicle** | yes | yes | yes | yes | yes | **new** | a current assignment exists |
| **Supervisor designation** | yes | yes | n/a¹ | yes | yes | **new** | a current assignment exists |
| **Vehicle assignment** | yes | yes | — | End | Replace | **not added**² | — |
| **Standard list value** | yes | yes | yes | yes | yes | **new** | — |
| **User (tenant level)** | yes | yes | yes | yes (suspend) | yes (restore) | **new** | deleting yourself |

¹ The Route profile has no editable fields of its own; the person is edited in Core user management, which owns that concern.
² Per §6 of the instruction, assignment history keeps `Create / Read / End / Replace / History` and receives no destructive Delete.

### What Delete does, precisely

- Removes the record from the active list, the inactive list and operational selectors.
- Leaves the row in the database with `deleted_at` set, so historical references resolve.
- Is audited with the full prior state, because the screen can no longer show what was removed.
- Is rejected with **404** on a second attempt — the same treatment as another tenant's record: existence is not confirmed for something the Admin can no longer see.

### Users: membership, not identity

Deleting a user at tenant level marks `user_company.deleted_at`. The `user` row is untouched: it may belong to other companies and to the platform plane, and destroying it to remove someone from **one** tenant would be disproportionate and outside that Admin's authority.

**This is not cosmetic.** Both authentication gates require `deleted_at IS NULL`:

- `UsersDAO.find_active_membership` — authorizes every request
- `UsersDAO.find_login_candidate` — authenticates every login

A removed user cannot log in, and an already-open session stops authorizing on its next request (403 — the token is still valid; what no longer exists is their access to this company).

---

## 4. Exact initial values provisioned

28 values across the eight lists, exactly as approved — no synonyms, no extras. Source: `app/routers_api/standardvalues/provisioning.py`.

| List | Values |
|---|---|
| Client Visit Activities | Staffing Follow-up · Service Review · Attendance Follow-up · Safety Follow-up |
| Recruiting Activities | Candidate Sourcing · Hiring Event · Referral Follow-up |
| Employee Visit Reasons | Attendance Issue · Document Follow-up · Transportation Issue · Employee Support |
| Delivery Types | Payroll Check · Document Delivery · Equipment Delivery |
| Office Purposes | Paperwork · Meeting · Pickup / Drop-off · Administrative Follow-up |
| Other Activities | Housing Visit · Transportation Support · Supply Pickup |
| Outcomes | Completed · Follow-up Required · Escalated · No Contact |
| Received By | Employee · Authorized Person · Office Staff |

The tuple order **is** the `sort_order`: what CER numbered 1, 2, 3 appears in that order on screen.

**Not created:** no catalogs for Client Visit destination, Recruiting Area/Location, Employee/Reference, Office, or Other Area/Location. No `clientRefs`, `employeeRefs`, `recruitingAreas` or `offices` collections. Those fields stay free text.

`Outcomes` remains tenant data — rows in `standard_value`, not a hardcoded enum.

---

## 5. Provisioning idempotency

A provisioner that only avoids duplicates is not enough. Four things must not happen on re-run, and comparing by label fails all four — the moment an Admin renames "Escalated", the next run stops recognising it and creates a duplicate.

The marker is **`seed_key`**: the stable identity of a seeded value, derived from the *approved* label, which survives renaming, deactivation and the tombstone. The provisioner asks one question — *"have I already seeded this key in this company?"* — and if the answer is yes, it touches nothing.

| Required behavior | How it holds |
|---|---|
| Fresh tenant receives the values | No `seed_key` rows present → all 28 created |
| Re-run creates no duplicates | Keys present → skipped |
| A renamed seed is not reset | Lookup is by key, not label; the label is never rewritten |
| A deleted seed is not resurrected | The key query deliberately **ignores** `deleted_at` |
| A deactivated seed is not reactivated | The key query deliberately **ignores** `is_active` |
| Tenant-safe | Reads and writes are scoped to `company_id` in both directions |

`seed_key` is `NULL` for anything the Admin creates, so no provisioning run will ever touch tenant-authored values.

Wired into `app/db/scripts/bootstrap.py`, which prints what it created and what it left alone. It is a reusable function, not script-local logic, so a future tenant-creation path can call it inside its own transaction.

---

## 6. Admin UX implemented

Two new shared components in `features/Common` — there was **no destructive-confirmation dialog anywhere in the frontend** before this:

- **`LifecycleRowActions`** — state-aware contextual menu. An active row offers Edit · Deactivate · Delete; an inactive row offers Edit · Reactivate · Delete. Never both transitions at once. Delete is last, separated, and destructive-coloured.
- **`ConfirmDestructiveDialog`** — confirmation before delete, and the same dialog inverted when the server refuses: it explains the business reason in plain language and offers only Close.

Wired into `VehiclesPanel`, `SupervisorSetupPanel` and `StandardValuesPanel`. Create remains a page-level primary action in each. Vocabulary aligned from "Retire/Restore" to "Deactivate/Reactivate", which is what the Addendum names.

Blocked delete surfaces the server's own message, e.g. `Delete unavailable — end the current vehicle assignment first.` The backend is authoritative: the dialog is UX, and the request still fails with 409 if the UI is stale (invariant 8).

Users are administered through the existing Core `SecurityUsersPanel`, reused as-is. No duplicate Route user domain was introduced.

---

## 7. Authorization

| Action | Capability | Notes |
|---|---|---|
| Delete standard value | `route.standardvalues.manage` | reused |
| Delete vehicle | `route.vehicles.manage` | reused |
| Delete supervisor designation | `route.vehicles.manage` | reused |
| Delete user from company | **`users.delete`** | **new — see below** |

### The one capability gap, documented

`users.update` is defined in the catalog as *"Edit users and suspend their access"*. Tenant-level removal is materially stronger than suspension, and folding it into `users.update` would hand delete to every existing holder through a silent scope change.

The catalog already separates `roles.delete` from `roles.update` for exactly this reason, so `users.delete` follows established precedent rather than inventing one.

Granted to `owner`, `admin` and `route_admin`. **Not** granted to `manager` — the Addendum only requires Route Admin, and minimum privilege applies.

`tests/test_permission_catalog.py` passes, which is the proof that the capability protects a real endpoint and is not orphan.

All authorization is server-side and tenant-scoped. No path grants platform-superuser privilege; `is_superuser` is untouched by every lifecycle action.

---

## 8. Audit

Every Delete records tenant, actor, entity, action, timestamp and the **full prior state** — because the screen can no longer show what was removed, the trail is the only remaining way to reconstruct it.

| Entity | `entity_type` | action |
|---|---|---|
| Standard value | `standard_value` | `delete` |
| Vehicle | `vehicle` | `delete` |
| Supervisor designation | `supervisor_profile` | `delete` |
| User membership | `user` | `delete` |

Existing Create/Edit/Deactivate/Reactivate/assignment/reorder auditing is unchanged. No secrets or credentials are logged. `audit_event` remains append-only.

---

## 9. Data / schema changes

Migration **`0004_admin_lifecycle`** (revises `0003_work_session`).

| Change | Table |
|---|---|
| `+ deleted_at timestamptz NULL` | `vehicle`, `supervisor_profile`, `standard_value`, `user_company` |
| `+ seed_key varchar(80) NULL` | `standard_value` |
| unique → **partial** unique index | `uq_vehicle_company_unit`, `uq_standard_value_company_list_label`, `uq_supervisor_profile_company_user` |
| `+ uq_standard_value_company_seed_key` | `standard_value` (full, not partial — deliberate) |

**No data is reinterpreted.** `deleted_at` starts `NULL` everywhere: nothing was deleted before, because delete did not exist. `seed_key` starts `NULL`: pre-existing values are treated as tenant-authored and no provisioning run will ever touch them.

Known `downgrade` limit: it restores the full unique constraints, so it fails if tombstoned rows collide by then (two "V-014", one deleted). Failing is correct — undoing the schema cannot decide which row should survive.

---

## 10. Tests and evidence

New file: `tests/integration/test_admin_lifecycle.py` — **61 tests, 61 passed**.

### The discriminating test

The Addendum requires proof that a single status flag cannot explain both outcomes. Every entity uses the same shape: create **two** records, deactivate one and delete the other, then assert the inactive view contains **exactly one**. A shared `is_active` cannot produce that result.

`test_delete_is_not_a_synonym_for_deactivate`, `test_vehicle_delete_is_not_a_synonym_for_deactivate`, `test_user_delete_is_not_a_synonym_for_suspend`.

### Coverage map

| Requirement | Tests |
|---|---|
| Deactivate removes from use, stays in inactive view | `test_deactivate_removes_from_operational_use_but_keeps_it_in_admin` |
| Reactivate restores | `test_reactivate_restores_the_value`, `test_a_deactivated_vehicle_can_be_reactivated` |
| Delete removes from both views | `test_delete_removes_the_value_from_both_admin_views` |
| Delete ≠ Deactivate | the three discriminating tests above |
| Row survives for history | `test_the_deleted_row_survives_for_history`, `test_the_designation_row_survives_for_history` |
| Deleted value gone from operational selectors | asserted inside the vehicle discriminating test |
| Label / unit freed for reuse | `test_deleting_frees_the_label_for_reuse`, `test_deleting_a_vehicle_frees_its_unit` |
| All eight lists | `test_every_list_supports_delete`, `test_each_list_gets_its_initial_values_in_order` (parameterized ×8) |
| Initial values exact | `test_a_fresh_tenant_receives_the_exact_approved_values` |
| Provisioning idempotency (5 rules) | `test_provisioning_twice_creates_no_duplicates`, `..._renamed_..._not_reset`, `..._deleted_..._not_resurrected`, `..._deactivated_..._not_silently_reactivated`, `test_provisioning_is_tenant_safe` |
| Current assignment blocks delete | `test_a_current_assignment_blocks_vehicle_delete`, `test_a_current_assignment_blocks_designation_delete` |
| Delete works after ending the assignment | `test_after_ending_the_assignment_the_vehicle_can_be_deleted` |
| Work session snapshot readable after | `test_a_work_session_snapshot_survives_the_vehicle_delete` |
| Assignment history survives | `test_assignment_history_survives_the_vehicle_delete` |
| Designation delete preserves Core user | `test_deleting_a_designation_does_not_delete_the_core_user` |
| Person re-designable after delete | `test_a_deleted_designation_can_be_created_again`, `..._leaves_the_person_as_a_candidate` |
| Authorized user can, unauthorized cannot | `test_route_admin_can_remove_a_user_from_the_company`, `test_removing_a_user_requires_the_delete_capability` |
| Removed user cannot authenticate | `test_a_removed_user_cannot_log_in` |
| Removed user loses an open session | `test_a_removed_user_loses_authorization_on_an_open_session` |
| Platform identity preserved | `test_removing_a_user_preserves_the_platform_identity` |
| No superuser escalation | `test_removing_a_user_does_not_grant_platform_privilege` |
| Cannot remove yourself | `test_nobody_can_remove_their_own_access` |
| Cross-tenant rejected | `test_one_tenant_cannot_delete_another_tenants_value`, `..._vehicle`, `..._membership` |
| Route history survives membership delete | `test_removing_a_user_keeps_their_route_history_readable` |
| Audit | `test_every_delete_is_audited`, `test_the_audit_records_who_acted_and_what_was_removed` |

### Failures that occurred during development

Reported because they happened, not only the final green:

| Failed | Cause | Resolution |
|---|---|---|
| `test_vehicle_delete_is_not_a_synonym_for_deactivate` | `CONFIRMED` — the test used `GET /api/vehicles`, which is the **assignment selector** and already filtered `is_active=True` by design | Switched to `/api/vehicles/pagination`, and **added** an assertion on the selector, which the Addendum also requires |
| 3 × `KeyError: 'items'` | `CONFIRMED` — pagination returns `results`, not `items` | Key corrected |
| `assert 403 == 401` | `CONFIRMED` — a session whose membership is deleted gets **403**: the token is valid, the company access is not | Expectation corrected to the established contract |
| 1181 × `linebreak-style` | `CONFIRMED` — Python's `write_text` emits CRLF on Windows | 7 files normalized to LF in binary |
| `test_every_relative_import_resolves_to_a_versioned_file` (full regression) | `CONFIRMED` — the two new `features/Common` components existed on disk but were **not yet tracked by git**, so a fresh clone would have failed to build | Files staged; net re-run green |

None was a product defect. The first improved coverage, and the last is the repository's own architecture net doing exactly its job — catching a module that exists locally but would be missing for everyone else.

---

## 11. Regression

| Scope | Command | Result |
|---|---|---|
| Admin lifecycle (new) | `uv run pytest tests/integration/test_admin_lifecycle.py` | **61 passed** |
| Architecture nets (capability catalog, public surface, page wiring, navigation wiring, frontend source completeness) | `uv run pytest tests/test_permission_catalog.py tests/test_public_surface.py tests/test_page_wiring.py tests/test_navigation_wiring.py tests/test_frontend_source_completeness.py` | **62 passed** |
| Full backend suite | `uv run pytest` | **460 passed**, 0 failed, **exit code 0** (399 before this Addendum; +61 new) |
| Frontend typecheck | `npm run typecheck` | **0 errors** |
| Frontend lint | `npm run lint:ts` | **0 errors** |
| Production build | `npm run build:prod` | compiled; 2 pre-existing warnings (Sass legacy API, bundle size) |
| Migration | `alembic upgrade head` | PASS |
| Migration roundtrip | `alembic downgrade -1 && upgrade head` | PASS |
| Schema drift | `alembic check` | `No new upgrade operations detected.` |
| Alembic heads | `alembic heads` | `0004_admin_lifecycle` — **1 head** |
| App import | `python -c "import app.main"` | OK |

**Environment:** all of the above ran against the **local development and test databases**. No shared or production environment was touched.

---

## 12. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Gap |
|---|---|---|---|
| Create is a page-level primary action | yes, in all three panels | §6 | — |
| Active row: Edit + contextual Deactivate/Delete | `LifecycleRowActions` | §6 | — |
| Inactive row: Reactivate/Delete, not Deactivate | state-aware by construction | §6 | — |
| Delete requires confirmation | `ConfirmDestructiveDialog` | §6 | — |
| Blocked delete explains the reason | server message shown in the dialog | §6, `test_a_current_assignment_blocks_vehicle_delete` | — |
| No Postman / DB access needed | full lifecycle reachable from Admin | §6 | — |
| Core user management reused | `SecurityUsersPanel` unchanged | §6 | — |
| No duplicate Route user domain | none created | §6 | — |
| Tenant Delete removes from tenant experience | membership tombstone | §3, `test_route_admin_can_remove_a_user_from_the_company` | — |
| Delete does not destroy shared identity | `user` untouched | `test_removing_a_user_preserves_the_platform_identity` | — |
| Deactivate/Reactivate still separate | unchanged endpoints | §3 | — |
| No identity re-enrollment | none added | §13 item 1 | deferred by instruction |
| Designate / deactivate / restore supervisor | unchanged + delete added | §3 | — |
| Designation delete preserves Core user | yes | `test_deleting_a_designation_does_not_delete_the_core_user` | — |
| Vehicle full lifecycle from Admin | yes | §3, §6 | — |
| Vehicle with current assignment cannot be deleted | server-enforced | `test_a_current_assignment_blocks_vehicle_delete` | — |
| Backend independently enforces it | service-level check, not UI | §6 | — |
| Historical assignments + snapshots valid | tombstone | `test_assignment_history_survives...`, `test_a_work_session_snapshot_survives...` | — |
| Assignments keep Create/Read/End/Replace/History | unchanged | §3 | — |
| No destructive Delete on assignments | none added | §3 | — |
| Eight list codes visible and manageable | unchanged | §4 | — |
| Values support the full lifecycle | delete added | `test_every_list_supports_delete` ×8 | — |
| Deleted values gone from lists and selectors | DAO filtering | §2, §10 | — |
| List codes not deletable by tenant | still a `BusinessEnum` | §4 | — |
| Outcomes remain tenant data | unchanged | §4 | — |
| All exact initial values provisioned | 28 values | `test_a_fresh_tenant_receives_the_exact_approved_values` | — |
| No extra prototype catalogs | none | §4 | — |
| Free-text fields stay free text | untouched | §4 | — |
| Provisioning idempotent (5 rules) | `seed_key` | §5, 5 tests | — |
| Server-side authorization everywhere | yes | §7 | — |
| Cross-tenant rejected | yes | §10 | — |
| Audit covers lifecycle changes | yes | §8 | — |
| RTE03 Work Session unchanged | no file under `worksessions/` modified | §13 | — |
| Backend suite green | see §11 | §11 | — |
| Frontend checks green | 0 / 0 / compiled | §11 | — |
| No RTE04 or odometer started | none | §14 | — |

---

## 13. Deviations, technical debt and pending items

**1 — User delete is terminal under the current model.** `DEVIATION (documented)`
`uq_user_company_user_company` was deliberately **not** made partial. Making it partial would enable creating a second membership row for the same person — which is identity re-enrollment, explicitly deferred by §3 of the instruction. Consequence: a removed person cannot be re-added to that company without re-enrollment. This matches the instruction's own operational guidance: *"If the same person may return under the current model, normal operational guidance remains to use Deactivate rather than inventing identity recovery behavior in this sprint."*

**2 — Pre-existing Route Admin frontend debt.** `TECHNICAL DEBT`
The three Route panels violate two `AGENTS.md` rules that predate this Addendum: they use raw `<Table>` instead of `DataTable`/`DataTablePagination` (frontend rule 9), and they call endpoints directly from the panel instead of dispatching thunks against selectors (frontend rule 3) — there are no Redux slices for any Route entity. **Not corrected here**, deliberately: migrating three panels to Redux + DataTable is a state-management refactor outside the approved delta and would add risk immediately before RTE04. Cause: `UNVERIFIED` — not investigated. Recommend CER schedule it as its own delta.

**3 — Fixed in passing: the Vehicles panel could never show an inactive vehicle.** `PRE-EXISTING DEFECT, CORRECTED`
`VehiclesPanel` loaded through `GET /vehicles`, which the backend documents as the **assignment selector** and filters `is_active=True`. The panel rendered a "Retired" badge and a "Restore" button that were unreachable: deactivating a vehicle removed it from the screen with no way to bring it back from the product. Cause: `CONFIRMED`. This blocked the Addendum criterion *"Inactive records expose Reactivate/Delete"*, so it entered scope: added `fetchVehiclesForAdmin` (via `/vehicles/pagination`) and a "Show inactive vehicles" toggle.

**4 — No frontend automated tests.** `PENDING VALIDATION`
The repository has no JS test runner. The new components were validated by typecheck, lint and production build; their runtime behavior in a browser is **not** covered by an automated test in this delivery. Browser-level validation exists only for the RTE03 offline queue (`tests/e2e/`), which this Addendum does not touch.

**5 — Operational action for shared environments.** `ACTION REQUIRED`
Two steps must run wherever this is deployed, and the local work does **not** perform them elsewhere:
- `alembic upgrade head` to apply `0004_admin_lifecycle`;
- `uv run python -m app.db.scripts.bootstrap` to seed the new `users.delete` capability **and** the 28 initial standardized values. Existing tenants do not receive the values until this runs.

---

## 14. Confirmation — scope not started

No file under `app/routers_api/worksessions/` was modified. RTE03 Work Session lifecycle, Start/End Work, the vehicle/MPG snapshot, `route.worksession.execute`, the Supervisor-only grant, Routing Mileage, the Mobile-only Supervisor decision, the fixed FuelGrade values, the eight fixed list codes, Outcomes as tenant data, and the approved free-text fields are all unchanged.

Nothing was created for: Trip, Trip Purpose, Start Trip / On Route / Arrived / Change Plan / Home Trip, Activity execution, geolocation, GPS permission, routing mileage, fuel calculation, odometer, camera, OCR, odometer exception workflow, Today/Live, Reports, post-close corrections, Supervisor Desktop, identity re-enrollment, generic-email reassignment, new tenant-defined list codes, or any RTE04 functionality.

No STOP condition was triggered.

---

## 15. Proposed status

**RTE02-A01 — Completed / Ready for CER Validation.**

Delete is genuinely distinct from Deactivate and proven so by tests that a single status flag cannot satisfy. The exact approved values are provisioned idempotently in a way that never overrides a tenant decision. Server-side authorization, tenant isolation and audit hold across every new action.

Two items need CER attention: the terminal nature of user delete under the deferred re-enrollment model (§13 item 1), and whether to schedule the pre-existing Route Admin frontend debt as its own delta (§13 item 2).

Work stops here. RTE04 and the odometer checkpoint were not started.
