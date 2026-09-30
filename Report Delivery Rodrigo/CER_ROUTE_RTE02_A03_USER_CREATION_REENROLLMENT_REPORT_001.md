# CER Route — RTE02-A03: User Creation UX + Same-Tenant Re-enrollment

| | |
|---|---|
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE02_A03_USER_CREATION_REENROLLMENT_INSTRUCTIONS_001.md` |
| **Branch** | `feature/rte02-a03-user-creation`, cut from `dev` |
| **Date** | 2026-09-29 |
| **Proposed status** | **A03 — Ready for CER Certification** |
| **Does not overwrite** | any previous report |
| **RTE02 / A01 / A02** | certified baseline preserved |
| **RTE03 / RTE04 / RTE05** | untouched |
| **RTE06** | not modified, not started |
| **STOP conditions** | **none triggered** — all nine evaluated in §1 |

---

## 0. Read first

**1. One authoritative password policy exists.** `MIN_PASSWORD_LENGTH = 10`, declared once and imported. The first STOP condition asks whether contradictory policies exist; they do not. §2.

**2. The full uniqueness constraint was A01's deliberate preparation for this checkpoint.** Migration 0004 says, in as many words, that leaving it partial *"would enable an identity re-enrollment, which this addendum explicitly defers"*. Restoring the tombstoned row is not a workaround for the constraint — it is what that decision left ready. §10.

**3. Three mistakes of mine are reported with their cause**, including one destructive editing error that emptied a file and one **over-claim in an earlier draft of this report**: four §13/§15 requirements were tabulated as covered when no test exercised them. They are covered now, and the over-claim is reported rather than quietly overwritten. §21.

---

## 1. Current State Audit (§4, sixteen items)

| # | Item | Finding |
|---|---|---|
| 1 | Core password schema(s) used by Route Add User | `MIN_PASSWORD_LENGTH = 10` in `app/routers_api/users/schemas.py:9`, imported by `usermanagement/schemas.py`. **One policy** |
| 2 | Frontend password helper / validation | `SecurityUserForm.tsx` validated `< 6` with the message "at least 6 characters"; **no helper text at all** |
| 3 | Create endpoint used by Route Users | `UserManagementDAO.create_user_in_company`, behind the same router mounted twice (A02 product contract) |
| 4 | A02 product-context wrapper | `marcar_contexto_de_route` + `acota_a_roles_de_route` + `ensure_assignable_role`. Intact |
| 5 | Duplicate-username lookup | **Reactive only**: catch `IntegrityError`, map the violated constraint's name to an English sentence |
| 6 | `user` uniqueness | `user_username_key` — username unique **platform-wide**. Email index is `unique=False` |
| 7 | `user_company` uniqueness | `uq_user_company_user_company` on `(user_id, company_id)`, **full, not partial** |
| 8 | Tombstone filtering | `query()`, `set_access` and `delete_membership` all filter `deleted_at IS NULL`. A tombstoned membership is invisible to the list **and to Reactivate** |
| 9 | Deactivate / Reactivate | `set_access(is_active)` — `UPDATE` on rows without a tombstone |
| 10 | Tenant Delete | `deleted_at = now()` on `user_company`; Core `user` untouched |
| 11 | Membership state after Delete | Row survives: `deleted_at` set, `is_active` and `role_id` preserved |
| 12 | Audit behaviour | Core `record_event`, invoked at router level |
| 13 | Route role restriction | `ensure_assignable_role`, A02. Intact |
| 14 | Reusable restore primitive | **None existed.** No "undelete" path. This was the gap |
| 15 | Frontend/API error normalization | `normalizeApiError` **already** extracted field errors from `detail[].loc/.msg` — and `SecurityUserForm` did not use it, reading `(error as Error).message` instead |
| 16 | Credential behaviour on restore | **No behaviour existed**: create always inserts a new `Users` row with a fresh hash; the re-enrollment path did not exist |

### The instruction's warning was worth heeding

§4 says *"Do not assume the duplicate conflict is caused only by username until verified."* Verified: the conflict can come from **two** constraints — `user_username_key` (platform-wide username) or `uq_user_company_user_company` (membership). Only the first can fire on a fresh create; the second fires when the identity exists and a membership row is already present, tombstoned or not. That distinction is the whole basis of the classification in §5.

### STOP conditions, each evaluated

| Condition | Verdict |
|---|---|
| Password policy is not 10, or several conflict | **No** — one policy, value 10 |
| Re-enrollment requires merging Core identities | **No** — the same `user.id` is reused |
| Requires automatic cross-tenant linking | **No** — only the current tenant's own history is consulted |
| Requires exposing another tenant | **No** — §13 |
| Safe restoration requires destroying history/audit | **No** — `audit_event` is append-only and records the transition |
| Credential handling requires inventing a reset rule | **No** — the existing credential is preserved and the UI says so |
| A new Route role/capability is required | **No** — `users.create` |
| RTE03+ domain behaviour must change | **No** |
| RTE06 must be modified | **No** |

---

## 2. Password Policy Source

**Single source:** `MIN_PASSWORD_LENGTH = 10` in `app/routers_api/users/schemas.py:9`.

Used by `UserCreate.password`, `UserSelfUpdate.new_password`, `UserManagementCreate.password` and `UserManagementUpdate.password` — the last two by importing the constant, not by repeating the number. A repository-wide search for a second length rule (`len(password)`, another `min_length`, a literal 6) returns nothing.

The server remains authoritative. The frontend now mirrors the same value in one place (`MIN_PASSWORD = 10`) and says where it comes from.

---

## 3. UI / Server Validation Gap

| | Before | After |
|---|---|---|
| Client validation | `password.length < 6` | `< MIN_PASSWORD` (10) |
| Message | "Password must be at least 6 characters" | "Password must be at least 10 characters" |
| Helper text | **none** | "Minimum 10 characters", shown under the field |
| 6–9 characters | passed the client, server returned 422, UI showed `Submission failed` | caught at the field, with the right number |
| Server 422 | collapsed into a toast title | mapped to the field named in `detail[].loc` |

**Why the generic toast happened**, which the instruction asked to identify: the Redux thunks reject with `error.response.data`, so what reaches the component's `catch` is `{detail: …}` — **not** an `Error`. Reading `(error as Error).message` yielded `undefined`, and the fallback string took over. The server had explained itself; the client was looking in the wrong place.

---

## 4. Error Contract

A machine-readable envelope, because §9 requires the UI not to parse English.

```
409  { "detail": { "code": "<stable code>", "message": "<for the person>",
                   "user_id": <only same-tenant cases>,
                   "display_name": "<only same-tenant cases>" } }
422  { "detail": [ { "loc": [..., "password"], "msg": "...", ... } ] }
```

| Code | Meaning | HTTP |
|---|---|---|
| `same_tenant_active` | works here, access live | 409 |
| `same_tenant_inactive` | works here, access suspended | 409 |
| `same_tenant_removed` | was here, access removed — **re-enrollment available** | 409 |
| `username_unavailable` | taken platform-wide, no history in this tenant | 409 |
| `role_not_allowed` | role not assignable from CER Route | 403 (A02, pre-existing) |
| `reenrollment_already_done` | another admin restored them first | 409 |

**Backward compatibility:** `normalizeApiError` still handles a string `detail` (every other endpoint) and an array `detail` (Pydantic). The coded object is a third shape, checked before the array because a code is more specific than a message. Old servers keep working; old clients see the `message` and lose only the recovery path, never gaining unsafe behaviour.

`normalizeRejectedPayload` was added for the thunk shape, so both paths share one interpretation instead of two that can drift.

---

## 5. Existing-User Classification Logic

`clasificar_nombre(username, company_id)` runs **before** any write:

1. find `Users` by username — if absent, the name is free;
2. find `UserCompany` for `(user.id, company_id)`, **without** filtering the tombstone — that row is precisely what makes re-enrollment possible, and the normal query hides it;
3. no membership → `username_unavailable`;
4. tombstoned → `same_tenant_removed`;
5. live and active → `same_tenant_active`;
6. live and inactive → `same_tenant_inactive`.

The reactive `IntegrityError` handling is **kept** underneath: another request fits between classifying and writing, and the database remains the guarantor of uniqueness. Classification improves the message; it does not replace the constraint.

---

## 6. Active Same-Tenant Behavior (D-A03-02, FR-04)

`same_tenant_active`, message *"A user with this username already exists in this company."*, shown at the Username field. **No identity created, no membership created, nothing mutated** — asserted by counting `user_company` rows before and after. No re-enrollment action is offered, because nobody left.

---

## 7. Deactivated Same-Tenant Behavior (D-A03-03, FR-05)

`same_tenant_inactive`, message directing the Admin to reactivate rather than recreate. The certified Reactivate lifecycle is untouched and is the path.

Asserted after the conflict: **one** membership, still without a tombstone, still `is_active = false`. Re-enrollment is refused for this state — calling the endpoint directly returns `same_tenant_inactive` and **does not change the role**, so it cannot become a side door into reactivation with a different role.

---

## 8. Removed Same-Tenant Re-enrollment (D-A03-04, FR-06)

The conflict carries `code`, `message`, `user_id` and `display_name` — the minimum for the screen to offer re-adding a specific person, and all of it data this company already sees in its own user list.

**No internal vocabulary reaches the person.** Asserted against the message text: `user_company`, `deleted_at`, `tombstone` and `membership` are all absent, in the API response and on screen.

The flow, per §10:

1. Submit returns the conflict — **nothing is restored**;
2. a confirmation states the person previously belonged to the company and which role will apply;
3. **Cancel writes nothing** — asserted by re-reading the tombstone after cancelling;
4. Confirm calls `POST /{user_id}/reenrollment` explicitly.

---

## 9. Core Identity Preservation (FR-07)

Same `user.id` before and after. A count of `"user"` rows for that username returns **1** after the round trip. No second identity, no merge, no cross-tenant linking.

---

## 10. Membership Persistence

**The same row is restored.** `UPDATE user_company SET deleted_at = NULL, is_active = true, role_id = :role WHERE user_id = … AND company_id = … AND deleted_at IS NOT NULL`.

Asserted: one membership row before, **the same `id`** after, tombstone cleared, active, with the chosen role. No parallel membership is created to bypass uniqueness (FR-07, AC-12).

### Why this is the right shape, not a workaround

Migration 0004 left `uq_user_company_user_company` **full rather than partial**, with this comment: making it partial *"would enable an identity re-enrollment, which this addendum explicitly defers"*. A01 shaped the constraint anticipating this checkpoint. Restoring the row is what that decision prepared.

**One consequence, declared:** restoring clears the tombstone, so the fact that the person was once removed lives in the **audit trail**, not in the row. `audit_event` is append-only and trigger-protected, so §11.11 ("historical evidence remains auditable") holds — but the row itself no longer shows it, and that is worth knowing before anyone looks for it there.

---

## 11. Credential Handling (FR-09)

**Audited first, as required:** no re-enrollment credential behaviour existed, because the path did not exist. Create always inserted a new `Users` row with a fresh hash.

**As-built now:** re-enrollment touches **no** credential. The person returns with the password they already had. The re-enrollment request carries only `role_id` — not username, email or password — so there is nothing to overwrite even by accident.

**The tension the instruction anticipated, and how it is resolved without inventing policy:** Add User requires a password, and on re-enrollment that typed value is **not applied**. Preserving the existing credential is the certified default, not a new rule — so no STOP. But a password typed and silently discarded is its own confusion, so **the confirmation says it out loud**: *"they will keep the password they already had."*

**Never audited:** asserted against the **full text** of the audit event, not against the fields I expected — `password`, `hash`, `token`, `secret` and the literal password value are all absent. If someone adds the credential to `changes` tomorrow, that test fails.

---

## 12. Route Role Enforcement (D-A03-06, FR-08)

`ensure_assignable_role` guards re-enrollment exactly as it guards create. Called from the router, so a direct API call is bound by it too.

Asserted by calling the endpoint directly with each Core role: `owner`, `admin`, `manager`, `viewer` → **403 each**, and the membership **stays removed** — a refusal does not half-restore. The browser form offers exactly Administrador and Supervisor, and none of the four Core roles appears as an option.

A platform Superadmin on the Route surface is bound too: requesting `owner` returns 403. A02's rule is двойная — product context **or** actor's product role — and the Route context constrains on its own.

---

## 13. Cross-Tenant / Enumeration Protection (D-A03-05, FR-10)

A username that exists platform-wide with no history in this tenant returns `username_unavailable` and the message *"This username is unavailable."*

Asserted: the response carries **no `user_id` and no `display_name`**, so nothing identifies the person or their company. The other tenant's membership is re-read afterwards and is unchanged.

Re-enrollment cannot cross tenants: removing someone in `beta` and attempting to re-enroll them from `alpha` returns `username_unavailable` — the same answer as for any unknown id, so it does not confirm existence — and `beta`'s membership stays removed.

The current tenant **is** told about its own history, which §10 permits and which is what makes re-adding possible at all.

---

## 14. Audit (§12)

`record_event` at router level, matching the existing pattern rather than a new mechanism:

| Field | Value |
|---|---|
| actor | authenticated user |
| tenant | from context |
| entity | `user_company`, restored membership id |
| action | `reenroll` |
| prior state | `membership: removed` |
| resulting state | `membership: active` |
| resulting role | `role_id: {old, new}` |
| timestamp / context | `occurred_at`, request context |

Asserted present, with the actor checked, and asserted **free of credentials** (§11).

---

## 15. Browser Evidence

`tests/e2e/test_user_creation_browser.py` — **7 journeys, 0 failures, exit 0.** Production bundle, Microsoft Edge, 1280×900, via normal navigation.

| Journey | Asserts |
|---|---|
| Password minimum | "Minimum 10 characters" visible; "at least 6 characters" absent; a 9-character password produces the field error with the right number; `Submission failed` absent; **0 rows created** |
| Active duplicate | message at the Username field; **no** Re-add action offered |
| Re-enrollment | first Submit does not restore; confirmation names the person and states the credential is kept; no internal vocabulary on screen; **Cancel leaves the tombstone**; Confirm restores the same row with the chosen role; one platform identity |
| Route roles | Administrador and Supervisor offered; `owner`/`admin`/`manager`/`viewer` absent |
| Server 422 mapped to its field | a 422 naming `body.password` lands **at the Password field** with the server's own wording; the notice directs to the fields; `"loc"` absent from the screen |
| Unexpected server error (500) | generic notice + retry; `Internal Server Error` **absent** from the screen; the form keeps what was typed; **0 rows created** |
| Malformed validation body | same safe fallback; the body's keys absent from the screen; **0 rows created** |

**Why three of these intercept the request.** The three added journeys respond to the create `POST` from the browser instead of letting it reach the server, and each has a reason the server cannot supply:

- **Server 422 → Password.** The client validates the length *before* sending (FR-01), so the server's password 422 is unreachable through the screen. Testing only the reachable path leaves the **mapping** — `detail[].loc` → form field — with no evidence, and the mapping is what FR-02 asks for. The body used is the one Pydantic actually emits.
- **500 and malformed 422.** Neither can be provoked from a working server without breaking it.

The interception is filtered by method: the same URL serves the panel's list, and capturing that too would empty the screen for a reason unrelated to what is under test. Per §15 of the instruction these are deterministic doubles for failure paths, not substitutes for the server-side evidence in §16.

**One test-anchoring change, declared:** the three form selects had no `id` while every text field did. Ids were added following the same `security-user-*` convention, so the journeys anchor on them rather than on positional guesses. No behaviour change.

---

## 16. API Evidence

`tests/integration/test_user_reenrollment.py` — **19 tests, 0 failures, exit 0.** The matrix is tabulated in §20.

Two of them cover the duplicate create directly: the **sequential** double submit (first `200`, second `409 same_tenant_active`, one platform identity, one membership) and the **genuinely concurrent** one (`asyncio.gather` of two identical creates → exactly one success, one identity). The concurrent case is what shows that the classifier improves the message without replacing the constraint: both requests pass classification — the username is free at that instant — and the database rejects the second. That is why the `IntegrityError` catch remains underneath it.

---

## 17. Concurrency / Replay

| Case | Behaviour |
|---|---|
| Stale confirmation (edge case 14) | the second request finds no tombstone to clear → 409, and **the first admin's role survives** |
| Two simultaneous re-enrollments (edge case 13) | exactly one 200, one membership row |
| Double submit on re-enrollment | the classifier returns the same conflict; the write is idempotent because the `UPDATE` is conditional |
| Double submit on create (edge case 12) | sequential: `200` then `409 same_tenant_active`, one identity, one membership. Concurrent: exactly one success — the unique constraint, not the classifier |

The condition lives in the `WHERE`, not in a prior `if` that both requests would pass — the same pattern that already protects activity terminalization.

---

## 18. Regression

| Suite | Result |
|---|---|
| `test_user_reenrollment.py` (A03) | **19, 0 failures, exit 0** |
| `test_user_creation_browser.py` (A03) | **7 journeys, 0 failures, exit 0** |
| A01 admin lifecycle, A02 access model / product context / role authority, Route foundation, authorization matrix, tenant isolation | **227 tests, 0 failures, exit 0** |
| Browser: Route access, admin lifecycle | **15 journeys, 0 failures, exit 0** |

**Total: 227 + 15 regression, plus 19 + 7 new — 268 tests, 0 failures, every batch exit 0.**

The 227-test and 15-journey regression batches are the results of the earlier run in this same checkpoint and are **not re-executed** after the evidence additions of §21.5: those additions touched only the two A03 test files — `git status` shows no source file modified — so no behaviour they cover could have changed. The two A03 batches were re-run in full and are reported above.

No test was weakened or removed.

---

## 19. Typecheck / Lint / Build

| Check | Result |
|---|---|
| `npm run typecheck` | **0 errors** |
| `npm run lint:ts` | **0 errors** |
| `npm run build:prod` | **exit 0** |
| `uv run python -c "import app.main"` | **exit 0** |
| Migration | **none** — no schema change; the tombstoned row already existed |

---

## 20. Expected → Implemented → Evidence → Gap

| Expected | Implemented | Evidence | Classification |
|---|---|---|---|
| UI no longer says 6 | yes | §15 journey 1 | AS-BUILT / CONFIRMED |
| 6 and 9 show actionable Password errors | yes | §15, §16 | AS-BUILT / CONFIRMED |
| 10+ passes | yes | §16 | AS-BUILT / CONFIRMED |
| Server remains authoritative | yes | §2 — one constant, unchanged | AS-BUILT / CONFIRMED |
| Structured errors reach the right field | yes | §3, §15 — 422 interception proves the `loc` → field mapping | AS-BUILT / CONFIRMED |
| Unexpected / malformed error falls back safely | yes | §15 — 500 and malformed 422, no leakage, retry offered | AS-BUILT / CONFIRMED |
| Duplicate create is consistent | yes | §16, §17 — sequential and concurrent | AS-BUILT / CONFIRMED |
| Generic failure is not the sole feedback | yes | §15 — `Submission failed` absent | AS-BUILT / CONFIRMED |
| Active duplicate explained | yes | §6 | AS-BUILT / CONFIRMED |
| Deactivated routed to Reactivate | yes | §7 | AS-BUILT / CONFIRMED |
| Removed can be re-enrolled explicitly | yes | §8, §15 | AS-BUILT / CONFIRMED |
| Core identity preserved | yes | §9 | AS-BUILT / CONFIRMED |
| No duplicate Core user | yes | §9 — count = 1 | AS-BUILT / CONFIRMED |
| No duplicate membership | yes | §10 — same row id | AS-BUILT / CONFIRMED |
| Explicit confirmation required | yes | §8, §15 | AS-BUILT / CONFIRMED |
| Cancel mutates nothing | yes | §15 | AS-BUILT / CONFIRMED |
| Only Administrador / Supervisor | yes | §12 | AS-BUILT / CONFIRMED |
| Core roles unreachable through Route | yes | §12 — 403 ×4 | AS-BUILT / CONFIRMED |
| Direct API bypass fails | yes | §12 | AS-BUILT / CONFIRMED |
| External-tenant identity not disclosed | yes | §13 | AS-BUILT / CONFIRMED |
| Re-enrollment audited | yes | §14 | AS-BUILT / CONFIRMED |
| Password absent from audit | yes | §11 — full-text assertion | AS-BUILT / CONFIRMED |
| Tenant isolation proven | yes | §13, §18 | AS-BUILT / CONFIRMED |
| Historical Route data intact | yes | §21.3 | AS-BUILT / CONFIRMED |
| Deactivate / Reactivate intact | yes | §7, §18 | AS-BUILT / CONFIRMED |
| Delete intact | yes | §18 | AS-BUILT / CONFIRMED |
| A02 protections intact | yes | §12, §18 | AS-BUILT / CONFIRMED |
| RTE03/04/05 unchanged | yes | no file in those domains touched | AS-BUILT / CONFIRMED |
| typecheck / lint / build green | yes | §19 | AS-BUILT / CONFIRMED |
| Backend / browser regression green | yes | §18 | AS-BUILT / CONFIRMED |

### Edge cases (§13)

| # | Case | Covered |
|---|---|---|
| 1–3 | password 6 / 9 / 10 | §16, §15 |
| 4–6 | active / deactivated / removed same-tenant | §6, §7, §8 |
| 7–8 | removed with Supervisor designation and vehicle assignment | §21.3 |
| 9 | username only outside current tenant | §13 |
| 10 | email collision | **not applicable** — the Core email index is `unique=False`; verified, not assumed |
| 11 | case normalization | as-built: username is compared after `strip()`, **case-sensitively**; email is lowercased on create. Declared as observed, unchanged |
| 12 | duplicate double-submit | §16, §17 — sequential **and** concurrent |
| 13 | concurrent re-enrollment | §17 |
| 14 | stale confirmation | §17 |
| 15–16 | Route Admin attempting `owner` / `admin` | §12 |
| 17 | platform Superadmin on Route Users | §12 |
| 18 | Supervisor direct API attempt | §12 |
| 19 | malformed validation response | §15 — browser evidence: `{"detail":{"unexpected":"shape"}}` → generic notice, keys not shown, nothing created |
| 20 | unexpected server error | §15 — browser evidence: `500` → generic notice + retry; the server's internal text is **not** shown |

---

## 21. Deviations / Debt / Pending Validation

### 21.1 A destructive editing error of mine — `CONFIRMED`, recovered

While applying a patch I **emptied `SecurityUserForm.tsx`**. The script's last statement opened the file for writing — truncating it — and read it afterwards, so it wrote back an empty string. Restored in full from git (461 lines) and reapplied with a script that reads once and writes once.

Nothing was lost because the file was version-controlled. It is also why I do not edit untracked files: the same slip on an unversioned file would have destroyed work with no recovery.

### 21.2 A false expectation of mine — `CONFIRMED`, corrected

I asserted that removing tenant access tombstones the supervisor profile. **It does not.** A01 chose a soft delete for the membership precisely so it would not: `supervisor_profile` references it with `CASCADE`, and a physical delete would have taken the Route designation and its vehicle history with it.

So §13's rule ("do not automatically resurrect deleted Supervisor designation or vehicle assignment") is satisfied by doing nothing — there is nothing deleted to resurrect. The test was corrected to the measured behaviour, not to the one I assumed.

### 21.3 Route history across the round trip — `AS-BUILT / CONFIRMED`

Removing and re-adding a user who held a supervisor designation and a vehicle assignment leaves both rows untouched: the assignment count is unchanged and the profile stays live. Re-enrollment neither resurrects nor disturbs them.

### 21.4 Declared as-built, for CER's awareness — no action taken

| Observation | Why it is reported rather than changed |
|---|---|
| Restoring clears the tombstone, so "was once removed" lives only in the audit trail | §11.11 is satisfied (`audit_event` is append-only), but the row no longer shows it |
| Username comparison is case-sensitive | Pre-existing behaviour; changing it is a username-policy redesign, which §6 places out of scope |
| A tombstoned membership is invisible to Reactivate | Pre-existing and correct: that state is re-enrollment's, not Reactivate's |

### 21.5 An over-claim in an earlier draft of this report — `CONFIRMED`, closed

An earlier draft tabulated four requirements as covered when **no test exercised them**. A clause-by-clause re-reading against the test files — `grep`, not against my own summary of them — found it:

| Requirement | What the draft said | What was true |
|---|---|---|
| FR-02 / AC-05, server 422 → Password field | "§3, §15" | no browser journey provoked a server 422; the client pre-empts it, so the mapping had no evidence |
| §13.19, malformed validation body | described the code path | no test exercised it |
| §13.20, unexpected server error | described the code path | no test exercised it |
| §13.12, duplicate create | "§17" | §17 covered double submit on **re-enrollment**; create was not covered |

**Cause — `CONFIRMED`:** for these four I reported the *mechanism I had written* as though it were the *evidence that it works*. Describing a code path is not exercising it, and §3 of the reporting protocol says absent evidence never becomes `PASS`. Two of them — 19 and 20 — were even worded as descriptions of the code rather than as evidence, which is what made them easy to wave through.

All four now have tests (§15, §16, §17), all green. Reported rather than silently overwritten, because a report that repairs its own claims without saying so cannot be audited.

### 21.6 Two incidental findings, outside A03 scope — no action taken

Both surfaced while building the evidence above. Reported here, when found, with their verified cause; **neither was changed**, because A03's scope is creation validation, existing users and re-enrollment.

**1. While a modal dialog is open, toast notices leave the accessibility tree — `CONFIRMED`.**
The `Try again` action on the error notice is rendered, visible and clickable (`is_visible()` → true), but an ancestor carries `aria-hidden="true"`: Radix Dialog marks everything outside the open dialog as hidden, and the notifier mounts at the application root. Measured: `get_by_role("button", name="Try again")` → **0**; the same query with `include_hidden=True` → **1**.

*Impact:* a sighted administrator sees and can use the recovery; someone using a screen reader is **not told the creation failed**, because both the notice and its retry are outside the tree while the dialog is open. It affects every dialog-plus-toast pairing in the product, not only this screen — which is also why it does not belong to A03.

*Operational action:* none automatic. It is an accessibility decision at the shell level (announce inside the dialog, or render the notifier within it).

**2. `CER Route > Users` lists through the Core contract — `CONFIRMED`, no functional effect today.**
Measured from the browser on `/admin/route/users`:

```
GET /api/route/users/assignable-roles     ← the form: correct, product contract
GET /api/users/pagination?page=1&…        ← the list: Core contract
```

`SecurityUsersPanel` threads its `contract` prop into the form but not into its own pagination thunk, and `fetchUserManagementPagination` accepts no contract at all.

*Why it is not a defect today — verified, not assumed:* `GET /pagination` scopes by `company_id` and nothing else; the product context narrows **assignable roles** and role validation on write, never the listing. The two mounts return identical rows, so **tenant isolation is intact** and no data crosses a boundary. A02's fix, which was about who may grant which role, is unaffected — §12 proves it still holds.

*Why it is still worth reporting:* the coupling is missing rather than deliberately absent. If the Route contract is ever given a narrower listing, this panel will not follow it, and the failure will look like a server bug on a screen that is calling the wrong endpoint.

*Operational action:* none. It is a one-line change in a file A03 has no reason to touch.

### 21.7 Pending validation

**Real-device validation is not applicable** to this checkpoint — it is an administration screen used at desktop width, and it was validated there. No `PENDING VALIDATION` item remains inside A03 scope.

---

## 22. Proposed Status

**A03 — Ready for CER Certification.**

The two operational gaps are closed: the password requirement is stated before it is needed and validated with the server's own number, and a repeated username now produces a named, actionable outcome with a recovery path where one legitimately exists.

**No remaining `PARTIAL`, `NOT IMPLEMENTED / GAP`, `DEVIATION`, `UNAUTHORIZED DECISION`, `DECISION REQUIRED` or `BLOCKED` inside A03 scope.** The four requirements that an earlier draft over-claimed are now evidenced, and the over-claim is on the record at §21.5.

Two findings outside A03 scope are recorded at §21.6 for CER's decision: an accessibility gap affecting every dialog-plus-toast pairing, and a contract inconsistency in the users list with no functional effect today. Neither was acted on — reporting does not authorize scope.

### Operational action required elsewhere

**None.** No migration, no capability, no seed, no configuration. Deploying the built assets is the only requirement.

### Next step

RTE06, resumed at CP0 — which must be completed in full before CP1: `effective_from`, `effective_to`, Start Work occurrence time, the vehicle snapshot, **and the non-overlap invariant**, which is the part still outstanding.

# STOP
