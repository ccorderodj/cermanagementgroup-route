# RTE-LOC-01 — Diagnóstico AS-IS de datos de ubicación y archivado mensual

**Fecha:** 2026-10-20 · **Tipo:** diagnóstico, sin implementación · **Autor:** agente técnico, para el PO

## 1. Executive summary · Readiness: **READY WITH GAPS**

- **CONFIRMED: CER Route guarda puntos de evento, no una traza periódica.**
  - Un punto por evento del día: Start Work, salida de viaje, cambio de plan, llegada, fin o abandono de actividad, y End Work.
  - Cada punto lleva tenant, jornada, sujeto, precisión, hora del dispositivo, hora del servidor, nivel de evidencia y estado del permiso.
  - Cuando no hay punto, se registra la ausencia con su motivo.
  - No hay `watchPosition`, ni muestreo por intervalo, ni captura en segundo plano.
- **CONFIRMED: con lo que hay hoy ya se puede archivar un histórico de eventos.** Un histórico de trayectoria continua requiere RTE-LOC-02: una nueva captura periódica, una tabla nueva y decisiones del PO.
- **Calidad de los puntos existentes, buena** (copia local, 925 puntos):
  - 0 puntos en `0,0`;
  - 0 duplicados, porque la clave única lo impide;
  - el 72 % con precisión ≤ 20 m;
  - mediana de 1,2 s entre la captura y la llegada al servidor.
- **Cobertura, ~77–84 % de los eventos.** Las ausencias se deben sobre todo a **permiso denegado** (162 de 200).
- **Bloqueos para el archivado mensual (GAP):**
  1. **No hay almacenamiento de objetos confirmado** en el despliegue: el disco del contenedor es efímero.
  2. **`location_fix` es de solo inserción**, con triggers que bloquean `DELETE` y `TRUNCATE`, vigilados por el control de integridad. Una purga tras exportar exige una decisión explícita.
  3. **No se auditan las lecturas ni las exportaciones.**
- **Brechas de privacidad o seguridad (GAP):**
  - la cola del dispositivo no se separa por usuario ni se borra al cerrar sesión;
  - el aviso de privacidad existe en el código, pero **ninguna pantalla lo muestra**.

## 2. Repository & environment baseline

| Item | Valor |
|---|---|
| Rama / commit inspeccionado | `dev` @ `4bc266e` (fusión de MR !112) |
| Migración (head local) | `0027_activity_email_obs` · origen de los datos de ubicación: `0010`, `0011`, `0013`, `0014`, `0015` |
| Entorno observado | **Solo la base local**: copia del entorno DigitalOcean `dev`, con datos del 01/10/2026 al 20/10/2026. **No** es el entorno compartido actual |
| No inspeccionado | Base y almacenamiento de DigitalOcean, configuración real de `document_storage`, buckets. Sin acceso → `PENDING VALIDATION` |
| Cambios realizados | Ninguno en código, datos ni configuración (ver §13, `git status`) |

## 3. Source inventory

| Fuente | Qué es | Estado | Evidencia |
|---|---|---|---|
| `location_fix` | **Punto crudo**, uno por evento del ciclo de vida | AS-BUILT | `app/routers_api/location/models.py:219-312`; migración `0010` |
| `missing_location_event` (+ `missing_location_notification`) | Hecho «no hubo punto» con motivo e intentos. **Sin coordenadas** | AS-BUILT | `location/models.py:315-507`; `0010`, `0011`, `0014` |
| `trip_mileage_segment` | **Copia** de los pares de puntos usados para el millaje oficial (TomTom/OSRM/Valhalla) | AS-BUILT | `mileage/models.py:188-272`; `mileage/service.py:391-449` |
| `trip_mileage` | Estado del millaje por viaje. Sin coordenadas | AS-BUILT | `mileage/models.py:105-185` |
| `work_session`, `trip`, `trip_purpose_change`, `activity_execution` | Horas del dispositivo y del servidor, `client_action_key`, zona y desfase (solo en la jornada). **Sin coordenadas** | AS-BUILT | `0013`, `0015`; `worksessions/models.py:195-236` |
| `POST /api/location/evidence` · `POST /api/location/missing` · `GET /api/location/policy` | Ingesta y umbrales | AS-BUILT | `location/router.py:51-119` |
| Route Map Viewer `GET /api/activity-explorer/trips/{id}/map` | Marcadores sin líneas. Lee **solo** `trip_mileage_segment` de viajes calculados, nunca `location_fix` | AS-BUILT | `activityexplorer/route_map.py:35-90` |
| Cliente: `shared/lib/location/location.ts` | `getCurrentPosition` por evento: fresco → caché → recuperación 180 s → ausencia | AS-BUILT | `location.ts:242-704` |
| Cola sin conexión: IndexedDB `cer-route-offline` v3 | `pending_location_evidence`, con la clave de correlación por evento | AS-BUILT | `offlineQueue.ts:123-277` |
| Traza periódica, breadcrumbs, geofence, PostGIS, rumbo, velocidad, altitud, id de dispositivo | — | **NOT IMPLEMENTED** («§21 breadcrumbs opcional, no implementado», `location/models.py:222-225`) | búsqueda negativa |
| GPS en las fotos de odómetro | El EXIF se elimina en el derivado; el **original** se conserva | **PENDING VALIDATION** (puede retener GPS EXIF) | `core/storage/media.py:10, 19-21, 202-212` |

**Caminos descartados:**
- **Inicio de actividad:** no captura ubicación, a propósito (`location.ts:49`).
- **Odómetro:** sin ubicación.
- **Live y Reports:** no leen coordenadas.

## 4. Data dictionary (`location_fix`, fuente principal)

| Campo | Tipo | Null | Significado | Origen del tiempo | Estado |
|---|---|---|---|---|---|
| `company_id` | int, FK compuesta | no | Tenant, **del subdominio y la sesión**, nunca del cuerpo | — | AS-BUILT |
| `work_session_id` | int, FK (id, company) | no | Jornada | — | AS-BUILT |
| `event_kind` / `subject_kind` / `subject_id` | str / str / int | no | Evento y sujeto (polimórfico, sin FK) | — | AS-BUILT |
| `evidence_level` | `fresh` / `degraded_cached` / `recovered` | no | Cómo se obtuvo | — | AS-BUILT |
| `latitude` / `longitude` | numeric(9,6) / (10,7) | no | Coordenadas; CHECK de rango | — | AS-BUILT |
| `accuracy_m` | numeric(10,2) | sí en BD; la API la exige | Precisión horizontal | — | AS-BUILT |
| `device_captured_at` | timestamptz | no | Hora del punto (`position.timestamp`) | Dispositivo | AS-BUILT |
| `server_received_at` | timestamptz | no | Recepción | Servidor | AS-BUILT |
| `source_age_seconds` | int | sí | Edad de la caché (solo `degraded_cached`) | Dispositivo | AS-BUILT |
| `permission_state` | str | sí | `granted` / `prompt` / `denied` / `unavailable` | Cliente (no verificable) | AS-BUILT |
| usuario | — | — | Implícito por `work_session.user_id`. **No hay columna** | — | PARTIAL |
| zona / desfase | — | — | Solo en la jornada (`start_time_zone`, `*_utc_offset_minutes`) | — | PARTIAL |
| id de dispositivo, rumbo, velocidad, altitud | — | — | No existen | — | NOT IMPLEMENTED |

- **Deduplicación:** índice único `(company_id, event_kind, subject_kind, subject_id)`. Una repetición devuelve el existente y nunca sobrescribe (`location/service.py:203-247`).
- **Integridad:** triggers `trg_location_fix_append_only` / `_no_truncate`, vigilados por `core/platform/integrity.py:35-47`.

## 5. Data quality & volume (copia local, agregados, sin coordenadas)

Cifras sacadas con `SELECT` agregados sobre la copia local. Hay **un solo tenant con datos**. **PENDING VALIDATION** en el entorno compartido.

| Métrica | Valor |
|---|---|
| Puntos `location_fix` | **925** (01–20/10/2026) · 114 jornadas con puntos · media **8,1** por jornada (máx. 32) |
| Por evento | start_work 102 · end_work 103 · start_trip 248 · arrived 246 · change_plan 13 · activity_complete 208 · activity_leave 5 |
| Nivel de evidencia | fresh 892 · degraded_cached 31 · recovered 2 |
| Permiso al capturar | granted 867 · prompt 58 |
| Cobertura de jornadas | Start Work con punto 102/132 (**77 %**) · End Work con punto 103/128 cerradas (**80 %**) |
| Cobertura de viajes | salida 248/299 (**83 %**) · llegada 246/298 llegados (**83 %**) |
| Cobertura de actividades | con algún punto 213/255 (**84 %**) |
| Ausencias (`missing_location_event`) | 200: `permission_denied` 162 · `no_client_report` 37 · `recovery_accuracy_rejected` 1 |
| Precisión | nulos 0 · p50 **11,8 m** · p90 51,7 m · p99 104 m · máx. 127 m · ≤ 20 m: 667 (**72 %**) · > 100 m: 15 |
| Coordenadas `0,0` | **0** |
| Desfase recepción − captura | p50 1,2 s · p90 17 s · p99 148 s · > 10 min: 0 |
| Reloj del dispositivo adelantado | 163 puntos, ≤ 2,0 s (benigno; el servidor rechaza más de 5 min en el futuro) |
| Cronología fuera de orden / puntos tras End Work + 5 min | 0 / 0 |
| Huecos entre puntos de una jornada | mediana ~1 min · p90 **134 min** → confirma que la captura es **por evento**, no periódica |
| Jornadas que cruzan medianoche | 10 (fechadas por `session_date` de inicio) · duración media 9,6 h, p90 ~24 h (jornadas olvidadas) |
| Usuarios con jornada por día | media 4,7 · máx. 8 |
| Tamaño | 434 KB para 925 filas, con índices → **~470 B/fila** |
| Millaje oficial | calculated 169 (57 %) · routing_exhausted 54 · start_waypoint_missing 51 · implausible_segment 22 · arrival_waypoint_missing 2 |

**Fórmula de densidad para una futura traza periódica (supuestos, no hechos):**
- puntos/día = U × H × 3600 / I
- bytes/día ≈ puntos/día × B

Con U = 10 usuarios, H = 9,6 h, I = 60 s y B ≈ 470 B: **5.760 puntos/día ≈ 2,7 MB/día ≈ 80 MB/mes**. Con I = 30 s, el doble. Hay que añadir la sobrecarga del muestreo por distancia si se elige.

## 6. Gap analysis

| Expected | Implemented | Evidence | Gap | Impact |
|---|---|---|---|---|
| Puntos con contexto suficiente | Tenant, jornada, sujeto, precisión, dos horas y nivel | §4 | Sin `user_id` directo; sin zona en el punto | Bajo: se derivan de la jornada |
| Traza periódica Start–End Work | Solo eventos | Sin `watchPosition` | **NOT IMPLEMENTED** | No hay recorrido real entre eventos |
| Captura en segundo plano | No | Web pura: sin PWA, service worker ni envoltorio nativo | **No viable en web** | Con la app cerrada o la pantalla bloqueada no hay puntos |
| Cola sin conexión segura por usuario | Cola por origen (subdominio), no por usuario; no se borra al cerrar sesión | `offlineQueue.ts`, `logout.ts:6-16` | GAP | Un dispositivo compartido podría enviar puntos de otro usuario con la sesión del siguiente. La API valida la jornada activa del usuario autenticado, lo que mitiga parcialmente |
| Archivo mensual recuperable | No existe | §9 | **NOT IMPLEMENTED** | — |
| Purga tras archivar | Bloqueada por diseño (triggers append-only) | `0010:230-256`, `integrity.py` | Requiere decisión | Hoy el crecimiento es pequeño (~470 B/evento) |
| Auditoría de lecturas y exportaciones | No | Sin `record_event` en exportaciones | GAP | Sin rastro de quién vio o exportó |
| Aviso al trabajador | Código del aviso existe, **sin uso** | `privacyNotice.ts` | GAP | Riesgo legal (§8) |
| Separación del millaje oficial | Sí: el millaje copia sus puntos en `trip_mileage_segment` | `mileage/service.py:391-449` | — | Un archivo de `location_fix` no altera el millaje |

## 7. Mobile/background feasibility (CONFIRMED por código)

- **Tipo de cliente:** web adaptable servida por Jinja (`templates/base.html:5`). Sin manifest, service worker, Capacitor ni Cordova.
- **Cuándo se pide la ubicación:** solo en los 7 eventos, con `getCurrentPosition` (`location.ts:242-262`).
  - **Primer intento:** alta precisión, 10 s, punto fresco.
  - **Segundo:** caché de hasta 300 s y 500 m.
  - **Tercero:** recuperación durante 180 s.
  - Umbrales en la política de plataforma `route_location` (`policies.py:72-77`).
- **Sin permiso:** se bloquea abrir trabajo nuevo (jornada, plan, salida, cambio de plan). Cerrar trabajo sigue permitido (`operationalActions.ts:31-62`). La captura en sí es silenciosa y registra la ausencia.
  - El encabezado `X-Location-Permission` lo envía el cliente y **el servidor no puede verificarlo** (`location/permission_gate.py:22-27`).
- **Sin señal, pantalla bloqueada o app minimizada:** la captura en curso vive en memoria. Si se cierra la página durante la recuperación de 180 s, se pierde y el barrido del servidor registra `no_client_report` (37 casos). No hay wake lock ni Background Sync.
- **Imprescindible para una traza Start–End Work:** `watchPosition` con la página abierta, y un buffer por usuario y por jornada con identificador idempotente por punto.
- **No garantizable en web:** captura con la pestaña en segundo plano o la pantalla bloqueada. Navegadores y sistemas operativos limitan los temporizadores y la geolocalización. Garantizarla requeriría una app nativa o híbrida con permiso de ubicación «siempre», que es una decisión de producto, legal y de coste.
- **Detener la captura:** hoy no hay captura continua que detener. Para RTE-LOC-02 debe pararse en End Work, al cerrar sesión, al revocar el permiso y al cambiar de usuario o tenant (los eventos `visibilitychange` y `PermissionStatus.onchange` ya existen en `permission.ts:222-275`).

## 8. Security / privacy / audit

| Control | Hoy | Riesgo / pendiente |
|---|---|---|
| Tenant y usuario | Sesión y subdominio; el cuerpo usa `extra="forbid"`; jornada **activa del usuario** obligatoria; sujeto ajeno → 404 | OK (CONFIRMED) |
| Antigüedad y reloj | Captura > 5 min en el futuro o > 30 días → rechazo | Manipulación de reloj limitada, no eliminada |
| Falsificación (GPS falso), replay, varios dispositivos | Replay sin efecto, por la clave única; **no hay detección de ubicación falsa ni id de dispositivo** | Riesgo aceptado hoy; documentar en LOC-02 |
| Alcance jerárquico | El visor exige `route.activity.read` + `route.activity.map.read` (a demanda) y el alcance de rama; fuera → 404 | Para el historial, una capacidad **nueva** y separada; no heredarla de los reportes |
| Logs | Auditoría de la ingesta **sin coordenadas** (`location/service.py:249-264`); el error de TomTom oculta la clave | OK |
| Cifrado | En tránsito, TLS; en reposo, el de la BD gestionada (PENDING VALIDATION); los objetos S3 se suben sin SSE | GAP para el archivo |
| Auditoría de consultas y exportaciones | No existe | GAP |
| Aviso y consentimiento | Aviso sin uso | **Revisión legal humana** por estado o jurisdicción; no se concluye que un aviso baste |
| Retención | Indefinida; no hay purga | Decisión del PO (§11) |

## 9. Archive feasibility (diseño, NO implementación)

**Lo que existe y se puede reutilizar (CONFIRMED):**
- Programador interno APScheduler con líder por candado PostgreSQL, que admite `cron` (`core/platform/scheduler.py:30-170`).
- Patrón de job CLI `--once` (`activityemails/jobs.py`) y su latido.
- `S3CompatibleStorage`, compatible con DigitalOcean Spaces, en la integración `document_storage` (`core/storage/base.py:289-459`).
- Secretos AES-GCM.

**Lo que falta (GAP):**
- **Almacenamiento:**
  - un bucket confirmado (la App Spec no tiene ninguno y el código dice que el piloto no tiene);
  - una integración de archivo **separada** (hoy solo `document_storage`, con prefijo `evidence/`);
  - subida por partes y en streaming (`put` recibe `bytes` enteros);
  - listado de objetos;
  - SSE.
- **Exportación y auditoría:**
  - exportación CSV o comprimida;
  - auditoría de exportación;
  - registro de ejecuciones del job.
- **Riesgo actual:** `get_storage()` cae a disco local en silencio si falta el secreto de S3 (`base.py:447-459`).

**Propuesta para RTE-LOC-03 (para aprobar):**
1. **Destino:** bucket **privado** separado del de evidencias, con una llave limitada a ese bucket. Proveedor y creación, sujetos a aprobación. Nunca el disco del contenedor.
2. **Partición y nombre:** `tenant={id}/year=YYYY/month=MM/location_fix-v1.csv.gz`, más `manifest.json` con versión de esquema, rango, recuento, SHA-256, `generated_at` y job_id. CSV comprimido por simplicidad y por poder restaurarse sin herramientas; Parquet si el volumen crece.
3. **Corte:** mes calendario cerrado, más un **margen para datos tardíos**. El retraso observado es p99 148 s; la cola tiene una vida de ~5 min. Se exporta el mes M el día D+N de M+1, con instantánea transaccional (`REPEATABLE READ`) por tenant.
4. **Verificación:** releer el objeto, y comparar el recuento y el SHA con el manifiesto antes de marcar el mes como archivado. Registro por tenant y mes, idempotente: un mes ya verificado no se reexporta. Alarma si falla, y sin purga parcial.
5. **Purga:**
   - **No** un `TRUNCATE` ni un `DELETE` sobre `location_fix` tal como está.
   - **Opción A, recomendada:** dejar `location_fix` (eventos, pocos KB/mes) **fuera** de la purga y aplicar la retención solo a la nueva tabla de traza periódica de LOC-02, particionada por mes y cuyo borrado es `DROP PARTITION`, solo después de verificar.
   - **Opción B:** cambiar el control de integridad para permitir borrados autorizados y auditados en `location_fix`. Requiere decisión explícita.
6. **Lectura futura:** un índice o catálogo de archivos por tenant y mes, y restauración a una tabla de staging bajo demanda. **No** se prometen consultas interactivas sobre los archivos.
7. **Coste:** ~80 MB/mes sin comprimir para 10 usuarios a 60 s; CSV.gz ~5–10× menos. Coste de almacenamiento marginal; PENDING de la tarifa real.

**Histórico solo de eventos:** posible hoy, con `location_fix` más `missing_location_event`. **Trayectoria continua:** requiere LOC-02.

## 10. Proposed minimum data contract (sin DDL)

| Campo | Clase | Justificación |
|---|---|---|
| `company_id`, `work_session_id`, `point_id` | required | Aislamiento y relación (servidor) |
| `user_id` | derived (de la jornada) | No confiar en el cliente |
| `latitude`, `longitude`, `accuracy_m` | required | Utilidad para distancias; precisión obligatoria para filtrar |
| `device_captured_at`, `server_received_at` | required | Temporalidad y detección de tardíos y de reloj |
| `client_point_id` (UUID por punto) | required | Deduplicación en reintentos y multidispositivo |
| `source` (`event` / `periodic` / `recovered`), `event_kind` o nulo | required | Separar evento de traza |
| `permission_state`, `evidence_level` | optional | Calidad |
| `speed_mps`, `heading_deg` | optional, **solo si el navegador lo da y se aprueba** | Coherencia de trayecto; no imprescindibles |
| `altitude` | not recommended | Sin uso previsto |
| IP, id de hardware, Wi-Fi, contactos, user-agent persistente | **prohibited** | PII innecesaria |

## 11. Decisions required from PO

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| D1 | Alcance de captura | (a) solo eventos (hoy) · (b) periódica **con la app abierta** Start–End Work · (c) segundo plano real (exige app nativa) | **(b)**, sin prometer segundo plano |
| D2 | Muestreo | Intervalo de 30 / 60 s, o por distancia (≥ 100 m), con el umbral de precisión vigente (100 m) | 60 s o 100 m, lo que ocurra antes |
| D3 | Ventana y corte | Mes calendario + margen, o ventana móvil de 30 días | Mes calendario + margen de 7 días |
| D4 | Destino del archivo y quién restaura | Bucket privado dedicado; restauración por un admin de plataforma con auditoría | Bucket dedicado; restaura solo plataforma |
| D5 | Purga | A: retención solo en la nueva tabla periódica · B: abrir `location_fix` a borrado auditado | **A** |
| D6 | Quién ve y exporta el historial | Nueva capacidad a demanda, más alcance de rama, más auditoría de cada lectura y exportación | Sí, separada de los reportes |
| D7 | Aviso y consentimiento | Activar el aviso existente y revisarlo legalmente por estado | Revisión legal **antes** de LOC-02 |
| D8 | Higiene del dispositivo | Partir la cola por usuario y vaciarla al cerrar sesión | Incluir en LOC-02 |

## 12. Next checkpoints (solo definidos, sin iniciar)

- **RTE-LOC-02: captura y almacenamiento.**
  - Depende de D1, D2, D6, D7 y D8.
  - Incluye:
    - `watchPosition` con la app abierta y su parada en los 6 casos;
    - un buffer en el dispositivo por usuario y jornada, con `client_point_id`;
    - un endpoint por lotes idempotente;
    - una tabla particionada por mes;
    - una capacidad nueva y auditoría de lecturas.
  - Pruebas: deduplicación, sin conexión, revocación, cambio de usuario, medianoche, aislamiento de tenant, y que el millaje oficial no cambie.
- **RTE-LOC-03: archivo mensual.**
  - Depende de D3, D4 y D5, y de que exista el bucket.
  - Incluye:
    - job `cron` con líder e idempotencia por tenant y mes;
    - CSV.gz con manifiesto y SHA;
    - verificación por relectura;
    - purga solo tras verificar;
    - restauración a staging;
    - alarma.
  - Pruebas: fallo a medias, dato tardío, dos réplicas, restauración sin mezclar tenants.

## 13. Evidence appendix

**Casos LC (respuesta corta):**
- **LC-01:** sí, Start Work y End Work, con precisión y las dos horas (77 % y 80 % de cobertura).
- **LC-02:** solo salida, cambio de plan y llegada; nada intermedio.
- **LC-03:** no; la jornada activa y el sujeto son obligatorios.
- **LC-04:** §7.
- **LC-05:** `session_date` de inicio; 10 jornadas cruzan medianoche; la zona está solo en la jornada.
- **LC-06:** clave única por evento, más clave de correlación en el dispositivo; un punto por evento evita el problema multidispositivo, pero sin id de dispositivo.
- **LC-07 y LC-08:** §9 (manifiesto, verificación, idempotencia, partición por tenant).
- **LC-09:** faltan los puntos intermedios y la velocidad/rumbo opcionales; el millaje oficial no se toca.
- **LC-10:** hoy, el visor con `route.activity.map.read` y alcance de rama; sin auditoría de lectura (GAP).

**Consultas usadas (solo lectura y agregados, sin resultados personales):**
- `information_schema.columns`, `pg_constraint`, `pg_indexes` y `pg_trigger` sobre `location_fix`, `missing_location_event`, `missing_location_notification`, `trip_mileage` y `trip_mileage_segment`;
- `count` / `percentile_cont` por evento, nivel, permiso y precisión;
- `extract(epoch from server_received_at - device_captured_at)`;
- coberturas con `exists(...)`;
- `lag()` para orden y huecos;
- `pg_total_relation_size('location_fix')`.

**Tests existentes relacionados:**
- `tests/e2e/test_rte06_offline_durability_browser.py`;
- `test_rte06_recovery_accuracy_browser.py`;
- `test_rte06_bounded_queue_browser.py`;
- `test_rte06_silent_capture_browser.py`;
- `test_location_permission_gate_browser.py`.

En la regresión del 20/10, **5 de los RTE-06 fallan desde antes**, causa no diagnosticada. Afectan a la captura sin conexión y a la recuperación por precisión, que habría que revisar antes de LOC-02.

**Inconsistencias encontradas en comentarios del código (sin corregir):**
- el docstring del programador interno cita una «re-scan de cuarentena» y «jobs de retención» que no existen;
- el comentario de `integrity.py:43-45` sobre el trigger de `missing_location_event` está desactualizado;
- `MileageService.ensure_pending` dice ejecutarse dentro de la transacción, pero corre después.

**Sin cambios:** `git status` limpio, salvo este informe.
