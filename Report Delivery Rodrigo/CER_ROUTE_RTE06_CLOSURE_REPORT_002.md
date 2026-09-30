# CER Route — RTE06 Closure & Validation
## Delivery Report 002 (incremental — does not replace Report 001)
## Instruction: `CER_ROUTE_RTE06_CLOSURE_INSTRUCTIONS_003.md` (Revision 003)

**Proposed status:** `COMPLETED WITH PENDING VALIDATION`
**Date:** 2026-09-30
**Branch:** `feature/rte06-closure`

---

## 0. Read first — what closed, what did not, and why

**Three of the six closure items are closed with executed evidence.** Item A
(offline durability), Item B (real routing, primary **and** fallback) and Item C
(V-4 soak) are `CONFIRMED`, each measured rather than argued. The Missing
refactor of D-RTE06-MISSING-01 is implemented, migrated and tested.

**Three cannot be executed from a development environment**, and they are the
ones §12 counts for criterion 28. Item D needs a physical iPhone and a physical
Android. Item E needs a field run in CER's actual operating area. Item F needs a
pilot sample. No amount of work here produces them, and fabricating them is
what §9 explicitly forbids. They are `PENDING VALIDATION`, with executable
protocols delivered in
`_cer_delivery/CER_ROUTE_RTE06_FIELD_VALIDATION_PROTOCOLS.md`.

**So RTE06 closure cannot be proposed `COMPLETED` under §12's criterion 28**,
which requires no `PENDING VALIDATION` anywhere in scope. Saying otherwise would
be the exact claim the instruction is written to prevent. §27.

**Two real defects were found by measuring, not by reasoning**, and both are
fixed:

1. **OSRM invents plausible routes for coordinates outside its graph.** Measured
   against a real engine: two Berlin points against a Monaco extract returned
   **10,137.9 m** of "route" when the straight line is **1,072,614.23 m**. §6.
2. **A concurrent vehicle reassignment could leave a zero-length assignment**
   that `EXCLUDE` cannot see, because an empty range overlaps nothing. CP0's own
   concurrency test caught it intermittently. §19.

---

## 1. Closure Scope

What this delta touches, and nothing else:

| Item | Status | Section |
|---|---|---|
| D-RTE06-MISSING-01 — strict immutable fact, separated notification | `AS-BUILT / CONFIRMED` | §15, §16, §17 |
| Item A — offline location evidence durability | `AS-BUILT / CONFIRMED` | §3, §4, §5 |
| Item B — routing primary + fallback, live | `AS-BUILT / CONFIRMED` | §6, §7, §8 |
| Item C — V-4 offline soak | `AS-BUILT / CONFIRMED` | §9 |
| Item D — real device validation | `PENDING VALIDATION` | §10, §11 |
| Item E — field accuracy sampling | `PENDING VALIDATION` | §12 |
| Item F — evidence-level distribution | `PENDING VALIDATION` | §13 |

**Nothing in §11's do-not-reopen list was touched.** No Work Session, Trip state
machine, Activity execution, Change Plan semantics, odometer, OCR, Route roles or
permissions, standardized lists, Today/Live, Reports, Activity Explorer, fuel,
geocoding, maps, navigation, continuous tracking or retention duration. No
framework refactor.

The approved baseline of §1 is preserved: official mileage is still routed road
distance, one Trip is still one Trip across Change Plan, every Change Plan is
still an authoritative waypoint, a missing required waypoint is still
`Not Calculable`, Haversine/breadcrumbs/odometer/destination text are still never
official, `Pending` is still transient, `Calculated` is still immutable,
provenance still survives a purge, OCR is still out.

---

## 2. Starting Findings

What the closure instruction got right about the previous delivery:

**§4 was correct that fire-and-forget delivery is not durable.** The previous
implementation called `$api.post` directly from the capture module. With no
network, the promise rejected, the `catch` swallowed it — correctly, for §12's
silence — and a point the device had actually measured was **lost**. Report 001
described the capture as non-blocking, which it was, and did not notice that
non-blocking had been implemented as fire-and-forget.

**§3's tension was real and CER resolved it.** Report 001 §36.3 flagged that
`missing_location_event` carried notification state and therefore could not be
append-only without column exemptions, and said so as an interpretive call of
mine. D-RTE06-MISSING-01 resolves it toward the strict reading. That is
implemented here.

**§6 was correct that `PARTIAL` is not a closure state.** V-4 is now
`CONFIRMED` with an executed soak. §9.

---

## 3. Offline Location Durability

### The store

Evidence is written to IndexedDB **before** the send is attempted, in the same
module and the same database as the RTE03 queue (`cer-route-offline`, version
bumped to 2), in a **separate object store** (`pending_location_evidence`).

**Separate store, not a separate queue.** §7 of the base instruction forbids a
second queue and this is not one: same module, same database, same single flush
entry point. Two lanes, because the two kinds of data have different ordering
semantics — see §4.

`onupgradeneeded` creates what is missing and touches nothing that exists, so a
device sitting on version 1 with queued actions keeps them.

### The key is the correlation tuple

The store's `keyPath` is `id`, and `id` is `{event_kind}:{subject_id}` — the same
tuple the server uses. So storing the same event twice **replaces** rather than
appends: idempotency starts on the device and does not depend on the server
fixing it afterwards. The server's unique index still guarantees it, which is
why both exist.

### What is preserved verbatim

The payload is stored exactly as measured, including `evidence_level` and
`device_captured_at`. Nothing recomputes those at send time, which is what makes
"a cached point does not become fresh because the upload happened later" true by
construction rather than by care. Asserted in §5.

---

## 4. Offline Storage / Replay Architecture

### Two lanes, and why the operational queue was not reused directly

The action queue **stops at the first failure** so that an `Arrived` is never
applied before its `Start Trip` — an ordering the domain cannot produce by
itself. Location evidence has no such requirement: each point is bound to its
event by the correlation tuple, and the server rejects it if the event does not
exist.

If they shared a lane, a point the server rejects would block the operational
actions queued behind it. So the evidence lane **continues past a failure**,
implemented as a sequential recursion mirroring `enviarEnOrden`, for the same
reason the project avoids loops and to make the difference explicit in the code.

### Flush order is deliberate

`flushPendingActions()` drains the action queue **first**, then the evidence
lane. A point can only be bound to its event once the event exists on the
server, and the event arrives through the action queue. The other order would
waste one attempt per point on every reconnect.

### Definitive rejection differs from the action queue

The action queue treats any 4xx except 408/429 as definitive. The evidence lane
adds **404** to the non-definitive set, and that is the interesting difference:
a 404 means the event does not exist on the server **yet**, because its action is
still in the other queue. Retrying is exactly right. Treating it as definitive
would discard evidence for the most common offline case.

### The deferred subject — the hard part

The correlation key is a **server-generated id**. Offline, `Start Work` has no
`work_session.id`, so a measured point has nothing to bind to. Three options,
and two of them are wrong:

- capture only after the action confirms → loses the measurement (the previous
  behaviour, which §4 rejects);
- bind to "the current session" at flush time → binding by proximity, which §4
  forbids in as many words;
- **store the point with the subject deferred, and resolve it after the action
  syncs** — which is what §4 actually describes: "bind to the exact lifecycle
  event after replay".

The entry carries `subjectPending: 'work_session' | 'trip'`. At flush, if the
subject is deferred, the sender reads `/worksessions/current` and fills the id —
**but only if exactly one deferred entry of that kind exists.** If a supervisor
made two trips with no network, two `start_trip` points would compete for one
`trip.id` and either could be the wrong one. In that case **neither** is bound,
the entries stay pending, and the server's sweeper declares Missing. Refusing to
bind when the binding cannot be proven is the truthful behaviour, and it is what
§4's "never bind by nearest timestamp / never bind to the wrong event" requires.

---

## 5. Exact Correlation Evidence

`tests/e2e/test_rte06_offline_durability_browser.py` — **6 journeys, 0 failures,
exit 0.** Production bundle, Edge, 390×844, geolocation **granted** with a fixed
position so the module produces real `fresh` evidence.

| Journey | What it proves |
|---|---|
| A location captured offline is not lost | network cut **before** the action; the point is in the store with `evidence_level: fresh` and a key starting `start_work:`; after reconnect it reaches `location_fix` with the right event kind and the coordinate that was set |
| Pending evidence survives a page restart | the page is **closed** and another opened in the same context — what a supervisor does by closing the browser. The entry is still there and syncs |
| A cached point does not become fresh after a delayed upload | the level and `device_captured_at` that arrive are the ones that were stored, not recomputed |
| A replayed capture writes one authoritative point | reloading with the network still cut does not stack entries; one point arrives |
| The store is drained and left clean after sync | the entry is removed **on confirmation**, so the device does not grow without limit or retry accepted points forever |
| Reauthentication does not discard pending evidence | the store is per-origin, not per-session; the point survives a fresh login |

§4's required list, mapped:

| Required | Where |
|---|---|
| Start Trip queued offline + location captured offline → both sync | journey 1 (Start Work; same mechanism, and the one whose subject id does not exist yet — the harder case) |
| Change Plan queued offline → correct purpose-change id after replay | the change id is server-generated and read from `/plan-changes`; offline it defers, and §4's ordering guarantee is covered by the soak (§9, invariant 6) |
| Multiple queued Change Plans preserve occurrence order | §9, invariant 6 — evidence sent **in reverse** and the first segment still starts at `start_trip` |
| Duplicate evidence replay writes one point | journey 4, and §9 invariant 1 across 12 cycles |
| App/browser restart does not lose evidence | journey 2 |
| Reauthentication does not discard evidence | journey 6 |
| Cached does not become Fresh after delayed upload | journey 3 |
| Recovered preserves its actual capture timestamp | Report 001 §32 (C3), unchanged |
| Missing is not created if valid evidence arrives in time | the server refuses a Missing when a point exists (409) — Report 001 §32 |

---

## 6. Routing Primary Live Validation

**Self-hosted OSRM, in Docker, on a real OSM extract.** Not a public endpoint and
not a double: `osrm/osrm-backend` with the Monaco test extract from the OSRM
project itself, built through `osrm-extract` → `osrm-partition` →
`osrm-customize` and served by `osrm-routed --algorithm mld` on
`localhost:5000`.

### Measured

| Measurement | Value |
|---|---|
| Straight line A→B (haversine) | **1,262.67 m** |
| OSRM A→B | **2,061.60 m**, `provider=osrm`, `method=driving` |
| OSRM A→C + C→B (multi-segment) | 977.9 + 1,661.5 = **2,639.40 m** — ≥ the direct route, as detouring must be |

A and B are two real points in Monaco (43.7311/7.4197 and 43.7398/7.4298). The
ratio to the straight line is 1.63×, which is what city streets look like.

### The defect this measurement found

**Without a snap radius, OSRM binds any coordinate to the nearest road in
whatever graph it has loaded.** Measured:

```
A → Berlin, no radius:  10,137.90 m of "route"
straight line A → Berlin: 1,072,614.23 m
```

The engine returned `Ok` and a plausible number for a place that is not there.
This is the failure mode that breaks nothing and lies, and Report 001 §20 named
it as a risk without knowing it was already happening.

Fixed by sending `radiuses` on every request, configurable as
`route_mileage.snap_radius_m`, default 1,000 m. With it, the same query returns
`NoSegment`, which the adapter classifies as **permanent** — a truthful
`Not Calculable` instead of a distance from another continent.

Default 1,000 m is generous on purpose: a stop in a large car park or a rural
area can legitimately be far from a mapped way, and an aggressive radius would
turn real stops into `Not Calculable`. Item E's field sampling is what should
tune it, and the protocol document lists it as a fifth threshold to review.

**Both defences now exist and that is deliberate.** The geometric plausibility
check would have caught this downstream — the invented route is *shorter* than
the straight line, which is impossible — and a test pins that too, so nobody
removes `radiuses` believing it is an optimisation.

### One more adapter fix from the same measurement

`NoSegment` arrives with **HTTP 400**. Classifying by status first produced the
correct terminal state but lost the reason: "OSRM rejected the request with 400"
tells a reader nothing in a year's time. The adapter now reads the body's `code`
before the generic 4xx branch, so "no road within the snap radius of a waypoint"
survives into the trace.

---

## 7. Routing Fallback Live Validation

**Self-hosted Valhalla, in Docker, on the same OSM extract.** `ValhallaRouter`
was written for this closure — Report 001 named Valhalla as the fallback but only
OSRM had an adapter, which is exactly the "documented but not exercised" state
§5 rejects.

### Why Valhalla and not a second OSRM

A process failure is covered by either. An **engine** failure — a version with a
defect, a profile that rejects a geometry — is only covered by a different
implementation. Same OSM data, different codebase, MIT licence.

### What the adapter had to convert

Valhalla's contract does not resemble OSRM's: the request is JSON, points are
`{lat, lon}` — the reverse order — and the distance arrives in **kilometres**
inside `trip.summary`. Converting there is the adapter's whole job.

### Measured

| Measurement | Value |
|---|---|
| Valhalla A→B | **2,059.00 m**, `provider=valhalla`, `method=auto` |
| Divergence from OSRM | **1.001×** |

The two engines, over the same data, agree to **within one tenth of a percent**.
That is the strongest evidence available that both adapters are correct: a unit
error in either — kilometres left unconverted, coordinates swapped — would show
up as a factor, not a rounding difference.

### The fallback path, exercised

| Measurement | Value |
|---|---|
| Primary pointed at a closed port, fallback live | **2,059.00 m**, `provider=valhalla` |

`provider` is the engine **actually used**, not the one configured, and that is
what gets written into the segment's provenance — §23 requires exactly that.

---

## 8. Routing Failure Matrix

`tests/integration/test_route_routing_live.py` — **10 tests, 0 failures,
exit 0**, with both engines running.

| # | Case | Real or simulated | Result |
|---|---|---|---|
| 1 | Primary returns a credible road distance | **real** OSRM | `Ok`, > straight line, < 5× |
| 2 | Waypoint outside the graph → **permanent** | **real** OSRM | `NoSegment`, `transient=False`, reason preserved |
| 3 | No snap radius → the engine invents a route | **real** OSRM | routed < straight line: the lie, pinned |
| 4 | Unreachable primary → **transient** | **real** (closed port) | `transient=True` |
| 5 | Fallback returns a credible road distance | **real** Valhalla | km→m conversion correct |
| 6 | The two engines agree within a sane margin | **real** both | 1.001× |
| 7 | Primary down → fallback succeeds | **real** both | `provider=valhalla`, distance > 0 |
| 8 | Permanent primary failure does **not** consult the fallback | **real** primary, counting double | 0 calls to the fallback |
| 9 | Both down → transient chain failure naming both | **real** (two closed ports) | message carries both |
| 10 | Multi-segment trip sums real road distances | **real** OSRM | via C ≥ direct |

Case 8 matters: over the same OSM data a permanent answer would be the same from
either engine, so retrying would turn an honest terminal state into one more
attempt. The fallback covers a primary that is **down**, not a primary answering
something inconvenient.

**Deterministic doubles remain** for the automated failure coverage §40 requires
— Report 001 §32 — and the suite still does not depend on the network: this file
skips when the engines are not configured. The closure evidence is that it was
executed, which is what §13 of this instruction allows.

### How to reproduce

```bash
# primary
docker run -d --name cer-osrm -p 5000:5000 -v "$PWD:/data" \
  osrm/osrm-backend osrm-routed --algorithm mld /data/monaco.osrm
# fallback
docker run -d --name cer-valhalla -p 8002:8002 -v "$PWD/valhalla_files:/custom_files" \
  -e serve_tiles=True ghcr.io/nilsnolde/docker-valhalla/valhalla:latest

ROUTE_ROUTING_URL=http://localhost:5000 \
ROUTE_ROUTING_FALLBACK_URL=http://localhost:8002 \
  uv run pytest tests/integration/test_route_routing_live.py
```

---

## 9. Offline Soak Result

`tests/integration/test_route_offline_soak.py` — **1 test, 0 failures, exit 0,
216.89 s.**

### The load, and why it is what it is

**12 cycles**, configurable through `ROUTE_SOAK_CYCLES`. Each cycle is a full
work day: session, trip, one or two Change Plans, arrival, close. Every piece of
evidence is sent **twice**, two of them concurrently, and **out of order** —
arrival first, departure last, which is what a queue draining after several
disconnections produces. Reauthentication happens mid-cycle in a third of them,
and a second tenant runs in parallel every third cycle.

**Twelve is a measured limit, not a preference.** The first version used 30 and
failed after **39 minutes** with an asyncpg `TimeoutError`: the suite's
`NullPool` opens a physical connection per query, and 30 days' worth of
duplicated evidence exhausts the test server's pool. That was an infrastructure
failure, not an invariant — but a soak that does not finish proves nothing, so
the load is set to what this harness sustains **and the limit is declared rather
than hidden**.

Twelve remains meaningful because what this soak checks is **structural**:
uniqueness is guaranteed by indexes and ordering comes from domain rows, so
neither becomes more true at 30 repetitions. What repetition buys is the
concurrent duplicate arriving in different orders, and that happens in **every**
cycle.

### The six invariants, all green

| # | Invariant | How it is measured |
|---|---|---|
| 1 | No duplicated point | `GROUP BY` the correlation tuple `HAVING count(*) > 1` → 0 |
| 2 | No wrong correlation | every point's subject row must exist **and** be of its company → 0 orphans; and every `change_plan` point's trip must itself have a departure point → 0 crossed |
| 3 | No duplicated mileage | one `trip_mileage` per trip, no duplicated `(trip_mileage_id, sequence)` |
| 4 | No **permanent** Pending | no pending row without a retry date or with attempts exhausted; then, with the clock advanced each pass, all reach terminal |
| 5 | Tenant isolation | no point bound to another company's session; both tenants carry evidence |
| 6 | Occurrence order, not arrival order | evidence was sent **in reverse**; every first segment still starts at `start_trip` and every `arrived` is the last |

Invariant 6 is the one the out-of-order submission exists for: if the engine
ordered by capture time or by insertion id, the segments would come out
backwards.

### Two mistakes of mine inside this soak

**1. Waypoints one minute apart with a 9 km segment — `CONFIRMED`, corrected.**
Three mileages would not resolve, failing with
`Implausible segment 2: implied speed 540.0 km/h exceeds 160`. My fixture placed
two Change Plan captures **60 seconds** apart while the double returned 9 km per
segment. The plausibility check was right and the test data was impossible. Now
spaced an hour apart. Same class of error as the 130 km one in Report 001.

**2. The clock was advanced once, outside the retry loop — `CONFIRMED`,
corrected.** Each sweep pass schedules a new backoff, so advancing the clock
once left every later pass with nothing due, and a pending that was merely
waiting looked eternal. The loop now advances the clock on each turn, which
makes the bounded retry actually exhaust — so the assertion means "it either
calculates or reaches terminal", which is what §24 requires.

**And one earlier wrong assertion of mine**, reported because it happened: the
first version of invariant 4 demanded **zero** pending rows after sweeping and
failed with four. Those four had a future `next_attempt_at`: the backoff
working. "No permanent Pending" means no pending **without a path**, not no
pending right now.

**V-4 is `CONFIRMED`.**

---

## 10. iOS Physical Validation

`PENDING VALIDATION`. **Not executable from this environment** — it needs a
physical iPhone.

§38 of the base instruction states that desktop browser emulation is not
real-device validation, so nothing in this delivery can be offered in its place.
What is unmeasured, specifically: behaviour under backgrounding, under screen
lock, on return to the foreground, and with permission revoked mid-session,
under Safari's stricter geolocation lifecycle.

**The protocol is delivered and ready to run**:
`_cer_delivery/CER_ROUTE_RTE06_FIELD_VALIDATION_PROTOCOLS.md`, Item D, ten
scenarios with a recording template.

One constraint written into that protocol, because getting it wrong would
produce a false claim: **background capture must not be claimed.** Neither
Safari nor Chrome grants geolocation to a backgrounded tab or a locked screen.
What the validation records is what actually happens — the event stays pending
and resolves on return, or it ends as Missing — not what would be desirable.

---

## 11. Android Physical Validation

`PENDING VALIDATION`. Same reason, same protocol, same ten scenarios under
Chrome on a physical Android device.

---

## 12. Field Accuracy Sample

`PENDING VALIDATION`. Needs a run through CER's actual operating area: the mix
of dense urban, indoors, car park and open road is precisely what moves these
numbers, and an office desk cannot produce it.

The protocol specifies **at least 40 captures** across the seven lifecycle
events, over two different days and two times of day, with the SQL to extract
latency, accuracy, cached age and rejection cases — `attempts` already carries
per-stage durations, so acquisition latency needs no extra instrumentation.

Forty is not arbitrary: it is the minimum at which a 10% Missing rate is
distinguishable from a 25% one. Below that the sample cannot support a decision
about thresholds.

---

## 13. Evidence-Level Distribution

`PENDING VALIDATION`. A distribution is a field measurement, and §9 of the
closure instruction says not to fabricate percentages. Nothing in this delivery
produces one.

The protocol gives the query — with `missing` counted **separately**, because it
is not an evidence level and summing it into the same percentage would
contradict §11 — and the four pathologies to look for: excessive Missing, cached
dominating normal use, recovery almost never succeeding, and Fresh acquisition
taking too long.

---

## 14. Final Thresholds

**Not final.** They cannot be, and this is the honest statement of it: §8 of the
closure instruction says final thresholds must no longer be described as
temporary or unvalidated defaults, and that becomes true only when Item E has
run. Until then they are **technically defensible and unvalidated**, which is
what Report 001 already said.

| Key | Value | Basis | Status |
|---|---|---|---|
| `fresh_timeout_seconds` | 10 | a GPS that has not fixed in 10 s at high accuracy usually does not fix at 20 | awaiting Item E |
| `cached_max_age_seconds` | 300 | **the most doubtful of the five**; in a moving vehicle five minutes can be kilometres | awaiting Item E |
| `cached_max_accuracy_m` | 500 | above half a kilometre the point stops distinguishing one stop from the next | awaiting Item E |
| `recovery_window_seconds` | 180 | bounded because §11 requires it bounded | awaiting Item E |
| **`snap_radius_m`** | **1,000** | **added by this closure**, after measuring that no radius lets the engine invent routes. Generous so real stops far from mapped ways are not lost | awaiting Item E |
| `segment_max_meters` | 800,000 | the point beyond which a result is almost certainly a coordinate error | defensible without field data |
| `implied_speed_max_kmh` | 160 | catches what a distance limit cannot see | defensible without field data |
| `max_attempts` / `backoff_base_seconds` | 5 / 60 | ~30 minutes of provider outage, bounded per §24 | defensible without field data |

All live in `PlatformPolicy` and are adjustable without a deploy, so closing
Item E changes configuration and not code.

---

## 15. Missing Location Event Refactor

### The fact is now strictly immutable

`missing_location_event` carries the generic project trigger: no `UPDATE`, no
`DELETE`, no `TRUNCATE`, **no column exemptions**. The previous version exempted
`notification_status`, `notified_at`, `notes` and `updated_at`, which is a
mutable fact with extra steps.

`notes` is **gone and not replaced**. An editable free-text field on a historical
fact is exactly the reinterpretation D-RTE06-MISSING-01 forbids.

### What the fact retains

Everything §3 lists: company, work session, trip, lifecycle action/subject,
event kind, occurrence timestamp, reason code, permission/acquisition state,
attempt evidence, rejected candidate **age and accuracy**, and created
timestamp.

**Rejected candidate coordinates are not stored.** Knowing there was a two-hour-old
point with 3 km of error explains the failure; storing where it was would retain
a location the system decided not to use. Asserted directly.

---

## 16. Notification State Separation

`missing_location_notification` — operational, and it does change.

| Column | Why |
|---|---|
| `missing_location_event_id` + `company_id` | composite FK, `RESTRICT`: cannot reference another tenant's fact, cannot outlive it, cannot take it down |
| `channel` | `in_platform` and `email` **from the start**, so adding a channel is not a schema migration — §3 requires compatibility with future channels |
| `status` | `pending` / `notified` / `failed` / `suppressed` |
| `attempt_count`, `last_attempt_at`, `delivered_at` | the delivery lifecycle |
| `failure_code`, `failure_detail` | a code, not a phrase: the interface decides what to show |

One row per fact **and channel** (`uq_missing_location_notification_channel`), so
a retry advances the row instead of stacking attempts — otherwise "was the
in-platform notice sent?" would have as many answers as attempts.

A `CHECK` requires `notified` to carry `delivered_at` and every other status not
to: a row claiming delivery without saying when would make the delivery
unauditable, which is the only thing this table exists for.

**No Route notification inbox was created**, and no delivery mechanism was
built. §30 and §3 both forbid it. The fact and its notification row are created
in the **same transaction**, so a fact can never be invisible to whatever
delivers notices later.

---

## 17. Migration Evidence

### `0011_strict_missing_fact`

| Check | Result |
|---|---|
| `upgrade` | **exit 0** |
| Data moved, not dropped | `INSERT ... SELECT` creates one notification row per existing fact, preserving its status and `notified_at`, **before** the columns are dropped, in the same transaction |
| Rows it could not interpret | **counted and logged**, not silenced |
| `notes` with content | **counted and logged** — there is no destination for that text in the new model and one was not invented; the decision about it belongs to whoever reads the log |
| Measured in this environment | `0011 | missing_location_event -> notification: 0 migradas, 0 con estado desconocido migradas como pending, 0 con notas que NO tienen destino en el modelo nuevo` |
| `downgrade` | **exit 0** — restores the columns, moves the state back **before** dropping the table, and restores the column-scoped trigger |
| Autogenerate roundtrip | **0 operations** |

One ordering fix made by hand: autogenerate created the new table before the
composite unique on `missing_location_event(id, company_id)` that its FK needs,
so `CREATE TABLE` failed. The unique now comes first.

### `0012_no_empty_period`

See §19 for the defect. The migration deletes zero-length assignment rows and
**counts** them in its log; measured here: `0`. Deleting loses no information
because an empty interval asserts no fact, and what actually happened remains in
`audit_event`, which is append-only and untouched.

| Check | Result |
|---|---|
| `upgrade` / `downgrade` | **exit 0** |
| `alembic heads` | **1** — `0012_no_empty_period` |

---

## 18. Security / Tenant Isolation

| Requirement | Evidence |
|---|---|
| Notification cannot reference another tenant's fact | composite FK; asserted with a cross-tenant `INSERT` → `fk_missing_location_notification_event_same_company` |
| Evidence cannot be bound to another tenant's session | soak invariant 5 — 0 rows across 12 cycles and two tenants |
| Cross-tenant mileage read | 404 — Report 001 §32 (L6), unchanged |
| No new capability | none added; capture still uses `route.worksession.execute` |
| No coordinates in logs or audit | unchanged from Report 001 §31; the new notification table holds no coordinates either |

**No capability, role or permission was introduced or changed.**

---

## 19. Historical Immutability

### The defect this closure found in CP0

`ex_vehicle_assignment_no_overlap` uses `tstzrange(..., '[)')`, and an **empty**
range — `effective_to = effective_from` — **overlaps nothing**, so the constraint
cannot see it. That leaves a crack on the concurrent path:

```
two assign(desde = t) at once, with no previous assignment
  request A: no previous, inserts [t, inf)
  request B: reads A's row, closes it at effective_to = t
             -> A's row becomes [t, t), which is EMPTY
             -> inserts [t, inf), and EXCLUDE does not object
```

Measured in this repository:

```
codes: [200, 200]
id=1 vehicle=1 from=...693463 to=...693463  empty=True
id=2 vehicle=2 from=...693463 to=NULL       empty=False
```

Found by CP0's own concurrency test, which had been passing **intermittently**
depending on how the two requests interleaved.

**What it does and does not break.** The applicable vehicle stays deterministic:
`effective_at` requires `effective_from <= T AND effective_to > T`, which is
false for an empty range, so the phantom row is never resolved as current and no
work session started with the wrong vehicle. What it does break is the register —
a row asserting "this vehicle was assigned from t until t", i.e. never — and the
register exists to be read.

**Fixed** by tightening `ck_vehicle_assignment_period` from `>=` to `>`
(migration 0012). On the concurrent path the second request's `UPDATE` now
fails, so exactly one survives — which is what §8.3's invariant intended. The
only thing lost is the ability to record a zero-length assignment, and that is
not a business fact.

The 409 is legible: `23514` (check_violation) maps to "Another change to this
supervisor's vehicle happened at the same moment. Reload and try again."

**CP0's overlap suite: 8/8, three consecutive runs.** The race is closed.

### Mileage immutability

Unchanged and re-verified: `UPDATE ... WHERE state = 'pending_calculation'`,
segments written in the same transaction under the same condition. Report 001
§24, plus soak invariant 3.

---

## 20. Purge-Safe Provenance

Unchanged from Report 001 §25 and re-verified by the regression: each segment
copies both waypoints' coordinates, evidence level, accuracy and capture time,
plus provider, method, version and computation time; `*_fix_id` are soft
references with no foreign key.

The H2 test still deletes `location_fix` for real and reads every provenance
field back.

One thing the closure adds: with the fallback in play, `provider` records the
engine **actually used**, so a segment routed by Valhalla after an OSRM outage
says `valhalla` years later.

---

## 21. Regression

| Batch | Tests | Result | Exit |
|---|---|---|---|
| RTE06 core: location evidence, mileage engine, Missing immutability, CP0 overlap, platform diagnostics | **80** | **0 failures** | 0 |
| Remaining `tests/integration`, first half | **207** | **0 failures** | 0 |
| Remaining `tests/integration`, second half + page wiring + navigation wiring + permission catalog + public surface | **463** | **0 failures** | 0 |
| Offline soak | **1** | **0 failures** | 0 |
| Live routing, both real engines | **10** | **0 failures** | 0 |

**Total: 761 integration tests, 0 failures, every batch exit 0**, plus 91 browser journeys in §22 — **852 in all**.

### Why the suite ran in batches, declared

Two attempts at larger runs were **stopped by the harness at its 30-minute
background limit** — the first with 467 tests and 0 failures recorded, the second
with 437. Neither is reported as a pass: a stopped run is not a result. The suite
was split by file until every batch finished on its own, and those are the
figures above.

### One batch stopped by the harness, declared

The first attempt at a single full-suite run was **stopped at the 30-minute
background limit** with **467 tests and 0 failures** recorded before the cut.
That is not a pass and is not reported as one: the suite was re-run in batches,
and those are the figures above.

### Changed existing tests — `old → approved delta → new`

Two tests in `test_route_location_evidence.py` asserted the pre-closure
notification model. §40 requires documenting the delta:

| Test | Old expectation | Approved CER delta | New expectation |
|---|---|---|---|
| `test_missing_is_created_once_and_fabricates_nothing` | the fact carried `notification_status` and it was read from there | D-RTE06-MISSING-01 | the column does not exist; delivery state is read from `missing_location_notification`, and the API still returns it for the client's convenience |
| `test_only_the_notification_fields_of_a_missing_event_may_change` → renamed `test_the_missing_fact_admits_no_update_at_all` | the trigger permitted `UPDATE` of four columns | D-RTE06-MISSING-01 | no `UPDATE` and no `DELETE`, `updated_at` included; that the notice **does** advance is proven in `test_route_missing_immutability.py`, where it now belongs |

**No test was weakened, skipped or xfailed to obtain closure.** The only skips
are the environment-gated live routing tests when no engine is configured, and
§13 permits exactly that provided the closure evidence shows execution — §8 shows
it.

---

## 22. Browser Evidence

Every browser suite was re-run after the frontend changes, because the capture
module, the queue and the workbench were all touched.

| Batch | Journeys | Result | Exit |
|---|---|---|---|
| RTE05 workbench + RTE06 silent capture + **RTE06 offline durability (new)** + RTE03 work-session offline | **33** | **0 failures** | 0 |
| Activity execution, RTE05 closure, Route access, admin lifecycle, user creation, odometer | **58** | **0 failures** | 0 |

**Total: 91 browser journeys, 0 failures, both batches exit 0.**

The RTE05 workbench staying green is the load-bearing evidence here: the capture
is wired into six of its actions and the durable store now sits in front of every
send, so §36's "no extra step, no blocking spinner" had every opportunity to
break and did not.

---

## 23. Typecheck / Lint / Build

| Check | Result |
|---|---|
| `npm run typecheck` | **0 errors** |
| `npm run lint:ts` | **0 errors** |
| `npm run build:prod` | **exit 0**, 2 pre-existing webpack size hints |
| `import app.main` | **exit 0** |
| `alembic heads` | **1** |
| `alembic upgrade` / `downgrade` / `upgrade` | **exit 0** each way for 0011 and 0012 |
| Autogenerate roundtrip | **0 operations** |

---

## 24. Expected → Implemented → Evidence → Gap

§12's 28 closure criteria:

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | CP0 remains green | **AS-BUILT / CONFIRMED** | §19 — and a latent defect in it was found and fixed; 8/8 ×3 |
| 2 | Offline location evidence is durable and proven | **AS-BUILT / CONFIRMED** | §3, §5 |
| 3 | Exact action correlation survives offline replay | **AS-BUILT / CONFIRMED** | §4, §5, §9 inv. 2 and 6 |
| 4 | App restart does not lose pending evidence | **AS-BUILT / CONFIRMED** | §5 journey 2 |
| 5 | Primary routing engine is live-tested | **AS-BUILT / CONFIRMED** | §6 |
| 6 | Fallback path implemented and live-tested | **AS-BUILT / CONFIRMED** | §7 |
| 7 | Primary failure → fallback success proven | **AS-BUILT / CONFIRMED** | §7, §8 case 7 |
| 8 | Total routing failure → correct terminal state | **AS-BUILT / CONFIRMED** | §8 case 9 |
| 9 | V-4 soak is `CONFIRMED` | **AS-BUILT / CONFIRMED** | §9 |
| 10 | iOS physical validation completed | **PENDING VALIDATION** | §10 — not executable here |
| 11 | Android physical validation completed | **PENDING VALIDATION** | §11 — not executable here |
| 12 | Field accuracy sampling completed | **PENDING VALIDATION** | §12 — not executable here |
| 13 | Evidence-level distribution measured | **PENDING VALIDATION** | §13 — not executable here |
| 14 | Configurable thresholds reviewed and finalized | **PENDING VALIDATION** | §14 — depends on 12 |
| 15 | `MissingLocationEvent` strictly immutable | **AS-BUILT / CONFIRMED** | §15 |
| 16 | Notification state separated | **AS-BUILT / CONFIRMED** | §16 |
| 17 | No generic mutable Missing notes remain | **AS-BUILT / CONFIRMED** | §15 — column dropped, not replaced |
| 18 | No partial mileage total published | **AS-BUILT / CONFIRMED** | Report 001 §32 (R5) + table CHECK |
| 19 | No Missing waypoint skipped | **AS-BUILT / CONFIRMED** | Report 001 §32 (C4) |
| 20 | Calculated mileage immutable | **AS-BUILT / CONFIRMED** | §19, Report 001 §24 |
| 21 | Purge-safe provenance intact | **AS-BUILT / CONFIRMED** | §20 |
| 22 | Tenant isolation green | **AS-BUILT / CONFIRMED** | §18 |
| 23 | No new capability without approval | **AS-BUILT / CONFIRMED** | §18 |
| 24 | RTE03/04/05 regression green | **AS-BUILT / CONFIRMED** | §21 |
| 25 | Migration checks green | **AS-BUILT / CONFIRMED** | §17, §23 |
| 26 | Typecheck / lint / build green | **AS-BUILT / CONFIRMED** | §23 |
| 27 | No RTE07+ scope introduced | **AS-BUILT / CONFIRMED** | §1 |
| 28 | **No `PARTIAL`, `PENDING VALIDATION`, `NOT IMPLEMENTED / GAP` or `BLOCKED` in scope** | **NOT MET** | five items above |

**23 of 28 met. Five are `PENDING VALIDATION`, and criterion 28 therefore fails
by construction.**

No `PARTIAL` remains — V-4 was the only one and it is `CONFIRMED`. No
`NOT IMPLEMENTED / GAP`, no `DEVIATION`, no `UNAUTHORIZED DECISION`, no
`BLOCKED`.

---

## 25. Deviations / Technical Debt

### No deviations from the instruction

Every technical choice was made inside §14's authority: the store layout, the
deferred-subject mechanism, Valhalla as the fallback engine, the snap radius,
the soak's shape and load. None of them alters approved business behaviour, the
privacy model, permissions, tenant isolation, the modular architecture, scope, or
cost/contract/licensing — both engines are BSD-2 and MIT, self-hosted, no spend.

No STOP condition of §16 was triggered.

### Technical debt, declared

| Item | Why it is debt, not a defect |
|---|---|
| The soak runs at 12 cycles because of `NullPool` connection churn in the test harness | the limitation is the harness, not the product. A pooled test engine would let it run at 30+; nobody has needed that until now |
| `snap_radius_m` default is generous (1,000 m) | it is a first defensible value, not a measured one. Item E should tune it, and the protocol lists it |
| The deferred subject resolves only when exactly one entry of its kind is pending | two offline trips in one session leave both unbound and the server declares Missing. Correct and truthful, but it means a supervisor working offline through two full trips loses both departure waypoints. Closing it properly would need the server to know the client's action key, which is a contract change not in this scope |

---

## 26. Final Validation Inventory

| # | Item | Status | Change from Report 001 |
|---|---|---|---|
| **V-1** | Real iOS Safari lifecycle | `PENDING VALIDATION` | unchanged — protocol now delivered |
| **V-1b** | Real Android Chrome lifecycle | `PENDING VALIDATION` | unchanged — protocol now delivered |
| **V-2** | Field accuracy / acquisition sampling | `PENDING VALIDATION` | unchanged — protocol now delivered, and a fifth threshold added to it |
| **V-3** | Routing provider: evaluation **and live measurement** | **`CONFIRMED`** | **was `PENDING VALIDATION`.** Both engines stood up in Docker on real OSM data and measured; §6, §7, §8 |
| **V-4** | Offline queue soak with location evidence | **`CONFIRMED`** | **was `PARTIAL`.** §9 |
| **V-5** | Evidence-level distribution | `PENDING VALIDATION` | unchanged — protocol now delivered |

---

## 27. Proposed Status

**`COMPLETED WITH PENDING VALIDATION`.**

**This is not a proposal to certify RTE06.** §2 of the closure instruction asks
for a status of `COMPLETED / READY FOR CER CERTIFICATION` with no
`PENDING VALIDATION` in scope, and §15 says a `COMPLETED` proposal is valid only
when no unresolved classification remains. Five items remain, so proposing
`COMPLETED` would be making the claim the instruction was written to prevent.

What is closed: the Missing refactor, offline durability, real routing with a
real exercised fallback, the soak, and two defects that only measuring could
have found.

What is not, and cannot be from here: physical devices, a field sample, a pilot
distribution, and the threshold review that depends on the sample.

### Operational action required elsewhere

| Action | Why | Where |
|---|---|---|
| **Execute Items D, E and F** | the five open criteria. Protocols are written and ready in `_cer_delivery/CER_ROUTE_RTE06_FIELD_VALIDATION_PROTOCOLS.md` | CER / pilot with real devices |
| **Provision OSRM and Valhalla** in the shared environment | both are proven locally; without them deployed, mileage stays pending and terminalises by bounded retry | DevOps |
| **Run migrations 0011 and 0012** | notification separation, and the zero-length assignment fix. 0012 logs how many phantom rows it removed — **if that number is not zero in a shared environment, that tenant went through the race** | deploy |
| Review `snap_radius_m` after Item E | a first defensible value | CER / DevOps |

No capability, no seed, no bootstrap.

### Next step

CER's review. **No RTE07 work has begun and none will begin before explicit
certification.**

# STOP
