# CER Route — Geolocation Technical Context

**Source application:** CER Technologies main site + **Lead Hub** sales module
(`certechss_mainsite`)
**Prepared:** 2026-09-21
**Purpose:** technical context for the future CER Route project. **This is not a
design for CER Route and not a recommendation to reuse this stack.**

---

## How to read this document

Everything below was read directly from the repository on 2026-09-21. The labels
are used strictly:

| Label | Meaning |
|---|---|
| **Implemented** | Exists in the code and was located file by file |
| **Not implemented** | Searched for and **absent** |
| **Not verified** | Cannot be established from the repository — usually because it is field experience that was never instrumented or recorded |
| **Recommendation** | An opinion, clearly separated from what exists |

**One honest warning about scope.** This repository has four coarse commits and
no issue tracker, changelog or telemetry. **The field experience Rodrigo asks
about in §5, §17 and §18 — observed accuracy, browser differences, problems
encountered and approaches abandoned — is not recorded anywhere.** What the code
*does* show is which failure modes the developer anticipated, because the
handling for them is written into it. Those are reported as *anticipated*, never
as *encountered*. Presenting them as lived incidents would be the exact thing
this brief asks not to do.

---

## 1. Existing Application Overview

**Implemented.**

| | |
|---|---|
| Type | Server-rendered multi-tenant SaaS web application |
| Platform | ASP.NET **Web Forms** (`.aspx` + code-behind), .NET Framework **4.7.2** |
| Frontend | Server-rendered HTML with `__doPostBack`; plain JavaScript. **No SPA framework, no frontend router, no build step** |
| Backend | C#, Entity Framework **6.5.1** |
| Database | **SQL Server**, hosted (`site4now.net`) |
| Maps library | **Leaflet 1.9.4** loaded from the unpkg CDN |
| PWA | **Not implemented** — no manifest, no service worker |
| Native / hybrid app | **Not implemented** |
| Tenancy | Every query is scoped by `TenantId`; roles are Sales Rep / Admin / Super Admin |
| Devices | Field sales reps on mobile browsers, desk users on desktop. **Which devices and browsers specifically: Not verified** |

**Why it uses geolocation.** Two separate and unrelated purposes:

1. **Visit check-in / check-out.** A sales rep in the field records arriving at
   and leaving a lead, and the position is stamped on the visit record.
2. **Weekly route planning.** Each rep stores a *starting* coordinate on their
   profile, which the planner uses as the origin when ordering the week's
   visits.

The first is the one that resembles CER Route.

---

## 2. Geolocation Technologies Used

**Implemented.**

| Component | Technology / Provider | Purpose | Frontend / Backend | Current Use |
|---|---|---|---|---|
| Position capture | **Browser Geolocation API** — `navigator.geolocation.getCurrentPosition` | Capture rep position at check-in/out and on the profile page | Frontend | Active |
| Continuous tracking | `watchPosition` | — | — | **Not implemented** (zero occurrences) |
| Forward geocoding | **TomTom Search API v2** — `/search/2/geocode` | Address → coordinates for leads | Backend | Active (requires `TomTom.ApiKey`) |
| Reverse geocoding | **TomTom Search API v2** — `/search/2/reverseGeocode` | Coordinates → address | Backend | **Defined but never called** — §11 |
| Routing | **TomTom Routing API v1** — `calculateRoute`, `matrix/sync` | Travel time and distance between stops, with live traffic | Backend | Active |
| Distance fallback | **Haversine**, implemented in-house | Straight-line km when TomTom is unavailable or unconfigured | Backend | Active |
| Area geocoding | **Nominatim** (OpenStreetMap) | City/state → OSM area id | Backend | Active (no key) |
| Entity discovery | **Overpass API** (OpenStreetMap) | Find businesses by category inside an area or radius | Backend | Active (no key) |
| Map tiles | **OpenStreetMap** raster tiles | Map background | Frontend | Active |
| Map rendering | **Leaflet 1.9.4** (unpkg CDN) | Markers, map interaction | Frontend | Active |
| Marker icons | `raw.githubusercontent.com` (leaflet-color-markers) | Green check-in / red check-out pins | Frontend | Active |
| Contact enrichment | **Google Places API** | Enrich imported leads | Backend | Active when `Google.PlacesEnabled` |
| Geofencing | — | — | — | **Not implemented** |

**Acquisition and visualization use different providers**, and the separation is
clean: positions come from the device and from TomTom; the map that draws them is
Leaflet over OSM tiles. Neither depends on the other.

Configuration keys involved (names only): `TomTom.ApiKey`, `TomTom.RateLimit`,
`Google.PlacesApiKey`, `Google.PlacesEnabled`, `Google.RateLimitPerMinute`,
`Route.DefaultSpeedKmh`.

---

## 3. Location Capture Model

**Implemented — one-shot, user-initiated, foreground only.**

### When and who

| Trigger | Page | What it does |
|---|---|---|
| **Check In** button | `Admin/MyWork/MyVisits.aspx` | Captures position, writes it into hidden fields, then fires the postback |
| **Check In** from a planned item | same | Same, per planned visit |
| **Check Out** button | same | Same, on the way out |
| **Detect location** button | `Admin/Profile.aspx` | Fills the rep's starting coordinates, which the rep must then **save** |

**Nothing captures position automatically.** There is no timer, no interval and
no background job on the client. A position exists only because a person pressed
a button.

### Parameters actually used

```js
// MyVisits.aspx — check-in, planned check-in and check-out
navigator.geolocation.getCurrentPosition(ok, fail,
    { enableHighAccuracy: true, timeout: 10000 });

// Profile.aspx — starting coordinates
navigator.geolocation.getCurrentPosition(ok, fail,
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
```

`maximumAge` is omitted at the three visit call sites. The Geolocation
specification defaults it to `0`, so a cached position is not accepted there
either — but the intent is explicit in one file and implicit in the other, and
the timeouts differ (10 s vs 15 s) for no reason the code explains.

### What is kept, and what is thrown away

| `GeolocationCoordinates` field | Read? | Stored? |
|---|---|---|
| `latitude` | Yes | Yes — `decimal` |
| `longitude` | Yes | Yes — `decimal` |
| `accuracy` | **No** | **No** |
| `altitude`, `altitudeAccuracy` | No | No |
| `heading`, `speed` | No | No |
| `position.timestamp` (device clock) | **No** | **No** |

**This is the single most consequential fact in this document.** The application
requests high accuracy and then **never looks at the accuracy it got**. There is
no threshold, no "position too imprecise to use" path, and no way to answer
afterwards how good any stored position was — because the number was never kept.

Timestamps are the server's: `CheckInAt` and `CheckOutAt` are set to
`DateTime.UtcNow` inside the service, not taken from the device. For integrity
that is the right default; it also means the record cannot distinguish "captured
at 10:00, submitted at 10:00" from "captured at 10:00, submitted at 10:40".

### When GPS is unavailable or refused

Both failure paths end the same way, by design:

```js
function () {           // error callback — no error code inspected on MyVisits
    if (confirm('Could not get GPS location. Continue without it?')) {
        __doPostBack(...);   // the visit is recorded with NULL coordinates
    }
}
```

**Location is optional.** A rep who denies permission, has Location Services off,
or times out can still check in — the visit is saved with `NULL` latitude and
longitude. That is a deliberate product decision, and it is why the columns are
nullable.

`Profile.aspx` is the only place that inspects the error code:

| `err.code` | Message shown |
|---|---|
| `1` PERMISSION_DENIED | "Permission denied — please allow location access in your browser." |
| `2` POSITION_UNAVAILABLE | "Position unavailable." |
| `3` TIMEOUT | "Request timed out." |

`MyVisits.aspx` discards the error object entirely and shows one generic prompt.

---

## 4. Permissions and Browser Behavior

**Partially implemented; the observational part is Not verified.**

What the code does:

* it feature-detects (`if (!navigator.geolocation)`) and offers to continue
  without GPS;
* it distinguishes denied / unavailable / timeout **only on the profile page**;
* it never queries the **Permissions API** (`navigator.permissions.query`), so it
  cannot tell "not asked yet" from "blocked earlier". A rep who blocked the
  prompt once sees the same generic failure forever, with no guidance.

**HTTPS.** The Geolocation API requires a secure context in every current
browser. The application does not enforce that itself — there is no HTTPS
redirect rule in `Web.config`; what it does set is `httpCookies requireSSL="true"`,
which is about cookies, not about the API. In practice the hosted deployment is
served over HTTPS. **Whether any environment was ever served over plain HTTP, and
what happened if so: Not verified.**

**Differences between Chrome Android, Chrome Desktop, Safari iOS, Safari macOS
and Edge: Not verified.** Nothing in the repository records browser-specific
behaviour, and there is no browser-conditional code anywhere in the geolocation
paths.

**"Allow once" versus "While using", and permission revoked after being granted:
Not verified**, and worth stating plainly — the application would simply take the
"continue without GPS" branch, and nothing would flag that the visit lost its
position.

---

## 5. Accuracy

**Not verified — and structurally unverifiable in this application.**

`accuracy` is never read, so:

* typical accuracy observed: **Not verified**;
* indoor / outdoor, parking structures, industrial areas: **Not verified**;
* GPS vs Wi-Fi vs cellular differences: **Not verified**;
* position jumps, stale positions, implausible coordinates: **Not verified**;
* accuracy threshold: **Not implemented** — there is none.

The only coordinate sanity check anywhere in the repository is in
`GoogleSearchScraper.cs`, which rejects scraped coordinates outside a North
America bounding box (`lat 18..72`, `lon -180..-50`). **It does not apply to
positions captured from the browser.**

> **Recommendation for CER Route.** Store `accuracy` with every position from day
> one, even if no rule uses it yet. It costs one column and it is the difference
> between being able to answer "was this visit really at the site?" and not being
> able to.

---

## 6. Mobile Browser Limitations

**Implemented behaviour: foreground, one-shot, user-initiated.**

Because there is no `watchPosition`, no service worker and no PWA, most of the
questions in this section have the same answer — the application never attempts
the thing that would be limited:

| Situation | Behaviour |
|---|---|
| App in foreground, user presses the button | Works |
| App in background / screen locked | **Nothing happens** — nothing is scheduled |
| Tab switched, browser suspended | **Nothing happens** |
| PWA installed | **Not applicable** — not a PWA |
| Browser closed | **Nothing happens** |
| Battery saver, JS throttling | Does not apply to a one-shot capture the user just triggered |

**What this application can guarantee:** that a position was obtained by the
browser at the moment a rep pressed a button, if the rep allowed it.

**What it cannot guarantee:** anything about where the rep was at any other
moment. It is a *check-in stamp*, not tracking — and for its own use case that is
sufficient.

> This is the gap CER Route needs to face honestly: "seguimiento de actividades
> en campo" as continuous tracking is a **different problem** from what this
> application solves, and nothing here demonstrates it can be done from a mobile
> browser. See §21 and §22.

---

## 7. Continuous Tracking

**Not implemented.**

No `watchPosition`, no polling, no background sync, no temporary local buffer.
Battery and data consumption figures: **Not applicable** — there is nothing
running to measure.

---

## 8. Geofencing

`Not currently implemented.`

There is no zone model, no radius, no polygon and — worth noting separately —
**no proximity check between the check-in position and the lead's known
coordinates**. `HaversineDistanceKm` exists and is used by the route planner,
but it is never applied to validate that a check-in happened near the place it
claims.

---

## 9. Distance and Routing

**Implemented, backend, for planning — not for measuring what a rep did.**

`Helpers/LeadHub/RouteOptimizationService.cs` (725 lines):

* **TomTom Routing API v1**, `travelMode=car`, `traffic=true`, for travel time
  and distance between two points;
* a **matrix** endpoint for many-to-many distances;
* **nearest-neighbour heuristic** from the rep's starting coordinate to order a
  day's visits;
* **Haversine fallback** (`R = 6371 km`) when the API key is absent or the call
  fails, combined with `Route.DefaultSpeedKmh` to estimate a duration.

The fallback is the interesting part: **the feature degrades instead of
breaking.** No key, no network, or a bad response, and the planner still produces
an ordering — a straight-line one, which is worse but usable.

**Distance actually travelled, mileage, road matching, ETA against real
progress: Not implemented.** Nothing measures the rep's real path, because no
path is captured.

---

## 10. Maps and Visualization

**Implemented, frontend.**

| | |
|---|---|
| Library | Leaflet 1.9.4, from `unpkg.com`, with SRI hashes on the Default page |
| Tiles | `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`, attributed to OpenStreetMap contributors |
| Pages | `VisitMap.aspx`, `MasterRepository.aspx`, `TenantUniverse.aspx`, `MyWork/Default.aspx` |
| Markers | Green = check-in, red = check-out (icons fetched from `raw.githubusercontent.com`) |
| Default view | Miami area, `[25.7617, -80.1918]`, zoom 10 |
| Clustering, polygons, drawn routes | **Not implemented** |

**Known limits/costs:** OSM tile usage is subject to the OSMF tile usage policy,
which is a courtesy service and not a contract. Two third-party origins are
loaded at runtime — `unpkg.com` for the library and `raw.githubusercontent.com`
for the marker images — and if either is unreachable the map degrades or loses
its pins. **Neither has a local fallback.**

---

## 11. Reverse Geocoding

**Implemented as a provider, and never used.**

`TomTomGeoProvider.ReverseGeocode(lat, lng)` exists and is complete.
`QueueTaskProcessor` even declares a task type constant, `"ReverseGeocode"`.

**There is not one caller.** Verified: zero references to
`TomTomGeoProvider.ReverseGeocode`, and the task-type constant is referenced only
by its own declaration.

The consequence is visible in the data model: `VisitSession` has
`CheckInAddress` and `CheckOutAddress` (`nvarchar(500)`), the service signature
accepts an address, and **every call site passes `null`**:

```csharp
VisitService.CheckIn(CurrentTenantId, CurrentUserId, leadId, null, lat, lng, null);
//                                                                        ^^^^ address
```

So the visit list shows the address of the *lead*, never the address the rep was
actually standing at. Forward geocoding of leads, by contrast, is wired and used.

Caching of geocoding results: **Not implemented** as a cache; results are
persisted onto the lead record, which achieves the same thing for that use.

---

## 12. Backend Processing

**Implemented.**

```
Mobile browser
  → getCurrentPosition (user-initiated)
  → hidden fields on the form
  → __doPostBack
  → MyVisits.aspx.cs        identity and tenant from the authenticated session
  → ParseDecimal            invariant-culture parse; unparseable → null
  → VisitService.CheckIn/CheckOut
  → Entity Framework → SQL Server (VisitSessions)
  → AuditService.Log(..., newValues: { tenantLeadLinkId, weeklyPlanItemId, lat, lng })
```

| Aspect | How |
|---|---|
| Endpoint | No REST endpoint — a Web Forms postback to the same page |
| Data transmitted | `latitude`, `longitude` as strings in hidden fields, plus the form's own fields |
| Authentication | `LeadHubBasePage` redirects unauthenticated users; `AuthHelper.GetCurrentTenantId()` |
| Authorization | Role gates for Admin / Super Admin areas; a rep only sees their own work |
| User association | `RepUserId` from the session — **never from the request body** |
| Tenant association | `TenantId` from the session; check-out re-queries with `Id && TenantId && RepUserId` |
| Device timestamp | **Not transmitted and not stored** |
| Server timestamp | `DateTime.UtcNow` at check-in and at check-out; `DurationMinutes` derived from the two |
| Audit | Coordinates are written into the audit trail as well as the record |

`ParseDecimal` uses `CultureInfo.InvariantCulture`, which is the correct choice
and a classic source of bugs when it is omitted — a browser in a comma-decimal
locale sends `41,40338`, and a culture-sensitive parse on a US server silently
produces a wrong number or a null.

---

## 13. Data Model

**Implemented.** Only the geolocation-relevant parts:

### `VisitSessions`

| Column | Type | Persisted | Note |
|---|---|---|---|
| `Id`, `TenantId`, `RepUserId` | int | Permanent | Ownership and scope |
| `TenantLeadLinkId`, `WeeklyPlanItemId` | int? | Permanent | What the visit was for |
| `CheckInAt`, `CheckOutAt` | datetime? | Permanent | **Server UTC** |
| `CheckInLat`, `CheckInLng` | decimal? | Permanent | Nullable by design — §3 |
| `CheckOutLat`, `CheckOutLng` | decimal? | Permanent | Same |
| `CheckInAddress`, `CheckOutAddress` | nvarchar(500) | Permanent | **Always `NULL`** — §11 |
| `DurationMinutes` | int? | Permanent | Derived at check-out |
| `Outcome`, `OutcomeNotes`, `NextStep`, `FollowUpRequired` | — | Permanent | Business result |

**No accuracy column. No device column. No source column. No
`server_received_at` distinct from the capture time.**

### Rep profile

`StartLatitude`, `StartLongitude` (decimal?) — the origin for route planning.
`Admin.Master.cs` nags the rep when they are missing or zero, because the planner
cannot order a route without them.

### Transient

Hidden form fields (`hfCheckInLat`, `hfCheckInLng`, `hfCheckOutLat`,
`hfCheckOutLng`) exist only for the duration of the postback.

---

## 14. Offline / Poor Connectivity

**Not implemented, for location.**

No `localStorage`, no `IndexedDB`, no offline queue, no retry and no
synchronisation for captured positions. The capture and the submission are the
same user gesture, so:

| Situation | What happens |
|---|---|
| No Internet | The postback fails. The visit is **not** recorded, and the position is lost with the page |
| Weak signal | Same, or a slow postback |
| GPS works, Internet does not | The position is obtained and then **discarded** — nothing can be saved |
| Internet works, GPS does not | The visit is saved with `NULL` coordinates (§3) |
| External API fails | Only affects planning, never check-in: routing falls back to Haversine (§9) |

There **is** a server-side queue — `QueueTaskProcessor`, with `Pending`/`Failed`
states — but it is for geocoding imported leads in batches, not for field
capture.

> **Recommendation for CER Route.** Of everything in this document, this is the
> gap most likely to hurt a field application. A rep in a warehouse or a rural
> industrial park routinely has GPS and no data. Capturing to a local queue and
> synchronising later is a design decision to take **before** building, not a
> feature to add afterwards.

---

## 15. Security and Integrity

**Partially implemented.**

| Control | State |
|---|---|
| User identity from the authenticated session, never from the request | **Implemented** |
| Tenant scoping on every read and write | **Implemented** |
| Check-out re-verifies id + tenant + rep before mutating | **Implemented** |
| Server-controlled timestamps | **Implemented** |
| Audit trail including coordinates | **Implemented** |
| Coordinate **range** validation (−90..90 / −180..180) | **Not implemented** for browser-supplied positions |
| Plausibility checks (impossible jumps, speed between consecutive points) | **Not implemented** |
| Duplicate-position detection | **Not implemented** |
| GPS spoofing detection | **Not implemented** |

The browser sends whatever is in the hidden field. `ParseDecimal` accepts any
decimal, so a value of `999` is stored as readily as `25.76`. Nothing downstream
rejects it — it would simply draw a marker in an impossible place.

**On spoofing, stated plainly because the brief asks for it:** a web application
**cannot** guarantee that a reported position is real. `navigator.geolocation` is
a browser API, and browser developer tools, device emulators and mock-location
apps on Android can override it without leaving a trace the page can see. Any
claim that a web app "verifies" a rep's location is false. What a web app can do
is make a *false* position **inconvenient and detectable after the fact**:
correlate positions with known site coordinates, record accuracy, look for
impossible travel between consecutive stamps, and keep an audit trail.
**None of those four is implemented here**, but the first three are cheap.

---

## 16. Privacy

**Implemented decisions — few, and mostly implicit.**

| Question | Answer from the code |
|---|---|
| When is location captured? | Only on an explicit user action, at check-in, check-out, and when the rep asks to detect their starting point |
| For how long? | Only at those instants — there is no ongoing capture |
| What is stored? | Latitude and longitude on the visit, plus the rep's starting coordinate on their profile |
| Who can see it? | The rep (their own visits); Admins within the tenant; Super Admins across all tenants — `VisitMap.aspx` sets `tenantFilter = CurrentUserIsSuperAdmin ? 0 : CurrentTenantId` |
| Auditing | Coordinates are written to the audit log on check-in and check-out |
| Retention | **Not implemented** — no purge, no expiry, no anonymisation anywhere |
| Deletion | **Not implemented** — no path deletes a position |

A rep can decline to share location and still do their job (§3). That is a real
privacy property, and it is worth keeping in mind for CER Route, where the
temptation will be to make it mandatory.

---

## 17. Problems Encountered

**This is the section the repository cannot honestly fill.**

There is no issue tracker, no changelog, no code comment describing a geolocation
defect, and the git history is four large feature commits. Reporting invented
incidents here would be worse than reporting none.

What *can* be documented is which failure modes the developer **anticipated**,
because the handling exists in the code. These are design responses, not
post-mortems:

| Anticipated failure | Where | How it is handled | Still a limitation? |
|---|---|---|---|
| Browser without the Geolocation API | `MyVisits`, `Profile` | Feature detection, then "continue without GPS" | Yes — the visit loses its position silently |
| Permission denied | `Profile` explains it; `MyVisits` shows a generic prompt | Continue without GPS | Yes — `MyVisits` cannot tell the rep *why* it failed |
| GPS fix takes too long | Both | `timeout: 10000` / `15000` | Yes — a 10 s budget indoors often fails |
| TomTom key missing or API failing | `RouteOptimizationService` | Haversine + `Route.DefaultSpeedKmh` fallback | Mitigated — degraded but functional |
| Third-party API quota exhaustion | `TenantRateLimitService` | Daily per-tenant quotas (Geocoding 100, PlacesRefresh 200, Import 10, EmailSend 500) with admin notifications at 80 % and 100 % | Mitigated |
| Nominatim's 1 req/s policy | `OsmSearchProvider` | Documented in the class comment; Overpass queries carry `[out:json][timeout:30|60]` | **Not verified** whether pacing is actually enforced |
| Decimal separator by locale | `ParseDecimal` | `CultureInfo.InvariantCulture` on both parse and format | Handled |
| Leads with no coordinates | `DataQuality.aspx` | A "Not Geocoded" counter and filter, so the gap is visible | Visible, not prevented |
| Provider configuration drift | `Diagnostics.aspx` | Shows whether each provider has a key and offers a connectivity test | Mitigated |

**Everything else in Rodrigo's list — Safari/iOS specifics, Android background
execution, battery, cached positions, duplicates, incorrect coordinates, CORS,
deployment and browser compatibility — is `Not verified`.** Not "did not happen":
*not recorded*.

---

## 18. Approaches That Did Not Work

**Not verified.**

No abandoned approach is documented anywhere in the repository. The one piece of
suggestive evidence is the reverse-geocoding provider that was built, wired into
a task-type constant, and never called (§11) — but whether it was tried and
dropped, or simply never finished, **cannot be determined from the code**, and
guessing which would be exactly the kind of assumption this brief forbids.

---

## 19. Current Known Limitations

Stated without softening, even though the application serves its own use case:

1. **No background tracking of any kind.** Foreground, one-shot, user-initiated.
2. **`accuracy` is never captured**, so no position can be qualified — before or
   after the fact.
3. **No accuracy threshold and no rejection path.** Any fix is as good as any
   other.
4. **The device timestamp is discarded**; only server time is kept.
5. **Location is optional** — a visit with `NULL` coordinates is a normal,
   accepted record.
6. **No offline capture.** No connectivity means no visit and a lost position.
7. **No server-side coordinate validation.** Out-of-range values would be stored.
8. **No spoofing detection**, and a web application cannot provide a guarantee
   here (§15).
9. **No geofencing and no proximity check** between the check-in and the lead.
10. **Reverse geocoding is dead code**; visit addresses are always `NULL`.
11. **`MyVisits` does not distinguish permission-denied from timeout**, so the
    rep gets no actionable message.
12. **Two runtime third-party origins with no fallback** — unpkg for Leaflet,
    raw.githubusercontent for marker icons.
13. **OSM tiles and Nominatim/Overpass are courtesy services**, not contracted
    capacity.
14. **No retention or deletion policy** for stored positions.
15. **Web Forms + `__doPostBack`**, which constrains how capture can be
    orchestrated on the client.

---

## 20. Technology Inventory

| Layer | Technology | Version | Purpose | External dependency | Cost / licence |
|---|---|---|---|---|---|
| Browser | Geolocation API | W3C | Position capture | No | Free |
| Frontend | Plain JavaScript in `.aspx` | — | Capture, hidden fields, postback | No | — |
| Frontend | Leaflet | 1.9.4 (unpkg CDN) | Map rendering | **Yes** | BSD-2 |
| Maps | OpenStreetMap raster tiles | — | Tiles | **Yes** | ODbL, usage policy applies |
| Maps | leaflet-color-markers via raw.githubusercontent | — | Marker icons | **Yes** | — |
| Geocoding | TomTom Search API | v2 | Address → coordinates | **Yes**, key | Commercial, quota |
| Reverse geocoding | TomTom Search API | v2 | Coordinates → address | Yes | **Unused** |
| Geocoding (free) | Nominatim | — | City/state → OSM area | **Yes** | Free, 1 req/s policy |
| Discovery | Overpass API | — | Entities by category | **Yes** | Free, fair-use |
| Routing | TomTom Routing API | v1 | Distance, time, traffic | **Yes**, key | Commercial, quota |
| Routing fallback | Haversine (own code) | — | Straight-line km | No | — |
| Enrichment | Google Places API | — | Contact enrichment | **Yes**, key | Commercial |
| Backend | ASP.NET Web Forms | .NET 4.7.2 | Pages and postbacks | No | — |
| ORM | Entity Framework | 6.5.1 | Persistence | No | — |
| Database | SQL Server (hosted) | — | `VisitSessions` and the rest | Yes | Hosting |
| Quotas | `TenantRateLimitService` (own code) | — | Daily per-tenant limits | No | — |
| Monitoring | `Diagnostics.aspx`, `DataQuality.aspx` (own code) | — | Provider status, ungeocoded leads | No | — |

---

## 21. Lessons Learned for CER Route

### Reusable

* **Optional location with an explicit user gesture.** Capture on a button press,
  let the work proceed if it fails. It keeps the product usable and it respects
  the rep.
* **Degrade instead of break.** The Haversine fallback behind the routing API is
  the best pattern in this codebase: the feature gets worse, never unavailable.
* **Invariant-culture parsing and formatting of coordinates**, on the way in and
  the way out.
* **Identity, tenant and timestamps from the server**, never from the request.
* **Per-tenant daily quotas with warnings at 80 % and 100 %** for paid
  third-party APIs.
* **A diagnostics screen that shows which providers are configured and reachable**,
  and a data-quality screen that counts what failed to geocode. Both turn silent
  degradation into something visible.
* **Separating acquisition from visualization.** Positions from one provider, map
  from another; either can be swapped.

### Needs Re-evaluation

* **One-shot capture.** Sufficient for check-in/out; **insufficient if CER Route
  means following a route.** That is a different problem, not a bigger version of
  this one.
* **Storing only latitude and longitude.** For CER Route, `accuracy` and the
  device timestamp should be captured from the start.
* **Letting location be optional.** Defensible for a sales visit; needs an
  explicit decision when the position is the evidence.
* **OSM tiles and Nominatim/Overpass.** Fine at this volume; they are courtesy
  services and a field application at scale should confirm the terms.
* **Server-only timestamps.** Correct for integrity, but capturing *both* device
  and server time is what lets you detect a delayed or replayed submission.

### Avoid

* **Discarding `accuracy`.** It is one field, and without it no question about
  position quality can be answered afterwards.
* **Trusting browser-supplied coordinates without range or plausibility checks.**
* **Building a provider and leaving it uncalled** (§11): dead code that looks like
  a feature is worse than an absent one, because the data model implies it works.
* **Loading runtime assets from `raw.githubusercontent.com`.** It is not a CDN and
  offers no availability guarantee.
* **Promising verified location from a web application.** It cannot be done.

### Unknown

* Real-world accuracy in the environments CER Route targets — warehouses,
  industrial parks, parking structures. **Never measured here.**
* Behaviour of `getCurrentPosition` on iOS Safari versus Chrome Android in the
  field. **Never recorded here.**
* Whether an installed PWA is sufficient for CER Route's needs, or a native
  capability is required. **Never tested here.**
* Battery and data cost of continuous tracking. **Never attempted here.**

---

## 22. Questions CER Route Will Eventually Need to Resolve

Identified, **not decided**:

1. **One-shot capture or continuous tracking?** Everything else follows from
   this, and this application only demonstrates the first.
2. **Web/PWA or native capability?** If background tracking is required, a mobile
   browser cannot deliver it, and no amount of engineering in the page changes
   that.
3. **Foreground only, or must capture survive a locked screen?**
4. **What accuracy is good enough**, and what happens to a position that does not
   meet it — reject, store flagged, or ask the user?
5. **Is location mandatory or optional** for an activity to count?
6. **Geofencing?** If arrival must be validated against a site, that needs zones,
   a radius, and a decision about the accuracy tolerance at the boundary.
7. **Offline operation.** Local queue, synchronisation, conflict resolution — or
   an explicit decision that connectivity is required.
8. **Capture frequency**, and its battery and data budget.
9. **Which map and routing providers**, and under what contract rather than
   courtesy policy.
10. **Data retention and deletion** of position history, which this application
    never addressed.
11. **How much integrity can be claimed**, given that a web application cannot
    guarantee a real position.
12. **What is recorded per position**: accuracy, device timestamp, server
    timestamp, source, device identifier.

---

## What this document is not

It is not a design for CER Route, not an architecture selection, and not a
recommendation to reuse this stack. The source application solves a narrower
problem — stamping a position on a sales visit — and does it in a way that fits
its constraints. CER Route should decide its own answers to §22 first, and treat
§19 and §21 as a list of things already paid for once.
