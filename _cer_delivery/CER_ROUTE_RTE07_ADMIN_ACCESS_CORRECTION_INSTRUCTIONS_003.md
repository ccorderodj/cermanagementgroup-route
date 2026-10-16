# CER Route — RTE07 Post-Certification Correction
## Administrador access to Today / Live
### Product Owner Instructions for Development Agent
### Revision 003

## 1. Context

RTE07 — Today / Live was certified and closed based on the delivered evidence.

A field/product validation has now exposed a defect:

> The CER Route **Administrador** profile is not seeing/accessing the Today / Live experience as expected.

This is a **post-certification corrective delta for RTE07**.

It is not a redesign of Today / Live, not a new checkpoint, and not permission to modify the general RBAC architecture.

The certified CER Route product roles remain:

- **Administrador** → technical code `route_admin`
- **Supervisor** → technical code `supervisor`

The Today / Live surface is protected by:

`route.live.read`

The approved product rule is:

> CER Route Administrador can access Today / Live. Supervisor cannot.

---

# 2. Important Role Boundary

Before changing code or permissions, confirm the reported account's **effective CER Route role**.

The product role called **Administrador** is:

`route_admin`

Core/Foundation roles such as:

- `owner`
- `admin`
- `manager`
- `viewer`

are not to be redefined or repurposed by this correction.

## Mandatory diagnostic rule

If the affected user is actually assigned `route_admin`, continue with this corrective scope.

If the affected user is only a Core/Foundation `admin` and does **not** hold the CER Route `route_admin` role, do not silently broaden RTE07 access.

STOP and report:

`actual role → effective capabilities → expected CER Route role → proposed correction`

before changing role architecture.

---

# 3. Objective

Restore the certified behavior so that a CER Route **Administrador (`route_admin`)**:

1. sees **Today / Live** in the CER Route navigation;
2. can open the Today / Live page;
3. can call the Today / Live API;
4. receives the authorized tenant-scoped data;
5. does not require manual database permission editing.

At the same time:

- Supervisor remains denied;
- tenant isolation remains unchanged;
- Core roles remain unchanged;
- Today / Live UX remains unchanged.

---

# 4. Scope

Perform a narrow end-to-end diagnosis and correction covering:

1. effective role assigned to the affected user;
2. effective capabilities of `route_admin`;
3. whether `route.live.read` exists in the capability catalog;
4. whether `route.live.read` is actually granted to `route_admin` in the affected tenant;
5. provisioning/bootstrap/update behavior for existing tenants;
6. CER Route navigation capability gating;
7. Today / Live page guard;
8. Today / Live API guard;
9. browser behavior using a real `route_admin` account;
10. regression for Supervisor and tenant isolation.

---

# 5. Diagnostic Sequence — Mandatory Before Fix

Trace the failing path end to end.

## D1 — User / Role

Confirm:

- affected user identity;
- company/tenant;
- assigned CER Route role;
- technical role code;
- effective capabilities returned by the system.

Expected for the product Administrador:

`role = route_admin`

and:

`route.live.read = granted`

Do not infer capability from the visible role label alone.

---

## D2 — Catalog

Confirm that:

`route.live.read`

exists exactly once in the RBAC capability catalog and is attached to a protected surface.

Do not create a second capability with another name.

---

## D3 — Role template / provisioning

Determine whether the current `route_admin` role template includes `route.live.read`.

Then verify whether an **existing tenant created before RTE07** receives that newly introduced capability through the supported provisioning path.

This is critical.

A catalog definition that is correct for new tenants but does not update existing `route_admin` roles is not sufficient.

Classify the actual cause as one of:

- `ROLE TEMPLATE GAP`
- `EXISTING TENANT PROVISIONING GAP`
- `NAVIGATION GATING GAP`
- `PAGE GUARD GAP`
- `API AUTHORIZATION GAP`
- `DEPLOYMENT / DATA DRIFT`
- other, with evidence.

Do not guess.

---

## D4 — Navigation

Confirm that CER Route navigation shows **Today / Live** when the authenticated actor effectively has:

`route.live.read`

The navigation must be capability-driven.

Do not hardcode:

`if role == route_admin`

if the existing application convention is capability-based.

The visible navigation and server authorization must remain aligned.

---

## D5 — Page

Direct navigation to the Today / Live page as `route_admin` must succeed.

A hidden menu with a working page is still a defect.

A visible menu with a 403 page is also a defect.

Both must agree.

---

## D6 — API

Call the Today / Live API as the same `route_admin`.

Expected:

- authorized response;
- correct tenant scope;
- no client-provided company authority;
- no cross-tenant data.

---

# 6. Corrective Rule

Fix the **smallest actual cause** found by the diagnostic.

Preferred order:

`existing mechanism → correct provisioning → capability-driven navigation/page/API → no RBAC redesign`

If the issue is missing capability synchronization for existing tenants, implement/reuse an **idempotent supported provisioning/alignment mechanism**.

Do not require manual SQL updates as the product solution.

Do not modify unrelated Core roles to compensate for a Route provisioning defect.

---

# 7. Existing-Tenant Compatibility

The correction must explicitly validate this scenario:

```text
1. Tenant already existed before route.live.read was introduced.
2. route_admin role already existed.
3. RTE07 capability is introduced/deployed.
4. Supported provisioning/alignment runs.
5. Existing route_admin receives route.live.read.
6. Re-running the process produces no duplicate grants and no unrelated permission changes.
```

If this scenario already works, prove it and locate the defect elsewhere.

---

# 8. Roles & Permissions Expected After Correction

| Experience / Capability | Administrador (`route_admin`) | Supervisor |
|---|---:|---:|
| CER Route navigation | Yes | operational shell only |
| Today / Live visible | **Yes** | **No** |
| Today / Live page | **Allowed** | **Denied** |
| Today / Live API | **Allowed** | **403** |
| `route.live.read` | **Granted** | **Not granted** |

Do not change the certified separation of CER Route roles.

---

# 9. Tests Required

## T1 — Administrador capability

Using a real tenant user assigned to `route_admin`:

- effective permissions include `route.live.read`;
- no unrelated new capability is added by this correction.

PASS required.

---

## T2 — Administrador navigation

Browser test:

1. sign in as CER Route Administrador;
2. open CER Route shell;
3. verify **Today / Live** is visible in normal navigation;
4. click it;
5. page loads without 403.

PASS required.

---

## T3 — Administrador API

As the same `route_admin` user:

`GET` the Today / Live API.

Expected:

- success;
- only current tenant data.

PASS required.

---

## T4 — Supervisor remains denied

As `supervisor`:

- Today / Live is not exposed as an Admin destination;
- direct page access is denied;
- direct API access returns 403.

PASS required.

---

## T5 — Cross-tenant isolation

Administrador of tenant A must not receive tenant B supervisors or Today / Live facts.

PASS required.

---

## T6 — Existing-tenant upgrade/provisioning

Create/reproduce a state equivalent to a tenant whose `route_admin` existed before `route.live.read`.

Apply the supported provisioning/alignment mechanism.

Assert:

- `route.live.read` is granted;
- unrelated role grants unchanged;
- second execution is idempotent.

PASS required.

---

## T7 — Navigation / page / API parity

Assert the same capability is the authority for all three:

```text
navigation
page
API
```

No state is allowed where one layer grants and another denies for `route_admin`.

---

## T8 — RTE07 regression

Re-run the affected RTE07 Today / Live tests, including:

- desktop;
- mobile;
- authorization;
- tenant isolation;
- freshness/error behavior;
- Official Miles semantics.

The fix must not change the Today / Live visible UX.

---

# 10. Out of Scope

Do not use this correction to change:

- Today / Live layout;
- V0.7 desktop/mobile behavior;
- freshness behavior;
- Official Miles;
- Work Session;
- Trips;
- Activities;
- hierarchy/data scope;
- Supervisor permissions;
- Core/Foundation role model;
- Core `owner/admin/manager/viewer` semantics;
- Activity Explorer / RTE08;
- Reports;
- Fuel Reference;
- RTE10-A01.

---

# 11. Acceptance Criteria

This corrective delta is complete only when:

1. Root cause is demonstrated with evidence.
2. A CER Route `route_admin` has `route.live.read`.
3. Today / Live is visible in normal navigation for that Administrador.
4. Today / Live page opens successfully.
5. Today / Live API succeeds for that Administrador.
6. Existing tenants are covered by the supported permission/provisioning path.
7. No manual DB patch is required as the normal solution.
8. Supervisor remains denied.
9. Cross-tenant isolation remains intact.
10. Core roles were not repurposed.
11. RTE07 visual/functional behavior remains unchanged.
12. RTE07 affected regression is green.
13. No `PARTIAL`, `GAP`, `BLOCKED` or unresolved `DECISION REQUIRED` remains in this correction.

---

# 12. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE07_ADMIN_ACCESS_CORRECTION_REPORT_003.md`

Include:

1. Executive Result
2. Field Defect Reproduced
3. Affected User / Effective Role
4. Root Cause
5. Capability Catalog / Role Grant Analysis
6. Existing-Tenant Provisioning Analysis
7. Navigation / Page / API Alignment
8. Correction Applied
9. Supervisor Negative Validation
10. Tenant Isolation
11. Regression
12. Expected → Implemented → Evidence → Gap
13. Remaining Issues
14. Proposed Status

For the root cause use:

`observed → expected → actual cause → correction → proof`

---

# 13. Status Rule

If all criteria are green, propose:

`RTE07 ADMIN ACCESS CORRECTION COMPLETE / READY FOR CER VALIDATION`

Do not declare the overall product checkpoint closed again on Development's authority.

CER will certify the corrective delta.

If the reported account turns out to be a Core `admin`, not CER Route `route_admin`, and supporting it would require changing the approved role model:

`RTE07 ADMIN ACCESS CORRECTION BLOCKED — CER DECISION REQUIRED`

with:

`actual role → impact → options → recommendation`

---

# 14. STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE07_ADMIN_ACCESS_CORRECTION_REPORT_003.md`

**STOP.**

Do not start or modify RTE08 as part of this correction.

Do not resume RTE10-A01.

Wait for CER review.
