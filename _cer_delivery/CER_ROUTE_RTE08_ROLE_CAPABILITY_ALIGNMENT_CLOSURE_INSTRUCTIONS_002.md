# CER Route — RTE08 Final Closure Delta
## Activity Explorer — Role Capability Alignment
### Product Owner Instructions for Development Agent
### Revision 002

## 1. Context

RTE08 — Activity Explorer is functionally implemented and is pending CER closure.

A cross-check performed during the RTE07 post-certification correction exposed a provisioning gap that also affects RTE08:

- `route.activity.read` exists in the capability catalog;
- the authorized role templates declare it where applicable;
- navigation, page and API use the capability correctly;
- however, existing tenants may not have their role grants aligned automatically when a new Route capability is introduced.

The confirmed corrective mechanism is:

`uv run python -m app.db.scripts.align_role_capabilities`

This command aligns existing tenant roles against the capabilities declared by their approved role templates.

For the real development tenant `cerroute`, the alignment already demonstrated:

- `route_admin → route.live.read`
- `route_admin → route.activity.read`
- other template-declared grants as applicable;
- second execution adds `0` grants.

This RTE08 delta closes the **existing-tenant authorization/provisioning gap** for Activity Explorer.

It is not a redesign of RBAC and not a new feature.

---

# 2. Objective

Ensure that every existing tenant whose approved role template declares:

`route.activity.read`

receives that capability through the supported alignment mechanism, so that authorized users can:

1. see **Activity** in CER Route navigation;
2. open the Activity Explorer page;
3. call the Activity Explorer API successfully;
4. receive only tenant-authorized historical data;
5. obtain the same result without manual database updates.

The correction must preserve:

- Supervisor denial where its template does not declare `route.activity.read`;
- tenant isolation;
- existing role templates;
- V0.7 Activity Explorer UX;
- existing RTE08 read contract;
- RTE07 behavior.

---

# 3. Confirmed Root Cause

Treat the following as the confirmed starting point unless new evidence disproves it:

```text
Capability catalog ............. correct
Role templates ................. correct
Navigation capability gate ..... correct
Page capability gate ............ correct
API capability gate ............. correct
Existing tenant grants .......... may be stale
Alignment path .................. previously incomplete
```

The previous bootstrap behavior aligned:

- capabilities globally; and
- role grants only for one configured company.

That was insufficient for multiple existing tenants.

Do not create another RTE08-specific permission patch.

Use the shared alignment mechanism.

---

# 4. Scope

Perform only the following:

1. Verify `route.activity.read` exists exactly once.
2. Verify the intended approved role templates declare it.
3. Verify `align_role_capabilities` processes existing tenants correctly.
4. Verify `cerroute` receives the expected Activity Explorer grant.
5. Verify idempotency.
6. Verify navigation / page / API parity.
7. Verify Supervisor remains denied unless its approved template explicitly changes in a future checkpoint.
8. Verify cross-tenant isolation.
9. Update RTE08 operational instructions/report so `bootstrap` is no longer documented as the required fix for this capability gap.
10. Deliver closure evidence.

---

# 5. Role Rule

Do not hardcode Activity Explorer access by role name.

Authorization remains capability-driven.

The rule is:

> A role may access Activity Explorer only when its approved template/effective grants include `route.activity.read`.

Expected CER Route behavior includes:

- `route_admin` → allowed;
- `supervisor` → denied.

If Core roles such as `owner` or `admin` legitimately declare `route.activity.read` through their existing templates, preserve that behavior.

Do not remove valid grants merely to force a two-role interpretation.

The invariant to protect is:

`effective grants ⊆ approved template grants`

and after alignment:

`all template-declared grants required by the product are present`

---

# 6. Alignment Requirements

The supported mechanism must:

- operate across existing tenant companies;
- never require manual SQL as the normal solution;
- never create a missing role silently;
- never revoke tenant-specific grants unless a separately authorized revocation mechanism exists;
- add only capabilities declared by the approved role template;
- be idempotent;
- audit each grant according to the existing audit conventions;
- reuse the existing permission catalog/bootstrap logic rather than duplicating capability definitions.

If a company lacks a template role, report it rather than creating it automatically.

---

# 7. Existing-Tenant Scenario — Mandatory

Prove this exact lifecycle:

```text
1. Tenant exists before route.activity.read is introduced.
2. Its authorized role already exists.
3. The capability exists in the current catalog.
4. The role grant is absent.
5. Run:
   uv run python -m app.db.scripts.align_role_capabilities
6. route.activity.read is added where the template declares it.
7. Activity appears in normal CER Route navigation.
8. Activity page opens.
9. Activity Explorer API returns authorized data.
10. Run alignment again.
11. Added grants = 0.
```

PASS required.

---

# 8. Navigation / Page / API Parity

Validate that the same capability controls all three layers:

```text
CER Route navigation
Activity Explorer page
Activity Explorer API
```

For an actor with `route.activity.read`:

```text
navigation .... visible
page .......... allowed
API ........... allowed
```

For an actor without it:

```text
navigation .... not exposed as authorized destination
page .......... denied
API ........... 403
```

No layer may use a different permission.

---

# 9. Tests Required

## T1 — Catalog uniqueness

Assert:

`route.activity.read`

exists exactly once.

PASS required.

## T2 — Template declaration

Assert the expected approved templates declare or do not declare `route.activity.read` correctly.

At minimum:

- `route_admin` → yes
- `supervisor` → no

Do not invent new template rules.

PASS required.

## T3 — Existing tenant alignment

Create or reproduce a stale tenant grant state.

Run the supported aligner.

Assert:

- missing `route.activity.read` is added;
- unrelated capabilities are unchanged;
- no role is created implicitly.

PASS required.

## T4 — Idempotency

Run alignment a second time.

Expected:

`0 new grants`

PASS required.

## T5 — Browser access

Using the same session where possible:

1. sign in as authorized administrator;
2. verify Activity is initially absent/denied in stale state;
3. align capabilities;
4. refresh/reload application state;
5. verify Activity appears;
6. open Activity Explorer successfully.

Do not require logout/login unless the actual application architecture requires it.

PASS required.

## T6 — API access

As the same authorized actor:

`GET /api/activity-explorer...`

Expected:

- success;
- tenant-scoped data only.

PASS required.

## T7 — Supervisor negative test

As `supervisor`:

- Activity Admin destination unavailable;
- direct page access denied;
- API returns 403.

PASS required.

## T8 — Cross-tenant isolation

Actor from tenant A must not receive tenant B historical records.

PASS required.

## T9 — RTE08 regression

Re-run the affected RTE08 suites:

- integration;
- browser desktop;
- browser mobile;
- authorization;
- tenant isolation;
- hierarchy;
- multi-Activity;
- business-day grouping.

No visible Activity Explorer change is expected.

---

# 10. Documentation Correction

The RTE08 implementation report previously stated the operational action:

`uv run python -m app.db.scripts.bootstrap`

as the way to seed `route.activity.read`.

That instruction is now superseded for this cross-tenant role-alignment need.

The authoritative operational action becomes:

`uv run python -m app.db.scripts.align_role_capabilities`

Update the incremental closure report accordingly.

Do not overwrite the original RTE08 Report 001.

---

# 11. Out of Scope

Do not use this delta to modify:

- Activity Explorer UX;
- V0.7 layout;
- hierarchy;
- filters;
- Work Session;
- Trips;
- Activities;
- Standardized Values;
- Today / Live behavior;
- general role architecture;
- organizational hierarchy;
- Reports;
- RTE09;
- RTE10-A01.

Do not add automatic role creation.

Do not add automatic revocation.

Do not couple authorization alignment to frontend logic.

---

# 12. Acceptance Criteria

The delta is complete only when:

1. Root cause remains confirmed as existing-tenant role grant alignment.
2. `route.activity.read` exists exactly once.
3. `route_admin` receives `route.activity.read` through the shared alignment path.
4. Supervisor remains without `route.activity.read`.
5. Other roles follow their existing approved templates.
6. Existing tenants are aligned without manual DB edits.
7. The alignment process is idempotent.
8. No missing role is silently created.
9. Each added grant is auditable.
10. Navigation, page and API agree.
11. Cross-tenant isolation remains green.
12. RTE08 visible UX remains unchanged.
13. RTE08 regression remains green.
14. The obsolete `bootstrap` operational instruction is superseded.
15. No `PARTIAL`, `GAP`, `BLOCKED` or unresolved `DECISION REQUIRED` remains in this delta.

---

# 13. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE08_ROLE_CAPABILITY_ALIGNMENT_CLOSURE_REPORT_002.md`

Include:

1. Executive Result
2. Confirmed Root Cause
3. Capability / Template Matrix
4. Existing-Tenant Reproduction
5. Alignment Execution
6. Idempotency Evidence
7. Navigation / Page / API Parity
8. Supervisor Negative Validation
9. Cross-Tenant Validation
10. RTE08 Regression
11. Operational Instruction Correction
12. Expected → Implemented → Evidence → Gap
13. Remaining Issues
14. Proposed Status

Use:

`observed → expected → correction → evidence`

---

# 14. Status Rule

If all acceptance criteria are green, propose:

`RTE08 ROLE CAPABILITY ALIGNMENT COMPLETE / READY FOR CER FINAL VALIDATION`

Do not declare:

`RTE08 CLOSED`

Final checkpoint certification remains with CER.

If a new product/role decision is genuinely required, stop with:

`RTE08 ROLE CAPABILITY ALIGNMENT BLOCKED — CER DECISION REQUIRED`

and provide:

`fact → impact → options → recommendation`

Do not leave the work as `PARTIAL`.

---

# 15. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE08_ROLE_CAPABILITY_ALIGNMENT_CLOSURE_REPORT_002.md`

**STOP.**

Do not start RTE09.

Do not resume RTE10-A01.

Do not modify RTE07 beyond reporting shared alignment evidence.

Wait for CER final review.
