# CER Route — Visualizador de ruta estimada en Activity: diagnóstico AS-BUILT

**Reporte 001 — respuesta a** `CER_ROUTE_ACTIVITY_ROUTE_MAP_VIEWER_DIAGNOSTIC_SINGLE_INSTRUCTION_V1_0.md`
**Fecha:** 14 de octubre de 2026
**Naturaleza:** diagnóstico de solo lectura. No se modificó código, esquema, datos, permisos, configuración, tests ni UI. No se llamó a ningún proveedor externo.

---

## 1. Status y alcance revisado

**Status: COMPLETED (diagnóstico).** La funcionalidad de mapas **no** está diseñada ni autorizada.

| Elemento | Valor |
|---|---|
| Rama inspeccionada | `dev` |
| Commit | `069b5893e298ddda7d892ce9cc948542c3641d95` (= `origin/dev`), que ya incluye V1.3 |
| Ramas remotas revisadas para el enlace de Google Maps | 4 de 4, más el historial completo (`git log -G`) |
| Base inspeccionada | **local** `db-dev-cer-route`, migración `0018_route_distinct_roles`. Según el desarrollador, es una copia actualizada del entorno de trabajo |
| Tipo de consulta | `SET TRANSACTION READ ONLY` + `SELECT` sobre el esquema y **agregados**. No se extrajo ninguna coordenada ni ningún nombre |
| Entorno desplegado | **NOT RUN**. No hay acceso; nada de lo que aquí se afirma sobre datos se ha comprobado en él |

Etiquetas usadas: **CONFIRMED** (visto en código o en datos), **PARTIAL**, **GAP** (no existe), **RISK**, **PENDING VALIDATION**, **DECISION REQUIRED**.

---

## 2. Resumen ejecutivo

**¿Podemos dibujar hoy la ruta estimada con lo ya guardado? NO.** **CONFIRMED.**

1. **No se guarda ninguna geometría, y nunca se pidió.** Los cuatro adaptadores de Routing (TomTom, OSRM, Valhalla y el de respaldo) piden **solo la distancia**: TomTom con `routeRepresentation=summaryOnly`, OSRM con `overview=false`, Valhalla con `directions_type=none`. La geometría no se recibe, así que no hay nada descartado que recuperar. En la base no existe ninguna columna de polilínea, GeoJSON ni respuesta cruda, y PostGIS no está instalado.
2. **Sí se guardan los puntos de paso** de cada viaje calculado, en orden: inicio, cada Change Plan y llegada, en `trip_mileage_segment`, con metros, proveedor y método. Con eso se dibujan **marcadores unidos en línea recta**, **no la ruta por calles**.
3. **Esos puntos solo existen para el 44 % de los viajes de la base local:** 96 de 216 cálculos de millaje. Los viajes fallidos, no calculables o pendientes no tienen segmentos.
4. **El enlace de Google Maps que menciona la instrucción no existe en el código.** **CONFIRMED** en `dev`, en las 4 ramas remotas y en todo el historial. Ninguna respuesta de la API, pantalla ni exportación lo genera. Ver la decisión D1.
5. **El permiso por usuario no existe.** La autorización es **solo por rol**: cada usuario tiene exactamente un rol por compañía y no hay overrides, grants individuales ni feature flags. Un `route.map.read` asignado a «determinados usuarios» requiere una decisión (D3).
6. **El alcance jerárquico ya resuelve casi todo** lo que el mapa necesitaría, incluida la separación Sales/COO, con tests negativos. Lo que falta es validar que un `trip_id` o un `work_session_id` pertenecen al alcance del que consulta: hoy ningún endpoint administrativo los acepta.

**Recomendación:** la ruta original **no se puede recuperar** para los viajes históricos. Si CER quiere la ruta estimada fiel, tiene que **empezar a guardarla en el momento del cálculo oficial** (en la misma petición al proveedor). Para el histórico, lo honesto es mostrar **solo los puntos registrados**, rotulados como tales. Detalle en §8.

---

## 3. Inventario técnico: evento → Trip → Routing → TripMileage → enlace

### 3.1 Captura de ubicación — CONFIRMED

| Elemento | Evidencia |
|---|---|
| **Eventos que capturan ubicación (7):** `start_work`, `start_trip`, `change_plan`, `arrived`, `activity_complete`, `activity_leave`, `end_work`. `start_activity` queda excluido a propósito | `app/routers_api/location/models.py:71-85` (`LocationEventKind`) |
| **Tabla `location_fix`:** `latitude`, `longitude`, `accuracy_m`, `evidence_level` (`fresh` / `degraded_cached` / `recovered`), `device_captured_at`, `server_received_at`, `source_age_seconds`, `permission_state`, `subject_kind`/`subject_id`, `work_session_id` | `location/models.py:219-306`; migración `0010_location_evidence_and_trip_mileage.py:100-116` |
| **Un punto por evento**, no una traza: índice único (compañía, evento, sujeto); tabla append-only. El docstring lo dice: «no una traza» | `location/models.py:222-225` |
| **Validación en el servidor:** sesión activa, `device_captured_at` como mucho 5 min en el futuro y 30 días en el pasado, precisión obligatoria y limitada por política, rangos de coordenadas por schema y CHECK, reenvío idempotente | `location/service.py:98-132, 203-212, 268-288, 325-365` |
| **Cliente:** fix fresco → fix en caché (`degraded_cached`) → ventana de recuperación → ausencia | `components/react/shared/lib/location/location.ts:441-620` |
| **Permiso denegado:** pasa directo a `missing_location_event` con `permission_denied` | `location.ts:482-493`; `location/models.py:157-178, 315-414` |
| **Offline:** la evidencia se encola en IndexedDB y se enlaza después por `client_action_key` | `shared/lib/offlineQueue/offlineQueue.ts:217`; `location/schemas.py:61-67` |
| **Retención:** comentarios que indican que la evidencia cruda puede purgarse. **PARTIAL:** no encontré el job de purga | `location/models.py:45`; `mileage/router.py:164-166` |

**Datos locales (agregados).**
- **Con punto:** 647 eventos en `location_fix`, de los que el 96 % son `fresh`.
- **Sin punto:** 193 eventos en `missing_location_event`. 162 son `permission_denied`; el resto, `no_client_report`.

### 3.2 WorkSession, Trip y ActivityExecution — CONFIRMED

- **WorkSession** (`worksessions/models.py:60-248`): como mucho una activa por usuario, pero **varias por día**. En local, 10 combinaciones usuario-día tienen más de una jornada.
- **Trip** (`trips/models.py:103-280`): N por jornada, ordenados por `sequence`. Estados: `planning`, `in_transit`, `arrived`, `closed` e `interrupted`.
  - Un viaje `home` se cierra al llegar **sin actividad** (`trips/service.py:441-463`).
  - Change Plan **no** crea otro viaje: añade una fila en `trip_purpose_change` y un punto intermedio.
  - En local hay de 1 a 11 viajes por jornada.
- **ActivityExecution**: 0 o 1 por viaje (`activities/models.py:118-189`).
- **TripMileage** se crea en estado pendiente al llegar o al interrumpirse (`trips/service.py:472, 533`). Los viajes en `planning` o `in_transit` no tienen fila.

### 3.3 Motor de Routing — CONFIRMED

| Adaptador | Petición | Lo que se lee | ¿Geometría? |
|---|---|---|---|
| `TomTomRouter` `mileage/routing.py:329-514` | `calculateRoute/{lat},{lon}:{lat},{lon}`, `routeRepresentation=summaryOnly`, `travelMode=car`, `routeType=fastest`, `traffic=false` | `routes[0].summary.lengthInMeters` | **No** (`:412-421`) |
| `OsrmRouter` `:128-237` | `overview=false` | `routes[0].distance` | **No** (`:131-134`) |
| `ValhallaRouter` `:241-326` | `directions_type=none` | `trip.summary.length` | **No** (`:273-275`) |
| `FallbackRouter` `:517-562` | OSRM → Valhalla ante un fallo transitorio | — | — |

- **Interfaz:** `RoadRouter.distance(origin, dest) -> SegmentResult` (`:93-104`). `SegmentResult` contiene solo `distance_meters`, `provider`, `method` y `version` (`:64-76`).
- **La frontera distancia/geometría es la propia interfaz:** devuelve distancia y nada más.
- **Puntos de paso del cálculo** (`mileage/service.py:192-239`): Start Trip → cada Change Plan → Arrived, con **una llamada por par consecutivo**.
  - Si falta un punto, el viaje queda `not_calculable` (`:175-190`).
  - Se calculan todos los tramos antes de escribir nada (`:331-388`).
  - Plausibilidad: la distancia por carretera no puede ser menor que la línea recta, hay un máximo por tramo y una velocidad implícita máxima (`:559-602`).
  - Reintentos con backoff (`:482-500`).
  - Un `calculated` no vuelve a cambiar (`:391-465`).
- **Millas oficiales:** `total_meters / 1609.344`, al leer (`mileage/read.py:57-78`).
- **Selección del proveedor:** primero la integración de plataforma `road_routing` (TomTom, con clave cifrada); luego las URL de entorno (`get_road_router`, `routing.py:592-688`). Sin caché.

### 3.4 Persistencia del cálculo — CONFIRMED

- **`trip_mileage`** (`mileage/models.py:105-185`): `trip_id` (único), `state`, `total_meters`, `calculated_at`, `terminal_reason`, `attempt_count`, `next_attempt_at` y `last_error`. No tiene FK directa a la jornada: se llega por el viaje.
- **`trip_mileage_segment`** (`:188-272`, append-only por trigger): `sequence` y, para cada extremo (`from_*` / `to_*`), `event_kind`, latitud, longitud, `evidence_level`, `accuracy_m`, `captured_at` y `fix_id`. Además: `distance_meters`, `provider`, `method`, `provider_version`, `computed_at` y `haversine_meters` (este último, solo diagnóstico).
- **No existe:** polilínea, polilínea codificada, GeoJSON, geometría, vértices, `route_id` ni respuesta cruda. Comprobado en modelos, en las migraciones 0001–0018 y en `information_schema` de la base local.

**Datos locales:**

| Estado del cálculo | Motivo | Viajes | Con segmentos (puntos) |
|---|---|---|---|
| `calculated` | — | 96 | 96 |
| `calculation_failed` | `routing_exhausted` | 54 | 0 |
| `calculation_failed` | `implausible_segment` | 13 | 0 |
| `not_calculable` | `start_waypoint_missing` | 49 | 0 |
| `not_calculable` | `arrival_waypoint_missing` | 2 | 0 |
| `pending_calculation` | — | 2 | 0 |
| sin fila de millaje (viaje `in_transit`) | — | 1 | — |

- **Proveedor:** los 99 segmentos son de TomTom, con `method = car/fastest/no-traffic` y versión `0.0.12`.
- **Forma de los viajes:** 93 tienen un solo tramo; 3 tienen dos (con Change Plan).

**Hallazgo incidental (RISK, fuera de alcance; sin tocar):**
- **Lo que se vio:** 54 viajes en `routing_exhausted`.
- **Causa:** **UNVERIFIED**. Puede deberse a la configuración de Routing del entorno de origen.
- **Por qué importa para el mapa:** cualquier vista basada en el cálculo tendrá huecos en esos viajes.
- **Acción operativa:** revisar en el entorno real. Existe `app/db/scripts/reprocess_failed_mileage.py`, que por defecto solo simula y que **no se ejecutó**.

### 3.5 Enlace de Google Maps — GAP (CONFIRMED)

- En `app/` no aparecen `google.com/maps`, `maps.google`, `goo.gl/maps`, `maps/dir`, `saddr` ni `daddr`.
- `git log --all -G` tampoco los encuentra.
- Las 4 ramas remotas tampoco los contienen.
- La única mención de Google en el código es un comentario de `mileage/routing.py:21` sobre proveedores alternativos.
- Ninguna respuesta de Activity, Live o Reports, ni el Excel, contiene un enlace o una coordenada (`reports/excel.py:39-56`; `reports/dao.py:19`).

**Consecuencia:** el «fallback al enlace existente» de la alternativa C no tiene sobre qué apoyarse; habría que construirlo. Ver D1.

---

## 4. Geometría e histórico

| Caso | Lo que hay hoy | ¿Se puede dibujar sin llamar al proveedor? |
|---|---|---|
| Viaje `calculated` (1 tramo) | Origen y destino ordenados, con metros oficiales | **PARTIAL:** 2 marcadores y una línea recta, no la ruta |
| Viaje `calculated` con Change Plan | Puntos intermedios en orden | **PARTIAL:** N marcadores y una poligonal recta |
| `calculation_failed` / `not_calculable` / `pending_calculation` | Sin segmentos; solo los `location_fix` existentes, mientras se retengan | **PARTIAL o NO:** los puntos que hubiera, sin cifra oficial que los respalde |
| Viaje sin actividad (`home`) | Igual que cualquier otro viaje: tiene `start_trip` y `arrived` | Igual que su estado de millaje |
| Viaje abierto (`in_transit`) | Sin millaje; solo el punto de inicio | **NO** hay ruta |
| **Jornada completa** | Secuencia de viajes por `sequence` | **PARTIAL:** se pueden encadenar **solo los tramos que existen**. Entre la llegada de un viaje y la salida del siguiente no hay tramo calculado, y no debe inventarse |
| Varias jornadas el mismo día | Jornadas separadas | Hay que mostrarlas por jornada, no fundir el día |

**Histórico — CONFIRMED.** Ningún viaje ya guardado tiene geometría. Para obtenerla habría que **volver a llamar** al proveedor.
- `provider`, `method` y `provider_version` permitirían dirigir la petición al mismo motor, y `traffic=false` ayuda a reproducirla.
- Aun así, **no hay garantía** de que la red de calles y la versión de hoy den el mismo trazado que el día del cálculo. Un trazado así **no puede presentarse como la ruta original**.

**Diferencia con la línea recta** (local): la distancia por carretera es, de media, 2,59 veces la recta (mínimo 1,01, máximo 50). Una poligonal recta **subestima visualmente** el recorrido y no casa con las millas mostradas: si se usa, tiene que rotularse como tal.

---

## 5. RBAC por usuario y alcance

### 5.1 Modelo de permisos efectivo — CONFIRMED

- **Solo por rol.** `user_company.role_id` es NOT NULL (`companies/models.py:129`): un rol por usuario y compañía. No hay ninguna tabla de override, allow/deny, grant individual ni feature flag por usuario o por tenant (revisados todos los `__tablename__`). `platform_policy` es configuración de despliegue, no autorización.
- **Permisos efectivos:** `get_user_permissions` (`users/permissions.py:33-58`) recorre membresía activa → rol activo → `role_permission` → `permission`, **en cada petición y sin caché**. `is_superuser` lo salta (`:135-136`).
- **La cookie `user_data`** solo pinta la interfaz y nunca autoriza (`loggedin_middleware.py:64-97`).

### 5.2 Cómo se cambia un permiso hoy — CONFIRMED

1. `PUT /api/roles/{id}/permissions` (`rolepermissions.update`) crea una **solicitud pendiente** con el conjunto completo, sin aplicar nada (`rolepermissionsapprovals/service.py:151-218`). Solo puede haber una pendiente por rol (`models.py:65-70`).
2. **Aprobar o rechazar** (`rolepermissionsapprovals/router.py:116-157`) tiene estas guardas:
   - el revisor debe tener un rol de categoría `management` (owner o admin);
   - nadie puede aprobar su propia solicitud;
   - una solicitud de otro tenant da 404;
   - una ya resuelta da 409 (`service.py:94-146, 240-249`).
3. **Gap de auditoría (RISK):** la aprobación **no escribe `audit_event`**. La traza es solo la fila de la solicitud: quién pidió, quién revisó, estado y nota. Para una capacidad sobre ubicaciones de empleados probablemente no baste.

### 5.3 Viabilidad de `route.map.read` (nombre provisional, no creado)

- **Declararlo es sencillo:** catálogo, endpoint que lo exija y alineación. `tests/test_permission_catalog.py` obliga a que exista un endpoint que lo use.
- **Asignarlo a «determinados usuarios» no se puede sin decisión:**

| Opción | Cómo | Riesgo / coste |
|---|---|---|
| a) Capacidad en roles existentes | Añadir `route.map.read` a, por ejemplo, CEO y COO | Lo reciben **todos** los del rol. Contradice «no a roles completos» |
| b) Rol gemelo («COO + mapa») | Duplicar un rol con la capacidad añadida | La instrucción lo prohíbe. Además **rompe V1.3**: el cargo se deriva del **nombre** del rol (`CARGO_DE_ROL`, `organization/models.py:98-105`) y el alcance de `ROLES_ACOTADOS`. Un rol propio tiene **alcance de tenant** (`scope.py:11-14`): un «COO + mapa» vería **toda la compañía**. **RISK alto** |
| c) Grant individual nuevo | Tabla `user_capability_grant` (tenant, usuario, capacidad, vigencia, quién la otorgó), con escritura auditada y comprobación en `require_permissions` | Mecanismo **nuevo** en Core: hay que decidir dónde vive y cómo se aprueba. Es la única opción que cumple «por usuario» sin tocar el alcance |

### 5.4 Alcance jerárquico — CONFIRMED (con un gap)

- **Activity administrativa:** `GET /api/activity-explorer`, con `route.activity.read`.
  - Construye `alcance_administrativo`.
  - Un `supervisor_user_id` fuera del alcance da **404, idéntico a uno inexistente** (`activityexplorer/router.py:73-123`).
  - Las jornadas se filtran por las ventanas históricas de la rama (`condicion_de_jornadas`, `organization/scope.py:119-137`).
- **Activity personal:** `GET /api/activity-explorer/me`, con `route.worksession.execute`. El sujeto es siempre quien llama e ignora cualquier `user_id` (`router.py:126-145`). Seguiría siendo self-only aunque la abra un CEO.
- **Separación Sales/COO:** Sales solo puede colgar de un CEO (`PADRES_PERMITIDOS`, `organization/models.py:82-93`; `service.py:241-265`), así que **nunca** cae en la rama de un COO o un RM. Los tests negativos ya lo cubren: COO y RM pidiendo un Sales reciben 404 en Activity, Reports y Excel (`tests/integration/test_org_hierarchy.py:441-517, 659-688`).
- **Gap para el mapa:** ningún endpoint administrativo acepta hoy `trip_id` ni `work_session_id`. El único que devuelve coordenadas, `GET /api/mileage/trips/{trip_id}/segments`, es **self-only** (404 si no es tuyo; `mileage/router.py:102-188`) y la interfaz no lo usa. Un mapa administrativo necesita un **validador nuevo**: el viaje pertenece a una jornada cuyo dueño está en el alcance **y** cuyo `started_at` cae dentro de su ventana. Sin eso, un COO podría pedir por `trip_id` el viaje de un Sales.

**Estado operativo de V1.3** (recordatorio del diagnóstico de jerarquía de hoy): en la base local, 5 jefes tienen el rol `supervisor` aunque conservan su cargo. Mientras siga así, no ven Activity administrativa y **tampoco verían el mapa**. Es independiente de este frente.

### 5.5 Matriz de autorización esperada (regla: `route.map.read` **y** acceso vigente a la Activity objetivo)

| Actor | Mapa en Activity administrativa | Mapa en Activity personal | ¿Ya lo garantiza el código? |
|---|---|---|---|
| route_admin | Todo el tenant, si tiene el permiso | Lo propio | Alcance sí; falta la capacidad |
| CEO | Su rama, **con** Sales | Lo propio | Alcance sí |
| COO / Regional Manager | Su rama, **sin** Sales; 404 fuera de ella | Lo propio | Alcance y 404 sí; **por `trip_id`, no** |
| OSM / Supervisor / Sales | 403 (no tienen `route.activity.read`) | Lo propio, si tienen el permiso | Sí |
| Sin el permiso de mapa | 403 en el mapa; Activity sigue igual | Igual | Requiere el endpoint nuevo |
| Rol inactivo o sin capacidades | 403 | 403 | Sí |
| Rol de mando sin cargo | Lista vacía | Lo propio | Sí (`scope.py:22-23`) |
| Membresía suspendida o identidad desactivada | 401/403, también con sesión abierta | 401/403 | Sí (`users/dependencies.py:82-119`) |
| `supervisor_user_id` manipulado | 404 idéntico | Ignorado | Sí |
| `trip_id` / `work_session_id` manipulado | **Debe** dar 404 | **Debe** dar 404 si no es suyo | Personal sí; **administrativo, GAP** |
| Cookie `user_data` editada | Sin efecto | Sin efecto | Sí |

---

## 6. Viabilidad: mapa, API, Web/Mobile y proveedor

- **Activity:** las dos vistas usan el mismo widget, `ActivityExplorerPanel` (`scope="self"` / `"admin"`), y el mismo router, `activityexplorer`.
  - Cada viaje es una tarjeta con `key={trip_id}` (`features/RouteActivityExplorer/ui/ExplorerActivityCards.tsx:53-68`).
  - Los viajes aparecen en orden cronológico, pero **no agrupados por jornada**, sin número de secuencia y sin vista de detalle.
  - **Ninguna respuesta incluye coordenadas, enlace ni `work_session_id`**, y los schemas son `extra="forbid"`: añadirlos sería un cambio explícito de contrato.
- **Renderizador:** **GAP.** No hay ninguna librería de mapas instalada (ni leaflet, maplibre, mapbox, Google ni OpenLayers), ni iframes o imágenes estáticas de mapa.
- **CSP — RISK de diseño** (`core/middleware/security_headers_middleware.py:45-76`): `default-src 'self'`, `script-src 'self'`, `img-src 'self' data: blob:`, `connect-src 'self'`, sin `frame-src`, más `X-Frame-Options: DENY`.
  - **Bloquea:** scripts, teselas e iframes de cualquier proveedor externo. Habrá que abrir orígenes concretos o servir las teselas a través del propio servidor.
  - **No bloquea:** un enlace `<a href>` saliente.
- **Mobile/Web:**
  - `/route/activity` vive en `RouteMobileShell` (columna `max-w-md`).
  - No hay service worker ni PWA. Las lecturas no se guardan en caché offline: si falla la red, el panel conserva lo último que tenía.
  - La vista del día devuelve todos los viajes sin paginar. Una geometría por viaje (decenas o cientos de vértices) **no** debería ir en esa respuesta, sino cargarse **bajo demanda por viaje**.
- **Proveedor y costes (PENDING VALIDATION externa):**
  - TomTom permite pedir la geometría **en la misma petición** que ya se hace (cambiando la representación de la ruta).
  - Por verificar:
    - que la distancia devuelta no cambie;
    - si la tarifa por petición varía;
    - si los **términos de TomTom permiten almacenar** la geometría y por cuánto tiempo (el propio código lo advierte en `mileage/routing.py:332-338`).
  - **Teselas:** dibujar el mapa necesita un proveedor de teselas, con su propia licencia y cuota, que hoy no existe en el proyecto.
- **Millas oficiales:** el mapa no debe cambiarlas. Hoy están protegidas: un `calculated` no se recalcula (`mileage/router.py:191-217`) y los segmentos son append-only.

---

## 7. Matriz Expected → As-Built → Evidence → Gap → Impact → Recommendation

| # | Expected | As-Built | Evidence | Gap | Impact | Recommendation |
|---|---|---|---|---|---|---|
| 1 | Puntos GPS de eventos | 7 eventos, un punto cada uno, con precisión y nivel de evidencia | `location/models.py:71-306` | Ninguno | Hay base para los marcadores | Reutilizar |
| 2 | Millaje y proveedor | TomTom; `trip_mileage` + `trip_mileage_segment` | `mileage/routing.py:329-514`; `mileage/models.py:105-272` | 56 % de los viajes locales sin cálculo | Mapas con huecos | Resolver `routing_exhausted` aparte (fuera de alcance) |
| 3 | Geometría de la ruta | **No**; solo distancia | `routing.py:131,273,412`; `information_schema` | **GAP total** | No se puede dibujar la ruta original | Decidir si se captura a partir de ahora (D2) |
| 4 | Enlace de Google Maps | **No existe** | grep + `git log -G` en 4 ramas | **GAP** respecto a la premisa | La alternativa C no tiene fallback | Aclarar el origen de la premisa (D1) |
| 5 | Activity personal y administrativa | Mismo widget y router; alcance correcto | `activityexplorer/router.py:73-145` | Sin coordenadas, sin `work_session_id`, sin detalle de viaje | Hace falta contrato nuevo | Endpoint de mapa aparte, bajo demanda por viaje |
| 6 | Permiso por usuario | **Solo por rol** | `companies/models.py:129`; `users/permissions.py:33-58` | **GAP** | «Por usuario» no es posible hoy | Decisión D3 |
| 7 | Alcance jerárquico | Rama histórica por periodo; Sales solo bajo el CEO; tests negativos | `organization/scope.py`; `test_org_hierarchy.py:441-688` | Falta validar `trip_id` y `work_session_id` en el alcance | Un IDOR, si no se cubre | Validador nuevo sobre `condicion_de_jornadas`, con tests COO→Sales |
| 8 | Auditoría de la habilitación | La aprobación de permisos no escribe `audit_event` | `rolepermissionsapprovals/service.py` | **GAP** | Sin traza fuerte de quién habilitó ver ubicaciones | Auditar la concesión (D3/D5) |
| 9 | Renderizado | Sin librería; la CSP bloquea lo externo | `package.json`; `security_headers_middleware.py:45-76` | **GAP** | Trabajo de plataforma | Elegir proveedor de teselas y ajustar la CSP (D4) |
| 10 | Privacidad | Coordenadas solo en un endpoint self-only que no se usa | `mileage/router.py:155-188` | No hay política para el nuevo uso | **RISK** legal y laboral | Revisión de consentimiento y retención (D5) |

### Riesgos de seguridad, privacidad y costes

- **RISK — exposición:** hoy ninguna vista administrativa expone coordenadas. El mapa sería **la primera** en mostrar ubicaciones de empleados a terceros. Necesita control en el servidor (capacidad, alcance y propiedad del viaje) y no en la interfaz.
- **RISK — enlace externo:** un enlace a Google Maps con coordenadas es una URL **copiable y compartible** que sale del control de `route.map.read`, y además envía las coordenadas a Google. Si se construye, debe generarse bajo demanda, tras la misma autorización, y nunca guardarse ni incluirse en el Excel.
- **RISK — fidelidad:** abrir Google Maps traza **su** ruta, no la de TomTom que dio las millas. No debe presentarse como «la ruta calculada».
- **RISK — retención:** guardar la geometría crea un dato nuevo de localización de empleados, con su política de retención y los términos del proveedor.
- **Costes:** guardar la geometría hacia adelante **no añade llamadas**. Reconstruir el histórico añade **una llamada por tramo** (99 en local) y queda sujeto a cuota. Las teselas tienen un coste aparte. **PENDING VALIDATION** con los proveedores.

---

## 8. Alternativas

| Criterio | **A — geometría persistida** | **B — reconstruir desde los puntos** | **C — marcadores + enlace** |
|---|---|---|---|
| ¿Existe hoy? | **No.** Sería «A hacia adelante»: capturarla en la misma petición del cálculo oficial | Viable para los viajes con segmentos | Marcadores sí; **el enlace no existe** |
| Fidelidad | **Máxima**: misma petición, mismo motor, misma distancia | Media: mismo motor, distinto día; puede diferir | Baja: puntos reales, sin trazado; Google traza otra ruta |
| Histórico | Solo los viajes nuevos | Histórico con segmentos (44 % local) | Todo viaje con puntos |
| Contratos y API | Columna nueva + endpoint de mapa + cambio en el adaptador | Endpoint + llamadas bajo demanda | Endpoint de puntos; enlace construido |
| Coste operativo | Ninguna llamada extra; más almacenamiento | Una llamada por tramo y cuota | Ninguno |
| Privacidad | Dato nuevo que se retiene | Coordenadas enviadas de nuevo al proveedor | Coordenadas a Google si se abre el enlace |
| Latencia y rendimiento | Lectura local, bajo demanda por viaje | Llamada externa en cada consulta o caché | Inmediata |
| Mobile | Polilíneas simplificadas, bajo demanda | Igual que A, más la espera | Ligero |
| Esfuerzo relativo | **Medio** (proveedor + plataforma + UI) | Medio-alto (cuotas y caché) | **Bajo-medio** |

**Recomendación** (condicionada a D1–D5):
1. **Para los viajes nuevos, «A hacia adelante»**, si los términos de TomTom permiten guardar la geometría. Es la única forma de mostrar *la misma* ruta que dio las millas, sin coste extra por llamada. **No** cambia la distancia ni las millas, y requiere verificar que la distancia devuelta es idéntica.
2. **Para el histórico, C sin enlace:** los puntos registrados, en orden, rotulados *«puntos registrados — no es la ruta recorrida ni la calculada»*.
3. **B solo bajo demanda**, si CER lo pide explícitamente, rotulado *«trazado reconstruido»*.
4. **El enlace de Google Maps**, solo si D1 lo confirma, con las mitigaciones de §7.

**Esfuerzo orientativo** (horas-agente; se revisará en el MD de desarrollo):

| Bloque | Complejidad | Horas-agente |
|---|---|---|
| Captura y guardado de la geometría (adaptador, columna, migración, tests de que la distancia no cambia) | media | 3–5 |
| Endpoint de mapa por viaje y jornada + validador de alcance por `trip_id` + tests negativos (COO→Sales, otro tenant, IDs manipulados) | media | 4–6 |
| Mecanismo de permiso individual (opción c), con auditoría | media-alta | 5–8 |
| Renderizador, teselas, CSP y vista en Activity (Web y Mobile) + E2E | alta | 8–12 |
| **Subtotal** | | **20–31** |
| Margen: +30 % por integración de terceros en el proveedor y las teselas; +50 % sobre la parte de navegador | | **≈ 28–43** |

---

## 9. Decisiones pendientes del Product Owner (bloquean el diseño)

- **D1 — El enlace de Google Maps.** El código no lo genera. ¿Dónde se ve hoy (otra herramienta, una hoja de cálculo, otra aplicación)? ¿Se quiere construir?
- **D2 — Fidelidad.** ¿Basta con mostrar la ruta estimada **solo desde la fecha de activación**, con los puntos para el histórico? ¿O se exige trazado histórico reconstruido, asumiendo que no es el original?
- **D3 — Habilitación por usuario.** Elegir entre la capacidad por rol (a) y un grant individual nuevo y auditado (c). La opción (b) se desaconseja porque rompe el alcance V1.3. Si es (c): quién lo otorga y lo revoca, y si pasa por aprobación de dos personas.
- **D4 — Proveedor de teselas.** Elegirlo y aceptar sus costes y licencia, junto con la apertura de la CSP que exija.
- **D5 — Privacidad.** Consentimiento de los empleados para este uso nuevo, retención de la geometría y de los puntos, y si el enlace externo está permitido.

---

## 10. Conclusión y siguiente paso

- **Conclusión:**
  - La polilínea original **no existe**.
  - Lo fiel y viable es **capturarla a partir de ahora** y mostrar el histórico como puntos registrados.
  - El acceso se puede restringir con el alcance actual, **más** un validador de `trip_id` y `work_session_id`.
  - Un permiso individual de verdad exige un mecanismo nuevo.
- **Siguiente paso:** el paso (2) de la secuencia: revisar con el PO las decisiones D1–D5 y diseñar la vista de Activity (viaje y jornada). Hasta que el diseño esté aprobado **no** se redacta el MD de desarrollo.
- **Información que falta (PENDING VALIDATION):**
  - datos del entorno desplegado;
  - términos y tarifas de TomTom para la geometría y su almacenamiento;
  - el job de purga de `location_fix`;
  - la causa de los 54 `routing_exhausted`.
