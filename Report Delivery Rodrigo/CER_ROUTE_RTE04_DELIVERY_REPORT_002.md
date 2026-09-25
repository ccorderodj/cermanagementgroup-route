# CER Route — RTE04 Delivery Report

| | |
|---|---|
| **Checkpoint** | RTE04 — Trip Foundation + Odometer Evidence |
| **Delivery** | **002 — final, evidence-first** |
| **Instructions** | `CER_ROUTE_RTE04_DEVELOPMENT_INSTRUCTIONS_001.md`, `..._CER_DECISIONS_AND_CONTINUATION_002.md`, `..._C1_CLOSURE_AND_CONTINUATION_003.md` |
| **Source branch** | `feature/rte04-c1-closure-c2` |
| **Base commit** | `3211c6a` (tip of `dev`) |
| **Date** | 2026-09-25 |
| **Proposed status** | **RTE04 — Completed / Ready for CER Certification** |
| **RTE05** | **Not started.** No Activity execution, no Outcome, no Notes, no GPS, no Routing Mileage, no fuel, no reports. |

---

## 0. Read this first

Three things in this delivery need a decision or an action from someone other than Development. They are here, at the top, rather than buried in §9.

**1. A product defect that made three approved Trip contexts unusable — found, fixed, and worth knowing about.**
`GET /api/standard-values/{list_code}` required `route.standardvalues.manage`. Supervisors do not have that capability, so the mobile trip form received 403 when loading its options. Because C1 made the standardized value **required before Start Trip** for Employee Visit, Check Delivery and Office, those three contexts were impossible to start from the phone: the form demanded a value it could not offer.

The API tests never saw it, because they post `standard_value_id` directly. Only driving a real browser surfaced it. It is fixed by allowing the read under **either** `route.standardvalues.manage` **or** `route.worksession.execute`, and not by granting Supervisors `manage` — that would let a field user create and delete the tenant's lists. No new capability, so **no re-bootstrap is required**.

**2. One derived rule that CER did not state explicitly, and that we implemented rather than stopping on.**
Option B lets the workday close with the END exception still unreviewed. Without an additional rule, a Supervisor could request the exception, end the day, then upload any photograph and self-confirm it as `PHOTO_CONFIRMED` — the Admin approval would be decorative and the manual path avoidable. So **a closed workday no longer accepts a new END photo**; the ending reading completes only through the approved manual entry, which is the path Option B itself names. We judged this a consequence of Option B rather than a new product decision, because it changes nothing for the Supervisor who genuinely has no photo. **If CER reads it differently, say so and we will change it** — it is one guard in one method.

**3. A final pass against the instruction found three more gaps — two of them defects that would have reached certification.**
After the first draft of this report was written, we re-read instruction 003 clause by clause instead of trusting our own summary. Three things did not hold:

- **§4 required queued actions to preserve occurrence time.** The backend accepted `device_captured_at` for every Trip action; **the client never sent it.** A trip started at 08:05 and synced at 10:00 would have been recorded at 10:00 — precisely the failure RTE03's occurrence/receipt semantics exist to prevent. The three queued Trip actions now send it, using one shared helper rather than a second copy of the Work Session's.
- **§10 required concurrent/idempotent evidence.** The odometer had none. Writing it found two real defects, below.
- **`ensure_row` returned HTTP 500 under concurrent reads.** It caught `IntegrityError` *inside* `async with transaction()`, so the context manager then committed a session whose transaction had already rolled back → `PendingRollbackError`. Two tabs or two devices reading the odometer state at the same time — ordinary, not rare — produced a 500.
- **`decide_exception` let two Admins both succeed.** The status guard read outside the transaction, so both wrote: each got HTTP 200, the audit trail kept an approval *and* a rejection of the same request, and the final state was whoever committed last. The decision is now a conditional `UPDATE ... WHERE status = 'requested'`; the loser gets 409.

All four are fixed and covered by tests. They are listed here rather than in §7 because two of them were defects in behavior CER is being asked to certify.

**4. `data-testid` does not exist in production builds.**
`configwebpack/build/loaders/buildBabelLoader.ts` strips it when `isProd`. This is pre-existing and deliberate, and no browser test in the repository relied on it — but it means any future browser validation must anchor on text, role or form `id`. Ours do. Noted so the next checkpoint does not lose half a day to it.

---

## 1. Implementation status C1–C5

| Phase | Scope | Status |
|---|---|---|
| **C1** | Trip foundation + closure (current Trip in the state envelope, required pre-trip fields) | `COMPLETED / VALIDATED` |
| **C2** | Mobile Trip lifecycle | `COMPLETED / VALIDATED` |
| **C3** | START odometer evidence + capture UX + Admin exception queue | `COMPLETED / VALIDATED` |
| **C4** | END odometer + End Work, CER Option B | `COMPLETED / VALIDATED` |
| **C5** | Validation | `COMPLETED` — see §7 |

Commits on the branch:

```
bcce308  RTE04-C1 closure: current trip in the state envelope, required pre-trip fields
4fa1fae  RTE04-C2: mobile trip lifecycle and End Work review
66c94bc  RTE04-C3: START odometer evidence, server-side guard
4c1a731  RTE04-C3/C4: odometer capture UX, Admin review queue, END odometer
```

---

## 2. Expected → Implemented → Evidence → Gap

### 2.1 C1 closure

| Expected | Implemented | Evidence | Gap |
|---|---|---|---|
| `GET /worksessions/current` returns the authoritative current Trip | `current_trip` added to the existing envelope; no parallel recovery endpoint | `test_trips.py`, browser flows 5 and 6 | none |
| No current Trip returns `null`, not a placeholder | `Optional[TripRead] = None` | `test_trips.py` | none |
| CLOSED / INTERRUPTED not returned as current | `TERMINAL_STATUSES` excludes them; `ARRIVED` deliberately stays current | `test_trips.py` | none |
| Second device resolves the same Trip | Server-side resolution; screen holds no authority | browser flow 6 — trip count unchanged in PostgreSQL | none |
| Employee Visit / Check Delivery / Office cannot Start Trip without their value | `_exigir_dato_de_planificacion` in `trips/service.py` | `test_trips.py` (9 discriminating tests) | none |
| Wrong-list value rejected; other tenant's value rejected; tombstoned value not selectable | `StandardValuesDAO.find_selectable` | `test_trips.py` | none |
| Post-arrival fields absent from the pre-trip contract | Not present in any RTE04 schema | `test_trips.py` | none |

The envelope stays extensible: RTE05 adds `current_activity` to the same response. There is no second Supervisor recovery model.

### 2.2 C2 — Mobile Trip lifecycle

| Expected | Implemented | Evidence | Gap |
|---|---|---|---|
| Mobile-only, one primary action at a time, no Admin chrome | `RouteMyRoutePage` + `RouteMobileShell`, validated at 390×844 | browser flows 1–6 | none |
| No state-machine vocabulary | Screen reads "On route", "Heading to", "Arrived" | browser flows | none |
| Seven V0.7 contexts preserved | `TRIP_CONTEXTS` | `test_navigation_wiring`, browser flow 1 | none |
| Free-text fields stay free text | No catalog created for any of them | `TRIP_CONTEXTS` has `freeTextLabel` only | none |
| Change Plan only while IN_TRANSIT, original preserved, append-only | `change_plan` appends to `trip_purpose_change`; never touches `original_*` | browser flow 2 — trip count unchanged, 1 change row | none |
| HOME closes on Arrived Home, session stays ACTIVE | `arrive()` → `CLOSED` for HOME | browser flow 4 | none |
| Reuse the RTE03 durable queue; no second queue | Same `shared/lib/offlineQueue` | `test_work_session_offline_browser.py` | see §5 |
| Arrived operational Trip awaits RTE05 without fabrication | `NotBuiltYet feature="Activities" checkpoint="RTE05"` | browser flow 3 | none |

### 2.3 C3 — START odometer evidence

| Expected | Implemented | Evidence | Gap |
|---|---|---|---|
| `Start Work ≠ Start Driving`; notice, not a forced popup | `OdometerPendingBanner`; "Where to next?" stays enabled | browser flow 1 asserts the button is enabled with the notice shown | none |
| Contextual capture on first travel context; Trip context preserved underneath; return to the same Trip | Capture renders under the `Destino` card in the `planning` phase | browser flow 1 | none |
| Hard server-side guard on Start Trip | `ensure_start_reading_resolved` | `test_odometer.py` | none |
| Photo + confirmed reading is primary; OCR assistive; OCR silence is normal | `NoSuggestionReader` default; suggestion stored separately | `test_odometer.py` | OCR quality, §8 |
| `PHOTO_CONFIRMED` for the normal path, even with no OCR | Status derives from photo presence, not from OCR | `test_odometer.py`, browser flow 7 | none |
| No "Enter manually" shortcut | Only "I can't take a photo" → reason → wait | browser flow 8 | none |
| Approval one-time and scoped to tenant / Supervisor / session / vehicle / START / request | Scope enforced by columns; `CONSUMED` on use | `test_odometer.py` | none |
| `MANUAL_EXCEPTION_CONFIRMED` permanently distinguishable | `evidence_method = manual_no_photo` | `test_odometer.py`, browser flow 9 | none |
| Admin queue surfaces the request | `RouteOdometerExceptionsPage` under `route.records.adjust` | browser flow 9 | none |

### 2.4 C4 — END odometer + End Work

| Expected | Implemented | Evidence | Gap |
|---|---|---|---|
| Asked at End Work, not at Arrived Home | `ensure_end_work_not_blocked` runs in `End Work` only | `test_odometer_end_work.py`, browser flow 4 (Arrived Home asks nothing) | none |
| Trip blockers resolved first | Trip check precedes the odometer check in `end()` | `test_odometer_end_work.py::test_the_trip_blocker_is_resolved_before_the_end_reading` | none |
| `End Reading >= Start Reading` | `_validar_contra_inicio` → 422 | `test_odometer.py` | none |
| `Odometer Distance = End − Start`, separate from Routing Mileage | `_distance`; named `odometer_distance` everywhere | `test_odometer.py`, browser flow 12 | none |
| **Option B**: session may end with END pending | `END_WORK_UNBLOCKING_STATUSES` includes `exception_requested` / `exception_approved` | `test_odometer_end_work.py` | none |
| `ended_at` remains the real occurrence | Read before and after late completion; identical | `test_completing_the_end_reading_later_never_moves_ended_at` | none |
| Session not reopened later | Status still `ended` after completion | same test + browser flow 12 | none |
| Late completion creates no Trip | Trip count unchanged | `test_completing_the_end_reading_later_creates_no_trip` | none |
| Distance pending until END completed | `None`, never `0` | `test_odometer.py`, `test_odometer_end_work.py` | none |
| Audit captures requester, approver, reason, timestamps | `audit_event` rows; requester ≠ approver asserted | `test_the_late_end_reading_is_fully_audited` | none |

### 2.5 D-07 — End Work / Trip interaction

| Expected | Implemented | Evidence |
|---|---|---|
| IN_TRANSIT → End Work is a review, with Continue Working and explicit End Work Anyway | 409 without `end_anyway`; screen opens the review | browser flow 10 |
| Continue Working restores the Trip, creates nothing, changes no history | Queue discards the rejected action; state re-read from the server | §5 |
| End Work Anyway → `INTERRUPTED`, no fake arrival | `TripService.interrupt` | browser flow 10 asserts `interrupted` |
| ARRIVED operational Trip: no fabricated Activity completion | Does not block and does not close | browser flow 3 |

---

## 3. Data / API / UI impact

### Data — migration `0006_odometer_evidence`

Two tables, both tenant-scoped, both with composite foreign keys so a cross-tenant reference is structurally impossible.

`odometer_evidence` — one row per (session, end). Storage key, content hash, content type and byte size live inline; `ocr_detected_reading` is a separate column from `confirmed_reading`, so what the machine saw and what the person confirmed are never conflated.

`odometer_exception_request` — partial unique index `uq_odometer_exception_open` on `(company_id, work_session_id, evidence_type) WHERE status IN ('requested','approved')`: requesting twice cannot open two doors.

**Why the file metadata lives on the evidence row.** The repository has storage primitives — provider, media validation, scanner — but no file registry and no domain consuming one; RTE04 is the first. Creating a generic platform-wide file registry for a single consumer is what §8 of the instruction and the repository's own rules forbid. CER accepted this in delivery 001.

Migration state: `alembic heads` → `0006_odometer_evidence` (single head). `alembic check` → *No new upgrade operations detected*. Upgrade, downgrade and round-trip verified.

### API

New, all under `/api` (internal; **nothing added to `/api/v1`, nothing public**):

| Method | Path | Capability |
|---|---|---|
| `GET` | `/odometer/sessions/{id}` | `route.worksession.execute` |
| `POST` | `/odometer/sessions/{id}/{start\|end}/photo` | `route.worksession.execute` |
| `POST` | `/odometer/sessions/{id}/{start\|end}/confirm` | `route.worksession.execute` |
| `POST` | `/odometer/sessions/{id}/{start\|end}/exception` | `route.worksession.execute` |
| `GET` | `/odometer/evidence/{id}/photo` | `route.worksession.execute` + ownership |
| `GET` | `/odometer/exceptions/pending` | `route.records.adjust` |
| `POST` | `/odometer/exceptions/{id}/approve` | `route.records.adjust` |
| `POST` | `/odometer/exceptions/{id}/reject` | `route.records.adjust` |

Changed: `GET /worksessions/current` gained `current_trip`; `POST /worksessions/{id}/end` gained `end_anyway` and the END odometer guard; `GET /standard-values/{list_code}` now readable by Supervisors (§0.1).

`tests/test_public_surface.py` unchanged — **no endpoint was added to the unauthenticated surface.**

### UI

New: `entities/RouteOdometer`, `features/RouteOdometer` (capture, notice, Admin panel), `pages/RouteOdometerExceptionsPage`. Changed: `RouteMyRoutePage` (full lifecycle + odometer), navigation, `maincontent`, `mainContentConfig`.

The Admin page followed the eight-step page-add procedure. `tests/test_page_wiring.py` caught the missing template anchor on the first run and was updated — the net did its job.

---

## 4. State transitions

```
Trip:     PLANNING ──▶ IN_TRANSIT ──▶ ARRIVED        (operational: awaits RTE05)
                            │    └──▶ CLOSED         (HOME only)
                            └───────▶ INTERRUPTED    (End Work Anyway)

Odometer: PENDING ──photo + confirm──────────────────▶ PHOTO_CONFIRMED
             │
             ├──no photo possible──▶ EXCEPTION_REQUESTED ──approve──▶ EXCEPTION_APPROVED
             │                              │                              │
             │                              └──reject──▶ back to PENDING    │
             │                                                              ▼
             │                                          MANUAL_EXCEPTION_CONFIRMED
             └──no applicable vehicle──▶ NOT_REQUIRED
```

Two guards, different on purpose:

- **Start Trip** requires `PHOTO_CONFIRMED`, `MANUAL_EXCEPTION_CONFIRMED` or `NOT_REQUIRED`. An *approved* exception is not yet a reading: it authorizes typing, not departing.
- **End Work** additionally accepts `EXCEPTION_REQUESTED` and `EXCEPTION_APPROVED` (Option B). Whoever is finishing will not drive again, and holding the workday open until someone reviews the request would write an `ended_at` that never happened.

`NOT_REQUIRED` is a truthful answer, not a zero. `odometer_distance` is `null` until both readings exist — also not a zero.

---

## 5. The durable queue: a defect found and fixed

The queue kept actions the server had rejected on their merits. It stops at the first failure to preserve order, so a permanently rejected action **blocked everything behind it** — the next workday would never open. And the D-07 review was unreachable from the screen at all: `End Work`'s 409 was being swallowed by the flush, so the dialog CER approved never appeared in the mobile flow.

Worse than either: an `End Work` the Supervisor abandoned by choosing "keep working" would have resent itself on the next reconnect and closed their day unasked.

A 4xx (except 408 and 429) now leaves the queue and is handed back to the caller. Network failures and 5xx still wait and retry. The screen then **re-reads authoritative state** to decide what the 409 meant — Trip still in transit opens the review; END reading pending opens the capture — rather than matching strings in an error message.

This is queue *retry policy*, not RTE03 lifecycle or time semantics, so §12 is not touched. Occurrence/receipt semantics are untouched.

---

## 6. Permissions, security, audit

- **`route.records.adjust`** activated now that endpoints enforce it; granted to `route_admin`, **not** to `supervisor`. A Supervisor cannot approve their own exception: `test_a_supervisor_cannot_approve_their_own_exception`, plus browser flow 13.
- **Photos have no public or permanent URL.** Every download re-checks tenant and ownership by joining `work_session`. Another Supervisor in the same tenant gets **404, not 403** — existence is not confirmed.
- **Storage keys are server-generated**, never derived from the uploaded filename. Content type is resolved from the bytes, not the declared header; size capped at 12 MB; the existing scanner boundary is reused.
- **The audit trail never stores photo bytes or the storage key**: `test_the_audit_never_stores_photo_bytes`.
- **Cross-tenant isolation**: another tenant's admin decides nothing — 404.
- `Users.is_superuser` appears in no RTE04 input schema.
- No request body carries who acts, in which company, or when: identity from the session, tenant from the subdomain, time from the database clock with device evidence validated against causality.

---

## 7. Tests and regression

### Backend, by batch

| Batch | Tests | Exit | Duration |
|---|---|---|---|
| Unit + architecture nets | 99 | `0` | 15s |
| Auth / CSRF / authorization matrix | 83 | `0` | 136s |
| Platform + integration primitives + maker-checker | 49 | `0` | 128s |
| Route configuration + admin lifecycle | 140 | `0` | 587s |
| Data: constraints, pagination, tenant isolation | 47 | `0` | 117s |
| Work Sessions + Trips | 102 | `0` | 496s |
| Odometer (START + END) | 43 | `0` | 431s |
| **Total** | **565** | **0 failures** | |

Plus the three authorization tests added for §0.1 and the six added during the final review of §4 and §10 (see §0.4): `9/9 PASS`.

### Frontend

| Check | Result |
|---|---|
| `npm run typecheck` (`tsc --noEmit`) | **0 errors** |
| `npm run lint:ts` (eslint) | **0 errors** |
| `npm run build:prod` | **exit 0** (2 pre-existing bundle-size warnings) |

### Browser, all 13 required flows

Real Microsoft Edge, 390×844 viewport, against a real `uvicorn` and the production bundle. State asserted in PostgreSQL, not on screen.

| # | Flow | Journey | Result |
|---|---|---|---|
| 1 | Start Work → Trip → pre-trip field → START odometer → Start Trip | A | PASS |
| 2 | On Route → Change Plan → same Trip continues | A | PASS |
| 3 | Operational Arrived stays ARRIVED, no fabrication | A | PASS |
| 4 | HOME → Arrived Home → Trip CLOSED, session ACTIVE | B | PASS |
| 5 | Reload resumes the current Trip | B | PASS |
| 6 | Second device resolves the same Trip, creates none | B | PASS |
| 7 | START photo + manual confirmation | A | PASS |
| 8 | START no-photo exception → Trip blocked | C | PASS |
| 9 | Admin approves → one-time manual entry → Trip starts | C | PASS |
| 10 | END normal photo path | D | PASS |
| 11 | END no-photo exception → session ENDED, evidence pending | E | PASS |
| 12 | Later approved END entry → distance resolves, no reopen | E | PASS |
| 13 | Unauthorized access to queue / photo refused | F | PASS |

Grouped into six journeys because the harness requires it: `seeded` reseeds between tests and the adjacent `uvicorn` caches tenant resolution for sixty seconds, so a second test in the same module would authenticate against a company that no longer exists.

**Full browser suite re-run, including RTE03 and RTE02-A01:** `tests/e2e/` → **13 tests, exit 0, 0 failures**. The six RTE04 journeys above, the RTE03 offline-queue journey and the six RTE02-A01 admin-lifecycle journeys all pass against the same production bundle — so the queue retry-policy change in §5 did not disturb the certified RTE03 behavior.

### Failures that occurred during this work

Reported because they happened, not because they survived.

| What failed | Cause | Status |
|---|---|---|
| 10 of 11 C4 tests, connect `TimeoutError` | `CONFIRMED` — reading odometer state cost five queries, two of them re-fetching rows the caller already held; with one physical connection per query under the tests' `NullPool`, the repetition exhausted PostgreSQL | Fixed: `session_state` reads each row once. Also removes real connection churn on a path the mobile screen hits every reconciliation |
| 5 of 6 browser flows, odometer UI absent | `CONFIRMED` — two separate causes: the bundle had not been rebuilt, and the production build strips `data-testid` | Fixed: rebuilt; locators anchored on text, role and `id` |
| 2 C4 tests | `CONFIRMED` — my own test bugs: `audit_event` uses `occurred_at`, not `created_at`; and a premise that cannot exist (an `arrived` Trip is still non-terminal, so a session cannot also hold a second `in_transit` Trip) | Fixed |
| Browser flow 1, twice | `CONFIRMED` — the standardized-values defect in §0.1, then a test bug (Change Plan opens on the current plan, so the context list needs an explicit step back) | Both fixed |
| `test_page_wiring` anchor test | `CONFIRMED` — new template not registered. The net exists to force this | Registered |
| 2 of 4 new odometer concurrency tests | `CONFIRMED` — `ensure_row` caught `IntegrityError` inside `transaction()`, producing `PendingRollbackError` (HTTP 500) on concurrent state reads | Fixed: the `try` now wraps the whole `async with`. This is the second time this exact misuse appeared in the project; it is worth a lint rule |
| 1 of 4 new odometer concurrency tests | `CONFIRMED` — `decide_exception` checked the request status outside the transaction, so two concurrent Admin decisions both returned 200 and the audit kept two contradictory decisions | Fixed: conditional `UPDATE ... WHERE status = 'requested'`; `rowcount == 0` → 409 |

---

## 8. Remaining PENDING VALIDATION

Carried forward explicitly. None of these authorizes bypassing any odometer integrity rule.

1. **Real iOS / Android hardware.** Validation is desktop Edge at phone viewport. Camera capture, `capture="environment"`, IndexedDB under iOS storage pressure and real network transitions are **not** validated.
2. **Offline odometer photo capture is not implemented.** The durable queue stores JSON, not multi-megabyte binaries. The odometer path deliberately does not queue: what the Supervisor needs to know is whether they may depart, and a queued confirmation would tell them yes while the server could still refuse. This is a declared scope limit, not an oversight.
3. **Representative real-fleet OCR quality.** PaddleOCR was measured in an isolated environment: correct on mechanical roller odometers and clean print, **total non-detection on a seven-segment display**, ~760 MB installed, 52.4s cold start. CER accepted leaving it **disabled by default**. The port is in place; plugging a provider in is one adapter and one registration, with no domain change.
4. **Bundle size.** `main.js` is 787 KiB, above webpack's 244 KiB advisory. Pre-existing, not introduced here.

---

## 9. Operational actions

| Action | Needed? |
|---|---|
| Migration `0006_odometer_evidence` on the target environment | **Yes** |
| `bootstrap` re-run to seed capabilities | **Yes** — `route.records.adjust` is new in the catalog and must be seeded before the Admin queue works |
| Frontend production build on deploy | **Yes** |
| Re-seed for the standardized-values fix | No — no capability was added |
| Manual data review | None. No ambiguous business data was interpreted |

**Local is not shared.** Everything in §7 was executed on a local Windows machine against a local PostgreSQL. No shared environment was touched and none of these results describes one.

---

## 10. Scope discipline

Not built, and not started: Activity execution, multi-select or timers, Outcome, Notes, GPS or geolocation, routing provider, official Routing Mileage, fuel calculation, Today/Live, Reports or export, route optimization, client or employee master catalogs, mid-session vehicle switching.

Not changed: RTE03 Work Session lifecycle and time semantics, RTE02-A01 certified configuration behavior, one active Work Session per Supervisor, one non-terminal Trip per Work Session, HOME arrival behavior, Change Plan traceability, the free-text field decisions, CER's timing matrix, the official Routing Mileage definition, odometer as independent evidence, OCR as assistive only, END exception Option B.

No microservices, event bus, CQRS, GraphQL, React Router, second ORM, second state manager or second HTTP client was introduced. No control was disabled to make a test pass.

---

## 11. Proposed status

**RTE04 — Completed / Ready for CER Certification**, with the four `PENDING VALIDATION` items in §8 carried forward and the one derived rule in §0.2 offered for confirmation.

Development stops here and awaits CER validation.
