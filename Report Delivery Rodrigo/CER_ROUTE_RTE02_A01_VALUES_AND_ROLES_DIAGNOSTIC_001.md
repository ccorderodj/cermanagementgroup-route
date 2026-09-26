# CER Route — RTE02-A01 Diagnostic: Standard Values + Roles

| | |
|---|---|
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE02_A01_VALUES_AND_ROLES_DIAGNOSTIC_006.md` |
| **Type** | Diagnostic — evidence first, no product behavior changed |
| **Date** | 2026-09-26 |
| **Branch** | `feature/rte04-c1-closure-c2` |
| **Outcome** | **STOPPED for CER review.** One `SECURITY GAP` found; two `CONFIGURATION/ENVIRONMENT` root causes found |
| **RTE04 / RTE05** | **Unchanged.** No business flow, guard or schema of RTE03/RTE04 was touched |

---

## 0. The three things that matter

**1. A privilege escalation is live, and it is exploitable end to end.** A user holding only `route_admin` permissions can create an account with the `owner` role, set its password, sign in as it, and then do things `route_admin` cannot — including deleting a role, which the catalog deliberately withholds even from `admin`. Tested against the API, not inferred from the UI. This is §11's first STOP condition, so the fix was **not** started.

**2. The missing Standardized Values are not a code or UI defect.** The reviewed tenant has **zero rows** in `standard_value` — the whole table is empty in that database. The code still defines exactly the 28 approved values, and the Admin screen renders all eight lists correctly when the values exist. What is missing is provisioning in that environment.

**3. The same root cause is breaking more than the values.** In the reviewed environment the `supervisor` role has **zero capabilities**, so the entire RTE03/RTE04 Supervisor experience — Work Session, Trip, odometer — cannot run there at all. Three capabilities were never seeded. This has not been reported before and it is more disruptive than the symptom that prompted the diagnostic.

---

## 1. Exact environment and tenant inspected (§2.1)

| Item | Value |
|---|---|
| Application | CER Route (`APP_NAME = "CER Route"`) |
| Environment / mode | `MODE = DEV` |
| Database actually connected | **`cer_route`** on `localhost:5432` |
| Test database (separate) | `cer_time_test` — **not** the one the browser uses |
| `BASE_DOMAIN` | `localhost` |
| `BOOTSTRAP_COMPANY_SUBDOMAIN` (`.env`) | `cerroute` |
| Tenant present in `cer_route` | **exactly one**: `id=1`, `CER Management Group LLC`, subdomain `cerroute` |
| Tenant created at | **2026-09-22 15:11:58 UTC** |
| Schema state | 30 tables — schema applied |

**One caveat, stated plainly.** This is the local development environment on this machine. I cannot see the Product Owner's browser, so I cannot prove it is the same database they are reviewing. What I can say is that this environment reproduces the reported symptom exactly, and that only one tenant exists here, so there is no chance of having inspected the wrong one *within* this environment. §11 lists "the current tenant is not the tenant the Product Owner believes is being reviewed" as a STOP condition; if the review is happening against a shared or hosted environment, this section must be re-run there before acting on §3.

A configuration detail worth recording: `BOOTSTRAP_COMPANY_SUBDOMAIN` is read by `bootstrap.py` from `os.environ` after its own `load_dotenv()` call, and is **not** a field on `Settings`. So it applies when bootstrap runs, and the running application never reads it. That is correct behavior, not a defect, but it means the value cannot be verified from the application's own settings.

---

## 2. Approved source re-verified (§2.2)

`INITIAL_VALUES` was compared against `_cer_delivery/CER_ROUTE_RTE02_ADDENDUM_A01_DEVELOPMENT_INSTRUCTIONS_004.md` **mechanically** — the document was parsed and the labels compared character by character, not read over.

| List | Approved | In code | Same order |
|---|---|---|---|
| Client Visit Activities | 4 | 4 | yes |
| Recruiting Activities | 3 | 3 | yes |
| Employee Visit Reasons | 4 | 4 | yes |
| Delivery Types | 3 | 3 | yes |
| Office Purposes | 4 | 4 | yes |
| Other Activities | 3 | 3 | yes |
| Outcomes | 4 | 4 | yes |
| Received By | 3 | 3 | yes |
| **Total** | **28** | **28** | — |

**Result: identical.** No synonyms, nothing extra, nothing missing, same order — and the order matters, because the document's numbering is the `sort_order` the Supervisor sees on the phone.

This comparison is now a permanent net: `tests/test_standard_value_catalog.py`, 12 tests. It was verified to actually fail — changing `Attendance Issue` to `Attendance Problem` made it fail and name the exact list. The pre-existing test compared the database against `INITIAL_VALUES`, which means the code was checking itself; a label edited to a synonym would have passed.

---

## 3. Actual tenant data (§2.3) — the 28-value matrix

Captured **before** modifying anything. Nothing was modified.

```sql
SELECT company_id, list_code, count(*) ... FROM standard_value GROUP BY ...
→ 0 rows
```

**The `standard_value` table is empty across the entire `cer_route` database.** Not filtered, not deactivated, not tombstoned — absent.

So the matrix collapses to one row, repeated 28 times:

| Approved value | DB state | API state | UI state |
|---|---|---|---|
| all 28, in all 8 lists | **no row at all** | `[]` — empty array, HTTP 200 | list shown with counter `0`, no rows |

There is nothing to distinguish between "deleted", "deactivated" and "never created" *per value*, because no row exists in any state. That matters for §3 of the instruction: this is **not** the case of values deliberately retired by the tenant, so restoring them would not override any tenant decision.

---

## 4. Was provisioning applied to this tenant? (§2.4)

**No.** Three independent pieces of evidence agree:

| Evidence | What it shows |
|---|---|
| Zero rows with a `seed_key` | `provision_standard_values()` never ran here |
| Tenant created **2026-09-22**; A01 provisioning delivered **2026-09-24** | the tenant predates the provisioning code |
| `permission` table has **20** rows; the catalog defines **23** | bootstrap has not been re-run since RTE03 |

The missing capabilities are `route.worksession.execute`, `users.delete` and `route.records.adjust` — added by RTE03, RTE02-A01 and RTE04 respectively. That is a precise timestamp: **bootstrap was last run before RTE03**, and the values, the capabilities and the role grants have all been frozen since.

The approved idempotency semantics are intact and were not exercised: nothing was renamed, deactivated or deleted, because nothing was ever created.

### Role capability drift in the reviewed environment

| Role | In DB | In catalog | Missing |
|---|---|---|---|
| `owner` | 20 | 23 | `route.records.adjust`, `route.worksession.execute`, `users.delete` |
| `admin` | 19 | 22 | same three |
| `manager` | 6 | 6 | — |
| `viewer` | 3 | 3 | — |
| `route_admin` | 9 | 11 | `route.records.adjust`, `users.delete` |
| **`supervisor`** | **0** | **1** | **`route.worksession.execute`** |

**`supervisor` has no capabilities at all in this environment.** Everything RTE03 and RTE04 built for the field user — Start Work, Trip, odometer capture — returns 403 there. The Standardized Values symptom is the visible tip of this; the Supervisor being unable to work at all is the larger part of it, and it was not in the original report.

---

## 5. Where the values disappear (§2.5, §2.6)

The instruction asks whether they vanish before the API, in API filtering, in frontend state, or in rendering. **None of those.** They were never there.

Proven by exclusion, with browser evidence: `tests/e2e/test_standard_values_browser.py`, real Microsoft Edge against the production bundle.

| Check | Result |
|---|---|
| With the 28 values provisioned, all 8 lists appear in the Admin screen | **PASS** |
| Each list's counter shows its exact approved count | **PASS** |
| Selecting each list renders each approved label | **PASS** |
| A second tenant without provisioning shows all 8 lists at **0** and none of the other tenant's values | **PASS** |

`2/2 PASS, exit 0`.

The second test reproduces the reported symptom exactly: the lists are present because they are product-defined, and every counter reads `0` because that tenant was never provisioned. **The wiring, the API filter, the frontend state and the rendering are all correct.**

---

## 6. Role inventory (§4.1, §4.2)

From the reviewed tenant, with capabilities and assigned user counts read from the database:

| id | Name | Origin | Category | Active | Capabilities (DB) | Users |
|---|---|---|---|---|---|---|
| 1 | `owner` | **Core/Foundation** | management | yes | 20 | 1 |
| 2 | `admin` | **Core/Foundation** | management | yes | 19 | 0 |
| 3 | `manager` | **Core/Foundation** | operative | yes | 6 | 0 |
| 4 | `viewer` | **Core/Foundation** | operative | yes | 3 | 0 |
| 5 | `supervisor` | **CER Route** | operative | yes | **0** | 0 |
| 6 | `route_admin` | **CER Route** | operative | yes | 9 | 0 |

**Origin established by capability, not by label**, as §4.1 requires. A role is CER Route's if it grants a `route.*` capability as part of its own definition:

- `route_admin` and `supervisor` are defined by Route capabilities → **the two roles CER Route created.**
- `manager` and `viewer` grant no `route.*` capability at all → **Core, untouched.**
- `owner` and `admin` receive `route.*` capabilities **because they are "everything" and "almost everything"**, not because they are Route personas. This is the distinction §4.2 asks for and it is now pinned by a test.

Nothing was deleted, renamed or repurposed.

---

## 7. Why the dropdown shows six roles (§4.3)

Traced end to end:

```
pages/RouteUsersPage        → renders SecurityUsersPanel directly, by design
features/SecurityUsers/ui/SecurityUserForm.tsx:69
                            → dispatch(fetchRoles())
entities/Roles/fetchRoles   → GET /api/roles
GET /api/roles              → every active role of the tenant
```

**Cause: intended reuse with no Route-specific filtering anywhere in the chain.** RTE02 deliberately reused the Core user-management screen instead of building a second one — the page's own docstring says so: *"Escribir aquí una segunda pantalla de usuarios habría creado un segundo sitio donde arreglar el mismo fallo."* The backend returns all six tenant roles and the frontend shows what it receives.

So the six options are not a bug in the sense of broken code. They are the visible consequence of reuse, and the UI is faithfully reporting what the server permits — which is the real problem, below.

Classification: **UX GAP**, and it is the surface of a **SECURITY GAP**.

---

## 8. Privilege escalation test results (§5) — `SECURITY GAP`

Tested against the API directly, authenticated as a user holding only `route_admin` permissions.

| # | Action | Result | Verdict |
|---|---|---|---|
| 1 | Create user with `owner` | **HTTP 200 — permitted** | **escalation** |
| 2 | Create user with `admin` | **HTTP 200 — permitted** | **escalation** |
| 3 | Change existing `supervisor` → `owner` | **HTTP 200 — permitted** | **escalation** |
| 4 | Change existing `supervisor` → `admin` | **HTTP 200 — permitted** | **escalation** |
| 5 | Assign `manager` | HTTP 200 | out of Route's scope |
| 6 | Assign `viewer` | HTTP 200 | out of Route's scope |
| 7 | Assign `route_admin` | HTTP 200 | correct |
| 8 | Assign `supervisor` | HTTP 200 | correct |

### The full consequence, tested

Not merely a badly assigned role — the account is **usable**:

1. `route_admin` creates a user with role `owner` and sets its password → **200**
2. That account signs in → **200**
3. That account deletes a role → **200**

`roles.delete` is **not** in `route_admin`'s capabilities. The catalog withholds it even from `admin`, with a stated reason: *"borrar el rol equivocado es la forma más rápida de dejar una compañía sin nadie que pueda administrarla."* A Route Admin obtains it by proxy in three API calls.

The granted account holds 23 capabilities including `roles.create`, `roles.delete`, `rolepermissions.update` and `rolepermissionsapprovals.read` — full control of the tenant's security configuration.

### Why the existing protections do not prevent it

§5 warned about exactly this, and the warning is correct. All three existing protections hold, and none of them helps:

| Protection | Status | Why it does not help |
|---|---|---|
| `is_superuser` refused from the request body | **holds** (HTTP 422, `extra_forbidden`) | escalation needs no platform privilege — a tenant role suffices |
| Cannot create or edit roles | **holds** (HTTP 403 on create and delete) | the powerful role already exists; it only has to be granted |
| Role from another tenant rejected | **holds** (HTTP 404, existence not confirmed) | the escalation is entirely within one tenant |

The only check on the way in is `UserManagementDAO._assert_role_of_company` — the role must belong to this company and be active. **There is no check on whether the caller is entitled to grant it.** Anyone with `users.create` or `users.update` can grant any role in the tenant.

### Scope note

This is not specific to `route_admin`. It follows from the Core user-management contract: `users.create` and `users.update` carry no notion of which roles the caller may confer. `manager` also holds `users.create` and `users.update` and is therefore in the same position. **The gap lives in Core, not in CER Route.**

That is why **no fix was attempted.** §11 stops on "`route_admin` can assign `owner` or `admin`", and §7 stops if the fix requires changing the shared Core user-management contract — which it does. Both conditions are met.

---

## 9. Expected vs Implemented vs Evidence vs Gap

| Expected | Implemented | Evidence | Gap |
|---|---|---|---|
| 8 lists, 28 approved values in code | yes, identical | `tests/test_standard_value_catalog.py` — 12/12, verified to fail on a synonym | none |
| Reviewed tenant holds the 28 values | **no — zero rows** | direct DB query on `cer_route` | `CONFIGURATION/ENVIRONMENT` |
| API returns active values | yes, when they exist | browser test, 8 lists rendered | none |
| Admin UI renders them | yes | `tests/e2e/test_standard_values_browser.py` — 2/2 PASS | none |
| Wrong tenant cannot see them | yes | second-tenant browser test, all counters `0` | none |
| Delete/deactivate semantics unchanged | yes, untouched | nothing was modified | none |
| Exactly two Route role templates | yes | `test_exactly_two_role_templates_are_specific_to_cer_route` | none |
| Core roles intact | yes | role inventory; nothing renamed or deleted | none |
| Supervisor cannot administer users | yes | 403 on users and roles; exactly one capability | none |
| Cross-tenant role assignment rejected | yes | HTTP 404 | none |
| No `is_superuser` path | yes | HTTP 422 `extra_forbidden` | none |
| Role dropdown behavior intentional and tested | reuse is intentional; **consequence is not safe** | §7 trace | `UX GAP` |
| `route_admin` cannot exceed its authority | **no** | §8 — 4 of 4 escalation cases permitted | **`SECURITY GAP`** |
| Supervisor role functional in the reviewed tenant | **no — 0 capabilities** | capability drift table | `CONFIGURATION/ENVIRONMENT` |

---

## 10. Findings and classification

| # | Finding | Classification |
|---|---|---|
| **F-1** | `route_admin` can grant `owner` / `admin`, and the granted account is usable to exceed the granter's authority | **`SECURITY GAP` / PRIVILEGE ESCALATION** |
| **F-2** | `standard_value` is empty in the reviewed tenant; provisioning never ran there | **`CONFIGURATION/ENVIRONMENT`** |
| **F-3** | `supervisor` has zero capabilities in the reviewed tenant; three capabilities never seeded. RTE03/RTE04 field experience non-functional there | **`CONFIGURATION/ENVIRONMENT`** |
| **F-4** | The Route Users form offers all six tenant roles, with no Route-specific filtering | **`UX GAP`** (surface of F-1) |
| **F-5** | `owner` and `admin` hold Route capabilities by being "everything", not as Route personas | **`AS-BUILT / ALIGNED`** — documented, now pinned by a test |
| **F-6** | The pre-existing values test compared the code against itself; a synonym would have passed | **`FUNCTIONAL GAP` in test coverage** — closed in this diagnostic |
| **F-7** | Whether an Admin may empty a list that RTE04 made mandatory before departure | **`DECISION REQUIRED`** (carried over from the RTE04 delivery) |

---

## 11. Corrections made in this diagnostic

Deliberately minimal. No product behavior was changed.

| Change | Why it is safe |
|---|---|
| `tests/test_standard_value_catalog.py` (12 tests) | test-only; parses the approved document and compares |
| `tests/e2e/test_standard_values_browser.py` (2 tests) | test-only; browser evidence for §2.6 |
| `tests/integration/test_route_role_authority.py` (13 tests) | test-only; the §5 audit, with the four escalation cases as `xfail(strict=True)` |

**Nothing was provisioned, reseeded, deleted or reactivated.** §3 of the instruction permits using the approved provisioning mechanism for the affected tenant, but doing so writes to the environment the Product Owner is reviewing, and §11 makes the identity of that environment a STOP condition. That is CER's call and the command is in §13.

### About the `xfail` marks

The four escalation cases are recorded as tests that assert the **correct** behavior and are marked `xfail(strict=True)`. This keeps the suite green while stating the intent in code, and `strict=True` means the day the gap is fixed **those tests fail** and force the mark to be removed. An `xfail` that stays green forever would be an elegant way to forget the problem.

---

## 12. Recommendation for the role-selector UX

The UI change alone is **not** a fix. Filtering the dropdown to `Route Admin` and `Supervisor` would hide the escalation without removing it: the API accepts any tenant role from anyone holding `users.create`. The guard has to be server-side, as it is everywhere else in this codebase.

The narrowest safe option, for CER's consideration — **not implemented**:

**Server-side: nobody may grant authority they do not hold.** When assigning a role, compare the role's capabilities against the caller's. If the role would grant something the caller lacks, refuse with 403. This needs no new capability, no new role concept, and no change to how roles are defined. It is a single rule at the one place that already validates the role (`_assert_role_of_company`). It also closes the same gap for `manager`, which has it today.

Three properties follow, matching §7's preferred target:

- an `owner` can still grant `owner` — they already hold everything;
- a `route_admin` can grant `route_admin` and `supervisor`, and nothing above itself;
- a user who already holds a Core role keeps it; nothing is silently changed.

**Then, and only then**, the dropdown can be narrowed as user experience — showing options the server would accept rather than options it would refuse.

This touches the shared Core user-management contract, which §7 and §11 both make a STOP condition. Hence the recommendation rather than the change.

---

## 13. Operational actions

To restore the reviewed environment, once CER confirms it is the right one:

```bash
uv run python -m app.db.scripts.bootstrap
```

Idempotent by design. It will:

- seed the three missing capabilities (`route.worksession.execute`, `users.delete`, `route.records.adjust`);
- grant them to the role templates, restoring `supervisor` to a working state;
- provision the 28 Standardized Values via the **existing** mechanism — no second seeding path was created.

Also pending from the RTE04 delivery: migrations `0006_odometer_evidence` and `0007_odometer_scan_verdict`.

**Local is not shared.** Everything above was executed against a local Windows machine and a local PostgreSQL. No shared environment was inspected or changed, and none of these results describes one.

---

## 14. Scope confirmation

RTE04 and RTE05 behavior was **not** changed by this diagnostic. No Core or Foundation role was deleted, renamed or repurposed. No role capability was altered to simplify a dropdown. No Standardized Value was resurrected. No tenant id or subdomain was hardcoded. No duplicate user management was created. No server-side authorization was weakened. No second seeding path exists.

---

## 15. Status

**STOPPED for CER review**, on two of §11's conditions:

- `route_admin` can assign `owner` and `admin` — confirmed against the API;
- the correct fix changes the shared Core user-management contract.

Two decisions are needed from CER:

1. **F-1** — approve the server-side rule in §12, or direct a different approach.
2. **F-2 / F-3** — confirm that `cer_route` / `cerroute` is the environment being reviewed, and authorize running bootstrap there.

Development stops here.
