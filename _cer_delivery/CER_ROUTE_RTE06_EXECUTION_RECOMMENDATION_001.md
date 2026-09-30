# RTE06 — Recomendación técnica de ejecución

**Para:** el programador/agente que ejecuta RTE06.
**Autoridad:** `CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_INSTRUCTIONS_002.md`.
Este documento **no** la repite: sólo dice qué hacer, en qué orden y con qué
decisiones ya cerradas.

Todo lo que sigue se midió contra el repositorio, no contra un resumen.

---

## A. Estado real encontrado

### CP0 — lo que ya existe y funciona

| Requisito §8 | Estado | Dónde |
|---|---|---|
| `effective_from` en el modelo | **existe** | `vehicles/models.py:269` |
| `effective_to` en el modelo | **existe** | id. |
| Resolución por instante (`from <= T < to`) | **existe** | `VehicleAssignmentsDAO.effective_at()`, `vehicles/dao.py:266` |
| Start Work usa la hora de **ocurrencia** | **existe** | `worksessions/service.py` — calcula el instante primero y luego resuelve |
| Snapshot histórico e inmutable | **existe** | `test_the_vehicle_snapshot_does_not_change_retroactively` |
| E1 asignación futura | **probado** | `test_a_future_assignment_does_not_apply_yet` |
| E2 asignación vigente | **probado** | `test_with_a_current_assignment_the_start_reading_is_pending_and_blocks` |
| E3 asignación terminada | **probado** | `test_an_assignment_with_an_end_date_is_not_current` |
| E4 Start Work offline diferido | **probado** | `test_a_queued_start_work_resolves_the_vehicle_it_had_then` |
| **E5 no solapamiento** | **FALTA** | ver abajo |

Entregado en MR !24. CP0 está al 90%: falta E5 y sólo E5.

### El hueco de E5, con su caso reproducible

Hoy protegen tres cosas, todas parciales o no atómicas:

1. `uq_vehicle_assignment_current` — índice único **parcial**
   (`WHERE effective_to IS NULL`): impide dos asignaciones *abiertas*.
2. `VehicleAssignmentsDAO.overlaps_existing()` — busca una asignación **cerrada**
   que cubra el `effective_from` nuevo.
3. La guarda `desde < anterior.effective_from` dentro de `assign()`.

**El caso que se cuela** (`CONFIRMED`, una sola petición, sin concurrencia):

```
existe:  [Mar 1 → Abr 1)   cerrada
no hay:  ninguna abierta

assign(effective_from = Feb 1)
  → overlaps_existing(Feb 1) busca  from <= Feb 1 AND to > Feb 1
    la de marzo tiene from = Mar 1 > Feb 1  → no la encuentra
  → no hay asignación abierta → la guarda 3 no aplica
  → inserta [Feb 1 → ∞)  que SOLAPA [Mar 1 → Abr 1)
```

Resultado: dos asignaciones simultáneamente vigentes el 15 de marzo, que es
exactamente lo que §8.3 prohíbe. Y `effective_at()` devolvería una de las dos de
forma arbitraria — un snapshot de jornada no determinista.

Segundo problema, menor pero real: `overlaps_existing()` se ejecuta **fuera** de
`transaction()`, así que es un TOCTOU. Dos peticiones concurrentes con `desde`
distintos pasan las dos.

### Componentes reutilizables — verificados, no supuestos

| Necesidad RTE06 | Ya existe | Cómo se usa |
|---|---|---|
| Cola offline durable | `shared/lib/offlineQueue/` + `sync.ts` | `enqueueAction(kind, …)`; el envío es `flushPendingActions()` |
| Idempotencia de acción | `app/core/integration/idempotency.py` | cabecera `Idempotency-Key`, `claim()` / `remember()`; **ojo**: el registro se **purga cada hora** (`_purge_idempotency`) |
| Ocurrencia vs recepción | `_resolve_occurrence()` y pares `*_at` / `*_received_at` | ya está en `trip`, `trip_purpose_change`, `work_session` |
| Scheduler con elección de líder | `app/core/platform/scheduler.py` | `scheduler.register(name, job, **trigger)` y `_only_leader` |
| Configuración de umbrales | `PlatformPolicy` + `app/core/platform/policies.py` | añadir una `PolicyDefinition` con schema Pydantic; se lee con `platform_config.policy("clave")` |
| Auditoría | `app/core/audit/` | `record_event(entity_type=…, action=…, changes=…)` |
| Append-only garantizado por la base | `0001_foundation_baseline.py:417` | `CREATE OR REPLACE FUNCTION {tabla}_is_append_only()` + disparador por fila y por sentencia |
| Enum que genera su propio CHECK | `app/core/enums.py`, `BusinessEnum` | `Enum.check("columna", name=…)` |
| Concurrencia sin pisar | `UPDATE … WHERE estado = 'x'` y `rowcount == 0` → 409 | patrón ya usado en actividades |
| Cliente HTTP de servidor | `httpx>=0.28.1` | ya en `pyproject.toml`; no hace falta añadir dependencia |

**Postgres 16.4**, y `btree_gist` figura como **trusted**
(`pg_available_extensions.trusted = true`). Esto decide C-1.

### Contradicciones y deuda relevante

- **Cero código de geolocalización** en el repositorio. `grep` de
  `location_fix|LocationFix|missing_location|latitude` → sin resultados. CP2 y
  CP3 parten de cero, lo cual es bueno: no hay que desmontar nada.
- **`IdempotencyRecord` se purga cada hora.** No puede ser el ancla durable de
  correlación que pide §14. Ver C-2.
- **El docstring de `VehicleAssignment` afirma** que el índice parcial garantiza
  que «un supervisor no puede tener dos asignaciones vigentes a la vez». Con el
  caso de arriba eso es **falso**. Al cerrar E5 hay que corregirlo; dejarlo sería
  documentación que miente.
- `current_for_supervisor()` significa «la abierta», no «la vigente». Ya está
  documentado con ese alcance estrecho y se usa sólo para guardas de
  desactivación, pero §8.3 dice no *retener* una definición engañosa de
  "current": conviene renombrarlo a `open_for_supervisor` en el mismo cambio,
  para que nadie lo vuelva a confundir.

---

## B. Arquitectura recomendada

Dos módulos nuevos, con la estructura de módulo del repositorio
(`router.py` / `schemas.py` / `models.py` / `dao.py` / `service.py`):

```
app/routers_api/location/     evidencia de ubicación (CP2)
app/routers_api/mileage/      waypoints, segmentos, motor (CP3)
```

Separados porque son dos dominios con dueños distintos (invariante 9): la
ubicación es evidencia de un hecho del dispositivo; el kilometraje es un cálculo
derivado. `mileage` **lee** de `location`; `location` no sabe que `mileage`
existe.

### Evidencia de ubicación

**`location_fix`** — append-only por disparador (añadir a `APPEND_ONLY_TABLES`).

```
id, company_id
work_session_id             jornada dueña — la privacidad se ata aquí
event_kind                  BusinessEnum, con su CHECK generado
subject_kind, subject_id    la correlación exacta — ver C-2
evidence_level              BusinessEnum: fresh | degraded_cached | recovered
latitude, longitude         Numeric(9,6) / Numeric(10,7) — NO float
accuracy_m                  Numeric, nullable
device_captured_at          ocurrencia real de la captura
server_received_at          recepción
source_age_seconds          edad del punto cacheado; null si es fresh
permission_state            lo que dijo el navegador, sin interpretarlo
```

`missing` **no** es un `evidence_level` (§11). El CHECK debe rechazarlo, y debe
haber un test que compruebe que **la base** lo rechaza (invariante 6).

**`missing_location_event`** — append-only, misma correlación, más `reason_code`
(BusinessEnum de hechos observables), `attempts` JSONB y `notification_status`.

### Correlación

Una tupla, sin tabla nueva:

```
(company_id, event_kind, subject_kind, subject_id)
```

con índice **único**: un evento de ciclo de vida tiene como máximo un punto
autoritativo. Los sujetos ya existen y son durables:

| `event_kind` | sujeto | id durable |
|---|---|---|
| `start_work`, `end_work` | `work_session` | `work_session.id` |
| `start_trip`, `arrived` | `trip` | `trip.id` |
| `change_plan` | `trip_purpose_change` | `trip_purpose_change.id` |
| `activity_complete`, `activity_leave` | `activity_execution` | `activity_execution.id` |

`trip_purpose_change` ya guarda `changed_at` (ocurrencia) y tiene id propio: los
Change Plan múltiples **ya son** independientes y ordenables sin inventar nada
(§14, y §32 "preserve occurrence order"). Este es el hallazgo que más trabajo
ahorra en RTE06.

### Recuperación

Ventana acotada, iniciada en el cliente, **finalizada en el servidor**:

- el cliente reintenta en segundo plano durante la ventana y, si obtiene punto,
  lo envía como `recovered` con su `device_captured_at` **real**;
- si la ventana se agota, el cliente llama al endpoint de finalización;
- si el cliente nunca llama —se cerró el navegador, se quedó sin red— el
  **sweeper** finaliza a `missing` pasada la ventana más un margen.

Sin ese tercer camino, un evento se quedaría sin resolver para siempre: la misma
enfermedad que §24 prohíbe para `Pending`, sólo en otra tabla.

### Puerto de routing

Igual que `OdometerReader` en `app/routers_api/odometer/ocr.py`. Ese patrón ya
está probado en este repositorio: hay que copiarlo, no reinventarlo.

```python
class RoadRouter(Protocol):
    async def distance_meters(self, origen: Punto, destino: Punto) -> SegmentResult: ...

get_road_router() / set_road_router()      # como get/set_odometer_reader
```

El dominio nunca ve la respuesta del proveedor: el adaptador devuelve
`SegmentResult(distance_meters, provider, method, version)`.

### Modelo waypoint / segmento

**No** hay tabla de waypoints. El waypoint **es** el `location_fix` del evento
correspondiente; una tabla aparte sería un segundo lugar donde vive el mismo
hecho (invariante 9). La secuencia se ordena por ocurrencia:

```
start_trip  (trip.started_at)
  → change_plan …  (trip_purpose_change.changed_at ASC)
  → arrived  (trip.arrived_at)
```

**`trip_mileage`** — una fila por viaje, con `VersionedMixin`:

```
trip_id (único por compañía), state, total_meters, total_miles,
calculated_at, terminal_reason, attempt_count, next_attempt_at
```

**`trip_mileage_segment`** — append-only, una fila por segmento, con las
coordenadas **copiadas dentro**:

```
trip_mileage_id, sequence
from_*:  latitude, longitude, evidence_level, accuracy_m, captured_at, fix_id
to_*:    idem
distance_meters, provider, method, version, computed_at
haversine_meters        sólo diagnóstico, nunca oficial
```

Copiar las coordenadas en el segmento es **lo que hace la provenance
purge-safe** (§28). `fix_id` va como referencia blanda —sin FK dura, o con
`ON DELETE SET NULL`—: un purgado futuro de evidencia cruda no puede borrar ni
bloquear el kilometraje.

### Ciclo de vida y sweeper

`pending_calculation → calculated | not_calculable | calculation_failed`

La inmutabilidad (§27) se consigue con el patrón de la casa:

```sql
UPDATE trip_mileage SET … WHERE id = :id AND state = 'pending_calculation'
```

`rowcount == 0` significa que ya era terminal, así que no se toca. Ningún
reintento, ningún trabajo duplicado y ningún cambio de proveedor puede alterar un
`calculated`, porque el `WHERE` no se lo permite. No hace falta un disparador
para eso.

Reintento acotado con `next_attempt_at` y backoff. El sweeper se registra en el
**scheduler existente** con `_only_leader` y hace dos cosas: reintentar lo
vencido y terminalizar lo que agotó sus intentos.

---

## C. Decisiones técnicas cerradas

### C-1 · Invariante de no solapamiento

**Problema:** el caso de §A se cuela, y las tres protecciones actuales son
parciales o no atómicas.

**Decisión:** restricción `EXCLUDE` en la base, con `btree_gist`.

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE vehicle_assignment
ADD CONSTRAINT ex_vehicle_assignment_no_overlap
EXCLUDE USING gist (
    company_id WITH =,
    supervisor_profile_id WITH =,
    tstzrange(effective_from, effective_to, '[)') WITH &&
);
```

**Razón:** es la única forma correcta por construcción. Cubre el caso que se
cuela, es atómica frente a concurrencia —no queda TOCTOU que arreglar— y expresa
el intervalo semiabierto `[from, to)` que el modelo ya usa, de modo que cerrar en
`effective_to = desde` y abrir en `effective_from = desde` **no** solapa.

Un disparador PL/pgSQL no sirve: dos inserciones concurrentes no se ven la una a
la otra sin bloqueo explícito, y añadir bloqueo sería reimplementar a mano lo que
`EXCLUDE` ya hace bien.

`btree_gist` es **trusted** en Postgres 16, así que la instala el dueño de la
base sin superusuario — verificado en este entorno. Es infraestructura de base de
datos, no un servicio nuevo: sin contenedor, sin coste.

**En el mismo cambio:**

- borrar `overlaps_existing()` y su llamada — la base ya lo garantiza, y dejar la
  comprobación en Python sería el código muerto que la regla general 2 prohíbe;
- capturar `IntegrityError` **fuera** de `async with transaction()` y devolver 409
  con mensaje legible. Dentro, la sesión queda en rollback y `commit()` lanza
  `PendingRollbackError` → HTTP 500. Ya ha pasado dos veces en este proyecto;
- corregir el docstring de `VehicleAssignment`, que hoy afirma algo falso;
- renombrar `current_for_supervisor` → `open_for_supervisor`.

### C-2 · Clave de correlación

**Problema:** §14 exige correlación exacta por acción, y `IdempotencyRecord` se
purga cada hora, así que no puede ser el ancla.

**Decisión:** la tupla `(company_id, event_kind, subject_kind, subject_id)` con
índice único, apuntando a filas de dominio que ya son durables. El
`Idempotency-Key` se sigue usando para que un reenvío no escriba dos veces, pero
**no** es la identidad del evento.

**Razón:** es el mecanismo más pequeño que cumple —§14 pide exactamente eso—, no
crea tabla ni estado nuevo, sobrevive al purgado, sobrevive al offline y resuelve
C6 (replay duplicado) con una restricción de la base en lugar de con lógica. Los
Change Plan múltiples salen ordenados e independientes sin trabajo adicional.

### C-3 · Coordenadas en `Numeric`, no en `float`

**Decisión:** `Numeric(9,6)` para latitud, `Numeric(10,7)` para longitud.

**Razón:** el kilometraje es un dato que acaba en dinero —alimenta la estimación
de combustible—. Un `double precision` reintroduce ruido de redondeo en la
provenance que §28 obliga a poder auditar años después. Unos 11 cm de resolución
sobran para routing vial.

### C-4 · Umbrales como `PlatformPolicy`

**Decisión:** dos claves nuevas en `policies.py`, `route_location` y
`route_mileage`, cada una con su schema Pydantic.

```
route_location:  cached_max_age_seconds, cached_max_accuracy_m,
                 recovery_window_seconds, sweeper_grace_seconds
route_mileage:   segment_max_meters, implied_speed_max_kmh,
                 max_attempts, backoff_seconds, plausibility_enabled
```

**Razón:** §26 prohíbe fijar los umbrales indicativos de RTE01 como constantes
aprobadas por CER. `PlatformPolicy` ya da validación, persistencia y superficie
de administración; una variable de entorno no se puede ajustar sin desplegar.

Los valores iniciales son **técnicamente defendibles pero no certificados**, y el
reporte debe decirlo así: su validación depende de V-2 y V-5.

### C-5 · Breadcrumbs: no se implementan

**Decisión:** no. Se documenta la elección, como §21 permite expresamente.

**Razón:** son opcionales, no pueden ser kilometraje oficial, no pueden sustituir
un waypoint ausente y no intervienen en ningún criterio de aceptación.
Recogerlos de continuo sería el mayor coste de privacidad de RTE06 sin beneficio
demostrado.

### C-6 · La ventana de recuperación la finaliza también el sweeper

**Decisión:** finalización por endpoint (camino normal) **y** por sweeper
(cliente que no volvió).

**Razón:** sin el sweeper, cerrar el navegador durante la ventana deja el evento
sin resolver para siempre.

### C-7 · El kilometraje se crea al terminar el viaje

**Decisión:** crear `trip_mileage` en `pending_calculation` cuando el viaje
alcanza `ARRIVED` o `INTERRUPTED`, **dentro de la misma transacción** que la
transición. El cálculo lo hace el trabajo de fondo, nunca la petición del
supervisor.

**Razón:** la acción operativa no puede esperar al routing (§36: sin spinner que
bloquee). Y crear la fila en la misma transacción garantiza que ningún viaje
terminado se quede sin fila de kilometraje, que es la única forma de que el
sweeper pueda encontrarlos todos.

---

## D. Routing

### Opciones evaluadas

| Opción | Licencia | Coste | Guardar distancias | Infraestructura |
|---|---|---|---|---|
| Google Routes API | comercial | ~5 USD / 1.000 | **restringido por ToS** | ninguna |
| Mapbox Directions | comercial | ~0,5–2 USD / 1.000 | caché limitada por ToS | ninguna |
| HERE / TomTom / Azure Maps | comercial | por contrato | según plan | ninguna |
| **OSRM** | **BSD-2** | **0** | **sin restricción** | 1 contenedor + extracto OSM |
| **Valhalla** | **MIT** | **0** | **sin restricción** | 1 contenedor + teselas |
| OpenRouteService | GPLv3 | 0 | sin restricción | 1 contenedor |
| GraphHopper | Apache-2 / comercial | 0 / contrato | sin restricción | 1 contenedor (JVM) |

### Lo que decide

§27 y §28 exigen que la distancia de cada segmento se **guarde para siempre** y
siga siendo auditable. Los términos de servicio de Google y Mapbox restringen
precisamente el almacenamiento permanente de contenido derivado de su routing.
Eso no es un detalle de coste: es un conflicto directo con un criterio de
aceptación de RTE06.

Y hay una segunda razón, tomada de la propia instrucción: *los doubles no son por
sí solos evidencia suficiente para cerrar RTE06*. Un motor auto-alojado se puede
levantar y medir de verdad **hoy**, sin credenciales, sin contrato y sin gasto.
Un proveedor comercial deja RTE06 esperando una aprobación externa.

### Recomendación

**Primario: OSRM auto-alojado** — `osrm/osrm-backend`, BSD-2, datos OSM.

Un contenedor, un extracto regional, una llamada HTTP por segmento
(`/route/v1/driving/{lon},{lat};{lon},{lat}?overview=false`), y
`routes[0].distance` en metros. Es la de menor complejidad operativa entre las
auto-alojadas y la más rápida en consulta.

**Fallback: Valhalla auto-alojado** — MIT, mismos datos OSM.

Segundo motor, código base distinto, algoritmo distinto, coste marginal cero,
licencia igualmente permisiva. Cubre el fallo que §25 describe —el proveedor
falla temporalmente— sin recurrir a otra fórmula de distancia.

El fallback **no es** Haversine, ni el odómetro, ni un total parcial: los tres
están prohibidos (§20, §25). Si los dos motores fallan y se agota el reintento
acotado, el estado terminal correcto es `Calculation Failed`, y eso es una
respuesta válida del sistema, no un fallo de RTE06.

**Manejo de fallos.** Timeout por segmento (5 s inicial, configurable en
`route_mileage`); mapeo explícito de error a `SegmentOutcome`
(`ok | transient | permanent`); reintento acotado con backoff sólo sobre los
transitorios; `permanent` va directo a terminal. Un segmento ya válido **nunca**
se recalcula (§25: no descartar provenance válida).

**Observabilidad.** Proveedor, método y versión en cada fila de segmento;
transiciones de estado en `audit_event`; el logger existente para latencia y tasa
de fallo. Coordenadas **fuera** de los logs ordinarios (§35).

**Reemplazabilidad.** El puerto `RoadRouter`. Cambiar de motor es escribir un
adaptador; el dominio no cambia. Un proveedor comercial se enchufa ahí el día que
CER lo quiera, sin tocar el motor de kilometraje.

**¿Requiere decisión de CER?** **No, ni para desarrollar ni para probar.** La
suite automatizada usa el doble determinista y no depende de la red. Levantar el
contenedor es una acción de DevOps, no un producto ni un contrato.

Lo que sí conviene que Rodrigo **sepa** —informativo, no bloqueante— es que la
vía comercial habría traído gasto recurrente *y* un conflicto de términos de
servicio con la provenance permanente. Por eso no se recomienda.

---

## E. Secuencia de implementación

El orden importa por una razón concreta: la forma de la correlación (C-2) y el
hecho de que los segmentos llevan las coordenadas copiadas (C-3, §28) tienen que
estar decididos **antes** de escribir la primera migración de CP2, o CP3 obliga a
reformar las tablas de CP2.

| # | Unidad funcional | Cierra | Verde al terminar |
|---|---|---|---|
| 1 | `EXCLUDE` + extensión + migración; borrar `overlaps_existing`; capturar `IntegrityError` fuera de la transacción; docstring; renombrar `open_for_supervisor` | **CP0 / E5** | tests E5 + regresión de odómetro RTE04 |
| 2 | Auditoría escrita, decisiones C-1..C-7, inventario V-1..V-5, plan de migración | **CP1** | secciones 1–9 del reporte |
| 3 | `location_fix` y `missing_location_event`: modelos, enums con CHECK, append-only, índice único de correlación, migración | CP2 | la base rechaza `missing` como nivel, coordenadas fuera de rango, correlación duplicada, `UPDATE`/`DELETE` |
| 4 | Endpoint de ingesta: idempotente, tenant del contexto, propiedad de la acción verificada, ocurrencia ≠ recepción, frontera de jornada ACTIVE | CP2 | autorización, aislamiento, replay, evidencia ajena rechazada |
| 5 | Finalización de `missing`: endpoint + sweeper | CP2 | G5 — exactamente un evento, sin coordenada fabricada |
| 6 | Cliente: `shared/lib/location/`, enganchado en los siete puntos de acción; no bloqueante; cola offline; aviso de privacidad una sola vez | CP2 | G1–G4, C5, travesías sin paso visible |
| 7 | Puerto `RoadRouter`, adaptador OSRM, doble determinista, mapeo de fallos | CP3 | adaptador, timeout, transitorio vs permanente |
| 8 | Waypoints ordenados, routing por segmentos, plausibilidad, agregación, máquina de estados, reintento, sweeper | CP3 | M1–M3, C1–C8, R1–R5 |
| 9 | Contrato de lectura de jornada (§33): servicio y consulta, **sin UI** | CP3 | suma de jornada, recuento de no resueltos |
| 10 | Suite de escenarios, regresión RTE03/04/05, typecheck, lint, build, migraciones, reporte 001 (38 secciones) | **CP4** | H1–H3, L1–L6, y todo lo anterior |

Las unidades 3 y 7 pueden ir en paralelo si hay dos manos: no se tocan.

Lo que **no** se debe hacer para ahorrar tiempo: meter CP2 y CP3 en una sola
migración. Son dos entregas verificables, y la de CP2 tiene que estar verde antes
de que el motor dependa de ella.

---

## F. Estrategia de pruebas

Junto a cada unidad, no al final. Las que impiden falsos positivos:

**Unidad 1 — solapamiento.** El caso reproducible de §A tal cual: cerrada
`[Mar 1, Abr 1)`, `assign(Feb 1)` → **409**. Sin ese caso concreto, un test de
solapamiento genérico pasa con las protecciones actuales y no prueba nada. Y
además: cerrar en `effective_to = desde` y abrir en `effective_from = desde` debe
**seguir funcionando** — si ese test falla, la restricción está mal escrita.

**Unidad 3 — la base, no Python.** `INSERT` directo con
`evidence_level = 'missing'` → rechazado. Latitud 91 → rechazado. Dos filas con
la misma tupla de correlación → rechazado. `UPDATE` y `DELETE` sobre
`location_fix` → rechazados por el disparador.

**Unidad 4 — inyección cruzada.** Evidencia de otro supervisor, de otra jornada y
de otro tenant: **404, no 403** (regla 8 de backend). Y evidencia enviada con la
jornada ya `ended` → rechazada, salvo la excepción acotada de End Work.

**Unidad 6 — no bloquear.** La aserción que importa no es que se capture: es que
la acción operativa **termina igual** cuando el permiso está denegado (G2).
Medirlo sin conceder el permiso de geolocalización y comprobando que el flujo
RTE05 llega a `What's next?`.

**Unidad 8 — las tres que más fácil se falsean:**

- **C4, Change Plan Missing.** Start y Arrived válidos, Change Plan ausente →
  `Not Calculable`. El test tiene que comprobar *además* que el total **no** es
  `route(Start, Arrived)`. El atajo silencioso es el fallo que persigue §17, y un
  test que sólo mire el estado lo dejaría pasar si alguien calcula y descarta.
- **C7, texto de destino.** Mismo par de coordenadas, texto de destino distinto →
  **la misma distancia**. Prueba que no hay geocodificación.
- **H2, purgado.** `DELETE FROM location_fix` dentro del test, y después el
  kilometraje y toda su provenance siguen legibles. Si falla, las coordenadas no
  se copiaron en el segmento.

**Unidad 8 — inmutabilidad.** Reejecutar el trabajo sobre un viaje ya
`calculated` y comprobar `total_meters` idéntico y `calculated_at` intacto: con
proveedor cambiado, con umbral cambiado y con el trabajo duplicado (H1).

**Doble determinista, no red.** El adaptador por defecto en tests es el fake,
igual que `NoSuggestionReader`. Una prueba contra OSRM real va marcada y sólo
corre si `ROUTE_ROUTING_URL` está definida: la suite normal no puede depender de
un contenedor (§40).

**Y una medición real de OSRM** — un par de coordenadas conocidas, distancia
comparada con la esperada — registrada en el reporte como V-3 `CONFIRMED`. Es lo
que convierte la integración en real en lugar de un fake declarado resuelto.

---

## G. Riesgos reales

| Riesgo | Por qué puede impedir el cierre | Mitigación |
|---|---|---|
| **V-1, V-2 y V-5 no son producibles aquí** — iOS Safari y Android Chrome reales, muestreo de precisión en campo, distribución Fresh/Degraded/Recovered/Missing | §38 dice que la emulación de escritorio **no** es validación de dispositivo real, y que la evidencia ausente no se convierte en PASS | Se declaran `PENDING VALIDATION` con su razón. No bloquean los criterios 1–40, pero **el reporte no puede llamarlos CONFIRMED**, y hay que decírselo a CER al entregar, no en la letra pequeña |
| Provisión del contenedor OSRM en el entorno compartido | Sin él no hay kilometraje en producción, aunque los tests estén verdes | Acción operativa de DevOps, declarada en el reporte. Local no es compartido |
| `NullPool`: cada consulta abre conexión física | Las travesías de navegador largas dan timeouts que parecen flakiness | Lotes cortos de navegador, como en RTE05 |
| `btree_gist` en el entorno compartido | La migración falla si el usuario no tiene `CREATE` en la base | Es *trusted* en PG16: basta ser dueño. Verificarlo antes de desplegar; es la única dependencia nueva de CP0 |
| Que un Change Plan quede sin waypoint por diseño del cliente | Convertiría C4 en el caso normal en vez de la excepción | La captura del Change Plan se engancha en el **mismo** despacho de acción que el cambio, no en un efecto aparte que se pueda olvidar |

---

## H. Decisiones que requieren a Rodrigo

**No Product Owner decision required to proceed.**

Una nota informativa, no una decisión: el routing se recomienda auto-alojado
—OSRM primario, Valhalla de reserva— en parte porque las alternativas comerciales
restringen por contrato el almacenamiento permanente de las distancias que §28
obliga a conservar. Si CER prefiriera un proveedor comercial, **eso sí** sería
decisión suya, por gasto y por términos de servicio, y habría que plantearla
antes de CP3.

Y una advertencia de expectativa, tampoco una decisión: V-1, V-2 y V-5 llegarán a
certificación como `PENDING VALIDATION`. No es alcance incompleto — es la
clasificación que §38 prescribe para evidencia que este entorno no puede
producir.

---

## I. Recomendación final al programador

Ejecuta en el orden de §E, sin adelantar unidades.

1. **Cierra CP0** con la unidad 1: la restricción `EXCLUDE`, el caso reproducible
   de §A como test, y la limpieza que arrastra — borrar `overlaps_existing`,
   capturar `IntegrityError` fuera de la transacción, corregir el docstring que
   hoy miente, renombrar `open_for_supervisor`. Migración con `downgrade`, un
   solo head.
2. **CP1 es documento**, y este archivo es casi todo su contenido: pásalo a las
   secciones 1–9 del reporte con la evidencia medida, no resumida.
3. **CP2 en orden 3 → 4 → 5 → 6**, con los tests de cada unidad escritos a la
   vez. No pases a 6 sin que 3 y 4 estén verdes: un fallo de cliente sobre un
   servidor no probado es indistinguible de un fallo de servidor.
4. **CP3 en orden 7 → 8 → 9.** Levanta OSRM de verdad una vez y registra la
   medición como V-3; el resto de la suite va con el doble.
5. **CP4:** escenarios completos, regresión RTE03/04/05 por lotes, typecheck,
   lint, build de producción, `alembic heads` = 1, y el reporte
   `CER_ROUTE_RTE06_GEOLOCATION_MILEAGE_ENGINE_REPORT_001.md` con sus 38
   secciones.
6. **STOP.** No empieces RTE07.

Dos cosas que no se negocian por conveniencia: ningún criterio se marca
`CONFIRMED` sin la evidencia nombrada al lado, y ningún control se debilita para
poner un test en verde. Si algo de §45 aparece de verdad, para y dilo — pero
ninguno de los catorce está activado hoy.
