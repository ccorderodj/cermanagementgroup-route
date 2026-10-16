# CER Route — RTE06 Final Closure Delta
## Agent Instructions — Revision 004

**Purpose:** close the remaining Development-side gaps identified in `CER_ROUTE_RTE06_CLOSURE_REPORT_002.md` and leave RTE06 with no implementation gap before CER executes the remaining physical-device / field validation gate.

**Baseline documents**
- `CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_INSTRUCTIONS_002.md`
- `CER_ROUTE_RTE06_CLOSURE_INSTRUCTIONS_003.md`
- `Report Delivery Rodrigo/CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_REPORT_001.md`
- `Report Delivery Rodrigo/CER_ROUTE_RTE06_CLOSURE_REPORT_002.md`

This is a **small closure delta**. Do not reopen RTE06 broadly and do not start RTE07.

---

# 1. Current CER Review Result

CER accepts as closed and must not be rebuilt unless regression proves otherwise:

- RTE06-CP0 Effective Dating baseline;
- strict immutable `MissingLocationEvent`;
- notification-state separation;
- durable client-side storage of pending location evidence;
- real OSRM primary integration;
- real Valhalla fallback integration;
- primary-failure → fallback-success behavior;
- bounded routing failure behavior;
- purge-safe provenance;
- mileage immutability;
- V-4 offline soak;
- RTE03/RTE04/RTE05 regression already demonstrated.

Two Development-side issues remain:

1. **exact offline correlation is not complete for multiple lifecycle actions performed while offline**;
2. **migration safety for pre-existing `missing_location_event.notes` content is not yet acceptable**.

One documentation correction is also required:

3. final acceptance-count/status matrix must be internally consistent.

The remaining physical-device / field validation items are **CER validation responsibilities**, not an excuse to fabricate evidence and not a Development implementation gap:

- physical iPhone / Safari;
- physical Android / Chrome;
- field accuracy sampling;
- evidence-level distribution;
- final threshold calibration based on field evidence.

Development must deliver the protocol file for CER review if it has not already been delivered as an artifact.

---

# 2. Objective

Close all remaining RTE06 implementation gaps so that the final Development status can truthfully be proposed as:

`RTE06 IMPLEMENTATION COMPLETE / READY FOR CER FIELD VALIDATION`

Development must **not** claim:

`RTE06 COMPLETED / CER CERTIFIED`

while CER field validation remains outstanding.

After this delta, there must be:

- no `PARTIAL`;
- no `NOT IMPLEMENTED / GAP` inside Development scope;
- no unresolved technical ambiguity around offline event correlation;
- no unsafe migration behavior that can discard historical content;
- no inconsistent status/counting in the report.

---

# 3. Closure Item A — Exact Offline Event Correlation

## 3.1 Confirmed problem

The current closure stores location evidence durably before submission, which is correct.

However, for lifecycle actions whose authoritative subject id is created by the server, the current implementation may store evidence with a deferred subject and resolve it after reconnect.

The current implementation refuses to bind when multiple offline actions of the same kind make the mapping ambiguous.

Example:

```text
Offline:
Start Trip A → Point A
Start Trip B → Point B

Reconnect:
Two pending Start Trip points
Only server-generated Trip ids exist after replay

Current result:
mapping cannot be proven
→ neither point bound
→ both may become Missing
```

This is truthful but does **not** satisfy the RTE06 requirement that valid evidence captured for an exact lifecycle action survive offline execution and later bind to that exact action.

Treat this as:

`NOT IMPLEMENTED / GAP`

until corrected.

---

# 4. Required Correlation Result

The final design must establish a durable identity chain from the offline lifecycle action to the server-side domain event.

Conceptually:

```text
client action identity
→ durable offline operational action
→ server-created domain event
→ exact location evidence
```

CER does **not** prescribe the technical mechanism.

Possible implementation approaches may include, for example:

- client-generated durable action/event correlation id propagated to the server;
- durable idempotency/action key promoted into the domain correlation contract;
- another equivalent server-recognized client identity.

Choose the technically strongest solution that fits the current architecture.

Do **not** return several equivalent technical options for CER to choose.

Evaluate, select, implement, and document your choice unless it crosses a Product Owner boundary.

---

# 5. Mandatory Correlation Rules

The solution must guarantee:

1. exact event identity survives offline;
2. no nearest-timestamp matching;
3. no "current trip/session" guessing;
4. no ordering by upload time;
5. multiple offline actions of the same event kind remain individually distinguishable;
6. multiple Change Plans remain individually distinguishable;
7. app/browser restart preserves the identity mapping;
8. reauthentication preserves pending action/evidence correlation;
9. replay remains idempotent;
10. an accepted point cannot later be replaced by another replay;
11. evidence level and `device_captured_at` remain the originally measured values;
12. tenant isolation remains server-side;
13. no lifecycle rule of RTE03/RTE04/RTE05 is altered merely to solve correlation.

If solving this correctly requires extending an existing internal request/domain contract, do so in the smallest compatible way.

Do not introduce a second Trip state machine, second Work Session model, second audit system, or unrelated queue architecture.

---

# 6. Required Offline Scenarios

Write direct discriminating tests. Do not substitute analogous tests.

## O1 — Start Work offline
- Start Work queued offline;
- location captured at Start Work;
- reconnect;
- Work Session created;
- exact point binds to that Work Session;
- one authoritative location row.

## O2 — Start Trip offline
- Start Trip queued offline;
- departure location captured at that exact action;
- reconnect;
- Trip created;
- exact departure point binds to that Trip.

This must be a real Start Trip scenario. A Start Work test is not substitute evidence.

## O3 — Multiple offline Trip-producing actions
Within behavior permitted by the current domain lifecycle, prove that multiple offline actions that later create server-side Trip identities cannot make location identities ambiguous.

The acceptance condition is:

```text
Point A → Event A
Point B → Event B
```

with no guessing and no forced Missing caused solely by correlation ambiguity.

Do not invent an invalid lifecycle just to satisfy the test; exercise the strongest valid multi-action offline scenario the current product allows.

## O4 — Change Plan offline
- Change Plan queued offline;
- location captured for that Change Plan;
- reconnect;
- `trip_purpose_change` created;
- exact point binds to that exact purpose-change row.

## O5 — Multiple Change Plans offline
- two or more Change Plans queued;
- each has independently captured evidence;
- reconnect;
- each point binds to the correct `trip_purpose_change`;
- occurrence ordering remains domain ordering, not upload ordering.

## O6 — Restart
- pending operational action + pending evidence;
- close/reopen browser/app context;
- reconnect;
- exact binding still succeeds.

## O7 — Reauthentication
- pending action/evidence;
- auth expires;
- secure reauthentication;
- exact binding still succeeds;
- no duplicate or discard.

## O8 — Replay
- same pending action/evidence replayed;
- one domain event;
- one authoritative point.

## O9 — Delayed cached/recovered evidence
- evidence level remains unchanged after delayed synchronization;
- original capture timestamp preserved.

## O10 — Missing truthfulness
Missing may be created only when acquisition/evidence actually fails after the approved recovery path.

A valid captured point must not become Missing merely because Development cannot identify which event it belonged to.

---

# 7. Closure Item B — Migration Safety for Historical `notes`

## 7.1 Confirmed product decision

CER decision remains:

- `MissingLocationEvent` is strictly immutable;
- generic mutable `notes` do not belong on the historical fact;
- notification state remains separate.

Do not restore mutable notes.

## 7.2 Migration risk

The current migration counts existing non-empty `notes` but has no destination for their content before dropping the column.

That is not acceptable for shared/production data.

CER has not authorized:

```text
existing historical text
→ count it
→ drop it
```

even if a log records the count.

## 7.3 Required behavior

Choose and implement a migration-safe strategy that guarantees no silent historical-content loss.

Preferred principle:

> If the migration cannot preserve the meaning of existing content without inventing a new product model, it must fail safely and require explicit review rather than destroy it.

A valid solution may use:

- preflight detection + fail-fast when non-empty notes exist;
- controlled export/archive artifact before destructive schema change;
- another non-mutating historical preservation mechanism already available in the platform.

Do not invent a new editable notes feature merely to save the old field.

Do not silently transform free text into notification failure detail or another semantically different field.

Document:

- what happens when count = 0;
- what happens when count > 0;
- how the deploy operator identifies affected rows;
- how the migration avoids data loss;
- how retry/resume works after remediation.

---

# 8. Migration Tests Required

At minimum prove:

### M1
No historical notes:
- migration succeeds;
- Missing fact becomes strictly immutable;
- notification state migrates correctly.

### M2
At least one non-empty historical note:
- migration does not silently discard it;
- behavior follows the chosen safe strategy;
- no partially migrated state remains.

### M3
Unknown notification status:
- existing safe behavior remains explicit and auditable;
- no row disappears silently.

### M4
Upgrade / downgrade / upgrade:
- clean according to the supported migration contract.

### M5
Autogenerate/schema roundtrip:
- no unexplained operations.

---

# 9. Closure Item C — Documentation / Status Correction

The next report must reconcile the acceptance count from the actual matrix.

Do not write:

`23 of 28 met`

unless the row-by-row status mathematically supports that figure.

The report must separately identify:

## Development Scope
- `CONFIRMED`
- `GAP`
- `BLOCKED`
- etc.

## CER Field Validation Scope
- physical-device validation;
- field accuracy;
- evidence distribution;
- threshold finalization.

Do not call a CER field-validation item an implementation defect.

Do not call RTE06 `COMPLETED` or `CERTIFIED` while CER's required field validation remains open.

Preferred proposed status after this delta:

`IMPLEMENTATION COMPLETE / READY FOR CER FIELD VALIDATION`

If a Development gap remains, do not use that status.

---

# 10. Field Validation Protocol Artifact

The closure report references:

`_cer_delivery/CER_ROUTE_RTE06_FIELD_VALIDATION_PROTOCOLS.md`

Ensure this file is delivered with the final closure package/report so CER can review and execute it.

Do not merely reference a file that is not provided.

The protocol must cover at least:

- physical iPhone / Safari;
- physical Android / Chrome;
- permission grant/deny;
- background / foreground transitions;
- screen-lock behavior as observable;
- permission revocation;
- recovery;
- field accuracy sample;
- evidence-level distribution;
- threshold review;
- recording template;
- extraction/query steps;
- explicit rule that background geolocation capability must not be falsely claimed.

Do not change the approved event-based best-effort privacy model.

---

# 11. Preserve Closed RTE06 Behavior

Do not change unless regression forces a corrective action:

- official road-routing mileage definition;
- segmented Start Trip → Change Plan(s) → Arrived calculation;
- same-Trip Change Plan semantics;
- Missing required waypoint → `Not Calculable`;
- Haversine never official;
- breadcrumbs never official;
- odometer independent;
- mileage terminal states;
- bounded retry/sweeper;
- historical mileage immutability;
- purge-safe provenance;
- OSRM primary;
- Valhalla fallback;
- routing provenance;
- snap-radius protection;
- strict Missing fact;
- separated notification delivery state;
- tenant isolation;
- no new Route capability;
- OCR remains outside RTE06;
- RTE07 remains not started.

---

# 12. Security Requirements

Revalidate after the correlation change:

- tenant isolation;
- authenticated supervisor ownership;
- exact event/action identity;
- replay idempotency;
- no client-selected tenant;
- no arbitrary subject id injection;
- no cross-user evidence binding;
- no cross-tenant evidence binding;
- no ability to mutate an accepted location point through replay;
- no raw coordinates in ordinary logs/audit;
- no weakening of authorization.

If a client-generated key is introduced, treat it as an identifier, **not authority**.

The server must independently prove the key belongs to the authenticated tenant/supervisor and the lifecycle action being synchronized.

---

# 13. Regression Required

At minimum rerun:

- RTE06 location evidence;
- RTE06 offline durability;
- new exact-correlation scenarios O1–O10;
- mileage engine;
- real routing live integration when configured;
- routing fallback;
- offline soak;
- Missing immutability;
- migration safety tests;
- CP0 vehicle overlap/concurrency;
- RTE03 Work Session / offline queue;
- RTE04 Trip / odometer;
- RTE05 Activity / workbench;
- tenant isolation;
- platform diagnostics;
- typecheck;
- lint;
- production build;
- migration upgrade/downgrade/roundtrip.

Do not weaken, skip or xfail a failing test to achieve closure.

Environment-gated real-routing tests may remain gated in the general suite, but the prior executed live evidence remains valid unless the routing code is changed by this delta.

---

# 14. Acceptance Criteria — Development Closure

Development-side RTE06 may be proposed complete only when all are true:

1. durable location evidence remains implemented;
2. exact offline event correlation works for Start Work;
3. exact offline event correlation works for Start Trip;
4. exact offline correlation works for Change Plan;
5. multiple pending server-generated events remain individually identifiable;
6. multiple Change Plans remain individually identifiable;
7. restart preserves correlation;
8. reauthentication preserves correlation;
9. replay creates no duplicate;
10. valid captured evidence is not converted to Missing due solely to correlation ambiguity;
11. original evidence level is preserved;
12. original capture timestamp is preserved;
13. tenant isolation remains intact;
14. historical Missing facts remain strictly immutable;
15. notification state remains separate;
16. migration does not silently destroy historical notes;
17. migration behavior with existing notes is tested;
18. CP0 remains green;
19. RTE03/RTE04/RTE05 regression remains green;
20. mileage behavior remains unchanged;
21. real routing/fallback behavior remains intact;
22. V-4 remains confirmed;
23. migration checks are green;
24. typecheck/lint/build are green;
25. field validation protocol is delivered to CER;
26. no RTE07+ scope is introduced;
27. no `PARTIAL`, `NOT IMPLEMENTED / GAP`, `BLOCKED`, or unresolved `DECISION REQUIRED` remains inside Development scope.

Physical-device and field-validation items may remain explicitly:

`PENDING CER FIELD VALIDATION`

because they require CER devices / operating environment and are not Development implementation evidence.

They must not be converted to PASS.

---

# 15. Deliverable

Create a new incremental report:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_FINAL_DEVELOPMENT_CLOSURE_REPORT_003.md`

Do not overwrite previous reports.

Include only the sections needed to prove the delta:

1. Starting CER Findings
2. Exact Offline Correlation — Previous Gap
3. Correlation Architecture Selected
4. Contract/Data Changes
5. Start Work Offline Evidence
6. Start Trip Offline Evidence
7. Multiple Offline Actions Evidence
8. Change Plan Offline Evidence
9. Multiple Change Plans Evidence
10. Restart / Reauth / Replay
11. Missing Truthfulness
12. Historical Notes Migration Safety
13. Migration Evidence
14. Security / Tenant Isolation
15. Regression
16. Expected → Implemented → Evidence → Gap
17. Development Closure Inventory
18. CER Field Validation Items Remaining
19. Proposed Status

Also deliver:

`_cer_delivery/CER_ROUTE_RTE06_FIELD_VALIDATION_PROTOCOLS.md`

if CER does not already have the file as an artifact.

---

# 16. Classification Rules

Use:

- `AS-BUILT / CONFIRMED`
- `PARTIAL`
- `PENDING CER FIELD VALIDATION`
- `NOT IMPLEMENTED / GAP`
- `DEVIATION`
- `UNAUTHORIZED DECISION`
- `TECHNICAL DEBT`
- `DECISION REQUIRED`
- `BLOCKED`

Do not hide a functional gap under `TECHNICAL DEBT`.

A limitation is technical debt only if the approved product behavior remains fully satisfied.

---

# 17. Decision Authority

You may make technical choices needed to solve exact correlation and migration safety without asking CER when they do not alter:

- product behavior;
- lifecycle states;
- privacy boundary;
- tenant isolation;
- roles/permissions;
- official mileage semantics;
- meaningful external cost/contract;
- approved module boundaries.

If several compliant technical approaches exist:

`evaluate → choose → implement → document`

Do not send ordinary engineering choices back to Rodrigo.

---

# 18. STOP Conditions

STOP and return to CER before implementation only if the correct solution requires:

- changing a certified Work Session / Trip / Activity business rule;
- changing the privacy boundary;
- introducing continuous/background tracking;
- introducing a new product role/capability;
- weakening tenant isolation;
- changing official mileage semantics;
- introducing a meaningful external paid dependency;
- a new Product Owner decision not covered here.

Do not STOP for internal identifiers, schema shape, indexes, adapter structure, idempotency mechanism, or migration implementation details that satisfy the approved behavior.

---

# 19. Final STOP

After delivering:

`Report Delivery Rodrigo/CER_ROUTE_RTE06_FINAL_DEVELOPMENT_CLOSURE_REPORT_003.md`

and the field-validation protocol artifact:

**STOP.**

Do not start RTE07.

CER will review the Development closure, execute the remaining field-validation gate, and issue final RTE06 certification explicitly.
