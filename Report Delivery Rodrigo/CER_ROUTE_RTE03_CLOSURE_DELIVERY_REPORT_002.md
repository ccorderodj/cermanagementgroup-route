# CER Route — RTE03 Closure Delivery Report

| | |
|---|---|
| **Checkpoint** | RTE03 — Supervisor Work Session (closure) |
| **Delivery** | **002** |
| **Instruction** | `_cer_delivery/CER_ROUTE_RTE03_CLOSURE_INSTRUCTIONS_002.md` |
| **Baseline delivery** | `Report Delivery Rodrigo/CER_ROUTE_RTE03_DELIVERY_REPORT_001.md` |
| **Source branch** | `feature/rte03-closure-002` |
| **Base commit** | `e9c4d0f` (tip of `dev` — see §1, this is **not** the branch the instruction expected) |
| **Candidate commit** | `be104be` (closure implementation) — final tip including report metadata: see §12.1 |
| **Push status** | Pushed to `origin/feature/rte03-closure-002` |
| **MR status** | [merge_requests/5](https://gitlab.com/cermanagementgroup/cermanagementgroup-route/-/merge_requests/5) was opened targeting `dev` and **has since been merged** (`7290519`), before CER certification and not by this delivery — see §1 and §12.1 |
| **Date** | 2026-09-23 |
| **Proposed status** | **RTE03 closure — Completed / Ready for CER certification** |

---

## 1. Repository state — a deviation CER must know about first

The instruction states *"Applies to: `feature/rte03-work-session`"* and *"Do not merge to `dev`… until CER reviews and certifies the closure."*

**When this closure began, RTE03 had already been merged into `dev` and pushed.** Observed state:

```
e9c4d0f  Merge branch 'feature/rte03-work-session' into 'dev'   <- tip of origin/dev
632ffc2  RTE03: Work Session domain, D-09 auth continuity, D-10 time handling
75f58a6  Merge branch 'feature/rte03-work-session' into 'dev'
2983d71  RTE03: Work Session domain, D-09 auth continuity, D-10 time handling
```

Facts, stated plainly:

- The RTE03 delivery-001 work is **already on `dev` and already pushed to `origin/dev`**, by two separate merges.
- The commit hashes differ from those left by delivery 001 (`00f620c`, `941e274`), so the branch was re-created or rebased outside the development session that produced delivery 001.
- This merge was **not** performed as part of delivery 001 and not as part of this closure. Delivery 001 explicitly left the branch unmerged with no MR opened.
- No git history was rewritten by this closure.

**What this closure did about it:** nothing destructive, and nothing that compounds it. The closure work was *not* committed to `dev`. A dedicated branch `feature/rte03-closure-002` was created from the current tip and carries every change in this delivery, so CER reviews a diff that contains only the closure correction.

**What CER should decide:** whether the already-merged RTE03 state on `dev` is acceptable, or whether it must be reverted on `dev` and re-landed after certification. That is a product/governance call, not a development one, so no revert was attempted.

---

## 2. Previous behavior vs corrected behavior

| | Before (delivery 001) | After (this closure) |
|---|---|---|
| `started_at` / `ended_at` | Server clock at the moment the request was **processed** | The moment the Supervisor **performed** the action |
| Server receipt time | Not stored separately — it *was* `started_at` | Stored separately in `started_received_at` / `ended_received_at`, always from the server clock |
| `session_date` | Derived from the server receipt time + device UTC offset | Derived from the **occurrence** + device UTC offset |
| Offline Start Work before local midnight, synced after | Assigned to the **wrong** local date | Assigned to the date the Supervisor actually worked |
| Device evidence | Stored but never used for anything operational | Used for occurrence, after validation the server can perform on its own |
| Missing or contradictory device evidence | Indistinguishable from a known time | Explicitly labelled `server_receipt` in `started_at_source` / `ended_at_source` |
| End before Start | Not prevented | Rejected by the service **and** by a database CHECK |

The defect was one line in `app/routers_api/worksessions/service.py`: `session_date` was anchored to the server's own clock. Everything else in this closure exists to make the corrected anchor honest and verifiable rather than merely different.

---

## 3. Occurrence time vs server receipt — the semantics chosen

Two different facts, stored in two different places, with the provenance of the first recorded:

- **Occurrence** (`started_at`, `ended_at`) — when the Supervisor pressed the button. For an online action this equals receipt. For a queued action it can be hours earlier, and it is the only fact that describes the workday.
- **Receipt** (`started_received_at`, `ended_received_at`) — the server's own clock when it committed the action. Never influenced by any client value. This is the traceability: the gap between the two *is* the synchronization delay.
- **Provenance** (`started_at_source`, `ended_at_source` — `device` | `server_receipt`) — which clock the occurrence came from.
- **Raw evidence** (`start_device_captured_at`, `end_device_captured_at`, `*_utc_offset_minutes`) — kept verbatim **whether accepted or rejected**, so a rejection leaves a trail of what was rejected.

### How device evidence is validated

The server does not trust the device clock, and it does not need to. It validates against two things it knows with certainty (`_resolve_occurrence` in `service.py`):

1. **Causality** — an action cannot occur after it was received. Evidence ahead of the server clock by more than a 2-minute network/jitter tolerance is contradictory and rejected.
2. **Lifecycle order** — an End Work cannot occur before the Start Work of its own session. Evidence earlier than that session's `started_at` is rejected.

Plus one bounded plausibility rule: evidence older than **7 days** is rejected, because an occurrence from weeks ago does not describe the workday being synchronized. The window is deliberately generous (it covers a long weekend without coverage).

**Rejection never blocks the action.** The occurrence falls back to the receipt time, the provenance column says so, and Start/End Work still succeed — D-10's requirement that time handling never blocks the lifecycle is preserved.

**Decision for CER to confirm:** the 2-minute tolerance and the 7-day window are engineering constants, documented at their definition. They are not product rules, and neither redefines `session_date`. If CER wants different values, they are one-line changes.

### Trust boundary, stated honestly

The UTC **offset** is trusted more than the device **clock**: the offset comes from OS timezone configuration and is reliable even on a phone whose clock has drifted. The occurrence **instant** is the only possible source for a queued action, so it is accepted — but only after the two certainty checks above. This closure does **not** claim the device clock is authoritative, and does not fabricate precision the evidence cannot support.

---

## 4. Exact model / schema / API changes

### Model — `app/routers_api/worksessions/models.py`

New `BusinessEnum`:

```python
class WorkSessionTimeSource(BusinessEnum):
    DEVICE = "device"
    SERVER_RECEIPT = "server_receipt"
```

New columns on `work_session`:

| Column | Type | Null | Notes |
|---|---|---|---|
| `started_received_at` | `timestamptz` | no | server clock, `server_default now()` |
| `ended_received_at` | `timestamptz` | yes | server clock at End Work |
| `started_at_source` | `varchar(20)` | no | `server_default 'server_receipt'` |
| `ended_at_source` | `varchar(20)` | yes | |

Semantics changed (no rename): `started_at` / `ended_at` now mean **occurrence**.

New constraints:

| Constraint | Guarantee |
|---|---|
| `ck_work_session_started_at_source` | provenance is one of the two known values |
| `ck_work_session_ended_at_source` | idem (NULL allowed while ACTIVE) |
| `ck_work_session_end_after_start` | `ended_at IS NULL OR ended_at >= started_at` — no negative duration, ever, by any path |

The last one is deliberate: part of the end time now originates from a clock outside our control, so per repository invariant 6 the guarantee belongs in the database, not only in the service.

### API — `app/routers_api/worksessions/schemas.py`

`WorkSessionRead` gains four **additive** fields: `started_received_at`, `started_at_source`, `ended_received_at`, `ended_at_source`.

- No field was removed or renamed. No endpoint was added or removed. `GET /worksessions/current` keeps its `{"work_session": …}` envelope unchanged.
- Request contracts (`WorkSessionStart`, `WorkSessionEnd`) are **unchanged** — the device evidence the correction needs was already being sent by the RTE03 frontend and already being stored; it simply was not being used.
- Frontend compatibility: `workSessionSchema` (Zod) was extended with the same four fields, so the contract is validated rather than assumed. Zod strips unknown keys, so an older bundle would not have broken either.

### Frontend

- `entities/RouteWorkSessions/model/types/index.ts` — Zod schema extended.
- **No change was needed to `RouteMyRoutePage`.** It already renders `started_at` under the label *"Working since"*. Before this closure, an offline Start Work synced later displayed the **sync time** as the start of the workday — a visible falsehood to the Supervisor. The same line now displays the real time, because the field's meaning was corrected rather than a new field being added alongside it.
- Provenance is intentionally **not** shown in the mobile UI: for an online action it carries no information, and V0.7 calls for one primary action and minimal text. It is in the API and the audit trail, where reports and later checkpoints can use it.

---

## 5. Migration status and Alembic head

Migration `0003_work_session.py` was **amended** rather than followed by a `0004`.

**Why amended:** `work_session` does not exist in any certified environment, and the instruction explicitly permits *"migration amendment/new migration consistent with the current unmerged branch"*. A `0004` that renamed and re-typed columns introduced by an unmerged `0003` would permanently encode a mistake that was never shipped and would make the final schema harder to read.

**Risk, stated honestly:** anyone who had already applied the previous `0003` to a local database must `downgrade` and re-`upgrade`. No deployed environment is affected.

Verification performed:

| Command | Result |
|---|---|
| `alembic downgrade 0002_route_foundation` | OK |
| `alembic upgrade head` | OK |
| `alembic check` | `No new upgrade operations detected.` — no drift between models and migration |
| `alembic heads` | `0003_work_session (head)` — exactly one head |

The integration suite rebuilds the schema with `alembic upgrade head` from a dropped schema on every run, so the amended migration is exercised by every test in this delivery.

---

## 6. Offline-across-midnight evidence

`tests/integration/test_work_sessions.py::test_offline_start_queued_before_midnight_keeps_the_previous_day`

- Occurrence: Friday 2026-09-25 23:50 local (EDT, offset −240) = `2026-09-26T03:50Z`.
- Server receipt (sync): `2026-09-26T12:00Z` (Saturday 08:00 local), with the server clock frozen there.
- Asserted: `session_date == 2026-09-25`; `started_at == 03:50Z`; `started_received_at == 12:00Z`; `started_at < started_received_at`; `started_at_source == "device"`.

**Proven discriminating, not assumed.** The occurrence anchor was temporarily reverted to the receipt clock and the test was re-run:

```
FAILED tests/integration/test_work_sessions.py::test_offline_start_queued_before_midnight_keeps_the_previous_day
```

The anchor was then restored and the absence of the temporary marker verified by grep before proceeding.

Also covered: `test_cross_midnight_session_with_device_evidence_stays_on_start_date` — start Friday 20:00 local, end Saturday 01:00 local, one session, `session_date` unchanged.

---

## 7. Delayed End Work evidence

`tests/integration/test_work_sessions.py::test_offline_end_keeps_its_occurrence_not_the_sync_time`

- Start Work at `2026-09-25T14:00Z`.
- End Work performed at 17:00 local = `2026-09-25T21:00Z`; synchronized at `2026-09-26T02:00Z`.
- Asserted: `ended_at == 21:00Z` (the operational end), `ended_received_at == 02:00Z` (traceable), `ended_at_source == "device"`.

---

## 8. Replay / idempotency evidence

| Test | Proves |
|---|---|
| `test_replaying_a_queued_action_does_not_move_the_occurrence` | Same `Idempotency-Key` replayed 6 h later returns the same session with **identical** `started_at` and `started_received_at` |
| `test_replaying_the_same_idempotency_key_changes_state_once` (001) | One state transition per key |
| `test_end_work_replayed_twice_is_safe` (001) | Replayed End Work is a no-op |
| `test_out_of_order_end_before_start_does_not_corrupt_state` (001) | Contradictory ordering does not corrupt the state machine |

No second Work Session is created by any replay path, and no replay rewrites an established occurrence time (closure Functional Rule 5).

---

## 9. Clock-skew and suspicious-evidence evidence

| Test | Scenario | Result |
|---|---|---|
| `test_skewed_device_clock_does_not_affect_authoritative_ordering` | Device claims to be 3 days in the future | Evidence rejected; occurrence = receipt; `started_at_source == "server_receipt"`; raw claim preserved |
| `test_stale_device_evidence_beyond_the_window_is_rejected` | Device claims 24 days ago | Rejected, labelled, **Start Work still succeeds (200)** |
| `test_end_evidence_before_start_is_rejected_as_impossible` | End Work claims 2 h before its own start | Rejected, labelled, `ended_at >= started_at` holds |
| `test_the_database_rejects_an_end_before_its_start` | Direct SQL `UPDATE`, bypassing the service entirely | Rejected by `ck_work_session_end_after_start` |
| `test_without_device_evidence_the_receipt_time_is_labelled_as_such` | No evidence sent | Receipt used, labelled `server_receipt` — never presented as a known time |
| `test_online_start_and_end_behave_as_before` | Online control case | Occurrence == receipt, `session_date` correct, behavior unchanged |

Closure Functional Rule 9 is satisfied by construction: there is no code path where a receipt time is silently relabelled as an occurrence time.

---

## 10. Browser-level offline validation (§B)

`tests/e2e/test_work_session_offline_browser.py::test_queued_start_work_survives_reload_and_reauthentication` — **passing**.

Setup: a real `uvicorn` process against the same seeded test database, driven through **the Microsoft Edge already installed on the machine** (`channel="msedge"`, no browser download), at a 390×844 mobile viewport.

Demonstrated, in one continuous browser session:

| §B requirement | How it was proven |
|---|---|
| Action queued while offline | `/api/worksessions**` requests aborted; **Start Work** clicked; IndexedDB read back from the page shows exactly 1 row with `kind: "worksession.start"`; **0 rows in PostgreSQL** |
| IndexedDB persistence survives app reopen | Page reloaded (fresh JS context) while the API is still unreachable; the queue still holds the **same action id**, and the UI re-derives *"Starting your day…"* from IndexedDB alone |
| Reauthentication does not discard the pending action | All cookies cleared (what an expiry leaves behind), page reloaded; the action is still queued with the same id |
| Reconnect flushes in order | Interception removed, valid re-login, page reloaded |
| Server reconciliation returns the authoritative session | UI reaches *"Working since"*, driven by `GET /worksessions/current` |
| No duplicate Work Session | `SELECT count(*)` in PostgreSQL == **1** |

**Why one test and not two:** `seeded` re-seeds between tests while the adjacent `uvicorn` caches tenant resolution for 60 s, so a second test authenticates against the previous company. A single continuous run avoids that harness artifact and matches the real field sequence. This is documented in the test itself.

**New dev dependency:** `playwright` in the `dev` group (`pyproject.toml`). No browser binaries are downloaded; the system Edge is used. The test `importorskip`s the package and **skips with an explicit reason** where Edge is unavailable (e.g. a Linux CI), so it never fails for a reason unrelated to the product. A new `browser` pytest marker is registered.

**Interception vs true offline:** `context.route(...).abort()` was used instead of `context.set_offline(True)` because Playwright's offline mode also blocks the document request, making it impossible to reload the page — which is precisely the durability property under test. The API request fails identically either way.

---

## 11. Real-device items still PENDING VALIDATION

| Item | Status |
|---|---|
| V-1 / V-4 on real iOS hardware | **PENDING VALIDATION** — no device available |
| V-1 / V-4 on real Android hardware | **PENDING VALIDATION** — no device available |
| Background/suspended-tab eviction on mobile OSes | **PENDING VALIDATION** |
| Desktop Chromium (Edge) queue durability, reload, reconnect, reauth | **Validated** — §10 |

Desktop Edge is not a substitute for mobile hardware and is not reported as one. Delivery 001's honest classification of real-device behavior stands; this closure narrows what is unvalidated, it does not clear it.

### Durability boundaries (unchanged, restated)

IndexedDB does **not** protect against the user clearing site data, browser storage eviction, uninstall, or device loss/destruction. An accepted action is durable across app close, reload, reconnect and reauthentication — nothing more is claimed.

---

## 12. Regression results

| Scope | Command | Result |
|---|---|---|
| Work Session integration tests | `uv run pytest tests/integration/test_work_sessions.py` | **42 passed** |
| Auth continuity tests (D-09) | `uv run pytest tests/integration/test_auth_continuity.py` | **4 passed** |
| Time / occurrence subset | `uv run pytest tests/integration/test_work_sessions.py -k "offline or occurrence or …"` | **15 passed** |
| Authorization / permission matrix | `uv run pytest tests/integration/test_authorization_matrix.py` | **50 passed** |
| Architecture nets (permission catalog, public surface, page wiring, navigation wiring) | `uv run pytest tests/test_permission_catalog.py tests/test_public_surface.py tests/test_page_wiring.py tests/test_navigation_wiring.py` | **60 passed** |
| Browser validation | `uv run pytest tests/e2e/test_work_session_offline_browser.py` | **1 passed** |
| Full backend suite | `uv run pytest` | **399 passed**, 0 failed, 0 skipped, **exit code 0** (389 at delivery 001; +9 in `test_work_sessions.py`, +1 browser test) |
| Frontend typecheck | `npm run typecheck` | clean, 0 errors |
| Frontend lint | `npm run lint:ts` | clean |
| Production build | `npm run build:prod` | compiled; 2 pre-existing warnings (Sass legacy JS API deprecation, bundle size), no errors |
| Migration roundtrip | `alembic downgrade 0002_route_foundation && alembic upgrade head` | OK |
| Schema drift | `alembic check` | `No new upgrade operations detected.` |
| Alembic heads | `alembic heads` | one head |
| App import | `python -c "import app.main"` | OK |

### Tests added by this closure

| File | Before | After | Added |
|---|---|---|---|
| `tests/integration/test_work_sessions.py` | 33 | **42** | 9 |
| `tests/integration/test_auth_continuity.py` | 4 | 4 | 0 |
| `tests/e2e/test_work_session_offline_browser.py` | — | **1** | 1 |

Bootstrap / role-capability behavior was **not** touched by this closure: no capability, role template or seed was changed. The architecture-net row above confirms it — `test_permission_catalog.py` fails by design if the catalog and the `require_permissions` calls diverge.

### 12.1 Commits on the closure branch

| Commit | Contents |
|---|---|
| `be104be` | The closure itself: model, service, schemas, migration amendment, 9 integration tests, browser test, this report |
| `07b400a` | Report metadata only — candidate commit, push status and MR number, which could not exist before the commit did |
| `d31db93` | This section: itemized auth-continuity, authorization and architecture-net regression rows requested by instruction item 10, on `feature/rte03-closure-002-report` |

The reviewable diff for the closure itself is `e9c4d0f..07b400a` on `feature/rte03-closure-002`.

**Both branches were merged into `dev` before CER certification, outside this delivery** — see §1 and §16, item 1. The instruction's *"do not merge before certification"* was therefore not honoured by the repository, though it was honoured by this delivery: nothing here merged anything.

---

## 13. Expected → Implemented → Evidence

| Closure requirement | Implemented | Evidence |
|---|---|---|
| Sync delay never represented as occurrence time | Occurrence and receipt stored separately | §6, §7 |
| Offline Start across local midnight keeps `session_date` | Anchor moved to occurrence | `test_offline_start_queued_before_midnight_keeps_the_previous_day` (proven to fail pre-fix) |
| Offline End preserves occurrence independently | `ended_at` vs `ended_received_at` | `test_offline_end_keeps_its_occurrence_not_the_sync_time` |
| Occurrence and receipt distinguishable | 4 new columns + provenance enum | §4 |
| Replays do not modify occurrence | Return-existing semantics unchanged | `test_replaying_a_queued_action_does_not_move_the_occurrence` |
| One ACTIVE session still DB-enforced | `uq_work_session_one_active` untouched | `test_the_database_rejects_a_second_active_session_directly`, `test_concurrent_start_work_creates_only_one_active_session` |
| Auth continuity preserves queued actions | IndexedDB independent of session cookie | §10, `test_valid_reauthentication_resumes_the_same_session` |
| Multi-device resolves one session | `GET current` unchanged | `test_a_second_device_resolves_the_same_session` |
| Tenant isolation and authorization intact | No change to identity, capability or scoping | `test_cross_tenant_session_id_returns_not_found`, `test_a_supervisor_cannot_end_another_supervisors_session`, full suite |
| Audit intact | Start/End events now also record both times and the provenance | `test_start_and_end_are_audited` |
| Browser-level evidence, or explicit PENDING | Desktop Edge validated; real devices pending | §10, §11 |
| Full regression green | — | §12 |
| Report no longer claims unvalidated device behavior | §11 states it explicitly | §11 |
| No RTE04 / RTE02-A01 / odometer / OCR / routing mileage | Nothing started | §14 |
| Compatible with later Trip and odometer extensions | Occurrence carries the operational name; blockers still addable in `end()` | §15 |

---

## 14. Confirmation — scope not started

No code, table, schema, route, capability, menu entry or test was created for any of the following:

Trip, Trip Purpose, Start Trip, On Route, Arrived, Change Plan, Return Home Trip, Activity Block, Activity selections, Outcomes/Notes, geolocation, GPS permission, Recovery Window, Missing Location Event, routing provider, routing mileage, breadcrumbs, fuel reference, fuel estimate, odometer, camera capture, OCR, odometer exception workflow, RTE02-A01 Delete/Deactivate UX, Standardized List seed changes, Today/Live, Activity Explorer, Reports/export, Admin post-close corrections, notifications, maps, Supervisor Desktop, CER ERP integration.

The Work Session lifecycle remains `ACTIVE → ENDED`. `route.worksession.execute` and the Supervisor-only default grant are unchanged. The certified Routing Mileage definition was not touched and was not redefined using odometer data.

---

## 15. Extension points preserved

- `WorkSessionService.end()` still resolves the session, then transitions it. RTE04/RTE05 blockers (Trip `IN_TRANSIT` review, Continue Working, explicit End Work Anyway, Activity `IN_PROGRESS` rejection) insert between those two steps without restructuring.
- Occurrence time carries the operational name (`started_at`), so Trip ordering and later odometer/mileage math read the right field by default instead of having to remember to avoid a misnamed one.
- `GET /worksessions/current` still returns only `work_session`; `current_trip` / `current_activity` can be added to the same envelope.
- Work Session events can receive location evidence later without redesign: nothing about the time model assumes the absence of a location row.

---

## 16. Deviations and risks

| # | Item | Assessment |
|---|---|---|
| 1 | **RTE03 was already merged to `dev` and pushed before this closure started**, by two merges, with hashes that do not match delivery 001. **The closure branch was then also merged to `dev` (`7290519`) before certification**, while this report was being finalized | None of these merges was performed by delivery 001 or by this closure — both left their branch unmerged with an open MR. Requires a CER governance decision (§1): accept the merged state, or revert on `dev` and re-land after certification. No revert attempted |
| 2 | Migration `0003` amended instead of a new `0004` | Explicitly permitted by the instruction. Local databases on the previous `0003` need a downgrade/upgrade. No deployed environment affected |
| 3 | `started_at` / `ended_at` changed meaning without changing name | Deliberate (§4). The alternative left the obvious field carrying the wrong semantics — a latent defect for RTE04. No certified consumer existed |
| 4 | New dev dependency `playwright` | Dev-group only, no browser download, test skips where Edge is absent. Added to satisfy §B |
| 5 | 2-minute future tolerance and 7-day staleness window | Engineering constants, documented at definition, one-line changes if CER prefers other values. Neither redefines `session_date` |
| 6 | Real-device V-1/V-4 still unvalidated | Stated as PENDING VALIDATION (§11). Not a claim of completion |
| 7 | Browser validation covers desktop Edge only, and is one test | Honest scope; documented in §10 and in the test |

No STOP condition from the instruction was triggered: `session_date`'s meaning was not redefined, more than one active session was never allowed, Routing Mileage authority was untouched, no timezone catalog or configuration was introduced, tenant identity and authorization boundaries were unchanged, and no Trip/Activity/RTE04 or RTE02-A01 scope was started.

---

## 17. Proposed status

**RTE03 closure — Completed / Ready for CER certification.**

The correctness gap is closed and proven with a test that demonstrably fails against the previous behavior. Browser-level offline evidence now exists; real-device validation remains explicitly pending.

Two things need a CER decision: the already-merged state of both RTE03 and this closure on `dev` (§1, §16 item 1), and confirmation of the two time-tolerance constants (§3).

Work stops here. RTE04 has not been started.
