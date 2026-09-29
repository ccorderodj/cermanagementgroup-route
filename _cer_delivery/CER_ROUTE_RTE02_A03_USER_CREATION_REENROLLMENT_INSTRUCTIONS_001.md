# CER Route — RTE02-A03
## User Creation UX + Same-Tenant Re-enrollment Closure
## Developer / Agent Instructions — 001

# 1. Context

RTE02 / RTE02-A01 / RTE02-A02 remain the certified baseline for CER Route administration.

CER has identified two operational gaps in `CER Route → Configuration → Users → Add User`:

1. The backend currently rejects passwords shorter than 10 characters, while the user experience is not aligned and reduces the response to a generic `Could not create user / Submission failed`.
2. When a username already exists, the backend returns a specific conflict such as `Username already exists. Please choose a different one.`, but the UI again presents only the same generic failure and offers no recovery path.

RTE02-A01 intentionally preserved the Core `user` identity when tenant access is deleted: the tenant membership is tombstoned while the Core identity remains. RTE02-A01 also explicitly deferred identity re-enrollment. RTE02-A03 closes that known same-tenant lifecycle gap without changing ownership of identity or weakening RTE02-A02 access controls.

This checkpoint is independent from RTE06.

# 2. Objective

Make CER Route user creation operationally complete and understandable by:

- aligning frontend password guidance/validation with the current authoritative server contract;
- surfacing actionable field and business errors;
- differentiating active, deactivated, and previously removed same-tenant users;
- allowing explicit same-tenant re-enrollment without duplicating the Core identity;
- preserving Deactivate / Reactivate semantics;
- preserving Route role restrictions, tenant isolation and audit;
- leaving RTE03+ behavior unchanged.

# 3. Confirmed CER Decisions

## D-A03-01 — Password minimum

For this checkpoint, align CER Route to the current authoritative server-side minimum of **10 characters**.

Do not reduce the backend minimum to 6.

Expected UX:

- helper/requirement indicates minimum 10 characters;
- client-side validation catches shorter values when practical;
- server remains authoritative;
- server-side password validation errors are shown at the Password field;
- a generic toast may be secondary feedback but cannot replace the actionable field error.

If repository evidence reveals multiple contradictory authoritative server policies rather than one actual Core rule, STOP and report before changing password security.

## D-A03-02 — Active same-tenant user

If the username belongs to an active membership in the same tenant:

- do not create another user;
- do not create another membership;
- show an actionable message such as `A user with this username already exists in this company.`;
- no re-enrollment action is offered.

## D-A03-03 — Deactivated same-tenant user

If the Core user and same-tenant membership exist and the membership is inactive/deactivated but not deleted:

- do not create a second identity;
- do not create a second membership;
- direct the Admin to Reactivate the existing user;
- reuse the certified Reactivate lifecycle;
- if safely reusable, the create flow may expose a contextual Reactivate action rather than forcing navigation elsewhere.

Re-enrollment is not used for ordinary deactivation.

## D-A03-04 — Previously removed same-tenant user

If:

- the Core `user` identity exists;
- a historical membership for the same tenant exists;
- that membership was removed through the certified tenant-level Delete lifecycle;

then Add User must recognize a **same-tenant re-enrollment case** instead of returning an unrecoverable generic duplicate conflict.

Expected behavior:

1. identify the historical same-tenant membership safely;
2. tell the Admin that this user previously belonged to the company;
3. require explicit confirmation to re-add;
4. reuse the existing Core identity;
5. restore/re-enroll the historical tenant membership;
6. apply one of the allowed CER Route roles selected by the Admin;
7. do not create a duplicate Core user;
8. do not create a duplicate tenant membership merely to bypass the tombstone;
9. audit the action.

Suggested user-facing concept:

`This user previously belonged to this company. Re-add user?`

Do not expose internal terms such as `user_company`, `deleted_at`, tombstone or re-enrollment state-machine terminology.

## D-A03-05 — Identity exists outside current tenant

If a username exists in the platform but there is no historical membership for the current tenant:

- do not reveal that it belongs to another company;
- do not automatically attach that identity to this tenant;
- do not implement cross-tenant person matching;
- do not implement generic email/username identity linking;
- return a safe conflict such as `This username is unavailable.`

Broader cross-tenant identity association remains out of scope.

## D-A03-06 — Route role boundary remains authoritative

CER Route Users may assign only:

- Administrador (`route_admin`)
- Supervisor (`supervisor`)

RTE02-A02 protections remain mandatory for create, edit, Reactivate, re-enrollment and direct API access.

Re-enrollment must not become a path to `owner`, `admin`, `manager`, `viewer` or platform superuser.

# 4. Current State Audit Before Coding

Inspect and report:

1. actual Core password schema(s) used by Route Add User;
2. current frontend password helper/validation;
3. create-user endpoint used by Route Users;
4. RTE02-A02 Route product-context wrapper;
5. duplicate-username lookup behavior;
6. `user` uniqueness constraints;
7. `user_company` uniqueness constraints;
8. tombstone filtering;
9. Deactivate / Reactivate flow;
10. tenant-level Delete flow;
11. exact membership state after Delete;
12. audit behavior;
13. Route role restriction behavior;
14. reusable restore primitive, if any;
15. existing frontend/API error normalization patterns;
16. credential behavior when the same Core identity is restored.

Do not assume the duplicate conflict is caused only by username until verified.

# 5. Scope

In scope:

- Add User UX;
- Add/Edit User password guidance;
- field-level validation errors;
- actionable duplicate-user handling;
- same-tenant active-user detection;
- same-tenant deactivated-user resolution;
- same-tenant deleted-membership re-enrollment;
- safe conflict for identities without current-tenant history;
- Route role application on re-enrollment;
- server authorization;
- tenant isolation;
- audit;
- browser validation;
- RTE02-A01/A02 regression.

# 6. Out of Scope

Do not implement:

- RTE06 geolocation or mileage;
- OCR;
- Work Session / Trip / Activity changes;
- new password-complexity policy beyond the current Core contract;
- passwordless auth;
- invitation flows;
- email verification;
- cross-tenant same-person matching;
- automatic linking by email;
- merging Core identities;
- global identity deduplication;
- username-policy redesign;
- deleting the global Core user;
- Route-specific duplicate identity tables;
- new Route roles;
- Core role redesign.

# 7. Existing Components to Reuse

Reuse:

- Core `Users`;
- Core `UserCompany`;
- `SecurityUsersPanel`;
- Route Users contract from RTE02-A02;
- existing Add/Edit User dialog;
- existing Deactivate / Reactivate service;
- existing tenant-level Delete behavior;
- Core audit primitives;
- Route assignable-role contract;
- existing tenant resolution;
- existing confirmation-dialog pattern;
- existing notification/toast infrastructure.

Do not create a parallel user-management domain.

# 8. Functional Requirements

## FR-01 — Password UX alignment

Password field must communicate the same minimum enforced by the server:

`Minimum 10 characters`

A value shorter than 10 produces a field-level error.

Do not show only `Submission failed` for a known password validation error.

## FR-02 — Field-aware server validation

When the server returns structured validation errors (`detail[].loc`, `detail[].msg`, `detail[].ctx`), map supported field errors to the correct form field.

At minimum cover Add User fields.

Do not expose raw JSON.

## FR-03 — Business conflict messaging

Known conflicts must be actionable rather than collapsed into a generic failure.

Cover at minimum:

- active same-tenant username;
- inactive same-tenant membership;
- removed same-tenant membership;
- unavailable username with no same-tenant history;
- disallowed Route role.

## FR-04 — Active same-tenant duplicate

No duplicate identity, no duplicate membership, no mutation. Explain that the user already exists.

## FR-05 — Deactivated same-tenant duplicate

No duplicate identity or membership. Explain that access is inactive and use the existing Reactivate lifecycle.

## FR-06 — Removed same-tenant membership

Detect historical same-tenant membership and present explicit re-add confirmation.

## FR-07 — Re-enrollment persistence

Re-enrollment must preserve the same Core identity.

Preferred outcome:

- restore the historical same-tenant membership when compatible with existing lifecycle semantics;
- do not create a second `user`;
- do not create a parallel membership merely to bypass uniqueness constraints.

If safe restoration requires destroying history or redesigning identity persistence, STOP and report options.

## FR-08 — Role selection on re-enrollment

Admin selects/confirms the Route role applied on re-enrollment.

Only Administrador or Supervisor.

Server validates independently of UI.

## FR-09 — Credentials on re-enrollment

Do not silently reset or overwrite the existing Core credential.

Audit actual current behavior first.

If the Add User dialog's password requirement conflicts with safely restoring the same identity, STOP and report the product/security decision required.

Do not invent a password-reset policy.

## FR-10 — No tenant enumeration

Do not reveal which other tenant uses a username or how many memberships an identity has.

The current tenant may be told about its own historical membership.

# 9. API / Error Contract

Frontend behavior must not depend on parsing English sentences.

Reuse or introduce a stable machine-readable contract that can distinguish:

- field validation;
- same-tenant active;
- same-tenant inactive;
- same-tenant removed / re-enrollment available;
- username unavailable without same-tenant history;
- role not allowed;
- unauthorized/forbidden.

Exact status codes and schema names are delegated.

Requirements:

- semantic states must be distinguishable;
- UI must not guess from raw text;
- tenant data must not leak;
- old clients must not gain unsafe behavior.

# 10. Re-enrollment Confirmation UX

When re-enrollment is available:

- initial Submit must not silently restore;
- show a clear confirmation;
- identify the user only with current-tenant-authorized data;
- state that the user previously belonged to the company;
- show/confirm the Route role;
- provide Cancel;
- provide explicit Re-add/Restore action.

Cancel writes nothing.

Confirm:

- restores tenant access;
- applies allowed Route role;
- writes audit;
- refreshes Users;
- resulting user is visible as active.

# 11. Business Rules

1. Core identity remains authoritative.
2. Tenant Delete removes tenant access, not platform identity.
3. Deactivate remains the normal temporary-offboarding path.
4. Reactivate handles inactive non-deleted memberships.
5. Re-enrollment handles same-tenant memberships previously removed.
6. Re-enrollment does not mean cross-tenant linking.
7. Route roles remain exactly Administrador and Supervisor.
8. Server remains authoritative for password policy.
9. Server remains authoritative for role authorization.
10. No duplicate membership is created to bypass a tombstone.
11. Historical evidence remains auditable.
12. Re-enrollment is explicit, never automatic.

# 12. Security / Audit

Authorization:

- use the existing approved Core user-management capabilities;
- Supervisor remains denied;
- direct API calls cannot assign broader roles.

Tenant isolation:

- tenant comes from authenticated context;
- never accept arbitrary company ownership from the client.

Enumeration resistance:

- identities outside the current tenant must not reveal tenant membership details.

Audit re-enrollment with:

- actor;
- tenant;
- Core user target;
- membership target;
- action;
- prior membership state;
- resulting membership state;
- resulting Route role;
- timestamp;
- request context.

Never audit plaintext password, password hash, token or secret.

# 13. Edge Cases

Validate at minimum:

1. password length 6;
2. password length 9;
3. password length 10;
4. active same-tenant username;
5. deactivated same-tenant user;
6. removed same-tenant membership;
7. removed membership with prior Supervisor designation;
8. removed membership with historical vehicle assignment;
9. username exists only outside current tenant;
10. email collision if Core has independent email uniqueness;
11. case normalization if applicable;
12. duplicate double-submit;
13. concurrent re-enrollment;
14. stale confirmation after another Admin already restored the user;
15. Route Admin attempting `owner`;
16. Route Admin attempting `admin`;
17. platform Superadmin using CER Route Users;
18. Supervisor direct API attempt;
19. malformed validation response fallback;
20. unexpected server error fallback.

Do not automatically resurrect deleted Supervisor designation or vehicle assignment unless an existing certified lifecycle rule explicitly requires it.

# 14. Acceptance Criteria

A03 may be proposed Ready for CER Certification only if:

1. UI no longer communicates a 6-character minimum;
2. 6- and 9-character passwords show actionable Password errors;
3. 10+ characters pass minimum-length validation;
4. server remains authoritative;
5. structured validation errors reach the correct field;
6. generic `Submission failed` is not the sole feedback for known errors;
7. active same-tenant duplicate is explained;
8. deactivated user is routed to Reactivate behavior;
9. removed same-tenant user can be explicitly re-enrolled;
10. Core user identity is preserved;
11. no duplicate Core user is created;
12. no duplicate same-tenant membership is created merely to bypass deletion history;
13. re-enrollment requires explicit confirmation;
14. Cancel mutates nothing;
15. re-enrollment allows only Administrador / Supervisor;
16. Core roles cannot be assigned through Route;
17. direct API bypass cannot evade the restriction;
18. external-tenant identity is not disclosed or auto-linked;
19. re-enrollment is audited;
20. password value is absent from audit/log output;
21. tenant isolation is proven;
22. historical Route data remains intact;
23. Deactivate / Reactivate behavior remains intact;
24. Delete behavior remains intact;
25. RTE02-A02 protections remain intact;
26. RTE03/RTE04/RTE05 behavior remains unchanged;
27. typecheck/lint/build are green;
28. relevant backend/browser regression is green.

# 15. Tests Required

Password / UX:

- short password frontend validation;
- short password backend validation;
- server 422 maps to Password field;
- known validation error is not generic-only;
- unexpected error has safe fallback.

Existing-user matrix:

- active same-tenant;
- inactive same-tenant;
- removed same-tenant;
- identity without current-tenant membership;
- concurrent restore;
- duplicate request consistency.

Re-enrollment:

- same Core `user.id` before/after;
- historical membership restored or handled according to approved persistence model;
- no duplicate membership;
- allowed role applied;
- forbidden Core roles rejected;
- audit present;
- password not audited;
- historical references survive.

Security:

- Supervisor denied;
- Route Admin cannot assign owner/admin/manager/viewer;
- Superadmin on Route surface still sees/assigns only Route roles;
- cross-tenant identity details not exposed;
- another tenant's membership unchanged.

Regression:

- RTE02-A01 lifecycle;
- RTE02-A02 role restrictions;
- Users create/edit/deactivate/reactivate/delete;
- Supervisor designation;
- frontend typecheck;
- frontend lint;
- production build.

For every changed pre-existing test document:

`old expectation → approved A03 decision → new expectation`

# 16. Do Not Change

Without CER approval, do not change:

- global Core identity ownership;
- RTE02-A02 role model;
- Administrador / Supervisor labels;
- capability model;
- tenant resolution;
- User Delete = tenant access removal, not global identity deletion;
- Deactivate / Reactivate semantics;
- Supervisor designation semantics;
- Vehicle Assignment history;
- Standardized Values;
- Work Session;
- Trip;
- Activity;
- Odometer;
- OCR roadmap;
- RTE06 instructions.

# 17. Checkpoints

## A03-CP1 — Diagnostic / Contract Audit

Deliver:

- password policy source;
- UI mismatch source;
- create endpoint;
- duplicate-user decision path;
- membership/tombstone behavior;
- uniqueness constraints;
- restore primitives;
- error-envelope approach;
- credential behavior for same Core identity.

STOP if safe same-tenant re-enrollment requires a new identity/security decision not covered here.

## A03-CP2 — Error UX Alignment

Implement:

- 10-character UI alignment;
- field errors;
- stable error mapping;
- actionable conflict messages;
- safe generic fallback.

## A03-CP3 — Same-Tenant Re-enrollment

Implement:

- active/inactive/removed differentiation;
- explicit confirmation;
- safe membership restoration;
- Route role application;
- authorization;
- audit;
- concurrency handling.

## A03-CP4 — Closure Validation

Run:

- existing-user matrix;
- browser journeys;
- security regression;
- tenant isolation;
- RTE02-A01/A02 regression;
- build checks.

Then STOP.

# 18. Deliverable

Create:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_A03_USER_CREATION_REENROLLMENT_REPORT_001.md`

Report sections:

1. Current State Audit
2. Password Policy Source
3. UI / Server Validation Gap
4. Error Contract
5. Existing-User Classification Logic
6. Active Same-Tenant Behavior
7. Deactivated Same-Tenant Behavior
8. Removed Same-Tenant Re-enrollment
9. Core Identity Preservation
10. Membership Persistence
11. Credential Handling
12. Route Role Enforcement
13. Cross-Tenant / Enumeration Protection
14. Audit
15. Browser Evidence
16. API Evidence
17. Concurrency / Replay
18. Regression
19. Typecheck / Lint / Build
20. Expected → Implemented → Evidence → Gap
21. Deviations / Debt / Pending Validation
22. Proposed Status

Use classifications:

- AS-BUILT / CONFIRMED
- PARTIAL
- PENDING VALIDATION
- NOT IMPLEMENTED / GAP
- DEVIATION
- UNAUTHORIZED DECISION
- TECHNICAL DEBT
- DECISION REQUIRED
- BLOCKED

# 19. STOP Conditions

STOP and return to CER if:

- Core password policy is not actually 10 and multiple authoritative policies conflict;
- re-enrollment requires merging Core identities;
- re-enrollment requires automatic cross-tenant identity linking;
- re-enrollment requires exposing another tenant;
- safe restoration requires destroying historical membership/audit evidence;
- credential handling requires inventing a password-reset rule;
- a new Route role/capability is required;
- RTE03+ domain behavior must change;
- RTE06 must be modified to complete A03.

# 20. Final STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE02_A03_USER_CREATION_REENROLLMENT_REPORT_001.md`

**STOP.**

Do not continue into unrelated scope.

CER will review and certify A03 independently from RTE06.
