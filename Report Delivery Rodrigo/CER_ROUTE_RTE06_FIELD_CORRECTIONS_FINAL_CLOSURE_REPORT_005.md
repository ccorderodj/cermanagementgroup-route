# CER Route — RTE06 Field Corrections Final Closure

**Report 005** · incremental over Report 004 · branch
`feature/rte06-field-corrections-final-closure` · 2026-10-02

Scope: the Development-side delta requested in
`CER_ROUTE_RTE06_FIELD_CORRECTIONS_FINAL_CLOSURE_INSTRUCTIONS_002.md`.
RTE07, RTE10-A01 and Location Permission Enforcement were not started.

---

## 1. Executive Result

The gap CER identified in §2.1 was real, and looking for it found **five more**
in the same area. The important one changes the shape of the problem:

> The quality rule CER approved was **not enforced on the server at all** for
> `fresh` and `recovered`. `_validar_calidad` returned on its first line for
> any level other than `degraded_cached`, and `fresh_max_accuracy_m` was
> declared in the platform policy and used nowhere.

Because `for_trip_waypoints()` does not filter by level or accuracy, any client
that posted `recovered` with 2 km of error — or with no accuracy at all —
obtained an official mileage waypoint. The client-side check CER saw in Report
004 is user experience, not a control: the bundle and the cookie belong to the
browser.

So the fix moved to where the gate belongs. The client was hardened too, and
the rule is now written **once** instead of three times.

A second finding is worth CER's attention because it affects a screen CER
already has:

> `setLocationPolicy` was exported and **called by nobody**. The
> `route_location` policy — editable from the platform panel — had no effect on
> the device. An administrator lowering `fresh_max_accuracy_m` or shortening
> `recovery_window_seconds` saw the screen save the change while the phone kept
> using the values compiled into the bundle.

That one was found by executing the G3/G4/G6/G7 browser tests that Report 004
left `NOT RUN`.

Those four tests failed — and it is worth being exact about why, because an
earlier draft of this report got it wrong. **They failed for a harness reason,
not a product one.** The product behaviour was correct throughout; what was
broken was a fixture that could never have worked. §2's F-H has the measurement
and the three attempts it took to establish it.

**Proposed status is in §14.** One acceptance criterion is still missing its
evidence, and it is named.

---

## 2. Changes Since Report 004

| File | What changed and why |
|---|---|
`app/routers_api/location/service.py` | `_validar_calidad` now enforces the configured threshold for **all three** levels and rejects unknown accuracy. It previously validated only `degraded_cached`. |
`app/routers_api/location/router.py` | New `GET /api/location/policy`: the thresholds the client must apply. Same capability as capture (`route.worksession.execute`). |
`app/routers_api/location/schemas.py` | `LocationPolicyRead`, six fields. |
`app/components/react/shared/lib/location/location.ts` | The quality rule in one place (`precisionAceptable`), unknown accuracy no longer acceptable in any stage, truthful rejection reasons, the policy actually loaded from the server with a bounded timeout, and a per-send expiry derived from that policy. |
`app/components/react/shared/lib/offlineQueue/offlineQueue.ts` | Queue entries carry `expiresAt`. |
`app/components/react/shared/lib/offlineQueue/sync.ts` | `haCaducado` bounds the retry. Also corrects a comment of mine that claimed a limit which did not exist. |
`app/components/react/pages/RouteMyRoutePage/ui/RouteMyRoutePage.tsx` | The odometer task is now marked on the **Start Trip** path too, and the mark is written under the same key it is read from. |

### Findings discovered while closing this delta

All classified. The mechanism is confirmed for every one of them; where the
field impact depends on circumstances, that is said.

| # | Finding | Cause |
|---|---|---|
**F-A** | `fresh` and `recovered` had no server-side accuracy validation; `fresh_max_accuracy_m` was declared and unused. | `CONFIRMED` |
**F-B** | Unknown accuracy was treated as satisfying the threshold, in all three client stages **and** on the server for `degraded_cached`. | `CONFIRMED` |
**F-C** | `setLocationPolicy` was never called: the company's location policy never reached the device. | `CONFIRMED` |
**F-D** | `salirDeViaje` opened the capture without marking the task, so arriving at the reading through **Start Trip** — the normal path — lost it if the page died before the photo was uploaded. The same field finding through the other door. | `CONFIRMED` |
**F-E** | No retry bound existed anywhere in either queue: `attempts` was written and never read. My own comment in Report 004's change asserted that the retry "runs out against the queue's limit". That limit did not exist. | `CONFIRMED` — my error |
**F-F** | The odometer mark was written with `view.session.id` and read with `ultimaJornada.current?.id`. Equal today; the day they diverge the mark is stored under a key nobody consults and the task is lost silently. | `CONFIRMED` |
**F-G** | My own first version of the policy load awaited `$api.get` with **no timeout** — `$api` sets none — on the capture critical path, before stage 1. A stalled request would have hung capture indefinitely, which §12 forbids. Found by the suite hanging, fixed with a bounded timeout. | `CONFIRMED` — my error |
**F-H** | The `ventana_corta` test fixture **never worked and could not work**. `app/main.py` returns from its startup event *before* `platform_config.refresh()` when `settings.is_testing`, so the e2e `uvicorn` process never loads platform configuration: `policy()` always returns the factory defaults, and nothing listens for its `NOTIFY` either. | `CONFIRMED` |

### F-H is the reason G3/G4/G6/G7 failed, and the product was never at fault

This matters for how CER reads Report 004's `NOT RUN`, so it is worth being
precise.

Those four tests are the only ones of the ten that need the recovery window to
**exhaust**. The other six end with an accepted point and never wait for it.
With the fixture silently ineffective, the window in the browser stayed at its
180 s default while the tests waited 15 s — so they failed, and the failure
looked exactly like "the staged model does not resolve into a truthful Missing".

Measured, by extending the wait to 200 s on an instrumented run:

```
[diag] t=15s  missing=[]
[diag] t=45s  missing=[]
[diag] t=90s  missing=[]
[diag] t=150s missing=[]
[diag] t=200s missing=[('recovery_accuracy_rejected', {'accuracy_m': '5000.00'})]

POST /api/location/missing status=201
```

The behaviour was correct all along: the specific reason, the rejected
accuracy, no coordinates. **AC-4 was never broken — the harness was.**

The cause took three attempts to pin down, and the first two were wrong:

1. I suspected the geolocation stub hanging on a mismatched stage. Eliminated
   by reading the stub, which answers such a call with `code: 3`.
2. I suspected `seeded` wiping the fixture's row — `platform_policy` **is** in
   `TABLES_IN_DELETE_ORDER` — and made the fixture depend on `seeded` so it
   would run after the wipe. **That changed nothing**, and the three tests
   failed again identically.
3. Then I stopped guessing and made the harness report what the server actually
   serves. It serves the defaults:

```
AssertionError: la ventana acortada no llegó al navegador: el servidor sirvió
{... 'recovery_window_seconds': 180, 'sweeper_grace_seconds': 120}
assert 180 == 7
```

The reason is `app/main.py`:

```python
@app.on_event("startup")
async def _platform_config_startup() -> None:
    ...
    if settings.is_testing:
        return
    await platform_config.refresh()
```

In TEST mode the e2e server never loads platform configuration at all, and
never starts the `NOTIFY` listener the fixture was signalling. That is
**deliberate** — `_platform_config_vacia` isolates platform config per test for
the same reason — so what was wrong was the fixture, not the server.

**Resolution.** The fixture is deleted rather than repaired: it could not work
by design. The wait is now derived from the window the server actually serves,
read through the browser. That has no silent-failure mode — if configuration
ever does reach the e2e server, the wait adjusts itself. The cost is that the
four exhaustion tests take about 3.5 minutes each instead of 15 seconds.

**A limitation this exposes, worth recording:** in TEST mode **no platform
policy reaches the e2e server**. Any future browser test that needs a
non-default company policy cannot obtain one by writing to `platform_policy`.
That is not a defect of this delta and nothing here depends on changing it, but
the next person to try will lose the same afternoon I did.

One more reusable note: the browser tests captured **no** page errors or console
output, so a failure could not be told apart from "the rule rejected it" versus
"the code broke halfway". Error capture is now part of `_movil`.

### A scope decision CER should confirm

CER scoped §2.1 and FR-01 to **Recovery**. The delta changes **all three**
stages and the server. The reason is not thoroughness for its own sake:

Unknown accuracy was accepted at **stage 1**. A point with no measurable
accuracy therefore became authoritative `fresh` evidence immediately and never
reached Recovery. Fixing Recovery alone would have produced a change that could
almost never fire while the real path stayed open, and FR-02 forbids the
outcome regardless of which stage produced it.

**The approved threshold itself is unchanged**: 100 m, the Fresh policy, now
read from the company's configuration instead of a constant in the bundle. What
changed is that "unknown" stopped counting as "within threshold".

---

## 3. Recovered Quality — Final Behavior

A recovered candidate becomes authoritative only when its accuracy is a number
and that number is at or below the configured Fresh threshold. The threshold is
shared with Fresh deliberately: a point that took longer to obtain cannot be
allowed to be worse.

Two gates, and only the second is a control:

- **Client** — `precisionAceptable(precision, politica.freshMaxAccuracyM)`.
  Prevents spending a send the server will refuse.
- **Server** — `_validar_calidad`. Refuses with 422 and writes no row. This is
  the gate, because `for_trip_waypoints()` does not filter again.

A rejected candidate does not close the recovery window. While time remains the
client retries, because GPS usually improves as it fixes satellites. What closes
the window is the clock.

---

## 4. Unknown Accuracy — Final Behavior

Unknown accuracy is **not** acceptable accuracy, in any stage, on either side.

The client records which of the two happened rather than inventing the missing
number: `accuracy unknown: cannot be evaluated` instead of
`accuracy 0m above threshold`. That distinction survives into the immutable
`attempts` record of the Missing fact.

**Terminal reason.** A candidate rejected for unknown accuracy resolves as
`recovery_accuracy_rejected`, the reason added in the previous delta. The
statement is true — a candidate was obtained and discarded on accuracy grounds
— and which of the two cases it was is in `attempts`.

Development chose this over adding a seventh reason code, because a second
enum value meaning almost the same thing would need a migration and would make
every consumer decide which of the two to treat as which. **If CER prefers the
distinction to be explicit in `reason_code`, say so**: it is a migration plus
one branch, roughly 1.5 agent-hours, and nothing else depends on it.

No coordinates are stored for a rejected candidate, and no `rejected_accuracy_m`
is sent when there is no number to send — a `0` there would be fabricated.

---

## 5. Silent Evidence-Loss Finding — Final Resolution

CER asked Development to evaluate this against the whole context rather than
apply a status-code recipe. Doing that found that the previous delta's fix was
**half a fix**.

**What is genuinely transient.** The endpoint returns 409 in two situations that
look identical from the device: evidence arriving before its work session is
`ACTIVE` (a race, which resolves itself) and the End Work recovery window having
closed (a verdict, which does not). 404 is also transient here, because the
operational action that creates the subject is in the other queue and will
arrive. From the client there is no way to tell the two 409s apart.

**What was missing.** Treating them as transient without a bound leaves the
entry retrying forever. Report 004's comment claimed the retry "runs out
against the queue's limit" — **there was no limit**. `attempts` was incremented
and never read by anything. That is F-E, and it is the condition FR-03 forbids:
an indefinite processing state.

**The bound chosen, and why it is not a magic number.** Each queued send now
carries `expiresAt`, computed at capture time as the company's
`recovery_window_seconds` plus `sweeper_grace_seconds` — the same two values the
server uses to decide it will close the fact itself. The client therefore stops
insisting exactly when the server stops being able to accept it. A retry
counter would have been a number invented here; this one is the server's own
rule, read from configuration.

Entries saved before this existed have no `expiresAt` and keep the previous
behaviour, so nothing in flight changes meaning.

**Why dropping is safe.** It is not a discard. The event with neither fix nor
Missing is closed by `sweep_unreported_windows` with `no_client_report` — the
observable fact, not a guess about the device. That is the third recovery path
the architecture already had, and it is now tested (it was not).

**What is lost on expiry, stated plainly.** The client's specific reason — for
instance `recovery_accuracy_rejected` — is more informative than the sweep's
`no_client_report`, and expiry forfeits it. Development accepted that because
the alternative is an unbounded queue, and because if the server has already
closed the window the sweep has very likely written the fact already: insisting
would not recover the reason, only repeat the rejection.

---

## 6. Odometer START — Final Behavior

The task survives both doors into it and both ways of losing the page.

| Requirement (FR-04) | Behaviour |
|---|---|
Returning from camera returns to the task | The capture stays open; resolution is what closes it. |
Page recreation restores the task | Three independent sources, in order of authority: a persisted photo (domain truth), the session-scoped intent mark, and live React state. |
A persisted photo is available for confirmation | `tieneFoto` derives from `evidence.captured_at`. The button reads **Retake photo** and the reading field is present. |
A photo that was never persisted is not pretended | Same source, inverted: the button reads **Take photo** and there is no reading field. |
Start Trip stays protected | Pressing it with the reading unresolved leads to the capture and **creates no trip**. |
No OCR suggestion still allows manual confirmation | `ocr_detected_reading` stays null; the reading is entered by hand and the evidence remains photographic. |

**F-D is the substantive change here.** The mark was only written when entering
through the workbench banner. Entering through Start Trip — the normal path —
left the task unmarked, so a page death before the upload lost it. That is
fixed, and the mark is now written under the same key it is read from (F-F).

Resolution forgets the mark. Cancelling forgets it too: cancelling is the
supervisor's decision and reopening what they just closed would be ignoring
them.

---

## 7. Odometer END — Final Behavior

| Requirement (FR-05) | Behaviour |
|---|---|
Camera return restores the END task | The END phase is derived from the evidence, not from volatile state. |
Page recreation restores it | `reconcile()` reads `evidencia.end`; an unresolved end reading outranks any other phase. |
Terminal state stays truthful | `ended_at` is already written and this only decides which screen shows. |
Restoring END does not reopen the session | Verified against the database: same session id, no new trip. |
Photo persistence represented honestly | Same `captured_at` source as START. |
Valid photo without OCR does not force an exception | The reading is confirmed manually; the existing no-photo exception path is untouched. |

---

## 8. Tests / Evidence

### Added

| Test | Covers |
|---|---|
`test_g4_a_grossly_inaccurate_point_is_not_authoritative` (×2 levels) | G4, server side |
`test_g3_the_threshold_is_the_threshold` (×3: 100, 100.01, 99.99) | G3 boundary, including `<` vs `<=` |
`test_g12_unknown_accuracy_is_not_acceptable_accuracy` (×3 levels) | G12 |
`test_g12_a_rejected_point_never_becomes_a_trip_waypoint` | FR-02 at the end of the path, through `for_trip_waypoints()` |
`test_g12_the_good_point_still_enters` | that the hardening did not close the good path |
`test_the_client_can_read_the_capture_policy` | F-C |
`test_the_capture_policy_needs_a_session` | the new endpoint is not public surface |
`test_an_event_the_client_never_reported_is_closed_by_the_sweep` | §8.3 — no limbo |
`test_the_sweep_leaves_alone_what_already_has_an_answer` | that the sweep does not overwrite a true answer |
`test_the_start_reading_task_survives_the_camera_and_a_recreated_tab` | O1, O2, O3, O4, O5, FR-04 |
`test_the_end_reading_task_survives_a_recreated_tab_without_reopening_the_day` | O6, O7, O8, O9, FR-05 |

Each pair deliberately includes its negative half. `test_g12_the_good_point_
still_enters` exists because the other G12 tests would pass just as well against
a server that refused everything, which is the easiest mistake to make when
adding a check.

### Measured

| Batch | Result |
|---|---|
RTE06 integration batch (6 files) | **101 passed, 1 skipped, exit 0** |
**Full integration tier** | **735 passed, 15 skipped, exit 0**, 10 min 33 s |
Unit / wiring tier | **132 passed, exit 0**, 14.4 s |
`test_route_location_evidence.py` quality subset | **10 passed** |
Policy endpoint | **2 passed** |
Sweep | **2 passed** |
`npm run check` (tsc + eslint) | **0 errors** |
`npm run build:prod` | **exit 0**, 2 pre-existing bundle-size warnings |
Browser — G1–G11 | **10 passed, exit 0**, 13 min 47 s |
Browser — odometer lifecycle O1–O9 | **2 passed, exit 0**, 31.5 s |
Browser — G12 | **1 passed, exit 0**, 3 min 13 s |

G coverage maps as follows, so CER can check nothing was dropped: G1–G4 in
`test_umbral_de_recuperacion` (parametrized 50, 100, 101, 2000), G5 in
`test_g5_candidato_malo_y_luego_bueno`, **G6, G7 and G8** together in
`test_g6_g7_todos_malos_dan_missing_con_su_motivo`, G9 in
`test_g9_fresh_sigue_aceptando_dentro_del_umbral` (×2), G10 in
`test_g10_cached_sigue_exigiendo_las_dos_cosas`, G11 in
`test_g11_un_candidato_rechazado_no_es_waypoint`.

**The five scenarios Report 004 left `NOT RUN` — G3, G4, G6, G7 and G8 — are
now executed and green.**

### How page recreation is simulated, and its limit

With `page.reload()`. It destroys React state and remounts against the same
`sessionStorage` and the same server, which is what a recreated tab gets. It
does **not** reproduce Android killing the browser process. That still needs
real hardware and is in §12.

---

## 9. Regression

| Area | Result |
|---|---|
Location evidence, exact correlation, Missing immutability | included in the 101-passed batch |
Mileage engine | included — also closes the item Report 004 left unverified |
Odometer END / business rules | included |
Recovery-accuracy migration | included |
Typecheck, lint | **0 errors** |
Production build | **exit 0** |
Work Sessions, Trips, Activities, Change Plan, tenant isolation, routing | **included: the whole integration tier ran, 735 passed / 15 skipped / exit 0** |
Unit and wiring nets (page wiring, navigation, permission catalog, public surface) | **132 passed, exit 0** |

Nothing was weakened, skipped, xfailed or removed. No existing test asserted
that unknown accuracy is accepted, so the server hardening broke no assertion —
verified by searching for `precision=None` and for accuracies above the
threshold before changing anything.

---

## 10. Security / Privacy / Tenant Isolation

- **The gate moved to the server.** This is the security substance of the
  delta: the rule CER approved is now enforced where the client cannot reach it.
- **Rejected candidates keep no coordinates.** Only age and accuracy are
  recorded, and only when they exist.
- **No fabricated values.** No `accuracy_m` is sent when there is none.
- **The new endpoint** requires an authenticated session and a resolved company,
  uses the same capability as capture, adds no new capability, and is not in the
  public surface — asserted by a test, and `tests/test_public_surface.py` is
  unchanged.
- **The intent mark is `sessionStorage`**, per-tab and not domain state. It is
  interface position, not evidence; it never decides whether evidence exists.
- **Append-only tables untouched.** The sweep adds rows; nothing updates or
  deletes `missing_location_event`.
- **No new migration.** The delta needed none.

---

## 11. Expected → Implemented → Evidence → Gap

| AC | Expected | Implemented | Evidence | Gap |
|---|---|---|---|---|
1 | Unknown/unverifiable Recovery accuracy cannot become authoritative | Yes, all three stages + server | `test_g12_…` ×3 on the server (422, no row) **and** G12 in the browser, **passed**: the scripted provider returns `accuracy: null` in all three stages, no fix is written, and the fact resolves as `recovery_accuracy_rejected` with **no** `accuracy_m` — no number is invented | — |
2 | Recovered acceptable evidence satisfies the approved rule | Yes, threshold from company policy | `test_g3_…` ×3 | — |
3 | A grossly inaccurate point cannot become official mileage | Yes | `test_g4_…` ×2, `…never_becomes_a_trip_waypoint` | — |
4 | Invalid/unverifiable Recovery resolves truthfully through the staged model | Yes | `…closed_by_the_sweep` + **browser G6/G7/G8 green**; measured reason `recovery_accuracy_rejected` with the rejected accuracy | — |
5 | Rejected coordinates not fabricated or persisted | Yes | existing privacy tests + `rejected_candidate` shape test | — |
6 | No valid evidence silently lost on a transient condition | Yes | 409 retryable (Report 004) + bound added here; browser G1–G11 green | — |
7 | Final invalid conditions bounded and traceable | Yes, `expiresAt` from server policy | sweep tests green; the client bound itself is **not** exercised end to end | **yes — §13.1** |
8 | START returns/restores to the correct task | Yes, incl. the Start Trip path (F-D) | journey A, **passed** | — |
9 | END returns/restores to the correct task | Yes | journey B, **passed** | — |
10 | Persisted photo restored honestly | Yes | both journeys **passed**; asserted on the button label (`Retake photo`) and on `captured_at` | — |
11 | Non-persisted photo not fabricated | Yes | both journeys **passed**; `Take photo` and `captured_at IS NULL` | — |
12 | Start Trip protected by START odometer | Yes | journey A **passed** + existing RTE04 tests | — |
13 | END restoration never reopens the session | Yes | journey B **passed**: same session id, same trip count | — |
14 | Valid photo + no OCR still allows manual confirmation | Yes | both journeys **passed**; `ocr_detected_reading` null | — |
15 | Existing no-photo exception unchanged | Yes, untouched | `test_odometer_end_work.py` in the 101-passed batch | — |
16 | Productive OCR not introduced | Yes | `ocr_detected_reading` stays null | — |
17 | Location Permission Enforcement not introduced | Yes | nothing added | — |
18 | RTE03–RTE06 regression green | Yes | **735 passed, 15 skipped, exit 0** across the full integration tier, plus 132 in the unit tier | — |
19 | Tenant isolation green | Yes | included in the full tier; `test_public_surface.py` unchanged and green | — |
20 | Migrations/constraints validated | Yes | migration tests in batch; no new migration | — |
21 | Typecheck/lint/build green | Yes | 0 errors, build exit 0 | — |
22 | No PARTIAL/GAP/BLOCKED left | **No** | one item remains: AC-7's client-side bound | **§13.1** |

---

## 12. Targeted Physical Revalidation Checklist for CER

Short on purpose. Only what changed, and only what a desktop browser cannot
prove.

1. **Unknown accuracy on a real device.** Where a device reports a position
   without usable accuracy, confirm the trip ends with a truthful Missing and no
   waypoint — not a point.
2. **Android kills the tab with the camera open, START.** Open the reading from
   **Start Trip** (not the banner — that is the path that was broken), take the
   photo, let Android recreate the tab. The task must come back.
3. **The same, before the photo uploads.** Open the camera, kill the app before
   it returns. The task must come back and must say **Take photo**, not Retake.
4. **The same for END.** The day must not reopen.
5. **A company threshold that is not the default.** Lower
   `fresh_max_accuracy_m` in the platform panel and confirm the phone now
   respects it. Before this delta it did not — that is F-C, and it is the one
   finding whose fix is only observable on a device.
6. **Airplane mode across a reading.** Confirm nothing ends as neither evidence
   nor Missing.

---

## 13. Remaining Items

Stated as they are. Absent evidence is not a pass.

1. **The client-side expiry bound (AC-7) is not exercised end to end.** This is
   the one real gap. `expiresAt` is computed and `haCaducado` consumes it, and
   the server half — the sweep that closes an unreported event truthfully — is
   tested. What is missing is a browser test that drives the real IndexedDB
   queue past `expiresAt` and asserts the entry is dropped rather than retried
   forever. `tests/e2e/test_rte06_offline_durability_browser.py` already has
   the store-reading helper that needs. Estimated **1.5 agent-hours** including
   the browser margin.

2. **A harness limitation, recorded so the next person does not lose the time I
   did.** In TEST mode **no platform policy reaches the e2e server** — see
   F-H. A browser test cannot be given a non-default company policy by writing
   to `platform_policy`. Nothing in this delta depends on changing that, and
   the recovery tests now calibrate themselves against whatever the server
   serves, which costs the four exhaustion scenarios about 3.5 minutes each.

3. **Open question for CER, not a defect.** Whether unknown accuracy should
   have its own `reason_code` instead of sharing `recovery_accuracy_rejected`
   (§4). Development's recommendation is to keep it shared; the detail lives in
   the immutable `attempts` record either way.

### Estimate to close the remaining items

| Task | State | Volume | Complexity | Agent-hours |
|---|---|---|---|---|
Client expiry bound, browser test | `NOT STARTED` | ~60 LoC | browser | 1.0 (+50 % = **1.5**) |

Everything else that this report listed as pending has since been executed and
is reported with its real result in §8 and §9.

---

## 14. Proposed Status

```text
IMPLEMENTATION COMPLETE / PENDING VALIDATION
```

**Not** `IMPLEMENTATION COMPLETE / READY FOR CER PHYSICAL REVALIDATION`, and
not `RTE06 CERTIFIED`.

Twenty-one of the twenty-two acceptance criteria are met with named evidence.
All the browser evidence CER asked for is green: G1–G12 in a real browser, both
odometer lifecycle journeys, and the five scenarios Report 004 left `NOT RUN`.
The full suite is green too — 735 integration plus 132 unit, zero failures,
typecheck, lint and production build clean.

**AC-22 is the one that fails, because of AC-7.** The client-side retry bound
is implemented and reasoned, and the server half of it — the sweep that closes
an unreported event truthfully — is tested. But the bound itself is not
exercised end to end: no test drives the real IndexedDB queue past `expiresAt`
to prove the entry is dropped instead of retried forever. That is the condition
FR-03 cares most about, so Development will not call it validated from code
presence. §13.1 names it and estimates 1.5 agent-hours.

CER may reasonably decide that gap is small enough to revalidate physically in
parallel; that is CER's call, not Development's, and the physical checklist in
§12 is ready either way.
