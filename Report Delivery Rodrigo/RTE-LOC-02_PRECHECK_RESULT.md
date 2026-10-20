# RTE-LOC-02 · PRECHECK — GPS periódico a 300 s (read-only)

**Fecha:** 2026-10-20 · **Veredicto: GO WITH GAPS**

## 1. Baseline
- Inspeccionado: `dev` @ `3ebc5cd`.
- Delta respecto a RTE-LOC-01 (`4bc266e`): **solo documentación** (el informe de LOC-01); **0 cambios en `app/`**.
- Datos: copia local (solo lecturas). Sin cambios de código, datos ni configuración.

## 2. Matriz

| # | Confirmed | GAP real | Decisión técnica mínima | Estado |
|---|---|---|---|---|
| 1 Aviso y bloqueo | **Bloqueo AS-BUILT:**<br>• `LocationGate.tsx` (puerta sin cierre, «Location Required»), montado en `RouteMyRoutePage.tsx:780`<br>• cola: `offlineQueue.ts:enqueueAction` lanza `PermisoDeUbicacionRequerido`<br>• servidor: `location/permission_gate.py` (403)<br>• revocación: `permission.ts:observarPermiso` (`onchange`, `visibilitychange`, `focus`, `pageshow`)<br>• cierre siempre permitido (`operationalActions.ts:56-62`)<br>**Aviso:** `privacyNotice.ts` (`LOCATION_NOTICE`, `localStorage`) **sigue sin importarse en ninguna pantalla** (grep: solo `location/index.ts:6`) | **El aviso no se muestra en la app.** Su texto dice *«Only at those moments. Your route between them is not tracked»*, que sería **falso** con captura periódica | Sin consentimiento nuevo: actualizar **solo el texto** (un punto cada N min durante la jornada activa con la app abierta) y mostrarlo una vez antes del primer prompt (flujo ya diseñado). Si el aviso aceptado por el PO vive fuera de la app, basta corregir el texto | OPEN |
| 2 Temporizador | `RouteMyRoutePage` ya conoce la fase (`working` / `planning` / `on-route` / `ending`) y escucha `visibilitychange` (`:430-438`). `captureFor` / `getCurrentPosition` de eventos en `location.ts:242-704` | No existe muestreo | Un hook `usePeriodicLocation(session)` montado **solo** con jornada activa y permiso operativo. **`setInterval` + `getCurrentPosition`** propio (alta precisión, timeout 10 s, `maximumAge` 60 s), no `watchPosition`: a 300 s no conviene mantener el GPS encendido. Al volver a `visible`, captura si toca. **Una sola pestaña** con `navigator.locks`. Se para en End Work, desmontaje, revocación, logout y cambio de usuario. Con la pantalla bloqueada **no se garantiza** | READY |
| 3 Config UX / API / RBAC | La política `route_location` (`core/platform/policies.py:46-77`) es de **plataforma**, no de tenant. El cliente la lee una vez en `GET /api/location/policy` (`location.ts:78-182`). Convención de capacidades: `route.<módulo>.<acción>`, con gestión `*.manage` (`catalog.py:120,150`) | No hay configuración de Route por tenant | Tabla de Route por `company_id` (no en el núcleo): `enabled` + `capture_interval_seconds` (300, **rango propuesto 60–3600**), con `version` (409). Pantalla en CER Route Configuration. Capacidad **`route.locationcapture.manage`**, a demanda (coherente con `activityemails.manage`; la sugerida `route.location.capture.configure` también encaja). La política del cliente añade estos campos y se relee al volver a `visible` y en cada ciclo: **sin refresh**. Validación y auditoría (`record_event`) en el servidor | READY |
| 4 Ingesta / cola | Tenant y usuario del servidor; jornada activa obligatoria; deduplicación por tupla de evento (`location/service.py:165-288`). **P0 CONFIRMED (código):**<br>• `PendingAction` y `pending_location_evidence` **no guardan usuario** (`offlineQueue.ts:93-118, 216-241`)<br>• el logout **no limpia** IndexedDB (`logout.ts:6-16`)<br>• `flushQueue` envía todo con la cookie actual | Cruce de cola entre usuarios del mismo navegador: un `worksession.start` encolado por A se ejecutaría como B | **Fix mínimo:** guardar `userId` al encolar (como ya hacen las fotos, `offlineQueue.ts:324-405`) y enviar **solo** lo del usuario actual. Lo ajeno no se borra, queda retenido. Muestras: carril propio con `client_sample_id` (UUID), lote ≤ 50, rechazo > 30 días o > 5 min en el futuro | **BLOCKER (P0)** |
| 5 Vista unificada | `trip.started_at` / `arrived_at` / `ended_at`, `trip_purpose_change.changed_at`, `work_session.started_at` / `ended_at` / `user_id`. Copia local: **0 viajes solapados por jornada**, 1 abierto, 10 jornadas que cruzan medianoche | No hay unión | `VIEW` de solo lectura: `location_fix` (source=`event`, viaje por `subject`: **seguro**) UNION ALL muestras (source=`periodic`). Viaje de la muestra = jornada + `device_captured_at` ∈ [`started_at`, `coalesce(arrived_at, ended_at, siguiente started_at, session.ended_at)`): **aproximado**, por la deriva de reloj del dispositivo. Unión siempre por `company_id` + `work_session_id`; sin escribir en `location_fix` | READY |
| 6 Archivado posterior | `location_fix` es de solo inserción (triggers, `integrity.py`); el patrón de scheduler y job CLI existe | — | Tabla de muestras **particionada por mes** con `company_id` en la clave. Mes de archivo por **`server_received_at`** (corte cerrado, sin reabrir lo archivado); `device_captured_at` para el análisis. Sin FK desde `location_fix`; purga solo de muestras (`DROP PARTITION`) tras verificar | READY |

## 3. Contract sketch (sin DDL)
- **`location_sample`** (Route):
  - claves: `id`, `company_id` y `work_session_id` (servidor, FK compuesta), `user_id` (del servidor);
  - `client_sample_id` uuid, **único por `company_id`**;
  - punto: `latitude`, `longitude`, `accuracy_m` (umbral fresco vigente: 100 m);
  - tiempos: `device_captured_at`, `server_received_at`;
  - estado: `permission_state`, `interval_seconds_applied`.
- **API:** `POST /api/location/samples` con un lote ≤ 50.
  - Requiere `route.worksession.execute`, y la jornada debe ser la **activa del usuario autenticado**, o haberse cerrado dentro de la gracia.
  - Responde por ítem `accepted` / `duplicate` / `rejected`.
- **Configuración:**
  - `GET` y `PUT /api/route/location-capture`, con `route.locationcapture.manage` (`GET` también para `worksession.execute`, vía `/api/location/policy`).
- **Vista:** `location_point_timeline` (`source`, `company_id`, `work_session_id`, `user_id`, `trip_id` derivado, `captured_at`, `accuracy_m`), consultada siempre con filtro de tenant y alcance.

## 4. P0 / Blockers
- **P0 · Cola sin conexión entre usuarios:** CONFIRMED por código; no reproducido en navegador por regla read-only. Debe corregirse **antes** de añadir otro carril de muestras.
- **Aviso GPS: OPEN.** Sin pantalla, y con un texto incompatible con la captura periódica.
- **Los 5 E2E RTE-06 que fallan desde antes** (reproducido hoy: `test_g5` falla igual, `0 == 1` en `recovered`):
  - **G1–G3 y G5:** causa **LIKELY**.
    - El guion sustituye `getCurrentPosition` (tests del 02/10).
    - El sondeo de permiso de RTE10-A02 (`permission.ts:sondear`, 07/10) **también lo llama** al cargar y al abrir trabajo, y consume pasos del guion.
    - Verificación: contar `window.__geoLlamadas` con `maximumAge: Infinity`.
  - **`offline_durability`** (otra coordenada guardada): **UNVERIFIED**; mismo periodo, sin reproducir aparte.

## 5. Siguiente checkpoint (propuesta)
1. **U1 (P0), ~3 h:**
   - **Qué:** cola por usuario y texto o pantalla del aviso.
   - **Tests:** E2E de logout A → login B sin envío cruzado; reparar el guion de los 5 E2E para ignorar el sondeo.
2. **U2, ~6 h:**
   - **Qué:** configuración por tenant, tabla, API de lotes, hook de 300 s y vista.
   - **Tests:**
     - integración: idempotencia, otro tenant, jornada ajena 404, rango 422, auditoría;
     - E2E: muestra a los N s, parada en End Work, revocación, una sola pestaña.
3. **U3, ~1,5 h:**
   - **Qué:** documentación y regresión de ubicación y millaje (que el millaje oficial no cambie).

**Total ~10,5 h + 30 % por E2E de navegador ≈ 13,5 h.** **GO WITH GAPS:** se puede codificar si U1 va primero.

## 6. Preguntas al PO
1. ¿El aviso aceptado está **dentro** de la app (entonces hay que mostrarlo y corregir el texto) o en un documento externo (solo texto)?
2. ¿Rango permitido del intervalo, por ejemplo **60–3600 s**?
3. ¿Quién recibe `route.locationcapture.manage` por defecto: nadie (a demanda, como los correos) o el Admin?
