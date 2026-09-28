# CER Route — RTE02-A02 Final Closure

| | |
|---|---|
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE02_A02_FINAL_CLOSURE_INSTRUCTIONS_008.md` |
| **Branch** | `feature/rte02-a02-final-closure` |
| **Date** | 2026-09-28 |
| **Proposed status** | **RTE02-A02 — Completed / Ready for CER Certification** |
| **Supersedes** | `CER_ROUTE_RTE02_A02_DELIVERY_REPORT_001.md` (not overwritten) |
| **RTE03 / RTE04 business behavior** | **Unchanged** |
| **RTE05** | **Not started** |

---

## 0. Read first

**1. The gap CER found is closed, and closing it opened another one that we caught.**
Route role assignment now keys on **product context** — everything entering through `/api/route/users` is limited to the two Route roles, for anyone including the platform Superadmin. But switching to context *alone* immediately reopened the A01 escalation: a `route_admin` holds `users.create`, so calling `/api/users` directly let them create an `owner` again. Measured returning 200 before it was fixed. **Both conditions are required** — context closes the screen, actor closes the back door — and that regression now has its own test.

**2. The residual grant is gone, through a documented mechanism.**
`route_admin → roles.read` removed by a targeted, idempotent, audited script. Final counts in the aligned tenant: **Administrador 12, Supervisor 2**, exactly as §"Final expected counts" requires. `roles.read` still exists as a capability and `owner`/`admin` still hold it.

**3. The mandatory FR-03 browser test found a second, real gap — the exact one CER described.**
With the server fixed, the browser still showed **six** options to a Superadmin in `CER Route > Users`. The form was calling the **Core** contract (`/api/users/assignable-roles`), so the product context was never set. The API tests passed because they called the Route path directly, and the earlier browser test passed because it signed in as `route_admin`, where the *actor* rule masked it.

Fixed by composition, not duplication: `SecurityUsersPanel` now takes a `contract` prop and `RouteUsersPage` declares `cer-route`. This is why CER made that test mandatory — it survived a server-side fix that looked complete.

**4. Six existing tests changed expectations, none was weakened.**
Three browser tests validated the old permanent-form layout; two backend tests asserted denials that BR-02 and BR-03 explicitly supersede. Each is listed in §9 with what changed and why.

---

## 1. Final role model

| Shown in the product | Technical code | Capabilities |
|---|---|---:|
| **Administrador** | `route_admin` | **12** |
| **Supervisor** | `supervisor` | **2** |

Core/Foundation roles — `owner`, `admin`, `manager`, `viewer` — remain untouched: not deleted, not renamed, not repurposed. They are simply not offered through the CER Route contract.

Technical codes were preserved as §"Technical compatibility" prefers, and never reach the screen. A browser test asserts `route_admin` appears nowhere in the selector's text.

---

## 2. Product context governs role assignment

### How the context is known

By the **route**, not by a header. The same router is mounted twice:

```
/api/users        → Core contract       → unchanged
/api/route/users  → CER Route contract  → only the two product roles
```

Trusting a client-supplied header to declare its own context would be trusting the client to decide a boundary. Mounting the same `APIRouter` under a second prefix with one extra dependency also means **no duplicated user management**: same handlers, same DAO, same audit.

### The rule, as built

Assignment is limited to the two Route roles when **either** holds:

1. **the context is CER Route** — the request arrived through `/api/route/users`, whoever is calling (PD-02, new in FC1);
2. **the actor is a Route role** — `route_admin` or `supervisor`, through whichever contract (A02, and load-bearing).

Both conditions live in one function, `acota_a_roles_de_route`, used by the write path and the read path alike, so the list offered and the list accepted cannot drift.

### Evidence

| Actor | `/api/route/users/assignable-roles` | `/api/users/assignable-roles` |
|---|---|---|
| Administrador Route | **2 roles** | **2 roles** (actor rule) |
| Core `owner` | **2 roles** | 6 roles (Core unchanged) |
| Core `admin` | **2 roles** | 6 roles |
| **Platform Superadmin** | **2 roles** | 6 roles (authority intact) |

---

## 3. Superadmin scenario and API bypass (FR-03)

The scenario that exposed the gap, tested end to end:

| Step | Result |
|---|---|
| Sign in as platform Superadmin | ok |
| `GET /api/route/users/assignable-roles` | **exactly 2**: Administrador, Supervisor |
| No Core role label present | confirmed |
| No technical code present | confirmed |
| `POST /api/route/users` with `role_id = owner` | **403** |
| User row written? | **none** — checked in PostgreSQL |
| `POST /api/users` with `role_id = owner` (Core contract) | **200** — authority intact |

Browser evidence covers the same path through the screen: the role selector in `CER Route > Users` offers exactly two options for Administrador, Core `owner`, Core `admin` and Superadmin.

### Every rejected path

| Case | Result |
|---|---|
| Route contract, create with `owner` / `admin` / `manager` / `viewer` | **403**, nothing written |
| Route contract, promote existing user to any Core role | **403** |
| **Core contract, `route_admin` creating any Core role** | **403** (the regression we caught) |
| Role from another tenant | **404**, existence not disclosed |
| Supervisor listing, creating or reading assignable roles, either contract | **403** |
| `is_superuser` in the request body | **422** `extra_forbidden` |
| Core actor through the Core contract | **200** — unchanged, by design |

---

## 4. Capability matrix — as built

| Capability / Experience | Administrador | Supervisor |
|---|---:|---:|
| Mobile / My Route | Yes | Yes |
| Work Session execute | Yes | Yes |
| Trip execute | Yes | Yes |
| Odometer execute | Yes | Yes |
| Read operational Standardized Values | Yes | Yes |
| Manage Standardized Values | Yes | **No** |
| Manage Route users | Yes | No |
| Assign Administrador / Supervisor | Yes | No |
| Assign Core roles from CER Route | **No** | No |
| Manage Vehicles / Assignments | Yes | No |
| Odometer exception administration | Yes | No |
| `roles.read` | **No** | No |
| Platform superuser | No | No |

**Administrador 12 · Supervisor 2**, verified against the aligned tenant's database and asserted by test.

---

## 5. `roles.read` removed safely

### Why a script was needed

Bootstrap **adds and never revokes**. That is the right default for something run against tenants holding real decisions — removing what an administrator granted would destroy work silently — but it means a capability *withdrawn from the catalog* persists, and the drift is one-directional.

### What the cleanup does, and does not

`app/db/scripts/cleanup_route_admin_roles_read.py` removes exactly one grant: `roles.read` from `route_admin`, in every company still holding it.

- **not** a generic revocation engine — the role and the capability are written in the file, one each, not derived from the catalog;
- **not** a change to bootstrap semantics;
- **not** a removal of the `permission` row — `roles.read` still exists and Core still uses it;
- **not** a re-addition to the Route template.

### Evidence

| | Before | After |
|---|---:|---:|
| `route_admin` capabilities | 13 | **12** |
| `supervisor` capabilities | 2 | **2** |
| `roles.read` granted to `route_admin` | yes | **no** |
| `roles.read` exists as a capability | yes | **yes** |
| Roles still holding it | owner, admin, route_admin | **owner, admin** |

Second run: `= nada que hacer: 'roles.read' ya no está concedida a 'route_admin'`. Idempotent.

Audit row written:

```
role_permission / revoke
Obsolete grant 'roles.read' revoked from 'route_admin'
(RTE02-A02 FC4: the Route user form no longer reads the role catalog)
```

Recorded with no actor, deliberately: no person requested it from a screen, an approved cleanup executed it, and attributing it to someone would credit them with a decision they did not make.

**Route Users still works without it** — the form reads `/api/route/users/assignable-roles`, which needs only `users.read`. Proven by the browser test that opens the selector as Administrador.

---

## 6. Vehicles UX — before and after

| | Before | After |
|---|---|---|
| Page opens on | a permanent empty form | the vehicle list |
| Create | inline form at the top | **`Add Vehicle` → dialog** |
| Edit | same inline form, scrolled up | same dialog, pre-filled |
| Inactive filter | below the form | beside the primary action |
| Row lifecycle | contextual menu | **unchanged** |
| Business rules | — | **unchanged** |

Create and edit share one dialog on purpose: the same six fields and the same validations, and splitting them would create two places to fix the same thing.

Browser-validated in one journey: cancel creates nothing → create → row appears → verified in PostgreSQL → edit → deactivate → row disappears → show inactive → badge reads *Inactive* → reactivate → badge reads *Active*.

---

## 7. Standardized Lists UX — before and after

| | Before | After |
|---|---|---|
| Group navigation | bare column | **bordered container panel** |
| The 8 groups, labels, counts | present | **unchanged** |
| Create | permanent `Add a value` input | **`Add Value` → contextual dialog** |
| Which list receives the value | implicit | **named in the dialog header** |
| Selection after save | — | **preserved**; count updates |
| Table header | `Order · Label · Status · Actions` | `Order · Label · Status · ·` |
| Reorder arrows | mixed with the row menu | **grouped with Order** |
| Reorder behavior | — | **unchanged** |
| Lifecycle menu | — | **unchanged** |

The `Actions` header is gone because that column carries only the contextual menu, and titling it named a control that already explains itself. The arrows moved next to Order because moving a row is position, not a decision about the value.

Browser-validated: eight groups with correct counts inside the container → no `Actions` header → select *Office Purposes* → `Add Value` → header reads *"Add value to Office Purposes"* → save → value appears, count goes 4 → 5, **selection does not move** → cancel writes nothing → reorder works → deactivate → show inactive → badge reads *Inactive*.

---

## 8. The 28 approved values

Unchanged. Labels, order, spelling, counts, seed keys, active/inactive and delete/tombstone semantics all untouched by this checkpoint.

| Check | Result |
|---|---|
| Seeded values still present after the UX work | **28**, asserted inside the browser test |
| Code vs approved document | **identical** — `test_standard_value_catalog.py`, 12 tests |
| Provisioning idempotency and lifecycle | **10 tests**, green |
| Duplicates / renames / resurrections | none |

---

## 9. Test results

All runs **serial**, against controlled test databases. No discarded or invalid concurrent run is counted as evidence.

### Backend, by batch

| Batch | Tests | Exit |
|---|---:|---|
| Unit + architecture nets + catalog | 111 | `0` |
| **A02 access model + product context + provisioning** | 78 | `0` |
| Auth / CSRF / authorization matrix | 83 | `0` |
| Route configuration + admin lifecycle | 143 | `0` |
| Data: constraints, pagination, tenant isolation | 47 | `0` |
| Work Sessions + Trips (RTE03/RTE04 access) | 108 | `0` |
| Odometer (RTE04 access) | 48 | `0` |
| Platform + integration + maker-checker | 49 | `0` |
| **Backend total** | **667** | **0 failures** |

### Browser

| Suite | Tests | Exit |
|---|---:|---|
| Route access, incl. **FR-03 for Superadmin, Core owner and Core admin** | 9 | `0` |
| **Admin UX (Vehicles list-first, Lists contextual create)** | 2 | `0` |
| Standardized Values rendering + tenant isolation | 2 | `0` |
| Trip + odometer (13 RTE04 flows) | 6 | `0` |
| Admin lifecycle (RTE02-A01) | 6 | `0` |
| Work Session offline queue (RTE03) | 1 | `0` |
| **Browser total** | **26** | **0 failures** |

### Frontend

`npm run typecheck` **0 errors** · `npm run lint:ts` **0 errors** · `npm run build:prod` **exit 0**.

### Corrected counts from the previous report

§"Documentation Correction" is right that the earlier figure was wrong, and the current numbers differ from both — this checkpoint added tests and reran everything.

| | Previous report | **This closure** |
|---|---:|---:|
| Backend | 331 *(reported)* / 325 *(supported)* | **667** |
| Browser | 6 | **26** |
| **Total** | 331 | **693** |

The earlier figure came from adding batch totals across runs that overlapped in coverage. These are the actual final execution counts, per batch, each with its exit code.

### Failures that occurred during this checkpoint

Reported because they happened, not because they survived.

| What failed | Cause | Status |
|---|---|---|
| FR-03 browser test, all three actors — selector showed 6 options | `CONFIRMED` — the form called the Core contract, so the product context was never set | Fixed by passing the contract through the panel; re-run **9/9** |
| `test_every_relative_import_resolves_to_a_versioned_file` | `CONFIRMED` — `contract.ts` not yet git-tracked. The net exists to force this | `git add`; re-run **111/111** |
| `test_change_plan_before_starting_is_rejected`, with `TimeoutError` → 500 | `CONFIRMED` — connection exhaustion under the tests' `NullPool`; the batch took 1450s against 531s for the same files earlier | Not a logic failure: the same batch re-run alone is **108/108, exit 0** |

### Existing tests whose expectations changed

Five. None was weakened; each expectation was superseded by an approved decision, and the reason is recorded in the test itself.

| Test | Change | Superseded by |
|---|---|---|
| `test_a_supervisor_cannot_administer_standard_values` | now asserts the Supervisor **reads** (200) and cannot create, list groups or see retired values | BR-03 — reading to choose is not administering |
| `test_planning_a_trip_requires_the_capability` | denies a `viewer`; asserts the Administrador **can** plan | BR-02 — both product roles execute |
| `test_vehicle_lifecycle_in_the_browser` | opens the create dialog instead of waiting for the permanent form | FR-05 |
| `test_standard_value_lifecycle_in_the_browser` | same, for `Add Value` | FR-06 |
| `test_user_delete_is_reachable_and_complete_from_the_admin_ui` | throwaway user created as `supervisor`, not `viewer` | FR-02 — its intent was "some user" |
| *(new)* `test_the_route_user_form_shows_two_roles_to_every_authority` | added: browser, three authorities, plus the API bypass | FR-03, mandatory |

---

## 10. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Gap |
|---|---|---|---|
| Route Users exposes exactly two roles | yes | browser selector = 2, four actor types | none |
| True for Superadmin | yes | FR-03 scenario, API + browser | none |
| Core roles never assignable via Route | yes | 12 API cases, 403, nothing written | none |
| Core management unchanged | yes | Core actor via Core contract, 200 | none |
| Not solved by frontend filtering | yes | context is the route; policy is server-side | none |
| `roles.read` removed from Administrador | yes | §5, audited, idempotent | none |
| 12 / 2 final capability counts | yes | database + test | none |
| Route Users works without `roles.read` | yes | browser selector opens and saves | none |
| Vehicles list-first + modal | yes | §6, browser journey | none |
| Vehicle lifecycle intact | yes | edit, deactivate, filter, reactivate | none |
| Lists container + contextual modal | yes | §7, browser journey | none |
| Selection preserved after save | yes | count 4→5, group still selected | none |
| `Actions` header removed | yes | `columnheader` count = 0 | none |
| Reorder intact and understandable | yes | arrows with Order; move up verified | none |
| 28 values intact | yes | §8 | none |
| RTE03 / RTE04 access smoke | yes | 108 + 48 backend, 6 browser | none |
| Backend / browser regression green | yes | §9 | none |
| **Core `manager → owner` exposure** | **not fixed, by instruction** | §11 | **out of scope** |

---

## 11. Remaining Core-only exposure (out of scope)

`manager` holds `users.create` and `users.update` in the Core catalog, and through the **Core contract** can assign `owner` — the same position `route_admin` was in before A02.

This is **Core/Foundation exposure, not CER Route**. §"Out of Scope" of this instruction forbids fixing it here and §"Do not" requires it stay documented as a separate Core Security Gap. It is unchanged, still documented, and deserves its own checkpoint.

It is **not** reachable through CER Route: a `manager` is not a Route product role and the Route contract rejects any Core role regardless of caller.

---

## 12. Security and audit

- Server-side enforcement on create **and** update, in both contracts.
- Tenant isolation intact; cross-tenant roles rejected with 404, non-disclosing.
- No client-trusted tenant scope; the product context comes from the route, not from the request body or a header.
- No platform-superuser path; `is_superuser` refused with 422.
- Role changes audited with actor, target, old and new role, timestamp and tenant.
- The `roles.read` cleanup is audited.
- Supervisor denied from every Admin/Manage endpoint, in both contracts.

---

## 13. Operational actions

| Action | Status |
|---|---|
| `cleanup_route_admin_roles_read` on the aligned tenant | **done** — 1 grant revoked, audited |
| Bootstrap on the aligned tenant | done in A02 — 28 values, capabilities aligned |
| Frontend production build on deploy | **required** |
| Run the cleanup script on any other environment where `route_admin` holds `roles.read` | **required if such an environment exists** |

**Local is not shared.** Everything here ran on a local Windows machine against a local PostgreSQL. No shared environment was inspected or changed.

---

## 14. Scope confirmation

Not changed: RTE03 Work Session rules or time semantics; RTE04 Trip state machine; odometer business rules; END Option B; Routing Mileage definition; Standardized Value business lifecycle; vehicle business lifecycle; the 28 approved values; tenant isolation; Core role meanings; the platform superuser model; the existing audit primitive.

Not created: CEO/COO/RM/OSM roles; multi-role membership; a generic revocation engine; a second Standardized Values seeding path; duplicate Route user management — the Route contract is the same router mounted twice, not a second implementation.

Core/Foundation RBAC was **not** redesigned. No Core role was deleted or renamed.

**RTE05 was not started.**

---

## 15. Status

**RTE02-A02 — Completed / Ready for CER Certification.**

No decision is pending on CER for this checkpoint. The one open item, the Core `manager → owner` exposure, is out of scope by instruction and carried forward as a separate Core Security Gap.

Development stops here and does not continue with RTE04 closure or RTE05 until CER certifies RTE02-A02.
