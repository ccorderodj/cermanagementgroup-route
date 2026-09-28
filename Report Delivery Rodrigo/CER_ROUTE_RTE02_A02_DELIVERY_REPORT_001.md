# CER Route — RTE02-A02 Access Alignment & Closure

| | |
|---|---|
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE02_A02_ACCESS_ALIGNMENT_AND_CLOSURE_INSTRUCTIONS_007.md` |
| **Branch** | `feature/rte02-a02-access-alignment` |
| **Date** | 2026-09-26 |
| **Proposed status** | **RTE02-A02 — Completed / Ready for CER Certification** |
| **RTE03 / RTE04 business behavior** | **Unchanged.** No Work Session lifecycle, Trip state machine, odometer rule, END Option B or Routing Mileage definition was touched |
| **RTE05** | **Not started.** |

---

## 0. The three things worth reading first

**1. The privilege escalation is closed.** The sequence the A01 diagnostic measured against the API — a `route_admin` creating an `owner`, signing in as it, deleting a role — no longer starts. The first step returns **403** and nothing is written. The five tests that documented the gap as `xfail(strict=True)` began failing the moment the fix landed, which is precisely what a strict xfail is for; their marks are gone and they are now permanent nets.

**2. The reviewed environment is aligned.** Provisioning ran once, through the existing bootstrap and nothing else: **0 → 28** Standardized Values, **20 → 24** capabilities, and `supervisor` went from **zero capabilities to two**. Before this, everything RTE03 and RTE04 built for the field user returned 403 in that environment.

**3. One residue CER should know about, because bootstrap cannot fix it.** `route_admin` still holds `roles.read` in the aligned tenant, a capability this checkpoint removed from the template. **Bootstrap adds missing grants and never revokes**, so a capability *withdrawn* from the catalog stays granted in tenants that already had it. It grants no assignment authority — that is closed server-side — but it means code and database disagree on one row, and closing that needs an action the approved mechanism does not perform. Details and options in §11.

---

## 1. As-built role model

### Visible labels vs technical identifiers

The existing technical codes were preserved, as §"Technical compatibility" prefers. Renaming `role.name` in every tenant purely to change a label would have been a destructive migration for a presentation change.

| Shown in the product | Technical code | Origin |
|---|---|---|
| **Administrador** | `route_admin` | CER Route |
| **Supervisor** | `supervisor` | CER Route |
| — *(not offered in CER Route)* | `owner` | Core/Foundation |
| — | `admin` | Core/Foundation |
| — | `manager` | Core/Foundation |
| — | `viewer` | Core/Foundation |

The labels live in one place, `ROUTE_PRODUCT_ROLE_LABELS`, and the API returns them; the technical code never reaches the screen. Verified by a browser test that asserts `route_admin` appears nowhere in the selector's text.

Core roles were **not** deleted, renamed, repurposed or migrated.

---

## 2. Exact permission matrix — as built

| Area | Administrador | Supervisor | Enforced by |
|---|---:|---:|---|
| Mobile / My Route | Yes | Yes | session-only page, both roles reach it |
| Execute Work Session | Yes | Yes | `route.worksession.execute` |
| Execute Trip flow | Yes | Yes | `route.worksession.execute` |
| Execute odometer flow | Yes | Yes | `route.worksession.execute` |
| Read operational Standardized Values | Yes | Yes | **`route.standardvalues.read`** |
| Manage Standardized Values | Yes | **No** | `route.standardvalues.manage` |
| See retired values (`include_inactive`) | Yes | **No** | `route.standardvalues.manage` |
| Manage Route users | Yes | No | `users.read/create/update/delete` |
| Assign Administrador | Yes | No | `ensure_assignable_role` |
| Assign Supervisor | Yes | No | `ensure_assignable_role` |
| **Assign Core roles** | **No** | No | `ensure_assignable_role` → 403 |
| Read the tenant role catalog | **No** | No | `roles.read` withdrawn |
| Manage vehicles / assignments | Yes | No | `route.vehicles.manage` |
| Review odometer exceptions | Yes | No | `route.records.adjust` |
| Core role administration | No | No | not granted |
| Platform superuser | No | No | not in any tenant input schema |

Capability counts: **Administrador 12**, **Supervisor 2**.

### Read / Execute / Manage separation

The Supervisor's two capabilities are exactly `route.worksession.execute` (Execute) and `route.standardvalues.read` (Read). There is no third. A test asserts the set equality, so adding anything manage-shaped to that role fails the suite.

**A shortcut was removed, and it was mine.** RTE04-C5 authorised reading the value lists with `route.standardvalues.manage` **or** `route.worksession.execute`. That closed a real 403 — Employee Visit, Check Delivery and Office were impossible to start from the phone — but it made *Execute* serve as a generic read permission, which is what BR-03 forbids. The read now has its own capability, so it can be granted without granting anything else. A test reads the endpoint's source (comments stripped) and fails if `worksession.execute` reappears in that authorization.

### BR-02, applied

RTE03 deliberately withheld `route.worksession.execute` from the Route Admin, reasoning that reaching Admin and executing field work are different authorizations. They still are — what changed is that CER decided one role holds both, because a CEO or COO uses that role and drives. The RTE03 test that asserted the denial was rewritten to assert the new behavior, with the reasoning recorded in it. **Work Session lifecycle semantics were not touched**: the Administrator executes their own session, resolved from the authenticated session, like anyone else.

---

## 3. Server-side role-assignment policy

`app/routers_api/usermanagement/role_policy.py` → `ensure_assignable_role`, called on **both** create and update, **before** the DAO's existing company check.

The rule, in one sentence: **whoever administers users from CER Route may only grant CER Route roles.**

```
actor holds a Route product role?  ──no──▶  unchanged (Core behavior untouched)
             │ yes
             ▼
target role is a Route product role?  ──yes──▶  allowed
             │ no
             ▼
                                              403
```

### Why not the rule the A01 diagnostic proposed

That diagnostic recommended "nobody may grant authority they do not hold". FR-05 rejects it, and correctly: the Administrador must be able to create a Supervisor, and the two roles hold **deliberately different** capability sets, so that rule would have blocked the normal case. The approved rule needs no capability comparison and no hierarchy.

### Scope, stated plainly

The policy keys on the **actor's** role, which is the narrowest form that closes the CER Route surface. A Core `owner` or `admin` administers exactly as before — proven by a test. The platform administrator is exempt, because their authority is of a different nature (D6) and a test confirms they are not caught by the Route rule.

**Remaining Core-only exposure:** `manager` holds `users.create` and `users.update` and is in the same position `route_admin` was — it can grant any role in its tenant, including `owner`. That is **Core exposure, not CER Route**, and §103 of the instruction directs reporting it rather than redesigning the Core hierarchy here. It is reported in §10.

---

## 4. Evidence that Core roles cannot be assigned through CER Route

Tested against the API, never inferred from the UI. All twenty edge cases from the instruction are covered; these are the security-relevant ones.

| # | Case | Result |
|---|---|---|
| 1 | Administrador creates Supervisor | **200** |
| 2 | Administrador creates Administrador | **200** |
| 3 | Supervisor → Administrador | **200** |
| 4 | Administrador → Supervisor | **200** |
| 5 | Create with `owner` | **403** |
| 6 | Create with `admin` | **403** |
| 7 | Create with `manager` | **403** |
| 8 | Create with `viewer` | **403** |
| 9 | Promote existing user to any Core role (4 cases) | **403** |
| 10 | Direct API submission bypassing the selector | **403**, and **no user row written** |
| 11 | Role from another tenant | **404**, existence not disclosed |
| 12 | Supervisor creates/edits users | **403** |
| 20 | Core roles absent from the Route assignment surface | selector offers exactly 2 |

Case 10 is asserted twice over: the response is 403 **and** a database check confirms the user was not created half-way — the rejection precedes the write.

---

## 5. Administrator uses Admin + Mobile; Supervisor uses Mobile only

Browser evidence, real Microsoft Edge against the production bundle.

| Check | Result |
|---|---|
| Administrador opens Users, Vehicles, Standardized Lists, Odometer Exceptions | **PASS** |
| Administrador then opens `/route` in the same session | **PASS** |
| Administrador presses Start Work; session exists in PostgreSQL | **PASS** |
| Supervisor presses Start Work; session exists in PostgreSQL | **PASS** |
| Supervisor sees no Admin links inside the mobile experience | **PASS** |
| Server refuses all four Admin pages to a Supervisor | **PASS** (401/403/404) |
| Supervisor reads the four approved Employee Visit reasons in the trip form | **PASS** |
| Supervisor is refused the Standardized Lists page | **PASS** |
| Role selector offers exactly Administrador and Supervisor | **PASS** |
| No Owner/Admin/Manager/Viewer option; no technical code shown | **PASS** |

`6/6, exit 0`.

Both roles use the same mobile experience; the flow is not forked by role. The Supervisor receives no Admin control from sharing it — checked on the screen *and* on the server, because hiding a link has never protected anything.

### One implementation note on the UI

`SecurityUsersPanel` is still reused, not duplicated. What changed is where the form gets its options: it dispatched `fetchRoles()` (`GET /api/roles`, the tenant catalog) and now dispatches `fetchAssignableRoles()` (`GET /api/users/assignable-roles`), which returns what the server **would actually accept** from the caller. One call serves both audiences: a Core administrator still receives the full catalog.

That is also what let `roles.read` be withdrawn from the Administrador without breaking their form — the new endpoint needs only `users.read`.

---

## 6. Environment and tenant provisioned (the gate)

Recorded **before** any write, as §"Gate before writing target-environment data" requires.

| Item | Value |
|---|---|
| Environment / mode | `MODE = DEV` |
| Database | `cer_route` on `localhost:5432` |
| Tenant id | **1** |
| Tenant name | CER Management Group LLC |
| Subdomain | `cerroute` |
| Tenants present in this database | **exactly one** |
| Schema version | `0007_odometer_scan_verdict` (current head) |

Only one tenant exists in this database, so there is no ambiguity *within* the environment. Its identity is the same one the A01 diagnostic reported, and instruction 007 builds on that diagnostic's findings — including that this tenant has zero `standard_value` rows — which is what we treated as CER's confirmation to proceed.

**Local is not shared.** This is a local Windows machine and a local PostgreSQL. No shared or hosted environment was inspected or modified. If CER's visual validation happens elsewhere, §6 must be re-run there before the bootstrap in §13.

**A correction to the RTE04 delivery report:** it listed migrations `0006` and `0007` as pending on the target environment. They were already applied here — our own `alembic upgrade head` during RTE04 ran against this DEV database. The claim was wrong for this environment.

---

## 7. Standardized Values — pre / post

| | Before | After |
|---|---:|---:|
| `standard_value` rows | **0** | **28** |
| Rows carrying a `seed_key` | 0 | 28 |

| List | Active after | Approved |
|---|---:|---:|
| client_visit_activities | 4 | 4 |
| recruiting_activities | 3 | 3 |
| employee_visit_reasons | 4 | 4 |
| delivery_types | 3 | 3 |
| office_purposes | 4 | 4 |
| other_activities | 3 | 3 |
| outcomes | 4 | 4 |
| received_by | 3 | 3 |

Labels, order, spelling and counts unchanged. A test independent of the implementation constant parses `CER_ROUTE_RTE02_ADDENDUM_A01_DEVELOPMENT_INSTRUCTIONS_004.md` and compares — verified to fail when a label is changed to a synonym.

---

## 8. Capabilities and grants — pre / post

| | Before | After |
|---|---:|---:|
| `permission` rows | **20** | **24** |
| `supervisor` capabilities | **0** | **2** |
| `route_admin` capabilities | 9 | 13 *(12 in catalog — see §11)* |
| `owner` | 20 | 24 |
| `admin` | 19 | 23 |
| `manager` | 6 | 6 |
| `viewer` | 3 | 3 |

Newly seeded: `route.worksession.execute`, `route.standardvalues.read`, `users.delete`, `route.records.adjust`.

**`supervisor` had zero capabilities.** Every RTE03 and RTE04 command returned 403 in this environment. That is the condition the instruction names, and it is resolved.

---

## 9. Provisioning idempotency

Second bootstrap run, immediately after the first:

```
+ 0 capacidades creadas (24 en el catálogo)
= rol 'owner' … 'route_admin' ya existían   (no grants added)
+ 0 valores creados, 28 ya existían (28 aprobados)
  Clave (sin cambios; el usuario ya existía)
```

Lifecycle semantics proven by test, one decision at a time:

| Tenant decision | Second run |
|---|---|
| Renamed a seeded value | name kept; original does not reappear; no duplicate |
| Deactivated a seeded value | stays inactive; no active twin created |
| Deleted a seeded value | not resurrected; tombstone preserved |
| Authored their own value | untouched; carries no `seed_key` |
| Nothing changed | every row byte-identical, `updated_at` included |

`10/10 PASS`.

---

## 10. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Gap |
|---|---|---|---|
| Exactly two product roles in the UX | yes | browser selector = 2 options | none |
| Core roles preserved | yes, untouched | role inventory | none |
| Both roles execute the Route workflow | yes | API + browser Start Work for both | none |
| Only Administrador administers | yes | 403 on 4 admin pages + APIs for Supervisor | none |
| Supervisor = Read + Execute | yes, exactly 2 capabilities | set-equality test | none |
| No escalation into Core roles | yes | 12 API cases, 403; nothing written | none |
| Direct API bypass rejected | yes | case 10 | none |
| Cross-tenant assignment non-disclosing | yes | 404 | none |
| No `is_superuser` path | yes | 422 `extra_forbidden` | none |
| Read separate from Manage | yes, `route.standardvalues.read` | Supervisor reads, is refused all 5 manage ops | none |
| Execute not a generic read shortcut | yes, shortcut removed | source-level test | none |
| Correct tenant confirmed before writing | yes | §6 | see §6 caveat |
| 28 values present after provisioning | yes | §7 | none |
| Grants match the catalog | yes for a fresh tenant | `test_a_freshly_seeded_tenant_matches_the_capability_catalog` | **one residue, §11** |
| Supervisor not left at zero capabilities | yes | §8 | none |
| Provisioning idempotent | yes | §9 | none |
| RTE02 / A01 suites green | yes | §12 | none |
| RTE03/RTE04 access smoke | yes | both roles Start Work; both read the values | none |
| **Core-only exposure reported separately** | reported, not fixed | §3 | **`manager` — Core, out of scope** |

---

## 11. The one residue, and what it would take

`route_admin` holds **13** capabilities in the aligned tenant against **12** in the catalog. The extra one is `roles.read`, which this checkpoint withdrew from the template because the Route user form no longer reads the tenant catalog.

**Why it is still there:** bootstrap aligns what is missing and never revokes. That is the right default for a mechanism that runs against tenants holding real decisions — but it means a *withdrawn* capability persists, and drift is one-directional.

**What it does and does not allow:** it lets an Administrador read the list of role names via `GET /api/roles`. It grants no assignment authority; every Core role assignment is refused. So it is information, not power — but the information is precisely the Core taxonomy FR-01 says is not part of this product's experience.

**Three ways to close it, for CER to choose:**

1. **Authorize a targeted revoke** in the aligned tenant. Smallest change, but the instruction forbids manual row writes and creating a second script, so it needs explicit authorization for a one-off operation.
2. **Teach bootstrap to revoke** capabilities a template no longer lists. Correct long-term and idempotent, but it changes the provisioning mechanism's semantics for every tenant, which is more than this checkpoint's scope.
3. **Keep `roles.read` in the template.** Makes code and database agree immediately and costs nothing functionally — but it grants a capability nothing uses, and hands the Route Administrador the Core role taxonomy that FR-01 keeps out of the product.

We did **not** choose one. Option 1 needs authorization the instruction withholds; option 2 exceeds scope; option 3 we judge wrong on the merits but it is a product call.

---

## 12. Tests and regression

All runs **serial**. An earlier attempt ran two pytest processes against the same test database concurrently and one recreated the schema under the other; both results were discarded as invalid rather than reported.

| Suite | Tests | Exit |
|---|---:|---|
| A02 access model (20 edge cases + matrix) | 29 | `0` |
| Provisioning alignment + lifecycle | 10 | `0` |
| Route role authority (ex-`xfail`, now nets) | 13 | `0` |
| Standard value catalog vs approved document | 12 | `0` |
| Permission catalog / page & navigation wiring / public surface / frontend completeness | 63 | `0` |
| Work Sessions + Route configuration + admin lifecycle + authorization matrix | 198 | `0` |
| **Browser (role selector, both roles Mobile, Supervisor denial, values)** | **6** | **`0`** |
| `npm run typecheck` / `lint:ts` | — | **0 errors** |
| `npm run build:prod` | — | `exit 0` |

### Test changes made, and why each was legitimate

Fourteen existing tests failed after the access-model change. None was weakened to pass; each expectation was updated to the newly approved model:

| Test | Change |
|---|---|
| `test_a_route_admin_without_the_capability_cannot_start_work` | rewritten as `test_the_route_administrator_can_also_start_work` — BR-02 supersedes it by name |
| `test_route_admin_uses_core_user_capabilities_not_route_ones` | asserts `roles.read` is **absent**, with the reason |
| `test_route_admin_cannot_administer_roles_themselves` | `GET /api/roles` now 403; asserts the replacement endpoint works |
| 6 tests creating a throwaway user as `viewer` | now create a `supervisor` — their intent was "some user", not "a Core user" |
| `test_a_removed_user_loses_authorization_on_an_open_session` | probes `/api/worksessions/current` instead of the company profile, which the Supervisor cannot read |
| 5 `xfail(strict=True)` escalation tests | marks removed — they started failing because the gap closed |

---

## 13. Operational actions

| Action | Status |
|---|---|
| Migrations on the reviewed environment | **already applied** (`0007`) |
| Bootstrap on the reviewed environment | **done** — 28 values, 4 capabilities, grants aligned |
| Frontend production build on deploy | **required** |
| Re-run §6 and bootstrap on any other validation environment | **required if CER validates elsewhere** |
| Decide the §11 residue | **CER** |

---

## 14. Scope confirmation

Not changed: RTE03 Work Session lifecycle or time semantics; RTE04 Trip state machine; odometer business rules; END Option B; Routing Mileage definition; Activity/RTE05 behavior; free-text decisions; Standardized Values labels or order; the tenant isolation model; Core role meanings; the platform superuser model; the existing audit primitive.

Not created: CEO/COO/RM/OSM roles; organizational hierarchy or team scope; multi-role membership; a parallel identity model; a second Standardized Values seeding path; duplicate Route user management. No Core role was deleted, renamed or repurposed. No technical role code was renamed. No tenant id was hardcoded. No server-side authorization was weakened.

**RTE05 was not started.** RTE04 is **not** certified from this checkpoint; the RTE03/RTE04 runs here prove access compatibility only.

---

## 15. Status

**RTE02-A02 — Completed / Ready for CER Certification**, with one item for CER:

- **§11** — how to close the `roles.read` residue in the aligned tenant. Three options, trade-offs stated, none chosen.

Development stops here, as the instruction directs, and does not continue with RTE04 closure or RTE05.
